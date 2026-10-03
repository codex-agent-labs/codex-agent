"""Run imported JavaScript metadata inside the caller's authenticated lifetime.

The caller authenticates the validation upload's original consumer directory.
This leaf neither infers it from commands nor finalizes/adopts any phase receipt.
The caller privately finalizes once, runs full admission, and publishes only
after all enclosing input contexts have exited successfully.
"""

from collections.abc import Callable, Mapping
from pathlib import Path
import os
import subprocess
import time
from typing import Any

from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, read_regular_file_bytes,
    require_exact_keys, require_integer, require_semver, require_sha256, write_canonical_json,
)
from products.receipt import validate_phase_receipt, validate_producer, verify_output_manifest_identity
from products.restore import PHASE_PLAN_KEYS
from products.sdk_native_metadata import _inventory
from products.sdk_package import _require_capability_output_separate


_LIMIT = 16 * 1024 * 1024
_IDENTITIES = (
    ("contract", "contract", "binary", "common"),
    ("sdk", "javascript", "package", "node"),
    ("sdk", "javascript", "validation", "node"),
    ("runtime", "node-js", "validation", "node-js-binding"),
)


def execute(
    plan: Mapping[str, Any], *, producer: Mapping[str, Any], sdk_version: str,
    trust_domain: str, repository_root: Path, destination: Path,
    predecessor: Callable[[str, str, str, str], Mapping[str, Any]],
    original_consumer_directory: Path, environ: Mapping[str, str],
) -> dict[str, Any]:
    from native_wrappers import HOSTS, host_classifier
    from product_reuse import (
        _prepare_destination, _runtime_worker_checkout, _runtime_worker_command, _runtime_worker_environment,
    )

    require_exact_keys(plan, PHASE_PLAN_KEYS, "JavaScript metadata elected plan")
    if (require_integer(plan["schemaVersion"], "JavaScript metadata schema", 1) != 1
            or tuple(plan[field] for field in ("product", "component", "phase", "target")) !=
            ("sdk", "javascript", "metadata", "node")):
        raise ValueError("Unsupported JavaScript metadata phase")
    require_sha256(plan["buildKey"], "JavaScript metadata elected key")
    validate_producer(producer, "JavaScript metadata producer")
    require_semver(sdk_version, "JavaScript metadata SDK version")
    if trust_domain not in {"development", "release"}:
        raise ValueError("Invalid JavaScript metadata trust domain")
    if HOSTS[host_classifier()][2:4] != ("Linux", "X64"):
        raise ValueError("JavaScript metadata worker requires its actual Linux X64 route")
    original_consumer_directory = Path(original_consumer_directory)
    if (not original_consumer_directory.is_absolute()
            or original_consumer_directory != Path(os.path.normpath(original_consumer_directory))):
        raise ValueError("JavaScript metadata requires its authenticated original consumer directory")
    root = Path(repository_root).resolve(strict=True)
    destination = Path(destination).absolute()
    build = root / "codex-agent-sdk/build"
    stage = build / "product-stage/sdk/javascript/metadata"
    owned = (stage, build / f"imported-sdk-product-stages/{producer['tree']}/javascript-metadata",
             build / "javascript-metadata/installed-package",
             build / "reports/npm/metadata-sdk-compatibility-archive.json",
             build / "reports/javascript-metadata/javascript-typescript-parity.json")
    if any(path.exists() or path.is_symlink() for path in (*owned, destination)):
        raise ValueError("JavaScript metadata requires fresh diagnostic, snapshot and product outputs")
    plan_bytes, producer_bytes = canonical_json_bytes(plan), canonical_json_bytes(producer)
    originals = {}
    # Capture all four original inventories/receipt bytes before any original
    # receipt or manifest verifier, including verifiers for earlier members.
    for identity in _IDENTITIES:
        value = predecessor(*identity)
        source, receipt_path = Path(value["stage"]), Path(value["receiptPath"])
        if not source.is_absolute() or not receipt_path.is_absolute():
            raise ValueError("JavaScript metadata requires absolute original predecessor paths")
        originals[identity] = (source, _inventory(source), receipt_path,
            read_regular_file_bytes(receipt_path, max_bytes=_LIMIT, reject_symlink_parents=True), value["receipt"])

    def originals_unchanged():
        if (canonical_json_bytes(plan) != plan_bytes or canonical_json_bytes(producer) != producer_bytes
                or any(_inventory(source) != inventory or read_regular_file_bytes(
                    path, max_bytes=_LIMIT, reject_symlink_parents=True) != raw
                    for source, inventory, path, raw, _ in originals.values())):
            raise ValueError("JavaScript metadata original inputs changed during execution")

    receipts = {}
    for identity, (source, _, _, raw, supplied) in originals.items():
        receipt = validate_phase_receipt(load_canonical_json_bytes(raw))
        if receipt != supplied or tuple(receipt[field] for field in ("product", "component", "phase", "target")) != identity:
            raise ValueError("JavaScript metadata predecessor receipt has a different identity")
        if identity[0] == "sdk" and receipt["productVersion"] != sdk_version:
            raise ValueError("JavaScript metadata original SDK version differs from its election")
        manifest = verify_output_manifest_identity(source, *identity, receipt["productVersion"])
        if manifest["outputs"] != receipt["outputs"]:
            raise ValueError("JavaScript metadata original stage differs from its receipt")
        originals_unchanged()
        receipts[identity] = receipt
    inputs = [path for source, _, receipt, _, _ in originals.values() for path in (source, receipt)]
    _require_capability_output_separate(destination, [*owned, *inputs])
    for output in owned:
        _require_capability_output_separate(output, inputs)
    environment, wrapper = _runtime_worker_environment(root, producer, destination, environ)
    for output in owned:
        _prepare_destination(output, root).rmdir()
    destination = _prepare_destination(destination, root)
    contract, package, validation, runtime = _IDENTITIES
    fields = {"codexAgent.product": "sdk", "codexAgent.component": "javascript",
        "codexAgent.phase": "metadata", "codexAgent.target": "node",
        "codexAgent.candidateCommit": producer["commit"], "codexAgent.candidateTree": producer["tree"],
        "codexAgent.contractBinaryStage": str(originals[contract][0]),
        "codexAgent.sdkPackageStageRoot": str(originals[package][0]),
        "codexAgent.sdkValidationStageRoot": str(originals[validation][0]),
        "codexAgent.runtimeBindingValidationStage": str(originals[runtime][0]),
        "codexAgent.runtimeBindingValidationVersion": receipts[runtime]["productVersion"],
        "codexAgent.sdkOriginalConsumerDirectory": str(original_consumer_directory)}

    def unchanged():
        _runtime_worker_checkout(root, producer)
        bytecode = destination / "python-bytecode"
        if bytecode.exists() or bytecode.is_symlink():
            raise ValueError("JavaScript metadata private bytecode namespace was modified")
        originals_unchanged()

    unchanged()
    if any(path.exists() or path.is_symlink() for path in owned):
        raise ValueError("JavaScript metadata output appeared before execution")
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
            "workingDirectory": str(root), "returnCode": return_code, "launchError": launch_error,
            "elapsedNs": time.monotonic_ns() - started})
        unchanged()
    if return_code != 0:
        raise ValueError(f"JavaScript metadata failed with exit code {return_code}; see {destination / 'gradle.log'}")
    output_inventory = _inventory(stage)
    manifest = verify_output_manifest_identity(stage, "sdk", "javascript", "metadata", "node", sdk_version)
    if (len(manifest["outputs"]) != 1 or manifest["outputs"][0]["kind"] != "binding-evidence"
            or manifest["outputs"][0]["relativePath"] != "outputs/binding-evidence/javascript-typescript-parity.json"):
        raise ValueError("JavaScript metadata requires its sole exact semantic output")
    unchanged()
    if _inventory(stage) != output_inventory:
        raise ValueError("JavaScript metadata output changed during manifest verification")
    return {"stage": stage, "diagnostics": destination, "outputInventory": output_inventory}
