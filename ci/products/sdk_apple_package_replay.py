"""Authenticated-tooling adapter for retained original Apple package replay."""

from pathlib import Path
import tempfile
from typing import Any

from .inventory import require_semver, require_sha256
from .sdk_apple_content import _verify_sdk_apple_with_tooling
from .sdk_apple_package_source import capture_apple_package_sources


def verify_sdk_apple_original_package_content(
    *, product_directory: Path, binary_frameworks: Path, sdk_version: str,
    expected_sdk_compatibility: Path, source_revision: str,
    evidence_directory: Path, execution_binding_file: Path,
    expected_binding_sha256: str, expected_execution_files: Path,
    repository: Path, tooling_evidence: Path, tooling_public_key: Path,
    java_executable: Path, policy_revision: str, required_trust_domain: str,
    tooling_keyring: Path | None = None, tooling_keys_directory: Path | None = None,
) -> list[dict[str, Any]]:
    """Replay privately copied original bytes and return only product inventory.

    The caller authenticates the binding digest and execution-file inventory as
    independent members of one outer original closure. This adapter never derives
    either expectation from the supplied evidence and grants no receipt, producer,
    host, or phase authority.
    """
    require_semver(sdk_version, "Apple SDK version")
    require_sha256(expected_binding_sha256, "Original Apple execution binding digest")
    with tempfile.TemporaryDirectory(prefix="sdk-apple-original-package-source-") as temporary:
        source = Path(temporary).resolve() / "source"
        toolchain = capture_apple_package_sources(Path(repository), source_revision, source)
        before = _verify_sdk_apple_with_tooling(
            sources={
                "product": (Path(product_directory), False),
                "binary": (Path(binary_frameworks), False),
                "source": (source, False),
                "execution": (Path(evidence_directory), True),
            },
            expected_paths={
                "sdk-compatibility.json": Path(expected_sdk_compatibility),
                "input-binding.json": Path(execution_binding_file),
                "expected-execution-files.json": Path(expected_execution_files),
            },
            command_name="verify-original-apple-package-execution",
            argument_builder=lambda private, expected, root: {
                "evidence-directory": private["execution"],
                "product-directory": private["product"],
                "version": sdk_version,
                "binary-frameworks": private["binary"],
                "source-snapshot": private["source"],
                "sdk-compatibility": expected["sdk-compatibility.json"],
                "work-directory": root / "work",
                "execution-binding-file": expected["input-binding.json"],
                "expected-binding-sha256": expected_binding_sha256,
                "expected-execution-files": expected["expected-execution-files.json"],
                "xcode-version": toolchain["xcodeVersion"],
                "xcode-build": toolchain["xcodeBuild"],
                "swift-version": toolchain["swiftVersion"],
            },
            repository=repository, tooling_evidence=tooling_evidence,
            tooling_public_key=tooling_public_key, java_executable=java_executable,
            policy_revision=policy_revision, required_trust_domain=required_trust_domain,
            tooling_keyring=tooling_keyring, tooling_keys_directory=tooling_keys_directory,
        )
    return before["product"]
