"""Compose elected Core/Android packages without inventing original authority."""

import argparse
import os
from pathlib import Path
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse
import sdk_workflow
from products.contract_attestation import CONTRACT_EXECUTION_CLOSURE_DIRECTORY
from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, publish_regular_tree,
    read_regular_file_bytes, require_exact_keys, snapshot_regular_tree, write_canonical_json,
)
from products.registry import PhaseInstanceId
from products.restore import PHASE_RECEIPT_NAME, verify_phase_shard
from products.runtime_aggregate_handoff import _public_policy
from products.sdk_facade_inputs import _EVIDENCE_FIELDS, _path
from products.sdk_facade_validation import _inventory
from products.sdk_inputs import REQUEST_NAME
from products.sdk_package import _require_capability_output_separate, verify_sdk_package_inputs
from products.signing_isolation import require_no_signing_secret
from sdk_ios_package import _record
from sdk_maven_phase import execute as execute_package


_TARGETS = {"sdk-core": "common", "sdk-android": "android"}
_LIMIT = 512 * 1024 * 1024


def _read(path):
    return read_regular_file_bytes(Path(path), max_bytes=_LIMIT, reject_symlink_parents=True)


def execute(plan, discovery, state, destination, *, component, expected_build_key,
            sdk_inputs_artifact_id, sdk_inputs_artifact_sha256, trusted_workflow_sha,
            keyring, keys_directory, binary_contract_evidence, repository_root, environ, token,
            sdk_validation_tooling=None, sdk_apple_validation_policy=None):
    """Publish one shard only after full original gates and successful context exit.

    The binary's original Contract evidence is mandatory caller policy, even if
    the currently selected Contract is equivalent. The existing full package
    gate authenticates that original binary plan and compares its components to
    the current S858 Contract. No receipt or original producer is substituted.
    Retained captures and invocation paths stay outside deterministic content.
    """
    require_no_signing_secret(environ)
    if component not in _TARGETS:
        raise ValueError("Maven package controller requires Core or Android")
    target = _TARGETS[component]
    instance = PhaseInstanceId("sdk", component, "package", target)
    identity = dict(product="sdk", component=component, phase="package", target=target)
    root = Path(repository_root).resolve(strict=True)
    plan = Path(plan).absolute()
    discovery, state, destination = product_reuse._product_materialization_paths(root, discovery, state, destination)
    evidence = require_exact_keys(binary_contract_evidence, _EVIDENCE_FIELDS, "Original binary Contract evidence")
    evidence_bytes = canonical_json_bytes(evidence)
    if (evidence["expectedTrustDomain"] not in {"release", "development"}
            or (evidence["keyring"] is None) != (evidence["keysDirectory"] is None)):
        raise ValueError("Original binary Contract requires exact caller trust policy")
    for name in _EVIDENCE_FIELDS - {"expectedTrustDomain"}:
        if evidence[name] is None:
            if name not in {"keyring", "keysDirectory"}:
                raise ValueError("Original binary Contract requires every original evidence path")
        else:
            _path(evidence[name], "Original binary Contract " + name)
    stage = Path(evidence["stageRoot"])
    receipt_path = Path(evidence["phaseReceipt"])
    _record({"stage": stage, "receiptPath": receipt_path,
        "receipt": load_canonical_json_bytes(_read(receipt_path))},
        ("contract", "contract", "metadata", "common"), "Original binary Contract")
    trees = {"discovery": discovery, "state": state, "keys": Path(keys_directory), "binaryContract": stage,
             "binaryClosure": Path(evidence["attestation"]).parent / CONTRACT_EXECUTION_CLOSURE_DIRECTORY}
    files = {"plan": plan, "keyring": Path(keyring)}
    for name in ("phaseReceipt", "attestation", "attestationSignature", "publicKey", "keyring"):
        if evidence[name] is not None:
            files["binaryContract/" + name] = Path(evidence[name])
    if evidence["keysDirectory"] is not None:
        trees["binaryContractKeys"] = Path(evidence["keysDirectory"])
    policies = sdk_workflow._caller_policies(sdk_validation_tooling, sdk_apple_validation_policy)
    policy_bytes = canonical_json_bytes(policies)
    # Existing replay validates each policy schema. Preserve its explicit local
    # paths too; never recover caller policy from a transported request.
    for label, policy in policies.items():
        if type(policy) is not dict:
            raise ValueError("Caller replay policy must be an explicit mapping")
        for name, value in policy.items():
            if isinstance(value, (str, Path)) and Path(value).is_absolute():
                path = Path(value)
                (trees if path.is_dir() else files)[label + "/" + name] = path
    protected = [*trees.values(), *files.values()]
    _require_capability_output_separate(destination, protected)
    if (root not in destination.parents or destination.resolve(strict=False) != destination
            or destination.exists() or destination.is_symlink()):
        raise ValueError("Maven package destination must be fresh and normalized inside checkout")
    before_trees = {name: _inventory(path, allow_empty=True) for name, path in trees.items()}
    before_files = {name: _read(path) for name, path in files.items()}
    retained, values = {}, []

    def unchanged():
        require_no_signing_secret(environ)
        if (canonical_json_bytes(evidence) != evidence_bytes or canonical_json_bytes(policies) != policy_bytes
                or any(_inventory(path, allow_empty=True) != before_trees[name] for name, path in trees.items())
                or any(_read(path) != before_files[name] for name, path in files.items())
                or any(_inventory(path, allow_empty=True) != inventory for path, inventory in retained.items())
                or any(canonical_json_bytes(value) != raw for value, raw in values)):
            raise ValueError("Maven package original inputs, selection or retained evidence changed")

    destination = product_reuse._prepare_destination(destination, root)
    try:
        with tempfile.TemporaryDirectory(prefix="sdk-maven-package-") as temporary:
            private = Path(temporary).resolve()
            _require_capability_output_separate(private, [root, *protected])
            candidate = private / "shard"
            with sdk_workflow.verified_inputs(plan, discovery, state,
                    artifact_id=sdk_inputs_artifact_id, artifact_sha256=sdk_inputs_artifact_sha256,
                    trusted_workflow_sha=trusted_workflow_sha, keyring=keyring, keys_directory=keys_directory,
                    repository_root=root, environ=environ, token=token, **policies) as sdk_inputs:
                selection = sdk_inputs["selection"]
                values.append((selection, canonical_json_bytes(selection)))
                if identity not in selection["consumers"]:
                    raise ValueError("Maven SDK package is not selected")
                prepared = destination / "inputs"
                ready = product_reuse.materialize_product_predecessors(plan, discovery, state, instance, prepared,
                    expected_build_key=expected_build_key, repository_root=root, environ=environ, **policies)
                retained[prepared] = _inventory(prepared, allow_empty=True)
                producer = product_reuse.validate_producer(load_canonical_json_bytes(_read(prepared / "producer.json")))
                values.extend((value, canonical_json_bytes(value)) for value in (ready, producer))
                if _read(prepared / "phase-plan.json") != canonical_json_bytes(ready):
                    raise ValueError("Maven package retained election differs from its selected plan")

                def original(product, name, phase, source_target):
                    directory = prepared / "-".join((product, name, phase, source_target))
                    receipt = directory / PHASE_RECEIPT_NAME
                    return _record({"stage": directory / "stage", "receiptPath": receipt,
                        "receipt": load_canonical_json_bytes(_read(receipt))},
                        (product, name, phase, source_target), "Elected Maven package predecessor")[0]

                binary = original("sdk", component, "binary", target)
                current_contract = original("contract", "contract", "metadata", "common")
                arguments = sdk_inputs["sdk"]["arguments"]
                if _read(current_contract["receiptPath"]) != _read(arguments["contract_metadata_receipt"]):
                    raise ValueError("Current elected Contract differs from authenticated SDK inputs")
                unchanged()

                capture = Path(sdk_inputs["capture"])
                capture_inventory = _inventory(capture, allow_empty=True)
                snapshot_regular_tree(capture, destination / "sdk-inputs-original", allow_empty=True)
                if _inventory(capture, allow_empty=True) != capture_inventory:
                    raise ValueError("Maven package SDK capture changed during retention")
                retained[destination / "sdk-inputs-original"] = capture_inventory
                selected = destination / "selection"
                selected.mkdir()
                for name, raw in (("impact-plan.json", before_files["plan"]),
                                  ("phase-plan.json", canonical_json_bytes(ready)),
                                  ("producer.json", canonical_json_bytes(producer))):
                    (selected / name).write_bytes(raw)
                retained[selected] = _inventory(selected)

                copied = destination / "binary-contract-original"
                snapshot_regular_tree(stage, copied / "stage")
                local = {**evidence, "stageRoot": str(copied / "stage")}
                for name in ("phaseReceipt", "attestation", "attestationSignature", "publicKey"):
                    source = Path(evidence[name])
                    output = copied / "evidence" / source.name
                    if output.exists():
                        raise ValueError("Original binary Contract file names must not collide")
                    output.parent.mkdir(parents=True, exist_ok=True)
                    output.write_bytes(before_files["binaryContract/" + name])
                    local[name] = str(output)
                snapshot_regular_tree(trees["binaryClosure"],
                    copied / "evidence" / CONTRACT_EXECUTION_CLOSURE_DIRECTORY)
                if evidence["keyring"] is not None:
                    _public_policy(Path(evidence["keyring"]), Path(evidence["keysDirectory"]), copied / "policy")
                    local.update(keyring=str(copied / "policy/product-signing-keys.json"),
                                 keysDirectory=str(copied / "policy/keys"))
                write_canonical_json(copied / "invocation.json", local)
                retained[copied] = _inventory(copied, allow_empty=True)
                values.append((local, canonical_json_bytes(local)))
                unchanged()
                result = execute_package(ready, producer=producer, sdk_version=selection["sdkVersion"],
                    sdk_binary=binary, compatibility_request=sdk_inputs["sdk"]["directory"] / REQUEST_NAME,
                    repository_root=root, destination=destination / "worker", environ=environ)
                retained[result["stage"]] = result["outputInventory"]
                retained[destination / "worker"] = _inventory(destination / "worker", allow_empty=True)
                unchanged()
                provisional = product_reuse.finalize_phase_object(stage_root=result["stage"], phase_plan=ready,
                    producer=producer, product_version=selection["sdkVersion"],
                    trust_domain="development" if producer["event"] == "pull_request" else "release", destination=candidate)
                candidate_inventory = _inventory(candidate)
                candidate_receipt = _read(candidate / PHASE_RECEIPT_NAME)
                verified, raw = verify_sdk_package_inputs(root, result["stage"], candidate / PHASE_RECEIPT_NAME,
                    sdk_inputs["sdk"]["directory"] / REQUEST_NAME, binary_stage_root=binary["stage"],
                    binary_receipt_path=binary["receiptPath"], binary_contract_evidence=local)
                if (raw != candidate_receipt or _read(candidate / PHASE_RECEIPT_NAME) != candidate_receipt
                        or canonical_json_bytes(verified) != raw or _inventory(candidate) != candidate_inventory
                        or verified != provisional["receipt"]):
                    raise ValueError("Maven package full gate returned a different candidate receipt")
                unchanged()
                if _inventory(capture, allow_empty=True) != capture_inventory:
                    raise ValueError("Maven package SDK capture changed before context exit")
            unchanged()
            product_reuse._runtime_worker_checkout(root, producer)
            if (_inventory(candidate) != candidate_inventory or verify_phase_shard(candidate, instance) != provisional):
                raise ValueError("Maven package candidate changed after full verification")
            publish_regular_tree(candidate, destination / "shard")
            final = verify_phase_shard(destination / "shard", instance)
            if final != provisional:
                raise ValueError("Maven package published shard differs from its verified candidate")
            unchanged()
        return final
    finally:
        unchanged()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("plan", "destination", "keyring", "keys-directory", "repository-root",
                 "binary-contract-evidence"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--discovery-root", dest="discovery", type=Path, required=True)
    parser.add_argument("--state-root", dest="state", type=Path, required=True)
    parser.add_argument("--component", choices=tuple(_TARGETS), required=True)
    for name in ("expected-build-key", "sdk-inputs-artifact-sha256", "trusted-workflow-sha"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--sdk-inputs-artifact-id", type=int, required=True)
    for name in ("sdk-validation-tooling", "sdk-apple-validation-policy"):
        parser.add_argument("--" + name, type=Path)
    arguments = vars(parser.parse_args(argv))
    try:
        for name in ("binary_contract_evidence", "sdk_validation_tooling", "sdk_apple_validation_policy"):
            path = arguments.pop(name)
            if path is not None:
                arguments[name] = product_reuse._canonical_control(path, "Caller " + name)
        execute(**arguments, environ=os.environ, token=os.environ.get("GITHUB_TOKEN", ""))
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
