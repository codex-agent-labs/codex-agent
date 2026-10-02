"""Capture original Runtime signing preparation transport, not signing authority.

The protected consumer must validate preparation records, selected originals and
full product semantics separately. No uploaded field chooses producer or policy.
"""

import os
from pathlib import Path
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse as products
from products.inventory import (
    canonical_json_bytes, publish_regular_tree, read_regular_file_bytes, regular_file_inventory,
    require_integer, require_sha256, sha256_bytes, sha256_file, verified_zip_contents, write_canonical_json,
)
from products.registry import NATIVE_TARGETS
from products.sdk_package import _require_capability_output_separate


def capture_runtime_signing_preparation(plan_path, destination, *, target, artifact_id,
        artifact_sha256, trusted_workflow_sha, repository_root=None, environ=None, token):
    """Authenticate the fixed original job/upload and preserve all original bytes."""
    if target not in (*NATIVE_TARGETS, "aggregate"):
        raise ValueError("Runtime preparation capture requires a native or aggregate target")
    require_integer(artifact_id, "Runtime preparation artifact ID", 1)
    require_sha256(artifact_sha256, "Runtime preparation artifact digest")
    if type(token) is not str or not token:
        raise ValueError("Runtime preparation capture requires an observation token")
    root = Path(repository_root or Path(__file__).resolve().parents[1]).resolve(strict=True)
    plan_path, destination = Path(plan_path).absolute(), Path(destination).absolute()

    def output_safe():
        _require_capability_output_separate(destination, (root, plan_path))
        if destination.exists() or destination.is_symlink():
            raise ValueError("Runtime preparation capture destination must not exist")

    output_safe()
    plan_bytes = read_regular_file_bytes(plan_path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
    with tempfile.TemporaryDirectory(prefix="runtime-preparation-capture-") as temporary:
        private = Path(temporary).resolve()
        captured_plan = private / "impact-plan.json"
        captured_plan.write_bytes(plan_bytes)
        plan = products._validate_plan(captured_plan, root)
        if plan["remoteBuildAuthorized"] is not True or plan["event"] not in {"pull_request", "merge_group"}:
            raise ValueError("Runtime preparation capture requires an authorized PR or merge-group plan")
        producer = products.validate_producer(products._consumer(plan, os.environ if environ is None else environ)["producer"])
        job = f"product-validation / runtime-signing-prepare-{target}"
        observed = products._observe_ci_producer_jobs({"preparation": producer},
            jobs_by_phase={"preparation": job}, trusted_workflow_sha=trusted_workflow_sha, token=token)
        name = f"codex-agent-runtime-signing-preparation-{target}-{producer['tree']}-attempt-{producer['runAttempt']}"
        prepared = private / "captured"
        prepared.mkdir()
        archive = prepared / "original-upload.zip"
        artifact, _ = products._download_contract_ci_upload(
            artifact_id, artifact_sha256, name, producer, observed[0]["run"], token,
            destination=archive)
        products._require_artifact_job_window(observed[0], job, artifact)
        zipped, _, _ = verified_zip_contents(archive, retained_paths=(), allow_empty_members=True,
                                             **products._CATALOG_ZIP_LIMITS)
        original = prepared / "original"
        products.safe_extract(archive, original)
        if regular_file_inventory(original, allow_empty=True) != zipped:
            raise ValueError("Runtime preparation extraction differs from its original archive")
        required = {"preparation.json", "selected-inputs", "selected-state-transport"}
        actual = {path.name for path in original.iterdir()}
        if actual != required and not (target == "aggregate" and actual == required | {"release-handoff"}):
            raise ValueError("Runtime preparation requires its exact original root layout")
        if any(not (original / name).is_dir() for name in actual - {"preparation.json"}):
            raise ValueError("Runtime preparation original roots must be directories")
        read_regular_file_bytes(original / "preparation.json", max_bytes=16 * 1024 * 1024,
                                reject_symlink_parents=True)
        transport = {"artifact": artifact, "captureProducer": producer, "observed": observed, "target": target}
        write_canonical_json(prepared / "capture-transport.json", transport)
        transport_bytes = canonical_json_bytes(transport)
        expected_files = sorted([
            {"relativePath": "original-upload.zip", "bytes": archive.stat().st_size, "sha256": artifact_sha256},
            {"relativePath": "capture-transport.json", "bytes": len(transport_bytes),
             "sha256": sha256_bytes(transport_bytes)},
            *({**record, "relativePath": f"original/{record['relativePath']}"} for record in zipped),
        ], key=lambda record: record["relativePath"])
        if (read_regular_file_bytes(plan_path, max_bytes=16 * 1024 * 1024,
                                   reject_symlink_parents=True) != plan_bytes
                or read_regular_file_bytes(captured_plan) != plan_bytes
                or regular_file_inventory(original, allow_empty=True) != zipped
                or sha256_file(archive) != artifact_sha256
                or regular_file_inventory(prepared, allow_empty=True) != expected_files):
            raise ValueError("Runtime preparation original plan or upload changed before publication")
        output_safe()
        publish_regular_tree(prepared, destination, allow_empty=True, expected_inventory=expected_files)
    return transport
