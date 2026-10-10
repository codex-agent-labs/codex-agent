"""Join existing Apple validation content gates; never grant producer/host trust."""

from pathlib import Path
import tempfile

from .inventory import (
    canonical_json_bytes, load_json_bytes, read_regular_file_bytes, regular_file_inventory,
    require_sha256, sha256_file, snapshot_regular_tree,
)
from .receipt import output_inventory_digest, validate_phase_receipt, verify_output_manifest_identity
from .sdk_apple_content import verify_sdk_apple_validation_binding_content
from .sdk_apple_device_evidence import verify_apple_device_evidence
from .sdk_apple_simulator_replay import verify_sdk_apple_simulator_execution
from .sdk_apple_toolchain_evidence import verify_apple_toolchain_evidence
from .sdk_apple_validation_source import (
    verify_apple_validation_sources, read_apple_validation_simulator_policy,
)
from .sdk_apple_validation_content import apple_validation_content
from .sdk_apple_validation_evidence import verified_apple_validation_archive


APPLE_VALIDATION_EVIDENCE_ROOTS = (
    "canonical", "consumer", "reports", "compiler-raw", "xcframework", "xctest-raw",
    "simulator-raw", "xcresult", "xctest-package", "xctest-products", "device-raw",
    "device-archive", "device-test-application", "device-package", "toolchain",
)


def verify_apple_validation_stage(
    *, validation_stage: Path, target: str, sdk_version: str, package_stage: Path,
    package_receipt: dict, sdk_compatibility: Path, contract_digest: str,
    canonical_api: Path, canonical_coverage: Path, evidence_archive: Path, context: dict,
    repository: Path, source_revision: str, tooling_evidence: Path, tooling_public_key: Path,
    java_executable: Path, policy_revision: str, required_trust_domain: str,
    tooling_keyring: Path | None = None, tooling_keys_directory: Path | None = None,
) -> dict:
    """Compare canonical stage bytes with complete independently bound replay.

    The caller authenticates the package receipt, Contract, source revision and
    complete outer upload, and strictly validates its external context first.
    This returns ordinary content, never a receipt or phase-admission token.
    """
    if type(target) is not str or target not in ("ios-arm64", "ios-simulator-arm64"):
        raise ValueError("Apple validation stage requires an exact iOS target")
    if type(context) is not dict or context.get("target") != target:
        raise ValueError("Apple validation context differs from the selected stage target")
    require_sha256(contract_digest, "Selected Apple validation Contract digest")
    context_bytes = canonical_json_bytes(context)
    original_context = load_json_bytes(context_bytes)
    receipt = validate_phase_receipt(package_receipt)
    receipt_bytes = canonical_json_bytes(receipt)
    if tuple(receipt[name] for name in ("product", "component", "phase", "target", "productVersion")) != (
            "sdk", "sdk-ios", "package", "ios", sdk_version):
        raise ValueError("Apple validation requires the exact original iOS package receipt")
    validation_stage, package_stage, evidence_archive = map(Path, (validation_stage, package_stage, evidence_archive))
    directories = {path: regular_file_inventory(path) for path in (validation_stage, package_stage)}
    files = {Path(path): read_regular_file_bytes(Path(path), max_bytes=16 * 1024 * 1024,
                                                reject_symlink_parents=True)
             for path in (sdk_compatibility, canonical_api, canonical_coverage)}
    archive_digest = sha256_file(evidence_archive)

    def unchanged():
        if (canonical_json_bytes(context) != context_bytes or canonical_json_bytes(package_receipt) != receipt_bytes
                or sha256_file(evidence_archive) != archive_digest
                or any(regular_file_inventory(path) != inventory for path, inventory in directories.items())
                or any(read_regular_file_bytes(path, max_bytes=16 * 1024 * 1024,
                                               reject_symlink_parents=True) != raw for path, raw in files.items())):
            raise ValueError("Apple validation stage originals changed during complete replay")

    try:
        package = verify_output_manifest_identity(package_stage, "sdk", "sdk-ios", "package", "ios", sdk_version)
        if package["outputs"] != receipt["outputs"]:
            raise ValueError("Apple validation package manifest differs from its original receipt")
        manifest = verify_output_manifest_identity(validation_stage, "sdk", "sdk-ios", "validation", target, sdk_version)
        content_path = "outputs/validation/apple-validation.json"
        if (len(manifest["outputs"]) != 1 or manifest["outputs"][0]["kind"] != "apple-validation-content"
                or manifest["outputs"][0]["relativePath"] != content_path):
            raise ValueError("Apple validation stage must contain only its canonical content output")
        with verified_apple_validation_archive(evidence_archive,
                expected_sha256=original_context["evidenceSha256"],
                expected_roots=APPLE_VALIDATION_EVIDENCE_ROOTS) as evidence:
            verify_apple_validation_execution(
                evidence_root=evidence, product_directory=package_stage / "outputs/apple", sdk_version=sdk_version,
                sdk_compatibility=sdk_compatibility, canonical_api=canonical_api, canonical_coverage=canonical_coverage,
                repository=repository, source_revision=source_revision,
                original_working_directory=original_context["originalWorkingDirectory"],
                original_device_work_directory=original_context["originalDeviceWorkDirectory"],
                original_test_application_directory=original_context["originalTestApplicationDirectory"],
                developer_directory=original_context["developerDirectory"], tooling_evidence=tooling_evidence,
                tooling_public_key=tooling_public_key, java_executable=java_executable, policy_revision=policy_revision,
                required_trust_domain=required_trust_domain, tooling_keyring=tooling_keyring,
                tooling_keys_directory=tooling_keys_directory,
            )
            content = apple_validation_content(target=target, sdk_version=sdk_version,
                package_outputs_digest=output_inventory_digest(package["outputs"]), contract_digest=contract_digest,
                expected_canonical={"apiReportSha256": sha256_file(Path(canonical_api)).removeprefix("sha256:"),
                                    "coverageReceiptSha256": sha256_file(Path(canonical_coverage)).removeprefix("sha256:")},
                binding_receipts={language: load_json_bytes(read_regular_file_bytes(
                    evidence / f"reports/{language}-parity.json", max_bytes=16 * 1024 * 1024,
                    reject_symlink_parents=True)) for language in ("swift", "objective-c")})
            if read_regular_file_bytes(validation_stage / content_path, max_bytes=16 * 1024 * 1024,
                                       reject_symlink_parents=True) != canonical_json_bytes(content):
                raise ValueError("Apple validation staged content differs from complete evidence replay")
    finally:
        unchanged()
    return content


