"""Authenticate original Apple prerequisites without rebuilding or rewriting them.

This is a source/transport qualification, not product phase admission. The
caller must still run the existing native compiler/content semantic gate.
"""
from pathlib import Path
import os
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "ci"))

import product_reuse
from receipt import parse_mapping, safe_extract, validate_receipt
from sdk_apple_native import JOBS, LANES, _native_lane_content, _receipt_producer
from sdk_apple_source import _PLAN_JOB, _original_upload, _private_original_repository
from products.inventory import (
    canonical_json_bytes, load_json_bytes, publish_regular_tree,
    read_regular_file_bytes, regular_file_inventory, require_integer,
    require_sha256, sha256_bytes, verified_zip_contents, write_canonical_json,
)
from products.registry import PhaseInstanceId
from products.selection import phase_git_inventory


# Original SDK caller already reviewed independently; not a new Runtime policy.
_ORIGINAL_SDK_WORKFLOW_SHA = "1f1e15b374ae906008bae784095654802366d63b"


def _acquire_original_revision(repository, producer):
    """Acquire missing source objects only after original CI authentication."""
    if producer["repository"] != "codex-agent-labs/codex-agent":
        raise ValueError("Apple original source repository differs")
    revision = producer["commit"]
    try:
        tree = product_reuse._git_value(repository, "--no-replace-objects", "rev-parse", revision + "^{tree}")
    except ValueError:
        try:
            subprocess.run(["git", "--no-replace-objects", "-C", str(repository), "fetch",
                "--no-tags", "--depth=1", "https://github.com/codex-agent-labs/codex-agent.git", revision],
                check=True, capture_output=True, timeout=120)
        except (OSError, subprocess.SubprocessError) as error:
            raise ValueError("Apple authenticated original source acquisition failed") from error
        tree = product_reuse._git_value(repository, "--no-replace-objects", "rev-parse", revision + "^{tree}")
    if tree != producer["tree"]:
        raise ValueError("Apple original Git tree differs from authenticated producer")


def _original_workflow(run, current):
    workflow = product_reuse._runtime_prior_workflow_sha(run, current)
    if workflow is not None:
        return workflow
    product_reuse._require_ci_workflow_reference(run,
        "codex-agent-labs/codex-agent/.github/workflows/product-validation.yml@"
        + _ORIGINAL_SDK_WORKFLOW_SHA, _ORIGINAL_SDK_WORKFLOW_SHA)
    return _ORIGINAL_SDK_WORKFLOW_SHA


def compatible_source_inventories(repository, original, current, lane):
    """Use complete registered inputs, not hand-maintained control exclusions."""
    if lane not in LANES:
        raise ValueError("Qualification supports only Apple SDK prerequisites")
    instances = [PhaseInstanceId("sdk", "sdk-ios", "binary", "ios")]
    if lane == "ios-native-tests":
        instances.extend(PhaseInstanceId("sdk", "sdk-ios", "validation", target)
                         for target in ("ios-arm64", "ios-simulator-arm64"))
    digests = []
    for instance in instances:
        before = phase_git_inventory(repository, original, instance)
        after = phase_git_inventory(repository, current, instance)
        if not before or before != after:
            raise ValueError("Apple prerequisite byte-affecting source inventory changed")
        digests.append({"phase": instance.phase, "target": instance.target,
                        "inventorySha256": sha256_bytes(canonical_json_bytes(before))})
    return digests


def _extract(archive, destination):
    inventory, _, _ = verified_zip_contents(archive, retained_paths=(),
        allow_empty_members=True, **product_reuse._CATALOG_ZIP_LIMITS)
    safe_extract(archive, destination)
    if regular_file_inventory(destination, allow_empty=True) != inventory:
        raise ValueError("Original Apple extraction differs from authenticated archive")


