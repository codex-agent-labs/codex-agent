"""Admit an earlier protected Contract output and signed record without rebuilding.

The caller owns the original producer, both official upload IDs/digests, and
reviewed workflow/key pins. Nothing inside either downloaded upload is an
authority for locating the other upload.
"""

from __future__ import annotations

from collections.abc import Mapping
import argparse
import json
from pathlib import Path
import os
import re
import tempfile

from ci import product_reuse as products
from ci.contract_phase10_output_record import verify_signed_contract_phase10_output_record
from ci.products.inventory import (
    load_canonical_json_bytes, publish_regular_tree, read_regular_file_bytes,
    regular_file_inventory, require_integer, require_sha256, sha256_file,
    sha256_bytes, snapshot_regular_tree, verified_zip_contents, write_canonical_json,
)
from ci.products.signing_isolation import require_no_signing_secret
from ci.receipt import safe_extract


_ORIGINAL_OUTPUT_WORKFLOW = ".github/workflows/contract-phase10-output-record.yml"
_DISPATCH_RECORD_WORKFLOW = ".github/workflows/contract-phase10-later-record.yml"
_DISPATCH_RECORD_JOB = "contract-phase10-record / contract-phase10-record"


def _observe_protected_record_dispatch(producer, *, workflow_sha, token):
    """Authenticate the fixed record-only dispatch route, not a product build."""
    if (producer["repository"] != "codex-agent-labs/codex-agent"
            or producer["workflowPath"] != ".github/workflows/ci.yml"
            or producer["event"] != "workflow_dispatch"
            or producer["pullRequest"] is not None
            or type(workflow_sha) is not str
            or re.fullmatch(r"[0-9a-f]{40}", workflow_sha) is None):
        raise ValueError("Contract record dispatch differs from its fixed protected route")
    api = f"https://api.github.com/repos/{producer['repository']}"
    attempt = f"{api}/actions/runs/{producer['runId']}/attempts/{producer['runAttempt']}"
    run = products.api_json(attempt, token)
    if (type(run) is not dict
            or require_integer(run.get("id"), "Contract record dispatch run", 1) != producer["runId"]
            or require_integer(run.get("run_attempt"), "Contract record dispatch attempt", 1)
                != producer["runAttempt"]
            or run.get("path") != producer["workflowPath"]
            or run.get("event") != "workflow_dispatch"
            or run.get("status") != "completed"
            or run.get("conclusion") != "success"
            or run.get("head_sha") != producer["commit"]
            or any(type(run.get(field)) is not dict
                   or run[field].get("full_name") != producer["repository"]
                   or run[field].get("fork") is not False
                   for field in ("repository", "head_repository"))):
        raise ValueError("Contract record dispatch differs from pinned official run")
    products._require_ci_workflow_reference(
        run, f"{producer['repository']}/{_DISPATCH_RECORD_WORKFLOW}@{workflow_sha}", workflow_sha,
    )
    commit = products._observe_tested_commit(
        run, api="https://api.github.com", repository=producer["repository"], token=token,
        expected_commit=producer["commit"], expected_tree=producer["tree"],
        pull_request=None, allow_dispatch=True,
    )
    jobs = products.paginated_items(f"{attempt}/jobs", "jobs", token)
    if any(type(job) is not dict for job in jobs):
        raise ValueError("Contract record dispatch jobs are malformed")
    selected = [job for job in jobs if job.get("name") == _DISPATCH_RECORD_JOB]
    if len(selected) != 1:
        raise ValueError("Contract record dispatch job is missing or ambiguous")
    job = selected[0]
    require_integer(job.get("id"), "Contract record dispatch job ID", 1)
    if (require_integer(job.get("run_id"), "Contract record dispatch job run", 1)
                != producer["runId"]
            or job.get("head_sha") != run["head_sha"]
            or job.get("status") != "completed" or job.get("conclusion") != "success"):
        raise ValueError("Contract record dispatch job did not succeed")
    return {"run": run, "testedCommit": commit, "jobs": jobs}


