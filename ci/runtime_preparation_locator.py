"""Locate a fixed original preparation upload; never admit its product contents."""

import argparse
import os
from pathlib import Path
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse as products
from products.inventory import canonical_json_bytes, read_regular_file_bytes, require_integer, require_sha256
from products.registry import NATIVE_TARGETS
from products.signing_isolation import require_no_signing_secret
from reuse import github_output


def locate_runtime_signing_preparation(plan_path, candidate_root, *, target,
                                      trusted_workflow_sha, environ=None, token):
    """Return only a locator; the protected consumer must recapture and verify."""
    environment = os.environ if environ is None else environ
    require_no_signing_secret(environment)
    if target not in (*NATIVE_TARGETS, "aggregate"):
        raise ValueError("Runtime preparation locator requires a native or aggregate target")
    if type(token) is not str or not token:
        raise ValueError("Runtime preparation locator requires an observation token")
    candidate = Path(candidate_root).resolve(strict=True)
    plan_bytes = read_regular_file_bytes(plan_path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
    with tempfile.TemporaryDirectory(prefix="runtime-preparation-locator-") as temporary:
        captured_plan = Path(temporary).resolve() / "impact-plan.json"
        captured_plan.write_bytes(plan_bytes)
        plan = products._validate_plan(captured_plan, candidate)
        if plan["remoteBuildAuthorized"] is not True or plan["event"] not in {"pull_request", "merge_group"}:
            raise ValueError("Runtime preparation locator requires an authorized PR or merge-group plan")
        producer = products.validate_producer(products._consumer(plan, environment)["producer"])
        job = f"product-validation / runtime-signing-prepare-{target}"
        observation = products._observe_ci_producer_jobs({"preparation": producer},
            jobs_by_phase={"preparation": job}, trusted_workflow_sha=trusted_workflow_sha, token=token)[0]
        api = f"https://api.github.com/repos/{producer['repository']}/actions"
        name = f"codex-agent-runtime-signing-preparation-{target}-{producer['tree']}-attempt-{producer['runAttempt']}"
        artifacts = products.paginated_items(f"{api}/runs/{producer['runId']}/artifacts", "artifacts", token)
        selected = [value for value in artifacts if type(value) is dict
                    and value.get("name") == name and value.get("expired") is False]
        if len(selected) != 1:
            raise ValueError("Runtime preparation upload is missing or ambiguous")
        listed = selected[0]
        artifact_id = require_integer(listed.get("id"), "Runtime preparation upload ID", 1)
        digest = require_sha256(listed.get("digest"), "Runtime preparation upload digest")
        url = f"{api}/artifacts/{artifact_id}"
        detail = products.api_json(url, token)
        if (type(detail) is not dict or any(detail.get(field) != listed.get(field) for field in (
                "id", "name", "digest", "expired", "workflow_run", "created_at"))
                or detail.get("archive_download_url") != url + "/zip"
                or type(detail.get("workflow_run")) is not dict
                or require_integer(detail["workflow_run"].get("id"), "Runtime preparation upload run", 1) != producer["runId"]
                or detail["workflow_run"].get("head_sha") != observation["run"]["head_sha"]):
            raise ValueError("Runtime preparation upload differs from its observed run or listing")
        products._require_artifact_job_window(observation, job, detail)
        require_no_signing_secret(environment)
        if (read_regular_file_bytes(plan_path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True) != plan_bytes
                or read_regular_file_bytes(captured_plan) != plan_bytes):
            raise ValueError("Runtime preparation locator plan changed during observation")
    return {"artifact_id": artifact_id, "artifact_sha256": digest}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("plan", "candidate-root"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--target", choices=(*NATIVE_TARGETS, "aggregate"), required=True)
    parser.add_argument("--trusted-workflow-sha", required=True)
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args(argv)
    try:
        value = locate_runtime_signing_preparation(args.plan, args.candidate_root, target=args.target,
            trusted_workflow_sha=args.trusted_workflow_sha, environ=os.environ, token=os.environ["GITHUB_TOKEN"])
        if args.github_output is not None:
            github_output(args.github_output, value)
        else:
            print(canonical_json_bytes(value).decode().strip())
    except (OSError, ValueError, KeyError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
