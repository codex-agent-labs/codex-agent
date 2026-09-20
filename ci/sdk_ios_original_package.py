"""Recover one original iOS package through the existing complete content gates."""

from contextlib import contextmanager
from pathlib import Path
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse
from products.inventory import (
    canonical_json_bytes, git_product_versions, load_canonical_json_bytes,
    read_regular_file_bytes, regular_file_inventory, require_exact_keys, sha256_bytes, snapshot_regular_tree,
)
from products.receipt import validate_phase_receipt, verify_output_manifest_identity
from products.contract_attestation import CONTRACT_EXECUTION_CLOSURE_DIRECTORY
from products.registry import PhaseInstanceId
from products.restore import PHASE_PLAN_KEYS, restore_object, verify_phase_shard
from products.sdk_apple_original_inputs import verified_apple_original_inputs
from products.sdk_apple_content import _input_inventory
from products.sdk_apple_package_execution import verify_apple_package_execution_context
from products.sdk_inputs import REQUEST_NAME
from products.sdk_package import _require_capability_output_separate, verify_sdk_package_inputs
from products.sdk_release_selection import sdk_runtime_source


_INSTANCE = PhaseInstanceId("sdk", "sdk-ios", "package", "ios")
_LIMIT = 16 * 1024 * 1024


@contextmanager
def verified_original_ios_package(plan, package_receipt_path, *, artifact_id, artifact_sha256,
        trusted_workflow_sha, keyring, keys_directory, repository_root, environ, token,
        tooling_evidence, tooling_public_key, java_executable, policy_revision, required_trust_domain,
        tooling_keyring=None, tooling_keys_directory=None):
    """Independently capture original uploads, then use the common content gate."""
    with _verified_ios_package(plan, package_receipt_path, package_capture=None, sdk_capture=None,
            artifact_id=artifact_id, artifact_sha256=artifact_sha256, trusted_workflow_sha=trusted_workflow_sha,
            keyring=keyring, keys_directory=keys_directory, repository_root=repository_root, environ=environ, token=token,
            tooling_evidence=tooling_evidence, tooling_public_key=tooling_public_key, java_executable=java_executable,
            policy_revision=policy_revision, required_trust_domain=required_trust_domain,
            tooling_keyring=tooling_keyring, tooling_keys_directory=tooling_keys_directory) as value:
        yield value


@contextmanager
def verified_retained_ios_package(plan, package_receipt_path, *, package_capture, sdk_capture,
        keyring, keys_directory, repository_root, tooling_evidence, tooling_public_key,
        java_executable, policy_revision, required_trust_domain, tooling_keyring=None, tooling_keys_directory=None):
    """Replay caller-authenticated retained captures privately without network.

    The caller must authenticate the enclosing upload or catalog and selected
    original receipt. Stored transport/observation records grant no authority.
    This content-only entrypoint never observes CI, signs, or reissues receipts.
    """
    with _verified_ios_package(plan, package_receipt_path,
            package_capture=Path(package_capture), sdk_capture=Path(sdk_capture),
            keyring=keyring, keys_directory=keys_directory, repository_root=repository_root,
            tooling_evidence=tooling_evidence, tooling_public_key=tooling_public_key, java_executable=java_executable,
            policy_revision=policy_revision, required_trust_domain=required_trust_domain,
            tooling_keyring=tooling_keyring, tooling_keys_directory=tooling_keys_directory) as value:
        yield value


