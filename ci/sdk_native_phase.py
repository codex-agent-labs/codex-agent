"""Run native-wrapper packages inside the caller's verified-input lifetime.

These are unadmitted outputs. The caller must exit all original-input contexts,
recheck both returned inventories, then verify its private candidate receipt with
verify_sdk_package_inputs before publishing a shard. Host validation and metadata
are separate phases; this leaf neither executes nor substitutes for them.
"""

from collections.abc import Callable, Mapping
from pathlib import Path
import subprocess
import time
from typing import Any

from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, read_regular_file_bytes,
    require_exact_keys, require_integer, require_semver, require_sha256,
    write_canonical_json,
)
from products.receipt import validate_phase_receipt, validate_producer, verify_output_manifest_identity
from products.registry import NATIVE_BINDINGS, NATIVE_TARGETS, PHASE_INSTANCE_IDS
from products.restore import PHASE_PLAN_KEYS
from products.sdk_native_metadata import _inventory
from products.sdk_package import _require_capability_output_separate
from products.sdk_validation_inputs import _request_inventory
from products.sdk_dotnet_toolchain import verify_sdk_dotnet_toolchain


_LIMIT = 16 * 1024 * 1024


def route(plan: Mapping[str, Any]) -> dict[str, Any]:
    """Fixed portable package host; not a toolchain or execution observation."""
    identity = tuple(plan.get(name) for name in ("product", "component", "phase", "target"))
    if (identity[0] != "sdk" or identity[1] not in NATIVE_BINDINGS
            or identity[2:] != ("package", "desktop") or not any(
                identity == (item.product, item.component, item.phase, item.target)
                for item in PHASE_INSTANCE_IDS)):
        raise ValueError("Only native-wrapper SDK package phases have an implemented worker")
    return {"runner": "ubuntu-24.04", "runnerOs": "Linux", "runnerArch": "X64",
            "toolchainProfile": "sdk-csharp" if identity[1] == "csharp" else None,
            "producerRole": None, "supervisor": None}


def _runtime_originals(runtime_stages, runtime_inventory, predecessor):
    """Check the exact ten supplied originals; return integrity records, not trust."""
    originals, expected_runtime_files = [], set()
    for target in NATIVE_TARGETS:
        for phase in ("package", "validation"):
            identity = ("runtime", target, phase, target)
            value = predecessor(*identity)
            receipt_path = Path(value["receiptPath"])
            raw = read_regular_file_bytes(receipt_path, max_bytes=_LIMIT, reject_symlink_parents=True)
            receipt = validate_phase_receipt(load_canonical_json_bytes(raw))
            if receipt != value["receipt"] or tuple(receipt[name] for name in (
                    "product", "component", "phase", "target")) != identity:
                raise ValueError("Native SDK Runtime predecessor differs from its original receipt")
            original = Path(value["stage"])
            original_inventory = _inventory(original)
            manifest = verify_output_manifest_identity(original, *identity, receipt["productVersion"])
            imported = runtime_stages / target / phase
            if manifest["outputs"] != receipt["outputs"] or _inventory(imported) != original_inventory:
                raise ValueError("Native SDK Runtime stage differs from its original receipt or bytes")
            expected_runtime_files.update(f"{target}/{phase}/{item['relativePath']}"
                                          for item in original_inventory)
            originals.append((original, original_inventory, receipt_path, raw))
    if {item["relativePath"] for item in runtime_inventory} != expected_runtime_files:
        raise ValueError("Native SDK Runtime tree must contain exactly five original package/validation pairs")
    return originals


def _runtime_originals_unchanged(runtime_stages, runtime_inventory, originals):
    if (_inventory(runtime_stages) != runtime_inventory or any(
            _inventory(original) != inventory or read_regular_file_bytes(
                receipt, max_bytes=_LIMIT, reject_symlink_parents=True) != raw
            for original, inventory, receipt, raw in originals)):
        raise ValueError("Original native SDK Runtime inputs changed")


