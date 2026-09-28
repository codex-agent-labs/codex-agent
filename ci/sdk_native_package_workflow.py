"""Consume one authenticated preparation upload without restaging five SDKs."""

import argparse
import os
from pathlib import Path
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse
import sdk_workflow
from sdk_metadata_policy import add_metadata_admission_arguments, metadata_admission_options
from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, publish_regular_tree,
    read_regular_file_bytes, regular_file_inventory, snapshot_regular_tree,
)
from products.registry import NATIVE_BINDINGS, NATIVE_TARGETS, PhaseInstanceId
from products.restore import PHASE_PLAN_KEYS, PHASE_RECEIPT_NAME, verify_phase_shard
from products.sdk_inputs import REQUEST_NAME
from products.sdk_package import _require_capability_output_separate, verify_sdk_package_inputs
from sdk_native_phase import execute as execute_package


def execute(plan, discovery, state, destination, *, component, expected_build_key,
            preparation_component, preparation_build_key, preparation_state,
            prepared_artifact_id, prepared_artifact_sha256,
            sdk_inputs_artifact_id, sdk_inputs_artifact_sha256, trusted_workflow_sha,
            keyring, keys_directory, repository_root, environ, token, sdk_validation_tooling=None,
            sdk_apple_validation_policy=None, sdk_facade_metadata_admission=None,
            sdk_android_metadata_admission=None):
    """Admit one package inside full S858/original Runtime input verification.

    Preparation identity comes from replaying its original control state, never
    uploaded JSON. Transport capture alone cannot admit its source or SDK bytes.
    The private candidate becomes public only after every input context exits.
    """
    if component not in NATIVE_BINDINGS or preparation_component not in NATIVE_BINDINGS:
        raise ValueError("Native package execution requires fixed native language components")
    root = Path(repository_root).resolve(strict=True)
    plan = Path(plan).absolute()
    discovery, state, destination = product_reuse._product_materialization_paths(root, discovery, state, destination)
    _, preparation_state, _ = product_reuse._product_materialization_paths(
        root, discovery, preparation_state, destination)
    protected = [plan, discovery, state, preparation_state, Path(keyring), Path(keys_directory)]
    _require_capability_output_separate(destination, protected)
    # Product workers are confined to the candidate repository; no caller output
    # may become a cleanup target outside it.
    destination.relative_to(root)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Native package destination must not exist")
    controls = {path: regular_file_inventory(path, allow_empty=True)
                for path in {discovery, state, preparation_state}}
    plan_bytes = read_regular_file_bytes(plan, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)

    def controls_unchanged():
        if (any(regular_file_inventory(path, allow_empty=True) != inventory for path, inventory in controls.items())
                or read_regular_file_bytes(plan, max_bytes=16 * 1024 * 1024,
                                           reject_symlink_parents=True) != plan_bytes):
            raise ValueError("Native package original election state or plan changed")

    instance = PhaseInstanceId("sdk", component, "package", "desktop")
    identity = {"product": "sdk", "component": component, "phase": "package", "target": "desktop"}
    preparation_identity = {**identity, "component": preparation_component}
    tooling = {"sdk_validation_tooling": sdk_validation_tooling} if sdk_validation_tooling is not None else {}
    if sdk_apple_validation_policy is not None:
        tooling["sdk_apple_validation_policy"] = sdk_apple_validation_policy
    if sdk_facade_metadata_admission is not None:
        tooling["sdk_facade_metadata_admission"] = sdk_facade_metadata_admission
    if sdk_android_metadata_admission is not None:
        tooling["sdk_android_metadata_admission"] = sdk_android_metadata_admission
    with tempfile.TemporaryDirectory(prefix="sdk-native-package-") as temporary:
        private = Path(temporary).resolve()
        candidate, capture = private / "shard", private / "prepared-upload"
        with sdk_workflow.verified_inputs(plan, discovery, state,
                artifact_id=sdk_inputs_artifact_id, artifact_sha256=sdk_inputs_artifact_sha256,
                trusted_workflow_sha=trusted_workflow_sha, keyring=keyring, keys_directory=keys_directory,
                repository_root=root, environ=environ, token=token, **tooling) as inputs:
            controls_unchanged()
            selection = inputs["selection"]
            if identity not in selection["consumers"]:
                raise ValueError("Native SDK package is not selected")
            inspected = product_reuse.inspect_products(plan, discovery, preparation_state,
                repository_root=root, environ=environ,
                sdk_original_workflow_sha=trusted_workflow_sha, **tooling)
            elected = [row for row in inspected["readyPlans"]
                       if all(row.get(name) == value for name, value in preparation_identity.items())]
            if (len(elected) != 1 or set(elected[0]) != PHASE_PLAN_KEYS
                    or elected[0]["buildKey"] != preparation_build_key):
                raise ValueError("Original native preparation package is not uniquely ready with its elected key")
            preparation_plan = elected[0]
            preparation_plan_bytes = canonical_json_bytes(preparation_plan)
            controls_unchanged()
            transport = product_reuse.capture_sdk_native_prepared_upload(plan, capture,
                expected_phase_plan=preparation_plan, artifact_id=prepared_artifact_id,
                artifact_sha256=prepared_artifact_sha256, trusted_workflow_sha=trusted_workflow_sha,
                repository_root=root, environ=environ, token=token)
            capture_inventory = regular_file_inventory(capture, allow_empty=True)
            prepared = destination / "inputs"
            ready = product_reuse.materialize_product_predecessors(plan, discovery, state, instance, prepared,
                expected_build_key=expected_build_key, repository_root=root, environ=environ,
                sdk_original_workflow_sha=trusted_workflow_sha, **tooling)
            prepared_inventory = regular_file_inventory(prepared, allow_empty=True)
            producer = product_reuse.validate_producer(product_reuse._canonical_control(
                prepared / "producer.json", "Elected native package producer"))
            if transport["captureProducer"] != producer:
                raise ValueError("Native preparation upload differs from the elected package producer")
            contract = product_reuse.validate_phase_receipt(product_reuse._canonical_control(
                prepared / "contract-contract-metadata-common/phase-receipt.json", "Current Contract metadata"))
            bundles = [row for row in contract["outputs"] if row["kind"] == "contract-bundle"]
            if (tuple(contract[name] for name in ("product", "component", "phase", "target")) !=
                    ("contract", "contract", "metadata", "common") or len(bundles) != 1
                    or bundles[0]["sha256"] != selection["contractPayloadSha256"]):
                raise ValueError("Current Contract differs from authenticated native SDK inputs")
            csharp_binary = None
            if component == "csharp":
                binary_root = prepared / "sdk-csharp-binary-desktop"
                binary_receipt = product_reuse.validate_phase_receipt(product_reuse._canonical_control(
                    binary_root / PHASE_RECEIPT_NAME, "C# binary predecessor receipt"))
                if tuple(binary_receipt[name] for name in ("product", "component", "phase", "target")) != (
                        "sdk", "csharp", "binary", "desktop"):
                    raise ValueError("C# package has the wrong binary predecessor")
                csharp_binary = binary_root / "stage"
                binary_manifest = product_reuse.verify_output_manifest_identity(
                    csharp_binary, "sdk", "csharp", "binary", "desktop", selection["sdkVersion"])
                if binary_manifest["outputs"] != binary_receipt["outputs"]:
                    raise ValueError("C# binary predecessor differs from its original receipt")

            def original(product, target_component, phase, target):
                original_identity = PhaseInstanceId(product, target_component, phase, target)
                if (product != "runtime" or target_component not in NATIVE_TARGETS or target != target_component
                        or phase not in {"package", "validation"}):
                    raise ValueError("Unexpected native package original predecessor")
                directory = prepared / "-".join((product, target_component, phase, target))
                receipt_path = directory / PHASE_RECEIPT_NAME
                raw = read_regular_file_bytes(receipt_path, reject_symlink_parents=True)
                receipt = product_reuse.validate_phase_receipt(load_canonical_json_bytes(raw))
                if (raw != inputs["runtime"]["receiptBytes"].get(original_identity)
                        or tuple(receipt[name] for name in ("product", "component", "phase", "target")) !=
                        (product, target_component, phase, target)):
                    raise ValueError("Native package Runtime receipt differs from its verified original")
                manifest = product_reuse.verify_output_manifest_identity(directory / "stage",
                    product, target_component, phase, target, receipt["productVersion"])
                if manifest["outputs"] != receipt["outputs"]:
                    raise ValueError("Native package Runtime stage differs from its original receipt")
                return {"stage": directory / "stage", "receiptPath": receipt_path, "receipt": receipt}

            runtime_stages = destination / "runtime-stages"
            for target in NATIVE_TARGETS:
                for phase in ("package", "validation"):
                    record = original("runtime", target, phase, target)
                    snapshot_regular_tree(record["stage"], runtime_stages / target / phase)
            runtime_inventory = regular_file_inventory(runtime_stages)

            def unchanged():
                controls_unchanged()
                if (regular_file_inventory(capture, allow_empty=True) != capture_inventory
                        or regular_file_inventory(prepared, allow_empty=True) != prepared_inventory
                        or regular_file_inventory(runtime_stages) != runtime_inventory
                        or canonical_json_bytes(preparation_plan) != preparation_plan_bytes):
                    raise ValueError("Native package original inputs or preparation capture changed")

            unchanged()
            binary_argument = {"csharp_binary_stage": csharp_binary} if csharp_binary is not None else {}
            result = execute_package(ready, producer=producer, sdk_version=selection["sdkVersion"],
                repository_root=root, destination=destination / "worker", runtime_stages=runtime_stages,
                prepared_sources=capture / "original/prepared-sources", staged_sdks=capture / "original/staged-sdks",
                compatibility_request=inputs["sdk"]["directory"] / REQUEST_NAME,
                predecessor=original, environ=environ, **binary_argument)
            unchanged()
            finalized = product_reuse.finalize_phase_object(stage_root=result["stage"], phase_plan=ready,
                producer=producer, product_version=selection["sdkVersion"],
                trust_domain="development" if producer["event"] == "pull_request" else "release",
                destination=candidate)
            binary_gate = ({"binary_stage_root": csharp_binary,
                            "binary_receipt_path": binary_root / PHASE_RECEIPT_NAME}
                           if csharp_binary is not None else {})
            verified, raw = verify_sdk_package_inputs(root, result["stage"], candidate / PHASE_RECEIPT_NAME,
                inputs["sdk"]["directory"] / REQUEST_NAME,
                runtime_stage_root=runtime_stages, staged_sdks=capture / "original/staged-sdks",
                **binary_gate)
            if verified != finalized["receipt"] or raw != read_regular_file_bytes(candidate / PHASE_RECEIPT_NAME):
                raise ValueError("Native package full gate returned a different original candidate receipt")
            candidate_inventory = regular_file_inventory(candidate)
            unchanged()
        unchanged()
        def outputs_unchanged():
            if (regular_file_inventory(result["stage"]) != result["outputInventory"]
                    or Path(result["stagedSdks"]) != capture / "original/staged-sdks"
                    or regular_file_inventory(result["stagedSdks"]) != result["stagedSdkInventory"]
                    or regular_file_inventory(candidate) != candidate_inventory
                    or verify_phase_shard(candidate, instance) != finalized):
                raise ValueError("Native package outputs changed after full admission")

        outputs_unchanged()
        # After successful admission, preserve the authenticated preparation
        # upload externally, not in the deterministic package. Earlier failures
        # do not publish this private capture.
        publish_regular_tree(capture, destination / "prepared-upload", allow_empty=True)
        unchanged()
        outputs_unchanged()
        if regular_file_inventory(destination / "prepared-upload", allow_empty=True) != capture_inventory:
            raise ValueError("Native package retained preparation capture changed")
        _require_capability_output_separate(destination / "shard", protected)
        publish_regular_tree(candidate, destination / "shard")
    return verify_phase_shard(destination / "shard", instance)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("plan", "destination", "keyring", "keys-directory", "repository-root"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    for flag, name in (("discovery-root", "discovery"), ("state-root", "state"),
                       ("preparation-state-root", "preparation_state")):
        parser.add_argument(f"--{flag}", dest=name, type=Path, required=True)
    for name in ("component", "preparation-component"):
        parser.add_argument(f"--{name}", choices=NATIVE_BINDINGS, required=True)
    for name in ("expected-build-key", "preparation-build-key", "prepared-artifact-sha256",
                 "sdk-inputs-artifact-sha256", "trusted-workflow-sha"):
        parser.add_argument(f"--{name}", required=True)
    for name in ("prepared-artifact-id", "sdk-inputs-artifact-id"):
        parser.add_argument(f"--{name}", type=int, required=True)
    parser.add_argument("--sdk-validation-tooling", type=Path)
    parser.add_argument("--sdk-apple-validation-policy", type=Path)
    add_metadata_admission_arguments(parser)
    args = parser.parse_args(argv)
    arguments = {name: value for name, value in vars(args).items()
                 if name not in {"sdk_facade_metadata_policy", "sdk_android_metadata_policy"}}
    try:
        policy = arguments.pop("sdk_validation_tooling")
        if policy is not None:
            arguments["sdk_validation_tooling"] = product_reuse._canonical_control(policy, "Caller SDK tooling policy")
        apple_policy = arguments.pop("sdk_apple_validation_policy")
        if apple_policy is not None:
            arguments["sdk_apple_validation_policy"] = product_reuse._canonical_control(
                apple_policy, "Caller Apple validation policy")
        with metadata_admission_options(args) as admissions:
            execute(**arguments, environ=os.environ, token=os.environ.get("GITHUB_TOKEN", ""), **admissions)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