@contextmanager
def _verified_ios_package(plan, package_receipt_path, *, package_capture, sdk_capture,
        keyring, keys_directory, repository_root, tooling_evidence, tooling_public_key,
        java_executable, policy_revision, required_trust_domain, tooling_keyring=None, tooling_keys_directory=None,
        artifact_id=None, artifact_sha256=None, trusted_workflow_sha=None, environ=None, token=None):
    """Yield temporary verified originals; consumers publish only after clean exit.

    This joins observed original package execution with content/input verification.
    It does not grant iOS binary compiler, XCTest, simulator or final validation
    acceptance, and never generates a replacement receipt or product bytes.
    """
    root = Path(repository_root).resolve(strict=True)
    if (package_capture is None) != (sdk_capture is None):
        raise ValueError("Retained Apple package and SDK captures must be supplied together")
    retained = {} if package_capture is None else {"package": Path(package_capture), "sdk": Path(sdk_capture)}
    if retained:
        _require_capability_output_separate(retained["package"], retained["sdk"])
    retained_before = {name: _input_inventory(path, allow_empty=True) for name, path in retained.items()}

    def retained_unchanged():
        if any(_input_inventory(path, allow_empty=True) != retained_before[name] for name, path in retained.items()):
            raise ValueError("Original retained Apple package inputs changed during use")

    plan, package_receipt_path = Path(plan), Path(package_receipt_path)
    plan_bytes = read_regular_file_bytes(plan, max_bytes=_LIMIT, reject_symlink_parents=True)
    receipt_bytes = read_regular_file_bytes(package_receipt_path, max_bytes=_LIMIT, reject_symlink_parents=True)
    keyring_bytes = read_regular_file_bytes(Path(keyring), max_bytes=64 * 1024, reject_symlink_parents=True)
    keys_before = regular_file_inventory(Path(keys_directory), allow_empty=True)
    receipt = validate_phase_receipt(load_canonical_json_bytes(receipt_bytes))
    if tuple(receipt[name] for name in ("product", "component", "phase", "target")) != (
            "sdk", "sdk-ios", "package", "ios"):
        raise ValueError("Original Apple package requires an exact selected package receipt")
    producer = receipt["producer"]
    with tempfile.TemporaryDirectory(prefix="original-ios-package-") as temporary:
        private = Path(temporary).resolve()
        _require_capability_output_separate(private, [root, plan, package_receipt_path, Path(keyring),
            Path(keys_directory), Path(tooling_evidence), Path(tooling_public_key), Path(java_executable),
            *retained.values(),
            *(Path(path) for path in (tooling_keyring, tooling_keys_directory) if path is not None)])
        capture = private / "package-capture"
        if retained:
            snapshot_regular_tree(retained["package"], capture, allow_empty=True)
            if _input_inventory(capture, allow_empty=True) != retained_before["package"]:
                raise ValueError("Retained Apple package changed during private capture")
            retained_unchanged()
            product_reuse.verify_retained_sdk_ios_upload(capture, receipt_bytes)
            if _input_inventory(capture, allow_empty=True) != retained_before["package"]:
                raise ValueError("Retained Apple package changed during archive verification")
            retained_unchanged()
        else:
            product_reuse.capture_sdk_ios_package_upload(plan, capture, package_receipt_path=package_receipt_path,
                artifact_id=artifact_id, artifact_sha256=artifact_sha256, trusted_workflow_sha=trusted_workflow_sha,
                repository_root=root, environ=environ, token=token)
        capture_before = regular_file_inventory(capture, allow_empty=True)
        original = capture / "original"
        shard = verify_phase_shard(original / "shard", _INSTANCE)
        if shard["receiptBytes"] != receipt_bytes:
            raise ValueError("Original Apple uploaded package differs from the selected receipt")
        stage = private / "package-stage"
        restored = restore_object(original / "shard" / shard["objectPath"], stage,
            build_key=shard["buildKey"], receipt_sha256=shard["receiptSha256"], object_sha256=shard["objectSha256"])
        if restored["receiptBytes"] != receipt_bytes:
            raise ValueError("Original Apple restored package receipt changed")
        stage_before = regular_file_inventory(stage)
        selected_receipt = private / "package-receipt.json"
        selected_receipt.write_bytes(receipt_bytes)
        historical_plan = original / "original-plan/impact-plan.json"
        validated = product_reuse._validate_plan(historical_plan, root, expected_revision=producer["commit"])
        if validated.get("remoteBuildAuthorized") is not True or validated.get("event") == "workflow_dispatch":
            raise ValueError("Original Apple package requires an authorized historical plan")
        if product_reuse._consumer(validated, {"GITHUB_RUN_ID": str(producer["runId"]),
                "GITHUB_RUN_ATTEMPT": str(producer["runAttempt"])})["producer"] != producer:
            raise ValueError("Original Apple impact plan differs from its package producer")
        inputs = original / "inputs"
        if (load_canonical_json_bytes(read_regular_file_bytes(inputs / "producer.json")) != producer
                or load_canonical_json_bytes(read_regular_file_bytes(inputs / "phase-plan.json")) !=
                   {name: receipt[name] for name in PHASE_PLAN_KEYS}):
            raise ValueError("Original Apple elected phase differs from its package receipt")

        def predecessor(product, component, phase, target):
            directory = inputs / "-".join((product, component, phase, target))
            path = directory / "phase-receipt.json"
            value = validate_phase_receipt(load_canonical_json_bytes(read_regular_file_bytes(path)))
            if tuple(value[name] for name in ("product", "component", "phase", "target")) != (
                    product, component, phase, target):
                raise ValueError("Original Apple predecessor identity differs")
            manifest = verify_output_manifest_identity(directory / "stage", product, component, phase,
                                                       target, value["productVersion"])
            if manifest["outputs"] != value["outputs"]:
                raise ValueError("Original Apple predecessor stage differs from its receipt")
            return directory / "stage", path, value

        binary_stage, binary_receipt, _ = predecessor("sdk", "sdk-ios", "binary", "ios")
        _, contract_binary_receipt, _ = predecessor("contract", "contract", "binary", "common")
        contract_stage, contract_receipt, contract = predecessor("contract", "contract", "metadata", "common")
        payloads = [record["sha256"] for record in contract["outputs"] if record["kind"] == "contract-bundle"]
        if len(payloads) != 1:
            raise ValueError("Original Apple Contract metadata requires exactly one payload")
        descriptor_path = original / "apple-package-execution.json"
        descriptor = load_canonical_json_bytes(read_regular_file_bytes(descriptor_path, max_bytes=_LIMIT,
                                                                       reject_symlink_parents=True))
        if type(descriptor) is not dict:
            raise ValueError("Original Apple execution descriptor must be an object")
        locator = require_exact_keys(descriptor.get("sdkInputsArtifact"), {"artifactId", "artifactSha256"},
                                     "Original Apple SDK-input locator")
        descriptor = verify_apple_package_execution_context(descriptor_path,
            capture_directory=original / "package-execution", package_receipt=selected_receipt,
            binary_receipt=binary_receipt, contract_binary_receipt=contract_binary_receipt,
            contract_metadata_receipt=contract_receipt, producer=producer,
            sdk_compatibility=stage / "outputs/evidence/sdk-compatibility.json",
            sdk_inputs_artifact_id=locator["artifactId"], sdk_inputs_artifact_sha256=locator["artifactSha256"])
        versions = git_product_versions(root, producer["commit"])
        source = sdk_runtime_source(root, producer["commit"],
            instances=product_reuse._dependency_closure((_INSTANCE,)),
            runtime_version=versions["runtime-release"], sdk_version=versions["sdk"]) or "current-runtime"
        sdk_capture = private / "sdk-capture"
        if retained:
            snapshot_regular_tree(retained["sdk"], sdk_capture, allow_empty=True)
            if _input_inventory(sdk_capture, allow_empty=True) != retained_before["sdk"]:
                raise ValueError("Retained Apple SDK inputs changed during private capture")
            retained_unchanged()
            transport = require_exact_keys(load_canonical_json_bytes(read_regular_file_bytes(
                sdk_capture / "capture-transport.json", max_bytes=_LIMIT, reject_symlink_parents=True)),
                {"artifact", "captureProducer", "observed", "sdkRuntimeSource", "packageReceiptSha256"},
                "Retained Apple SDK transport")
            product_reuse._verify_retained_sdk_upload_archive(sdk_capture, transport["artifact"],
                extra_roots=("original-package-receipt.json",))
            artifact = transport["artifact"]
            if (artifact["id"] != locator["artifactId"] or artifact["digest"] != locator["artifactSha256"]
                    or artifact.get("name") != f"codex-agent-sdk-inputs-{producer['tree']}-attempt-{producer['runAttempt']}"
                    or transport["captureProducer"] != producer or transport["sdkRuntimeSource"] != source
                    or transport["packageReceiptSha256"] != sha256_bytes(receipt_bytes)
                    or read_regular_file_bytes(sdk_capture / "original-package-receipt.json") != receipt_bytes
                    or read_regular_file_bytes(sdk_capture / "plan/impact-plan.json") != read_regular_file_bytes(historical_plan)):
                raise ValueError("Retained Apple SDK inputs differ from their original package binding")
            sdk_original = sdk_capture / "original"
            expected_roots = ({"runtime-original", "current-contract", "sdk-inputs", "selection.json", "transport.json"}
                              if source == "released-default" else {"runtime-capture", "sdk-inputs"})
            if {path.name for path in sdk_original.iterdir()} != expected_roots:
                raise ValueError("Retained Apple SDK inputs differ from the selected source layout")
            if source == "released-default":
                selection = product_reuse._canonical_control(sdk_original / "selection.json", "Retained SDK selection")
                current = product_reuse._canonical_control(sdk_original / "transport.json", "Retained SDK transport")
                if (selection.get("source") != source or not isinstance(current.get("consumer"), dict)
                        or current["consumer"].get("producer") != producer):
                    raise ValueError("Retained Apple SDK selection differs from its original producer")
            elif read_regular_file_bytes(sdk_original / "runtime-capture/plan/impact-plan.json") != read_regular_file_bytes(historical_plan):
                raise ValueError("Retained Apple SDK original plan differs from its package plan")
            if _input_inventory(sdk_capture, allow_empty=True) != retained_before["sdk"]:
                raise ValueError("Retained Apple SDK inputs changed during archive verification")
            retained_unchanged()
        else:
            product_reuse.capture_sdk_inputs_upload(historical_plan, sdk_capture,
                original_package_receipt_path=selected_receipt, artifact_id=locator["artifactId"],
                artifact_sha256=locator["artifactSha256"], trusted_workflow_sha=trusted_workflow_sha,
                expected_source=source, repository_root=root, environ=environ, token=token)
        sdk_before = regular_file_inventory(sdk_capture, allow_empty=True)
        records = descriptor["captureFiles"]
        binding_digest = next(record["sha256"] for record in records if record["relativePath"] == "input-binding.json")
        event_bytes = canonical_json_bytes({record["relativePath"].removeprefix("events/"):
            record["sha256"].removeprefix("sha256:") for record in records if record["relativePath"].startswith("events/")})
        expected_events = private / "expected-execution-files.json"
        expected_events.write_bytes(event_bytes)

        def unchanged():
            retained_unchanged()
            if (canonical_json_bytes(receipt) != receipt_bytes
                    or read_regular_file_bytes(Path(keyring), max_bytes=64 * 1024, reject_symlink_parents=True) != keyring_bytes
                    or regular_file_inventory(Path(keys_directory), allow_empty=True) != keys_before
                    or read_regular_file_bytes(plan, max_bytes=_LIMIT, reject_symlink_parents=True) != plan_bytes
                    or read_regular_file_bytes(package_receipt_path, max_bytes=_LIMIT, reject_symlink_parents=True) != receipt_bytes
                    or read_regular_file_bytes(selected_receipt) != receipt_bytes
                    or read_regular_file_bytes(expected_events) != event_bytes
                    or regular_file_inventory(capture, allow_empty=True) != capture_before
                    or regular_file_inventory(sdk_capture, allow_empty=True) != sdk_before
                    or regular_file_inventory(stage) != stage_before):
                raise ValueError("Original Apple package recovery inputs changed during use")

        try:
            with verified_apple_original_inputs(sdk_capture, expected_source=source, keyring=keyring,
                    keys_directory=keys_directory, selection_repository_root=root, selection_revision=producer["commit"],
                    expected_contract_payload_sha256=payloads[0]) as joined:
                arguments = joined["sdk"]["arguments"]
                if read_regular_file_bytes(contract_receipt) != read_regular_file_bytes(arguments["contract_metadata_receipt"]):
                    raise ValueError("Original Apple Contract predecessor differs from authenticated SDK inputs")
                signed_binary = (arguments["contract_attestation"].parent / CONTRACT_EXECUTION_CLOSURE_DIRECTORY
                                 / "receipts/binary.json")
                if read_regular_file_bytes(contract_binary_receipt) != read_regular_file_bytes(signed_binary):
                    raise ValueError("Original Apple Contract binary differs from its signed execution closure")
                evidence = {"stageRoot": str(contract_stage), "phaseReceipt": str(contract_receipt),
                    "attestation": str(arguments["contract_attestation"]),
                    "attestationSignature": str(arguments["contract_attestation_signature"]),
                    "publicKey": str(arguments["contract_public_key"]),
                    "expectedTrustDomain": arguments["required_trust_domain"],
                    "keyring": str(arguments["contract_keyring"]), "keysDirectory": str(arguments["contract_keys_directory"])}
                policy = dict(repository=root, tooling_evidence=Path(tooling_evidence),
                    tooling_public_key=Path(tooling_public_key), java_executable=Path(java_executable),
                    policy_revision=policy_revision, required_trust_domain=required_trust_domain,
                    tooling_keyring=tooling_keyring, tooling_keys_directory=tooling_keys_directory,
                    evidence_directory=original / "package-execution/events",
                    execution_binding_file=original / "package-execution/input-binding.json",
                    expected_binding_sha256=binding_digest, expected_execution_files=expected_events)
                verified, raw = verify_sdk_package_inputs(root, stage, selected_receipt,
                    joined["sdk"]["directory"] / REQUEST_NAME, binary_stage_root=binary_stage,
                    binary_receipt_path=binary_receipt, binary_contract_evidence=evidence,
                    apple_original_verification=policy)
                if verified != receipt or raw != receipt_bytes:
                    raise ValueError("Original Apple package gate returned a different receipt")
                unchanged()
                yield {"stage": stage, "receiptPath": selected_receipt, "receipt": receipt,
                       "receiptBytes": receipt_bytes, "original": original, **joined,
                       "packageCapture": capture, "sdkCapture": sdk_capture}
        finally:
            unchanged()
