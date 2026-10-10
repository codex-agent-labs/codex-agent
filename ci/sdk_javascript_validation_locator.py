"""Locate original JavaScript validation transport, never admit its contents."""

from pathlib import Path
import sys

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse as products
from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, read_regular_file_bytes,
    require_integer, require_sha256,
)
from products.registry import PhaseInstanceId


def locate_javascript_validation_upload(validation_receipt_path, *, trusted_workflow_sha, token):
    """Return the exact original upload ID/digest under caller-pinned CI policy.

    The caller must authenticate the selected original receipt before calling.
    Structural receipt validation and observed upload metadata do not replace
    the existing original ZIP/shard/execution/content admission on consumption.
    No current environment producer, newer attempt or newest upload is selected.
    """
    if type(token) is not str or not token:
        raise ValueError("JavaScript validation locator requires an observation token")
    receipt_path = Path(validation_receipt_path).absolute()
    raw = read_regular_file_bytes(receipt_path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
    receipt = products.validate_phase_receipt(load_canonical_json_bytes(raw))
    if products._identity(receipt) != PhaseInstanceId("sdk", "javascript", "validation", "node"):
        raise ValueError("JavaScript validation locator requires the selected original validation receipt")
    producer = receipt["producer"]
    job = "product-validation / sdk-javascript-validation-node"
    observation = products._observe_ci_producer_jobs({"javascript-validation": producer},
        jobs_by_phase={"javascript-validation": job}, trusted_workflow_sha=trusted_workflow_sha, token=token)[0]
    api = f"https://api.github.com/repos/{producer['repository']}/actions"
    name = (f"codex-agent-sdk-worker-javascript-validation-node-{receipt['buildKey'].removeprefix('sha256:')}-"
            f"{producer['tree']}-attempt-{producer['runAttempt']}")
    artifacts = products.paginated_items(f"{api}/runs/{producer['runId']}/artifacts", "artifacts", token)
    selected = [value for value in artifacts if type(value) is dict
                and value.get("name") == name and value.get("expired") is False]
    if len(selected) != 1:
        raise ValueError("Original JavaScript validation upload is missing or ambiguous")
    listed = selected[0]
    artifact_id = require_integer(listed.get("id"), "JavaScript validation upload ID", 1)
    digest = require_sha256(listed.get("digest"), "JavaScript validation upload digest")
    url = f"{api}/artifacts/{artifact_id}"
    detail = products.api_json(url, token)
    if (type(detail) is not dict or any(detail.get(field) != listed.get(field) for field in (
            "id", "name", "digest", "expired", "workflow_run", "created_at"))
            or detail.get("archive_download_url") != url + "/zip"
            or type(detail.get("workflow_run")) is not dict
            or require_integer(detail["workflow_run"].get("id"), "JavaScript validation upload run", 1) != producer["runId"]
            or detail["workflow_run"].get("head_sha") != observation["run"]["head_sha"]):
        raise ValueError("Original JavaScript validation upload differs from its observed run or listing")
    products._require_artifact_job_window(observation, job, detail)
    if (read_regular_file_bytes(receipt_path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True) != raw
            or canonical_json_bytes(receipt) != raw):
        raise ValueError("Original JavaScript validation receipt changed during observation")
    return {"artifact_id": artifact_id, "artifact_sha256": digest}
