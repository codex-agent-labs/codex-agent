"""Recover one Android validation upload and replay its complete existing gate.

The observed or retained upload is transport only.  Caller-owned package,
binary, S858, Contract, tooling and source policy remains authoritative, and
all returned paths are private to the context lifetime.
"""

from contextlib import contextmanager
import os
from pathlib import Path
import tempfile

if __package__:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse
from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, read_regular_file_bytes,
    regular_file_inventory, sha256_bytes, snapshot_regular_tree,
)
from products.receipt import (
    validate_phase_receipt, validate_producer, verify_output_manifest_identity,
)
from products.registry import PhaseInstanceId
from products.restore import PHASE_PLAN_KEYS, restore_object, verify_phase_shard
from products.sdk_package import _require_capability_output_separate
from products.sdk_validation_inputs import _request_inventory
from products.signing_isolation import require_no_signing_secret
from products import sdk_android_validation_phase as validation_phase
from sdk_android_metadata_workflow import _compare_original_inputs, _replan
from sdk_facade_capture import (
    capture_sdk_android_validation_upload, verify_retained_sdk_phase_upload,
)


_INSTANCE = PhaseInstanceId("sdk", "sdk-android", "validation", "android")
_LIMIT = 512 * 1024 * 1024


def _read(path):
    return read_regular_file_bytes(
        Path(path), max_bytes=_LIMIT, reject_symlink_parents=True)


@contextmanager
def verified_original_android_validation(
        plan, validation_receipt_path, *, artifact_id, artifact_sha256,
        trusted_workflow_sha, package_stage, package_receipt, binary_stage,
        binary_receipt, compatibility_request, binary_contract_evidence,
        trusted_source_commit, trusted_source_tree, tooling_evidence,
        tooling_public_key, java_executable, apkanalyzer_executable,
        policy_revision, required_trust_domain, repository_root, environ, token,
        tooling_keyring=None, tooling_keys_directory=None,
        trusted_workflow_path=None, trusted_job_name=None):
    """Hold one official upload inside the complete original replay lifetime."""
    with _verified_android_validation(
            plan, validation_receipt_path, validation_capture=None,
            artifact_id=artifact_id, artifact_sha256=artifact_sha256,
            trusted_workflow_sha=trusted_workflow_sha,
            package_stage=package_stage, package_receipt=package_receipt,
            binary_stage=binary_stage, binary_receipt=binary_receipt,
            compatibility_request=compatibility_request,
            binary_contract_evidence=binary_contract_evidence,
            trusted_source_commit=trusted_source_commit,
            trusted_source_tree=trusted_source_tree,
            tooling_evidence=tooling_evidence,
            tooling_public_key=tooling_public_key,
            java_executable=java_executable,
            apkanalyzer_executable=apkanalyzer_executable,
            policy_revision=policy_revision,
            required_trust_domain=required_trust_domain,
            repository_root=repository_root, environ=environ, token=token,
            tooling_keyring=tooling_keyring,
            tooling_keys_directory=tooling_keys_directory,
            trusted_workflow_path=trusted_workflow_path,
            trusted_job_name=trusted_job_name) as value:
        yield value


@contextmanager
def verified_retained_android_validation(
        plan, validation_receipt_path, *, validation_capture,
        package_stage, package_receipt, binary_stage, binary_receipt,
        compatibility_request, binary_contract_evidence,
        trusted_source_commit, trusted_source_tree, tooling_evidence,
        tooling_public_key, java_executable, apkanalyzer_executable,
        policy_revision, required_trust_domain, repository_root, environ,
        tooling_keyring=None, tooling_keys_directory=None):
    """Replay a caller-authenticated retained carrier; it grants no trust."""
    with _verified_android_validation(
            plan, validation_receipt_path,
            validation_capture=Path(validation_capture),
            package_stage=package_stage, package_receipt=package_receipt,
            binary_stage=binary_stage, binary_receipt=binary_receipt,
            compatibility_request=compatibility_request,
            binary_contract_evidence=binary_contract_evidence,
            trusted_source_commit=trusted_source_commit,
            trusted_source_tree=trusted_source_tree,
            tooling_evidence=tooling_evidence,
            tooling_public_key=tooling_public_key,
            java_executable=java_executable,
            apkanalyzer_executable=apkanalyzer_executable,
            policy_revision=policy_revision,
            required_trust_domain=required_trust_domain,
            repository_root=repository_root, environ=environ,
            tooling_keyring=tooling_keyring,
            tooling_keys_directory=tooling_keys_directory) as value:
        yield value


