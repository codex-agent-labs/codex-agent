"""Prepare all native SDK inputs once inside the caller's verified lifetime.

An elected native package, validation or metadata plan supplies diagnostic
identity, not a new product phase. Preparation itself always runs on Linux X64.
Returned trees are not an authenticated upload: the controller must successfully
exit its input contexts, recheck inventories and bind the exact prepared source
upload to the original producer and selected source plan before language jobs.
"""

from collections.abc import Callable, Mapping
from pathlib import Path
import subprocess
import time
from typing import Any

from products.inventory import (
    canonical_json_bytes, git_regular_blob_bytes, read_regular_file_bytes, require_exact_keys,
    require_integer, require_semver, require_sha256, require_string, write_canonical_json,
)
from products.receipt import compute_build_key, validate_producer
from products.registry import NATIVE_BINDINGS, NATIVE_TARGETS, PHASE_INSTANCE_IDS, PhaseInstanceId
from products.restore import PHASE_PLAN_KEYS
from products.sdk_native import SDK_ROOT_PATH, verify_staged_native_sdk_inputs
from products.sdk_native_metadata import _inventory
from products.sdk_package import _require_capability_output_separate
from products.sdk_validation_inputs import _request_inventory
from sdk_native_phase import _runtime_originals, _runtime_originals_unchanged


TASK = ":codex-agent-sdk:prepareNativeWrapperPackageSources"
_LIMIT = 16 * 1024 * 1024


def validate_anchor(plan: Mapping[str, Any]) -> PhaseInstanceId:
    """Validate the unchanged ready-plan identity; never elect or forge a phase."""
    require_exact_keys(plan, PHASE_PLAN_KEYS, "Native SDK preparation elected plan")
    if require_integer(plan["schemaVersion"], "Native SDK preparation schema", 1) != 1:
        raise ValueError("Unsupported native SDK preparation plan schema")
    identity = PhaseInstanceId(*(require_string(plan[name], f"Native SDK preparation {name}")
                                 for name in ("product", "component", "phase", "target")))
    if (identity not in PHASE_INSTANCE_IDS or identity.product != "sdk" or identity.component not in NATIVE_BINDINGS
            or not ((identity.phase in {"package", "metadata"} and identity.target == "desktop")
                    or (identity.phase == "validation" and identity.target in NATIVE_TARGETS))):
        raise ValueError("Native SDK preparation requires an exact package, validation or metadata anchor")
    key = require_sha256(plan["buildKey"], "Native SDK preparation elected key")
    if compute_build_key(**{name: plan[name] for name in ("product", "component", "phase", "target", "inputs")}) != key:
        raise ValueError("Native SDK preparation identity or inputs differ from its original build key")
    return identity


