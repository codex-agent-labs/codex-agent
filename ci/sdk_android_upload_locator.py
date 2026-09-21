"""Locate the final protected Android upload without admitting its contents."""

from datetime import datetime, timedelta
import os
from pathlib import Path
import re
import tempfile
from typing import Mapping

if __package__:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse as products
from products.inventory import (
    canonical_json_bytes, read_regular_file_bytes, require_array,
    require_integer, require_sha256, require_string,
)
from products.signing_isolation import require_no_signing_secret


REPOSITORY = "codex-agent-labs/codex-agent"
ANDROID_WORKFLOW = ".github/workflows/android-runtime-evidence.yml"
FIREBASE_JOB = "product-validation / android-runtime-evidence / firebase-arm64-runtime"
ATTACH_JOB = "product-validation / android-runtime-evidence / attach-evidence"
_OID = re.compile(r"[0-9a-f]{40}")


def _utc(value, label):
    parsed = datetime.fromisoformat(require_string(value, label).replace("Z", "+00:00"))
    if parsed.utcoffset() != timedelta(0):
        raise ValueError("Android evidence job timestamps must be UTC")
    return parsed


def locate_android_validation_upload(
    plan_path: Path,
    candidate_root: Path,
    *,
    trusted_workflow_sha: str,
    trusted_android_workflow_sha: str,
    environ: Mapping[str, str] | None = None,
    token: str,
    expected_revision: str | None = None,
) -> dict[str, object]:
    """Return the final post-attach upload locator, never content authority.

    Protected workflow execution and the downloaded seven-file Firebase closure
    still require independent admission. Protected dispatch is intentionally not
    accepted until its environment approval has an official observer contract.
    """
    environment = os.environ if environ is None else environ
    require_no_signing_secret(environment)
    if type(token) is not str or not token:
        raise ValueError("Android upload locator requires an observation token")
    if type(trusted_android_workflow_sha) is not str or _OID.fullmatch(trusted_android_workflow_sha) is None:
        raise ValueError("Android upload locator requires a caller-pinned reusable workflow SHA")
    source = Path(plan_path).absolute()
    source_bytes = read_regular_file_bytes(source, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
    candidate = Path(candidate_root).resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="android-upload-locator-") as temporary:
        captured = Path(temporary).resolve() / "impact-plan.json"
        captured.write_bytes(source_bytes)
        plan = products._validate_plan(captured, candidate, expected_revision=expected_revision)
        android = plan.get("lanes", {}).get("android", {}) if isinstance(plan.get("lanes"), dict) else {}
        if (plan.get("remoteBuildAuthorized") is not True
                or plan.get("event") not in {"pull_request", "merge_group"}
                or plan.get("androidEvidenceRequired") is not True
                or type(android) is not dict
                or not any(android.get(action) is True for action in ("build", "test", "metadata"))):
            raise ValueError("Android upload locator requires authorized Android evidence work")
        plan_bytes = canonical_json_bytes(plan)
        producer = products.validate_producer(products._consumer(plan, environment)["producer"])
        observation = products._observe_ci_producer_jobs(
            {"firebase": producer, "attach": producer},
            jobs_by_phase={"firebase": FIREBASE_JOB, "attach": ATTACH_JOB},
            trusted_workflow_sha=trusted_workflow_sha,
            token=token,
        )[0]
        references = require_array(
            observation["run"].get("referenced_workflows"),
            "Android original workflow references",
        )
        # The checked-in caller deliberately declares this reusable workflow at
        # @main.  Its resolved `sha` is a separate official observation and is
        # pinned by the caller of this locator; do not conflate the two fields.
        expected = f"{REPOSITORY}/{ANDROID_WORKFLOW}@main"
        selected = [value for value in references if type(value) is dict
                    and isinstance(value.get("path"), str)
                    and value["path"].split("@", 1)[0] == expected.split("@", 1)[0]]
        if (len(selected) != 1 or selected[0].get("path") != expected
                or selected[0].get("sha") != trusted_android_workflow_sha):
            raise ValueError("Android upload lacks the declared and caller-pinned reusable workflow")
        jobs = observation["jobs"]
        firebase = next(job for job in jobs if job.get("name") == FIREBASE_JOB)
        attach = next(job for job in jobs if job.get("name") == ATTACH_JOB)
        if _utc(firebase.get("completed_at"), "Firebase completion") > \
                _utc(attach.get("started_at"), "Android attach start"):
            raise ValueError("Android attach job started before Firebase evidence completed")

        api = f"https://api.github.com/repos/{REPOSITORY}/actions"
        name = f"codex-agent-ci-android-{producer['tree']}"
        artifacts = products.paginated_items(
            f"{api}/runs/{producer['runId']}/artifacts", "artifacts", token,
        )
        selected = [value for value in artifacts if type(value) is dict
                    and value.get("name") == name and value.get("expired") is False]
        if len(selected) != 1:
            raise ValueError("Final Android upload is missing or ambiguous")
        listed = selected[0]
        artifact_id = require_integer(listed.get("id"), "Android upload ID", 1)
        digest = require_sha256(listed.get("digest"), "Android upload digest")
        url = f"{api}/artifacts/{artifact_id}"
        detail = products.api_json(url, token)
        if (type(detail) is not dict or any(detail.get(field) != listed.get(field) for field in (
                "id", "name", "digest", "expired", "workflow_run", "created_at",
                "archive_download_url"))
                or detail.get("archive_download_url") != url + "/zip"
                or type(detail.get("workflow_run")) is not dict
                or require_integer(detail["workflow_run"].get("id"), "Android upload run", 1) != producer["runId"]
                or detail["workflow_run"].get("head_sha") != observation["run"]["head_sha"]):
            raise ValueError("Android upload differs from its observed run or listing")
        products._require_artifact_job_window(observation, ATTACH_JOB, detail)
        require_no_signing_secret(environment)
        if (read_regular_file_bytes(source, max_bytes=16 * 1024 * 1024,
                                    reject_symlink_parents=True) != source_bytes
                or read_regular_file_bytes(captured) != source_bytes
                or canonical_json_bytes(plan) != plan_bytes
                or products.validate_producer(products._consumer(plan, environment)["producer"]) != producer):
            raise ValueError("Android locator plan or current producer changed during observation")
    return {"artifact_id": artifact_id, "artifact_sha256": digest}
