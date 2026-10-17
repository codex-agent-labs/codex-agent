"""Recover one signed failed-SDK-catalog key from a later protected dispatch.

The caller independently pins both producers, both upload identities, and the
reviewed custody route. This is development-cache transport, not release trust
or authorization to start a protected workflow.
"""

from __future__ import annotations

from pathlib import Path
import os
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from ci import product_reuse as products
from ci.products.inventory import (
    publish_regular_tree, regular_file_inventory,
    require_integer, require_sha256, sha256_file, verified_zip_contents,
)
from ci.products.receipt import validate_producer
from ci.products.signing_isolation import require_no_signing_secret
from ci.receipt import safe_extract
from ci.sdk_catalog_custody import (
    PUBLIC_KEY, RECORD, SIGNATURE, _pinned_policy,
    verify_failed_sdk_catalog_custody,
)


CUSTODY_WORKFLOW_PATH = ".github/workflows/sdk-failed-catalog-custody.yml"
CUSTODY_JOB_NAME = "sdk-failed-catalog-custody / sdk-failed-catalog-custody"
_CUSTODY_ZIP_LIMITS = {
    # Actions transport ZIP entry order is not product-canonical order.
    "require_sorted": False,
    "max_archive_bytes": 20 * 1024 * 1024,
    "max_central_directory_bytes": 64 * 1024,
    "max_members": 3,
    "max_entry_bytes": 16 * 1024 * 1024,
    "max_total_bytes": 17 * 1024 * 1024,
    "max_compression_ratio": 100,
}


def locate_failed_sdk_catalog_custody(destination, *, catalog_producer,
        catalog_artifact_id, catalog_artifact_sha256,
        catalog_workflow_sha, catalog_workflow_path, catalog_job_name,
        custody_producer, custody_artifact_id, custody_artifact_sha256,
        custody_workflow_sha, custody_job_name, trusted_source_commit,
        keyring_path, keys_directory, expected_keyring_sha256,
        expected_keys_inventory_sha256, token, environ=None):
    """Return independently signed catalog pins from exact official custody bytes."""
    environment = os.environ if environ is None else environ
    require_no_signing_secret(environment)
    require_no_signing_secret(os.environ)
    catalog_producer = validate_producer(catalog_producer)
    custody_producer = validate_producer(custody_producer)
    if (catalog_producer["event"] != "pull_request"
            or custody_producer["event"] != "workflow_dispatch"
            or catalog_producer["repository"] != custody_producer["repository"]
            or catalog_producer["runId"] == custody_producer["runId"]):
        raise ValueError("SDK custody requires distinct failed PR and protected dispatch producers")
    if type(token) is not str or not token or custody_job_name != CUSTODY_JOB_NAME:
        raise ValueError("SDK custody requires an observation token and its exact protected child job")
    catalog_artifact_id = require_integer(catalog_artifact_id, "Original catalog artifact ID", 1)
    catalog_artifact_sha256 = require_sha256(catalog_artifact_sha256, "Original catalog artifact digest")
    custody_artifact_id = require_integer(custody_artifact_id, "Custody artifact ID", 1)
    custody_artifact_sha256 = require_sha256(custody_artifact_sha256, "Custody artifact digest")
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("SDK custody destination already exists")
    # Reject substituted public policy before contacting GitHub.
    _pinned_policy(keyring_path, keys_directory,
        expected_keyring_sha256, expected_keys_inventory_sha256)
    name = (f"codex-agent-sdk-failed-catalog-custody-{custody_producer['runId']}"
            f"-attempt-{custody_producer['runAttempt']}")
    observed = products._observe_ci_producer_jobs(
        {"custody": custody_producer}, jobs_by_phase={"custody": custody_job_name},
        trusted_workflows_by_phase={"custody": {
            "path": CUSTODY_WORKFLOW_PATH, "sha": custody_workflow_sha,
        }}, token=token, allow_protected_dispatch=True,
        dispatch_authorization_job=None)[0]
    run = observed["run"]
    if run.get("status") != "completed" or run.get("conclusion") != "success":
        raise ValueError("SDK custody dispatch did not complete successfully")
    url = (f"https://api.github.com/repos/{custody_producer['repository']}"
           f"/actions/artifacts/{custody_artifact_id}")
    artifact = products.api_json(url, token)
    transport = artifact.get("workflow_run") if isinstance(artifact, dict) else None
    if (not isinstance(artifact, dict) or artifact.get("id") != custody_artifact_id
            or artifact.get("digest") != custody_artifact_sha256
            or artifact.get("name") != name or artifact.get("expired") is not False
            or artifact.get("archive_download_url") != url + "/zip"
            or not isinstance(transport, dict)
            or transport.get("id") != custody_producer["runId"]
            or transport.get("head_sha") != run.get("head_sha")):
        raise ValueError("SDK custody upload differs from independently pinned dispatch")
    size = require_integer(artifact.get("size_in_bytes"), "Custody transport bytes", 1)
    if size > _CUSTODY_ZIP_LIMITS["max_archive_bytes"]:
        raise ValueError("SDK custody upload exceeds transport limit")
    products._require_artifact_job_window(observed, custody_job_name, artifact)
    with tempfile.TemporaryDirectory(prefix="sdk-custody-locate-") as temporary:
        root = Path(temporary).resolve()
        archive = root / "official.zip"
        products.download_artifact_to_file(artifact, token, archive,
            max_bytes=_CUSTODY_ZIP_LIMITS["max_archive_bytes"])
        if archive.stat().st_size != size or sha256_file(archive) != custody_artifact_sha256:
            raise ValueError("SDK custody upload bytes differ from official digest")
        inventory, _, _ = verified_zip_contents(archive, retained_paths=(),
            **_CUSTODY_ZIP_LIMITS)
        if {item["relativePath"] for item in inventory} != {RECORD, SIGNATURE, PUBLIC_KEY}:
            raise ValueError("SDK custody upload contains an unexpected file")
        extracted = root / "extracted"
        safe_extract(archive, extracted)
        if regular_file_inventory(extracted) != inventory:
            raise ValueError("SDK custody extraction differs from official archive")
        pins = dict(producer=catalog_producer, artifact_id=catalog_artifact_id,
            artifact_sha256=catalog_artifact_sha256,
            trusted_workflow_sha=catalog_workflow_sha,
            trusted_workflow_path=catalog_workflow_path,
            trusted_job_name=catalog_job_name,
            trusted_source_commit=trusted_source_commit,
            keyring_path=keyring_path, keys_directory=keys_directory,
            expected_keyring_sha256=expected_keyring_sha256,
            expected_keys_inventory_sha256=expected_keys_inventory_sha256)
        verified = verify_failed_sdk_catalog_custody(extracted, **pins)
        publish_regular_tree(extracted, destination, expected_inventory=inventory)
        published = verify_failed_sdk_catalog_custody(destination, **pins)
        if regular_file_inventory(destination) != inventory or \
                {key: value for key, value in verified.items() if key != "publicKey"} != \
                {key: value for key, value in published.items() if key != "publicKey"}:
            raise ValueError("SDK custody publication differs from verified original")
    require_no_signing_secret(environment)
    return {"publicKey": published["publicKey"],
            "publicKeySha256": published["publicKeySha256"],
            "catalogArtifactId": catalog_artifact_id,
            "catalogArtifactSha256": catalog_artifact_sha256,
            "catalogArtifactName": published["catalogArtifactName"],
            "catalogIndexSha256": published["catalogIndexSha256"],
            "custodyArtifactId": custody_artifact_id,
            "custodyArtifactSha256": custody_artifact_sha256,
            "custodyArtifactName": name}
