"""Join authenticated SDK inputs, native preparation and metadata admission."""

import argparse
import os
from pathlib import Path
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse
import sdk_workflow
from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, publish_regular_tree,
    read_regular_file_bytes, regular_file_inventory, snapshot_regular_tree,
)
from products.registry import NATIVE_BINDINGS, NATIVE_TARGETS, PhaseInstanceId
from products.restore import PHASE_PLAN_KEYS, PHASE_RECEIPT_NAME, verify_phase_shard
from products.sdk_inputs import REQUEST_NAME
from products.sdk_package import _require_capability_output_separate


def execute(plan, discovery, state, destination, *, component, expected_build_key,
            preparation_component, preparation_build_key, preparation_state,
            prepared_artifact_id, prepared_artifact_sha256,
            sdk_inputs_artifact_id, sdk_inputs_artifact_sha256, trusted_workflow_sha,
            keyring, keys_directory, repository_root, environ, token,
            tooling_evidence, tooling_public_key, java_executable,
            required_trust_domain, tooling_keyring=None, tooling_keys_directory=None,
            preparation_phase="package", preparation_target="desktop"):
    """Run the existing five-host metadata caller and publish its shard last."""
    if component not in NATIVE_BINDINGS or preparation_component not in NATIVE_BINDINGS:
        raise ValueError("Native metadata execution requires fixed native language components")
    if (tooling_keyring is None) != (tooling_keys_directory is None):
        raise ValueError("Native metadata tooling keyring and keys directory must be supplied together")
    root = Path(repository_root).resolve(strict=True)
    plan = Path(plan).absolute()
    discovery, state, destination = product_reuse._product_materialization_paths(root, discovery, state, destination)
    _, preparation_state, _ = product_reuse._product_materialization_paths(root, discovery, preparation_state, destination)
    trees = {Path(path) for path in (discovery, state, preparation_state, keys_directory,
                                    tooling_evidence, tooling_keys_directory) if path is not None}
    files = {Path(path) for path in (plan, keyring, tooling_public_key,
                                    java_executable, tooling_keyring) if path is not None}
    _require_capability_output_separate(destination, [*trees, *files])
    destination.relative_to(root)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Native metadata destination must not exist")
    controls = {path: regular_file_inventory(path, allow_empty=True) for path in trees}
    raw_controls = {path: read_regular_file_bytes(path, max_bytes=128 * 1024 * 1024,
                    reject_symlink_parents=True) for path in files}

    def controls_unchanged():
        if (any(regular_file_inventory(path, allow_empty=True) != before
                for path, before in controls.items())
                or any(read_regular_file_bytes(path, max_bytes=128 * 1024 * 1024,
                       reject_symlink_parents=True) != before for path, before in raw_controls.items())):
            raise ValueError("Native metadata original election state or caller policy changed")

    tooling = {"evidence": str(Path(tooling_evidence).absolute()),
        "publicKey": str(Path(tooling_public_key).absolute()),
        "javaExecutable": str(Path(java_executable).absolute()),
        "requiredTrustDomain": required_trust_domain,
        "keyring": str(Path(tooling_keyring).absolute()) if tooling_keyring is not None else None,
        "keysDirectory": str(Path(tooling_keys_directory).absolute()) if tooling_keys_directory is not None else None}

    instance = PhaseInstanceId("sdk", component, "metadata", "desktop")
    identity = {"product": "sdk", "component": component, "phase": "metadata", "target": "desktop"}
    preparation_identity = {"product": "sdk", "component": preparation_component,
                            "phase": preparation_phase, "target": preparation_target}
    preparation_instance = product_reuse._identity(preparation_identity)
    if (preparation_phase not in {"package", "validation", "metadata"}
            or not product_reuse._sdk_family_worker_instance(
                preparation_instance, "native-" + preparation_phase)):
        raise ValueError("Native metadata requires an exact preparation consumer anchor")
    with tempfile.TemporaryDirectory(prefix="sdk-native-metadata-") as temporary:
        private = Path(temporary).resolve()
        capture = private / "prepared-upload"
        with sdk_workflow.verified_inputs(plan, discovery, state,
                artifact_id=sdk_inputs_artifact_id, artifact_sha256=sdk_inputs_artifact_sha256,
                trusted_workflow_sha=trusted_workflow_sha, keyring=keyring, keys_directory=keys_directory,
                repository_root=root, environ=environ, token=token, sdk_validation_tooling=tooling) as inputs:
            controls_unchanged()
            selection = inputs["selection"]
            if identity not in selection["consumers"]:
                raise ValueError("Native SDK metadata is not selected")
            inspected = product_reuse.inspect_products(plan, discovery, preparation_state,
                repository_root=root, environ=environ, sdk_validation_tooling=tooling)
            elected = [row for row in inspected["readyPlans"]
                       if all(row.get(name) == value for name, value in preparation_identity.items())]
            if (len(elected) != 1 or set(elected[0]) != PHASE_PLAN_KEYS
                    or elected[0]["buildKey"] != preparation_build_key):
                raise ValueError("Original native preparation consumer is not uniquely ready with its elected key")
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
                sdk_validation_tooling=tooling)
            ready_bytes = canonical_json_bytes(ready)
            prepared_inventory = regular_file_inventory(prepared, allow_empty=True)
            producer = product_reuse.validate_producer(product_reuse._canonical_control(
                prepared / "producer.json", "Elected native metadata producer"))
            producer_bytes = canonical_json_bytes(producer)
            if transport["captureProducer"] != producer:
                raise ValueError("Native preparation upload differs from the elected metadata producer")
            contract = product_reuse.validate_phase_receipt(product_reuse._canonical_control(
                prepared / "contract-contract-metadata-common/phase-receipt.json", "Current Contract metadata"))
            bundles = [row for row in contract["outputs"] if row["kind"] == "contract-bundle"]
            if (tuple(contract[name] for name in ("product", "component", "phase", "target")) !=
                    ("contract", "contract", "metadata", "common") or len(bundles) != 1
                    or bundles[0]["sha256"] != selection["contractPayloadSha256"]):
                raise ValueError("Current Contract differs from authenticated native metadata inputs")

            runtime_stages = destination / "runtime-stages"
            for target in NATIVE_TARGETS:
                for phase in ("package", "validation"):
                    original_identity = PhaseInstanceId("runtime", target, phase, target)
                    directory = prepared / f"runtime-{target}-{phase}-{target}"
                    receipt_path = directory / PHASE_RECEIPT_NAME
                    raw = read_regular_file_bytes(receipt_path, reject_symlink_parents=True)
                    receipt = product_reuse.validate_phase_receipt(load_canonical_json_bytes(raw))
                    if (raw != inputs["runtime"]["receiptBytes"].get(original_identity)
                            or tuple(receipt[name] for name in ("product", "component", "phase", "target")) !=
                            ("runtime", target, phase, target)):
                        raise ValueError("Native metadata Runtime receipt differs from its verified original")
                    manifest = product_reuse.verify_output_manifest_identity(
                        directory / "stage", "runtime", target, phase, target, receipt["productVersion"])
                    if manifest["outputs"] != receipt["outputs"]:
                        raise ValueError("Native metadata Runtime stage differs from its original receipt")
                    snapshot_regular_tree(directory / "stage", runtime_stages / target / phase)
            runtime_inventory = regular_file_inventory(runtime_stages)
            staged_sdks = destination / "staged-sdks"
            original_staged_sdk_inventory = regular_file_inventory(capture / "original/staged-sdks")
            snapshot_regular_tree(capture / "original/staged-sdks", staged_sdks)
            staged_sdk_inventory = regular_file_inventory(staged_sdks)
            sdk_inputs = destination / "sdk-inputs"
            original_sdk_input_inventory = regular_file_inventory(inputs["sdk"]["directory"])
            snapshot_regular_tree(inputs["sdk"]["directory"], sdk_inputs)
            sdk_input_inventory = regular_file_inventory(sdk_inputs)
            if (staged_sdk_inventory != original_staged_sdk_inventory
                    or sdk_input_inventory != original_sdk_input_inventory):
                raise ValueError("Native metadata authenticated inputs changed during relocation")

            def unchanged():
                controls_unchanged()
                if (regular_file_inventory(capture, allow_empty=True) != capture_inventory
                        or regular_file_inventory(prepared, allow_empty=True) != prepared_inventory
                        or regular_file_inventory(runtime_stages) != runtime_inventory
                        or regular_file_inventory(staged_sdks) != staged_sdk_inventory
                        or regular_file_inventory(sdk_inputs) != sdk_input_inventory
                        or canonical_json_bytes(preparation_plan) != preparation_plan_bytes
                        or canonical_json_bytes(ready) != ready_bytes
                        or canonical_json_bytes(producer) != producer_bytes):
                    raise ValueError("Native metadata original inputs or preparation capture changed")

            unchanged()
            candidate = destination / "candidate"
            result = product_reuse.execute_sdk_metadata(plan, discovery, state, candidate,
                component=component, expected_build_key=expected_build_key,
                compatibility_request=sdk_inputs / REQUEST_NAME,
                runtime_stages=runtime_stages, staged_sdks=staged_sdks,
                sdk_validation_tooling=tooling, repository_root=root, environ=environ)
            candidate_shard = candidate / "worker/shard"
            receipt = result["receipt"]
            trust_domain = "development" if producer["event"] == "pull_request" else "release"
            if (any(receipt.get(field) != ready[field] for field in PHASE_PLAN_KEYS)
                    or receipt.get("producer") != producer
                    or receipt.get("productVersion") != selection["sdkVersion"]
                    or receipt.get("trustDomain") != trust_domain):
                raise ValueError("Native metadata candidate differs from its outer election")
            candidate_inventory = regular_file_inventory(candidate, allow_empty=True)
            if verify_phase_shard(candidate_shard, instance) != result:
                raise ValueError("Native metadata caller returned a different candidate shard")
            unchanged()
        unchanged()

        def outputs_unchanged():
            product_reuse._runtime_worker_checkout(root, producer)
            if (regular_file_inventory(candidate, allow_empty=True) != candidate_inventory
                    or verify_phase_shard(candidate_shard, instance) != result):
                raise ValueError("Native metadata candidate changed after authenticated input use")

        outputs_unchanged()
        publish_regular_tree(capture, destination / "prepared-upload", allow_empty=True)
        unchanged()
        outputs_unchanged()
        if regular_file_inventory(destination / "prepared-upload", allow_empty=True) != capture_inventory:
            raise ValueError("Native metadata retained preparation capture changed")
        publish_regular_tree(candidate_shard, destination / "shard")
    return verify_phase_shard(destination / "shard", instance)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    paths = ("plan", "destination", "preparation-state", "keyring", "keys-directory", "repository-root",
             "tooling-evidence", "tooling-public-key", "java-executable")
    for name in paths:
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--discovery-root", dest="discovery", type=Path, required=True)
    parser.add_argument("--state-root", dest="state", type=Path, required=True)
    for name in ("component", "preparation-component", "expected-build-key", "preparation-build-key",
                 "prepared-artifact-sha256", "sdk-inputs-artifact-sha256", "trusted-workflow-sha"):
        parser.add_argument(f"--{name}", required=True)
    for name in ("prepared-artifact-id", "sdk-inputs-artifact-id"):
        parser.add_argument(f"--{name}", type=int, required=True)
    parser.add_argument("--required-trust-domain", choices=("development", "release"), required=True)
    parser.add_argument("--preparation-phase", choices=("package", "validation", "metadata"),
                        default=argparse.SUPPRESS)
    parser.add_argument("--preparation-target", choices=("desktop", *NATIVE_TARGETS),
                        default=argparse.SUPPRESS)
    parser.add_argument("--tooling-keyring", type=Path)
    parser.add_argument("--tooling-keys-directory", type=Path)
    arguments = vars(parser.parse_args(argv))
    if (arguments["tooling_keyring"] is None) != (arguments["tooling_keys_directory"] is None):
        parser.error("Native metadata tooling keyring and keys directory must be supplied together")
    try:
        execute(**arguments, environ=os.environ, token=os.environ.get("GITHUB_TOKEN", ""))
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
