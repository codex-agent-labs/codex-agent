"""Execute elected Apple validation from authenticated original package inputs.

Raw execution is not canonical phase admission. Full evidence replay and
original binary/host admission must precede any validation receipt.
"""

from pathlib import Path
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse
from products.inventory import load_json_bytes, read_regular_file_bytes, regular_file_inventory, sha256_file
from products.receipt import output_inventory_digest
from products.registry import PhaseInstanceId
from products.restore import verify_object
from products.sdk_apple_validation_source import capture_apple_validation_sources
from products.sdk_apple_validation_evidence import verified_apple_validation_archive
from products.sdk_apple_validation_execution import verify_apple_validation_execution
from products.sdk_apple_validation_content import apple_validation_content
from products.sdk_apple_device_evidence import _original_directory
from sdk_ios_original_package import verified_original_ios_package
from sdk_ios_validation import execute as execute_validation


_EVIDENCE_ROOTS = (
    "canonical", "consumer", "reports", "compiler-raw", "xcframework", "xctest-raw",
    "simulator-raw", "xcresult", "xctest-package", "xctest-products", "device-raw",
    "device-archive", "device-test-application", "device-package", "toolchain",
)


def execute(plan, discovery, state, destination, *, target, expected_build_key,
            package_artifact_id, package_artifact_sha256, trusted_workflow_sha,
            keyring, keys_directory, tooling_evidence, tooling_public_key,
            java_executable, policy_revision, required_trust_domain,
            repository_root, environ, token, tooling_keyring=None, tooling_keys_directory=None):
    """Run and replay elected validation; return content, never mint a receipt.

    Original binary/native-host admission and canonical phase staging remain
    separate requirements. The returned ordinary content dict grants no trust.
    """
    if target not in ("ios-arm64", "ios-simulator-arm64"):
        raise ValueError("SDK iOS validation requires an exact iOS target")
    root = Path(repository_root).resolve(strict=True)
    discovery, state, destination = product_reuse._product_materialization_paths(
        root, discovery, state, destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("SDK iOS validation destination must not exist")
    developer = str(_original_directory(environ.get("DEVELOPER_DIR"), "Selected Apple Developer directory"))
    plan_bytes = read_regular_file_bytes(Path(plan), max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
    tooling = {"evidence": str(Path(tooling_evidence).absolute()),
        "publicKey": str(Path(tooling_public_key).absolute()),
        "javaExecutable": str(Path(java_executable).absolute()),
        "requiredTrustDomain": required_trust_domain,
        "keyring": str(Path(tooling_keyring).absolute()) if tooling_keyring is not None else None,
        "keysDirectory": str(Path(tooling_keys_directory).absolute()) if tooling_keys_directory is not None else None}
    verified = product_reuse._verified_product_state(plan, discovery, state, root, environ, tooling)
    instance = PhaseInstanceId("sdk", "sdk-ios", "validation", target)
    ready = verified.prior_ready_plans.get(instance)
    if ready is None or ready["buildKey"] != expected_build_key:
        raise ValueError("SDK iOS validation is not ready with the elected build key")
    package = PhaseInstanceId("sdk", "sdk-ios", "package", "ios")
    if package not in verified.sources or package not in verified.prior_carrier_phases:
        raise ValueError("SDK iOS validation lacks its selected original package")
    record = verified.prior_carrier_phases[package]
    original = verify_object(verified.sources[package], build_key=record["buildKey"],
        receipt_sha256=record["receiptSha256"], object_sha256=record["objectSha256"])
    version = verified.expected_fixed["versions"]["sdk"]
    if (tuple(original["receipt"][name] for name in ("product", "component", "phase", "target")) !=
            ("sdk", "sdk-ios", "package", "ios") or original["receipt"]["productVersion"] != version):
        raise ValueError("SDK iOS validation package identity/version differs from its selection")

    with tempfile.TemporaryDirectory(prefix="sdk-ios-validation-inputs-") as temporary:
        private = Path(temporary).resolve()
        selected_receipt = private / "package-receipt.json"
        selected_receipt.write_bytes(original["receiptBytes"])
        sources = private / "source"
        capture_apple_validation_sources(root, verified.producer["commit"], sources)
        source_before = regular_file_inventory(sources)

        def unchanged():
            if (read_regular_file_bytes(Path(plan), max_bytes=16 * 1024 * 1024,
                    reject_symlink_parents=True) != plan_bytes
                    or regular_file_inventory(sources) != source_before
                    or read_regular_file_bytes(selected_receipt) != original["receiptBytes"]):
                raise ValueError("SDK iOS validation selected inputs changed during execution")

        try:
            with verified_original_ios_package(plan, selected_receipt,
                    artifact_id=package_artifact_id, artifact_sha256=package_artifact_sha256,
                    trusted_workflow_sha=trusted_workflow_sha, keyring=keyring, keys_directory=keys_directory,
                    repository_root=root, environ=environ, token=token, tooling_evidence=tooling_evidence,
                    tooling_public_key=tooling_public_key, java_executable=java_executable,
                    policy_revision=policy_revision, required_trust_domain=required_trust_domain,
                    tooling_keyring=tooling_keyring, tooling_keys_directory=tooling_keys_directory) as inputs:
                contract = inputs["original"] / "inputs/contract-contract-binary-common"
                contract_receipt = contract / "phase-receipt.json"
                contract_value = product_reuse.validate_phase_receipt(product_reuse._canonical_control(
                    contract_receipt, "Original signed Contract binary receipt"))
                unchanged()
                result = execute_validation(ready, producer=verified.producer, sdk_version=version,
                    package_stage={"stage": inputs["stage"], "receiptPath": inputs["receiptPath"],
                                   "receipt": inputs["receipt"]},
                    contract_binary_stage={"stage": contract / "stage", "receiptPath": contract_receipt,
                                           "receipt": contract_value},
                    sdk_compatibility=inputs["sdk"]["directory"] / "sdk-compatibility.json",
                    test_application=sources / "codex-agent-runtime-ios/apple/TestApp",
                    compiler_consumers=sources / "codex-agent-runtime-ios/apple/CompilerEvidence",
                    repository_root=root, destination=destination, environ=environ)
                canonical = contract / "stage/outputs/evidence"
                api, coverage = canonical / "canonical-api.json", canonical / "canonical-coverage.json"
                compatibility = inputs["sdk"]["directory"] / "sdk-compatibility.json"
                module = root / "codex-agent-runtime-ios"
                execution = module / "build/imported-sdk-validation" / verified.producer["tree"] / target
                with verified_apple_validation_archive(result["evidenceArchive"],
                        expected_sha256=result["evidenceSha256"], expected_roots=_EVIDENCE_ROOTS) as evidence:
                    verify_apple_validation_execution(evidence_root=evidence,
                        product_directory=inputs["stage"] / "outputs/apple", sdk_version=version,
                        sdk_compatibility=compatibility, canonical_api=api, canonical_coverage=coverage,
                        repository=root, source_revision=verified.producer["commit"],
                        original_working_directory=str(module),
                        original_device_work_directory=str(execution / "device-execution"),
                        original_test_application_directory=str(execution / "device-consumer/CodexAgentTestApp"),
                        developer_directory=developer, tooling_evidence=tooling_evidence,
                        tooling_public_key=tooling_public_key, java_executable=java_executable,
                        policy_revision=policy_revision, required_trust_domain=required_trust_domain,
                        tooling_keyring=tooling_keyring, tooling_keys_directory=tooling_keys_directory)
                    content = apple_validation_content(target=target, sdk_version=version,
                        package_outputs_digest=output_inventory_digest(inputs["receipt"]["outputs"]),
                        contract_digest=inputs["sdk"]["compatibility"]["contract"]["digest"],
                        expected_canonical={"apiReportSha256": sha256_file(api).removeprefix("sha256:"),
                                            "coverageReceiptSha256": sha256_file(coverage).removeprefix("sha256:")},
                        binding_receipts={language: load_json_bytes(read_regular_file_bytes(
                            evidence / f"reports/{language}-parity.json", max_bytes=16 * 1024 * 1024,
                            reject_symlink_parents=True)) for language in ("swift", "objective-c")})
        finally:
            unchanged()
    if sha256_file(result["evidenceArchive"]) != result["evidenceSha256"]:
        raise ValueError("SDK iOS validation raw archive changed during context exit")
    return {**result, "content": content}