@contextmanager
def _verified_android_validation(
        plan, validation_receipt_path, *, validation_capture,
        package_stage, package_receipt, binary_stage, binary_receipt,
        compatibility_request, binary_contract_evidence,
        trusted_source_commit, trusted_source_tree, tooling_evidence,
        tooling_public_key, java_executable, apkanalyzer_executable,
        policy_revision, required_trust_domain, repository_root, environ,
        tooling_keyring=None, tooling_keys_directory=None,
        artifact_id=None, artifact_sha256=None, trusted_workflow_sha=None,
        token=None, trusted_workflow_path=None, trusted_job_name=None):
    environment = os.environ if environ is None else environ
    require_no_signing_secret(environment)
    if (tooling_keyring is None) != (tooling_keys_directory is None):
        raise ValueError("Android original tooling keyring and directory must be paired")
    if (trusted_workflow_path is None) != (trusted_job_name is None):
        raise ValueError("Android original workflow path and job must be pinned together")
    if validation_capture is not None and trusted_workflow_path is not None:
        raise ValueError("Retained Android validation cannot select an official child route")
    root = Path(repository_root).resolve(strict=True)
    plan, receipt_path = Path(plan).absolute(), Path(validation_receipt_path).absolute()
    trees = {
        "package": Path(package_stage).absolute(),
        "binary": Path(binary_stage).absolute(),
        "tooling": Path(tooling_evidence).absolute(),
    }
    files = {
        "plan": plan, "receipt": receipt_path,
        "packageReceipt": Path(package_receipt).absolute(),
        "binaryReceipt": Path(binary_receipt).absolute(),
        "compatibilityRequest": Path(compatibility_request).absolute(),
        "toolingPublicKey": Path(tooling_public_key).absolute(),
        "java": Path(java_executable).absolute(),
        "apkanalyzer": Path(apkanalyzer_executable).absolute(),
    }
    contract_trees, contract_files = validation_phase._contract_sources(
        binary_contract_evidence)
    trees.update(contract_trees)
    files.update(contract_files)
    if tooling_keyring is not None:
        files["toolingKeyring"] = Path(tooling_keyring).absolute()
        trees["toolingKeys"] = Path(tooling_keys_directory).absolute()
    if validation_capture is not None:
        trees["retainedValidation"] = validation_capture.absolute()
    tree_before = {name: regular_file_inventory(path, allow_empty=True)
                   for name, path in trees.items()}
    file_before = {name: _read(path) for name, path in files.items()}
    request_before = _request_inventory(files["compatibilityRequest"])
    raw = file_before["receipt"]
    receipt = validate_phase_receipt(load_canonical_json_bytes(raw))
    if tuple(receipt[name] for name in ("product", "component", "phase", "target")) != (
            "sdk", "sdk-android", "validation", "android"):
        raise ValueError("Original Android validation requires its exact receipt")
    producer = validate_producer(receipt["producer"], "Original Android validation producer")
    authority = canonical_json_bytes({
        "binaryContractEvidence": binary_contract_evidence,
        "trustedSourceCommit": trusted_source_commit,
        "trustedSourceTree": trusted_source_tree,
        "policyRevision": policy_revision,
        "requiredTrustDomain": required_trust_domain,
    })
    captured = {}
    package = binary = None

    def unchanged():
        require_no_signing_secret(environment)
        if (canonical_json_bytes(receipt) != raw
                or canonical_json_bytes({
                    "binaryContractEvidence": binary_contract_evidence,
                    "trustedSourceCommit": trusted_source_commit,
                    "trustedSourceTree": trusted_source_tree,
                    "policyRevision": policy_revision,
                    "requiredTrustDomain": required_trust_domain,
                }) != authority
                or any(regular_file_inventory(path, allow_empty=True) != tree_before[name]
                       for name, path in trees.items())
                or any(_read(path) != file_before[name] for name, path in files.items())
                or _request_inventory(files["compatibilityRequest"]) != request_before
                or package is not None and
                   canonical_json_bytes(package) != file_before["packageReceipt"]
                or binary is not None and
                   canonical_json_bytes(binary) != file_before["binaryReceipt"]
                or any(regular_file_inventory(path, allow_empty=True) != inventory
                       for path, inventory in captured.items())):
            raise ValueError("Original Android validation inputs changed during recovery")

    with tempfile.TemporaryDirectory(prefix="original-android-validation-") as temporary:
        private = Path(temporary).resolve()
        _require_capability_output_separate(
            private, [root, *trees.values(), *files.values(), *request_before])
        selected_receipt = private / "validation-receipt.json"
        selected_receipt.write_bytes(raw)
        try:
            capture = private / "capture"
            if validation_capture is None:
                transport = capture_sdk_android_validation_upload(
                    plan, capture, validation_receipt_path=selected_receipt,
                    artifact_id=artifact_id, artifact_sha256=artifact_sha256,
                    trusted_workflow_sha=trusted_workflow_sha,
                    trusted_workflow_path=trusted_workflow_path,
                    trusted_job_name=trusted_job_name,
                    repository_root=root, environ=environment, token=token)
            else:
                snapshot_regular_tree(validation_capture, capture, allow_empty=True)
                if regular_file_inventory(capture, allow_empty=True) != tree_before["retainedValidation"]:
                    raise ValueError("Retained Android validation changed during private capture")
                verify_retained_sdk_phase_upload(capture, raw)
                transport = load_canonical_json_bytes(_read(capture / "capture-transport.json"))
            if (transport.get("captureProducer") != producer
                    or transport.get("validationReceiptSha256") != sha256_bytes(raw)):
                raise ValueError("Android validation transport differs from its selected receipt")
            captured[capture] = regular_file_inventory(capture, allow_empty=True)
            original = capture / "original"
            if ({path.name for path in original.iterdir()} !=
                    {"inputs", "originals", "stage", "shard"}):
                raise ValueError("Original Android validation has an unexpected retained layout")
            dependencies = tuple(dependency for dependency in
                product_reuse._dependency_closure((_INSTANCE,)) if dependency != _INSTANCE)
            dependency_names = {
                "-".join((value.product, value.component, value.phase, value.target)): value
                for value in dependencies
            }
            inputs = original / "inputs"
            if ({path.name for path in inputs.iterdir()} !=
                    {"phase-plan.json", "producer.json", *dependency_names}
                    or {path.name for path in (original / "originals").iterdir()} != {
                    "final", "protected", "validation-inputs",
                }):
                raise ValueError("Original Android validation inputs have an unexpected layout")
            for name, identity in dependency_names.items():
                directory = inputs / name
                if {path.name for path in directory.iterdir()} != {"stage", "phase-receipt.json"}:
                    raise ValueError("Original Android predecessor has an unexpected layout")
                predecessor = validate_phase_receipt(load_canonical_json_bytes(
                    _read(directory / "phase-receipt.json")))
                fields = tuple(getattr(identity, field) for field in
                               ("product", "component", "phase", "target"))
                manifest_value = verify_output_manifest_identity(
                    directory / "stage", *fields, predecessor["productVersion"])
                if (tuple(predecessor[field] for field in
                          ("product", "component", "phase", "target")) != fields
                        or predecessor["outputs"] != manifest_value["outputs"]):
                    raise ValueError("Original Android predecessor differs from its receipt")
            shard = verify_phase_shard(original / "shard", _INSTANCE)
            stage = private / "stage"
            restored = restore_object(
                original / "shard" / shard["objectPath"], stage,
                build_key=shard["buildKey"], receipt_sha256=shard["receiptSha256"],
                object_sha256=shard["objectSha256"])
            if (shard["receiptBytes"] != raw or restored["receiptBytes"] != raw
                    or regular_file_inventory(stage) != regular_file_inventory(original / "stage")):
                raise ValueError("Original Android validation shard differs from its selected receipt")
            manifest = verify_output_manifest_identity(
                stage, "sdk", "sdk-android", "validation", "android",
                receipt["productVersion"])
            if manifest["outputs"] != receipt["outputs"]:
                raise ValueError("Original Android validation stage differs from its receipt")
            plan_value = load_canonical_json_bytes(_read(original / "inputs/phase-plan.json"))
            producer_value = validate_producer(load_canonical_json_bytes(
                _read(original / "inputs/producer.json")), "Original Android retained producer")
            if (canonical_json_bytes(plan_value) != canonical_json_bytes(
                    {name: receipt[name] for name in PHASE_PLAN_KEYS})
                    or producer_value != producer):
                raise ValueError("Original Android validation selection differs from its receipt")
            package = validate_phase_receipt(load_canonical_json_bytes(file_before["packageReceipt"]))
            binary = validate_phase_receipt(load_canonical_json_bytes(file_before["binaryReceipt"]))
            _compare_original_inputs(
                original, package_stage=trees["package"],
                package_receipt=files["packageReceipt"],
                binary_stage=trees["binary"], binary_receipt=files["binaryReceipt"],
                compatibility_request=files["compatibilityRequest"],
                binary_contract_evidence=binary_contract_evidence)
            _replan(root, receipt, package)
            unchanged()
            replay = private / "replay-stage"
            validation_phase.produce_sdk_android_validation_phase(
                repository=root, package_stage=trees["package"],
                package_receipt=files["packageReceipt"],
                binary_stage=trees["binary"], binary_receipt=files["binaryReceipt"],
                compatibility_request=files["compatibilityRequest"],
                binary_contract_evidence=binary_contract_evidence,
                final_capture=original / "originals/final",
                protected_capture=original / "originals/protected",
                expected_capture_producer=producer,
                expected_original_producer=binary["producer"],
                trusted_source_commit=trusted_source_commit,
                trusted_source_tree=trusted_source_tree,
                tooling_evidence=trees["tooling"],
                tooling_public_key=files["toolingPublicKey"],
                java_executable=files["java"],
                apkanalyzer_executable=files["apkanalyzer"],
                policy_revision=policy_revision,
                required_trust_domain=required_trust_domain,
                destination=replay, tooling_keyring=tooling_keyring,
                tooling_keys_directory=tooling_keys_directory)
            if regular_file_inventory(replay) != regular_file_inventory(stage):
                raise ValueError("Full Android validation replay differs from its original stage")
            captured[stage] = regular_file_inventory(stage)
            captured[replay] = regular_file_inventory(replay)
            unchanged()
            yield {"stage": stage, "receiptPath": selected_receipt,
                   "receiptBytes": raw, "receipt": receipt,
                   "original": original, "capture": capture,
                   "packageStage": trees["package"], "packageReceipt": package}
        finally:
            unchanged()
            if _read(selected_receipt) != raw:
                raise ValueError("Selected original Android validation receipt changed during recovery")