def execute(
    plan: Mapping[str, Any], *, producer: Mapping[str, Any], sdk_version: str,
    repository_root: Path, destination: Path, runtime_stages: Path,
    compatibility_request: Path,
    predecessor: Callable[[str, str, str, str], Mapping[str, Any]],
    environ: Mapping[str, str],
) -> dict[str, Any]:
    """Execute the sole existing preparation task; never package or admit shards."""
    from native_wrappers import host_classifier
    from product_reuse import (
        _prepare_destination, _runtime_worker_checkout, _runtime_worker_command,
        _runtime_worker_environment,
    )

    validate_anchor(plan)
    validate_producer(producer, "Native SDK preparation producer")
    require_semver(sdk_version, "Native SDK preparation version")
    if host_classifier() != "linux-x64":
        raise ValueError("Native SDK preparation requires the actual Linux X64 host")
    root = Path(repository_root).resolve(strict=True)
    destination = Path(destination).absolute()
    runtime, request = Path(runtime_stages), Path(compatibility_request)
    if not runtime.is_absolute() or not request.is_absolute():
        raise ValueError("Native SDK preparation requires absolute original inputs")
    runtime_inventory = _inventory(runtime)
    request_bytes = read_regular_file_bytes(request, max_bytes=_LIMIT, reject_symlink_parents=True)
    request_inventory = _request_inventory(request)
    plan_bytes, producer_bytes = canonical_json_bytes(plan), canonical_json_bytes(producer)
    originals = _runtime_originals(runtime, runtime_inventory, predecessor)
    build = root / "codex-agent-sdk/build"
    tree = producer["tree"]
    sources = build / "native-wrapper-package-sources"
    sdks = build / f"native-wrapper-c-abi-sdks/{tree}"
    owned = (sources, sdks, build / f"imported-native-wrapper-runtime-stages/{tree}",
             build / f"native-wrapper-package-assets/{tree}", build / f"sdk-compatibility/{tree}")
    if any(path.exists() or path.is_symlink() for path in (*owned, destination)):
        raise ValueError("Native SDK preparation requires fresh diagnostics and prepared outputs")
    inputs = [runtime, request, *request_inventory,
              *(path for original, _, receipt, _ in originals for path in (original, receipt))]
    _require_capability_output_separate(destination, [*owned, *inputs])
    for output in owned:
        _require_capability_output_separate(output, inputs)
    environment, wrapper = _runtime_worker_environment(root, producer, destination, environ, build_directory=".")

    def unchanged():
        _runtime_worker_checkout(root, producer)
        bytecode = destination / "python-bytecode"
        if bytecode.exists() or bytecode.is_symlink():
            raise ValueError("Native SDK preparation private bytecode namespace was modified")
        if canonical_json_bytes(plan) != plan_bytes or canonical_json_bytes(producer) != producer_bytes:
            raise ValueError("Native SDK preparation elected plan or producer changed")
        _runtime_originals_unchanged(runtime, runtime_inventory, originals)
        if (read_regular_file_bytes(request, max_bytes=_LIMIT, reject_symlink_parents=True) != request_bytes
                or _request_inventory(request) != request_inventory):
            raise ValueError("Original SDK preparation compatibility request or inputs changed")

    unchanged()
    for output in owned:
        _prepare_destination(output, root).rmdir()
    destination = _prepare_destination(destination, root)
    properties = {
        "codexAgent.candidateCommit": producer["commit"], "codexAgent.candidateTree": tree,
        "codexAgent.nativeWrapperRuntimeStageRoot": str(runtime),
        "codexAgent.sdkCompatibilityRequest": str(request),
    }
    command = _runtime_worker_command(wrapper, properties, environment, build_directory=".")
    command[command.index("ciProductPhase")] = TASK
    unchanged()
    if any(path.exists() or path.is_symlink() for path in owned):
        raise ValueError("Native SDK preparation output appeared before execution")
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
        raise ValueError(f"Native SDK preparation failed with exit code {return_code}; see {destination / 'gradle.log'}")
    source_inventory, sdk_inventory = _inventory(sources), _inventory(sdks)
    if {path.name for path in sources.iterdir()} != set(NATIVE_BINDINGS):
        raise ValueError("Native SDK preparation must produce exactly five language source directories")
    for language in NATIVE_BINDINGS:
        if not _inventory(sources / language):
            raise ValueError("Native SDK prepared language source must not be empty")
    try:
        index = verify_staged_native_sdk_inputs(
            sdks, request, runtime,
            git_regular_blob_bytes(root, producer["commit"], SDK_ROOT_PATH, max_bytes=4096),
        )
        if (index["sdkVersion"] != sdk_version or index["producerCommit"] != producer["commit"]
                or index["producerTree"] != tree):
            raise ValueError("Prepared native SDK staging differs from its elected version or producer")
    finally:
        unchanged()
    if _inventory(sources) != source_inventory or _inventory(sdks) != sdk_inventory:
        raise ValueError("Prepared native SDK outputs changed during verification")
    return {"preparedSources": sources, "preparedSourcesInventory": source_inventory,
            "stagedSdks": sdks, "stagedSdkInventory": sdk_inventory, "diagnostics": destination}
