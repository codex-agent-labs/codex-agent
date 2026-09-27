"""Admit an earlier protected Contract output and signed record without rebuilding.

The caller owns the original producer, both official upload IDs/digests, and
reviewed workflow/key pins. Nothing inside either downloaded upload is an
authority for locating the other upload.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
import os
import tempfile

from ci import product_reuse as products
from ci.contract_phase10_output_record import verify_signed_contract_phase10_output_record
from ci.products.inventory import (
    publish_regular_tree, read_regular_file_bytes,
    regular_file_inventory, require_integer, require_sha256, sha256_file,
    snapshot_regular_tree, verified_zip_contents, write_canonical_json,
)
from ci.products.signing_isolation import require_no_signing_secret
from ci.receipt import safe_extract


def capture_reusable_contract_phase10_output(
    plan_path: Path, validation_repository: Path, trusted_repository: Path,
    destination: Path, *, original_producer: Mapping,
    trusted_source_commit: str, trusted_workflow_sha: str,
    trusted_workflow_path: str, output_job_name: str, record_job_name: str,
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
        jobs = {"output": output_job_name, "record": record_job_name}
        observations = products._observe_ci_producer_jobs(
            {phase: producer for phase in jobs}, jobs_by_phase=jobs, token=token,
            trusted_workflows_by_phase={phase: {"path": trusted_workflow_path,
                                                "sha": trusted_workflow_sha} for phase in jobs},
        )
        if len(observations) != 1:
            raise ValueError("Contract reuse requires one original CI attempt")
        observation = observations[0]
        tree, attempt = producer["tree"], producer["runAttempt"]
        names = {
            "output": f"codex-agent-contract-phase10-maven-{tree}-attempt-{attempt}",
            "record": f"codex-agent-contract-phase10-output-record-{tree}-attempt-{attempt}",
        }
        uploads = {}
        for phase, artifact_id, artifact_digest in (
            ("output", output_artifact_id, output_artifact_sha256),
            ("record", record_artifact_id, record_artifact_sha256),
        ):
            archive = root / f"{phase}.zip"
            artifact, _ = products._download_contract_ci_upload(
                artifact_id, artifact_digest, names[phase], producer,
                observation["run"], token, destination=archive,
            )
            products._require_artifact_job_window(observation, jobs[phase], artifact)
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
            token=token, environ=original_environment,
        )
        if record["officialUpload"]["producer"] != producer:
            raise ValueError("Contract signed record differs from caller-pinned original producer")
        captured = root / "captured"
        snapshot_regular_tree(root / "output", captured / "output")
        snapshot_regular_tree(root / "record", captured / "signed-record")
        write_canonical_json(captured / "transport.json", {
            "schemaVersion": 1, "producer": producer,
            "observedAttempt": observation,
            "officialUploads": uploads,
        })
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
    return {"record": record, "producer": producer, "files": inventory}
