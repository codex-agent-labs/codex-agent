"""Observe the protected Contract sidecar upload without granting release trust.

The reviewed caller supplies the exact workflow route and local Phase-10 output.
This locator checks the official run, job window, transport bytes, and extracted
inventory; a separate S1048 attestation must still pin these observations.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import os
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from ci import product_reuse as products
from ci.receipt import safe_extract
from ci.products.inventory import (
    canonical_json_bytes, read_regular_file_bytes, regular_file_inventory,
    require_integer, require_sha256, sha256_bytes, verified_zip_contents,
)
from ci.products.signing_isolation import require_no_signing_secret
from ci.reuse import github_output


def observe_contract_phase10_upload(plan_path: Path, repository_root: Path,
        protected_output: Path, *, trusted_workflow_sha: str,
        trusted_workflow_path: str, trusted_job_name: str,
        artifact_id: int, artifact_sha256: str, environ=None, token: str,
        original_run_id=None, original_run_attempt=None) -> dict:
    """Bind one official upload to the exact already-finalized Phase-10 files."""
    environment = os.environ if environ is None else environ
    require_no_signing_secret(environment)
    require_no_signing_secret(os.environ)
    if (not trusted_workflow_path or not trusted_job_name
            or type(token) is not str or not token):
        raise ValueError("Contract Phase-10 observation requires a reviewed route and token")
    artifact_id = require_integer(artifact_id, "Contract Phase-10 artifact ID", 1)
    artifact_sha256 = require_sha256(artifact_sha256, "Contract Phase-10 artifact digest")
    root = Path(repository_root).resolve(strict=True)
    output = Path(protected_output).resolve(strict=True)
    if not output.is_dir() or output == root or output in root.parents:
        raise ValueError("Contract Phase-10 output must be a distinct directory")
    before = regular_file_inventory(output)
    plan_bytes = read_regular_file_bytes(Path(plan_path), max_bytes=16 * 1024 * 1024,
                                         reject_symlink_parents=True)
    with tempfile.TemporaryDirectory(prefix="contract-phase10-upload-") as temporary:
        private = Path(temporary).resolve()
        captured_plan = private / "impact-plan.json"
        captured_plan.write_bytes(plan_bytes)
        plan = products._validate_plan(captured_plan, root)
        if plan["remoteBuildAuthorized"] is not True or plan["event"] not in {"pull_request", "merge_group"}:
            raise ValueError("Contract Phase-10 upload requires an authorized plan")
        producer = products.validate_producer(products._consumer(
            plan, environment, original_run_id=original_run_id,
            original_run_attempt=original_run_attempt,
        )["producer"])
        name = (f"codex-agent-contract-phase10-maven-{producer['tree']}-"
                f"attempt-{producer['runAttempt']}")
        observed = products._observe_ci_producer_jobs(
            {"sidecars": producer}, jobs_by_phase={"sidecars": trusted_job_name},
            token=token, trusted_workflows_by_phase={"sidecars": {
                "path": trusted_workflow_path, "sha": trusted_workflow_sha,
            }})[0]
        run = observed["run"]
        archive = private / "official-upload.zip"
        artifact, _ = products._download_contract_ci_upload(
            artifact_id, artifact_sha256, name, producer, run, token,
            destination=archive)
        products._require_artifact_job_window(observed, trusted_job_name, artifact)
        inventory, _, _ = verified_zip_contents(
            archive, retained_paths=(), allow_empty_members=True,
            **products._CATALOG_ZIP_LIMITS)
        extracted = private / "extracted"
        safe_extract(archive, extracted)
        if inventory != before or regular_file_inventory(extracted) != before:
            raise ValueError("Contract Phase-10 upload differs from finalized output")
        if (regular_file_inventory(output) != before
                or read_regular_file_bytes(Path(plan_path), max_bytes=16 * 1024 * 1024,
                                           reject_symlink_parents=True) != plan_bytes):
            raise ValueError("Contract Phase-10 output or plan changed during observation")
        require_no_signing_secret(environment)
    return {"artifactId": artifact_id, "artifactSha256": artifact_sha256,
            "artifactName": name, "inventorySha256": sha256_bytes(canonical_json_bytes(before)),
            "producer": producer, "trustedWorkflowPath": trusted_workflow_path,
            "trustedWorkflowSha": trusted_workflow_sha, "trustedJobName": trusted_job_name}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("plan", "repository-root", "protected-output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    for name in ("trusted-workflow-sha", "trusted-workflow-path", "trusted-job-name",
                 "artifact-id", "artifact-sha256"):
        parser.add_argument(f"--{name}", required=True)
    parser.add_argument("--github-output", type=Path)
    parser.add_argument("--original-run-id", type=int)
    parser.add_argument("--original-run-attempt", type=int)
    args = parser.parse_args(argv)
    try:
        result = observe_contract_phase10_upload(
            args.plan, args.repository_root, args.protected_output,
            trusted_workflow_sha=args.trusted_workflow_sha,
            trusted_workflow_path=args.trusted_workflow_path,
            trusted_job_name=args.trusted_job_name,
            artifact_id=int(args.artifact_id), artifact_sha256=args.artifact_sha256,
            environ=os.environ, token=os.environ["GITHUB_TOKEN"],
            original_run_id=args.original_run_id,
            original_run_attempt=args.original_run_attempt)
        if args.github_output is not None:
            github_output(args.github_output, {key: result[key] for key in (
                "artifactId", "artifactSha256", "artifactName", "inventorySha256")})
        print(canonical_json_bytes(result).decode().strip())
    except (OSError, ValueError, KeyError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
