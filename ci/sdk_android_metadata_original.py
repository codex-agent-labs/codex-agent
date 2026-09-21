"""Recover original Android metadata through its full validation replay.

The worker upload is transport, not host or product authority. Caller-owned
package, binary, S858, Contract, tooling, source and an independently
authenticated validation capture remain authoritative for the held replay.
"""

from contextlib import contextmanager
from pathlib import Path, PurePosixPath, PureWindowsPath
import subprocess
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse
from products.inventory import (
    canonical_json_bytes, git_product_versions, load_canonical_json_bytes,
    read_regular_file_bytes, regular_file_inventory, require_exact_keys,
    require_integer, run_git, sha256_bytes, write_canonical_json,
)
from products.plan import NOT_APPLICABLE_FLAGS_DIGEST, NOT_APPLICABLE_TOOLCHAIN_DIGEST, plan_phase
from products.receipt import validate_phase_receipt, verify_output_manifest_identity
from products.registry import PhaseInstanceId
from products.restore import PHASE_PLAN_KEYS, restore_object, verify_phase_shard
from products.sdk_android_metadata import OUTPUT_KIND, OUTPUT_PATH, write_android_metadata_content
from products.sdk_android_validation_content import validate_android_validation_content
from products.sdk_package import _require_capability_output_separate
from products.selection import phase_git_inventory
from products.signing_isolation import require_no_signing_secret
from products import sdk_android_validation_phase as validation_phase
from sdk_android_original_validation import verified_retained_android_validation
from sdk_facade_capture import capture_sdk_android_metadata_upload


_INSTANCE = PhaseInstanceId("sdk", "sdk-android", "metadata", "android")
_LIMIT = 512 * 1024 * 1024


def _read(path):
    return read_regular_file_bytes(
        Path(path), max_bytes=_LIMIT, reject_symlink_parents=True)


def _json(path):
    return load_canonical_json_bytes(_read(path))


def _original_posix_path(value, label):
    path = PurePosixPath(value) if type(value) is str and value else None
    if (path is None or PureWindowsPath(value).drive or not path.is_absolute()
            or ".." in path.parts or str(path) != value
            or any(ord(character) < 32 or ord(character) == 127 for character in value)):
        raise ValueError(f"{label} path is invalid")
    return value


def _context(value):
    value = require_exact_keys(
        value, {"repositoryRoot", "metadataRequest"},
        "Caller original Android metadata context")
    for name, path in value.items():
        _original_posix_path(path, f"Original Android metadata {name}")
    return value


def _result_view(value):
    value = require_exact_keys(value, {
        "stage", "receiptPath", "receiptBytes", "receipt", "original",
        "capture", "transport",
    }, "Original Android metadata result")
    return canonical_json_bytes({
        "stagePath": str(value["stage"]),
        "receiptPath": str(value["receiptPath"]),
        "originalPath": str(value["original"]),
        "capturePath": str(value["capture"]),
        "receiptBytes": (value["receiptBytes"].hex()
                         if isinstance(value["receiptBytes"], bytes)
                         else value["receiptBytes"]),
        "receipt": value["receipt"],
        "transport": value["transport"],
        "stageInventory": regular_file_inventory(value["stage"]),
        "captureInventory": regular_file_inventory(value["capture"], allow_empty=True),
    })


