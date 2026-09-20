"""Join existing Apple validation content gates; never grant producer/host trust."""

from pathlib import Path
import tempfile

from .inventory import read_regular_file_bytes, regular_file_inventory, snapshot_regular_tree
from .sdk_apple_content import verify_sdk_apple_validation_binding_content
from .sdk_apple_device_evidence import verify_apple_device_evidence
from .sdk_apple_simulator_replay import verify_sdk_apple_simulator_execution
from .sdk_apple_toolchain_evidence import verify_apple_toolchain_evidence
from .sdk_apple_validation_source import (
    verify_apple_validation_sources, read_apple_validation_simulator_policy,
)


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
