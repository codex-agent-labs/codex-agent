"""Token-only capture of an independently pinned, official SDK promoted catalog.

This is transport custody, not release admission. The candidate join verifies
the signed index and exact Phase-10 objects after this capture.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
import tempfile

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ci import product_reuse as transport
from ci.products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, publish_regular_tree,
    read_regular_file_bytes, regular_file_inventory, require_exact_keys,
    require_integer, require_sha256, sha256_bytes, sha256_file,
    verified_zip_contents,
)
from ci.products.receipt import validate_producer
from ci.products.signing_isolation import require_no_signing_secret
from ci.receipt import safe_extract


_REPOSITORY = "codex-agent-labs/codex-agent"
_WORKFLOW = ".github/workflows/sdk-promoted-catalog.yml"
_JOB = "sdk-promoted-catalog / sdk-promoted-catalog-sign"
_FIELDS = {"schemaVersion", "producer", "trustedWorkflowSha", "artifactId",
           "artifactSha256", "inventorySha256", "indexSha256", "signatureSha256"}


def _selection(value: dict) -> dict:
    selected = require_exact_keys(value, _FIELDS, "SDK candidate catalog selection")
    if type(selected["schemaVersion"]) is not int or selected["schemaVersion"] != 1:
        raise ValueError("Unsupported SDK candidate catalog selection schema")
    producer = validate_producer(selected["producer"])
    if (producer["repository"] != _REPOSITORY
            or producer["workflowPath"] != ".github/workflows/promote.yml"
            or producer["event"] != "push" or producer["pullRequest"] is not None):
        raise ValueError("SDK candidate catalog requires promoted-main producer")
    if (type(selected["trustedWorkflowSha"]) is not str or
            re.fullmatch(r"[0-9a-f]{40}", selected["trustedWorkflowSha"]) is None):
        raise ValueError("SDK candidate catalog requires exact child-workflow commit")
    require_integer(selected["artifactId"], "SDK promoted artifact ID", 1)
    for field in ("artifactSha256", "inventorySha256", "indexSha256", "signatureSha256"):
        require_sha256(selected[field], f"SDK promoted {field}")
    return selected


def _observe(producer: dict, workflow_sha: str, token: str) -> dict:
    base = f"https://api.github.com/repos/{_REPOSITORY}"
    attempt = f"{base}/actions/runs/{producer['runId']}/attempts/{producer['runAttempt']}"
    run = transport.api_json(attempt, token)
    if (type(run) is not dict
            or require_integer(run.get("id"), "SDK promotion run", 1) != producer["runId"]
            or require_integer(run.get("run_attempt"), "SDK promotion attempt", 1)
                != producer["runAttempt"]
            or run.get("path") != producer["workflowPath"]
            or run.get("event") != "push" or run.get("head_branch") != "main"
            or run.get("head_sha") != producer["commit"]
            or run.get("status") != "completed" or run.get("conclusion") != "success"
            or any(type(run.get(field)) is not dict
                   or run[field].get("full_name") != _REPOSITORY
                   or run[field].get("fork") is not False
                   for field in ("repository", "head_repository"))):
        raise ValueError("SDK catalog lacks successful official promoted-main run")
    transport._require_ci_workflow_reference(
        run, f"{_REPOSITORY}/{_WORKFLOW}@{workflow_sha}", workflow_sha)
    commit = transport.api_json(f"{base}/git/commits/{producer['commit']}", token)
    if (type(commit) is not dict or commit.get("sha") != producer["commit"]
            or type(commit.get("tree")) is not dict
            or commit["tree"].get("sha") != producer["tree"]):
        raise ValueError("SDK promoted catalog run has a different Git tree")
    jobs = transport.paginated_items(f"{attempt}/jobs", "jobs", token)
    if any(type(job) is not dict for job in jobs):
        raise ValueError("SDK promotion jobs are malformed")
    matches = [job for job in jobs if job.get("name") == _JOB]
    if len(matches) != 1 or (
            require_integer(matches[0].get("run_id"), "SDK catalog job run", 1)
            != producer["runId"] or matches[0].get("head_sha") != producer["commit"]
            or matches[0].get("status") != "completed"
            or matches[0].get("conclusion") != "success"):
        raise ValueError("SDK promoted catalog sign job is missing or unsuccessful")
    require_integer(matches[0].get("id"), "SDK promoted job ID", 1)
    return {"run": run, "testedCommit": commit, "jobs": jobs}


def capture_sdk_candidate_catalog(selection: dict, destination: Path, *, token: str,
                                  environ=None) -> dict:
    environment = os.environ if environ is None else environ
    require_no_signing_secret(environment)
    require_no_signing_secret(os.environ)
    if type(token) is not str or not token:
        raise ValueError("SDK catalog capture requires an observation token")
    selected = _selection(selection)
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("SDK candidate catalog destination already exists")
    producer = selected["producer"]
    observed = _observe(producer, selected["trustedWorkflowSha"], token)
    name = (f"codex-agent-promoted-sdk-catalog-{producer['commit']}-"
            f"{producer['runId']}-{producer['runAttempt']}")
    with tempfile.TemporaryDirectory(prefix="sdk-candidate-catalog-") as temporary:
        root = Path(temporary).resolve()
        archive = root / "official-upload.zip"
        artifact, _ = transport._download_contract_ci_upload(
            selected["artifactId"], selected["artifactSha256"], name,
            producer, observed["run"], token, destination=archive)
        transport._require_artifact_job_window(observed, _JOB, artifact)
        listing, _, _ = verified_zip_contents(
            archive, retained_paths=(), allow_empty_members=True,
            **transport._CATALOG_ZIP_LIMITS)
        extracted = root / "catalog"
        safe_extract(archive, extracted)
        files = regular_file_inventory(extracted)
        if (files != listing
                or sha256_file(archive) != selected["artifactSha256"]
                or sha256_bytes(canonical_json_bytes(files)) != selected["inventorySha256"]
                or sha256_file(extracted / "product-index.json") != selected["indexSha256"]
                or sha256_file(extracted / "product-index.sig") != selected["signatureSha256"]):
            raise ValueError("SDK promoted catalog differs from independent S1048 pins")
        if (regular_file_inventory(extracted) != files
                or sha256_file(archive) != selected["artifactSha256"]):
            raise ValueError("SDK official catalog changed during capture")
        require_no_signing_secret(environment)
        require_no_signing_secret(os.environ)
        publish_regular_tree(extracted, destination, expected_inventory=files)
    return {"artifactId": selected["artifactId"],
            "artifactSha256": selected["artifactSha256"],
            "inventorySha256": selected["inventorySha256"]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--expected-selection-sha256", required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args(argv)
    raw = read_regular_file_bytes(args.selection, max_bytes=64 * 1024,
                                  reject_symlink_parents=True)
    if sha256_bytes(raw) != require_sha256(
            args.expected_selection_sha256, "SDK candidate catalog selection"):
        raise ValueError("SDK catalog selection differs from protected S1048 digest")
    result = capture_sdk_candidate_catalog(
        load_canonical_json_bytes(raw), args.destination, token=os.environ["GITHUB_TOKEN"])
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
