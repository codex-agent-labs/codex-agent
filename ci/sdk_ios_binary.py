"""Translate caller-authenticated iOS SDK binary inputs to fixed Gradle properties."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from products.inventory import (
    load_canonical_json_bytes,
    read_regular_file_bytes,
    regular_file_inventory,
    require_exact_keys,
    require_integer,
    require_regular_directory,
    require_semver,
    require_sha256,
)
from products.receipt import validate_phase_receipt, validate_producer, verify_output_manifest_identity
from products.registry import PHASE_INSTANCE_IDS
from products.restore import PHASE_PLAN_KEYS


_IDENTITY = ("sdk", "sdk-ios", "binary", "ios")
_LIMIT = 16 * 1024 * 1024
_BUNDLE_LIMIT = 512 * 1024 * 1024


def _directory(value: Any, label: str) -> Path:
    if not isinstance(value, Path) or not value.is_absolute():
        raise ValueError(f"{label} must be an absolute normalized directory")
    require_regular_directory(value, label)
    if value.resolve(strict=True) != value:
        raise ValueError(f"{label} must be non-symbolic and normalized")
    return value


def _file(value: Path, label: str, *, limit: int = _LIMIT) -> Path:
    if not isinstance(value, Path) or not value.is_absolute() or value.resolve(strict=True) != value:
        raise ValueError(f"{label} must be an absolute normalized file")
    if not read_regular_file_bytes(value, max_bytes=limit, reject_symlink_parents=True):
        raise ValueError(f"{label} must be nonempty and non-symbolic")
    return value


def properties(
    phase_plan: Mapping[str, Any],
    *,
    producer: Mapping[str, Any],
    contract_metadata: Mapping[str, Any],
    verified_contract_handoff: Path,
    native_evidence: Path,
) -> dict[str, str]:
    """Return existing settings/task properties without granting input trust."""
    plan = require_exact_keys(phase_plan, PHASE_PLAN_KEYS, "iOS SDK binary phase plan")
    if require_integer(plan["schemaVersion"], "iOS SDK binary plan schema", 1) != 1:
        raise ValueError("Unsupported iOS SDK binary plan schema")
    identity = tuple(plan[field] for field in ("product", "component", "phase", "target"))
    if identity != _IDENTITY or not any(
        identity == (item.product, item.component, item.phase, item.target)
        for item in PHASE_INSTANCE_IDS
    ):
        raise ValueError("Unsupported implemented iOS SDK binary identity")
    require_sha256(plan["buildKey"], "Elected iOS SDK binary build key")
    current_producer = validate_producer(producer, "Elected iOS SDK binary producer")

    record = require_exact_keys(
        contract_metadata, {"stage", "receiptPath", "receipt"},
        "Authenticated Contract metadata record",
    )
    stage = _directory(record["stage"], "Authenticated Contract metadata stage")
    receipt_path = _file(record["receiptPath"], "Authenticated Contract metadata receipt")
    handoff = _directory(verified_contract_handoff, "Verified Contract handoff")
    native = _directory(native_evidence, "Authenticated Apple native evidence")
    if not regular_file_inventory(native):
        raise ValueError("Authenticated Apple native evidence is empty")
    resolved = (stage, handoff, native)
    if any(left == right or left in right.parents or right in left.parents
           for index, left in enumerate(resolved) for right in resolved[index + 1:]):
        raise ValueError("iOS SDK binary input directories must not overlap")

    receipt_bytes = read_regular_file_bytes(
        receipt_path, max_bytes=_LIMIT, reject_symlink_parents=True,
    )
    receipt = validate_phase_receipt(load_canonical_json_bytes(receipt_bytes))
    if receipt != record["receipt"] or tuple(
            receipt[field] for field in ("product", "component", "phase", "target")) != (
                "contract", "contract", "metadata", "common"):
        raise ValueError("iOS SDK binary Contract metadata differs from its authenticated receipt")
    version = require_semver(receipt["productVersion"], "Authenticated Contract version")
    manifest = verify_output_manifest_identity(
        stage, "contract", "contract", "metadata", "common", version,
    )
    if manifest["outputs"] != receipt["outputs"]:
        raise ValueError("iOS SDK binary Contract metadata stage differs from its receipt")
    bundles = [output for output in receipt["outputs"] if output["kind"] == "contract-bundle"]
    if len(bundles) != 1:
        raise ValueError("iOS SDK binary requires one authenticated Contract bundle")
    bundle = stage / bundles[0]["relativePath"]
    stem = f"codex-agent-contract-{version}"
    if bundle.name != f"{stem}.zip":
        raise ValueError("iOS SDK binary Contract bundle filename is invalid")
    payload = _file(handoff / f"{stem}.zip", "Verified Contract payload", limit=_BUNDLE_LIMIT)
    if read_regular_file_bytes(
            bundle, max_bytes=_BUNDLE_LIMIT, reject_symlink_parents=True,
    ) != read_regular_file_bytes(
            payload, max_bytes=_BUNDLE_LIMIT, reject_symlink_parents=True,
    ):
        raise ValueError("Verified Contract payload differs from the authenticated metadata bundle")
    attestation = _file(handoff / f"{stem}.attestation.json", "Verified Contract attestation")
    signature = _file(handoff / f"{stem}.attestation.sig", "Verified Contract signature")
    public_key = _file(handoff / "public-key.pub", "Verified Contract public key")

    return {
        "codexAgent.product": "sdk",
        "codexAgent.component": "sdk-ios",
        "codexAgent.phase": "binary",
        "codexAgent.target": "ios",
        "codexAgent.candidateCommit": current_producer["commit"],
        "codexAgent.candidateTree": current_producer["tree"],
        "codexAgent.contractPayload": str(payload),
        "codexAgent.contractMetadataReceipt": str(receipt_path),
        "codexAgent.contractAttestation": str(attestation),
        "codexAgent.contractAttestationSignature": str(signature),
        "codexAgent.contractPublicKey": str(public_key),
        "codexAgent.contractVersion": version,
        "codexAgent.iosNativeEvidenceDirectory": str(native),
    }
