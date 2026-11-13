"""Capture original Core14 preparation transport; never attest its replay claim.

Run this module from independently pinned source. The uploaded record remains
unsigned candidate evidence until a protected caller admits its full originals.
"""

import os
from pathlib import Path
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from . import product_reuse as products
from .products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, publish_regular_tree,
    read_regular_file_bytes, regular_file_inventory, require_exact_keys,
    require_integer, require_sha256, sha256_bytes, sha256_file,
    verified_zip_contents, write_canonical_json,
)
from .products.receipt import validate_phase_receipt
from .products.sdk_package import _require_capability_output_separate
from .products.signatures import validate_signing_metadata
from .sdk_facade_metadata_original import _context


def capture_core_context_preparation(plan_path, receipt_path, destination, *,
        expected_receipt_sha256, metadata_artifact_id, metadata_artifact_sha256,
        preparation_artifact_id, preparation_artifact_sha256, original_context,
        expected_signing, trusted_workflow_sha, repository_root, environ=None, token):
    """Retain exact official bytes and caller comparisons, without signing.

    All expected values must come from independent successful-worker outputs or
    the protected caller's Git-pinned release policy, not from the upload.
    """
    for name, value in (("Core receipt", expected_receipt_sha256),
                        ("Core metadata upload", metadata_artifact_sha256),
                        ("Core preparation upload", preparation_artifact_sha256)):
        require_sha256(value, name)
    for name, value in (("Core metadata upload", metadata_artifact_id),
                        ("Core preparation upload", preparation_artifact_id)):
        require_integer(value, name, 1)
    if type(token) is not str or not token:
        raise ValueError("Core preparation capture requires an observation token")
    root = Path(repository_root).resolve(strict=True)
    plan_path, receipt_path, destination = (Path(path).absolute() for path in
        (plan_path, receipt_path, destination))
    _require_capability_output_separate(destination, (root, plan_path, receipt_path))
    if destination.exists() or destination.is_symlink() or destination.resolve(strict=False) != destination:
        raise ValueError("Core preparation capture destination must be fresh and normalized")
    plan_bytes = read_regular_file_bytes(plan_path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
    receipt_bytes = read_regular_file_bytes(receipt_path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
    if sha256_bytes(receipt_bytes) != expected_receipt_sha256:
        raise ValueError("Core preparation receipt differs from caller selection")
    receipt = validate_phase_receipt(load_canonical_json_bytes(receipt_bytes))
    if tuple(receipt[name] for name in ("product", "component", "phase", "target")) != \
            ("sdk", "sdk-core", "metadata", "common"):
        raise ValueError("Core preparation requires the selected metadata receipt")
    context_bytes = canonical_json_bytes(_context(original_context))
    signing_bytes = canonical_json_bytes(validate_signing_metadata(expected_signing, trust_domain="release"))
    producer = receipt["producer"]
    job = "product-validation / sdk-core-metadata-common"
    name = ("codex-agent-sdk-core-context-preparation-"
            f"{receipt['buildKey'].removeprefix('sha256:')}-{producer['tree']}-"
            f"attempt-{producer['runAttempt']}")
    with tempfile.TemporaryDirectory(prefix="core-context-capture-") as temporary:
        prepared = Path(temporary).resolve() / "capture"
        captured_plan = prepared / "plan/impact-plan.json"
        captured_plan.parent.mkdir(parents=True)
        captured_plan.write_bytes(plan_bytes)
        captured_receipt = prepared / "selection/metadata-receipt.json"
        captured_receipt.parent.mkdir(parents=True)
        captured_receipt.write_bytes(receipt_bytes)
        plan = products._validate_plan(captured_plan, root)
        if plan["remoteBuildAuthorized"] is not True or plan["event"] not in {"pull_request", "merge_group"}:
            raise ValueError("Core preparation requires an authorized PR or merge-group plan")
        observed = products._observe_ci_producer_jobs({"preparation": producer},
            jobs_by_phase={"preparation": job}, trusted_workflow_sha=trusted_workflow_sha, token=token)
        artifact, raw = products._download_contract_ci_upload(
            preparation_artifact_id, preparation_artifact_sha256, name, producer, observed[0]["run"], token)
        products._require_artifact_job_window(observed[0], job, artifact)
        archive = prepared / "transport.zip"
        archive.write_bytes(raw)
        zipped, _, _ = verified_zip_contents(archive, retained_paths=(),
            max_archive_bytes=1024 * 1024, max_members=1, max_entry_bytes=64 * 1024,
            max_total_bytes=64 * 1024)
        if [record["relativePath"] for record in zipped] != ["original-context.json"]:
            raise ValueError("Core preparation upload has an unexpected layout")
        original = prepared / "original"
        products.safe_extract(archive, original)
        if regular_file_inventory(original) != zipped:
            raise ValueError("Core preparation extraction differs from its original upload")
        record_bytes = read_regular_file_bytes(original / "original-context.json",
            max_bytes=64 * 1024, reject_symlink_parents=True)
        if len(record_bytes) != zipped[0]["bytes"] or sha256_bytes(record_bytes) != zipped[0]["sha256"]:
            raise ValueError("Core preparation record differs from the original upload")
        record = require_exact_keys(load_canonical_json_bytes(record_bytes), {
            "schemaVersion", "kind", "buildKey", "receiptSha256", "artifactId",
            "artifactSha256", "producer", "originalContext", "signing",
        }, "Core preparation record")
        if (require_integer(record["schemaVersion"], "Core preparation schema", 1) != 1
                or record["kind"] != "sdk-core-metadata-original-context"
                or record["buildKey"] != receipt["buildKey"]
                or record["receiptSha256"] != expected_receipt_sha256
                or record["artifactId"] != metadata_artifact_id
                or record["artifactSha256"] != metadata_artifact_sha256
                or record["producer"] != producer
                or canonical_json_bytes(_context(record["originalContext"])) != context_bytes
                or canonical_json_bytes(validate_signing_metadata(record["signing"],
                    trust_domain="release")) != signing_bytes):
            raise ValueError("Core preparation record differs from caller-selected originals")
        transport = {"artifact": artifact, "captureProducer": producer,
                     "observed": observed, "receiptSha256": expected_receipt_sha256,
                     "metadataArtifact": {"id": metadata_artifact_id,
                                          "sha256": metadata_artifact_sha256}}
        write_canonical_json(prepared / "capture-transport.json", transport)
        transport_bytes = canonical_json_bytes(transport)
        expected_files = sorted([
            {"relativePath": "plan/impact-plan.json", "bytes": len(plan_bytes),
             "sha256": sha256_bytes(plan_bytes)},
            {"relativePath": "selection/metadata-receipt.json", "bytes": len(receipt_bytes),
             "sha256": expected_receipt_sha256},
            {"relativePath": "transport.zip", "bytes": len(raw),
             "sha256": preparation_artifact_sha256},
            {**zipped[0], "relativePath": "original/original-context.json"},
            {"relativePath": "capture-transport.json", "bytes": len(transport_bytes),
             "sha256": sha256_bytes(transport_bytes)},
        ], key=lambda item: item["relativePath"])
        if (read_regular_file_bytes(plan_path, max_bytes=16 * 1024 * 1024,
                    reject_symlink_parents=True) != plan_bytes
                or read_regular_file_bytes(receipt_path, max_bytes=16 * 1024 * 1024,
                    reject_symlink_parents=True) != receipt_bytes
                or canonical_json_bytes(original_context) != context_bytes
                or canonical_json_bytes(expected_signing) != signing_bytes
                or canonical_json_bytes(transport) != transport_bytes
                or read_regular_file_bytes(captured_receipt) != receipt_bytes
                or sha256_file(archive) != preparation_artifact_sha256
                or regular_file_inventory(prepared) != expected_files):
            raise ValueError("Core preparation source or prepared bytes changed before publication")
        publish_regular_tree(prepared, destination, expected_inventory=expected_files)
    return transport
