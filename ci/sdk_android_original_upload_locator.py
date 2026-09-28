"""Locate one official SDK Android upload from its selected receipt.

This is transport lookup only. The caller independently authenticates the
selected receipt; the phase-specific original reader still downloads and
verifies the upload, nested validation, source, tooling and semantics.
"""

import os
from pathlib import Path
import tempfile

if __package__:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse as products
from products.inventory import (canonical_json_bytes, load_canonical_json_bytes,
    read_regular_file_bytes, regular_file_inventory, require_integer, require_sha256,
    sha256_bytes)
from products.receipt import validate_phase_receipt, validate_producer
from products.signing_isolation import require_no_signing_secret
from sdk_facade_capture import _capture_route, verify_retained_sdk_phase_upload


_LIMIT = 16 * 1024 * 1024
_REPOSITORY = "codex-agent-labs/codex-agent"
_CHILD_ROUTES = {
    "validation": (".github/workflows/sdk-android-validation.yml",
                   "product-validation / sdk-android-validation-result / sdk-android-validation-android"),
    "metadata": (".github/workflows/sdk-android-metadata-validation.yml",
                 "product-validation / sdk-android-metadata-result / sdk-android-metadata-android"),
}


def locate_sdk_android_validation_upload(plan_path, validation_receipt_path, *,
        expected_receipt_sha256, trusted_workflow_sha, repository_root,
        environ=None, token):
    """Return the exact original validation artifact ID/digest; never admit its bytes."""
    return _locate_sdk_android_upload(
        plan_path, validation_receipt_path, phase="validation",
        expected_receipt_sha256=expected_receipt_sha256,
        trusted_workflow_sha=trusted_workflow_sha, repository_root=repository_root,
        environ=environ, token=token)


def locate_sdk_android_metadata_upload(plan_path, metadata_receipt_path, *,
        expected_receipt_sha256, trusted_workflow_sha, repository_root,
        environ=None, token):
    """Return the exact original metadata artifact ID/digest; never admit its bytes."""
    return _locate_sdk_android_upload(
        plan_path, metadata_receipt_path, phase="metadata",
        expected_receipt_sha256=expected_receipt_sha256,
        trusted_workflow_sha=trusted_workflow_sha, repository_root=repository_root,
        environ=environ, token=token)


def locate_retained_sdk_android_upload(capture_path, receipt_path, *,
        expected_receipt_sha256, authenticated_capture_inventory, environ=None):
    """Extract coordinates only from a caller-authenticated exact carrier."""
    environment = os.environ if environ is None else environ
    require_no_signing_secret(environment)
    if environment is not os.environ:
        require_no_signing_secret(os.environ)
    require_sha256(expected_receipt_sha256, "Caller-selected Android receipt")
    capture, receipt_path = Path(capture_path).absolute(), Path(receipt_path).absolute()
    before = regular_file_inventory(capture, allow_empty=True)
    if before != authenticated_capture_inventory:
        raise ValueError("Retained Android capture differs from authenticated caller inventory")
    receipt_bytes = read_regular_file_bytes(
        receipt_path, max_bytes=_LIMIT, reject_symlink_parents=True)
    if sha256_bytes(receipt_bytes) != expected_receipt_sha256:
        raise ValueError("Retained Android receipt differs from independent caller selection")
    receipt = validate_phase_receipt(load_canonical_json_bytes(receipt_bytes))
    if tuple(receipt[name] for name in ("product", "component", "phase", "target")) not in {
            ("sdk", "sdk-android", phase, "android") for phase in ("validation", "metadata")}:
        raise ValueError("Retained Android locator requires a validation or metadata receipt")
    verify_retained_sdk_phase_upload(capture, receipt_bytes)
    transport = load_canonical_json_bytes(read_regular_file_bytes(
        capture / "capture-transport.json", max_bytes=_LIMIT, reject_symlink_parents=True))
    artifact = transport["artifact"]
    result = {
        "artifact_id": require_integer(artifact.get("id"), "Retained Android upload ID", 1),
        "artifact_sha256": require_sha256(artifact.get("digest"), "Retained Android upload digest"),
    }
    if (regular_file_inventory(capture, allow_empty=True) != before
            or read_regular_file_bytes(receipt_path, max_bytes=_LIMIT,
                                       reject_symlink_parents=True) != receipt_bytes):
        raise ValueError("Retained Android upload or selected receipt changed during lookup")
    require_no_signing_secret(environment)
    return result


