"""Byte binding for one externally authenticated Apple package execution closure.

This module does not authenticate source, signatures, hosts, tools, or phase admission.  The
caller must place the returned descriptor, all four receipts, the compatibility file, and the
complete capture under one authenticated outer transport.
"""

from __future__ import annotations

import stat
from pathlib import Path
from typing import Any

from .inventory import (
    canonical_json_bytes,
    load_canonical_json_bytes,
    read_regular_file_bytes,
    regular_file_inventory,
    require_regular_directory,
    require_integer,
    require_sha256,
    sha256_bytes,
)
from .receipt import validate_phase_receipt, validate_producer


_EVENTS = tuple(
    f"{index:02d}-{name}" for index, name in enumerate((
        "toolchain-before-xcode",
        "toolchain-before-swift",
        "device-platform",
        "device-architecture",
        "simulator-platform",
        "simulator-architecture",
        "assemble-xcframework",
        "device-strip",
        "device-normalize",
        "device-path-scan",
        "simulator-strip",
        "simulator-normalize",
        "simulator-path-scan",
        "available-libraries",
        "rewrite-available-libraries",
        "toolchain-after-xcode",
        "toolchain-after-swift",
    ))
)
_RECEIPT_IDENTITIES = {
    "package": ("sdk", "sdk-ios", "package", "ios"),
    "binary": ("sdk", "sdk-ios", "binary", "ios"),
    "contractBinary": ("contract", "contract", "binary", "common"),
    "contractMetadata": ("contract", "contract", "metadata", "common"),
}


def build_apple_package_execution_context(
    *,
    capture_directory: Path,
    package_receipt: Path,
    binary_receipt: Path,
    contract_binary_receipt: Path,
    contract_metadata_receipt: Path,
    producer: dict[str, Any],
    sdk_compatibility: Path,
    sdk_inputs_artifact_id: int,
    sdk_inputs_artifact_sha256: str,
) -> dict[str, Any]:
    """Describe exact closure bytes; this descriptor grants no trust or success authority."""

    capture = Path(capture_directory)
    if not capture.is_absolute() or capture.resolve(strict=True) != capture:
        raise ValueError("Apple package execution capture must be an exact normalized directory")
    capture = require_regular_directory(capture, "Apple package execution capture")
    receipt_paths = {
        "package": Path(package_receipt),
        "binary": Path(binary_receipt),
        "contractBinary": Path(contract_binary_receipt),
        "contractMetadata": Path(contract_metadata_receipt),
    }
    validated_producer = dict(validate_producer(producer, "Apple package execution producer"))
    sdk_inputs = {
        "artifactId": require_integer(sdk_inputs_artifact_id, "Original SDK inputs artifact ID", 1),
        "artifactSha256": require_sha256(sdk_inputs_artifact_sha256, "Original SDK inputs artifact digest"),
    }
    receipt_bytes = {
        name: read_regular_file_bytes(path, reject_symlink_parents=True)
        for name, path in receipt_paths.items()
    }
    receipts = {
        name: validate_phase_receipt(load_canonical_json_bytes(contents))
        for name, contents in receipt_bytes.items()
    }
    for name, identity in _RECEIPT_IDENTITIES.items():
        receipt = receipts[name]
        if tuple(receipt[field] for field in ("product", "component", "phase", "target")) != identity:
            raise ValueError(f"Apple package execution {name} receipt identity mismatch")
    if receipts["package"]["producer"] != validated_producer:
        raise ValueError("Apple package execution package producer differs from the caller producer")
    if receipts["package"]["productVersion"] != receipts["binary"]["productVersion"]:
        raise ValueError("Apple package execution package and binary versions differ")

    compatibility = Path(sdk_compatibility)
    compatibility_bytes = read_regular_file_bytes(compatibility, reject_symlink_parents=True)
    if not compatibility_bytes:
        raise ValueError("Apple package execution SDK compatibility is empty")
    _require_capture_layout(capture)
    capture_before = regular_file_inventory(capture, allow_empty=True)
    binding = next((record for record in capture_before if record["relativePath"] == "input-binding.json"), None)
    if binding is None or binding["bytes"] <= 0:
        raise ValueError("Apple package execution input binding is missing or empty")
    for event in _EVENTS:
        if not any(record["relativePath"].startswith(f"events/{event}/") for record in capture_before):
            raise ValueError(f"Apple package execution event is empty: {event}")

    descriptor = {
        "schemaVersion": 1,
        "kind": "apple-package-execution",
        "producer": validated_producer,
        "receiptSha256": {
            name: sha256_bytes(contents) for name, contents in receipt_bytes.items()
        },
        "sdkCompatibilitySha256": sha256_bytes(compatibility_bytes),
        "captureFiles": capture_before,
        "sdkInputsArtifact": sdk_inputs,
    }

    _require_capture_layout(capture)
    capture_after = regular_file_inventory(capture, allow_empty=True)
    if capture_after != capture_before:
        raise ValueError("Apple package execution capture changed while binding")
    if any(read_regular_file_bytes(path, reject_symlink_parents=True) != receipt_bytes[name]
           for name, path in receipt_paths.items()):
        raise ValueError("Apple package execution receipt changed while binding")
    if read_regular_file_bytes(compatibility, reject_symlink_parents=True) != compatibility_bytes:
        raise ValueError("Apple package execution SDK compatibility changed while binding")
    if validate_producer(producer, "Apple package execution producer") != validated_producer:
        raise ValueError("Apple package execution producer changed while binding")
    return descriptor