def capture_reusable_contract_phase10_output(
    plan_path: Path, validation_repository: Path, trusted_repository: Path,
    destination: Path, *, original_producer: Mapping,
    record_producer: Mapping | None = None,
    trusted_source_commit: str, trusted_workflow_sha: str,
    trusted_workflow_path: str, output_job_name: str, record_job_name: str,
    trusted_record_workflow_sha: str | None = None,
    expected_pgp_key_sha256: str, output_artifact_id: int,
    output_artifact_sha256: str, record_artifact_id: int,
    record_artifact_sha256: str, token: str, environ=None,
) -> dict:
    """Retain exact earlier Phase-10 bytes after independent official admission."""
    environment = os.environ if environ is None else environ
    require_no_signing_secret(environment)
    require_no_signing_secret(os.environ)
    if type(token) is not str or not token:
        raise ValueError("Contract reuse admission requires an observation token")
    output_artifact_id = require_integer(output_artifact_id, "Contract output upload ID", 1)
    record_artifact_id = require_integer(record_artifact_id, "Contract record upload ID", 1)
    if output_artifact_id == record_artifact_id:
        raise ValueError("Contract output and record must be distinct official uploads")
    output_artifact_sha256 = require_sha256(output_artifact_sha256, "Contract output upload digest")
    record_artifact_sha256 = require_sha256(record_artifact_sha256, "Contract record upload digest")
    producer = products.validate_producer(dict(original_producer))
    signed_producer = (producer if record_producer is None else
                       products.validate_producer(dict(record_producer)))
    dispatch_record = record_producer is not None
    if dispatch_record:
        if (trusted_workflow_path != _ORIGINAL_OUTPUT_WORKFLOW
                or record_job_name != _DISPATCH_RECORD_JOB
                or signed_producer["repository"] != producer["repository"]
                or signed_producer["runId"] == producer["runId"]
                or type(trusted_record_workflow_sha) is not str
                or re.fullmatch(r"[0-9a-f]{40}", trusted_record_workflow_sha) is None):
            raise ValueError("Contract record dispatch differs from approved route or original")
    elif trusted_record_workflow_sha is not None:
        raise ValueError("Same-run Contract record cannot claim separate workflow authority")
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Contract reuse destination already exists")
    source_roots = [Path(plan_path).resolve(strict=True), Path(validation_repository).resolve(strict=True),
                    Path(trusted_repository).resolve(strict=True)]
    destination_root = destination.resolve(strict=False)
    if any(destination_root == root or destination_root in root.parents or root in destination_root.parents
           for root in source_roots):
        raise ValueError("Contract reuse destination overlaps an input")
    plan_bytes = read_regular_file_bytes(plan_path, max_bytes=16 * 1024 * 1024,
                                         reject_symlink_parents=True)
    with tempfile.TemporaryDirectory(prefix="contract-phase10-reuse-") as temporary:
        root = Path(temporary).resolve()
        plan_copy = root / "impact-plan.json"
        plan_copy.write_bytes(plan_bytes)
        plan = products._validate_plan(plan_copy, Path(validation_repository))
        if plan["remoteBuildAuthorized"] is not True or plan["event"] not in {"pull_request", "merge_group"}:
            raise ValueError("Contract reuse requires an authorized original plan")
        original_environment = {"GITHUB_RUN_ID": str(producer["runId"]),
                                "GITHUB_RUN_ATTEMPT": str(producer["runAttempt"])}
        if products._consumer(plan, original_environment)["producer"] != producer:
            raise ValueError("Contract reuse producer differs from the validated plan")
        jobs = {"output": output_job_name}
        if not dispatch_record:
            jobs["record"] = record_job_name
        observations = products._observe_ci_producer_jobs(
            {phase: producer for phase in jobs}, jobs_by_phase=jobs, token=token,
            trusted_workflows_by_phase={phase: {"path": trusted_workflow_path,
                                                "sha": trusted_workflow_sha} for phase in jobs},
        )
        if len(observations) != 1:
            raise ValueError("Contract reuse requires one original CI attempt")
        observation = observations[0]
        record_observation = (_observe_protected_record_dispatch(
            signed_producer, workflow_sha=trusted_record_workflow_sha, token=token,
        ) if dispatch_record else observation)
        tree, attempt = producer["tree"], producer["runAttempt"]
        names = {
            "output": f"codex-agent-contract-phase10-maven-{tree}-attempt-{attempt}",
            "record": (f"codex-agent-contract-phase10-output-record-{tree}-attestation-"
                       f"{signed_producer['runId']}-attempt-{signed_producer['runAttempt']}"
                       if dispatch_record else
                       f"codex-agent-contract-phase10-output-record-{tree}-attempt-{attempt}"),
        }
        uploads = {}
        for phase, artifact_id, artifact_digest in (
            ("output", output_artifact_id, output_artifact_sha256),
            ("record", record_artifact_id, record_artifact_sha256),
        ):
            archive = root / f"{phase}.zip"
            selected_producer = producer if phase == "output" else signed_producer
            selected_observation = observation if phase == "output" else record_observation
            selected_job = output_job_name if phase == "output" else record_job_name
            artifact, _ = products._download_contract_ci_upload(
                artifact_id, artifact_digest, names[phase], selected_producer,
                selected_observation["run"], token, destination=archive,
            )
            products._require_artifact_job_window(selected_observation, selected_job, artifact)
            inventory, _, _ = verified_zip_contents(
                archive, retained_paths=(), allow_empty_members=True,
                **products._CATALOG_ZIP_LIMITS,
            )
            extracted = root / phase
            safe_extract(archive, extracted)
            if regular_file_inventory(extracted) != inventory or sha256_file(archive) != artifact_digest:
                raise ValueError(f"Contract {phase} official upload changed during extraction")
            uploads[phase] = artifact
        record_files = regular_file_inventory(root / "record")
        if {item["relativePath"] for item in record_files} != {
                "record.json", "record.sig"}:
            raise ValueError("Contract signed-record upload must contain exactly its signed pair")
        record = verify_signed_contract_phase10_output_record(
            root / "record/record.json", root / "record/record.sig",
            trusted_repository, validation_repository, root / "output", plan_copy,
            trusted_source_commit=trusted_source_commit,
            trusted_workflow_sha=trusted_workflow_sha,
            trusted_workflow_path=trusted_workflow_path,
            trusted_job_name=output_job_name,
            expected_pgp_key_sha256=expected_pgp_key_sha256,
            artifact_id=output_artifact_id, artifact_sha256=output_artifact_sha256,
            token=token, environ=environment,
            original_run_id=producer["runId"],
            original_run_attempt=producer["runAttempt"],
        )
        if record["officialUpload"]["producer"] != producer:
            raise ValueError("Contract signed record differs from caller-pinned original producer")
        captured = root / "captured"
        snapshot_regular_tree(root / "output", captured / "output")
        snapshot_regular_tree(root / "record", captured / "signed-record")
        transport = {"schemaVersion": 1, "producer": producer,
                     "observedAttempt": observation, "officialUploads": uploads}
        if dispatch_record:
            transport["recordProducer"] = signed_producer
            transport["recordObservedAttempt"] = record_observation
        write_canonical_json(captured / "transport.json", transport)
        inventory = regular_file_inventory(captured)
        if (regular_file_inventory(root / "output") != record["outputFiles"]
                or regular_file_inventory(captured / "output") != record["outputFiles"]
                or regular_file_inventory(root / "record") != record_files
                or regular_file_inventory(captured / "signed-record") != record_files
                or read_regular_file_bytes(plan_path, max_bytes=16 * 1024 * 1024,
                                           reject_symlink_parents=True) != plan_bytes
                or sha256_file(root / "output.zip") != output_artifact_sha256
                or sha256_file(root / "record.zip") != record_artifact_sha256):
            raise ValueError("Contract original inputs changed before reuse capture")
        require_no_signing_secret(environment)
        require_no_signing_secret(os.environ)
        publish_regular_tree(captured, destination, expected_inventory=inventory)
    return {"record": record, "producer": producer,
            "recordProducer": signed_producer, "files": inventory}


