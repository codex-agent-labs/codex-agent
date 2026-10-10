"""Admit elected JavaScript metadata using authenticated original executions."""

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
    read_regular_file_bytes,
)
from products.registry import PhaseInstanceId
from products.restore import PHASE_RECEIPT_NAME, verify_phase_shard
from products.sdk_inputs import REQUEST_NAME
from products.sdk_javascript_metadata_admission import verify_sdk_javascript_metadata_admission
from products.sdk_native_metadata import _inventory
from products.sdk_package import _require_capability_output_separate, verify_sdk_package_inputs
from sdk_javascript_metadata_phase import execute as execute_metadata


def execute(plan, discovery, state, destination, *, expected_build_key,
            sdk_inputs_artifact_id, sdk_inputs_artifact_sha256,
            trusted_workflow_sha,
            keyring, keys_directory, repository_root, environ, token,
            tooling_evidence, tooling_public_key, java_executable, policy_revision,
            required_trust_domain, tooling_keyring=None, tooling_keys_directory=None,
            validation_artifact_id=None, validation_artifact_sha256=None,
            sdk_apple_validation_policy=None, sdk_facade_metadata_admission=None,
            sdk_android_metadata_admission=None):
    """Finalize once privately; publish only after full input and content gates.

    The observed original validation upload supplies the consumer directory.
    Current Contract payload equality does not relabel retained Runtime receipts.
    When no explicit locator pair is supplied, locate only the selected original
    validation receipt's upload. An invalid explicit pair never falls back.
    """
    if (validation_artifact_id is None) != (validation_artifact_sha256 is None):
        raise ValueError("JavaScript validation upload ID and digest must be supplied together")
    root = Path(repository_root).resolve(strict=True)
    plan = Path(plan).absolute()
    discovery, state, destination = product_reuse._product_materialization_paths(root, discovery, state, destination)
    destination.relative_to(root)
    trees = {Path(path) for path in (discovery, state, keys_directory, tooling_evidence,
                                   tooling_keys_directory) if path is not None}
    files = {Path(path) for path in (plan, keyring, tooling_public_key, java_executable,
                                   tooling_keyring) if path is not None}
    _require_capability_output_separate(destination, [*trees, *files])
    if destination.exists() or destination.is_symlink():
        raise ValueError("JavaScript metadata destination must not exist")
    controls = {path: _inventory(path, allow_empty=True) for path in trees}
    raw_controls = {path: read_regular_file_bytes(path, max_bytes=128 * 1024 * 1024,
                   reject_symlink_parents=True) for path in files}

    def controls_unchanged():
        if (any(_inventory(path, allow_empty=True) != before for path, before in controls.items())
                or any(read_regular_file_bytes(path, max_bytes=128 * 1024 * 1024,
                    reject_symlink_parents=True) != raw for path, raw in raw_controls.items())):
            raise ValueError("JavaScript metadata original plan, state or caller policy changed")

    tooling = {"evidence": str(Path(tooling_evidence).absolute()),
        "publicKey": str(Path(tooling_public_key).absolute()),
        "javaExecutable": str(Path(java_executable).absolute()),
        "requiredTrustDomain": required_trust_domain,
        "keyring": str(Path(tooling_keyring).absolute()) if tooling_keyring is not None else None,
        "keysDirectory": str(Path(tooling_keys_directory).absolute()) if tooling_keys_directory is not None else None}
    apple = {} if sdk_apple_validation_policy is None else {"sdk_apple_validation_policy": sdk_apple_validation_policy}
    if sdk_facade_metadata_admission is not None:
        apple["sdk_facade_metadata_admission"] = sdk_facade_metadata_admission
    if sdk_android_metadata_admission is not None:
        apple["sdk_android_metadata_admission"] = sdk_android_metadata_admission
    instance = PhaseInstanceId("sdk", "javascript", "metadata", "node")
    identity = dict(product="sdk", component="javascript", phase="metadata", target="node")
    with tempfile.TemporaryDirectory(prefix="sdk-javascript-metadata-") as temporary:
        private = Path(temporary).resolve()
        _require_capability_output_separate(private, [root, *trees, *files])
        capture, candidate = private / "validation-upload", private / "shard"
        with sdk_workflow.verified_inputs(plan, discovery, state,
                artifact_id=sdk_inputs_artifact_id, artifact_sha256=sdk_inputs_artifact_sha256,
                trusted_workflow_sha=trusted_workflow_sha, keyring=keyring, keys_directory=keys_directory,
                repository_root=root, environ=environ, token=token, sdk_validation_tooling=tooling, **apple) as inputs:
            controls_unchanged()
            selection = inputs["selection"]
            if identity not in selection["consumers"]:
                raise ValueError("JavaScript metadata is not selected")
            prepared = destination / "inputs"
            ready = product_reuse.materialize_product_predecessors(plan, discovery, state, instance, prepared,
                expected_build_key=expected_build_key, repository_root=root, environ=environ,
                sdk_validation_tooling=tooling, sdk_original_workflow_sha=trusted_workflow_sha, **apple)
            before = _inventory(prepared, allow_empty=True)
            ready_bytes = canonical_json_bytes(ready)
            producer = product_reuse.validate_producer(product_reuse._canonical_control(
                prepared / "producer.json", "Elected JavaScript metadata producer"))
            producer_bytes = canonical_json_bytes(producer)
            contract = product_reuse.validate_phase_receipt(product_reuse._canonical_control(
                prepared / "contract-contract-metadata-common/phase-receipt.json", "Current Contract metadata"))
            bundles = [row for row in contract["outputs"] if row["kind"] == "contract-bundle"]
            if (tuple(contract[name] for name in ("product", "component", "phase", "target")) !=
                    ("contract", "contract", "metadata", "common") or len(bundles) != 1
                    or bundles[0]["sha256"] != selection["contractPayloadSha256"]):
                raise ValueError("Current Contract differs from authenticated JavaScript metadata inputs")

            def inputs_unchanged():
                controls_unchanged()
                if (_inventory(prepared, allow_empty=True) != before
                        or canonical_json_bytes(ready) != ready_bytes
                        or canonical_json_bytes(producer) != producer_bytes):
                    raise ValueError("JavaScript metadata elected originals changed")

            allowed = {("contract", "contract", "binary", "common"),
                ("sdk", "javascript", "package", "node"), ("sdk", "javascript", "validation", "node"),
                ("runtime", "node-js", "package", "node-js"),
                ("runtime", "node-js", "validation", "node-js-binding")}

            def original(product, component, phase, target):
                fields = product, component, phase, target
                if fields not in allowed:
                    raise ValueError("Unexpected JavaScript metadata predecessor")
                directory = prepared / "-".join(fields)
                receipt_path = directory / PHASE_RECEIPT_NAME
                raw = read_regular_file_bytes(receipt_path, reject_symlink_parents=True)
                receipt = product_reuse.validate_phase_receipt(load_canonical_json_bytes(raw))
                if (tuple(receipt[name] for name in ("product", "component", "phase", "target")) != fields
                        or product == "runtime" and raw != inputs["runtime"]["receiptBytes"].get(PhaseInstanceId(*fields))):
                    raise ValueError("JavaScript metadata predecessor differs from its verified original")
                manifest = product_reuse.verify_output_manifest_identity(directory / "stage", *fields, receipt["productVersion"])
                if manifest["outputs"] != receipt["outputs"]:
                    raise ValueError("JavaScript metadata predecessor stage differs from its original receipt")
                inputs_unchanged()
                return {"stage": directory / "stage", "receiptPath": receipt_path, "receipt": receipt}

            contract_input = original("contract", "contract", "binary", "common")
            package = original("sdk", "javascript", "package", "node")
            validation = original("sdk", "javascript", "validation", "node")
            runtime_package = original("runtime", "node-js", "package", "node-js")
            runtime_validation = original("runtime", "node-js", "validation", "node-js-binding")
            if validation_artifact_id is None:
                from sdk_javascript_validation_locator import locate_javascript_validation_upload
                locator = locate_javascript_validation_upload(validation["receiptPath"],
                    trusted_workflow_sha=trusted_workflow_sha, token=token)
                validation_artifact_id = locator["artifact_id"]
                validation_artifact_sha256 = locator["artifact_sha256"]
                inputs_unchanged()
            transport = product_reuse.capture_sdk_javascript_validation_upload(plan, capture,
                validation_receipt_path=validation["receiptPath"], artifact_id=validation_artifact_id,
                artifact_sha256=validation_artifact_sha256, trusted_workflow_sha=trusted_workflow_sha,
                repository_root=root, environ=environ, token=token)
            capture_inventory = _inventory(capture, allow_empty=True)
            consumer = Path(transport["originalConsumerDirectory"])
            # Deliberate original-source replay after upload authentication,
            # never a current-tooling failure fallback or a new metadata producer.
            validation_policy_revision = validation["receipt"]["producer"]["commit"]

            def unchanged():
                inputs_unchanged()
                if _inventory(capture, allow_empty=True) != capture_inventory:
                    raise ValueError("JavaScript metadata original validation capture changed")

            unchanged()
            package_receipt, package_raw = verify_sdk_package_inputs(root, package["stage"], package["receiptPath"],
                inputs["sdk"]["directory"] / REQUEST_NAME, runtime_package_stage=runtime_package["stage"],
                runtime_package_receipt=runtime_package["receiptPath"])
            if package_receipt != package["receipt"] or package_raw != read_regular_file_bytes(package["receiptPath"]):
                raise ValueError("JavaScript package gate returned a different original receipt")
            unchanged()
            trust = "development" if producer["event"] == "pull_request" else "release"
            result = execute_metadata(ready, producer=producer, sdk_version=selection["sdkVersion"],
                trust_domain=trust, repository_root=root, destination=destination / "worker",
                predecessor=original, original_consumer_directory=consumer, environ=environ)
            unchanged()
            if _inventory(result["stage"]) != result["outputInventory"]:
                raise ValueError("JavaScript metadata output changed before private finalization")
            finalized = product_reuse.finalize_phase_object(stage_root=result["stage"], phase_plan=ready,
                producer=producer, product_version=selection["sdkVersion"], trust_domain=trust, destination=candidate)
            candidate_inventory = _inventory(candidate)
            admitted, raw = verify_sdk_javascript_metadata_admission(
                contract_stage=contract_input["stage"], contract_receipt=contract_input["receiptPath"],
                package_stage=package["stage"], package_receipt=package["receiptPath"],
                validation_stage=validation["stage"], validation_receipt=validation["receiptPath"],
                runtime_validation_stage=runtime_validation["stage"], runtime_validation_receipt=runtime_validation["receiptPath"],
                metadata_stage=result["stage"], metadata_receipt=candidate / PHASE_RECEIPT_NAME,
                original_consumer_directory=consumer, repository=root, tooling_evidence=tooling_evidence,
                tooling_public_key=tooling_public_key, java_executable=java_executable,
                policy_revision=validation_policy_revision, required_trust_domain=required_trust_domain,
                tooling_keyring=tooling_keyring, tooling_keys_directory=tooling_keys_directory)
            if admitted != finalized["receipt"] or raw != read_regular_file_bytes(candidate / PHASE_RECEIPT_NAME):
                raise ValueError("JavaScript metadata admission returned a different candidate receipt")
            unchanged()
        unchanged()

        def outputs_unchanged():
            product_reuse._runtime_worker_checkout(root, producer)
            if (_inventory(result["stage"]) != result["outputInventory"]
                    or _inventory(candidate) != candidate_inventory or verify_phase_shard(candidate, instance) != finalized):
                raise ValueError("JavaScript metadata candidate changed after full admission")

        outputs_unchanged()
        publish_regular_tree(capture, destination / "validation-upload", allow_empty=True)
        unchanged()
        outputs_unchanged()
        if _inventory(destination / "validation-upload", allow_empty=True) != capture_inventory:
            raise ValueError("JavaScript metadata retained validation upload changed")
        publish_regular_tree(candidate, destination / "shard")
    return verify_phase_shard(destination / "shard", instance)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("plan", "destination", "keyring", "keys-directory", "repository-root",
                 "tooling-evidence", "tooling-public-key", "java-executable"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--discovery-root", dest="discovery", type=Path, required=True)
    parser.add_argument("--state-root", dest="state", type=Path, required=True)
    for name in ("expected-build-key", "sdk-inputs-artifact-sha256",
                 "trusted-workflow-sha", "policy-revision"):
        parser.add_argument(f"--{name}", required=True)
    parser.add_argument("--sdk-inputs-artifact-id", type=int, required=True)
    parser.add_argument("--validation-artifact-id", type=int)
    parser.add_argument("--validation-artifact-sha256")
    parser.add_argument("--required-trust-domain", choices=("development", "release"), required=True)
    parser.add_argument("--tooling-keyring", type=Path)
    parser.add_argument("--tooling-keys-directory", type=Path)
    parser.add_argument("--sdk-apple-validation-policy", type=Path)
    add_metadata_admission_arguments(parser)
    args = parser.parse_args(argv)
    arguments = {name: value for name, value in vars(args).items()
                 if name not in {"sdk_facade_metadata_policy", "sdk_android_metadata_policy"}}
    if (arguments["validation_artifact_id"] is None) != (arguments["validation_artifact_sha256"] is None):
        parser.error("JavaScript validation upload ID and digest must be supplied together")
    if (arguments["tooling_keyring"] is None) != (arguments["tooling_keys_directory"] is None):
        parser.error("JavaScript tooling keyring and keys directory must be supplied together")
    try:
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
