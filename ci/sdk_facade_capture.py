"""Retain an officially observed original Core worker upload, not admission.

Fixed job and runner-label metadata bind routing only: neither labels nor this
transport record establish hardware, compiler, source-policy or content trust.
The caller independently selects the exact original phase receipt; current
environment/run values cannot replace its producer. Full original replay and
host/toolchain admission remain separate, and no accepted family is registered.
"""

import os
from pathlib import Path
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse as products
from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, publish_regular_tree,
    read_regular_file_bytes, regular_file_inventory, require_integer,
    require_regular_directory, require_sha256, sha256_bytes, sha256_file,
    verified_zip_contents, write_canonical_json,
)
from products.receipt import validate_phase_receipt
from products.registry import PhaseInstanceId, SDK_FACADE_TARGETS
from products.restore import verify_phase_shard
from products.sdk_package import _require_capability_output_separate
from products.signing_isolation import require_no_signing_secret
from sdk_phase import route


_LIMIT = 16 * 1024 * 1024


def _read(path):
    return read_regular_file_bytes(Path(path), max_bytes=_LIMIT, reject_symlink_parents=True)


def capture_sdk_facade_validation_upload(
    plan_path, destination, *, validation_receipt_path, artifact_id, artifact_sha256,
    trusted_workflow_sha, repository_root=None, environ=None, token,
):
    """Capture only a selected original eleven-target validation route."""
    return _capture_sdk_facade_upload(plan_path, destination, phase="validation",
        receipt_path=validation_receipt_path, artifact_id=artifact_id, artifact_sha256=artifact_sha256,
        trusted_workflow_sha=trusted_workflow_sha, repository_root=repository_root, environ=environ, token=token)


def capture_sdk_facade_metadata_upload(
    plan_path, destination, *, metadata_receipt_path, artifact_id, artifact_sha256,
    trusted_workflow_sha, repository_root=None, environ=None, token,
):
    """Capture only the selected original common metadata route; grant no trust."""
    return _capture_sdk_facade_upload(plan_path, destination, phase="metadata",
        receipt_path=metadata_receipt_path, artifact_id=artifact_id, artifact_sha256=artifact_sha256,
        trusted_workflow_sha=trusted_workflow_sha, repository_root=repository_root, environ=environ, token=token)


