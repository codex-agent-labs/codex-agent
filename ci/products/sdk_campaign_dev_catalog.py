"""Assemble an exact same-PR SDK reuse catalog without granting release trust."""

from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
import tempfile

from .index import IndexEntrySource, SignedProductIndex, _verify_index_receipt, verify_signed_product_index, write_signed_product_index
from .inventory import publish_regular_tree, regular_file_inventory, sha256_bytes
from .receipt import validate_producer
from .registry import PhaseInstanceId
from .restore import _snapshot_archive, object_relative_path, verify_object
from .sdk_campaign_selection import SDK_CAMPAIGN_INSTANCES, verify_sdk_campaign_selection
from .sdk_package import _require_capability_output_separate
from .signatures import generate_development_key


def stage_sdk_same_pr_catalog(
    sources: Mapping[PhaseInstanceId, IndexEntrySource],
    envelopes: Mapping[PhaseInstanceId, dict],
    archives: Mapping[PhaseInstanceId, Path],
    stages: Mapping[PhaseInstanceId, Path],
    *,
    producer: dict,
    destination: Path,
) -> dict:
    """Sign a development cache index over original SDK receipts and objects.

    The caller must authenticate its current producer and selected phase transport;
    this content assembler never supplies original-worker or release admission.
    """
    current = validate_producer(producer)
    if current["event"] != "pull_request" or set(sources) != SDK_CAMPAIGN_INSTANCES:
        raise ValueError("Same-PR SDK catalog requires one current PR and all 61 phases")
    selected_sources = dict(sources)
    selected_envelopes = deepcopy(dict(envelopes))
    selected_archives = {instance: Path(path) for instance, path in archives.items()}
    selected_stages = {instance: Path(path) for instance, path in stages.items()}
    receipts = verify_sdk_campaign_selection(
        selected_sources, selected_envelopes, selected_archives, selected_stages)
    if any(receipt["trustDomain"] != "development"
           or receipt["producer"]["repository"] != current["repository"]
           or receipt["producer"]["event"] != "pull_request"
           or receipt["producer"]["pullRequest"] != current["pullRequest"]
           for receipt in receipts.values()):
        raise ValueError("Same-PR SDK catalog contains another trust or producer context")
    destination = Path(destination).absolute()
    _require_capability_output_separate(destination,
        [*selected_archives.values(), *selected_stages.values()])
    if destination.exists() or destination.is_symlink():
        raise ValueError("Same-PR SDK catalog destination must not exist")
    context = {"kind": "pull-request", "pullRequest": current["pullRequest"],
               **{field: current[field] for field in ("commit", "tree", "runId", "runAttempt")}}
    with tempfile.TemporaryDirectory(prefix="sdk-same-pr-catalog-") as temporary:
        private = Path(temporary).resolve()
        catalog = private / "catalog"
        catalog.mkdir()
        private_key, public_key, signing = generate_development_key(private / "keys")
        (catalog / "public-key.pub").write_bytes(public_key.read_bytes())
        for instance in sorted(SDK_CAMPAIGN_INSTANCES):
            receipt = receipts[instance]
            path = object_relative_path(receipt["buildKey"], sha256_bytes(selected_sources[instance].receipt_bytes))
            archive = selected_archives[instance]
            (catalog / path).parent.mkdir(parents=True, exist_ok=True)
            if _snapshot_archive(archive, catalog / path)["sha256"] != selected_envelopes[instance]["objectSha256"]:
                raise ValueError("Same-PR SDK original object changed during snapshot")
            restored = verify_object(catalog / path, build_key=receipt["buildKey"],
                receipt_sha256=sha256_bytes(selected_sources[instance].receipt_bytes),
                object_sha256=selected_envelopes[instance]["objectSha256"])
            if restored["receiptBytes"] != selected_sources[instance].receipt_bytes:
                raise ValueError("Same-PR SDK catalog changed an original receipt")
        publication = write_signed_product_index(
            [selected_sources[instance] for instance in sorted(SDK_CAMPAIGN_INSTANCES)],
            repository=current["repository"], context=context, trust_domain="development",
            signing=signing, producer=current, stable_history=None,
            private_key=private_key, public_key=public_key,
            manifest_path=catalog / "product-index.json")
        index = publication["index"]
        verified, _ = verify_signed_product_index(SignedProductIndex(
            catalog / "product-index.json", catalog / "product-index.sig"), catalog / "public-key.pub")
        if verified != index or len(index["entries"]) != len(SDK_CAMPAIGN_INSTANCES):
            raise ValueError("Same-PR SDK catalog index changed during signing")
        for entry in index["entries"]:
            original = verify_object(catalog / object_relative_path(entry["buildKey"], entry["receiptSha256"]),
                build_key=entry["buildKey"], receipt_sha256=entry["receiptSha256"])
            _verify_index_receipt(entry, {**original, "receiptSha256": entry["receiptSha256"]})
        if (dict(sources) != selected_sources or dict(envelopes) != selected_envelopes
                or {instance: Path(path) for instance, path in archives.items()} != selected_archives
                or {instance: Path(path) for instance, path in stages.items()} != selected_stages
                or verify_sdk_campaign_selection(
                    selected_sources, selected_envelopes, selected_archives, selected_stages) != receipts):
            raise ValueError("Same-PR SDK original selection changed before publication")
        inventory = regular_file_inventory(catalog)
        publish_regular_tree(catalog, destination, expected_inventory=inventory)
    return index
