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
ANDROID_WORKFLOW_REFERENCE = f"{REPOSITORY}/{ANDROID_WORKFLOW}@reuse-authority"
FIREBASE_JOB = "product-validation / android-runtime-evidence / firebase-arm64-runtime"
ATTACH_JOB = "product-validation / android-runtime-evidence / attach-evidence"
_OID = re.compile(r"[0-9a-f]{40}")


def retained_android_evidence_origin(build_key, consumer, *, phase="validation"):
    """Select reviewed device evidence, not a validation verdict or new producer."""
    if (phase == "metadata" and
            build_key == "sha256:6390796ea14dbff3a02840ccbe8683f08976985da6dbc3a4dec533d8937c50ba"):
        from sdk_campaign_original_locator import retained_core_origin
        origin = retained_core_origin(phase, build_key, consumer, component="sdk-android", target="android")
        if origin is None:
            return None
        # Metadata routing needs only the original caller's authority. The worker
        # and collector still authenticate the original upload and its contents.
        return {"authority": {"schemaVersion": 1,
            "trustedAndroidWorkflowSha": origin["workflow_sha"],
            "trustedSourceCommit": "d8fff91c7fde6e3721fe4979fe911e2020dc7eda",
            "trustedSourceTree": origin["producer"]["tree"]}}
    producer = {"repository": REPOSITORY, "workflowPath": ".github/workflows/ci.yml",
        "commit": "986d173ae4c05cf3ec456bef463641376a65e6d3",
        "tree": "554dee42106c5c00e0114d166fb2c52b2a5aa1e0", "event": "pull_request",
        "runId": 39012954522, "runAttempt": 2, "pullRequest": 31}
    expected = {"validation": "sha256:2ff282b398d370be407038bdbf3e4cace0ef024c1c9d2e2f0fca5ba20a228637",
                "metadata": "sha256:a0b5893e50c08d2f0386781d732032a075d4032717fe36648becd8c43e22b93d"}
    if (phase not in expected or build_key != expected[phase]
            or any(consumer.get(name) != producer[name]
                   for name in ("repository", "workflowPath", "event", "pullRequest"))
            or any(type(consumer.get(name)) is not int or consumer[name] < 1
                   for name in ("runId", "runAttempt"))
            or (consumer["runId"], consumer["runAttempt"]) <= (producer["runId"], producer["runAttempt"])):
        return None
    return {"producer": producer,
        "workflowSha": "26622ad8247c4c411890d22bc3519332ad11fb25",
        "authority": {"schemaVersion": 1,
            "trustedAndroidWorkflowSha": "26622ad8247c4c411890d22bc3519332ad11fb25",
            "trustedSourceCommit": "acb00a8f065d86e96ec047b17db7fc33fd2b2992",
            "trustedSourceTree": "554dee42106c5c00e0114d166fb2c52b2a5aa1e0"},
        "final": {"artifact_id": 12094264612,
            "artifact_sha256": "sha256:a04694b9c916300ba3e68db3665f132894a8b5e8fdfd14787e68d2f4434eec38"},
        "protected": {"artifact_id": 12094334017,
            "artifact_sha256": "sha256:731bbd6c9795735f1bcbe629fb2433c69c5ed74b18804bd6e6a47187be4fb113"}}


def require_retained_android_authority(origin, *, trusted_source_commit, trusted_source_tree,
                                       trusted_android_workflow_sha=None):
    if origin is None:
        return
    authority = origin["authority"]
    if (trusted_source_commit != authority["trustedSourceCommit"]
            or trusted_source_tree != authority["trustedSourceTree"]
            or trusted_android_workflow_sha is not None and
               trusted_android_workflow_sha != authority["trustedAndroidWorkflowSha"]):
        raise ValueError("Retained Android evidence differs from caller-owned source/workflow authority")


def require_retained_android_capture(origin, final, protected):
    if origin is not None and any(
            value.get("captureProducer") != origin["producer"] or value.get("locator") != origin[name]
            for name, value in (("final", final), ("protected", protected))):
        raise ValueError("Retained Android capture differs from its reviewed original identity")


def capture_retained_android_plan(origin, root, destination, *, token):
    """One scoped reader, four pinned controls; no product body or trust shortcut."""
    from runtime_reference_archive import open_reference_archive, copy_reference_member
    from runtime_reference_transport import count
    producer = {**origin["producer"], "runAttempt": 1}  # Original successful planner, never retry alias.
    job = "product-validation / plan"
    observed = products._observe_ci_producer_jobs({"plan": producer}, jobs_by_phase={"plan": job},
        trusted_workflow_sha=origin["workflowSha"], token=token)[0]
    artifact = products._contract_ci_upload_metadata(12093438301,
        "sha256:f08b52c4fe7e730d23129e235061d381b3cb3437c12ceecf87893e3218beda52",
        "codex-agent-ci-plan-" + producer["tree"], producer, observed["run"], token)
    products._require_artifact_job_window(observed, job, artifact)
    members = {
        "impact-plan.json": (166986, "7beceac7d13ba4fc92018494d28f52887d5ba55b4f05ff661c9edebfb39a5261"),
        "inventories/android/production-inputs.git-tree": (115438, "2fbe0ee28e686d8874c7e5444e0235b3cfafbd5717eb360d1b69fa50ed1f1e4a"),
        "inventories/android/test-inputs.git-tree": (1911, "65be67ce424143079d3ee33943cb5161f0a7a136447af8a42a2a3d3f29bf2cf3"),
        "inventories/android/metadata-inputs.git-tree": (314, "04f68e123cb2c77b5863adc88dfe4930d401ef99d4e7e7881f198de93fbc9f4c"),
    }
    destination = Path(destination)
    if destination.exists() or destination.is_symlink() or destination.resolve(strict=False) != destination:
        raise ValueError("Retained Android plan destination must be fresh and non-symbolic")
    with open_reference_archive(artifact, token, max_bytes=16 * 1024**2) as (archive, stream):
        for name, (size, digest) in members.items():
            copy_reference_member(archive, name, destination / name,
                {"bytes": size, "sha256": "sha256:" + digest})
        count("androidRetainedPlanRangeBytes", stream.transferred)
    plan = destination / "impact-plan.json"
    products._validate_plan(plan, root, expected_revision=producer["commit"])
    return plan


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
    still require independent admission. Protected dispatch additionally requires
    the exact-attempt, caller-pinned environment-gated job observation.
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
                or plan.get("event") not in {"pull_request", "merge_group", "workflow_dispatch"}
                or plan.get("androidEvidenceRequired") is not True
                or type(android) is not dict
                or not any(android.get(action) is True for action in ("build", "test", "metadata"))):
            raise ValueError("Android upload locator requires authorized Android evidence work")
        plan_bytes = canonical_json_bytes(plan)
        producer = products.validate_producer(products._consumer(plan, environment)["producer"])
        if producer["event"] == "workflow_dispatch":
            from sdk_android_dispatch_observer import observe_android_protected_dispatch
            observation = observe_android_protected_dispatch(producer,
                trusted_workflow_sha=trusted_workflow_sha,
                trusted_android_workflow_sha=trusted_android_workflow_sha, token=token)
        else:
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
        # @reuse-authority. Its resolved `sha` is a separate official observation and is
        # pinned by the caller of this locator; do not conflate the two fields.
        expected = ANDROID_WORKFLOW_REFERENCE
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
