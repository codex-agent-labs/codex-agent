"""Execute JS SDK phases inside the caller's verified original-input lifetime.

Returned outputs are not admitted evidence. The caller must successfully exit
its input verification contexts, recheck outputInventory, then finalize the phase.
"""

from collections.abc import Callable, Mapping
from pathlib import Path
import subprocess
import time
from typing import Any

from products.inventory import (
    load_canonical_json_bytes, read_regular_file_bytes, require_exact_keys,
    require_integer, require_semver, require_sha256, write_canonical_json,
)
from products.receipt import validate_phase_receipt, validate_producer, verify_output_manifest_identity
from products.restore import PHASE_PLAN_KEYS
from products.sdk_native_metadata import _inventory
from products.sdk_package import _require_capability_output_separate
from products.sdk_validation_inputs import _request_inventory
from sdk_phase import properties, route


_LIMIT = 16 * 1024 * 1024


def execute(
    plan: Mapping[str, Any], *, producer: Mapping[str, Any], sdk_version: str,
    trust_domain: str, repository_root: Path, destination: Path,
    predecessor: Callable[[str, str, str, str], Mapping[str, Any]],
    environ: Mapping[str, str], compatibility_request: Path | None = None,
) -> dict[str, Any]:
    """Run only fixed root ciProductPhase; never finalize or publish a shard."""
    from native_wrappers import HOSTS, host_classifier
    from product_reuse import (
        _prepare_destination, _runtime_worker_checkout, _runtime_worker_command,
        _runtime_worker_environment,
    )

    require_exact_keys(plan, PHASE_PLAN_KEYS, "JavaScript SDK phase plan")
    if require_integer(plan["schemaVersion"], "JavaScript SDK plan schema", 1) != 1:
        raise ValueError("Unsupported JavaScript SDK plan schema")
    elected_route = route(plan)
    require_sha256(plan["buildKey"], "Elected JavaScript SDK build key")
    validate_producer(producer, "Elected JavaScript SDK producer")
    require_semver(sdk_version, "Elected SDK version")
    if trust_domain not in {"development", "release"}:
        raise ValueError("Invalid elected SDK trust domain")
    if HOSTS[host_classifier()][2:4] != (elected_route["runnerOs"], elected_route["runnerArch"]):
        raise ValueError("JavaScript SDK worker actual host differs from its elected route")
    root = Path(repository_root).resolve(strict=True)
    destination = Path(destination).absolute()
    stage = root / f"codex-agent-sdk/build/product-stage/sdk/javascript/{plan['phase']}"
    if destination.exists() or destination.is_symlink() or stage.exists() or stage.is_symlink():
        raise ValueError("JavaScript SDK worker requires fresh diagnostic and product outputs")
    originals = []

    def original(*identity):
        value = predecessor(*identity)
        receipt_path = Path(value["receiptPath"])
        raw = read_regular_file_bytes(receipt_path, max_bytes=_LIMIT, reject_symlink_parents=True)
        receipt = validate_phase_receipt(load_canonical_json_bytes(raw))
        if receipt != value["receipt"] or tuple(receipt[key] for key in (
                "product", "component", "phase", "target")) != identity:
            raise ValueError("JavaScript SDK predecessor differs from its original receipt")
        if identity[0] == "sdk" and receipt["productVersion"] != sdk_version:
            raise ValueError("Original SDK package version differs from the elected SDK version")
        manifest = verify_output_manifest_identity(value["stage"], *identity, receipt["productVersion"])
        if manifest["outputs"] != receipt["outputs"]:
            raise ValueError("JavaScript SDK predecessor stage differs from its original receipt")
        originals.append((Path(value["stage"]), _inventory(value["stage"]), receipt_path, raw))
        return value

    fields = properties(plan, predecessor=original, compatibility_request=compatibility_request)
    request_bytes = None
    request_inventory = {}
    if compatibility_request is not None:
        request_bytes = read_regular_file_bytes(compatibility_request, max_bytes=_LIMIT, reject_symlink_parents=True)
        request_inventory = _request_inventory(compatibility_request)
    inputs = [path for tree, _, receipt, _ in originals for path in (tree, receipt)]
    if compatibility_request is not None:
        inputs.extend((compatibility_request, *request_inventory))
    _require_capability_output_separate(destination, [stage, *inputs])
    _require_capability_output_separate(stage, inputs)
    environment, wrapper = _runtime_worker_environment(root, producer, destination, environ)
    _prepare_destination(stage, root).rmdir()
    destination = _prepare_destination(destination, root)
    fields.update({"codexAgent.product": "sdk", "codexAgent.component": "javascript",
        "codexAgent.phase": plan["phase"], "codexAgent.target": "node",
        "codexAgent.candidateCommit": producer["commit"], "codexAgent.candidateTree": producer["tree"]})

    def unchanged():
        _runtime_worker_checkout(root, producer)
        bytecode = destination / "python-bytecode"
        if bytecode.exists() or bytecode.is_symlink():
            raise ValueError("JavaScript SDK private bytecode namespace was modified")
        if any(_inventory(tree) != inventory or read_regular_file_bytes(
                receipt, max_bytes=_LIMIT, reject_symlink_parents=True) != raw
                for tree, inventory, receipt, raw in originals):
            raise ValueError("Original JavaScript SDK worker inputs changed")
        if compatibility_request is not None and (read_regular_file_bytes(
                compatibility_request, max_bytes=_LIMIT, reject_symlink_parents=True) != request_bytes
                or _request_inventory(compatibility_request) != request_inventory):
            raise ValueError("Original SDK compatibility request or inputs changed")

    unchanged()
    if stage.exists() or stage.is_symlink():
        raise ValueError("JavaScript SDK product stage appeared before execution")
    command = _runtime_worker_command(wrapper, fields, environment, build_directory=".")
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
        write_canonical_json(destination / "execution.json", {"schemaVersion": 1,
            "producer": dict(producer), "buildKey": plan["buildKey"], "command": command,
            "returnCode": return_code, "launchError": launch_error,
            "elapsedNs": time.monotonic_ns() - started})
        unchanged()
    if return_code != 0:
        raise ValueError(f"JavaScript SDK phase failed with exit code {return_code}; see {destination / 'gradle.log'}")
    verify_output_manifest_identity(stage, "sdk", "javascript", plan["phase"], "node", sdk_version)
    output_inventory = _inventory(stage)
    unchanged()
    return {"stage": stage, "diagnostics": destination, "outputInventory": output_inventory}