def verify_apple_validation_execution(
    *, evidence_root: Path, product_directory: Path, sdk_version: str,
    sdk_compatibility: Path, canonical_api: Path, canonical_coverage: Path,
    repository: Path, source_revision: str, original_working_directory: str,
    original_device_work_directory: str, original_test_application_directory: str,
    developer_directory: str, tooling_evidence: Path, tooling_public_key: Path,
    java_executable: Path, policy_revision: str, required_trust_domain: str,
    tooling_keyring: Path | None = None, tooling_keys_directory: Path | None = None,
) -> None:
    """Verify every raw content family before any caller emits semantic content.

    The caller must authenticate the original archive/producer, selected package,
    Contract files, source revision and original execution directories. This
    function does not substitute for original binary/native-host admission.
    No receipt, deterministic product or acceptance token is produced here.
    """
    root = Path(evidence_root)
    if not root.is_absolute() or root.resolve(strict=True) != root:
        raise ValueError("Apple validation evidence must be absolute, normalized and non-symbolic")
    directories = {root: regular_file_inventory(root, allow_empty=True),
                   Path(product_directory): regular_file_inventory(Path(product_directory))}
    files = {Path(path): read_regular_file_bytes(Path(path), max_bytes=16 * 1024 * 1024,
                                               reject_symlink_parents=True)
             for path in (sdk_compatibility, canonical_api, canonical_coverage)}
    tooling = dict(repository=repository, tooling_evidence=tooling_evidence,
        tooling_public_key=tooling_public_key, java_executable=java_executable,
        policy_revision=policy_revision, required_trust_domain=required_trust_domain,
        tooling_keyring=tooling_keyring, tooling_keys_directory=tooling_keys_directory)

    try:
        sources = verify_apple_validation_sources(repository, source_revision, root)
        simulator = read_apple_validation_simulator_policy(repository, source_revision)
        with tempfile.TemporaryDirectory(prefix="apple-validation-consumers-") as temporary:
            consumers = Path(temporary).resolve() / "consumer"
            snapshot_regular_tree(root / "consumer", consumers)
            verify_sdk_apple_validation_binding_content(
                product_directory=product_directory, evidence_directory=root, sdk_version=sdk_version,
                expected_sdk_compatibility=sdk_compatibility, canonical_api=canonical_api,
                canonical_coverage=canonical_coverage, consumer_source_directory=consumers, **tooling)
        verify_sdk_apple_simulator_execution(evidence_directory=root,
            expected_runtime_name=simulator["runtimeName"],
            expected_device_type_identifier=simulator["deviceTypeIdentifier"],
            original_working_directory=original_working_directory, **tooling)
        # The complete binding gate above compared device-package bytes with the
        # independently selected product, so this inventory is now content-bound.
        verify_apple_device_evidence(root, original_work_directory=original_device_work_directory,
            original_test_application_directory=original_test_application_directory,
            developer_directory=developer_directory,
            expected_test_application_inventory=sources["testApplicationInventory"],
            expected_package_inventory=regular_file_inventory(root / "device-package"))
        verify_apple_toolchain_evidence(root, expected_toolchain=sources["toolchain"],
                                       original_working_directory=original_working_directory)
    finally:
        if (any(regular_file_inventory(path, allow_empty=path == root) != expected
                for path, expected in directories.items())
                or any(read_regular_file_bytes(path, max_bytes=16 * 1024 * 1024,
                                              reject_symlink_parents=True) != expected
                       for path, expected in files.items())):
            raise ValueError("Apple validation inputs changed during complete evidence verification")
