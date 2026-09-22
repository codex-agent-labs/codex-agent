"""Select Android metadata originals from authenticated retained state.

The caller must independently authenticate ``authenticated_state_root`` and
the elected build/receipt/object triple before invocation.  This adapter does
not authenticate a catalog or treat its carrier as trust: it verifies the
exact retained index, shard, producer and validation edge, then uses locator
fields only to invoke the existing official-gated policy producer.
"""

import os
from pathlib import Path
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse
from products.inventory import (
    _directory_inventory, _open_directory, _stat_identity,
    canonical_json_bytes, load_canonical_json_bytes, publish_regular_tree,
    read_regular_file_bytes,
    regular_file_inventory, require_exact_keys, require_integer,
    require_regular_directory, require_sha256, sha256_bytes,
)
from products.plan import _upstream_record
from products.receipt import validate_phase_receipt
from products.registry import PhaseInstanceId
from products.restore import verify_phase_shard
from products import sdk_android_validation_phase as validation_phase
from products.sdk_package import _require_capability_output_separate
from products.sdk_validation_inputs import _request_inventory
from products.signing_isolation import require_no_signing_secret
from sdk_android_metadata_policy import (
    POLICY_NAME, create_sdk_android_metadata_policy,
)
from sdk_metadata_evidence import load_sdk_metadata_evidence


_METADATA = PhaseInstanceId("sdk", "sdk-android", "metadata", "android")
_VALIDATION_IDENTITY = ("sdk", "sdk-android", "validation", "android")
_LIMIT = 16 * 1024 * 1024


def _read(path):
    return read_regular_file_bytes(
        Path(path), max_bytes=_LIMIT, reject_symlink_parents=True)


def _directory(path, label):
    path = Path(path).absolute()
    if path.resolve(strict=True) != path:
        raise ValueError(f"{label} must be normalized and non-symbolic")
    return require_regular_directory(path, label)


def _file(path, label):
    path = Path(path).absolute()
    if path.resolve(strict=True) != path:
        raise ValueError(f"{label} must be normalized and non-symbolic")
    _read(path)
    return path


