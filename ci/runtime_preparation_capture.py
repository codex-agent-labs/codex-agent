"""Capture original Runtime signing preparation transport, not signing authority.

The protected consumer must validate preparation records, selected originals and
full product semantics separately. No uploaded field chooses producer or policy.
"""

import os
from pathlib import Path
import sys
import tempfile
import zipfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse as products
from impact import require_oid
from products.inventory import (
    canonical_json_bytes, publish_regular_tree, read_regular_file_bytes, regular_file_inventory,
    require_integer, require_sha256, sha256_bytes, sha256_file, verified_zip_contents, write_canonical_json,
    require_exact_keys, require_array, require_regular_directory,
)
from products.registry import NATIVE_TARGETS
from products.runtime_attestation import read_runtime_variant_handoff
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


def capture_runtime_native_release_handoffs(plan_path, destination, *, recovery,
        selected_receipt_sha256s, trusted_workflow_sha, repository_root=None, environ=None, token):
    """Authenticate historical signed uploads against current selected receipts."""
    recovery = require_exact_keys(recovery, {"producer", "trustedWorkflowSha", "artifacts"}, "native recovery")
    producer = products.validate_producer(recovery["producer"])
    original_workflow = require_oid(recovery["trustedWorkflowSha"], "native recovery workflow SHA")
    require_oid(trusted_workflow_sha, "current trusted workflow SHA")
    if type(token) is not str or not token:
        raise ValueError("Native recovery requires an observation token")
    selected = require_exact_keys(selected_receipt_sha256s, NATIVE_TARGETS, "selected native receipts")
    for target in NATIVE_TARGETS:
        require_exact_keys(selected[target], {"binary", "package", "validation", "metadata"}, "selected native phases")
        for digest in selected[target].values():
            require_sha256(digest, "selected native receipt digest")
    artifacts = {}
    ids = set()
    for record in require_array(recovery["artifacts"], "native recovery artifacts"):
        require_exact_keys(record, {"target", "artifactId", "artifactSha256"}, "native recovery artifact")
        target = record["target"]
        if type(target) is not str or target not in NATIVE_TARGETS or target in artifacts:
            raise ValueError("Native recovery requires each exact native target once")
        require_integer(record["artifactId"], "native recovery artifact ID", 1)
        require_sha256(record["artifactSha256"], "native recovery artifact digest")
        if record["artifactId"] in ids:
            raise ValueError("Native recovery artifact IDs must be unique")
        ids.add(record["artifactId"])
        artifacts[target] = dict(record)
    if set(artifacts) != set(NATIVE_TARGETS):
        raise ValueError("Native recovery requires all five targets")
    authority_bytes = canonical_json_bytes({"recovery": recovery, "selected": selected})
    root = Path(repository_root or Path(__file__).resolve().parents[1]).resolve(strict=True)
    plan_path, destination = Path(plan_path).absolute(), Path(destination).absolute()

    def output_safe():
        _require_capability_output_separate(destination, (plan_path,))
        if destination == root or root not in destination.parents:
            raise ValueError("Native recovery destination must be below the repository")
        for parent in destination.parents:
            if parent.exists() or parent.is_symlink():
                require_regular_directory(parent)
        if destination.exists() or destination.is_symlink():
            raise ValueError("Native recovery destination must not exist")

    output_safe()
    plan_bytes = read_regular_file_bytes(plan_path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
    with tempfile.TemporaryDirectory(prefix="runtime-native-recovery-") as temporary:
        private = Path(temporary).resolve()
        captured_plan = private / "impact-plan.json"
        captured_plan.write_bytes(plan_bytes)
        plan = products._validate_plan(captured_plan, root)
        if plan["remoteBuildAuthorized"] is not True or plan["event"] not in {"pull_request", "merge_group"}:
            raise ValueError("Native recovery requires an authorized PR or merge-group plan")
        consumer = products.validate_producer(products._consumer(plan, os.environ if environ is None else environ)["producer"])
        if (producer["repository"] != consumer["repository"]
                or producer["event"] != consumer["event"]
                or producer.get("pullRequest") != consumer.get("pullRequest")):
            raise ValueError("Native recovery original producer must match the current repository and PR context")
        jobs = {target: f"product-validation / runtime-native-attestation-{target}" for target in NATIVE_TARGETS}
        observed = products._observe_ci_producer_jobs({target: producer for target in NATIVE_TARGETS},
            jobs_by_phase=jobs, trusted_workflow_sha=original_workflow, token=token)
        policy_root = private / "policy"
        trust = products._release_trust(root, plan["validationCommit"], policy_root)
        if trust is None:
            raise ValueError("Native recovery requires a tracked release signing policy")
        policy_inventory = regular_file_inventory(policy_root)
        prepared = private / "captured"
        prepared.mkdir()
        records = []
        expected_files = []
        for target in NATIVE_TARGETS:
            record = artifacts[target]
            with tempfile.TemporaryDirectory(prefix="original-native-", dir=private) as scratch:
                archive = Path(scratch) / "original-upload.zip"
                name = f"codex-agent-runtime-release-handoff-{target}-{producer['tree']}-attempt-{producer['runAttempt']}"
                artifact, _ = products._download_contract_ci_upload(record["artifactId"],
                    record["artifactSha256"], name, producer, observed[0]["run"], token, destination=archive)
                products._require_artifact_job_window(observed[0], jobs[target], artifact)
                with zipfile.ZipFile(archive) as zipped:
                    paths = [entry.filename for entry in zipped.infolist()
                             if entry.filename.startswith("runtime-input/") and not entry.is_dir()]
                if len(paths) != 9:
                    raise ValueError("Native recovery requires the exact nine-file signed leaf")
                _, contents, archive_info = verified_zip_contents(archive, retained_paths=paths,
                    max_retained_bytes=2 * 1024 * 1024 * 1024,
                    allow_empty_members=True, **products._CATALOG_ZIP_LIMITS)
                if archive_info != {"bytes": artifact["size_in_bytes"], "sha256": record["artifactSha256"]}:
                    raise ValueError("Native recovery original archive changed during verification")
                leaf = prepared / target / "runtime-input"
                leaf.mkdir(parents=True)
                for path, raw in contents.items():
                    relative = path.removeprefix("runtime-input/")
                    output = leaf / relative
                    output.parent.mkdir(parents=True, exist_ok=True)
                    output.write_bytes(raw)
                    expected_files.append({"relativePath": f"{target}/runtime-input/{relative}",
                                           "bytes": len(raw), "sha256": sha256_bytes(raw)})
                verified = read_runtime_variant_handoff(leaf, target=target,
                    keyring=trust.keyring, keys_directory=trust.keys)
                actual = {phase: sha256_bytes(raw) for phase, raw in verified["receiptBytes"].items()}
                if actual != selected[target]:
                    raise ValueError("Native recovery receipts differ from the current selected originals")
                records.append({"target": target, "artifact": artifact, "receiptSha256s": actual})
        transport = {"producer": producer, "trustedWorkflowSha": original_workflow,
            "captureProducer": consumer, "captureTrustedWorkflowSha": trusted_workflow_sha,
            "observed": observed, "artifacts": records}
        raw = canonical_json_bytes(transport)
        write_canonical_json(prepared / "transport.json", transport)
        expected_files.append({"relativePath": "transport.json", "bytes": len(raw), "sha256": sha256_bytes(raw)})
        expected_files.sort(key=lambda record: record["relativePath"])
        if (read_regular_file_bytes(plan_path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True) != plan_bytes
                or read_regular_file_bytes(captured_plan) != plan_bytes
                or canonical_json_bytes({"recovery": recovery, "selected": selected}) != authority_bytes
                or regular_file_inventory(policy_root) != policy_inventory
                or regular_file_inventory(prepared) != expected_files):
            raise ValueError("Native recovery authority or original bytes changed before publication")
        output_safe()
        publish_regular_tree(prepared, destination, expected_inventory=expected_files)
    return destination