def execute(
    plan: Mapping[str, Any], *, producer: Mapping[str, Any], sdk_version: str,
    repository_root: Path, destination: Path, runtime_stages: Path,
    prepared_sources: Path, staged_sdks: Path,
    compatibility_request: Path,
    predecessor: Callable[[str, str, str, str], Mapping[str, Any]],
    environ: Mapping[str, str],
    csharp_binary_stage: Path | None = None,
) -> dict[str, Any]:
    """Run existing root ciProductPhase only; never finalize or publish evidence.

    The caller authenticates S858/current Contract, the original Runtime source,
    and the single prepared-source/SDK upload bound to its original source plan
    before entering this leaf. Prepared sources are executable package inputs;
    inventory checks cannot grant them source authority. The callback supplies
    original Runtime records, not a replacement for election or trust gates.
    External package-manager dependencies must already be provisioned by the job.
    """
    from native_wrappers import HOSTS, host_classifier
    from product_reuse import (
        _prepare_destination, _runtime_worker_checkout, _runtime_worker_command,
        _runtime_worker_environment,
    )

    require_exact_keys(plan, PHASE_PLAN_KEYS, "Native SDK package plan")
    if require_integer(plan["schemaVersion"], "Native SDK plan schema", 1) != 1:
        raise ValueError("Unsupported native SDK package plan schema")
    elected_route = route(plan)
    require_sha256(plan["buildKey"], "Elected native SDK build key")
    validate_producer(producer, "Elected native SDK producer")
    require_semver(sdk_version, "Elected SDK version")
    if HOSTS[host_classifier()][2:4] != (elected_route["runnerOs"], elected_route["runnerArch"]):
        raise ValueError("Native SDK package actual host differs from its elected route")
    root = Path(repository_root).resolve(strict=True)
    dotnet_profile = root / "gradle/release/toolchains/sdk/csharp.json" if plan["component"] == "csharp" else None
    if dotnet_profile is not None:
        verify_sdk_dotnet_toolchain(dotnet_profile)
    destination = Path(destination).absolute()
    runtime_stages = Path(runtime_stages)
    prepared_sources, sdks = Path(prepared_sources), Path(staged_sdks)
    request = Path(compatibility_request)
    binary = Path(csharp_binary_stage) if csharp_binary_stage is not None else None
    if (component := plan["component"]) == "csharp" and binary is None:
        raise ValueError("C# package requires an authenticated binary predecessor")
    if component != "csharp" and binary is not None:
        raise ValueError("Only C# may import the C# binary predecessor")
    if any(not path.is_absolute() for path in (runtime_stages, prepared_sources, sdks, request)):
        raise ValueError("Native SDK inputs must be explicit absolute paths")
    if binary is not None and not binary.is_absolute():
        raise ValueError("C# binary predecessor must be an explicit absolute path")
    runtime_inventory = _inventory(runtime_stages)
    source_inventory, sdk_inventory = _inventory(prepared_sources), _inventory(sdks)
    request_bytes = read_regular_file_bytes(request, max_bytes=_LIMIT, reject_symlink_parents=True)
    request_inventory = _request_inventory(request)
    plan_bytes, producer_bytes = canonical_json_bytes(plan), canonical_json_bytes(producer)
    component, tree = plan["component"], producer["tree"]
    binary_inventory = _inventory(binary) if binary is not None else None
    if binary is not None:
        verify_output_manifest_identity(binary, "sdk", "csharp", "binary", "desktop", sdk_version)
    build = root / "codex-agent-sdk/build"
    stage = build / f"product-stage/sdk/{component}/package"
    # Both supplied trees were produced once by the separately authenticated
    # preparation job. This package worker must never clean or regenerate them.
    _inventory(prepared_sources / component)
    owned = (stage,)
    if any(path.exists() or path.is_symlink() for path in (*owned, destination)):
        raise ValueError("Native SDK worker requires fresh diagnostic and package outputs")

    originals = _runtime_originals(runtime_stages, runtime_inventory, predecessor)
    inputs = [runtime_stages, prepared_sources, sdks, request, *request_inventory,
              *(path for original, _, receipt, _ in originals for path in (original, receipt))]
    if binary is not None:
        inputs.append(binary)
    _require_capability_output_separate(destination, [*owned, *inputs])
    for output in owned:
        _require_capability_output_separate(output, inputs)
    environment, wrapper = _runtime_worker_environment(root, producer, destination, environ, build_directory=".")

    def unchanged():
        _runtime_worker_checkout(root, producer)
        bytecode = destination / "python-bytecode"
        if bytecode.exists() or bytecode.is_symlink():
            raise ValueError("Native SDK private bytecode namespace was modified")
        if canonical_json_bytes(plan) != plan_bytes or canonical_json_bytes(producer) != producer_bytes:
            raise ValueError("Native SDK elected plan or producer changed")
        _runtime_originals_unchanged(runtime_stages, runtime_inventory, originals)
        if _inventory(prepared_sources) != source_inventory or _inventory(sdks) != sdk_inventory:
            raise ValueError("Original prepared native SDK source or staging inputs changed")
        if binary is not None and _inventory(binary) != binary_inventory:
            raise ValueError("Original C# binary predecessor changed")
        if (read_regular_file_bytes(request, max_bytes=_LIMIT, reject_symlink_parents=True) != request_bytes
                or _request_inventory(request) != request_inventory):
            raise ValueError("Original SDK compatibility request or inputs changed")

    unchanged()
    # These exact task-owned paths may be cleaned by Gradle; never reuse one.
    for output in owned:
        _prepare_destination(output, root).rmdir()
    destination = _prepare_destination(destination, root)
    fields = {
        "codexAgent.product": "sdk", "codexAgent.component": component,
        "codexAgent.phase": "package", "codexAgent.target": "desktop",
        "codexAgent.candidateCommit": producer["commit"], "codexAgent.candidateTree": tree,
        "codexAgent.nativeWrapperRuntimeStageRoot": str(runtime_stages),
        "codexAgent.nativeWrapperPackageSourcesRoot": str(prepared_sources),
        "codexAgent.nativeWrapperPackageSdksRoot": str(sdks),
        "codexAgent.sdkCompatibilityRequest": str(request),
    }
    if binary is not None:
        fields["codexAgent.csharpBinaryStageRoot"] = str(binary)
        fields["codexAgent.csharpDotnetProfile"] = str(dotnet_profile)
    command = _runtime_worker_command(wrapper, fields, environment, build_directory=".")
    unchanged()
    if any(path.exists() or path.is_symlink() for path in owned):
        raise ValueError("Native SDK task output appeared before execution")
    started = time.monotonic_ns()
    return_code, launch_error = None, None
    try:
        with (destination / "gradle.log").open("xb") as log:
            process = subprocess.run(command, cwd=root, env=environment, stdout=log,
                                     stderr=subprocess.STDOUT, check=False)
            return_code = process.returncode
    except OSError as error:
        launch_error = str(error)
        raise
    finally:
        write_canonical_json(destination / "execution.json", {
            "schemaVersion": 1, "producer": dict(producer), "buildKey": plan["buildKey"],
            "command": command, "returnCode": return_code, "launchError": launch_error,
            "elapsedNs": time.monotonic_ns() - started,
        })
        unchanged()
    if return_code != 0:
        raise ValueError(f"Native SDK package failed with exit code {return_code}; see {destination / 'gradle.log'}")
    verify_output_manifest_identity(stage, "sdk", component, "package", "desktop", sdk_version)
    output_inventory = _inventory(stage)
    unchanged()
    return {"stage": stage, "diagnostics": destination, "outputInventory": output_inventory,
            "stagedSdks": sdks, "stagedSdkInventory": sdk_inventory}