def _locate_sdk_android_upload(plan_path, receipt_path, *, phase,
        expected_receipt_sha256, trusted_workflow_sha, repository_root,
        environ, token):
    """Locate only; the phase-specific original reader must still verify content."""
    environment = os.environ if environ is None else environ
    require_no_signing_secret(environment)
    if environment is not os.environ:
        require_no_signing_secret(os.environ)
    require_sha256(expected_receipt_sha256, f"Caller-selected Android {phase} receipt")
    if type(token) is not str or not token:
        raise ValueError("Android original upload locator requires an observation token")
    root = Path(repository_root).resolve(strict=True)
    plan_path, receipt_path = Path(plan_path).absolute(), Path(receipt_path).absolute()
    plan_bytes = read_regular_file_bytes(plan_path, max_bytes=_LIMIT, reject_symlink_parents=True)
    receipt_bytes = read_regular_file_bytes(receipt_path, max_bytes=_LIMIT, reject_symlink_parents=True)
    if sha256_bytes(receipt_bytes) != expected_receipt_sha256:
        raise ValueError(f"Android {phase} receipt differs from independent caller selection")
    receipt = validate_phase_receipt(load_canonical_json_bytes(receipt_bytes))
    family = f"android-{phase}"
    _, runner, _, _, name, _ = _capture_route(receipt, family=family)
    workflow_path, job = _CHILD_ROUTES[phase]
    producer = validate_producer(receipt["producer"], f"Original Android {phase} producer")
    if producer["repository"] != _REPOSITORY:
        raise ValueError("Android original producer differs from the fixed repository")
    with tempfile.TemporaryDirectory(prefix="sdk-android-upload-locator-") as temporary:
        copied = Path(temporary).resolve() / "impact-plan.json"
        copied.write_bytes(plan_bytes)
        plan = products._validate_plan(copied, root)
        if (plan["remoteBuildAuthorized"] is not True
                or plan["event"] not in {"pull_request", "merge_group"}):
            raise ValueError("Android original upload lookup requires an authorized PR or merge-group plan")
        plan_value = canonical_json_bytes(plan)

        def unchanged():
            require_no_signing_secret(environment)
            if (read_regular_file_bytes(plan_path, max_bytes=_LIMIT, reject_symlink_parents=True) != plan_bytes
                    or read_regular_file_bytes(receipt_path, max_bytes=_LIMIT, reject_symlink_parents=True) != receipt_bytes
                    or read_regular_file_bytes(copied, max_bytes=_LIMIT) != plan_bytes
                    or canonical_json_bytes(plan) != plan_value
                    or canonical_json_bytes(receipt) != receipt_bytes):
                raise ValueError("Android original plan or selected receipt changed during lookup")

        unchanged()
        observation = products._observe_ci_producer_jobs(
            {family: producer}, jobs_by_phase={family: job},
            trusted_workflows_by_phase={family: {
                "path": workflow_path, "sha": trusted_workflow_sha}}, token=token)[0]
        jobs = [value for value in observation["jobs"] if value.get("name") == job]
        if len(jobs) != 1:
            raise ValueError("Android original worker job is missing or ambiguous")
        labels = jobs[0].get("labels")
        if (type(labels) is not list or any(type(value) is not str for value in labels)
                or runner not in labels):
            raise ValueError("Android original worker runner route differs from its selected receipt")
        require_integer(jobs[0].get("runner_id"), "Android original worker runner ID", 1)
        unchanged()
        api = f"https://api.github.com/repos/{_REPOSITORY}/actions"
        listed = products.paginated_items(
            f"{api}/runs/{producer['runId']}/artifacts", "artifacts", token)
        selected = [value for value in listed if type(value) is dict
                    and value.get("name") == name and value.get("expired") is False]
        if len(selected) != 1:
            raise ValueError("Android original worker upload is missing or ambiguous")
        artifact_id = require_integer(selected[0].get("id"), "Android original upload ID", 1)
        digest = require_sha256(selected[0].get("digest"), "Android original upload digest")
        url = f"{api}/artifacts/{artifact_id}"
        detail = products.api_json(url, token)
        if (type(detail) is not dict
                or any(detail.get(field) != selected[0].get(field) for field in (
                    "id", "name", "digest", "expired", "workflow_run", "created_at",
                    "archive_download_url", "size_in_bytes"))
                or detail.get("archive_download_url") != url + "/zip"
                or type(detail.get("workflow_run")) is not dict
                or require_integer(detail["workflow_run"].get("id"), "Android original upload run", 1)
                   != producer["runId"]
                or detail["workflow_run"].get("head_sha") != observation["run"]["head_sha"]
                or require_integer(detail.get("size_in_bytes"), "Android original upload bytes", 1)
                   > products._CATALOG_LIMIT):
            raise ValueError("Android original upload detail differs from official listing or run")
        products._require_artifact_job_window(observation, job, detail)
        unchanged()
        return {"artifact_id": artifact_id, "artifact_sha256": digest}