def verify_apple_package_execution_context(
    descriptor_path: Path,
    *,
    capture_directory: Path,
    package_receipt: Path,
    binary_receipt: Path,
    contract_binary_receipt: Path,
    contract_metadata_receipt: Path,
    producer: dict[str, Any],
    sdk_compatibility: Path,
    sdk_inputs_artifact_id: int,
    sdk_inputs_artifact_sha256: str,
) -> dict[str, Any]:
    """Check retained descriptor bytes against independent caller inputs only.

    Never derive these arguments from the descriptor itself. The caller must
    authenticate the same original transport/receipts/source closure separately.
    This reuses the builder's schema and mutation checks, but performs no native
    replay and grants no receipt, source, tool, host or phase admission authority.
    """
    path = Path(descriptor_path)
    original = read_regular_file_bytes(path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
    load_canonical_json_bytes(original)
    expected = build_apple_package_execution_context(
        capture_directory=capture_directory,
        package_receipt=package_receipt,
        binary_receipt=binary_receipt,
        contract_binary_receipt=contract_binary_receipt,
        contract_metadata_receipt=contract_metadata_receipt,
        producer=producer,
        sdk_compatibility=sdk_compatibility,
        sdk_inputs_artifact_id=sdk_inputs_artifact_id,
        sdk_inputs_artifact_sha256=sdk_inputs_artifact_sha256,
    )
    if canonical_json_bytes(expected) != original:
        raise ValueError("Retained Apple package execution descriptor differs from caller inputs")
    if read_regular_file_bytes(path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True) != original:
        raise ValueError("Retained Apple package execution descriptor changed during verification")
    return expected


def _require_capture_layout(capture: Path) -> None:
    expected = {"events", "input-binding.json"}
    actual: set[str] = set()
    for entry in capture.iterdir():
        metadata = entry.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError(f"Apple package execution capture contains an unsafe entry: {entry.name}")
        if entry.name == "input-binding.json":
            if not stat.S_ISREG(metadata.st_mode):
                raise ValueError("Apple package execution input binding is not a regular file")
        elif entry.name != "events" or not stat.S_ISDIR(metadata.st_mode):
            raise ValueError(f"Apple package execution capture entry is invalid: {entry.name}")
        actual.add(entry.name)
    if actual != expected:
        raise ValueError("Apple package execution capture top-level inventory mismatch")
    events = capture / "events"
    event_names: set[str] = set()
    for entry in events.iterdir():
        metadata = entry.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise ValueError(f"Apple package execution capture contains an unsafe event: {entry.name}")
        event_names.add(entry.name)
    if event_names != set(_EVENTS):
        raise ValueError("Apple package execution event directory inventory mismatch")
