"""Translate caller-authenticated iOS SDK binary inputs to fixed Gradle properties."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
import subprocess
import time
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
    write_canonical_json,
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


def execute(
    plan: Mapping[str, Any], *, producer: Mapping[str, Any], sdk_version: str,
    contract_metadata: Mapping[str, Any], verified_contract_handoff: Path,
    native_evidence: Path, repository_root: Path, destination: Path,
    environ: Mapping[str, str],
) -> dict[str, Any]:
    """Run the fixed iOS binary phase without finalizing or admitting its output."""
    from native_wrappers import host_classifier
    from product_reuse import (
        _prepare_destination, _runtime_worker_checkout, _runtime_worker_command,
        _runtime_worker_environment,
    )
    from products.sdk_native_metadata import _inventory
    from products.sdk_package import _require_capability_output_separate

    version = require_semver(sdk_version, "Elected SDK version")
    record = require_exact_keys(
        contract_metadata, {"stage", "receiptPath", "receipt"},
        "Authenticated Contract metadata record",
    )
    metadata = _directory(record["stage"], "Authenticated Contract metadata stage")
    receipt_path = _file(record["receiptPath"], "Authenticated Contract metadata receipt")
    handoff = _directory(verified_contract_handoff, "Verified Contract handoff")
    native = _directory(native_evidence, "Authenticated Apple native evidence")
    originals = {
        "metadata": (metadata, _inventory(metadata), False),
        "handoff": (handoff, _inventory(handoff, allow_empty=True), True),
        "native": (native, _inventory(native), False),
    }
    receipt_bytes = read_regular_file_bytes(
        receipt_path, max_bytes=_LIMIT, reject_symlink_parents=True,
    )
    fields = properties(
        plan, producer=producer, contract_metadata=contract_metadata,
        verified_contract_handoff=verified_contract_handoff,
        native_evidence=native_evidence,
    )

    def originals_unchanged() -> None:
        if any(_inventory(source, allow_empty=allow_empty) != inventory
               for source, inventory, allow_empty in originals.values()):
            raise ValueError("Original iOS SDK binary input changed during execution")
        if read_regular_file_bytes(
                receipt_path, max_bytes=_LIMIT, reject_symlink_parents=True) != receipt_bytes:
            raise ValueError("Original iOS SDK binary metadata receipt changed during execution")

    originals_unchanged()
    if host_classifier() != "macos-arm64":
        raise ValueError("iOS SDK binary production requires the actual macOS ARM64 host")
    root = Path(repository_root).resolve(strict=True)
    destination = Path(destination).absolute()
    stage = root / "build/product-stage/sdk/sdk-ios/binary"
    inputs = [receipt_path, *(path for path, _, _ in originals.values())]
    _require_capability_output_separate(destination, [stage, *inputs])
    _require_capability_output_separate(stage, inputs)
    if destination.exists() or destination.is_symlink() or stage.exists() or stage.is_symlink():
        raise ValueError("iOS SDK binary worker requires fresh diagnostic and product outputs")
    _prepare_destination(stage, root).rmdir()
    environment, wrapper = _runtime_worker_environment(root, producer, destination, environ, build_directory=".")
    destination = _prepare_destination(destination, root)

    def unchanged() -> None:
        _runtime_worker_checkout(root, producer)
        bytecode = destination / "python-bytecode"
        if bytecode.exists() or bytecode.is_symlink():
            raise ValueError("iOS SDK binary private bytecode namespace was modified")
        originals_unchanged()

    unchanged()
    if stage.exists() or stage.is_symlink():
        raise ValueError("iOS SDK binary product stage appeared before execution")
    from products.gradle_bootstrap import seed_sdk_ios_native_distribution
    seed_sdk_ios_native_distribution(root, producer["commit"], wrapper, environment,
                                    destination / "native-toolchain-seed")
    unchanged()
    command = _runtime_worker_command(wrapper, fields, environment, build_directory=".")
    started = time.monotonic_ns()
    return_code, launch_error = None, None
    try:
        with (destination / "gradle.log").open("xb") as log:
            process = subprocess.run(
                command, cwd=root, env=environment, stdout=log,
                stderr=subprocess.STDOUT, check=False,
            )
            return_code = process.returncode
    except OSError as error:
        launch_error = str(error)
        raise
    finally:
        write_canonical_json(destination / "execution.json", {
            "schemaVersion": 1, "producer": dict(producer),
            "buildKey": plan["buildKey"], "command": command,
            "returnCode": return_code, "launchError": launch_error,
            "elapsedNs": time.monotonic_ns() - started,
        })
        unchanged()
    if return_code != 0:
        raise ValueError(
            f"iOS SDK binary phase failed with exit code {return_code}; see {destination / 'gradle.log'}",
        )
    verify_output_manifest_identity(stage, "sdk", "sdk-ios", "binary", "ios", version)
    output_inventory = _inventory(stage)
    unchanged()
    return {"stage": stage, "diagnostics": destination, "outputInventory": output_inventory}
