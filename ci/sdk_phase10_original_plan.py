"""Capture the independently pinned plan uploaded by the original SDK PR run.

This is external transport custody, not SDK release admission. The later
protected caller supplies every producer, artifact, workflow and file digest;
the downloaded upload cannot choose its own authority.
"""

import argparse
import os
from pathlib import Path
import shutil
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from ci import product_reuse as products
from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, publish_regular_tree, read_regular_file_bytes,
    regular_file_inventory, require_integer, require_sha256, sha256_bytes,
    sha256_file, verified_zip_contents, write_canonical_json, git_file_inventory,
    tree_entries,
)
from products.receipt import validate_producer
from products.signing_isolation import require_no_signing_secret


_PLAN_JOB = "product-validation / plan"


def require_original_lane_policy(repository_root, revision):
    """Reject dirty/extra legacy pathspecs before and after plan validation."""
    root = Path(repository_root).resolve(strict=True)
    prefix = "ci/lanes/"
    paths = tuple(path for path, _ in tree_entries(root, revision)
        if path.startswith(prefix))
    if not paths:
        raise ValueError("Original SDK checkout has no committed lane policy")
    committed = [{**row, "relativePath": row["relativePath"].removeprefix(prefix)}
        for row in git_file_inventory(root, revision, paths)]
    current = regular_file_inventory(root / "ci/lanes", allow_empty=True)
    if current != committed:
        raise ValueError("Original SDK lane policy differs from the pinned Git tree")
    return committed


