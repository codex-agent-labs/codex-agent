"""Observe one fresh SDK worker upload without granting release or semantic trust.

Reused catalog objects have a different provenance route and are rejected here.
The caller must hold the selected 61-phase state while using this context.
"""

from contextlib import contextmanager
from pathlib import Path
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse
from products.inventory import (
    load_canonical_json_bytes, read_regular_file_bytes,
    regular_file_inventory, require_exact_keys, require_integer, require_sha256,
    sha256_bytes, sha256_file, verified_zip_contents,
)
from products.receipt import validate_phase_receipt
from products.registry import PhaseInstanceId
from products.restore import verify_object, verify_phase_shard
from products.sdk_campaign_selection import SDK_CAMPAIGN_INSTANCES
from products.signing_isolation import require_no_signing_secret
from ci.sdk_campaign_observation import ObservedSdkOriginal


@contextmanager
def held_fresh_sdk_worker_upload(instance, original, current_transport_bytes, *,
        artifact_id, artifact_sha256, trusted_workflow_sha, token, environ):
    """Bind one retained phase to its official original job, upload and exact shard.

    ``original`` and ``current_transport_bytes`` must come from the active
    held SDK campaign observation. This verifier does not accept reused phases,
    choose an index artifact path, or mint a release-admission token.
    """
    require_no_signing_secret(environ)
    if not isinstance(instance, PhaseInstanceId) or instance not in SDK_CAMPAIGN_INSTANCES:
        raise ValueError("Fresh SDK worker requires one registered phase instance")
    if not isinstance(original, ObservedSdkOriginal):
        raise ValueError("Fresh SDK worker requires an observed original phase")
    require_integer(artifact_id, "Original SDK worker artifact ID", 1)
    require_sha256(artifact_sha256, "Original SDK worker artifact digest")
    receipt = validate_phase_receipt(load_canonical_json_bytes(original.receipt_bytes))
    replay = require_exact_keys(load_canonical_json_bytes(original.replay_record_canonical),
        product_reuse._REUSE_PHASE_KEYS, "Original SDK replay phase")
    identity = tuple(getattr(instance, field) for field in ("product", "component", "phase", "target"))
    if (tuple(receipt[field] for field in ("product", "component", "phase", "target")) != identity
            or tuple(replay[field] for field in ("product", "component", "phase", "target")) != identity
            or replay["state"] != "retained" or replay["source"] is not None
            or replay["transportSource"] is not None or replay["misses"]
            or any(replay[field] != receipt[field] for field in ("buildKey",))
            or replay["receiptSha256"] != sha256_bytes(original.receipt_bytes)):
        raise ValueError("Fresh SDK worker requires the exact retained original phase")
    producer = receipt["producer"]
    current = load_canonical_json_bytes(current_transport_bytes)
    if not isinstance(current, dict) or current.get("captureProducer") != producer:
        raise ValueError("Fresh SDK worker differs from the current observed campaign producer")
    selected_object = verify_object(original.object_path, build_key=receipt["buildKey"],
        receipt_sha256=replay["receiptSha256"], object_sha256=replay["objectSha256"])
    if selected_object["receiptBytes"] != original.receipt_bytes:
        raise ValueError("Fresh SDK selected object changed its original receipt")
    name = f"{instance.component}-{instance.phase}-{instance.target}"
    job_name = f"product-validation / sdk-{name}"
    artifact_name = (f"codex-agent-sdk-worker-{name}-{receipt['buildKey'].removeprefix('sha256:')}-"
                     f"{producer['tree']}-attempt-{producer['runAttempt']}")
    observed = product_reuse._observe_ci_producer_jobs(
        {"worker": producer}, jobs_by_phase={"worker": job_name},
        trusted_workflow_sha=trusted_workflow_sha, token=token)
    artifact, raw = product_reuse._download_contract_ci_upload(
        artifact_id, artifact_sha256, artifact_name, producer, observed[0]["run"], token)
    product_reuse._require_artifact_job_window(observed[0], job_name, artifact)
    with tempfile.TemporaryDirectory(prefix="sdk-original-worker-") as temporary:
        root = Path(temporary).resolve()
        archive = root / "transport.zip"
        archive.write_bytes(raw)
        zipped, _, _ = verified_zip_contents(archive, retained_paths=(),
            allow_empty_members=True, **product_reuse._CATALOG_ZIP_LIMITS)
        extracted = root / "original"
        product_reuse.safe_extract(archive, extracted)
        if regular_file_inventory(extracted, allow_empty=True) != zipped:
            raise ValueError("Fresh SDK original extraction differs from its official upload")
        shard = verify_phase_shard(extracted / "shard", instance)
        if (shard["receiptBytes"] != original.receipt_bytes
                or shard["objectSha256"] != replay["objectSha256"]
                or sha256_file(extracted / "shard" / shard["objectPath"]) != replay["objectSha256"]):
            raise ValueError("Fresh SDK original upload differs from selected receipt or object")
        evidence = {"artifact": artifact, "observed": observed,
                    "originalReceiptSha256": replay["receiptSha256"],
                    "originalObjectSha256": replay["objectSha256"]}
        inventory = regular_file_inventory(root, allow_empty=True)
        require_no_signing_secret(environ)
        try:
            yield evidence, extracted
        finally:
            require_no_signing_secret(environ)
            if (regular_file_inventory(root, allow_empty=True) != inventory
                    or sha256_file(original.object_path) != replay["objectSha256"]
                    or read_regular_file_bytes(extracted / "shard/phase-receipt.json",
                        reject_symlink_parents=True) != original.receipt_bytes):
                raise ValueError("Fresh SDK original upload changed during verification")
