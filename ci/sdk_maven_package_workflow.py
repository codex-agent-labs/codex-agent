"""Compose elected Core/Android packages without inventing original authority."""

import argparse
from contextlib import ExitStack
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
    read_regular_file_bytes, require_exact_keys, require_integer, require_sha256,
    snapshot_regular_tree, write_canonical_json,
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
from sdk_maven_original import _context, verified_original_maven_phase, verified_retained_maven_phase


_TARGETS = {"sdk-core": "common", "sdk-android": "android"}
_LIMIT = 512 * 1024 * 1024


def _read(path):
    return read_regular_file_bytes(Path(path), max_bytes=_LIMIT, reject_symlink_parents=True)


def execute(plan, discovery, state, destination, *, component, expected_build_key,
            sdk_inputs_artifact_id, sdk_inputs_artifact_sha256, trusted_workflow_sha,
            keyring, keys_directory, binary_contract_evidence, binary_original_context,
            repository_root, environ, token, binary_artifact_id=None, binary_artifact_sha256=None,
            binary_capture_root=None, android_runtime_archive=None,
            sdk_validation_tooling=None, sdk_apple_validation_policy=None):
    """Publish one shard only after full original gates and successful context exit.

    The binary's original Contract evidence is mandatory caller policy, even if
    the currently selected Contract is equivalent. The existing full package
    gate authenticates that original binary plan and compares its components to
    the current S858 Contract. No receipt or original producer is substituted.
    The selected binary's full original upload reader must remain held through
    consumption and provisional finalization. Retained mode requires the caller
    to authenticate its enclosing carrier; uploaded context is not caller policy.
    Retained captures and invocation paths stay outside deterministic content.
    """
    require_no_signing_secret(environ)
    if component not in _TARGETS:
        raise ValueError("Maven package controller requires Core or Android")
    _context(binary_original_context, "binary")
    binary_context_bytes = canonical_json_bytes(binary_original_context)
    if (binary_capture_root is None) == (binary_artifact_id is None and binary_artifact_sha256 is None):
        raise ValueError("Maven package requires exactly one original binary upload or retained capture")
    if binary_capture_root is None:
        require_integer(binary_artifact_id, "Original binary upload ID", 1)
        require_sha256(binary_artifact_sha256, "Original binary upload digest")
    if (android_runtime_archive is not None) != (component == "sdk-android"):
        raise ValueError("Maven package requires the original Android archive only for Android binary replay")
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
    if binary_capture_root is not None:
        trees["binaryCapture"] = _path(str(binary_capture_root), "Caller-authenticated original binary capture")
    if android_runtime_archive is not None:
        files["androidArchive"] = _path(str(android_runtime_archive), "Caller original Android archive")
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
                or canonical_json_bytes(binary_original_context) != binary_context_bytes
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
                    repository_root=root, environ=environ, token=token, **policies) as sdk_inputs, ExitStack() as binary_contexts:
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

                binary_arguments = dict(binary_contract_evidence=evidence,
                    original_context=binary_original_context, repository_root=root, environ=environ)
                if android_runtime_archive is not None:
                    binary_arguments["android_runtime_archive"] = files["androidArchive"]
                if binary_capture_root is None:
                    original_binary = binary_contexts.enter_context(verified_original_maven_phase(
                        plan, binary["receiptPath"], artifact_id=binary_artifact_id,
                        artifact_sha256=binary_artifact_sha256, trusted_workflow_sha=trusted_workflow_sha,
                        token=token, **binary_arguments))
                else:
                    original_binary = binary_contexts.enter_context(verified_retained_maven_phase(
                        plan, binary["receiptPath"], capture_root=trees["binaryCapture"], **binary_arguments))
                binary_receipt_bytes = _read(binary["receiptPath"])
                if (original_binary["receiptBytes"] != binary_receipt_bytes
                        or canonical_json_bytes(original_binary["receipt"]) != binary_receipt_bytes
                        or _read(original_binary["receiptPath"]) != binary_receipt_bytes
                        or _inventory(original_binary["stage"]) != _inventory(binary["stage"])):
                    raise ValueError("Original Maven binary proof differs from the elected predecessor")
                binary_capture = Path(original_binary["capture"])
                binary_capture_inventory = _inventory(binary_capture, allow_empty=True)
                binary_original = destination / "binary-original"
                snapshot_regular_tree(binary_capture, binary_original / "capture", allow_empty=True)
                write_canonical_json(binary_original / "context.json", binary_original_context)
                if (_inventory(binary_capture, allow_empty=True) != binary_capture_inventory
                        or _inventory(binary_original / "capture", allow_empty=True) != binary_capture_inventory
                        or _read(binary_original / "context.json") != binary_context_bytes):
                    raise ValueError("Original Maven binary capture changed during retention")
                retained[binary_original] = _inventory(binary_original, allow_empty=True)
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
                if _inventory(binary_capture, allow_empty=True) != binary_capture_inventory:
                    raise ValueError("Maven package original binary capture changed before context exit")
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
                 "binary-contract-evidence", "binary-original-context"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--discovery-root", dest="discovery", type=Path, required=True)
    parser.add_argument("--state-root", dest="state", type=Path, required=True)
    parser.add_argument("--component", choices=tuple(_TARGETS), required=True)
    for name in ("expected-build-key", "sdk-inputs-artifact-sha256", "trusted-workflow-sha"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--sdk-inputs-artifact-id", type=int, required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--binary-artifact-id", type=int)
    source.add_argument("--binary-capture-root", type=Path)
    parser.add_argument("--binary-artifact-sha256")
    parser.add_argument("--android-runtime-archive", type=Path)
    for name in ("sdk-validation-tooling", "sdk-apple-validation-policy"):
        parser.add_argument("--" + name, type=Path)
    arguments = vars(parser.parse_args(argv))
    if (arguments["binary_artifact_id"] is None) != (arguments["binary_artifact_sha256"] is None):
        parser.error("Original binary upload ID and digest must be supplied together")
    if (arguments["android_runtime_archive"] is not None) != (arguments["component"] == "sdk-android"):
        parser.error("Original Android archive is required only for Android binary replay")
    try:
        for name in ("binary_contract_evidence", "binary_original_context", "sdk_validation_tooling", "sdk_apple_validation_policy"):
            path = arguments.pop(name)
            if path is not None:
                arguments[name] = product_reuse._canonical_control(path, "Caller " + name)
        execute(**arguments, environ=os.environ, token=os.environ.get("GITHUB_TOKEN", ""))
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
