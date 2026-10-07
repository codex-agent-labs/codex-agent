"""Translate and execute imported-only iOS validation without admission."""

from collections.abc import Mapping
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from products.inventory import (
    canonical_json_bytes, read_regular_file_bytes, regular_file_inventory,
    require_exact_keys, require_integer, require_semver, require_sha256,
    write_canonical_json,
)
from products.receipt import validate_producer, verify_output_manifest_identity
from products.restore import PHASE_PLAN_KEYS
from sdk_ios_phase import _directory, _request, _GIT_ID


_LIMIT = 16 * 1024 * 1024


def validation_properties(*, target, sdk_version, contract_version, candidate_tree,
                          package_stage: Path, contract_binary_stage: Path,
                          sdk_compatibility: Path, test_application: Path,
                          compiler_consumers: Path) -> dict[str, str]:
    """Map exact original paths to imported-only validation properties.

    The caller must authenticate the selected phase, original receipts/stages,
    compatibility bytes, test-application and compiler-consumer sources before
    using this mapper. Path and version checks
    here do not establish source, signature, Apple host or semantic authority.
    Tree IDs follow the current receipt producer contract: 40 lowercase hex.
    """
    if type(target) is not str or target not in ("ios-arm64", "ios-simulator-arm64"):
        raise ValueError("iOS SDK validation requires an exact iOS target")
    version = require_semver(sdk_version, "Selected SDK version")
    contract = require_semver(contract_version, "Original Contract version")
    if type(candidate_tree) is not str or _GIT_ID.fullmatch(candidate_tree) is None:
        raise ValueError("iOS SDK validation requires an exact candidate tree")
    consumers = _directory(compiler_consumers, "Authenticated iOS validation compiler consumers")
    for name in ("CodexFailureSwiftConsumer.swift", "CodexFailureObjectiveCConsumer.m"):
        _request(compiler_consumers / name, "Authenticated iOS validation compiler consumer")
    return {
        "codexAgent.product": "sdk",
        "codexAgent.component": "sdk-ios",
        "codexAgent.phase": "validation",
        "codexAgent.target": target,
        "codexAgent.iosValidationPackageStage": _directory(package_stage, "Original iOS SDK package stage"),
        "codexAgent.contractBinaryStage": _directory(contract_binary_stage, "Original Contract binary stage"),
        "codexAgent.sdkCompatibilityFile": _request(sdk_compatibility, "Authenticated SDK compatibility"),
        "codexAgent.iosValidationTestApplicationDirectory": _directory(
            test_application, "Authenticated iOS validation test application"),
        "codexAgent.iosValidationCompilerConsumersDirectory": consumers,
        "codexAgent.sdkVersion": version,
        "codexAgent.contractVersion": contract,
        "codexAgent.candidateTree": candidate_tree,
    }