def _worker(original, receipt, context, validation_content):
    execution = require_exact_keys(_json(original / "worker/execution.json"), {
        "schemaVersion", "producer", "buildKey", "command", "workingDirectory",
        "returnCode", "launchError", "elapsedNs",
    }, "Original Android metadata execution")
    if (require_integer(execution["schemaVersion"], "Android metadata execution schema", 1) != 1
            or execution["producer"] != receipt["producer"]
            or execution["buildKey"] != receipt["buildKey"]
            or require_integer(execution["returnCode"], "Android metadata execution exit", 0) != 0
            or execution["launchError"] is not None
            or execution["workingDirectory"] != context["repositoryRoot"]):
        raise ValueError("Original Android metadata worker differs from its receipt or caller context")
    require_integer(execution["elapsedNs"], "Android metadata execution elapsed time", 0)
    fields = {
        "codexAgent.product": "sdk", "codexAgent.component": "sdk-android",
        "codexAgent.phase": "metadata", "codexAgent.target": "android",
        "codexAgent.candidateCommit": receipt["producer"]["commit"],
        "codexAgent.candidateTree": receipt["producer"]["tree"],
        "codexAgent.sdkVersion": receipt["productVersion"],
        "codexAgent.sdkAndroidMetadataRequest": context["metadataRequest"],
    }
    expected = product_reuse._runtime_worker_command(
        PurePosixPath(context["repositoryRoot"]) / "gradlew", fields, {},
        build_directory=".", platform_name="posix")
    if execution["command"] != expected:
        raise ValueError("Original Android metadata worker differs from the fixed offline command")
    request = require_exact_keys(_json(original / "metadata-request.json"), {
        "sdkVersion", "packageStage", "packageReceipt", "validationStage",
        "validationReceipt", "releaseAarSha256", "bundledRuntimeSha256",
    }, "Original Android metadata request")
    if (request["sdkVersion"] != receipt["productVersion"]
            or request["releaseAarSha256"] != validation_content["releaseAarSha256"]
            or request["bundledRuntimeSha256"] != validation_content["bundledRuntimeSha256"]):
        raise ValueError("Original Android metadata request differs from verified validation")
    for name in ("packageStage", "packageReceipt", "validationStage", "validationReceipt"):
        _original_posix_path(request[name], "Original Android metadata input")


def _replan(root, receipt, validation_receipt):
    producer = receipt["producer"]
    commit = producer["commit"]
    try:
        if (run_git(root, "rev-parse", f"{commit}^{{commit}}").strip() != commit
                or run_git(root, "rev-parse", f"{commit}^{{tree}}").strip() != producer["tree"]):
            raise ValueError("Original Android metadata commit/tree differs from Git")
    except subprocess.CalledProcessError as error:
        raise ValueError("Original Android metadata source is unavailable") from error
    versions = git_product_versions(root, commit)
    planned = plan_phase(
        _INSTANCE, inventory=phase_git_inventory(root, commit, _INSTANCE),
        versions=versions, upstream_receipts=[validation_receipt],
        toolchain_profile_digest=NOT_APPLICABLE_TOOLCHAIN_DIGEST,
        flags_digest=NOT_APPLICABLE_FLAGS_DIGEST, output_schema_version=1)
    if (receipt["productVersion"] != versions["sdk"]
            or receipt["inputs"] != planned["inputs"]
            or receipt["buildKey"] != planned["buildKey"]):
        raise ValueError("Original Android metadata differs from its source/version/phase key")


def _same_stage(directory, stage, receipt_bytes, label):
    if (_read(directory / "phase-receipt.json") != receipt_bytes
            or regular_file_inventory(directory / "stage") != regular_file_inventory(stage)):
        raise ValueError(f"Original Android metadata {label} differs from verified originals")


