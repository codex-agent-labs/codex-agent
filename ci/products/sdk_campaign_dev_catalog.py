"""Assemble an exact same-PR SDK reuse catalog without granting release trust."""

from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
import tempfile

from .index import IndexEntrySource, SignedProductIndex, _validated_entry_source, _verify_index_receipt, verify_signed_product_index, write_signed_product_index
from .inventory import publish_regular_tree, regular_file_inventory, sha256_bytes
from .receipt import validate_producer
from .registry import PhaseInstanceId
from .restore import _snapshot_archive, object_relative_path, verify_object
from .reuse import _validate_envelope
from .sdk_campaign_selection import SDK_CAMPAIGN_INSTANCES, verify_sdk_campaign_objects
from .sdk_package import _require_capability_output_separate
from .signatures import generate_development_key


def stage_sdk_same_pr_catalog(
    sources: Mapping[PhaseInstanceId, IndexEntrySource],
    envelopes: Mapping[PhaseInstanceId, dict],
    archives: Mapping[PhaseInstanceId, Path],
    *,
    producer: dict,
    destination: Path,
) -> dict:
    """Sign a development cache index over original SDK receipts and objects.

    The caller must authenticate its current producer and selected phase transport;
    this content assembler never supplies original-worker or release admission.
    """
    return _stage_sdk_same_pr_catalog(sources, envelopes, archives, producer=producer,
                                      destination=destination, partial=False)


def stage_sdk_partial_same_pr_catalog(
    sources: Mapping[PhaseInstanceId, IndexEntrySource],
    envelopes: Mapping[PhaseInstanceId, dict],
    archives: Mapping[PhaseInstanceId, Path],
    *,
    producer: dict,
    destination: Path,
) -> dict:
    """Preserve successful original phases of an incomplete PR in a development index.

    A partial index is only a cache source. It is never a completed campaign or
    release-admission artifact; those gates still require the exact 61 phases.
    """
    return _stage_sdk_same_pr_catalog(sources, envelopes, archives, producer=producer,
                                      destination=destination, partial=True)


def _verify_partial_objects(sources, envelopes, archives):
    receipts = {}
    for instance in sorted(sources):
        identity, envelope = _validate_envelope(envelopes[instance])
        receipt, _, _ = _validated_entry_source(sources[instance])
        if (identity != instance or sources[instance].release_admission is not None
                or sources[instance].receipt_bytes != envelope["receiptBytes"]):
            raise ValueError("Partial SDK catalog original phase identity differs")
        original = verify_object(archives[instance], build_key=receipt["buildKey"],
            receipt_sha256=sha256_bytes(sources[instance].receipt_bytes),
            object_sha256=envelope["objectSha256"])
        if original["receiptBytes"] != sources[instance].receipt_bytes:
            raise ValueError("Partial SDK catalog original receipt differs")
        receipts[instance] = receipt
    if len({receipt["productVersion"] for receipt in receipts.values()}) != 1:
        raise ValueError("Partial SDK catalog phases require one SDK version")
    return receipts


def _stage_sdk_same_pr_catalog(sources, envelopes, archives, *, producer, destination, partial):
    current = validate_producer(producer)
    selected_instances = set(sources)
    if current["event"] != "pull_request":
        raise ValueError("Same-PR SDK catalog requires a current PR")
    if partial:
        if not selected_instances or not selected_instances < SDK_CAMPAIGN_INSTANCES:
            raise ValueError("Partial SDK catalog requires a nonempty proper subset of 61 phases")
    elif selected_instances != SDK_CAMPAIGN_INSTANCES:
        raise ValueError("Same-PR SDK catalog requires one current PR and all 61 phases")
    if set(envelopes) != selected_instances or set(archives) != selected_instances:
        raise ValueError("Same-PR SDK catalog sources, envelopes and archives must match")
    selected_sources = dict(sources)
    selected_envelopes = deepcopy(dict(envelopes))
    selected_archives = {instance: Path(path) for instance, path in archives.items()}
    verify_selected = _verify_partial_objects if partial else verify_sdk_campaign_objects
    receipts = verify_selected(selected_sources, selected_envelopes, selected_archives)
    if any(receipt["trustDomain"] != "development"
           or receipt["producer"]["repository"] != current["repository"]
           or receipt["producer"]["event"] != "pull_request"
           or receipt["producer"]["pullRequest"] != current["pullRequest"]
           for receipt in receipts.values()):
        raise ValueError("Same-PR SDK catalog contains another trust or producer context")
    destination = Path(destination).absolute()
    _require_capability_output_separate(destination, list(selected_archives.values()))
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
        for instance in sorted(selected_instances):
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
            [selected_sources[instance] for instance in sorted(selected_instances)],
            repository=current["repository"], context=context, trust_domain="development",
            signing=signing, producer=current, stable_history=None,
            private_key=private_key, public_key=public_key,
            manifest_path=catalog / "product-index.json")
        index = publication["index"]
        verified, _ = verify_signed_product_index(SignedProductIndex(
            catalog / "product-index.json", catalog / "product-index.sig"), catalog / "public-key.pub")
        if verified != index or len(index["entries"]) != len(selected_instances):
            raise ValueError("Same-PR SDK catalog index changed during signing")
        for entry in index["entries"]:
            original = verify_object(catalog / object_relative_path(entry["buildKey"], entry["receiptSha256"]),
                build_key=entry["buildKey"], receipt_sha256=entry["receiptSha256"])
            _verify_index_receipt(entry, {**original, "receiptSha256": entry["receiptSha256"]})
        if (dict(sources) != selected_sources or dict(envelopes) != selected_envelopes
                or {instance: Path(path) for instance, path in archives.items()} != selected_archives
                or verify_selected(selected_sources, selected_envelopes, selected_archives) != receipts):
            raise ValueError("Same-PR SDK original selection changed before publication")
        inventory = regular_file_inventory(catalog)
        publish_regular_tree(catalog, destination, expected_inventory=inventory)
    return index