def qualify_candidate(arguments, artifact, *, trusted_workflow_sha, repository_root, output,
                      archive_bytes=None):
    """Publish immutable originals and separate qualification; never grant admission.

    `arguments` is the existing legacy lookup namespace. The artifact supplies
    only a locator; all metadata and original successful jobs are observed anew.
    No historical/current receipt or source inventory is edited. A mismatch
    raises and publishes nothing; the caller may continue exact candidate search.
    """
    lane = arguments.lane
    if lane not in LANES:
        raise ValueError("Qualification supports only Apple SDK prerequisites")
    token = arguments.token or os.environ.get("GITHUB_TOKEN", "")
    if not token or not trusted_workflow_sha:
        raise ValueError("Qualification needs observation token and caller workflow authority")
    repository = Path(repository_root).resolve(strict=True)
    plan_path = Path(arguments.plan)
    plan_bytes = read_regular_file_bytes(plan_path, reject_symlink_parents=True)
    plan = product_reuse._validate_plan(plan_path, repository)
    if (plan["repository"] != "codex-agent-labs/codex-agent"
            or plan["event"] not in {"pull_request", "merge_group"}
            or plan["remoteBuildAuthorized"] is not True):
        raise ValueError("Qualification requires an authorized current CI plan")
    identifier = require_integer(artifact.get("id"), "Apple candidate artifact ID", 1)
    expected_digest = require_sha256(artifact.get("digest"), "Apple candidate archive digest")
    url = f"https://api.github.com/repos/{plan['repository']}/actions/artifacts/{identifier}"
    official = product_reuse.api_json(url, token)
    if (official.get("id") != identifier or official.get("digest") != expected_digest
            or official.get("expired") is not False
            or official.get("archive_download_url") != f"{url}/zip"):
        raise ValueError("Apple candidate differs from official immutable upload")

    with tempfile.TemporaryDirectory(prefix="sdk-native-qualification-") as temporary:
        private = Path(temporary).resolve()
        capture = private / "capture"
        capture.mkdir()
        archive = capture / "original-upload.zip"
        # Rejection-boundary callers retain the already downloaded immutable body.
        # Fresh official identity and original-job checks still run below.
        if archive_bytes is None:
            product_reuse.download_artifact_to_file(official, token, archive,
                                                    max_bytes=product_reuse._CATALOG_LIMIT)
        else:
            if (type(archive_bytes) is not bytes or not archive_bytes
                    or len(archive_bytes) > product_reuse._CATALOG_LIMIT
                    or len(archive_bytes) != official.get("size_in_bytes")
                    or sha256_bytes(archive_bytes) != expected_digest):
                raise ValueError("Retained Apple body differs from official immutable upload")
            archive.write_bytes(archive_bytes)
        original_lane = capture / "lane"
        _extract(archive, original_lane)
        receipt_path = original_lane / "lane-receipt.json"
        receipt_bytes = read_regular_file_bytes(receipt_path, max_bytes=16 * 1024 * 1024,
                                                reject_symlink_parents=True)
        receipt = load_json_bytes(receipt_bytes)
        producer = _receipt_producer(receipt)
        if producer["pullRequest"] != plan["pullRequest"]:
            raise ValueError("Apple prerequisite is outside the current PR scope")
        run = product_reuse.api_json(
            f"https://api.github.com/repos/{plan['repository']}/actions/runs/{producer['runId']}"
            f"/attempts/{producer['runAttempt']}", token)
        workflow = _original_workflow(run, trusted_workflow_sha)
        observation = product_reuse._observe_ci_producer_jobs(
            {"lane": producer, "plan": producer},
            jobs_by_phase={"lane": JOBS[lane], "plan": _PLAN_JOB},
            trusted_workflow_sha=workflow, token=token)[0]
        authenticated = product_reuse._contract_ci_upload_metadata(identifier, expected_digest,
            f"codex-agent-ci-{lane}-{producer['tree']}", producer, observation["run"], token)
        if authenticated != official:
            raise ValueError("Original Apple upload metadata changed during qualification")
        product_reuse._require_artifact_job_window(observation, JOBS[lane], authenticated)
        uploads = product_reuse.paginated_items(
            f"https://api.github.com/repos/{plan['repository']}/actions/runs/{producer['runId']}/artifacts",
            "artifacts", token)
        plan_artifact, plan_raw = _original_upload(
            name=f"codex-agent-ci-plan-{producer['tree']}", producer=producer,
            observation=observation, job=_PLAN_JOB, artifacts=uploads, token=token)
        plan_archive = capture / "original-plan-upload.zip"
        plan_archive.write_bytes(plan_raw)
        _extract(plan_archive, capture / "plan")
        _acquire_original_revision(repository, producer)
        original_repository = _private_original_repository(repository,
            private / "repository", producer["commit"], plan["validationCommit"])
        original_plan = capture / "plan/impact-plan.json"
        old = product_reuse._validate_plan(original_plan, original_repository,
                                           expected_revision=producer["commit"])
        if (old["repository"], old["event"], old["pullRequest"], old["validationTree"]) != (
                producer["repository"], producer["event"], producer["pullRequest"], producer["tree"]):
            raise ValueError("Original Apple plan differs from its authenticated producer")
        # The untouched complete legacy matcher is applied to ORIGINAL inputs.
        validate_receipt(receipt_path, original_plan, original_lane, lane,
            repository_root=original_repository, runner=parse_mapping(arguments.runner),
            toolchain=parse_mapping(arguments.toolchain))
        # Qualification retains the original files; only phase admission needs
        # a second compiler-input directory. Run all content checks in place.
        _, original_producer = _native_lane_content(original_plan, producer, lane,
            original_lane, None, original_repository)
        if original_producer != producer:
            raise ValueError("Qualification requires an original upload, not a transport wrapper")
        sources = compatible_source_inventories(repository, producer["commit"],
                                                plan["validationCommit"], lane)
        qualification = {"schemaVersion": 1, "lane": lane, "originalProducer": producer,
            "originalWorkflowSha": workflow, "originalArtifact": authenticated,
            "originalPlanArtifact": plan_artifact, "observed": observation,
            "receiptSha256": sha256_bytes(receipt_bytes), "sourceInventories": sources,
            "consumerCommit": plan["validationCommit"], "consumerTree": plan["validationTree"],
            "semanticAdmissionRequired": True}
        write_canonical_json(capture / "qualification.json", qualification)
        if (read_regular_file_bytes(plan_path, reject_symlink_parents=True) != plan_bytes
                or read_regular_file_bytes(receipt_path) != receipt_bytes
                or compatible_source_inventories(repository, producer["commit"],
                    plan["validationCommit"], lane) != sources):
            raise ValueError("Apple qualification inputs changed during use")
        publish_regular_tree(capture, Path(output), allow_empty=True,
                             expected_inventory=regular_file_inventory(capture, allow_empty=True))
    return qualification