def capture_sdk_phase10_original_plan(plan_path, repository_root, destination, *,
        original_producer, expected_original_producer_sha256,
        plan_artifact_id, plan_artifact_sha256, expected_plan_sha256,
        trusted_workflow_sha, token, environ=None):
    """Retain the official ZIP; repository_root must be the original commit checkout."""
    environment = os.environ if environ is None else environ
    require_no_signing_secret(environment)
    require_no_signing_secret(os.environ)
    if type(token) is not str or not token:
        raise ValueError("SDK original plan capture requires an observation token")
    producer = validate_producer(dict(original_producer))
    if sha256_bytes(canonical_json_bytes(producer)) != require_sha256(
            expected_original_producer_sha256, "Protected SDK original producer digest"):
        raise ValueError("SDK original plan producer differs from independent approval")
    if (producer["repository"] != "codex-agent-labs/codex-agent"
            or producer["workflowPath"] != ".github/workflows/ci.yml"
            or producer["event"] != "pull_request"):
        raise ValueError("SDK original plan requires an approved PR producer")
    artifact_id = require_integer(plan_artifact_id, "SDK original plan artifact ID", 1)
    artifact_sha = require_sha256(plan_artifact_sha256, "SDK original plan upload digest")
    plan_sha = require_sha256(expected_plan_sha256, "SDK original plan file digest")
    root = Path(repository_root).resolve(strict=True)
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("SDK original plan destination already exists")
    raw = read_regular_file_bytes(plan_path, max_bytes=16 * 1024 * 1024,
        reject_symlink_parents=True)
    if sha256_bytes(raw) != plan_sha:
        raise ValueError("SDK original plan differs from independent file approval")
    with tempfile.TemporaryDirectory(prefix="sdk-original-plan-") as temporary:
        private = Path(temporary).resolve()
        copy = private / "impact-plan.json"
        copy.write_bytes(raw)
        lane_policy = require_original_lane_policy(root, producer["commit"])
        plan = products._validate_plan(copy, root)
        if require_original_lane_policy(root, producer["commit"]) != lane_policy:
            raise ValueError("Original SDK lane policy changed during plan validation")
        selected = validate_producer(products._consumer(plan, {},
            original_run_id=producer["runId"],
            original_run_attempt=producer["runAttempt"])["producer"])
        if (selected != producer or plan["remoteBuildAuthorized"] is not True):
            raise ValueError("SDK original plan differs from the approved PR producer")
        observed = products._observe_ci_producer_jobs(
            {"plan": producer}, jobs_by_phase={"plan": _PLAN_JOB},
            trusted_workflow_sha=trusted_workflow_sha, token=token)[0]
        if (observed["run"].get("status") != "completed"
                or observed["run"].get("conclusion") != "success"):
            raise ValueError("SDK original plan run did not complete successfully")
        archive = private / "official-plan.zip"
        artifact, _ = products._download_contract_ci_upload(
            artifact_id, artifact_sha, f"codex-agent-ci-plan-{producer['tree']}",
            producer, observed["run"], token, destination=archive,
            max_bytes=products._CATALOG_ZIP_LIMITS["max_archive_bytes"])
        if sha256_file(archive) != artifact_sha:
            raise ValueError("SDK original plan differs from pinned official upload")
        products._require_artifact_job_window(observed, _PLAN_JOB, artifact)
        inventory, retained, _ = verified_zip_contents(archive,
            retained_paths=("impact-plan.json",), max_retained_bytes=16 * 1024 * 1024,
            allow_empty_members=True, **products._CATALOG_ZIP_LIMITS)
        if retained.get("impact-plan.json") != raw:
            raise ValueError("SDK original plan differs from pinned official upload")
        staged = private / "captured"
        (staged / "plan").mkdir(parents=True)
        (staged / "plan/impact-plan.json").write_bytes(raw)
        shutil.move(archive, staged / "official-plan.zip")
        write_canonical_json(staged / "transport.json", {
            "schemaVersion": 1, "producer": producer, "observation": observed,
            "artifact": artifact, "planSha256": plan_sha,
            "originalInventory": inventory,
            "trustedWorkflowSha": trusted_workflow_sha,
            "trustedJobName": _PLAN_JOB,
        })
        captured = regular_file_inventory(staged)
        if (read_regular_file_bytes(plan_path, max_bytes=16 * 1024 * 1024,
                    reject_symlink_parents=True) != raw
                or require_original_lane_policy(root, producer["commit"]) != lane_policy
                or sha256_file(staged / "official-plan.zip") != artifact_sha):
            raise ValueError("SDK original plan changed before capture")
        require_no_signing_secret(environment)
        require_no_signing_secret(os.environ)
        publish_regular_tree(staged, destination, expected_inventory=captured)
    return {"artifactId": artifact_id, "artifactSha256": artifact_sha,
            "planSha256": plan_sha, "files": captured}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("plan", "destination", "original-producer"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--repository-root", type=Path, required=True,
        help="separate exact original validation checkout, not trusted verifier source")
    parser.add_argument("--plan-artifact-id", type=int, required=True)
    for name in ("expected-original-producer-sha256", "plan-artifact-sha256",
                 "expected-plan-sha256", "trusted-workflow-sha"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args(argv)
    try:
        if args.destination.exists() or args.destination.is_symlink():
            raise ValueError("SDK original plan destination already exists")
        producer_raw = read_regular_file_bytes(args.original_producer,
            max_bytes=64 * 1024, reject_symlink_parents=True)
        if sha256_bytes(producer_raw) != require_sha256(
                args.expected_original_producer_sha256,
                "Protected SDK original producer digest"):
            raise ValueError("SDK original producer file differs from protected approval")
        plan_raw = read_regular_file_bytes(args.plan, max_bytes=16 * 1024 * 1024,
            reject_symlink_parents=True)
        with tempfile.TemporaryDirectory(prefix="sdk-plan-cli-") as temporary:
            private = Path(temporary).resolve() / "capture"
            result = capture_sdk_phase10_original_plan(
                args.plan, args.repository_root, private,
                original_producer=load_canonical_json_bytes(producer_raw),
                expected_original_producer_sha256=args.expected_original_producer_sha256,
                plan_artifact_id=args.plan_artifact_id,
                plan_artifact_sha256=args.plan_artifact_sha256,
                expected_plan_sha256=args.expected_plan_sha256,
                trusted_workflow_sha=args.trusted_workflow_sha,
                token=os.environ["GITHUB_TOKEN"], environ=os.environ)
            if (read_regular_file_bytes(args.original_producer, max_bytes=64 * 1024,
                    reject_symlink_parents=True) != producer_raw
                    or read_regular_file_bytes(args.plan, max_bytes=16 * 1024 * 1024,
                    reject_symlink_parents=True) != plan_raw):
                raise ValueError("SDK original plan inputs changed before final publication")
            publish_regular_tree(private, args.destination,
                expected_inventory=result["files"])
    except (OSError, ValueError, KeyError) as error:
        parser.error(str(error))
    print(canonical_json_bytes({key: result[key] for key in (
        "artifactId", "artifactSha256", "planSha256")}).decode().strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
