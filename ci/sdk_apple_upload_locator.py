"""Locate fixed Apple uploads; never admit or download product contents."""

import argparse
import os
from pathlib import Path
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse as products
from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, read_regular_file_bytes,
    require_integer, require_sha256,
)
from products.signing_isolation import require_no_signing_secret
from reuse import github_output


def _locate(producer, *, phase, job, name, token, trusted_workflow_sha=None,
            trusted_workflows_by_phase=None, expected_build_key=None):
    """Shared fixed-callsite observation/list/detail/window checks, no downloads."""
    producer_bytes = canonical_json_bytes(producer)
    if expected_build_key is not None:
        jobs = products.paginated_items(
            f"https://api.github.com/repos/{producer['repository']}/actions/runs/{producer['runId']}/attempts/{producer['runAttempt']}/jobs",
            "jobs", token)
        matching = products._matching_ci_jobs(jobs, job, expected_build_key=expected_build_key)
        if len(matching) != 1:
            raise ValueError("Apple original worker job is missing or ambiguous")
        job = matching[0]["name"]
    observation = products._observe_ci_producer_jobs({phase: producer},
        jobs_by_phase={phase: job}, trusted_workflow_sha=trusted_workflow_sha,
        trusted_workflows_by_phase=trusted_workflows_by_phase, token=token)[0]
    api = f"https://api.github.com/repos/{producer['repository']}/actions"
    artifacts = products.paginated_items(f"{api}/runs/{producer['runId']}/artifacts", "artifacts", token)
    selected = [value for value in artifacts if type(value) is dict
                and value.get("name") == name and value.get("expired") is False]
    if len(selected) != 1:
        raise ValueError("Apple original upload is missing or ambiguous")
    listed = selected[0]
    artifact_id = require_integer(listed.get("id"), "Apple upload ID", 1)
    digest = require_sha256(listed.get("digest"), "Apple upload digest")
    url = f"{api}/artifacts/{artifact_id}"
    detail = products.api_json(url, token)
    if (type(detail) is not dict or any(detail.get(field) != listed.get(field) for field in (
            "id", "name", "digest", "expired", "workflow_run", "created_at"))
            or detail.get("archive_download_url") != url + "/zip"
            or type(detail.get("workflow_run")) is not dict
            or require_integer(detail["workflow_run"].get("id"), "Apple upload run", 1) != producer["runId"]
            or detail["workflow_run"].get("head_sha") != observation["run"]["head_sha"]):
        raise ValueError("Apple upload differs from its observed run or listing")
    products._require_artifact_job_window(observation, job, detail)
    if canonical_json_bytes(producer) != producer_bytes:
        raise ValueError("Apple upload producer changed during observation")
    return {"artifact_id": artifact_id, "artifact_sha256": digest}


