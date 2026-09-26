"""Authenticate a held, reused SDK original against its same-PR catalog.

The current state and original bytes are caller-held inputs. This context
authenticates retrieval and producer provenance; it grants no release admission.
The required sdk-catalog producer job is not wired in the current workflow,
so official runs cannot pass this route yet.
"""

from contextlib import contextmanager
import os
from pathlib import Path
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse
from ci.sdk_campaign_observation import ObservedSdkOriginal
from ci.sdk_campaign_original_locator import fresh_sdk_worker_route, original_workflow_route
from products.index import SignedProductIndex, _verify_index_receipt, verify_signed_product_index
from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, read_regular_file_bytes,
    regular_file_inventory, require_exact_keys, require_integer, require_sha256,
    sha256_bytes, sha256_file, verified_zip_contents,
)
from products.receipt import validate_phase_receipt, validate_producer
from products.registry import PhaseInstanceId
from products.restore import verify_object, verify_phase_shard
from products.sdk_campaign_selection import SDK_CAMPAIGN_INSTANCES
from products.signing_isolation import require_no_signing_secret


@contextmanager
def held_reused_sdk_original(instance, original, current_transport_bytes, *,
        expected_receipt_sha256, catalog_artifact_id, catalog_artifact_sha256,
        original_artifact_id, original_artifact_sha256,
        catalog_public_key, expected_public_key_sha256, pull_request,
        trusted_workflow_sha, token, environ=None,
        trusted_worker_workflow_path=None, trusted_worker_job_name=None,
        trusted_catalog_workflow_path=None, trusted_catalog_job_name=None):
    """Hold exact original bytes under independently pinned same-PR catalog trust.

    The public key and artifact ID/digest are selected outside the replay and
    catalog. The current transport comes from held_sdk_campaign_observation.
    """
    environment = os.environ if environ is None else environ
    require_no_signing_secret(environment)
    require_no_signing_secret(os.environ)
    original_workflow_route("worker", "unused", trusted_workflow_sha,
        trusted_worker_workflow_path, trusted_worker_job_name)
    original_workflow_route("catalog", "unused", trusted_workflow_sha,
        trusted_catalog_workflow_path, trusted_catalog_job_name)
    if not isinstance(instance, PhaseInstanceId) or instance not in SDK_CAMPAIGN_INSTANCES:
        raise ValueError("Reused SDK original requires one registered phase")
    if not isinstance(original, ObservedSdkOriginal):
        raise ValueError("Reused SDK original requires held observation")
    require_sha256(expected_receipt_sha256, "Caller-selected SDK receipt")
    require_sha256(catalog_artifact_sha256, "Caller-selected catalog artifact")
    require_sha256(original_artifact_sha256, "Caller-selected original worker artifact")
    require_sha256(expected_public_key_sha256, "Independent catalog public key")
    require_integer(catalog_artifact_id, "Caller-selected catalog artifact ID", 1)
    require_integer(original_artifact_id, "Caller-selected original worker artifact ID", 1)
    require_integer(pull_request, "Caller-selected pull request", 1)
    if type(token) is not str or not token:
        raise ValueError("Reused SDK original requires observation token")
    key_input = Path(catalog_public_key)
    pinned_key = read_regular_file_bytes(key_input, max_bytes=64 * 1024,
        reject_symlink_parents=True)
    key_path = key_input.resolve(strict=True)
    object_path = Path(original.object_path).resolve(strict=True)
    stage_path = Path(original.stage_path).resolve(strict=True)
    if key_path == object_path or key_path == stage_path or stage_path in key_path.parents:
        raise ValueError("Reused SDK catalog key must not be a held original")
    if sha256_bytes(pinned_key) != expected_public_key_sha256:
        raise ValueError("Reused SDK catalog key differs from independent digest")
    receipt_bytes = original.receipt_bytes
    replay_bytes = original.replay_record_canonical
    if sha256_bytes(receipt_bytes) != expected_receipt_sha256:
        raise ValueError("Reused SDK original differs from independent receipt selection")
    receipt = validate_phase_receipt(load_canonical_json_bytes(receipt_bytes))
    replay = require_exact_keys(load_canonical_json_bytes(replay_bytes),
        product_reuse._REUSE_PHASE_KEYS, "Reused SDK replay phase")
    fields = ("product", "component", "phase", "target")
    identity = tuple(getattr(instance, field) for field in fields)
    transport = require_exact_keys(replay["transportSource"],
        {"kind", "indexSha256", "artifactName", "artifactSha256"}, "Reused SDK transport source")
    current = load_canonical_json_bytes(current_transport_bytes)
    if (not isinstance(current, dict) or "captureProducer" not in current):
        raise ValueError("Reused SDK original lacks held current transport")
    current_producer = validate_producer(current["captureProducer"])
    producer = receipt["producer"]
    if (canonical_json_bytes(receipt) != receipt_bytes
            or canonical_json_bytes(replay) != replay_bytes
            or tuple(receipt[field] for field in fields) != identity
            or tuple(replay[field] for field in fields) != identity
            or replay["state"] != "reused" or replay["source"] != "same-pr"
            or transport["kind"] != "same-pr" or replay["misses"] != []
            or replay["buildKey"] != receipt["buildKey"]
            or replay["receiptSha256"] != expected_receipt_sha256
            or producer["repository"] != current_producer["repository"]
            or producer["pullRequest"] != pull_request
            or current_producer["pullRequest"] != pull_request):
        raise ValueError("Reused SDK original differs from held same-PR state")
    require_sha256(transport["indexSha256"], "Reused SDK index digest")
    require_sha256(transport["artifactSha256"], "Reused SDK indexed artifact digest")
    original_object = verify_object(original.object_path, build_key=replay["buildKey"],
        receipt_sha256=expected_receipt_sha256, object_sha256=replay["objectSha256"])
    if original_object["receiptBytes"] != receipt_bytes:
        raise ValueError("Reused SDK original object changes its receipt")
    default_job, original_name = fresh_sdk_worker_route(instance, receipt)
    original_job, worker_policy = original_workflow_route("worker", default_job,
        trusted_workflow_sha, trusted_worker_workflow_path, trusted_worker_job_name)
    producer_observation = product_reuse._observe_ci_producer_jobs(
        {"worker": producer}, jobs_by_phase={"worker": original_job},
        token=token, **worker_policy)
    with tempfile.TemporaryDirectory(prefix="sdk-reused-worker-") as temporary:
        worker_root = Path(temporary).resolve()
        worker_archive = worker_root / "transport.zip"
        original_artifact, _ = product_reuse._download_contract_ci_upload(
            original_artifact_id, original_artifact_sha256, original_name,
            producer, producer_observation[0]["run"], token, destination=worker_archive)
        product_reuse._require_artifact_job_window(producer_observation[0], original_job, original_artifact)
        zipped, _, _ = verified_zip_contents(worker_archive, retained_paths=(), allow_empty_members=True,
            **product_reuse._CATALOG_ZIP_LIMITS)
        worker = worker_root / "original"
        product_reuse.safe_extract(worker_archive, worker)
        if regular_file_inventory(worker, allow_empty=True) != zipped:
            raise ValueError("Reused SDK worker extraction differs from official upload")
        shard = verify_phase_shard(worker / "shard", instance)
        if (shard["receiptBytes"] != receipt_bytes
                or shard["objectSha256"] != replay["objectSha256"]
                or sha256_file(worker / "shard" / shard["objectPath"])
                    != sha256_file(original.object_path)):
            raise ValueError("Reused SDK original worker upload differs from held object")
    repository = producer["repository"]
    api = "https://api.github.com"
    url = f"{api}/repos/{repository}/actions/artifacts/{catalog_artifact_id}"
    artifact = product_reuse.api_json(url, token)
    if not isinstance(artifact, dict):
        raise ValueError("Reused SDK catalog artifact detail is malformed")
    run = artifact.get("workflow_run")
    if (artifact.get("id") != catalog_artifact_id
            or artifact.get("digest") != catalog_artifact_sha256
            or artifact.get("expired") is not False
            or artifact.get("archive_download_url") != f"{url}/zip"
            or not isinstance(artifact.get("name"), str)
            or not artifact["name"].startswith(
                f"{product_reuse._CATALOG_PREFIX}pull-request-{pull_request}-")
            or not isinstance(run, dict)):
        raise ValueError("Reused SDK catalog differs from official artifact identity")
    size = require_integer(artifact.get("size_in_bytes"), "Reused SDK catalog size", 1)
    if size > product_reuse._CATALOG_LIMIT:
        raise ValueError("Reused SDK catalog exceeds transport limit")
    with tempfile.TemporaryDirectory(prefix="sdk-reused-original-") as temporary:
        root = Path(temporary).resolve()
        archive = root / "catalog.zip"
        product_reuse.download_artifact_to_file(artifact, token, archive,
            max_bytes=product_reuse._CATALOG_LIMIT)
        if archive.stat().st_size != size or sha256_file(archive) != catalog_artifact_sha256:
            raise ValueError("Reused SDK catalog differs from official artifact bytes")
        verified_zip_contents(archive, retained_paths=(), allow_empty_members=True,
            **product_reuse._CATALOG_ZIP_LIMITS)
        extracted = root / "catalog"
        product_reuse.safe_extract(archive, extracted)
        key = read_regular_file_bytes(extracted / "public-key.pub", max_bytes=64 * 1024,
            reject_symlink_parents=True)
        if key != pinned_key:
            raise ValueError("Reused SDK catalog key differs from independent policy")
        index, index_bytes = verify_signed_product_index(SignedProductIndex(
            extracted / "product-index.json", extracted / "product-index.sig"), key_path)
        if sha256_bytes(index_bytes) != transport["indexSha256"]:
            raise ValueError("Reused SDK replay differs from signed catalog")
        catalog = product_reuse._read_catalog_directory("same-pr", extracted, root, None,
            repository=repository, pull_request=pull_request, provenance_root=root,
            artifact=artifact, token=token, api=api)
        if index != catalog.index:
            raise ValueError("Reused SDK catalog changed during provenance verification")
        catalog_job, catalog_policy = original_workflow_route("catalog",
            "product-validation / sdk-catalog", trusted_workflow_sha,
            trusted_catalog_workflow_path, trusted_catalog_job_name)
        catalog_observation = product_reuse._observe_ci_producer_jobs(
            {"catalog": index["producer"]}, jobs_by_phase={"catalog": catalog_job},
            token=token, **catalog_policy)
        if (len(catalog_observation) != 1
                or catalog_observation[0]["run"]["id"] != index["producer"]["runId"]
                or catalog_observation[0]["run"]["run_attempt"] != index["producer"]["runAttempt"]):
            raise ValueError("Reused SDK catalog lacks exact producer attempt")
        product_reuse._require_artifact_job_window(catalog_observation[0], catalog_job, artifact)
        entries = [entry for entry in index["entries"] if entry["buildKey"] == replay["buildKey"]]
        if len(entries) != 1:
            raise ValueError("Reused SDK original lacks one exact indexed entry")
        entry = entries[0]
        catalog_object_path = catalog.objects.get(replay["buildKey"])
        if catalog_object_path is None:
            raise ValueError("Reused SDK catalog lacks original object")
        selected = verify_object(catalog_object_path, build_key=replay["buildKey"],
            receipt_sha256=expected_receipt_sha256, object_sha256=replay["objectSha256"])
        _verify_index_receipt(entry, {**selected, "receiptSha256": expected_receipt_sha256})
        if (selected["receiptBytes"] != receipt_bytes
                or sha256_file(catalog_object_path) != sha256_file(original.object_path)
                or transport["artifactName"] != entry["artifactName"]
                or transport["artifactSha256"] != entry["artifactSha256"]):
            raise ValueError("Reused SDK catalog changes its original receipt, object, or artifact")
        before = regular_file_inventory(root, allow_empty=True)
        evidence = {"catalogArtifact": artifact, "catalogIndexSha256": transport["indexSha256"],
                    "originalProducer": producer_observation, "originalArtifact": original_artifact,
                    "catalogProducer": catalog_observation,
                    "originalReceiptSha256": expected_receipt_sha256,
                    "originalObjectSha256": replay["objectSha256"]}
        require_no_signing_secret(environment)
        try:
            yield evidence, catalog_object_path
        finally:
            require_no_signing_secret(environment)
            require_no_signing_secret(os.environ)
            if (regular_file_inventory(root, allow_empty=True) != before
                    or original.receipt_bytes != receipt_bytes
                    or original.replay_record_canonical != replay_bytes
                    or sha256_file(original.object_path) != replay["objectSha256"]
                    or key_input.resolve(strict=True) != key_path
                    or read_regular_file_bytes(key_input, max_bytes=64 * 1024,
                        reject_symlink_parents=True) != pinned_key):
                raise ValueError("Reused SDK originals or catalog changed while held")