def _capture_sdk_facade_upload(
    plan_path, destination, *, phase, receipt_path, artifact_id, artifact_sha256,
    trusted_workflow_sha, repository_root=None, environ=None, token,
):
    """Preserve the complete original upload after exact receipt/CI comparison.

    The authorized current plan permits capture, not relabeling a historical
    producer. Context and retained execution are not interpreted as authority.
    No callback, uploaded policy, synthesized receipt or semantic success token.
    """
    environment = os.environ if environ is None else environ
    if phase not in {"validation", "metadata"}:
        raise ValueError("Unsupported Core original capture phase")
    require_no_signing_secret(environment)
    require_integer(artifact_id, "Core worker artifact ID", 1)
    require_sha256(artifact_sha256, "Core worker artifact digest")
    if type(token) is not str or not token:
        raise ValueError("Core worker capture requires an observation token")
    root = (Path(__file__).resolve().parents[1] if repository_root is None else Path(repository_root)).resolve(strict=True)
    plan_path, receipt_path, destination = (Path(path).absolute() for path in
        (plan_path, receipt_path, destination))

    def output_safe():
        _require_capability_output_separate(destination, [root, plan_path, receipt_path])
        if destination.resolve(strict=False) != destination or destination.exists() or destination.is_symlink():
            raise ValueError("Core worker capture destination must be fresh, normalized and non-symbolic")
        for ancestor in destination.parents:
            if ancestor.exists() or ancestor.is_symlink():
                require_regular_directory(ancestor, "Core capture destination ancestry")

    output_safe()
    plan_bytes, receipt_bytes = _read(plan_path), _read(receipt_path)
    receipt = validate_phase_receipt(load_canonical_json_bytes(receipt_bytes))
    if ((receipt["product"], receipt["component"], receipt["phase"]) != ("sdk", "sdk-core", phase)
            or receipt["target"] not in (SDK_FACADE_TARGETS if phase == "validation" else ("common",))):
        raise ValueError("Core capture requires an exact selected original " + phase + " receipt")
    target, producer = receipt["target"], receipt["producer"]
    instance = PhaseInstanceId("sdk", "sdk-core", phase, target)
    topology = route(receipt) if phase == "validation" else {"runner": "ubuntu-24.04"}
    job = f"product-validation / sdk-sdk-core-{phase}-{target}"
    name = (f"codex-agent-sdk-worker-sdk-core-{phase}-{target}-"
            f"{receipt['buildKey'].removeprefix('sha256:')}-{producer['tree']}-attempt-{producer['runAttempt']}")
    with tempfile.TemporaryDirectory(prefix="sdk-facade-upload-") as temporary:
        prepared = Path(temporary).resolve() / "capture"
        captured_plan = prepared / "plan/impact-plan.json"
        captured_plan.parent.mkdir(parents=True)
        captured_plan.write_bytes(plan_bytes)
        plan = products._validate_plan(captured_plan, root)
        if plan["remoteBuildAuthorized"] is not True or plan["event"] not in {"pull_request", "merge_group"}:
            raise ValueError("Core worker capture requires an authorized PR or merge-group plan")
        plan_value = canonical_json_bytes(plan)

        def unchanged():
            require_no_signing_secret(environment)
            if (_read(plan_path) != plan_bytes or _read(receipt_path) != receipt_bytes
                    or _read(captured_plan) != plan_bytes or canonical_json_bytes(receipt) != receipt_bytes
                    or canonical_json_bytes(plan) != plan_value):
                raise ValueError("Core capture original receipt or caller plan changed")

        unchanged()
        observed = products._observe_ci_producer_jobs({"facade-" + phase: producer},
            jobs_by_phase={"facade-" + phase: job}, trusted_workflow_sha=trusted_workflow_sha, token=token)
        jobs = [value for value in observed[0]["jobs"] if value.get("name") == job]
        if len(jobs) != 1:
            raise ValueError("Core original worker job is missing or ambiguous")
        official_job = jobs[0]
        labels = official_job.get("labels")
        if (type(labels) is not list or any(type(label) is not str for label in labels)
                or topology["runner"] not in labels):
            raise ValueError("Core original worker runner label differs from its fixed target route")
        require_integer(official_job.get("runner_id"), "Core original worker runner ID", 1)
        observed_bytes = canonical_json_bytes(observed)
        unchanged()
        artifact, raw = products._download_contract_ci_upload(
            artifact_id, artifact_sha256, name, producer, observed[0]["run"], token)
        products._require_artifact_job_window(observed[0], job, artifact)
        archive = prepared / "transport.zip"
        archive.write_bytes(raw)
        zipped, _, _ = verified_zip_contents(archive, retained_paths=(), allow_empty_members=True,
                                            **products._CATALOG_ZIP_LIMITS)
        original = prepared / "original"
        products.safe_extract(archive, original)
        if regular_file_inventory(original, allow_empty=True) != zipped:
            raise ValueError("Core worker extraction differs from its exact original upload")
        for directory in (("shard", "worker", "context") if phase == "validation" else
                          ("shard", "worker", "selection", "originals", "inputs")):
            require_regular_directory(original / directory, "Core original upload retained directory")
        verified = verify_phase_shard(original / "shard", instance)
        if verified["receiptBytes"] != receipt_bytes or canonical_json_bytes(verified["receipt"]) != receipt_bytes:
            raise ValueError("Core uploaded phase differs from the selected original receipt")
        transport = {"artifact": artifact, "captureProducer": producer, "observed": observed,
                     phase + "ReceiptSha256": sha256_bytes(receipt_bytes)}
        transport_bytes = canonical_json_bytes(transport)
        write_canonical_json(prepared / "capture-transport.json", transport)
        prepared_inventory = regular_file_inventory(prepared, allow_empty=True)
        unchanged()
        if (sha256_file(archive) != artifact_sha256 or canonical_json_bytes(observed) != observed_bytes
                or regular_file_inventory(original, allow_empty=True) != zipped
                or _read(prepared / "capture-transport.json") != transport_bytes
                or canonical_json_bytes(transport) != transport_bytes
                or regular_file_inventory(prepared, allow_empty=True) != prepared_inventory):
            raise ValueError("Core original upload or observation changed before publication")
        output_safe()
        publish_regular_tree(prepared, destination, allow_empty=True)
        unchanged()
        if regular_file_inventory(destination, allow_empty=True) != prepared_inventory:
            raise ValueError("Core capture bytes changed during publication")
    return transport
