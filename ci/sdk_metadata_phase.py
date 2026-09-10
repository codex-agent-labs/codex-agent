"""Execute the existing artifact-only native SDK metadata phase.

The shared caller elects the plan and authenticates predecessor/source authority.
This worker preserves their original bytes, uses the existing execution guards,
and publishes a shard only after the full original-source metadata admission.
"""

from collections.abc import Callable, Mapping
from pathlib import Path
import subprocess
import tempfile
import time
from typing import Any

from products.inventory import (
    load_canonical_json_bytes, publish_regular_tree,
    read_regular_file_bytes, require_exact_keys, require_integer,
    require_semver, require_sha256, snapshot_regular_tree, write_canonical_json,
)
from products.receipt import validate_phase_receipt, validate_producer, verify_output_manifest_identity
from products.registry import NATIVE_BINDINGS, NATIVE_TARGETS, PhaseInstanceId
from products.restore import PHASE_PLAN_KEYS, finalize_phase_object, verify_phase_shard
from products.sdk_inputs import REQUEST_NAME, stage_sdk_inputs
from products.sdk_native_metadata import _inventory
from products.sdk_native_metadata_admission import verify_sdk_native_metadata_admission
from products.sdk_package import _require_capability_output_separate
from products.sdk_validation import VerifiedSdkValidationProjection
from products.sdk_validation_inputs import _request_inventory


_LIMIT = 16 * 1024 * 1024


