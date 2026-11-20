"""Authenticated-tooling adapter for original simulator observation replay."""

from pathlib import Path

from .inventory import require_string
from .sdk_apple_content import _verify_sdk_apple_with_tooling
from .sdk_apple_device_evidence import _original_directory


def verify_sdk_apple_simulator_execution(
    *, evidence_directory: Path, expected_runtime_name: str,
    expected_device_type_identifier: str, original_working_directory: str,
    repository: Path, tooling_evidence: Path, tooling_public_key: Path,
    java_executable: Path, policy_revision: str, required_trust_domain: str,
    tooling_keyring: Path | None = None, tooling_keys_directory: Path | None = None,
) -> None:
    """Replay private original bytes without granting source, host or receipt trust.

    Runtime/device pins and the original producer's working directory must come
    independently from the authenticated caller. Full XCTest binding and phase
    admission remain separate. No product, receipt or acceptance token is emitted.
    """
    for value, label in ((expected_runtime_name, "Expected simulator runtime name"),
                         (expected_device_type_identifier, "Expected simulator device type")):
        value = require_string(value, label)
        if value != value.strip() or any(ord(c) < 32 or 127 <= ord(c) <= 159 for c in value):
            raise ValueError(f"{label} must be an exact nonempty caller pin")
    _original_directory(original_working_directory, "Original simulator working directory")
    _verify_sdk_apple_with_tooling(
        sources={"execution": (Path(evidence_directory), True)}, expected_paths={},
        command_name="verify-original-apple-simulator-execution",
        argument_builder=lambda private, _expected, _root: {
            "evidence-directory": private["execution"],
            "expected-runtime-name": expected_runtime_name,
            "expected-device-type-identifier": expected_device_type_identifier,
            "original-working-directory": original_working_directory,
        },
        repository=repository, tooling_evidence=tooling_evidence,
        tooling_public_key=tooling_public_key, java_executable=java_executable,
        policy_revision=policy_revision, required_trust_domain=required_trust_domain,
        tooling_keyring=tooling_keyring, tooling_keys_directory=tooling_keys_directory,
    )
