"""Admit exact Contract candidate bytes from independently pinned Phase-10 originals.

This is a token-only, build-free reader. The protected caller, not an upload or
this module, supplies the S1048 selection and its digest. Candidate workflow
authorization and publication remain separate.
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
from ci.contract_phase10_reuse_admission import capture_reusable_contract_phase10_output
from ci.contract_phase11_bytes import forward_verified_contract_phase10_bytes
from ci.products.index import SignedProductIndex, verify_release_product_index
from ci.products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, read_regular_file_bytes,
    regular_file_inventory, require_exact_keys, require_integer, require_sha256,
    sha256_bytes, sha256_file, verified_zip_contents,
)
from ci.products.receipt import validate_producer
from ci.products.signing_isolation import require_no_signing_secret
from ci.receipt import safe_extract


_REPOSITORY = "codex-agent-labs/codex-agent"
_CATALOG_WORKFLOW = ".github/workflows/contract-promoted-catalog.yml"
_CATALOG_JOB = "contract-promoted-catalog / contract-promoted-catalog"
_PLAN_WORKFLOW = ".github/workflows/product-validation.yml"
_PLAN_JOB = "product-validation / plan"
_OUTPUT_WORKFLOW = ".github/workflows/contract-phase10-output-record.yml"
_OUTPUT_JOB = "product-validation / contract-phase10-output-record / contract-phase10-output"
_RECORD_JOB = "contract-phase10-record / contract-phase10-record"
_PHASES = ("binary", "package", "validation", "metadata")
_PHASE11_PINS = {
    "expected_inventory_sha256", "expected_contract_version",
    "expected_payload_sha256", "expected_metadata_build_key",
    "expected_source_commit", "expected_source_tree", "expected_validation_tree",
    "expected_workflow_sha", "expected_caller_sha256", "expected_keyring_sha256",
    "expected_keys_inventory_sha256", "expected_pgp_key_sha256",
}


def _selection(value: dict) -> tuple[dict, dict]:
    selected = require_exact_keys(value, {"schemaVersion", "catalog", "phase10"},
                                  "Contract candidate selection")
    if type(selected["schemaVersion"]) is not int or selected["schemaVersion"] != 1:
        raise ValueError("Unsupported Contract candidate selection schema")
    catalog = require_exact_keys(selected["catalog"], {
        "producer", "trustedWorkflowSha", "jobName", "artifactId",
        "artifactSha256", "indexSha256", "inventorySha256",
    }, "Contract promoted catalog selection")
    phase10 = require_exact_keys(selected["phase10"], {
        "originalProducer", "recordProducer", "trustedSourceCommit",
        "trustedWorkflowSha", "trustedRecordWorkflowSha", "expectedPgpKeySha256",
        "planWorkflowSha", "planArtifactId", "planArtifactSha256",
        "outputArtifactId", "outputArtifactSha256", "recordArtifactId",
        "recordArtifactSha256", "recordSha256", "signatureSha256", "phase11Pins",
    }, "Contract Phase-10 selection")
    catalog_producer = validate_producer(catalog["producer"])
    if (catalog_producer["repository"] != _REPOSITORY
            or catalog_producer["workflowPath"] != ".github/workflows/promote.yml"
            or catalog_producer["event"] != "push"):
        raise ValueError("Contract catalog must come from a promoted-main push")
    original = validate_producer(phase10["originalProducer"])
    record = validate_producer(phase10["recordProducer"])
    if (original["repository"] != _REPOSITORY
            or original["workflowPath"] != ".github/workflows/ci.yml"
            or original["event"] not in {"pull_request", "merge_group"}
            or record["repository"] != _REPOSITORY
            or record["workflowPath"] != ".github/workflows/ci.yml"
            or record["event"] != "workflow_dispatch"
            or original["runId"] == record["runId"]):
        raise ValueError("Contract Phase-10 originals have an unsupported producer route")
    pins = require_exact_keys(phase10["phase11Pins"], _PHASE11_PINS,
                              "Contract candidate Phase-11 pins")
    if (pins["expected_source_commit"] != phase10["trustedSourceCommit"]
            or pins["expected_workflow_sha"] != phase10["trustedWorkflowSha"]
            or pins["expected_pgp_key_sha256"] != phase10["expectedPgpKeySha256"]
            or pins["expected_validation_tree"] != catalog_producer["tree"]
            or pins["expected_validation_tree"] != original["tree"]):
        raise ValueError("Contract candidate selection has inconsistent source or tree")
    for name in ("trustedWorkflowSha", "jobName"):
        if type(catalog[name]) is not str or not catalog[name]:
            raise ValueError(f"Contract catalog {name} is missing")
    if catalog["jobName"] != _CATALOG_JOB:
        raise ValueError("Contract catalog job differs from the fixed promotion route")
    for name in ("trustedWorkflowSha", "trustedRecordWorkflowSha", "trustedSourceCommit",
                 "planWorkflowSha"):
        if type(phase10[name]) is not str or re.fullmatch(r"[0-9a-f]{40}", phase10[name]) is None:
            raise ValueError(f"Contract Phase-10 {name} must be an exact Git commit")
    if re.fullmatch(r"[0-9a-f]{40}", catalog["trustedWorkflowSha"]) is None:
        raise ValueError("Contract catalog child workflow must be exactly pinned")
    for group in (catalog, phase10):
        for name in ("artifactId",) if group is catalog else (
                "planArtifactId", "outputArtifactId", "recordArtifactId"):
            require_integer(group[name], f"Contract {name}", 1)
    if len({catalog["artifactId"], phase10["planArtifactId"],
            phase10["outputArtifactId"], phase10["recordArtifactId"]}) != 4:
        raise ValueError("Contract catalog, plan, output and record must be distinct uploads")
    for name in ("artifactSha256", "indexSha256", "inventorySha256"):
        require_sha256(catalog[name], f"Contract catalog {name}")
    for name in ("planArtifactSha256", "outputArtifactSha256", "recordArtifactSha256", "recordSha256",
                 "signatureSha256", "expectedPgpKeySha256"):
        require_sha256(phase10[name], f"Contract Phase-10 {name}")
    return catalog, phase10


def _observe_catalog(producer: dict, workflow_sha: str, job_name: str, token: str) -> dict:
    """Observe the fixed protected-main promotion route independently of ZIP claims."""
    base = f"https://api.github.com/repos/{_REPOSITORY}"
    attempt = f"{base}/actions/runs/{producer['runId']}/attempts/{producer['runAttempt']}"
    run = transport.api_json(attempt, token)
    if (type(run) is not dict
            or require_integer(run.get("id"), "Contract promotion run", 1) != producer["runId"]
            or require_integer(run.get("run_attempt"), "Contract promotion attempt", 1)
                != producer["runAttempt"]
            or run.get("path") != producer["workflowPath"]
            or run.get("event") != "push" or run.get("head_branch") != "main"
            or run.get("head_sha") != producer["commit"]
            or run.get("status") != "completed" or run.get("conclusion") != "success"
            or any(type(run.get(field)) is not dict
                   or run[field].get("full_name") != _REPOSITORY
                   or run[field].get("fork") is not False
                   for field in ("repository", "head_repository"))):
        raise ValueError("Contract promoted catalog lacks successful official main run")
    transport._require_ci_workflow_reference(
        run, f"{_REPOSITORY}/{_CATALOG_WORKFLOW}@{workflow_sha}", workflow_sha,
    )
    commit = transport.api_json(f"{base}/git/commits/{producer['commit']}", token)
    if (type(commit) is not dict or commit.get("sha") != producer["commit"]
            or type(commit.get("tree")) is not dict
            or commit["tree"].get("sha") != producer["tree"]):
        raise ValueError("Contract promoted catalog run has a different Git tree")
    jobs = transport.paginated_items(f"{attempt}/jobs", "jobs", token)
    if any(type(job) is not dict for job in jobs):
        raise ValueError("Contract promotion jobs are malformed")
    matches = [job for job in jobs if job.get("name") == job_name]
    if len(matches) != 1 or (
            require_integer(matches[0].get("run_id"), "Contract catalog job run", 1)
            != producer["runId"] or matches[0].get("head_sha") != producer["commit"]
            or matches[0].get("status") != "completed"
            or matches[0].get("conclusion") != "success"):
        raise ValueError("Contract promoted catalog job is missing, ambiguous, or unsuccessful")
    require_integer(matches[0].get("id"), "Contract catalog job ID", 1)
    return {"run": run, "testedCommit": commit, "jobs": jobs}


def admit_contract_candidate(selection: dict, trusted_repository: Path,
                             validation_repository: Path, landed_repository: Path,
                             destination: Path, *, token: str,
                             environ=None) -> dict:
    """Reobserve both transports, join identities, and forward only Phase-10 bytes."""
    environment = os.environ if environ is None else environ
    require_no_signing_secret(environment)
    require_no_signing_secret(os.environ)
    if type(token) is not str or not token:
        raise ValueError("Contract candidate requires an observation token")
    catalog, phase10 = _selection(selection)
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Contract candidate destination already exists")
    for path in (trusted_repository, validation_repository, landed_repository):
        source = Path(path).resolve(strict=True)
        output = destination.resolve(strict=False)
        if output == source or output in source.parents or source in output.parents:
            raise ValueError("Contract candidate destination overlaps an authority input")
    observed = _observe_catalog(catalog["producer"], catalog["trustedWorkflowSha"],
                                catalog["jobName"], token)
    name = ("codex-agent-promoted-contract-catalog-"
            f"{catalog['producer']['commit']}-{catalog['producer']['runId']}-"
            f"{catalog['producer']['runAttempt']}")
    with tempfile.TemporaryDirectory(prefix="contract-candidate-admit-") as temporary:
        root = Path(temporary).resolve()
        archive = root / "catalog.zip"
        artifact, _ = transport._download_contract_ci_upload(
            catalog["artifactId"], catalog["artifactSha256"], name,
            catalog["producer"], observed["run"], token, destination=archive,
        )
        transport._require_artifact_job_window(observed, catalog["jobName"], artifact)
        listing, _, _ = verified_zip_contents(
            archive, retained_paths=(), allow_empty_members=True,
            **transport._CATALOG_ZIP_LIMITS,
        )
        extracted = root / "catalog"
        safe_extract(archive, extracted)
        catalog_files = regular_file_inventory(extracted)
        if (catalog_files != listing or sha256_file(archive) != catalog["artifactSha256"]
                or sha256_bytes(canonical_json_bytes(catalog_files)) != catalog["inventorySha256"]
                or sha256_file(extracted / "product-index.json") != catalog["indexSha256"]):
            raise ValueError("Contract promoted catalog differs from independent S1048 pins")
        trust = transport._release_trust(
            Path(trusted_repository), phase10["trustedSourceCommit"], root / "policy",
        )
        if trust is None:
            raise ValueError("Contract candidate has no source-pinned release trust")
        landed_trust = transport._release_trust(
            Path(landed_repository), "HEAD", root / "landed-policy",
        )
        if (landed_trust is None or
                regular_file_inventory(trust.keyring.parent) !=
                regular_file_inventory(landed_trust.keyring.parent)):
            raise ValueError("Contract candidate landed keyring differs from Phase-10 trust")
        index, _ = verify_release_product_index(
            SignedProductIndex(extracted / "product-index.json", extracted / "product-index.sig"),
            keyring_path=trust.keyring, keys_directory=trust.keys,
        )
        if (index["producer"] != catalog["producer"] or
                index["context"]["kind"] != "promoted-main" or
                index["trustDomain"] != "release" or
                len(index["entries"]) != len(_PHASES) or
                {(entry["product"], entry["component"], entry["phase"], entry["target"])
                 for entry in index["entries"]} !=
                {("contract", "contract", phase, "common") for phase in _PHASES}):
            raise ValueError("Contract catalog lacks exactly four promoted original phases")
        transport.stage_release_catalog(
            extracted, root / "verified-catalog", repository=_REPOSITORY,
            source="promoted-main", keyring=trust.keyring, keys_directory=trust.keys,
        )
        original = phase10["originalProducer"]
        plan_observation = transport._observe_ci_producer_jobs(
            {"plan": original}, jobs_by_phase={"plan": _PLAN_JOB}, token=token,
            trusted_workflows_by_phase={"plan": {
                "path": _PLAN_WORKFLOW, "sha": phase10["planWorkflowSha"],
            }},
        )[0]
        plan_archive = root / "plan.zip"
        plan_artifact, _ = transport._download_contract_ci_upload(
            phase10["planArtifactId"], phase10["planArtifactSha256"],
            f"codex-agent-ci-plan-{original['tree']}", original,
            plan_observation["run"], token, destination=plan_archive,
        )
        transport._require_artifact_job_window(plan_observation, _PLAN_JOB, plan_artifact)
        if sha256_file(plan_archive) != phase10["planArtifactSha256"]:
            raise ValueError("Contract original plan differs from independent S1048 pin")
        _, plan_files, _ = verified_zip_contents(
            plan_archive, retained_paths=("impact-plan.json",),
            max_retained_bytes=16 * 1024 * 1024, allow_empty_members=True,
            **transport._CATALOG_ZIP_LIMITS,
        )
        if not plan_files.get("impact-plan.json"):
            raise ValueError("Contract original plan upload lacks impact-plan.json")
        plan_path = root / "impact-plan.json"
        plan_path.write_bytes(plan_files["impact-plan.json"])
        captured = root / "phase10"
        record_producer = phase10["recordProducer"]
        result = capture_reusable_contract_phase10_output(
            plan_path, validation_repository, trusted_repository, captured,
            original_producer=original, record_producer=record_producer,
            trusted_source_commit=phase10["trustedSourceCommit"],
            trusted_workflow_sha=phase10["trustedWorkflowSha"],
            trusted_workflow_path=_OUTPUT_WORKFLOW, output_job_name=_OUTPUT_JOB,
            record_job_name=_RECORD_JOB,
            trusted_record_workflow_sha=phase10["trustedRecordWorkflowSha"],
            expected_pgp_key_sha256=phase10["expectedPgpKeySha256"],
            output_artifact_id=phase10["outputArtifactId"],
            output_artifact_sha256=phase10["outputArtifactSha256"],
            record_artifact_id=phase10["recordArtifactId"],
            record_artifact_sha256=phase10["recordArtifactSha256"],
            token=token, environ=environment,
        )
        pins = phase10["phase11Pins"]
        record = result["record"]
        metadata = next(entry for entry in index["entries"] if entry["phase"] == "metadata")
        handoff = captured / "output/contract-release-evidence/contract-input"
        attestation = f"codex-agent-contract-{pins['expected_contract_version']}.attestation"
        if (regular_file_inventory(extracted / "execution-closure") !=
                regular_file_inventory(handoff / "execution-closure") or any(
                    read_regular_file_bytes(extracted / f"{attestation}.{suffix}",
                                            max_bytes=16 * 1024 * 1024,
                                            reject_symlink_parents=True) !=
                    read_regular_file_bytes(handoff / f"{attestation}.{suffix}",
                                            max_bytes=16 * 1024 * 1024,
                                            reject_symlink_parents=True)
                    for suffix in ("json", "sig"))):
            raise ValueError("Contract catalog and Phase-10 output have different original closure")
        if (record["phase11Pins"] != pins or
                record["officialUpload"]["producer"] != original or
                sha256_file(captured / "signed-record/record.json") != phase10["recordSha256"] or
                sha256_file(captured / "signed-record/record.sig") != phase10["signatureSha256"] or
                metadata["productVersion"] != pins["expected_contract_version"] or
                metadata["buildKey"] != pins["expected_metadata_build_key"] or
                metadata["artifactSha256"] != pins["expected_payload_sha256"] or
                metadata["receiptSha256"] != sha256_file(
                    handoff / "execution-closure/receipts/metadata.json") or
                any(entry["productVersion"] != metadata["productVersion"] for entry in index["entries"]) or
                index["context"]["tree"] != pins["expected_validation_tree"]):
            raise ValueError("Contract catalog and signed Phase-10 record disagree")
        if (regular_file_inventory(extracted) != catalog_files
                or sha256_file(archive) != catalog["artifactSha256"]
                or sha256_file(plan_archive) != phase10["planArtifactSha256"]
                or sha256_file(captured / "signed-record/record.json") != phase10["recordSha256"]
                or sha256_file(captured / "signed-record/record.sig") != phase10["signatureSha256"]):
            raise ValueError("Contract candidate originals changed during admission")
        require_no_signing_secret(environment)
        candidate = forward_verified_contract_phase10_bytes(
            captured / "output", destination, landed_repository=landed_repository, **pins,
        )
        return {"catalogIndexSha256": catalog["indexSha256"],
                "signedRecordSha256": phase10["recordSha256"], "candidate": candidate}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("selection", "trusted-repository", "validation-repository",
                 "landed-repository", "destination"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--expected-selection-sha256", required=True)
    args = parser.parse_args(argv)
    selected = read_regular_file_bytes(args.selection, max_bytes=64 * 1024,
                                       reject_symlink_parents=True)
    if sha256_bytes(selected) != require_sha256(
            args.expected_selection_sha256, "independent Contract candidate selection"):
        raise ValueError("Contract candidate selection differs from protected S1048 digest")
    result = admit_contract_candidate(
        load_canonical_json_bytes(selected), args.trusted_repository,
        args.validation_repository, args.landed_repository, args.destination,
        token=os.environ["GITHUB_TOKEN"],
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