def execute(
    plan: Mapping[str, Any], *, producer: Mapping[str, Any], sdk_version: str,
    trust_domain: str, repository_root: Path, destination: Path,
    predecessor: Callable[[str, str, str, str], Mapping[str, Any]],
    compatibility_request: Path, runtime_stages: Path, staged_sdks: Path,
    sdk_validation_projections: tuple[VerifiedSdkValidationProjection, ...],
    tooling_evidence: Path, tooling_public_key: Path, java_executable: Path,
    policy_revision: str, required_trust_domain: str, environ: Mapping[str, str],
    tooling_keyring: Path | None = None, tooling_keys_directory: Path | None = None,
) -> dict[str, Any]:
    """Run fixed root ciProductPhase; imported process success alone never admits."""
    from product_reuse import (
        _prepare_destination, _runtime_worker_checkout, _runtime_worker_command,
        _runtime_worker_environment,
    )

    require_exact_keys(plan, PHASE_PLAN_KEYS, "Native SDK metadata plan")
    if require_integer(plan["schemaVersion"], "Metadata plan schema", 1) != 1:
        raise ValueError("Unsupported metadata plan schema")
    component = plan["component"]
    if (plan["product"], plan["phase"], plan["target"]) != ("sdk", "metadata", "desktop") or component not in NATIVE_BINDINGS:
        raise ValueError("Only native SDK metadata has an implemented worker")
    require_sha256(plan["buildKey"], "Elected metadata build key")
    validate_producer(producer, "Elected metadata producer")
    require_semver(sdk_version, "Elected SDK version")
    if trust_domain not in {"development", "release"}:
        raise ValueError("Invalid elected SDK trust domain")
    root = Path(repository_root).resolve(strict=True)
    destination = Path(destination).absolute()
    stage = root / f"codex-agent-sdk/build/product-stage/sdk/{component}/metadata"
    if destination.exists() or destination.is_symlink() or stage.exists() or stage.is_symlink():
        raise ValueError("Native SDK worker requires fresh diagnostic and product outputs")
    request = Path(compatibility_request)
    request_bytes = read_regular_file_bytes(request, max_bytes=_LIMIT, reject_symlink_parents=True)
    request_inventory = _request_inventory(request)
    trees = {"runtime": Path(runtime_stages), "sdks": Path(staged_sdks)}
    receipts, raw = {}, {}
    identities = [("package", "desktop"), *(("validation", target) for target in sorted(NATIVE_TARGETS))]
    for phase, target in identities:
        original = predecessor("sdk", component, phase, target)
        name = "package" if phase == "package" else f"validation/{target}"
        receipt_path = Path(original["receiptPath"])
        contents = read_regular_file_bytes(receipt_path, max_bytes=_LIMIT, reject_symlink_parents=True)
        receipt = validate_phase_receipt(load_canonical_json_bytes(contents))
        if receipt != original["receipt"] or tuple(receipt[key] for key in ("product", "component", "phase", "target")) != (
                "sdk", component, phase, target) or receipt["productVersion"] != sdk_version:
            raise ValueError("Native SDK predecessor differs from its elected original receipt")
        original_stage = Path(original["stage"])
        manifest = verify_output_manifest_identity(original_stage, "sdk", component, phase, target, sdk_version)
        if manifest["outputs"] != receipt["outputs"]:
            raise ValueError("Native SDK predecessor stage differs from its original receipt")
        trees[name] = original_stage
        receipts[name] = receipt_path
        raw[name] = contents
    original_inventory = {name: _inventory(path) for name, path in trees.items()}
    inputs = [*trees.values(), *receipts.values(), request, *request_inventory,
              Path(tooling_evidence), Path(tooling_public_key), Path(java_executable),
              *(Path(path) for path in (tooling_keyring, tooling_keys_directory) if path is not None)]
    _require_capability_output_separate(destination, [stage, *inputs])
    _require_capability_output_separate(stage, inputs)
    environment, wrapper = _runtime_worker_environment(root, producer, destination, environ)
    _prepare_destination(stage, root).rmdir()
    destination = _prepare_destination(destination, root)
    captured = destination / "inputs"
    for name, source in trees.items():
        snapshot_regular_tree(source, captured / name)
        if _inventory(captured / name) != original_inventory[name]:
            raise ValueError("Native SDK predecessor changed during capture")
    for name, contents in raw.items():
        output = captured / "receipts" / f"{name}.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(contents)
    stage_sdk_inputs(request, captured / "sdk-inputs")
    arguments = dict(package_stage=captured / "package", package_receipt=captured / "receipts/package.json",
        compatibility_request=captured / "sdk-inputs" / REQUEST_NAME, runtime_stages=captured / "runtime",
        staged_sdks=captured / "sdks", validation_stages=captured / "validation",
        validation_receipts=captured / "receipts/validation")
    properties = {"codexAgent.product": "sdk", "codexAgent.component": component,
        "codexAgent.phase": "metadata", "codexAgent.target": "desktop",
        "codexAgent.candidateCommit": producer["commit"], "codexAgent.candidateTree": producer["tree"]}
    properties.update({key: str(arguments[name]) for key, name in {
        "codexAgent.sdkPackageStageRoot": "package_stage", "codexAgent.sdkPackageReceipt": "package_receipt",
        "codexAgent.sdkCompatibilityRequest": "compatibility_request", "codexAgent.nativeWrapperRuntimeStageRoot": "runtime_stages",
        "codexAgent.nativeWrapperStagedSdkRoot": "staged_sdks", "codexAgent.sdkValidationStagesRoot": "validation_stages",
        "codexAgent.sdkValidationReceiptsRoot": "validation_receipts",
    }.items()})
    captured_inventory = _inventory(captured, allow_empty=True)

    def unchanged():
        _runtime_worker_checkout(root, producer)
        if (destination / "python-bytecode").exists() or (destination / "python-bytecode").is_symlink():
            raise ValueError("Native SDK private bytecode namespace was modified")
        if _inventory(captured, allow_empty=True) != captured_inventory or any(
                _inventory(source) != original_inventory[name] for name, source in trees.items()):
            raise ValueError("Original or captured native SDK worker inputs changed")
        if any(read_regular_file_bytes(path, max_bytes=_LIMIT, reject_symlink_parents=True) != raw[name]
               for name, path in receipts.items()) or read_regular_file_bytes(
                   request, max_bytes=_LIMIT, reject_symlink_parents=True) != request_bytes or _request_inventory(request) != request_inventory:
            raise ValueError("Original SDK receipts or compatibility request changed")

    unchanged()
    if stage.exists() or stage.is_symlink():
        raise ValueError("Native SDK product stage appeared before execution")
    command = _runtime_worker_command(wrapper, properties, environment, build_directory=".")
    started = time.monotonic_ns()
    with (destination / "gradle.log").open("xb") as log:
        process = subprocess.run(command, cwd=root, env=environment, stdout=log, stderr=subprocess.STDOUT, check=False)
    write_canonical_json(destination / "execution.json", {"schemaVersion": 1, "producer": dict(producer),
        "buildKey": plan["buildKey"], "command": command, "returnCode": process.returncode,
        "elapsedNs": time.monotonic_ns() - started})
    if process.returncode != 0:
        raise ValueError(f"Native SDK metadata failed with exit code {process.returncode}; see {destination / 'gradle.log'}")
    unchanged()
    output_inventory = _inventory(stage)
    with tempfile.TemporaryDirectory(prefix="sdk-metadata-candidate-") as temporary:
        candidate = Path(temporary).resolve() / "shard"
        finalized = finalize_phase_object(stage_root=stage, phase_plan=plan, producer=producer,
            product_version=sdk_version, trust_domain=trust_domain, destination=candidate)
        verified, original = verify_sdk_native_metadata_admission(repository=root, component=component,
            metadata_stage=stage, metadata_receipt=candidate / "phase-receipt.json", **arguments,
            sdk_validation_projections=sdk_validation_projections, tooling_evidence=tooling_evidence,
            tooling_public_key=tooling_public_key, java_executable=java_executable,
            policy_revision=policy_revision, required_trust_domain=required_trust_domain,
            tooling_keyring=tooling_keyring, tooling_keys_directory=tooling_keys_directory)
        if verified != finalized["receipt"] or original != read_regular_file_bytes(candidate / "phase-receipt.json"):
            raise ValueError("Native SDK admission returned a different candidate receipt")
        unchanged()
        if _inventory(stage) != output_inventory:
            raise ValueError("Native SDK metadata output changed after finalization")
        # Reauthenticate the exact candidate object after the full semantic gate.
        if verify_phase_shard(candidate, PhaseInstanceId("sdk", component, "metadata", "desktop")) != finalized:
            raise ValueError("Native SDK candidate shard changed after admission")
        publish_regular_tree(candidate, destination / "shard")
    return verify_phase_shard(destination / "shard", PhaseInstanceId("sdk", component, "metadata", "desktop"))
