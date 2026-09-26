"""Locate the official Runtime aggregate release upload without admitting it.

The reviewed workflow SHA is caller-owned. The returned ID/digest must still be
captured, content-verified and bound into the protected S1048 record.
"""

import argparse
import os
from pathlib import Path
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse as products
from products.inventory import canonical_json_bytes, read_regular_file_bytes, require_integer, require_sha256
from products.signing_isolation import require_no_signing_secret
from reuse import github_output


_JOB = "product-validation / runtime-aggregate-attestation"


def locate_runtime_phase10_upload(plan_path, candidate_root, *, trusted_workflow_sha, environ=None, token):
    """Return the exact successful job's current-run upload ID/digest only."""
    environment = os.environ if environ is None else environ
    require_no_signing_secret(environment)
    require_no_signing_secret(os.environ)
    if type(token) is not str or not token:
        raise ValueError("Runtime Phase-10 locator requires an observation token")
    candidate = Path(candidate_root).resolve(strict=True)
    plan_bytes = read_regular_file_bytes(plan_path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
    with tempfile.TemporaryDirectory(prefix="runtime-phase10-locator-") as temporary:
        captured_plan = Path(temporary).resolve() / "impact-plan.json"
        captured_plan.write_bytes(plan_bytes)
        plan = products._validate_plan(captured_plan, candidate)
        if plan["remoteBuildAuthorized"] is not True or plan["event"] not in {"pull_request", "merge_group"}:
            raise ValueError("Runtime Phase-10 locator requires an authorized PR or merge-group plan")
        producer = products.validate_producer(products._consumer(plan, environment)["producer"])
        observation = products._observe_ci_producer_jobs(
            {"aggregate": producer}, jobs_by_phase={"aggregate": _JOB},
            trusted_workflow_sha=trusted_workflow_sha, token=token,
        )[0]
        api = f"https://api.github.com/repos/{producer['repository']}/actions"
        name = (f"codex-agent-runtime-aggregate-release-handoff-{producer['tree']}"
                f"-attempt-{producer['runAttempt']}")
        artifacts = products.paginated_items(f"{api}/runs/{producer['runId']}/artifacts", "artifacts", token)
        selected = [item for item in artifacts if type(item) is dict
                    and item.get("name") == name and item.get("expired") is False]
        if len(selected) != 1:
            raise ValueError("Runtime Phase-10 upload is missing or ambiguous")
        listed = selected[0]
        artifact_id = require_integer(listed.get("id"), "Runtime Phase-10 upload ID", 1)
        digest = require_sha256(listed.get("digest"), "Runtime Phase-10 upload digest")
        require_integer(listed.get("size_in_bytes"), "Runtime Phase-10 upload size", 1)
        url = f"{api}/artifacts/{artifact_id}"
        detail = products.api_json(url, token)
        if (type(detail) is not dict or any(detail.get(field) != listed.get(field) for field in (
                "id", "name", "digest", "size_in_bytes", "expired", "workflow_run", "created_at"))
                or detail.get("archive_download_url") != url + "/zip"
                or type(detail.get("workflow_run")) is not dict
                or require_integer(detail["workflow_run"].get("id"), "Runtime Phase-10 upload run", 1)
                    != producer["runId"]
                or detail["workflow_run"].get("head_sha") != observation["run"]["head_sha"]):
            raise ValueError("Runtime Phase-10 upload differs from its observed run or listing")
        products._require_artifact_job_window(observation, _JOB, detail)
        require_no_signing_secret(environment)
        if (read_regular_file_bytes(plan_path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True) != plan_bytes
                or read_regular_file_bytes(captured_plan) != plan_bytes):
            raise ValueError("Runtime Phase-10 locator plan changed during observation")
    return {"artifact_id": artifact_id, "artifact_sha256": digest}


def capture_observed_runtime_phase10_upload(
        plan_path, candidate_root, destination, *, trusted_workflow_sha,
        expected_build_key, expected_metadata_receipt_sha256, environ=None, token):
    """Capture the exact located upload; product/release admission stays separate."""
    selected = locate_runtime_phase10_upload(
        plan_path, candidate_root, trusted_workflow_sha=trusted_workflow_sha,
        environ=environ, token=token,
    )
    return products.capture_runtime_aggregate_release_upload(
        plan_path, destination, **selected, trusted_workflow_sha=trusted_workflow_sha,
        expected_build_key=expected_build_key,
        expected_metadata_receipt_sha256=expected_metadata_receipt_sha256,
        repository_root=candidate_root, environ=environ, token=token,
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--candidate-root", type=Path, required=True)
    parser.add_argument("--trusted-workflow-sha", required=True)
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--expected-build-key")
    parser.add_argument("--expected-metadata-receipt-sha256")
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args(argv)
    try:
        capture = (args.destination, args.expected_build_key, args.expected_metadata_receipt_sha256)
        if any(value is not None for value in capture) and not all(value is not None for value in capture):
            raise ValueError("Runtime Phase-10 capture requires destination, build key, and metadata receipt")
        if args.destination is None:
            value = locate_runtime_phase10_upload(
                args.plan, args.candidate_root, trusted_workflow_sha=args.trusted_workflow_sha,
                environ=os.environ, token=os.environ["GITHUB_TOKEN"],
            )
        else:
            captured = capture_observed_runtime_phase10_upload(
                args.plan, args.candidate_root, args.destination,
                trusted_workflow_sha=args.trusted_workflow_sha,
                expected_build_key=args.expected_build_key,
                expected_metadata_receipt_sha256=args.expected_metadata_receipt_sha256,
                environ=os.environ, token=os.environ["GITHUB_TOKEN"],
            )
            value = {"artifact_id": captured["artifact"]["id"],
                     "artifact_sha256": captured["artifact"]["digest"]}
        if args.github_output is not None:
            github_output(args.github_output, value)
        else:
            print(canonical_json_bytes(value).decode().strip())
    except (OSError, ValueError, KeyError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
