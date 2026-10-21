"""Token-only capture of independently pinned SDK catalog, parity or Runtime evidence.

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
import time

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ci import product_reuse as transport
from ci.sdk_candidate_admission import _SECRETS
from ci.products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, publish_regular_tree,
    read_regular_file_bytes, regular_file_inventory, require_exact_keys,
    require_integer, require_regular_directory, require_sha256, sha256_bytes, sha256_file,
    verified_zip_contents, write_canonical_json,
)
from ci.products.receipt import validate_producer
from ci.products.signing_isolation import require_no_signing_secret
from ci.receipt import safe_extract


_REPOSITORY = "codex-agent-labs/codex-agent"
_WORKFLOW = ".github/workflows/sdk-promoted-catalog.yml"
_JOB = "sdk-promoted-catalog / sdk-promoted-catalog-sign"
_FIELDS = {"schemaVersion", "producer", "trustedWorkflowSha", "artifactId",
           "artifactSha256", "inventorySha256", "indexSha256", "signatureSha256"}
_PARITY_JOB = "product-validation / sdk-parity / sdk-parity"
_PARITY_WORKFLOW = ".github/workflows/sdk-binding-parity.yml"
_PARITY_LIMIT = 32 * 1024 * 1024
_RUNTIME_JOB = "runtime-library-authorizations / runtime-library-release-authorizations"
_RUNTIME_WORKFLOW = ".github/workflows/runtime-library-authorizations.yml"
_RUNTIME_LIMIT = 512 * 1024 * 1024


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


def _parity_selection(value: dict) -> dict:
    selected = require_exact_keys(value, {"schemaVersion", "producer", "trustedWorkflowSha", "jobId",
        "artifactId", "artifactSha256", "artifactBytes", "phaseIdentitiesSha256"},
        "SDK candidate parity selection")
    if type(selected["schemaVersion"]) is not int or selected["schemaVersion"] != 1:
        raise ValueError("Unsupported SDK candidate parity selection schema")
    producer = validate_producer(selected["producer"])
    if (producer["repository"] != _REPOSITORY or producer["workflowPath"] != ".github/workflows/ci.yml"
            or producer["event"] not in {"pull_request", "merge_group"}
            or producer["event"] == "pull_request" and producer["pullRequest"] != 31):
        raise ValueError("SDK candidate parity requires the approved PR or merge-group original")
    if (type(selected["trustedWorkflowSha"]) is not str
            or re.fullmatch(r"[0-9a-f]{40}", selected["trustedWorkflowSha"]) is None):
        raise ValueError("SDK candidate parity workflow must be commit-pinned")
    for field in ("artifactId", "jobId", "artifactBytes"):
        require_integer(selected[field], "SDK parity " + field, 1)
    if selected["artifactBytes"] > _PARITY_LIMIT:
        raise ValueError("SDK candidate parity exceeds its bounded evidence size")
    for field in ("artifactSha256", "phaseIdentitiesSha256"):
        require_sha256(selected[field], "SDK parity " + field)
    return selected


def capture_sdk_candidate_parity(selection: dict, archive: Path, destination: Path, *, token: str,
                                 environ=None) -> dict:
    """Authenticate the original upload; retain only its phase member and provenance.

    A held archive is rehashed, never overwritten or redownloaded. The original
    ZIP stays at the caller's path; only small controls are atomically published.
    Candidate semantics still joins all112 identities and the complete M11 content
    against the signed SDK campaign after the token has left the process.
    """
    environment = os.environ if environ is None else environ
    require_no_signing_secret(environment)
    if _SECRETS & (set(environment) | set(os.environ)):
        raise ValueError("SDK parity observer must not receive signing secrets")
    if type(token) is not str or not token:
        raise ValueError("SDK parity observer requires an observation token")
    selected = _parity_selection(selection)
    approved = canonical_json_bytes(selected)
    archive, destination = Path(archive).absolute(), Path(destination).absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError("SDK parity capture destination already exists")
    require_regular_directory(archive.parent, "SDK parity archive parent")
    if archive == destination or destination in archive.parents:
        raise ValueError("SDK parity capture overlaps the retained archive")
    started = time.monotonic_ns()
    producer = selected["producer"]
    observed, = transport._observe_ci_producer_jobs({"parity": producer},
        jobs_by_phase={"parity": _PARITY_JOB}, token=token,
        trusted_workflows_by_phase={"parity": {"path": _PARITY_WORKFLOW,
            "sha": selected["trustedWorkflowSha"]}})
    job, = transport._matching_ci_jobs(observed["jobs"], _PARITY_JOB)
    if job["id"] != selected["jobId"]:
        raise ValueError("SDK candidate parity differs from the approved successful job")
    artifact = transport._contract_ci_upload_metadata(selected["artifactId"], selected["artifactSha256"],
        "codex-agent-sdk-binding-parity-" + producer["tree"], producer, observed["run"], token)
    transport._require_artifact_job_window(observed, _PARITY_JOB, artifact)
    if artifact["size_in_bytes"] != selected["artifactBytes"]:
        raise ValueError("SDK parity upload size differs from independent approval")
    held = archive.exists() or archive.is_symlink()
    if not held:
        # Metadata/window admission above precedes acquisition; reuse the same
        # observed artifact instead of querying its metadata a second time.
        transport._reuse_contract_ci_upload(artifact, producer, observed["run"], token,
            destination=archive, limit=_PARITY_LIMIT,
            artifact_sha256=selected["artifactSha256"], size=selected["artifactBytes"])
    _, retained, identity = verified_zip_contents(archive,
        retained_paths=("original-phase-identities.json",), max_retained_bytes=512 * 1024,
        max_archive_bytes=_PARITY_LIMIT, max_members=32, max_entry_bytes=16 * 1024 * 1024,
        max_total_bytes=_PARITY_LIMIT, require_sorted=False)
    phases = retained.get("original-phase-identities.json")
    if (identity != {"bytes": selected["artifactBytes"], "sha256": selected["artifactSha256"]}
            or phases is None or sha256_bytes(phases) != selected["phaseIdentitiesSha256"]):
        raise ValueError("SDK parity bytes differ from the independently selected original")
    if type(load_canonical_json_bytes(phases)) is not list:
        raise ValueError("SDK parity phase identities must be a canonical array")
    with tempfile.TemporaryDirectory(prefix="sdk-candidate-parity-") as temporary:
        prepared = Path(temporary).resolve()
        (prepared / "original-phase-identities.json").write_bytes(phases)
        write_canonical_json(prepared / "transport.json", {
            "schemaVersion": 1, "producer": producer, "observed": {**observed, "jobs": [job]}, "artifact": artifact,
            "trustedWorkflowSha": selected["trustedWorkflowSha"], "selectionSha256": sha256_bytes(approved),
            "phaseIdentitiesSha256": selected["phaseIdentitiesSha256"], "heldArchive": held,
        })
        files = regular_file_inventory(prepared)
        require_no_signing_secret(environment)
        if (_SECRETS & (set(environment) | set(os.environ))
                or canonical_json_bytes(selected) != approved
                or sha256_file(archive, reject_symlink_parents=True) != selected["artifactSha256"]):
            raise ValueError("SDK parity capture inputs changed during observation")
        publish_regular_tree(prepared, destination, expected_inventory=files)
    return {"admitted": False, "artifactId": selected["artifactId"],
            "artifactSha256": selected["artifactSha256"], "heldArchive": held,
            "capturedControlBytes": sum(row["bytes"] for row in files),
            "captureInventorySha256": sha256_bytes(canonical_json_bytes(files)),
            "elapsedNs": time.monotonic_ns() - started}


def _runtime_selection(value: dict) -> dict:
    selected = require_exact_keys(value, {"schemaVersion", "producer", "trustedWorkflowSha", "jobId",
        "artifactId", "artifactSha256", "artifactBytes", "validationCommit", "inventorySha256"},
        "SDK candidate Runtime selection")
    if type(selected["schemaVersion"]) is not int or selected["schemaVersion"] != 1:
        raise ValueError("Unsupported SDK candidate Runtime selection schema")
    producer = validate_producer(selected["producer"])
    if (producer["repository"] != _REPOSITORY or producer["workflowPath"] != ".github/workflows/ci.yml"
            or producer["event"] != "workflow_dispatch" or producer["pullRequest"] is not None):
        raise ValueError("SDK candidate Runtime requires fixed protected dispatch producer")
    for field in ("trustedWorkflowSha", "validationCommit"):
        if type(selected[field]) is not str or re.fullmatch(r"[0-9a-f]{40}", selected[field]) is None:
            raise ValueError("SDK candidate Runtime requires exact source and workflow pins")
    for field in ("artifactId", "jobId", "artifactBytes"):
        require_integer(selected[field], "SDK candidate Runtime " + field, 1)
    if selected["artifactBytes"] > _RUNTIME_LIMIT:
        raise ValueError("SDK candidate Runtime upload exceeds its library-only bound")
    for field in ("artifactSha256", "inventorySha256"):
        require_sha256(selected[field], "SDK candidate Runtime " + field)
    return selected


def capture_sdk_candidate_runtime(selection: dict, archive: Path, destination: Path, *, token: str,
                                  environ=None) -> dict:
    """Authenticate only the five-library upload, preserving its original ZIP.

    No aggregate or variant bundles are consumed here. Only small custody controls
    are published; extraction and root/default checks belong to the offline SDK
    candidate join. Runtime publication still requires its complete aggregate gate.
    """
    from ci.products.runtime_library_authorization import _LIBRARY_PATHS
    environment = os.environ if environ is None else environ
    require_no_signing_secret(environment)
    require_no_signing_secret(os.environ)
    if _SECRETS & (set(environment) | set(os.environ)):
        raise ValueError("SDK Runtime observer must not receive signing secrets")
    if type(token) is not str or not token:
        raise ValueError("SDK Runtime observer requires an observation token")
    selected = _runtime_selection(selection)
    approved = canonical_json_bytes(selected)
    archive, destination = Path(archive).absolute(), Path(destination).absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError("SDK Runtime capture destination already exists")
    require_regular_directory(archive.parent, "SDK Runtime archive parent")
    if archive == destination or destination in archive.parents:
        raise ValueError("SDK Runtime capture overlaps the retained archive")
    started = time.monotonic_ns()
    producer = selected["producer"]
    observed, = transport._observe_ci_producer_jobs({"runtime": producer},
        jobs_by_phase={"runtime": _RUNTIME_JOB}, token=token, allow_protected_dispatch=True,
        dispatch_authorization_job=None, trusted_workflows_by_phase={"runtime": {
            "path": _RUNTIME_WORKFLOW, "sha": selected["trustedWorkflowSha"]}})
    job, = transport._matching_ci_jobs(observed["jobs"], _RUNTIME_JOB)
    if (job["id"] != selected["jobId"] or observed["run"].get("status") != "completed"
            or observed["run"].get("conclusion") != "success"):
        raise ValueError("SDK Runtime upload lacks the approved successful full authorization dispatch")
    name = (f"codex-agent-runtime-library-authorizations-{selected['validationCommit']}"
            f"-attestation-{producer['runId']}-attempt-{producer['runAttempt']}")
    artifact = transport._contract_ci_upload_metadata(selected["artifactId"], selected["artifactSha256"],
        name, producer, observed["run"], token)
    transport._require_artifact_job_window(observed, _RUNTIME_JOB, artifact)
    if artifact["size_in_bytes"] != selected["artifactBytes"]:
        raise ValueError("SDK Runtime upload size differs from independent approval")
    held = archive.exists() or archive.is_symlink()
    if not held:
        transport._reuse_contract_ci_upload(artifact, producer, observed["run"], token,
            destination=archive, limit=_RUNTIME_LIMIT,
            artifact_sha256=selected["artifactSha256"], size=selected["artifactBytes"])
    files, _, identity = verified_zip_contents(archive, retained_paths=(),
        max_archive_bytes=_RUNTIME_LIMIT, max_members=512, max_entry_bytes=128 * 1024 * 1024,
        max_total_bytes=_RUNTIME_LIMIT, require_sorted=False)
    required = {target + "/" + Path(path).name for target, path in _LIBRARY_PATHS.items()}
    if (identity != {"bytes": selected["artifactBytes"], "sha256": selected["artifactSha256"]}
            or sha256_bytes(canonical_json_bytes(files)) != selected["inventorySha256"]
            or not required <= {row["relativePath"] for row in files}
            or {row["relativePath"].split("/", 1)[0] for row in files} != set(_LIBRARY_PATHS)):
        raise ValueError("SDK Runtime bytes differ from the approved full five-library upload")
    with tempfile.TemporaryDirectory(prefix="sdk-candidate-runtime-") as temporary:
        prepared = Path(temporary).resolve()
        write_canonical_json(prepared / "library-inventory.json", files)
        write_canonical_json(prepared / "transport.json", {
            "schemaVersion": 1, "producer": producer, "observed": {**observed, "jobs": [job]},
            "artifact": artifact, "trustedWorkflowSha": selected["trustedWorkflowSha"],
            "selectionSha256": sha256_bytes(approved), "heldArchive": held,
        })
        controls = regular_file_inventory(prepared)
        require_no_signing_secret(environment)
        require_no_signing_secret(os.environ)
        if (_SECRETS & (set(environment) | set(os.environ))
                or canonical_json_bytes(selected) != approved
                or sha256_file(archive, reject_symlink_parents=True) != selected["artifactSha256"]):
            raise ValueError("SDK Runtime capture inputs changed during observation")
        publish_regular_tree(prepared, destination, expected_inventory=controls)
    return {"admitted": False, "artifactId": selected["artifactId"],
            "artifactSha256": selected["artifactSha256"], "heldArchive": held,
            "libraryInventorySha256": selected["inventorySha256"],
            "capturedControlBytes": sum(row["bytes"] for row in controls),
            "captureInventorySha256": sha256_bytes(canonical_json_bytes(controls)),
            "elapsedNs": time.monotonic_ns() - started}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--expected-selection-sha256", required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--kind", choices=("catalog", "parity", "runtime"), default="catalog")
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args(argv)
    if (args.kind != "catalog") != (args.archive is not None):
        parser.error("--archive is required for parity or Runtime capture, not catalog capture")
    raw = read_regular_file_bytes(args.selection, max_bytes=64 * 1024,
                                  reject_symlink_parents=True)
    if sha256_bytes(raw) != require_sha256(
            args.expected_selection_sha256, "SDK candidate catalog selection"):
        raise ValueError("SDK catalog selection differs from protected S1048 digest")
    selected = load_canonical_json_bytes(raw)
    if args.kind == "catalog":
        result = capture_sdk_candidate_catalog(selected, args.destination, token=os.environ["GITHUB_TOKEN"])
    else:
        capture = capture_sdk_candidate_parity if args.kind == "parity" else capture_sdk_candidate_runtime
        result = capture(selected, args.archive, args.destination, token=os.environ["GITHUB_TOKEN"])
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
