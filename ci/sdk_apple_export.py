"""Run the existing fresh Apple exporter inside caller-owned input authority.

This leaf neither authenticates S858 nor publishes or admits its outputs.  Its
caller must keep every supplied input verified through this call, then recheck
the returned inventories after its outer verification context exits.
"""

from collections.abc import Mapping
from pathlib import Path
import subprocess
import time
from typing import Any

from products.inventory import (
    load_canonical_json_bytes, read_regular_file_bytes, require_exact_keys,
    require_integer, require_sha256, write_canonical_json,
)
from products.receipt import validate_phase_receipt, validate_producer, verify_output_manifest_identity
from products.restore import PHASE_PLAN_KEYS
from products.sdk_inputs import REQUEST_NAME
from products.sdk_native_metadata import _inventory
from products.sdk_package import _require_capability_output_separate
from sdk_ios_phase import FRESH_EXPORT_TASK, fresh_export_properties


_LIMIT = 16 * 1024 * 1024
_GRADLE_ARGUMENTS = (
    "--offline", "--no-daemon", "--configuration-cache",
    "--configuration-cache-problems=fail", "-p", ".",
)


def execute(
    phase_plan: Mapping[str, Any], *, producer: Mapping[str, Any],
    current_contract: Mapping[str, Any], native_evidence: Path,
    compatibility_request: Path, destination: Path, repository_root: Path,
    environ: Mapping[str, str],
) -> dict[str, Any]:
    """Execute one fixed Apple export and retain diagnostics without publishing."""
    from native_wrappers import host_classifier
    from product_reuse import _prepare_destination, _runtime_worker_checkout, _runtime_worker_environment

    require_exact_keys(phase_plan, PHASE_PLAN_KEYS, "Apple SDK phase plan")
    if require_integer(phase_plan["schemaVersion"], "Apple SDK plan schema", 1) != 1:
        raise ValueError("Unsupported Apple SDK plan schema")
    require_sha256(phase_plan["buildKey"], "Elected Apple SDK build key")
    validate_producer(producer, "Elected Apple SDK producer")
    if host_classifier() != "macos-arm64":
        raise ValueError("Fresh Apple SDK export requires the actual macOS ARM64 host")

    root = Path(repository_root).resolve(strict=True)
    destination = Path(destination).absolute()
    contract_stage = Path(current_contract["stage"])
    contract_receipt = Path(current_contract["receiptPath"])
    native_evidence = Path(native_evidence)
    compatibility_request = Path(compatibility_request)
    if compatibility_request.name != REQUEST_NAME:
        raise ValueError("Fresh Apple export requires the exact verified S858 request")
    sdk_inputs = compatibility_request.parent
    originals = {
        "contract": (contract_stage, _inventory(contract_stage)),
        "native": (native_evidence, _inventory(native_evidence)),
        "sdk": (sdk_inputs, _inventory(sdk_inputs)),
    }
    receipt_bytes = read_regular_file_bytes(
        contract_receipt, max_bytes=_LIMIT, reject_symlink_parents=True,
    )
    if not receipt_bytes:
        raise ValueError("Fresh Apple Contract receipt is empty")
    receipt = validate_phase_receipt(load_canonical_json_bytes(receipt_bytes))
    if receipt != current_contract["receipt"] or tuple(receipt[field] for field in (
            "product", "component", "phase", "target")) != (
                "contract", "contract", "binary", "common"):
        raise ValueError("Fresh Apple Contract differs from its authenticated original receipt")
    manifest = verify_output_manifest_identity(
        contract_stage, "contract", "contract", "binary", "common", receipt["productVersion"],
    )
    if manifest["outputs"] != receipt["outputs"]:
        raise ValueError("Fresh Apple Contract stage differs from its original receipt")
    fields = fresh_export_properties(
        phase_plan, predecessor=lambda *identity: current_contract,
        native_evidence=native_evidence,
        compatibility_request=compatibility_request,
        candidate_commit=producer["commit"], candidate_tree=producer["tree"],
    )
    export_root = root / "build/apple-export" / producer["tree"]
    fields["codexAgent.appleExportBuildRoot"] = str(export_root)
    ios_build = export_root / "codex-agent-runtime-ios"
    distribution = ios_build / "apple-verified-distribution"
    execution = ios_build / "apple-verified-distribution-execution"
    inputs = [contract_receipt, *(path for path, _ in originals.values())]
    _require_capability_output_separate(destination, [distribution, execution, *inputs])
    _require_capability_output_separate(export_root, [destination, *inputs])
    _require_capability_output_separate(distribution, [execution, *inputs])
    _require_capability_output_separate(execution, inputs)
    if (export_root.exists() or export_root.is_symlink()
            or destination.exists() or destination.is_symlink()) or any(
            path.exists() or path.is_symlink() for path in (distribution, execution)):
        raise ValueError("Fresh Apple export requires fresh diagnostics and output roots")
    _prepare_destination(export_root, root).rmdir()
    environment, wrapper = _runtime_worker_environment(root, producer, destination, environ)
    destination = _prepare_destination(destination, root)

    def unchanged() -> None:
        _runtime_worker_checkout(root, producer)
        bytecode = destination / "python-bytecode"
        if bytecode.exists() or bytecode.is_symlink():
            raise ValueError("Fresh Apple private bytecode namespace was modified")
        if any(_inventory(source) != inventory for source, inventory in originals.values()):
            raise ValueError("Original fresh Apple input changed during export")
        if read_regular_file_bytes(
                contract_receipt, max_bytes=_LIMIT, reject_symlink_parents=True) != receipt_bytes:
            raise ValueError("Fresh Apple Contract receipt changed during export")

    unchanged()
    if export_root.exists() or export_root.is_symlink():
        raise ValueError("Fresh Apple output appeared before execution")
    command = [str(wrapper), *_GRADLE_ARGUMENTS, FRESH_EXPORT_TASK,
               *(f"-P{key}={value}" for key, value in sorted(fields.items()))]
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
            "buildKey": phase_plan["buildKey"], "command": command,
            "returnCode": return_code, "launchError": launch_error,
            "elapsedNs": time.monotonic_ns() - started,
        })
        unchanged()
    if return_code != 0:
        raise ValueError(
            f"Fresh Apple export failed with exit code {return_code}; see {destination / 'gradle.log'}",
        )
    inventories = {
        "distribution": _inventory(distribution),
        "execution": _inventory(execution, allow_empty=True),
    }
    unchanged()
    return {
        "distribution": distribution, "execution": execution,
        "diagnostics": destination, "inventories": inventories,
    }