def create_selected_sdk_android_metadata_policy(
        plan, authenticated_state_root, destination, *, expected_build_key,
        metadata_receipt_sha256, metadata_object_sha256,
        trusted_workflow_sha, trusted_android_workflow_sha,
        expected_original_run_id, expected_original_run_attempt,
        package_stage, package_receipt, binary_stage, binary_receipt,
        compatibility_request, binary_contract_evidence,
        trusted_source_commit, trusted_source_tree, original_context,
        tooling_evidence, tooling_public_key, java_executable,
        apkanalyzer_executable, required_trust_domain, repository_root,
        environ=None, token, tooling_keyring=None, tooling_keys_directory=None):
    """Create policy for one caller-authenticated local Android election.

    The retained metadata carrier supplies only exact bytes and artifact
    locator fields.  Caller workflow/source pins and the original run identity
    remain explicit, and the delegated producer re-observes and fully verifies
    the nested Android validation before publishing any descriptor.
    """
    environment = os.environ if environ is None else environ
    require_no_signing_secret(environment)
    if environment is not os.environ:
        require_no_signing_secret(os.environ)
    expected_build_key = require_sha256(
        expected_build_key, "Elected Android metadata build key")
    metadata_receipt_sha256 = require_sha256(
        metadata_receipt_sha256, "Elected Android metadata receipt")
    metadata_object_sha256 = require_sha256(
        metadata_object_sha256, "Elected Android metadata object")

    if (tooling_keyring is None) != (tooling_keys_directory is None):
        raise ValueError("Android metadata tooling keyring and directory must be paired")
    state = _directory(authenticated_state_root, "Authenticated Android metadata state")
    carriers = _directory(
        state / "sdk-metadata-evidence", "Authenticated metadata evidence carriers")
    repository = _directory(repository_root, "Android metadata repository")
    trees = {
        "packageStage": _directory(package_stage, "Android package stage"),
        "binaryStage": _directory(binary_stage, "Android binary stage"),
        "toolingEvidence": _directory(tooling_evidence, "Android tooling evidence"),
    }
    files = {
        "plan": _file(plan, "Android metadata plan"),
        "packageReceipt": _file(package_receipt, "Android package receipt"),
        "binaryReceipt": _file(binary_receipt, "Android binary receipt"),
        "compatibilityRequest": _file(
            compatibility_request, "Android compatibility request"),
        "toolingPublicKey": _file(tooling_public_key, "Android tooling public key"),
        "javaExecutable": _file(java_executable, "Android Java executable"),
        "apkanalyzerExecutable": _file(
            apkanalyzer_executable, "Android apkanalyzer executable"),
    }
    if tooling_keyring is not None:
        files["toolingKeyring"] = _file(tooling_keyring, "Android tooling keyring")
        trees["toolingKeysDirectory"] = _directory(
            tooling_keys_directory, "Android tooling keys directory")
    contract_trees, contract_files = validation_phase._contract_sources(
        binary_contract_evidence)
    trees.update({"contract:" + name: _directory(path, name)
                  for name, path in contract_trees.items()})
    files.update({"contract:" + name: _file(path, name)
                  for name, path in contract_files.items()})
    request_inventory = _request_inventory(files["compatibilityRequest"])
    files.update({f"compatibility:{index}": _file(path, "Compatibility input")
                  for index, path in enumerate(request_inventory)})
    protected = [state, repository, *trees.values(), *files.values()]
    output = Path(destination).absolute()
    def output_safe():
        _require_capability_output_separate(output, protected)
        if (output.exists() or output.is_symlink()
                or output.resolve(strict=False) != output):
            raise ValueError("Selected Android metadata policy destination must be fresh")

    output_safe()
    before = regular_file_inventory(state, allow_empty=True)
    tree_before = {name: regular_file_inventory(path, allow_empty=True)
                   for name, path in trees.items()}
    file_before = {name: _read(path) for name, path in files.items()}
    validated = product_reuse._validate_plan(files["plan"], repository)
    checkout_commit = validated["validationCommit"]
    checkout_tree = validated["validationTree"]
    matches = []
    for carrier in sorted(carriers.iterdir()):
        carrier = _directory(carrier, "Retained metadata evidence carrier")
        records = load_sdk_metadata_evidence(carrier)
        for record in records:
            if ((record["component"], record["phase"], record["target"])
                    == ("sdk-android", "metadata", "android")
                    and record["receiptSha256"] == metadata_receipt_sha256):
                matches.append((carrier, record))
    if len(matches) != 1:
        raise ValueError("Authenticated state lacks one exact elected Android metadata carrier")
    carrier, record = matches[0]
    metadata_receipt_path = carrier / record["receipt"]
    metadata_raw = _read(metadata_receipt_path)
    metadata = validate_phase_receipt(load_canonical_json_bytes(metadata_raw))
    if (tuple(metadata[name] for name in ("product", "component", "phase", "target"))
            != (_METADATA.product, _METADATA.component, _METADATA.phase, _METADATA.target)
            or sha256_bytes(metadata_raw) != metadata_receipt_sha256
            or metadata["buildKey"] != expected_build_key):
        raise ValueError("Retained Android metadata receipt differs from the authenticated election")

    metadata_capture = _directory(
        carrier / record["capture"], "Retained Android metadata capture")
    shard = verify_phase_shard(metadata_capture / "original/shard", _METADATA)
    if (shard["receiptBytes"] != metadata_raw
            or shard["receiptSha256"] != metadata_receipt_sha256
            or shard["objectSha256"] != metadata_object_sha256
            or shard["buildKey"] != expected_build_key):
        raise ValueError("Retained Android metadata object differs from the authenticated election")
    if shard["receipt"]["producer"] != metadata["producer"]:
        raise ValueError("Retained Android metadata producer differs from its indexed receipt")
    metadata_transport = require_exact_keys(load_canonical_json_bytes(_read(
        metadata_capture / "capture-transport.json")), {
            "artifact", "captureProducer", "metadataReceiptSha256", "observed",
        }, "Retained Android metadata transport")
    if (metadata_transport["captureProducer"] != metadata["producer"]
            or metadata_transport["metadataReceiptSha256"] != metadata_receipt_sha256):
        raise ValueError("Retained Android metadata transport differs from its exact receipt")

    original = metadata_capture / "original"
    validation_capture = _directory(
        original / "originals/validation", "Retained original Android validation")
    validation_receipt_path = (
        original / "inputs/sdk-sdk-android-validation-android/phase-receipt.json")
    validation_raw = _read(validation_receipt_path)
    validation = validate_phase_receipt(load_canonical_json_bytes(validation_raw))
    if (tuple(validation[name] for name in ("product", "component", "phase", "target"))
            != _VALIDATION_IDENTITY
            or validation["productVersion"] != metadata["productVersion"]
            or _upstream_record(validation) not in metadata["inputs"]["upstreamArtifacts"]):
        raise ValueError("Retained Android validation is not the metadata receipt's exact upstream")

    transport = require_exact_keys(load_canonical_json_bytes(_read(
        validation_capture / "capture-transport.json")), {
            "artifact", "captureProducer", "observed", "validationReceiptSha256",
        }, "Retained Android validation transport")
    if (transport["captureProducer"] != validation["producer"]
            or transport["validationReceiptSha256"] != sha256_bytes(validation_raw)):
        raise ValueError("Retained Android validation locator differs from its exact receipt")
    artifact = transport["artifact"]
    if type(artifact) is not dict:
        raise ValueError("Retained Android validation artifact locator is invalid")
    artifact_id = require_integer(
        artifact.get("id"), "Retained Android validation artifact ID", 1)
    artifact_sha256 = require_sha256(
        artifact.get("digest"), "Retained Android validation artifact digest")
    authority = canonical_json_bytes({
        "buildKey": expected_build_key,
        "receiptSha256": metadata_receipt_sha256,
        "objectSha256": metadata_object_sha256,
        "trustedWorkflowSha": trusted_workflow_sha,
        "trustedAndroidWorkflowSha": trusted_android_workflow_sha,
        "expectedOriginalRunId": expected_original_run_id,
        "expectedOriginalRunAttempt": expected_original_run_attempt,
        "trustedSourceCommit": trusted_source_commit,
        "trustedSourceTree": trusted_source_tree,
        "binaryContractEvidence": binary_contract_evidence,
        "originalContext": original_context,
        "requiredTrustDomain": required_trust_domain,
    })

    def unchanged():
        require_no_signing_secret(environment)
        if environment is not os.environ:
            require_no_signing_secret(os.environ)
        if (regular_file_inventory(state, allow_empty=True) != before
                or canonical_json_bytes({
                    "buildKey": expected_build_key,
                    "receiptSha256": metadata_receipt_sha256,
                    "objectSha256": metadata_object_sha256,
                    "trustedWorkflowSha": trusted_workflow_sha,
                    "trustedAndroidWorkflowSha": trusted_android_workflow_sha,
                    "expectedOriginalRunId": expected_original_run_id,
                    "expectedOriginalRunAttempt": expected_original_run_attempt,
                    "trustedSourceCommit": trusted_source_commit,
                    "trustedSourceTree": trusted_source_tree,
                    "binaryContractEvidence": binary_contract_evidence,
                    "originalContext": original_context,
                    "requiredTrustDomain": required_trust_domain,
                }) != authority
                or any(regular_file_inventory(path, allow_empty=True) != tree_before[name]
                       for name, path in trees.items())
                or any(_read(path) != file_before[name] for name, path in files.items())
                or _request_inventory(files["compatibilityRequest"]) != request_inventory
                or product_reuse._git_value(
                    repository, "rev-parse", "HEAD^{commit}") != checkout_commit
                or product_reuse._git_value(
                    repository, "rev-parse", "HEAD^{tree}") != checkout_tree):
            raise ValueError(
                "Authenticated Android metadata election or caller inputs changed during policy creation")

    published_identity = published_inventory = descriptor_bytes = None
    try:
        unchanged()
        with tempfile.TemporaryDirectory(prefix="selected-android-metadata-policy-") as temporary:
            private_output = Path(temporary).resolve() / "policy"
            _require_capability_output_separate(private_output, [output, *protected])
            descriptor = create_sdk_android_metadata_policy(
                plan, carrier, validation_receipt_path, validation_capture, private_output,
                validation_artifact_id=artifact_id,
                validation_artifact_sha256=artifact_sha256,
                trusted_workflow_sha=trusted_workflow_sha,
                trusted_android_workflow_sha=trusted_android_workflow_sha,
                expected_original_run_id=expected_original_run_id,
                expected_original_run_attempt=expected_original_run_attempt,
                package_stage=package_stage, package_receipt=package_receipt,
                binary_stage=binary_stage, binary_receipt=binary_receipt,
                compatibility_request=compatibility_request,
                binary_contract_evidence=binary_contract_evidence,
                trusted_source_commit=trusted_source_commit,
                trusted_source_tree=trusted_source_tree,
                original_context=original_context,
                tooling_evidence=tooling_evidence,
                tooling_public_key=tooling_public_key,
                java_executable=java_executable,
                apkanalyzer_executable=apkanalyzer_executable,
                required_trust_domain=required_trust_domain,
                repository_root=repository_root, environ=environment, token=token,
                tooling_keyring=tooling_keyring,
                tooling_keys_directory=tooling_keys_directory)
            descriptor_bytes = canonical_json_bytes(descriptor)
            private_inventory = regular_file_inventory(private_output)
            if _read(private_output / POLICY_NAME) != descriptor_bytes:
                raise ValueError("Private selected Android metadata policy is inconsistent")
            unchanged()
            output_safe()
            publish_regular_tree(private_output, output)
            published = _open_directory(output, "Selected Android metadata policy")
            try:
                published_identity = _stat_identity(os.fstat(published))
                published_inventory = _directory_inventory(published)
            finally:
                os.close(published)
            if (regular_file_inventory(output) != private_inventory
                    or _read(output / POLICY_NAME) != descriptor_bytes):
                raise ValueError("Published selected Android metadata policy is inconsistent")
        unchanged()
        published = _open_directory(output, "Selected Android metadata policy final check")
        try:
            if (_stat_identity(os.fstat(published)) != published_identity
                    or _directory_inventory(published) != published_inventory
                    or _read(output / POLICY_NAME) != descriptor_bytes):
                raise ValueError("Selected Android metadata policy changed after publication")
        finally:
            os.close(published)
        return descriptor
    except BaseException as error:
        try:
            unchanged()
        except BaseException as mutation:
            raise mutation from error
        raise
