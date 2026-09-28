"""Execute the C# SDK binary from elected Contract and S858 originals."""

import argparse
import os
from pathlib import Path
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse
import sdk_workflow
from products.contract_projection import verify_contract_component_projection
from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, publish_regular_tree,
    read_regular_file_bytes, regular_file_inventory, sha256_file,
)
from products.receipt import validate_phase_receipt, verify_output_manifest_identity
from products.registry import PhaseInstanceId
from products.restore import PHASE_PLAN_KEYS, PHASE_RECEIPT_NAME, verify_phase_shard
from products.sdk_inputs import COMPATIBILITY_NAME, REQUEST_NAME
from products.sdk_native_metadata import _inventory
from products.sdk_package import _require_capability_output_separate
from products.signing_isolation import require_no_signing_secret
from sdk_csharp_binary_phase import execute as execute_binary
from products.sdk_csharp_binary import verify_csharp_binary_stage
from sdk_metadata_policy import add_metadata_admission_arguments, metadata_admission_options


_INSTANCE = PhaseInstanceId("sdk", "csharp", "binary", "desktop")
_PACKAGE = {"product": "sdk", "component": "csharp", "phase": "package", "target": "desktop"}
_LIMIT = 16 * 1024 * 1024


def execute(plan, discovery, state, destination, *, expected_build_key,
            sdk_inputs_artifact_id, sdk_inputs_artifact_sha256, trusted_workflow_sha,
            keyring, keys_directory, repository_root, environ, token,
            sdk_validation_tooling=None, sdk_apple_validation_policy=None,
            sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None):
    """Admit a binary shard only after its original inputs and outputs survive recheck."""
    require_no_signing_secret(environ)
    root = Path(repository_root).resolve(strict=True)
    plan = Path(plan).absolute()
    discovery, state, destination = product_reuse._product_materialization_paths(root, discovery, state, destination)
    protected = [plan, discovery, state, Path(keyring), Path(keys_directory)]
    _require_capability_output_separate(destination, protected)
    if (root not in destination.parents or destination.resolve(strict=False) != destination
            or destination.exists() or destination.is_symlink()):
        raise ValueError("C# binary destination must be fresh and normalized inside checkout")
    control_inventory = {path: regular_file_inventory(path, allow_empty=True) for path in (discovery, state)}
    plan_bytes = read_regular_file_bytes(plan, max_bytes=_LIMIT, reject_symlink_parents=True)

    def controls_unchanged():
        if (read_regular_file_bytes(plan, max_bytes=_LIMIT, reject_symlink_parents=True) != plan_bytes
                or any(regular_file_inventory(path, allow_empty=True) != inventory
                       for path, inventory in control_inventory.items())):
            raise ValueError("C# binary original election controls changed")

    tooling = {"sdk_validation_tooling": sdk_validation_tooling} if sdk_validation_tooling is not None else {}
    if sdk_apple_validation_policy is not None:
        tooling["sdk_apple_validation_policy"] = sdk_apple_validation_policy
    if sdk_facade_metadata_admission is not None:
        tooling["sdk_facade_metadata_admission"] = sdk_facade_metadata_admission
    if sdk_android_metadata_admission is not None:
        tooling["sdk_android_metadata_admission"] = sdk_android_metadata_admission
    with tempfile.TemporaryDirectory(prefix="sdk-csharp-binary-") as temporary:
        candidate = Path(temporary).resolve() / "shard"
        with sdk_workflow.verified_inputs(plan, discovery, state,
                artifact_id=sdk_inputs_artifact_id, artifact_sha256=sdk_inputs_artifact_sha256,
                trusted_workflow_sha=trusted_workflow_sha, keyring=keyring,
                keys_directory=keys_directory, repository_root=root, environ=environ,
                token=token, **tooling) as inputs:
            controls_unchanged()
            selection = inputs["selection"]
            if _PACKAGE not in selection["consumers"]:
                raise ValueError("C# binary requires the selected C# package S858 inputs")
            inspected = product_reuse.inspect_products(plan, discovery, state,
                repository_root=root, environ=environ,
                sdk_original_workflow_sha=trusted_workflow_sha, **tooling)
            elected = [item for item in inspected["readyPlans"] if
                       tuple(item.get(name) for name in ("product", "component", "phase", "target")) ==
                       ("sdk", "csharp", "binary", "desktop")]
            if (len(elected) != 1 or set(elected[0]) != PHASE_PLAN_KEYS
                    or elected[0]["buildKey"] != expected_build_key):
                raise ValueError("C# binary is not uniquely ready with its elected key")
            expected_plan = elected[0]
            controls_unchanged()
            predecessors = destination / "inputs" / "predecessors"
            ready = product_reuse.materialize_product_predecessors(plan, discovery, state,
                _INSTANCE, predecessors, expected_build_key=expected_build_key,
                repository_root=root, environ=environ,
                sdk_original_workflow_sha=trusted_workflow_sha, **tooling)
            if ready != expected_plan:
                raise ValueError("C# binary predecessor materialization changed its elected plan")
            producer = product_reuse.validate_producer(product_reuse._canonical_control(
                predecessors / "producer.json", "Elected C# binary producer"))
            contract_root = predecessors / "contract-contract-metadata-common"
            receipt_path = contract_root / PHASE_RECEIPT_NAME
            receipt = validate_phase_receipt(load_canonical_json_bytes(read_regular_file_bytes(
                receipt_path, max_bytes=_LIMIT, reject_symlink_parents=True)))
            stage = contract_root / "stage"
            manifest = verify_output_manifest_identity(stage, "contract", "contract", "metadata", "common",
                                                       receipt["productVersion"])
            bundles = [item for item in receipt["outputs"] if item["kind"] == "contract-bundle"]
            if (manifest["outputs"] != receipt["outputs"] or len(bundles) != 1
                    or bundles[0]["sha256"] != selection["contractPayloadSha256"]):
                raise ValueError("C# binary Contract differs from selected S858 payload")
            verified_state = product_reuse._verified_product_state(plan, discovery, state, root,
                environ, sdk_validation_tooling, sdk_original_workflow_sha=trusted_workflow_sha,
                **sdk_workflow._caller_policies(None, sdk_apple_validation_policy,
                    sdk_facade_metadata_admission=sdk_facade_metadata_admission,
                    sdk_android_metadata_admission=sdk_android_metadata_admission))
            if (verified_state.prior_ready_plans.get(_INSTANCE) != expected_plan
                    or verified_state.producer != producer):
                raise ValueError("C# binary Contract election differs from original producer")
            evidence = verified_state.rebased_request.get("contractEvidence")
            if evidence is None or evidence["expectedTrustDomain"] != "release":
                raise ValueError("C# binary requires release-attested Contract evidence")
            trust = product_reuse._release_trust(root, producer["commit"], destination / "inputs" / "policy")
            if trust is None:
                raise ValueError("C# binary requires Git-authoritative Contract trust policy")

            def original(product, component, phase, target):
                if (product, component, target) != ("contract", "contract", "common") or phase not in (
                        "binary", "package", "validation", "metadata"):
                    raise ValueError("C# binary requested an unrelated Contract predecessor")
                directory = predecessors / "-".join((product, component, phase, target))
                original_receipt = directory / PHASE_RECEIPT_NAME
                original_raw = read_regular_file_bytes(original_receipt, max_bytes=_LIMIT,
                                                       reject_symlink_parents=True)
                original_value = validate_phase_receipt(load_canonical_json_bytes(original_raw))
                original_manifest = verify_output_manifest_identity(directory / "stage", product,
                    component, phase, target, original_value["productVersion"])
                if original_manifest["outputs"] != original_value["outputs"]:
                    raise ValueError("C# binary Contract predecessor differs from original receipt")
                return {"stage": directory / "stage", "receiptPath": original_receipt,
                        "receipt": original_value}

            def one_output(record, kind):
                outputs = [item for item in record["receipt"]["outputs"] if item["kind"] == kind]
                if len(outputs) != 1:
                    raise ValueError("C# binary requires one exact Contract payload")
                return record["stage"] / outputs[0]["relativePath"]

            contract, version, handoff, _, handoff_inventory = product_reuse._capture_runtime_contract(
                root, evidence, original, one_output, destination / "inputs", trust)
            stem = f"codex-agent-contract-{version}"
            verify_contract_component_projection(contract["stage"], contract["receiptPath"],
                handoff / f"{stem}.attestation.json", handoff / f"{stem}.attestation.sig",
                handoff / "public-key.pub", expected_trust_domain="release",
                expected_contract_version=version, required_components=("common",),
                keyring=trust.keyring, keys_directory=trust.keys)
            request = inputs["sdk"]["directory"] / REQUEST_NAME
            compatibility = inputs["sdk"]["directory"] / COMPATIBILITY_NAME
            original_inputs = _inventory(destination / "inputs")
            request_bytes = read_regular_file_bytes(request, max_bytes=_LIMIT, reject_symlink_parents=True)
            compatibility_bytes = read_regular_file_bytes(compatibility, max_bytes=_LIMIT,
                                                          reject_symlink_parents=True)
            plan_record = canonical_json_bytes(expected_plan)

            def unchanged():
                controls_unchanged()
                require_no_signing_secret(environ)
                if (_inventory(destination / "inputs") != original_inputs
                        or _inventory(handoff) != handoff_inventory
                        or read_regular_file_bytes(request, max_bytes=_LIMIT,
                                                   reject_symlink_parents=True) != request_bytes
                        or read_regular_file_bytes(compatibility, max_bytes=_LIMIT,
                                                   reject_symlink_parents=True) != compatibility_bytes
                        or canonical_json_bytes(expected_plan) != plan_record):
                    raise ValueError("C# binary authenticated originals changed")

            unchanged()
            result = execute_binary(ready, producer=producer, sdk_version=selection["sdkVersion"],
                contract_metadata=contract, verified_contract_handoff=handoff,
                compatibility_request=request, repository_root=root,
                destination=destination / "worker", environ=environ)
            output = result["stage"]
            if _inventory(output) != result["outputInventory"]:
                raise ValueError("C# binary output differs from worker inventory")
            unchanged()
            finalized = product_reuse.finalize_phase_object(stage_root=output, phase_plan=ready,
                producer=producer, product_version=selection["sdkVersion"],
                trust_domain="development" if producer["event"] == "pull_request" else "release",
                destination=candidate)
            verify_csharp_binary_stage(output, finalized["receipt"], compatibility,
                root / "gradle/release/keys/sdk-runtime-root.pub")
            candidate_inventory = regular_file_inventory(candidate)
            unchanged()
        controls_unchanged()
        if (regular_file_inventory(candidate) != candidate_inventory
                or _inventory(destination / "inputs") != original_inputs
                or _inventory(output) != result["outputInventory"]
                or verify_phase_shard(candidate, _INSTANCE) != finalized):
            raise ValueError("C# binary candidate changed after original-input verification")
        publish_regular_tree(candidate, destination / "shard")
    return verify_phase_shard(destination / "shard", _INSTANCE)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("plan", "destination", "keyring", "keys-directory", "repository-root"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    for flag, name in (("discovery-root", "discovery"), ("state-root", "state")):
        parser.add_argument(f"--{flag}", dest=name, type=Path, required=True)
    for name in ("expected-build-key", "sdk-inputs-artifact-sha256", "trusted-workflow-sha"):
        parser.add_argument(f"--{name}", required=True)
    parser.add_argument("--sdk-inputs-artifact-id", type=int, required=True)
    for name in ("sdk-validation-tooling", "sdk-apple-validation-policy"):
        parser.add_argument(f"--{name}", type=Path)
    add_metadata_admission_arguments(parser)
    args = parser.parse_args(argv)
    arguments = {name: value for name, value in vars(args).items()
                 if name not in {"sdk_facade_metadata_policy", "sdk_android_metadata_policy"}}
    try:
        for name in ("sdk_validation_tooling", "sdk_apple_validation_policy"):
            path = arguments.pop(name)
            if path is not None:
                arguments[name] = product_reuse._canonical_control(path, "Caller " + name)
        with metadata_admission_options(args) as admissions:
            execute(**arguments, environ=os.environ, token=os.environ.get("GITHUB_TOKEN", ""), **admissions)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