def locate_original_apple_upload(receipt_path, *, trusted_workflow_sha, token, environ=None):
    """Locate the selected original iOS binary/package upload, not current work.

    The caller must independently authenticate/select the original receipt.
    Canonical structure and official upload metadata do not replace recapture
    and complete original content admission. Current environment cannot relabel
    the receipt's producer, build key, run or attempt.
    """
    environment = os.environ if environ is None else environ
    require_no_signing_secret(environment)
    if type(token) is not str or not token:
        raise ValueError("Apple upload locator requires an observation token")
    receipt_path = Path(receipt_path).absolute()
    raw = read_regular_file_bytes(receipt_path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
    receipt = products.validate_phase_receipt(load_canonical_json_bytes(raw))
    if ((receipt["product"], receipt["component"], receipt["target"]) != ("sdk", "sdk-ios", "ios")
            or receipt["phase"] not in ("binary", "package")):
        raise ValueError("Original Apple upload locator requires an exact iOS binary or package receipt")
    producer, phase = receipt["producer"], receipt["phase"]
    job = f"product-validation / sdk-sdk-ios-{phase}-ios"
    name = (f"codex-agent-sdk-worker-sdk-ios-{phase}-ios-{receipt['buildKey'].removeprefix('sha256:')}-"
            f"{producer['tree']}-attempt-{producer['runAttempt']}")
    result = _locate(producer, phase=phase, job=job, name=name,
                     trusted_workflow_sha=trusted_workflow_sha, token=token,
                     expected_build_key=receipt["buildKey"])
    require_no_signing_secret(environment)
    if (read_regular_file_bytes(receipt_path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True) != raw
            or canonical_json_bytes(receipt) != raw):
        raise ValueError("Original Apple receipt changed during observation")
    return result


def locate_apple_upload(plan_path, candidate_root, *, mode, target,
        trusted_workflow_sha, expected_build_key=None, environ=None, token):
    """Return only an official locator; consumption must independently recapture.

    The producer is the current authorized plan/environment, not an uploaded
    receipt, a matrix output, a newest run, or a caller-supplied artifact name.
    """
    environment = os.environ if environ is None else environ
    require_no_signing_secret(environment)
    if mode not in ("validation", "preparation"):
        raise ValueError("Apple upload locator requires validation or preparation mode")
    if target not in ("ios-arm64", "ios-simulator-arm64"):
        raise ValueError("Apple upload locator requires an exact validation target")
    if mode == "validation":
        require_sha256(expected_build_key, "Selected Apple validation build key")
    elif expected_build_key is not None:
        raise ValueError("Apple preparation locator does not accept a build key")
    if type(token) is not str or not token:
        raise ValueError("Apple upload locator requires an observation token")
    candidate = Path(candidate_root).resolve(strict=True)
    plan_bytes = read_regular_file_bytes(plan_path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
    with tempfile.TemporaryDirectory(prefix="apple-upload-locator-") as temporary:
        captured_plan = Path(temporary).resolve() / "impact-plan.json"
        captured_plan.write_bytes(plan_bytes)
        plan = products._validate_plan(captured_plan, candidate)
        if plan["remoteBuildAuthorized"] is not True or plan["event"] not in {"pull_request", "merge_group"}:
            raise ValueError("Apple upload locator requires an authorized PR or merge-group plan")
        plan_value = canonical_json_bytes(plan)
        producer = products.validate_producer(products._consumer(plan, environment)["producer"])
        if mode == "validation":
            job = f"product-validation / sdk-sdk-ios-validation-{target}"
            name = (f"codex-agent-sdk-worker-sdk-ios-validation-{target}-"
                    f"{expected_build_key.removeprefix('sha256:')}-{producer['tree']}-attempt-{producer['runAttempt']}")
        else:
            job = f"product-validation / sdk-apple-signing-prepare-{target}"
            name = (f"codex-agent-sdk-apple-signing-preparation-{target}-"
                    f"{producer['tree']}-attempt-{producer['runAttempt']}")
        result = _locate(producer, phase=mode, job=job, name=name,
                         trusted_workflow_sha=trusted_workflow_sha, token=token,
                         expected_build_key=expected_build_key)
        require_no_signing_secret(environment)
        if (read_regular_file_bytes(plan_path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True) != plan_bytes
                or read_regular_file_bytes(captured_plan) != plan_bytes
                or canonical_json_bytes(plan) != plan_value
                or products.validate_producer(products._consumer(plan, environment)["producer"]) != producer):
            raise ValueError("Apple locator plan or current producer changed during observation")
    return result


def _digest(value):
    try:
        return require_sha256(value, "Apple validation build key")
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    modes = parser.add_subparsers(dest="mode", required=True)
    for mode in ("validation", "preparation"):
        command = modes.add_parser(mode, allow_abbrev=False)
        for name in ("plan", "candidate-root"):
            command.add_argument(f"--{name}", type=Path, required=True)
        command.add_argument("--target", choices=("ios-arm64", "ios-simulator-arm64"), required=True)
        command.add_argument("--trusted-workflow-sha", required=True)
        command.add_argument("--github-output", type=Path)
        if mode == "validation":
            command.add_argument("--expected-build-key", type=_digest, required=True)
    args = parser.parse_args(argv)
    try:
        value = locate_apple_upload(args.plan, args.candidate_root, mode=args.mode, target=args.target,
            trusted_workflow_sha=args.trusted_workflow_sha,
            **({"expected_build_key": args.expected_build_key} if args.mode == "validation" else {}),
            environ=os.environ, token=os.environ["GITHUB_TOKEN"])
        if args.github_output is None:
            print(canonical_json_bytes(value).decode().strip())
        else:
            github_output(args.github_output, value)
    except (OSError, ValueError, KeyError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
