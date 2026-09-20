"""Capture observed Apple attestation transport; signature/content gates are separate.

The signing upload belongs to the current authorized caller producer, while its
single carrier record identifies an independently selected original receipt.
Neither recorded observations nor structural carrier binding grant admission.
"""

import os
from pathlib import Path
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse as products
from products.inventory import (
    publish_regular_tree, read_regular_file_bytes, regular_file_inventory,
    require_integer, require_regular_directory, require_sha256, sha256_file,
    verified_zip_contents, write_canonical_json,
)
from products.sdk_apple_validation_inputs import load_sdk_apple_validation_evidence
from products.sdk_package import _require_capability_output_separate


def capture_apple_validation_attestation(plan_path, destination, *, target,
        expected_receipt_sha256, artifact_id, artifact_sha256, trusted_workflow_sha,
        repository_root=None, environ=None, token):
    """Preserve exact original upload bytes without signing or semantic replay."""
    if target not in ("ios-arm64", "ios-simulator-arm64"):
        raise ValueError("Apple attestation capture requires an exact validation target")
    require_sha256(expected_receipt_sha256, "Selected Apple validation receipt digest")
    require_integer(artifact_id, "Apple attestation artifact ID", 1)
    require_sha256(artifact_sha256, "Apple attestation artifact digest")
    if type(token) is not str or not token:
        raise ValueError("Apple attestation capture requires an observation token")
    root = Path(repository_root or Path(__file__).resolve().parents[1]).resolve(strict=True)
    plan_path, destination = Path(plan_path).absolute(), Path(destination).absolute()

    def output_safe():
        _require_capability_output_separate(destination, (root, plan_path))
        if destination.exists() or destination.is_symlink():
            raise ValueError("Apple attestation capture destination must not exist")

    output_safe()
    plan_bytes = read_regular_file_bytes(plan_path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
    with tempfile.TemporaryDirectory(prefix="apple-attestation-capture-") as temporary:
        private = Path(temporary).resolve()
        captured_plan = private / "impact-plan.json"
        captured_plan.write_bytes(plan_bytes)
        plan = products._validate_plan(captured_plan, root)
        if plan["remoteBuildAuthorized"] is not True or plan["event"] not in {"pull_request", "merge_group"}:
            raise ValueError("Apple attestation capture requires an authorized PR or merge-group plan")
        producer = products.validate_producer(products._consumer(
            plan, os.environ if environ is None else environ)["producer"])
        job = f"product-validation / sdk-apple-validation-attestation-{target}"
        observed = products._observe_ci_producer_jobs({"attestation": producer},
            jobs_by_phase={"attestation": job}, trusted_workflow_sha=trusted_workflow_sha, token=token)
        name = (f"codex-agent-sdk-apple-validation-evidence-{target}-"
                f"{expected_receipt_sha256.removeprefix('sha256:')}-{producer['tree']}-"
                f"attempt-{producer['runAttempt']}")
        artifact, raw = products._download_contract_ci_upload(
            artifact_id, artifact_sha256, name, producer, observed[0]["run"], token)
        products._require_artifact_job_window(observed[0], job, artifact)
        prepared = private / "captured"
        prepared.mkdir()
        archive = prepared / "original-upload.zip"
        archive.write_bytes(raw)
        zipped, _, _ = verified_zip_contents(archive, retained_paths=(), allow_empty_members=True,
                                             **products._CATALOG_ZIP_LIMITS)
        original = prepared / "original"
        products.safe_extract(archive, original)
        if regular_file_inventory(original, allow_empty=True) != zipped:
            raise ValueError("Apple attestation extraction differs from its original archive")
        directories = {"sdk-apple-validation-evidence", "preparation-transport", "validation-transport", "caller-policy"}
        if {path.name for path in original.iterdir()} != directories | {"caller.json"}:
            raise ValueError("Apple attestation requires its exact protected-controller result layout")
        for directory in directories:
            require_regular_directory(original / directory, "Apple attestation retained result directory")
        # Retain caller provenance verbatim; this transport reader grants it no
        # policy/source/signing authority and does not interpret its fields.
        read_regular_file_bytes(original / "caller.json", max_bytes=16 * 1024 * 1024,
                                reject_symlink_parents=True)
        records = load_sdk_apple_validation_evidence(original / "sdk-apple-validation-evidence")
        if (len(records) != 1 or records[0]["receiptSha256"] != expected_receipt_sha256
                or records[0]["target"] != target):
            raise ValueError("Apple attestation carrier differs from the exact selected receipt and target")
        transport = {"artifact": artifact, "captureProducer": producer, "observed": observed,
                     "target": target, "receiptSha256": expected_receipt_sha256}
        write_canonical_json(prepared / "capture-transport.json", transport)
        if (read_regular_file_bytes(plan_path, max_bytes=16 * 1024 * 1024,
                                   reject_symlink_parents=True) != plan_bytes
                or read_regular_file_bytes(captured_plan) != plan_bytes
                or regular_file_inventory(original, allow_empty=True) != zipped
                or sha256_file(archive) != artifact_sha256):
            raise ValueError("Apple attestation original plan or upload changed before publication")
        output_safe()
        publish_regular_tree(prepared, destination, allow_empty=True)
    return transport
