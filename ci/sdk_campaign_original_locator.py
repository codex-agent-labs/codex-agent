"""Locate one fresh SDK original upload; content and release admission stay separate."""

import os
from pathlib import Path
import sys

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from ci.sdk_campaign_observation import ObservedSdkOriginal
from sdk_apple_upload_locator import _locate
from sdk_facade_capture import _capture_route
import product_reuse as products
from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, require_exact_keys,
    require_sha256, sha256_bytes,
)
from products.receipt import validate_phase_receipt
from products.registry import PhaseInstanceId
from products.sdk_campaign_selection import SDK_CAMPAIGN_INSTANCES
from products.signing_isolation import require_no_signing_secret


def fresh_sdk_worker_route(instance, receipt):
    """Return the fixed original workflow job and upload name for one phase."""
    if instance.component == "sdk-android":
        if instance.phase not in ("binary", "package", "validation", "metadata") or instance.target != "android":
            raise ValueError("SDK Android original route requires one exact worker phase")
        job = f"product-validation / sdk-sdk-android-{instance.phase}-android"
        producer = receipt["producer"]
        name = (f"codex-agent-sdk-worker-sdk-android-{instance.phase}-android-"
                f"{receipt['buildKey'].removeprefix('sha256:')}-{producer['tree']}-attempt-{producer['runAttempt']}")
        return job, name
    if instance.component == "sdk-core":
        routed, _, _, job, name, _ = _capture_route(receipt)
        if routed != instance:
            raise ValueError("SDK Core original route differs from selected phase")
        return job, name
    stem = f"{instance.component}-{instance.phase}-{instance.target}"
    producer = receipt["producer"]
    return (f"product-validation / sdk-{stem}",
            f"codex-agent-sdk-worker-{stem}-{receipt['buildKey'].removeprefix('sha256:')}-"
            f"{producer['tree']}-attempt-{producer['runAttempt']}")


def original_workflow_route(phase, default_job, sha, path=None, job=None):
    """Keep a caller-pinned child path and job paired at the original-run gate."""
    if (path is None) != (job is None):
        raise ValueError("SDK original workflow path and job must be pinned together")
    if path is None:
        return default_job, {"trusted_workflow_sha": sha}
    if type(job) is not str or not job:
        raise ValueError("SDK original workflow job must be caller-pinned text")
    return job, {"trusted_workflows_by_phase": {phase: {"path": path, "sha": sha}}}


def locate_fresh_sdk_original_upload(instance, original, *, expected_receipt_sha256,
        trusted_workflow_sha, token, environ=None,
        trusted_workflow_path=None, trusted_job_name=None):
    """Return an official ID/digest for an independently selected retained receipt.

    The caller supplies the original receipt digest independently of the held
    state. This locator never accepts a claimed artifact ID, name, or path from
    that state. The consumer must still download and verify the exact upload.
    """
    environment = os.environ if environ is None else environ
    require_no_signing_secret(environment)
    if environment is not os.environ:
        require_no_signing_secret(os.environ)
    if type(token) is not str or not token:
        raise ValueError("SDK original locator requires an observation token")
    require_sha256(expected_receipt_sha256, "Caller-selected SDK receipt")
    if not isinstance(instance, PhaseInstanceId) or instance not in SDK_CAMPAIGN_INSTANCES:
        raise ValueError("SDK original locator requires one registered phase")
    if not isinstance(original, ObservedSdkOriginal):
        raise ValueError("SDK original locator requires one held original")
    receipt_bytes = original.receipt_bytes
    replay_bytes = original.replay_record_canonical
    if sha256_bytes(receipt_bytes) != expected_receipt_sha256:
        raise ValueError("SDK original receipt differs from independent caller selection")
    receipt = validate_phase_receipt(load_canonical_json_bytes(receipt_bytes))
    replay = require_exact_keys(load_canonical_json_bytes(replay_bytes),
        products._REUSE_PHASE_KEYS, "SDK original replay phase")
    identity = tuple(getattr(instance, field) for field in ("product", "component", "phase", "target"))
    if (canonical_json_bytes(receipt) != receipt_bytes
            or canonical_json_bytes(replay) != replay_bytes
            or tuple(receipt[field] for field in ("product", "component", "phase", "target")) != identity
            or tuple(replay[field] for field in ("product", "component", "phase", "target")) != identity
            or replay["state"] != "retained" or replay["source"] is not None
            or replay["transportSource"] is not None or replay["misses"]
            or replay["buildKey"] != receipt["buildKey"]
            or replay["receiptSha256"] != expected_receipt_sha256):
        raise ValueError("SDK original locator requires the exact retained phase")
    producer = receipt["producer"]
    default_job, name = fresh_sdk_worker_route(instance, receipt)
    job, policy = original_workflow_route("worker", default_job, trusted_workflow_sha,
        trusted_workflow_path, trusted_job_name)
    result = _locate(producer, phase="worker", job=job, name=name,
        token=token, **policy)
    require_no_signing_secret(environment)
    if (original.receipt_bytes != receipt_bytes or original.replay_record_canonical != replay_bytes
            or sha256_bytes(receipt_bytes) != expected_receipt_sha256):
        raise ValueError("SDK original receipt changed during lookup")
    return result
