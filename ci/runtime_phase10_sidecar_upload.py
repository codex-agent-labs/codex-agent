"""Capture an independently pinned official Runtime Phase-10 Maven upload.

This is transport evidence, not product admission. The caller supplies the
original plan/run and upload identity from protected authority, not from the
downloaded archive or this module's observation.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse as products
from receipt import safe_extract
from products.inventory import (
    canonical_json_bytes, publish_regular_tree, read_regular_file_bytes,
    regular_file_inventory, require_integer, require_sha256, sha256_bytes,
    sha256_file, verified_zip_contents, write_canonical_json,
)
from products.signing_isolation import require_no_signing_secret


_WORKFLOW = ".github/workflows/runtime-phase10-maven.yml"
_JOB = "product-validation / runtime-phase10-maven / runtime-phase10-maven-sidecars"
_PGP_SECRETS = frozenset({"SIGNING_IN_MEMORY_KEY", "SIGNING_IN_MEMORY_KEY_PASSWORD"})


def capture_runtime_phase10_maven_sidecar_upload(
    plan_path: Path, repository_root: Path, destination: Path, *,
    plan_artifact_id: int, plan_artifact_sha256: str,
    original_run_id: int, original_run_attempt: int,
    trusted_workflow_sha: str, artifact_id: int, artifact_sha256: str,
    token: str, environ=None,
) -> dict:
    """Retain exact official ZIP/extraction and separate observation provenance."""
    environment = os.environ if environ is None else environ
    require_no_signing_secret(environment)
    if _PGP_SECRETS & (set(environment) | set(os.environ)):
        raise ValueError("Runtime sidecar observation must not receive a PGP signing secret")
    if type(token) is not str or not token:
        raise ValueError("Runtime sidecar observation requires a token")
    plan_artifact_id = require_integer(plan_artifact_id, "Original Runtime plan upload ID", 1)
    plan_artifact_sha256 = require_sha256(plan_artifact_sha256, "Original Runtime plan upload digest")
    original_run_id = require_integer(original_run_id, "Original Runtime run ID", 1)
    original_run_attempt = require_integer(original_run_attempt, "Original Runtime run attempt", 1)
    artifact_id = require_integer(artifact_id, "Runtime Maven upload ID", 1)
    artifact_sha256 = require_sha256(artifact_sha256, "Runtime Maven upload digest")
    root = Path(repository_root).resolve(strict=True)
    plan_path = Path(plan_path)
    destination = Path(destination)
    output = destination.resolve(strict=False)
    if (destination.exists() or destination.is_symlink() or output == root
            or output in root.parents or root in output.parents):
        raise ValueError("Runtime Maven capture destination must be separate and absent")
    plan_bytes = read_regular_file_bytes(plan_path, max_bytes=16 * 1024 * 1024,
                                         reject_symlink_parents=True)
    with tempfile.TemporaryDirectory(prefix="runtime-phase10-maven-upload-") as temporary:
        private = Path(temporary).resolve()
        prepared = private / "capture"
        captured_plan = prepared / "plan/impact-plan.json"
        captured_plan.parent.mkdir(parents=True)
        captured_plan.write_bytes(plan_bytes)
        plan = products._validate_plan(captured_plan, root)
        if plan["remoteBuildAuthorized"] is not True or plan["event"] not in {"pull_request", "merge_group"}:
            raise ValueError("Runtime Maven capture requires an authorized original plan")
        producer = products.validate_producer(products._consumer(plan, {
            "GITHUB_RUN_ID": str(original_run_id),
            "GITHUB_RUN_ATTEMPT": str(original_run_attempt),
        })["producer"])
        observed = products._observe_ci_producer_jobs(
            {"sidecars": producer}, jobs_by_phase={"sidecars": _JOB}, token=token,
            trusted_workflows_by_phase={"sidecars": {
                "path": _WORKFLOW, "sha": trusted_workflow_sha,
            }},
        )[0]
        plan_archive = private / "official-plan.zip"
        products._download_contract_ci_upload(
            plan_artifact_id, plan_artifact_sha256,
            f"codex-agent-ci-plan-{producer['tree']}", producer, observed["run"], token,
            destination=plan_archive,
        )
        plan_inventory, _, _ = verified_zip_contents(
            plan_archive, retained_paths=(), allow_empty_members=True,
            **products._CATALOG_ZIP_LIMITS,
        )
        plan_extracted = private / "official-plan"
        safe_extract(plan_archive, plan_extracted)
        if (regular_file_inventory(plan_extracted) != plan_inventory
                or read_regular_file_bytes(plan_extracted / "impact-plan.json",
                max_bytes=16 * 1024 * 1024, reject_symlink_parents=True) != plan_bytes):
            raise ValueError("Original Runtime plan differs from pinned official upload")
        name = (f"codex-agent-runtime-phase10-maven-{producer['tree']}"
                f"-attempt-{producer['runAttempt']}")
        api = f"https://api.github.com/repos/{producer['repository']}/actions"
        listed = [item for item in products.paginated_items(
            f"{api}/runs/{original_run_id}/artifacts", "artifacts", token,
        ) if type(item) is dict and item.get("id") == artifact_id]
        if len(listed) != 1:
            raise ValueError("Runtime Maven upload is missing or ambiguous in the official listing")
        archive = prepared / "transport.zip"
        artifact, _ = products._download_contract_ci_upload(
            artifact_id, artifact_sha256, name, producer, observed["run"], token,
            destination=archive,
        )
        if any(artifact.get(field) != listed[0].get(field) for field in (
                "id", "name", "digest", "size_in_bytes", "expired", "workflow_run", "created_at")):
            raise ValueError("Runtime Maven upload detail differs from its official listing")
        products._require_artifact_job_window(observed, _JOB, artifact)
        zipped, _, _ = verified_zip_contents(
            archive, retained_paths=(), allow_empty_members=True,
            **products._CATALOG_ZIP_LIMITS,
        )
        original = prepared / "original"
        safe_extract(archive, original)
        if regular_file_inventory(original) != zipped:
            raise ValueError("Runtime Maven extracted sidecars differ from their exact archive")
        transport = {"artifact": artifact, "producer": producer, "observation": observed,
                     "trustedWorkflowPath": _WORKFLOW, "trustedWorkflowSha": trusted_workflow_sha,
                     "trustedJobName": _JOB, "planArtifactId": plan_artifact_id,
                     "planArtifactSha256": plan_artifact_sha256,
                     "planSha256": sha256_bytes(plan_bytes),
                     "sidecarFiles": zipped}
        write_canonical_json(prepared / "capture-transport.json", transport)
        transport_bytes = canonical_json_bytes(transport)
        expected_files = sorted([
            {"relativePath": "plan/impact-plan.json", "bytes": len(plan_bytes),
             "sha256": sha256_bytes(plan_bytes)},
            {"relativePath": "transport.zip", "bytes": archive.stat().st_size,
             "sha256": artifact_sha256},
            {"relativePath": "capture-transport.json", "bytes": len(transport_bytes),
             "sha256": sha256_bytes(transport_bytes)},
            *({**item, "relativePath": f"original/{item['relativePath']}"} for item in zipped),
        ], key=lambda item: item["relativePath"])
        if (read_regular_file_bytes(plan_path, max_bytes=16 * 1024 * 1024,
                                    reject_symlink_parents=True) != plan_bytes
                or sha256_file(plan_archive) != plan_artifact_sha256
                or sha256_file(archive) != artifact_sha256
                or regular_file_inventory(original) != zipped
                or regular_file_inventory(prepared) != expected_files):
            raise ValueError("Runtime Maven original upload changed before retention")
        require_no_signing_secret(environment)
        if destination.exists() or destination.is_symlink():
            raise ValueError("Runtime Maven capture destination already exists")
        publish_regular_tree(prepared, destination, expected_inventory=expected_files)
    return transport


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("plan", "repository-root", "destination"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    for name in ("plan-artifact-id", "plan-artifact-sha256",
                 "original-run-id", "original-run-attempt",
                 "trusted-workflow-sha", "artifact-id", "artifact-sha256"):
        parser.add_argument(f"--{name}", required=True)
    args = parser.parse_args(argv)
    try:
        result = capture_runtime_phase10_maven_sidecar_upload(
            args.plan, args.repository_root, args.destination,
            plan_artifact_id=int(args.plan_artifact_id),
            plan_artifact_sha256=args.plan_artifact_sha256,
            original_run_id=int(args.original_run_id),
            original_run_attempt=int(args.original_run_attempt),
            trusted_workflow_sha=args.trusted_workflow_sha,
            artifact_id=int(args.artifact_id), artifact_sha256=args.artifact_sha256,
            token=os.environ["GITHUB_TOKEN"], environ=os.environ,
        )
        print(canonical_json_bytes(result).decode().strip())
    except (OSError, ValueError, KeyError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