@contextmanager
def verified_original_sdk_android_metadata(
        plan, metadata_receipt_path, *, artifact_id, artifact_sha256,
        validation_capture, package_stage, package_receipt, binary_stage,
        binary_receipt, compatibility_request, binary_contract_evidence,
        trusted_source_commit, trusted_source_tree, original_context,
        trusted_workflow_sha, tooling_evidence, tooling_public_key,
        java_executable, apkanalyzer_executable, policy_revision,
        required_trust_domain, repository_root, environ, token,
        tooling_keyring=None, tooling_keys_directory=None):
    """Hold exact metadata transport and the existing full validation replay."""
    require_no_signing_secret(environ)
    if (tooling_keyring is None) != (tooling_keys_directory is None):
        raise ValueError("Android metadata tooling keyring and directory must be paired")
    root = Path(repository_root).resolve(strict=True)
    plan, receipt_path = Path(plan).absolute(), Path(metadata_receipt_path).absolute()
    context = _context(original_context)
    trees = {
        "validationCapture": Path(validation_capture).absolute(),
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
    contract_trees, contract_files = validation_phase._contract_sources(binary_contract_evidence)
    trees.update(contract_trees)
    files.update(contract_files)
    if tooling_keyring is not None:
        files["toolingKeyring"] = Path(tooling_keyring).absolute()
        trees["toolingKeys"] = Path(tooling_keys_directory).absolute()
    raw = _read(receipt_path)
    receipt = validate_phase_receipt(load_canonical_json_bytes(raw))
    if tuple(receipt[name] for name in ("product", "component", "phase", "target")) != (
            "sdk", "sdk-android", "metadata", "android"):
        raise ValueError("Android metadata recovery requires its exact selected receipt")
    before_trees = {name: regular_file_inventory(path, allow_empty=True)
                    for name, path in trees.items()}
    before_files = {name: _read(path) for name, path in files.items()}
    authority = lambda: canonical_json_bytes({
        "binaryContractEvidence": binary_contract_evidence,
        "trustedSourceCommit": trusted_source_commit,
        "trustedSourceTree": trusted_source_tree,
        "originalContext": _context(original_context),
        "policyRevision": policy_revision,
        "requiredTrustDomain": required_trust_domain,
    })
    authority_bytes = authority()
    retained = {}
    result = transport = None
    result_bytes = transport_bytes = None

    def unchanged():
        require_no_signing_secret(environ)
        if (authority() != authority_bytes or _read(receipt_path) != raw
                or canonical_json_bytes(receipt) != raw
                or any(regular_file_inventory(path, allow_empty=True) != before_trees[name]
                       for name, path in trees.items())
                or any(_read(path) != before_files[name] for name, path in files.items())
                or any(regular_file_inventory(path, allow_empty=True) != inventory
                       for path, inventory in retained.items())
                or (transport is not None and canonical_json_bytes(transport) != transport_bytes)
                or (result is not None and _result_view(result) != result_bytes)):
            raise ValueError("Original Android metadata inputs, outputs or caller authority changed")

    with tempfile.TemporaryDirectory(prefix="original-android-metadata-") as temporary:
        private = Path(temporary).resolve()
        _require_capability_output_separate(private, [root, *trees.values(), *files.values()])
        selected = private / "metadata-receipt.json"
        selected.write_bytes(raw)
        try:
            unchanged()
            capture = private / "capture"
            transport = capture_sdk_android_metadata_upload(
                plan, capture, metadata_receipt_path=selected,
                artifact_id=artifact_id, artifact_sha256=artifact_sha256,
                trusted_workflow_sha=trusted_workflow_sha,
                repository_root=root, environ=environ, token=token)
            transport_bytes = canonical_json_bytes(transport)
            if (transport.get("captureProducer") != receipt["producer"]
                    or transport.get("metadataReceiptSha256") != sha256_bytes(raw)
                    or _read(capture / "capture-transport.json") != transport_bytes):
                raise ValueError("Android metadata transport differs from its selected receipt")
            retained[capture] = regular_file_inventory(capture, allow_empty=True)
            original = capture / "original"
            if ({path.name for path in original.iterdir()} !=
                    {"shard", "worker", "selection", "originals", "inputs",
                     "metadata-request.json"}
                    or {path.name for path in (original / "worker").iterdir()} !=
                    {"execution.json", "gradle.log"}
                    or {path.name for path in (original / "selection").iterdir()} !=
                    {"impact-plan.json", "phase-plan.json", "producer.json"}
                    or {path.name for path in (original / "originals").iterdir()} != {"validation"}):
                raise ValueError("Original Android metadata has an unexpected retained layout")
            shard = verify_phase_shard(original / "shard", _INSTANCE)
            stage = private / "stage"
            restored = restore_object(
                original / "shard" / shard["objectPath"], stage,
                build_key=shard["buildKey"], receipt_sha256=shard["receiptSha256"],
                object_sha256=shard["objectSha256"])
            manifest = verify_output_manifest_identity(
                stage, "sdk", "sdk-android", "metadata", "android",
                receipt["productVersion"])
            if (shard["receiptBytes"] != raw or restored["receiptBytes"] != raw
                    or manifest["outputs"] != receipt["outputs"]
                    or len(manifest["outputs"]) != 1
                    or manifest["outputs"][0]["kind"] != OUTPUT_KIND
                    or manifest["outputs"][0]["relativePath"] != OUTPUT_PATH):
                raise ValueError("Original Android metadata shard differs from its selected receipt")
            historical = product_reuse._validate_plan(
                original / "selection/impact-plan.json", root,
                expected_revision=receipt["producer"]["commit"])
            if (historical["remoteBuildAuthorized"] is not True
                    or historical["event"] not in {"pull_request", "merge_group"}):
                raise ValueError("Original Android metadata impact plan is not authorized")
            producer = product_reuse._consumer(historical, {
                "GITHUB_RUN_ID": str(receipt["producer"]["runId"]),
                "GITHUB_RUN_ATTEMPT": str(receipt["producer"]["runAttempt"]),
            })["producer"]
            if producer != receipt["producer"]:
                raise ValueError("Original Android metadata historical producer differs from its receipt")
            selection = original / "selection"
            if (_json(selection / "phase-plan.json") !=
                    {name: receipt[name] for name in PHASE_PLAN_KEYS}
                    or _json(selection / "producer.json") != receipt["producer"]):
                raise ValueError("Original Android metadata retained selection differs from its receipt")
            inputs = original / "inputs"
            if (_json(inputs / "phase-plan.json") !=
                    {name: receipt[name] for name in PHASE_PLAN_KEYS}
                    or _json(inputs / "producer.json") != receipt["producer"]):
                raise ValueError("Original Android metadata election differs from its receipt")
            validation_directory = inputs / "sdk-sdk-android-validation-android"
            validation_receipt_path = validation_directory / "phase-receipt.json"
            validation_raw = _read(validation_receipt_path)
            validation_receipt = validate_phase_receipt(load_canonical_json_bytes(validation_raw))
            if (tuple(validation_receipt[name] for name in
                      ("product", "component", "phase", "target")) !=
                    ("sdk", "sdk-android", "validation", "android")
                    or validation_receipt["productVersion"] != receipt["productVersion"]):
                raise ValueError("Original Android metadata validation has the wrong identity")
            common = dict(
                package_stage=trees["package"], package_receipt=files["packageReceipt"],
                binary_stage=trees["binary"], binary_receipt=files["binaryReceipt"],
                compatibility_request=files["compatibilityRequest"],
                binary_contract_evidence=binary_contract_evidence,
                trusted_source_commit=trusted_source_commit,
                trusted_source_tree=trusted_source_tree,
                tooling_evidence=trees["tooling"], tooling_public_key=files["toolingPublicKey"],
                java_executable=files["java"], apkanalyzer_executable=files["apkanalyzer"],
                policy_revision=policy_revision, required_trust_domain=required_trust_domain,
                repository_root=root, environ=environ, tooling_keyring=tooling_keyring,
                tooling_keys_directory=tooling_keys_directory)
            with verified_retained_android_validation(
                    plan, validation_receipt_path,
                    validation_capture=trees["validationCapture"], **common) as validation:
                _same_stage(validation_directory, validation["stage"],
                            validation["receiptBytes"], "validation")
                package_directory = inputs / "sdk-sdk-android-package-android"
                _same_stage(package_directory, trees["package"],
                            before_files["packageReceipt"], "package")
                if (validation["receiptBytes"] != validation_raw
                        or validation["receipt"] != validation_receipt
                        or regular_file_inventory(original / "originals/validation", allow_empty=True) !=
                           regular_file_inventory(validation["capture"], allow_empty=True)):
                    raise ValueError("Original Android metadata retained validation differs from full replay")
                validation_content = validate_android_validation_content(load_canonical_json_bytes(
                    _read(validation["stage"] / validation_phase.OUTPUT_PATH)))
                request = private / "expected-request.json"
                write_canonical_json(request, {
                    "sdkVersion": receipt["productVersion"],
                    "packageStage": str(trees["package"]),
                    "packageReceipt": str(files["packageReceipt"]),
                    "validationStage": str(validation["stage"]),
                    "validationReceipt": str(validation["receiptPath"]),
                    "releaseAarSha256": validation_content["releaseAarSha256"],
                    "bundledRuntimeSha256": validation_content["bundledRuntimeSha256"],
                })
                expected_path = private / "expected-content.json"
                expected = write_android_metadata_content(request, expected_path)
                _worker(original, receipt, context, validation_content)
                _replan(root, receipt, validation["receipt"])
                if (_read(stage / OUTPUT_PATH) != canonical_json_bytes(expected)
                        or _read(expected_path) != canonical_json_bytes(expected)):
                    raise ValueError("Original Android metadata content differs from full replay")
                retained[private] = regular_file_inventory(private, allow_empty=True)
                result = {"stage": stage, "receiptPath": selected,
                    "receiptBytes": raw, "receipt": receipt,
                    "original": original, "capture": capture, "transport": transport}
                result_bytes = _result_view(result)
                unchanged()
                yield result
                unchanged()
            unchanged()
        finally:
            unchanged()
            if _read(selected) != raw:
                raise ValueError("Selected original Android metadata receipt changed")
