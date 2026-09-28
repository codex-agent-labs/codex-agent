"""Token-only custody of independently selected Runtime candidate transports.

This is not candidate admission: the signed catalog, Phase-10 record, original
product, Maven sidecars, and landed-tree policy must still be joined and
verified before the existing exact-byte Phase-11 forwarder may run.
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
from ci.receipt import safe_extract
from ci.runtime_phase10_output_record import _observe_protected_record_dispatch
from ci.products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, publish_regular_tree,
    read_regular_file_bytes, regular_file_inventory, require_exact_keys,
    require_integer, require_sha256, sha256_bytes, sha256_file,
    verified_zip_contents, write_canonical_json,
)
from ci.products.receipt import validate_producer
from ci.products.signing_isolation import require_no_signing_secret


_REPOSITORY = "codex-agent-labs/codex-agent"
_CATALOG_WORKFLOW = ".github/workflows/runtime-promoted-catalog.yml"
_CATALOG_JOB = "runtime-promoted-catalog / runtime-promoted-catalog"
_RECORD_WORKFLOW = ".github/workflows/runtime-phase10-output-record.yml"
_RECORD_JOB = "runtime-phase10-record / runtime-phase10-output-record"
_FORBIDDEN_SECRETS = frozenset({
    "SIGNING_IN_MEMORY_KEY", "SIGNING_IN_MEMORY_KEY_PASSWORD",
    "CODEX_AGENT_SDK_RUNTIME_ROOT_ED25519_PRIVATE_KEY",
})


def validate_selection(value: dict) -> tuple[dict, dict]:
    selected = require_exact_keys(value, {"schemaVersion", "catalog", "phase10"},
                                  "Runtime candidate transport selection")
    if type(selected["schemaVersion"]) is not int or selected["schemaVersion"] != 1:
        raise ValueError("Unsupported Runtime candidate transport selection schema")
    catalog = require_exact_keys(selected["catalog"], {
        "producer", "trustedWorkflowSha", "artifactId", "artifactSha256",
        "inventorySha256", "indexSha256", "signatureSha256",
    }, "Runtime promoted catalog selection")
    phase10 = require_exact_keys(selected["phase10"], {
        "originalProducer", "recordProducer", "trustedRecordWorkflowSha",
        "artifactId", "artifactSha256", "recordSha256", "signatureSha256",
    }, "Runtime Phase-10 record selection")
    promoted = validate_producer(catalog["producer"])
    original = validate_producer(phase10["originalProducer"])
    record = validate_producer(phase10["recordProducer"])
    if (promoted["repository"] != _REPOSITORY or promoted["event"] != "push"
            or promoted["workflowPath"] != ".github/workflows/promote.yml"
            or original["repository"] != _REPOSITORY
            or original["workflowPath"] != ".github/workflows/ci.yml"
            or original["event"] not in {"pull_request", "merge_group"}
            or record["repository"] != _REPOSITORY
            or record["workflowPath"] != ".github/workflows/ci.yml"
            or record["event"] != "workflow_dispatch"
            or len({promoted["runId"], original["runId"], record["runId"]}) != 3
            or promoted["tree"] != original["tree"]):
        raise ValueError("Runtime selected producers are not distinct promoted/Phase-10 originals")
    for label, sha in (("catalog workflow", catalog["trustedWorkflowSha"]),
                       ("record workflow", phase10["trustedRecordWorkflowSha"])):
        if type(sha) is not str or re.fullmatch(r"[0-9a-f]{40}", sha) is None:
            raise ValueError(f"Runtime {label} must be an exact Git commit")
    for group in (catalog, phase10):
        require_integer(group["artifactId"], "Runtime candidate upload ID", 1)
        for name in ("artifactSha256", "inventorySha256", "indexSha256", "signatureSha256") if group is catalog \
                else ("artifactSha256", "recordSha256", "signatureSha256"):
            require_sha256(group[name], f"Runtime candidate {name}")
    if catalog["artifactId"] == phase10["artifactId"]:
        raise ValueError("Runtime catalog and record must be distinct official uploads")
    return catalog, phase10


def _observe_catalog(producer: dict, workflow_sha: str, token: str) -> dict:
    base = f"https://api.github.com/repos/{_REPOSITORY}"
    attempt = f"{base}/actions/runs/{producer['runId']}/attempts/{producer['runAttempt']}"
    run = transport.api_json(attempt, token)
    if (type(run) is not dict
            or require_integer(run.get("id"), "Runtime promotion run", 1) != producer["runId"]
            or require_integer(run.get("run_attempt"), "Runtime promotion attempt", 1)
                != producer["runAttempt"]
            or run.get("path") != producer["workflowPath"]
            or run.get("event") != "push" or run.get("head_branch") != "main"
            or run.get("head_sha") != producer["commit"]
            or run.get("status") != "completed" or run.get("conclusion") != "success"
            or any(type(run.get(field)) is not dict
                   or run[field].get("full_name") != _REPOSITORY
                   or run[field].get("fork") is not False
                   for field in ("repository", "head_repository"))):
        raise ValueError("Runtime catalog lacks successful official protected-main run")
    transport._require_ci_workflow_reference(
        run, f"{_REPOSITORY}/{_CATALOG_WORKFLOW}@{workflow_sha}", workflow_sha)
    commit = transport.api_json(f"{base}/git/commits/{producer['commit']}", token)
    if (type(commit) is not dict or commit.get("sha") != producer["commit"]
            or type(commit.get("tree")) is not dict
            or commit["tree"].get("sha") != producer["tree"]):
        raise ValueError("Runtime catalog official commit differs from selected tree")
    jobs = transport.paginated_items(f"{attempt}/jobs", "jobs", token)
    if any(type(job) is not dict for job in jobs):
        raise ValueError("Runtime promotion jobs are malformed")
    selected = [job for job in jobs if job.get("name") == _CATALOG_JOB]
    if (len(selected) != 1
            or require_integer(selected[0].get("id"), "Runtime promotion job", 1) < 1
            or require_integer(selected[0].get("run_id"), "Runtime promotion job run", 1)
                != producer["runId"]
            or selected[0].get("head_sha") != producer["commit"]
            or selected[0].get("status") != "completed"
            or selected[0].get("conclusion") != "success"):
        raise ValueError("Runtime catalog producer job is missing or unsuccessful")
    return {"run": run, "testedCommit": commit, "jobs": jobs}


def capture_runtime_candidate_transports(selection: dict, destination: Path, *,
                                         token: str, environ=None) -> dict:
    """Retain exact official catalog/record ZIPs and observations, without admission."""
    environment = os.environ if environ is None else environ
    require_no_signing_secret(environment)
    require_no_signing_secret(os.environ)
    if _FORBIDDEN_SECRETS & (set(environment) | set(os.environ)):
        raise ValueError("Runtime candidate observer must not receive signing secrets")
    catalog, phase10 = validate_selection(selection)
    if type(token) is not str or not token:
        raise ValueError("Runtime candidate observer requires an observation token")
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Runtime candidate transport destination already exists")
    with tempfile.TemporaryDirectory(prefix="runtime-candidate-transport-") as temporary:
        root = Path(temporary).resolve()
        staged = root / "retained"
        staged.mkdir()
        observed_catalog = _observe_catalog(catalog["producer"], catalog["trustedWorkflowSha"], token)
        observed_record = _observe_protected_record_dispatch(
            phase10["recordProducer"], workflow_path=_RECORD_WORKFLOW,
            workflow_sha=phase10["trustedRecordWorkflowSha"],
            job_name=_RECORD_JOB, token=token)
        routes = (
            ("catalog", catalog, catalog["producer"], observed_catalog,
             f"codex-agent-promoted-runtime-catalog-{catalog['producer']['commit']}-"
             f"{catalog['producer']['runId']}-{catalog['producer']['runAttempt']}",
             {"caller.json", "catalog/product-index.json", "catalog/product-index.sig"},
             _CATALOG_JOB),
            ("phase10-record", phase10, phase10["recordProducer"], observed_record,
             f"codex-agent-runtime-phase10-output-record-{phase10['originalProducer']['tree']}"
             f"-attestation-{phase10['recordProducer']['runId']}"
             f"-attempt-{phase10['recordProducer']['runAttempt']}",
             {"record.json", "record.sig"}, _RECORD_JOB),
        )
        observations = {}
        for label, pins, producer, observed, name, members, job in routes:
            archive = staged / f"{label}.zip"
            artifact, _ = transport._download_contract_ci_upload(
                pins["artifactId"], pins["artifactSha256"], name,
                producer, observed["run"], token, destination=archive)
            transport._require_artifact_job_window(observed, job, artifact)
            inventory, _, _ = verified_zip_contents(
                archive, retained_paths=(), allow_empty_members=True,
                **transport._CATALOG_ZIP_LIMITS)
            paths = {entry["relativePath"] for entry in inventory}
            if label == "catalog":
                if (not members <= paths or any(path.split("/", 1)[0] not in {
                        "caller.json", "catalog", "original-evidence", "trust"}
                        for path in paths)):
                    raise ValueError("Runtime catalog upload has unexpected or missing members")
            elif paths != members:
                raise ValueError("Runtime Phase-10 record upload has unexpected members")
            extracted = staged / label
            safe_extract(archive, extracted)
            if regular_file_inventory(extracted) != inventory:
                raise ValueError(f"Runtime {label} extraction differs from official ZIP")
            if label == "catalog":
                if (sha256_bytes(canonical_json_bytes(inventory)) != pins["inventorySha256"]
                        or sha256_file(extracted / "catalog/product-index.json") != pins["indexSha256"]
                        or sha256_file(extracted / "catalog/product-index.sig") != pins["signatureSha256"]):
                    raise ValueError("Runtime catalog bytes differ from independent S1048 pins")
            elif (sha256_file(extracted / "record.json") != pins["recordSha256"]
                    or sha256_file(extracted / "record.sig") != pins["signatureSha256"]):
                raise ValueError("Runtime Phase-10 record differs from independent S1048 pins")
            observations[label] = {"artifact": artifact, "observation": observed,
                                   "producer": producer, "files": inventory}
        write_canonical_json(staged / "transport.json", {"schemaVersion": 1,
            "selectionSha256": sha256_bytes(canonical_json_bytes(selection)),
            "routes": observations})
        before = regular_file_inventory(staged)
        for label, pins, _, _, _, _, _ in routes:
            if (sha256_file(staged / f"{label}.zip") != pins["artifactSha256"]
                    or regular_file_inventory(staged / label) != observations[label]["files"]):
                raise ValueError("Runtime candidate official transport changed before retention")
        require_no_signing_secret(environment)
        require_no_signing_secret(os.environ)
        if _FORBIDDEN_SECRETS & (set(environment) | set(os.environ)):
            raise ValueError("Runtime candidate observer acquired a signing secret")
        publish_regular_tree(staged, destination, expected_inventory=before)
    return {"admitted": False, "selectionSha256": sha256_bytes(canonical_json_bytes(selection)),
            "files": before}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--expected-selection-sha256", required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args(argv)
    raw = read_regular_file_bytes(args.selection, max_bytes=64 * 1024,
                                  reject_symlink_parents=True)
    if sha256_bytes(raw) != require_sha256(
            args.expected_selection_sha256, "independently approved Runtime selection"):
        raise ValueError("Runtime candidate transport selection differs from S1048 pin")
    result = capture_runtime_candidate_transports(
        load_canonical_json_bytes(raw), args.destination,
        token=os.environ["GITHUB_TOKEN"], environ=os.environ)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