def execute(
    plan: Mapping[str, Any], *, producer: Mapping[str, Any], sdk_version: str,
    package_stage: Mapping[str, Any], contract_binary_stage: Mapping[str, Any],
    sdk_compatibility: Path, test_application: Path, compiler_consumers: Path,
    repository_root: Path, destination: Path, environ: Mapping[str, str],
) -> dict[str, Any]:
    """Run the fixed imported-validation phase over authenticated originals.

    The canonical stage is not a phase receipt or admission record. The raw
    archive and process diagnostics remain external execution evidence.
    """
    from native_wrappers import host_classifier
    from product_reuse import (
        _prepare_destination, _runtime_worker_checkout, _runtime_worker_command,
        _runtime_worker_environment,
    )
    from products.sdk_native_metadata import _inventory
    from products.sdk_package import _require_capability_output_separate
    from sdk_ios_package import _record

    selected = require_exact_keys(plan, PHASE_PLAN_KEYS, "iOS SDK validation phase plan")
    if require_integer(selected["schemaVersion"], "iOS SDK validation plan schema", 1) != 1:
        raise ValueError("Unsupported iOS SDK validation plan schema")
    target = selected["target"]
    if tuple(selected[field] for field in ("product", "component", "phase")) != (
            "sdk", "sdk-ios", "validation") or target not in ("ios-arm64", "ios-simulator-arm64"):
        raise ValueError("Unsupported implemented iOS SDK validation identity")
    require_sha256(selected["buildKey"], "Elected iOS SDK validation build key")
    current_producer = validate_producer(producer, "Elected iOS SDK validation producer")
    version = require_semver(sdk_version, "Elected SDK version")
    plan_bytes = canonical_json_bytes(selected)
    producer_bytes = canonical_json_bytes(current_producer)

    package = _record(
        package_stage, ("sdk", "sdk-ios", "package", "ios"),
        "Authenticated original iOS SDK package",
    )
    contract = _record(
        contract_binary_stage, ("contract", "contract", "binary", "common"),
        "Authenticated original Contract binary",
    )
    if package[-1]["productVersion"] != version:
        raise ValueError("Authenticated iOS SDK package version differs from the elected SDK version")
    contract_version = require_semver(
        contract[-1]["productVersion"], "Authenticated Contract binary version",
    )

    compatibility = Path(_request(Path(sdk_compatibility), "Authenticated SDK compatibility"))
    application = Path(_directory(test_application, "Authenticated iOS validation test application"))
    consumers = Path(_directory(compiler_consumers, "Authenticated iOS validation compiler consumers"))
    files = {
        "compatibility": (compatibility, read_regular_file_bytes(
            compatibility, max_bytes=_LIMIT, reject_symlink_parents=True)),
    }
    directories = {
        "package": (package[1], package[4]),
        "contract": (contract[1], contract[4]),
        "application": (application, _inventory(application)),
        "consumers": (consumers, _inventory(consumers)),
    }
    receipt_bytes = {"package": package[3], "contract": contract[3]}

    def originals_unchanged() -> None:
        if (canonical_json_bytes(selected) != plan_bytes
                or canonical_json_bytes(current_producer) != producer_bytes
                or any(_inventory(path) != inventory for path, inventory in directories.values())
                or read_regular_file_bytes(package[2], max_bytes=_LIMIT,
                                           reject_symlink_parents=True) != receipt_bytes["package"]
                or read_regular_file_bytes(contract[2], max_bytes=_LIMIT,
                                           reject_symlink_parents=True) != receipt_bytes["contract"]
                or any(read_regular_file_bytes(path, max_bytes=_LIMIT,
                                               reject_symlink_parents=True) != contents
                       for path, contents in files.values())):
            raise ValueError("Original iOS SDK validation input changed during execution")

    originals_unchanged()
    fields = validation_properties(
        target=target, sdk_version=version, contract_version=contract_version,
        candidate_tree=current_producer["tree"], package_stage=package[1],
        contract_binary_stage=contract[1], sdk_compatibility=compatibility,
        test_application=application, compiler_consumers=consumers,
    )
    fields["codexAgent.candidateCommit"] = current_producer["commit"]
    originals_unchanged()
    if host_classifier() != "macos-arm64":
        raise ValueError("iOS SDK validation requires the actual macOS ARM64 host")

    root = Path(repository_root).resolve(strict=True)
    destination = Path(destination).absolute()
    ios_build = root / "codex-agent-runtime-ios/build"
    stage = root / "build/product-stage/sdk/sdk-ios/validation"
    tree = current_producer["tree"]
    validation_root = ios_build / f"imported-sdk-validation/{tree}/{target}"
    envelope = validation_root / "execution-envelope"
    archive = envelope / "apple-validation-evidence.zip"
    owned_directories = (
        stage,
        validation_root,
        ios_build / f"imported-apple-contract-evidence/{tree}",
        ios_build / "reports/cross-language-api",
        ios_build / "reports/ios-release/toolchain",
        ios_build / "apple-compiler-evidence-task",
        ios_build / "swift-authentication-evidence-task",
        ios_build / "swift-simulator-compilation-derived-data",
        ios_build / "swift-authentication-tests.xcresult",
    )
    owned_files = (
        ios_build / "simulator-devices.json",
        ios_build / "swift-authentication-tests-summary.json",
    )
    original_paths = (
        package[1], package[2], contract[1], contract[2], compatibility, application, consumers,
    )
    outputs = (destination, *owned_directories, *owned_files)
    for index, left in enumerate(outputs):
        for right in outputs[index + 1:]:
            if left == right or left in right.parents or right in left.parents:
                raise ValueError("iOS SDK validation task-owned outputs overlap")
    for output in outputs:
        _require_capability_output_separate(output, original_paths)
        try:
            relative = output.relative_to(root)
        except ValueError as error:
            raise ValueError("iOS SDK validation output must remain inside the repository") from error
        current = root
        for part in relative.parts[:-1]:
            current /= part
            if current.is_symlink() or (current.exists() and not current.is_dir()):
                raise ValueError("iOS SDK validation output has an unsafe parent")
    if any(path.exists() or path.is_symlink() for path in outputs):
        raise ValueError("iOS SDK validation requires fresh diagnostic and task-owned outputs")

    for output in owned_directories:
        _prepare_destination(output, root).rmdir()
    environment, wrapper = _runtime_worker_environment(root, current_producer, destination, environ, build_directory=".")
    destination = _prepare_destination(destination, root)

    def unchanged() -> None:
        _runtime_worker_checkout(root, current_producer)
        bytecode = destination / "python-bytecode"
        if bytecode.exists() or bytecode.is_symlink():
            raise ValueError("iOS SDK validation private bytecode namespace was modified")
        originals_unchanged()

    unchanged()
    command = _runtime_worker_command(wrapper, fields, environment, build_directory=".")
    if command.count("ciProductPhase") != 1:
        raise ValueError("iOS SDK validation worker command no longer has the fixed phase task")
    unchanged()
    if any(path.exists() or path.is_symlink() for path in (*owned_directories, *owned_files)):
        raise ValueError("iOS SDK validation output appeared before execution")
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
            f"iOS SDK validation task failed with exit code {return_code}; see {destination / 'gradle.log'}",
        )
    manifest = verify_output_manifest_identity(
        stage, "sdk", "sdk-ios", "validation", target, version,
    )
    if (len(manifest["outputs"]) != 1
            or manifest["outputs"][0]["kind"] != "apple-validation-content"
            or manifest["outputs"][0]["relativePath"] !=
            "outputs/validation/apple-validation.json"):
        raise ValueError("iOS SDK validation canonical output is missing or ambiguous")
    output_inventory = _inventory(stage)
    evidence_inventory = regular_file_inventory(envelope)
    if ([record["relativePath"] for record in evidence_inventory] != [archive.name]
            or evidence_inventory[0]["bytes"] <= 0):
        raise ValueError("iOS SDK validation evidence archive output is missing or ambiguous")
    digest = evidence_inventory[0]["sha256"]
    unchanged()
    if (_inventory(stage) != output_inventory
            or regular_file_inventory(envelope) != evidence_inventory):
        raise ValueError("iOS SDK validation output changed during verification")
    return {
        "stage": stage, "diagnostics": destination, "outputInventory": output_inventory,
        "evidenceArchive": archive, "evidenceSha256": digest,
    }