def main(argv=None) -> int:
    require_no_signing_secret(os.environ)
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("plan", "validation-repository", "trusted-repository", "destination",
                 "original-producer"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--record-producer", type=Path)
    parser.add_argument("--expected-record-producer-sha256")
    parser.add_argument("--trusted-record-workflow-sha")
    for name in ("expected-original-producer-sha256", "trusted-source-commit",
                 "trusted-workflow-sha", "trusted-workflow-path", "output-job-name",
                 "record-job-name", "expected-pgp-key-sha256", "output-artifact-id",
                 "output-artifact-sha256", "record-artifact-id", "record-artifact-sha256"):
        parser.add_argument(f"--{name}", required=True)
    args = parser.parse_args(argv)
    producer_bytes = read_regular_file_bytes(
        args.original_producer, max_bytes=64 * 1024, reject_symlink_parents=True,
    )
    if sha256_bytes(producer_bytes) != require_sha256(
        args.expected_original_producer_sha256, "independent Contract original producer digest",
    ):
        raise ValueError("Contract original producer differs from independent digest")
    if (args.record_producer is None) != (args.expected_record_producer_sha256 is None):
        raise ValueError("Contract record dispatch requires producer and independent digest")
    record_producer = None
    if args.record_producer is not None:
        signed_bytes = read_regular_file_bytes(
            args.record_producer, max_bytes=64 * 1024, reject_symlink_parents=True,
        )
        if sha256_bytes(signed_bytes) != require_sha256(
            args.expected_record_producer_sha256,
            "independent Contract record producer digest",
        ):
            raise ValueError("Contract record producer differs from independent digest")
        record_producer = load_canonical_json_bytes(signed_bytes)
    result = capture_reusable_contract_phase10_output(
        args.plan, args.validation_repository, args.trusted_repository,
        args.destination, original_producer=load_canonical_json_bytes(producer_bytes),
        record_producer=record_producer,
        trusted_source_commit=args.trusted_source_commit,
        trusted_workflow_sha=args.trusted_workflow_sha,
        trusted_workflow_path=args.trusted_workflow_path,
        trusted_record_workflow_sha=args.trusted_record_workflow_sha,
        output_job_name=args.output_job_name, record_job_name=args.record_job_name,
        expected_pgp_key_sha256=args.expected_pgp_key_sha256,
        output_artifact_id=int(args.output_artifact_id),
        output_artifact_sha256=args.output_artifact_sha256,
        record_artifact_id=int(args.record_artifact_id),
        record_artifact_sha256=args.record_artifact_sha256,
        token=os.environ["GITHUB_TOKEN"], environ=os.environ,
    )
    print(json.dumps({"destination": str(args.destination), "files": result["files"]},
                     sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
