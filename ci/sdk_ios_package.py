"""Execute the fixed imported iOS SDK package phase without admitting it."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
import subprocess
import time
from typing import Any

from products.inventory import (
    load_canonical_json_bytes,
    read_regular_file_bytes,
    require_exact_keys,
    require_integer,
    require_semver,
    require_sha256,
    write_canonical_json,
)
from products.receipt import validate_phase_receipt, validate_producer, verify_output_manifest_identity
from products.restore import PHASE_PLAN_KEYS
from sdk_ios_phase import binary_package_properties, package_properties


_IDENTITY = ("sdk", "sdk-ios", "package", "ios")
_LIMIT = 16 * 1024 * 1024


def _record(value: Mapping[str, Any], identity: tuple[str, str, str, str], label: str):
    from products.sdk_native_metadata import _inventory

    record = require_exact_keys(value, {"stage", "receiptPath", "receipt"}, label)
    stage = Path(record["stage"])
    receipt_path = Path(record["receiptPath"])
    if (not stage.is_absolute() or stage.resolve(strict=True) != stage
            or not receipt_path.is_absolute() or receipt_path.resolve(strict=True) != receipt_path):
        raise ValueError(f"{label} paths must be absolute, normalized and non-symbolic")
    inventory = _inventory(stage)
    receipt_bytes = read_regular_file_bytes(
        receipt_path, max_bytes=_LIMIT, reject_symlink_parents=True,
    )
    receipt = validate_phase_receipt(load_canonical_json_bytes(receipt_bytes))
    if receipt != record["receipt"] or tuple(
            receipt[field] for field in ("product", "component", "phase", "target")) != identity:
        raise ValueError(f"{label} differs from its authenticated receipt")
    version = require_semver(receipt["productVersion"], f"{label} version")
    manifest = verify_output_manifest_identity(stage, *identity, version)
    if manifest["outputs"] != receipt["outputs"]:
        raise ValueError(f"{label} stage differs from its authenticated receipt")
    if (_inventory(stage) != inventory or read_regular_file_bytes(
            receipt_path, max_bytes=_LIMIT, reject_symlink_parents=True) != receipt_bytes):
        raise ValueError(f"{label} changed during verification")
    return record, stage, receipt_path, receipt_bytes, inventory, receipt


def execute(
    plan: Mapping[str, Any], *, producer: Mapping[str, Any], sdk_version: str,
    current_contract: Mapping[str, Any], sdk_binary: Mapping[str, Any],
    compatibility_request: Path,
    repository_root: Path, destination: Path, environ: Mapping[str, str],
    verified_distribution: Path | None = None, native_evidence: Path | None = None,
    expected_sdk_compatibility: Path | None = None, expected_distribution_proof: Path | None = None,
) -> dict[str, Any]:
    """Run canonical ``ciProductPhase`` over caller-authenticated originals.

    Omitting all legacy distribution inputs packages raw binary predecessors.
    That path produces no validation evidence and grants no compiler/host trust;
    the caller must separately admit its package content and final validation.
    """
    from native_wrappers import host_classifier
    from product_reuse import (
        _prepare_destination, _runtime_worker_checkout, _runtime_worker_command,
        _runtime_worker_environment,
    )
    from products.sdk_native_metadata import _inventory
    from products.sdk_package import _require_capability_output_separate
    from products.sdk_validation_inputs import _request_inventory

    selected = require_exact_keys(plan, PHASE_PLAN_KEYS, "iOS SDK package phase plan")
    if require_integer(selected["schemaVersion"], "iOS SDK package plan schema", 1) != 1:
        raise ValueError("Unsupported iOS SDK package plan schema")
    if tuple(selected[field] for field in ("product", "component", "phase", "target")) != _IDENTITY:
        raise ValueError("Unsupported implemented iOS SDK package identity")
    require_sha256(selected["buildKey"], "Elected iOS SDK package build key")
    current_producer = validate_producer(producer, "Elected iOS SDK package producer")
    version = require_semver(sdk_version, "Elected SDK version")

    contract = _record(
        current_contract, ("contract", "contract", "binary", "common"),
        "Authenticated current Contract binary",
    )
    binary = _record(
        sdk_binary, ("sdk", "sdk-ios", "binary", "ios"),
        "Authenticated iOS SDK binary",
    )
    if binary[-1]["productVersion"] != version:
        raise ValueError("Authenticated iOS SDK binary version differs from the elected SDK version")

    legacy_inputs = (verified_distribution, native_evidence, expected_sdk_compatibility,
                     expected_distribution_proof)
    binary_only = all(value is None for value in legacy_inputs)
    if not binary_only and any(value is None for value in legacy_inputs):
        raise ValueError("iOS SDK package legacy inputs must be supplied together")
    directories = {} if binary_only else {
        "distribution": Path(verified_distribution),
        "native": Path(native_evidence),
    }
    directory_inventories = {}
    for name, source in directories.items():
        if not source.is_absolute() or source.resolve(strict=True) != source:
            raise ValueError(f"Original Apple {name} must be absolute, normalized and non-symbolic")
        inventory = _inventory(source, allow_empty=name == "distribution")
        if not inventory:
            raise ValueError(f"Original Apple {name} is empty")
        directory_inventories[name] = inventory
    files = {
        "request": Path(compatibility_request),
    }
    if not binary_only:
        files.update(compatibility=Path(expected_sdk_compatibility), proof=Path(expected_distribution_proof))
    file_bytes = {}
    for name, source in files.items():
        if not source.is_absolute() or source.resolve(strict=True) != source:
            raise ValueError(f"iOS SDK package {name} must be absolute, normalized and non-symbolic")
        contents = read_regular_file_bytes(source, max_bytes=_LIMIT, reject_symlink_parents=True)
        if not contents:
            raise ValueError(f"iOS SDK package {name} must be nonempty")
        file_bytes[name] = contents
    request_inventory = _request_inventory(files["request"])

    root = Path(repository_root).resolve(strict=True)
    destination = Path(destination).absolute()
    sdk_build = root / "codex-agent-sdk/build"
    ios_build = root / "codex-agent-runtime-ios/build"
    tree = current_producer["tree"]
    stage = sdk_build / "product-stage/sdk/sdk-ios/package"
    validation = sdk_build / f"apple-sdk-package-tasks/{tree}/validation-evidence"
    owned_directories = (
        stage,
        sdk_build / f"imported-sdk-binary-stages/{tree}/sdk-ios",
        sdk_build / f"sdk-compatibility/{tree}",
        sdk_build / f"apple-sdk-package-tasks/{tree}",
    ) + ((
        ios_build / "imported-frameworks",
        ios_build / "XCFrameworks/release",
        ios_build / "release-xcframework",
        ios_build / "apple-distribution",
        ios_build / "distributions",
    ) if binary_only else (
        ios_build / "imported-rust",
        ios_build / "imported-verified-apple",
        ios_build / "distributions",
        ios_build / "reports",
    ))
    owned_files = () if binary_only else (ios_build / "swift-authentication-tests-summary.json",)
    original_paths = (
        contract[1], contract[2], binary[1], binary[2],
        *directories.values(), *files.values(), *request_inventory,
    )
    all_outputs = (destination, *owned_directories, *owned_files)
    for output in all_outputs:
        _require_capability_output_separate(output, original_paths)
        try:
            relative = output.relative_to(root)
        except ValueError as error:
            raise ValueError("iOS SDK package output must remain inside the repository") from error
        current = root
        for part in relative.parts[:-1]:
            current /= part
            if current.is_symlink() or (current.exists() and not current.is_dir()):
                raise ValueError("iOS SDK package output has an unsafe parent")
    if any(path.exists() or path.is_symlink() for path in all_outputs):
        raise ValueError("iOS SDK package worker requires fresh diagnostic and Gradle-owned outputs")

    def originals_unchanged() -> None:
        if (_inventory(contract[1]) != contract[4] or _inventory(binary[1]) != binary[4]
                or read_regular_file_bytes(contract[2], max_bytes=_LIMIT,
                                           reject_symlink_parents=True) != contract[3]
                or read_regular_file_bytes(binary[2], max_bytes=_LIMIT,
                                           reject_symlink_parents=True) != binary[3]
                or any(_inventory(directories[name], allow_empty=name == "distribution") != inventory
                       for name, inventory in directory_inventories.items())
                or any(read_regular_file_bytes(files[name], max_bytes=_LIMIT,
                                               reject_symlink_parents=True) != contents
                       for name, contents in file_bytes.items())
                or _request_inventory(files["request"]) != request_inventory):
            raise ValueError("Original iOS SDK package input changed during execution")

    def predecessor(product: str, component: str, phase: str, target: str):
        identity = (product, component, phase, target)
        if identity == ("contract", "contract", "binary", "common"):
            return contract[0]
        if identity == ("sdk", "sdk-ios", "binary", "ios"):
            return binary[0]
        raise ValueError("iOS SDK package requested an unauthenticated predecessor")

    originals_unchanged()
    if binary_only:
        fields = binary_package_properties(
            selected, sdk_version=version, predecessor=predecessor,
            compatibility_request=files["request"],
        )
    else:
        fields = package_properties(
            selected, sdk_version=version, predecessor=predecessor,
            verified_distribution=directories["distribution"], native_evidence=directories["native"],
            compatibility_request=files["request"], expected_sdk_compatibility=files["compatibility"],
            expected_distribution_proof=files["proof"],
        )
    fields.update({
        "codexAgent.candidateCommit": current_producer["commit"],
        "codexAgent.candidateTree": current_producer["tree"],
    })
    originals_unchanged()
    if host_classifier() != "macos-arm64":
        raise ValueError("iOS SDK package production requires the actual macOS ARM64 host")

    for output in owned_directories:
        _prepare_destination(output, root).rmdir()
    destination = _prepare_destination(destination, root)
    environment, wrapper = _runtime_worker_environment(root, current_producer, destination, environ)

    def unchanged() -> None:
        _runtime_worker_checkout(root, current_producer)
        if (destination / "python-bytecode").exists() or (destination / "python-bytecode").is_symlink():
            raise ValueError("iOS SDK package private bytecode namespace was modified")
        originals_unchanged()

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
            "schemaVersion": 1, "producer": dict(current_producer),
            "buildKey": selected["buildKey"], "command": command,
            "returnCode": return_code, "launchError": launch_error,
            "elapsedNs": time.monotonic_ns() - started,
        })
        unchanged()
    if return_code != 0:
        raise ValueError(
            f"iOS SDK package phase failed with exit code {return_code}; see {destination / 'gradle.log'}",
        )
    manifest = verify_output_manifest_identity(stage, *_IDENTITY, version)
    if {output["kind"] for output in manifest["outputs"]} != {"apple", "evidence", "maven"}:
        raise ValueError("iOS SDK package output is missing a canonical output family")
    output_inventory = _inventory(stage, allow_empty=True)
    if not output_inventory:
        raise ValueError("iOS SDK package output is empty")
    unchanged()
    result = {
        "stage": stage, "diagnostics": destination, "outputInventory": output_inventory,
    }
    if not binary_only:
        validation_inventory = _inventory(validation, allow_empty=True)
        if not validation_inventory:
            raise ValueError("iOS SDK package external validation evidence is empty")
        unchanged()
        result.update(validationEvidence=validation, validationEvidenceInventory=validation_inventory)
    return result
