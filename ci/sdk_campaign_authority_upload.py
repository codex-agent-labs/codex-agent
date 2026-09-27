"""Hold one officially uploaded, independently pinned SDK campaign authority.

This is no-secret transport authentication, not product release admission. The
protected caller must approve the manifest digest and reviewed route separately.
"""

from contextlib import contextmanager
import os
from pathlib import Path
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from ci import product_reuse as products
from ci.receipt import safe_extract
from products.inventory import (
    read_regular_file_bytes, regular_file_inventory, require_integer,
    require_sha256, sha256_bytes, sha256_file, verified_zip_contents,
)
from products.receipt import validate_producer
from products.signing_isolation import require_no_signing_secret


_FILE = "sdk-campaign-authority.json"
_ZIP_LIMITS = {"require_sorted": False, "max_archive_bytes": 2 * 1024 * 1024,
               "max_central_directory_bytes": 16 * 1024, "max_members": 1,
               "max_entry_bytes": 1024 * 1024, "max_total_bytes": 1024 * 1024,
               "max_compression_ratio": 100}


@contextmanager
def held_official_sdk_campaign_authority(plan_path: Path, repository_root: Path,
        *, artifact_id: int, artifact_sha256: str,
        expected_authority_sha256: str, trusted_workflow_sha: str,
        trusted_workflow_path: str, trusted_job_name: str,
        token: str, environ=None, original_run_id=None,
        original_run_attempt=None):
    """Yield exact authority file and official transport evidence before replay."""
    environment = os.environ if environ is None else environ
    require_no_signing_secret(environment)
    require_no_signing_secret(os.environ)
    artifact_id = require_integer(artifact_id, "SDK authority artifact ID", 1)
    artifact_sha256 = require_sha256(artifact_sha256, "SDK authority artifact digest")
    expected = require_sha256(expected_authority_sha256, "SDK authority file digest")
    if (type(token) is not str or not token or type(trusted_job_name) is not str
            or not trusted_job_name or type(trusted_workflow_path) is not str
            or not trusted_workflow_path):
        raise ValueError("SDK authority requires caller-pinned route and observation token")
    root = Path(repository_root).resolve(strict=True)
    plan_bytes = read_regular_file_bytes(Path(plan_path), max_bytes=16 * 1024 * 1024,
        reject_symlink_parents=True)
    with tempfile.TemporaryDirectory(prefix="sdk-authority-upload-") as temporary:
        private = Path(temporary).resolve()
        captured_plan = private / "impact-plan.json"
        captured_plan.write_bytes(plan_bytes)
        plan = products._validate_plan(captured_plan, root)
        if plan["remoteBuildAuthorized"] is not True or plan["event"] != "pull_request":
            raise ValueError("SDK campaign authority requires an authorized PR plan")
        producer = validate_producer(products._consumer(plan, environment,
            original_run_id=original_run_id,
            original_run_attempt=original_run_attempt)["producer"])
        if producer["event"] != "pull_request":
            raise ValueError("SDK campaign authority requires the exact PR producer")
        name = (f"codex-agent-sdk-campaign-authority-{producer['tree']}-"
                f"attempt-{producer['runAttempt']}")
        observed = products._observe_ci_producer_jobs(
            {"authority": producer}, jobs_by_phase={"authority": trusted_job_name},
            trusted_workflows_by_phase={"authority": {
                "path": trusted_workflow_path, "sha": trusted_workflow_sha,
            }}, token=token)[0]
        archive = private / "official-upload.zip"
        artifact, _ = products._download_contract_ci_upload(
            artifact_id, artifact_sha256, name, producer, observed["run"], token,
            destination=archive, max_bytes=_ZIP_LIMITS["max_archive_bytes"])
        products._require_artifact_job_window(observed, trusted_job_name, artifact)
        if archive.stat().st_size > _ZIP_LIMITS["max_archive_bytes"]:
            raise ValueError("SDK campaign authority upload exceeds its size limit")
        inventory, _, _ = verified_zip_contents(archive, retained_paths=(),
            **_ZIP_LIMITS)
        if {item["relativePath"] for item in inventory} != {_FILE}:
            raise ValueError("SDK campaign authority upload has unexpected files")
        extracted = private / "extracted"
        safe_extract(archive, extracted)
        authority = extracted / _FILE
        raw = read_regular_file_bytes(authority, max_bytes=1024 * 1024,
            reject_symlink_parents=True)
        if (sha256_bytes(raw) != expected or
                regular_file_inventory(extracted) != inventory):
            raise ValueError("SDK campaign authority differs from independently pinned bytes")
        evidence = {"artifactId": artifact_id, "artifactSha256": artifact_sha256,
            "artifactName": name, "authoritySha256": expected, "producer": producer,
            "trustedWorkflowPath": trusted_workflow_path,
            "trustedWorkflowSha": trusted_workflow_sha,
            "trustedJobName": trusted_job_name}
        try:
            yield authority, evidence
        finally:
            require_no_signing_secret(environment)
            require_no_signing_secret(os.environ)
            if (read_regular_file_bytes(authority, max_bytes=1024 * 1024,
                    reject_symlink_parents=True) != raw
                    or regular_file_inventory(extracted) != inventory
                    or sha256_file(archive) != artifact_sha256
                    or read_regular_file_bytes(Path(plan_path), max_bytes=16 * 1024 * 1024,
                        reject_symlink_parents=True) != plan_bytes):
                raise ValueError("SDK campaign authority upload changed during replay")
