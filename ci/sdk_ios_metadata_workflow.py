"""Produce iOS SDK metadata from two fully authenticated Apple validations."""

import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse
from sdk_metadata_policy import add_metadata_admission_arguments, metadata_admission_options
from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, publish_regular_tree,
    read_regular_file_bytes, regular_file_inventory, require_exact_keys,
    require_integer, require_semver, require_sha256, sha256_bytes, write_canonical_json,
)
from products.receipt import validate_producer, verify_output_manifest_identity
from products.registry import PhaseInstanceId
from products.restore import PHASE_PLAN_KEYS, PHASE_RECEIPT_NAME, verify_phase_shard
from products.sdk_apple_metadata import OUTPUT_KIND, OUTPUT_PATH
from products.sdk_apple_metadata_admission import (
    verified_sdk_apple_metadata_inputs, verify_sdk_apple_metadata_admission,
)
from products.sdk_apple_validation_admission import apple_validation_policy_arguments
from products.sdk_package import _require_capability_output_separate
from products.signing_isolation import require_no_signing_secret


_INSTANCE = PhaseInstanceId("sdk", "sdk-ios", "metadata", "ios")
_TARGETS = ("ios-arm64", "ios-simulator-arm64")
_LIMIT = 16 * 1024 * 1024


def _tooling(policy):
    parsed = apple_validation_policy_arguments(policy)
    return {
        "evidence": str(parsed["tooling_evidence"]),
        "publicKey": str(parsed["tooling_public_key"]),
        "javaExecutable": str(parsed["java_executable"]),
        "requiredTrustDomain": parsed["required_trust_domain"],
        "keyring": str(parsed["tooling_keyring"]) if parsed["tooling_keyring"] is not None else None,
        "keysDirectory": str(parsed["tooling_keys_directory"])
        if parsed["tooling_keys_directory"] is not None else None,
    }, parsed


def _execute_metadata(plan, *, producer, sdk_version, package_stage, validation_contents,
                      repository_root, destination, environ):
    """Run the fixed artifact-only Gradle producer; grant no receipt authority."""
    selected = require_exact_keys(plan, PHASE_PLAN_KEYS, "iOS metadata phase plan")
    if (require_integer(selected["schemaVersion"], "iOS metadata plan schema", 1) != 1
            or tuple(selected[name] for name in ("product", "component", "phase", "target")) !=
            ("sdk", "sdk-ios", "metadata", "ios")):
        raise ValueError("Unsupported iOS metadata phase plan")
    require_sha256(selected["buildKey"], "Elected iOS metadata key")
    current_producer = validate_producer(producer, "Elected iOS metadata producer")
    version = require_semver(sdk_version, "Elected iOS metadata SDK version")
    contents = {target: Path(path) for target, path in
                require_exact_keys(validation_contents, _TARGETS, "iOS metadata validation inputs").items()}
    package = Path(package_stage)
    originals = {"package": regular_file_inventory(package)}
    raw = {target: read_regular_file_bytes(path, max_bytes=_LIMIT, reject_symlink_parents=True)
           for target, path in contents.items()}
    plan_bytes, producer_bytes = canonical_json_bytes(selected), canonical_json_bytes(current_producer)

    def originals_unchanged():
        if (canonical_json_bytes(selected) != plan_bytes
                or canonical_json_bytes(current_producer) != producer_bytes
                or regular_file_inventory(package) != originals["package"]
                or any(read_regular_file_bytes(contents[target], max_bytes=_LIMIT,
                    reject_symlink_parents=True) != value for target, value in raw.items())):
            raise ValueError("Original iOS metadata inputs changed during execution")

    root, destination = Path(repository_root).resolve(strict=True), Path(destination).absolute()
    stage = root / "build/product-stage/sdk/sdk-ios/metadata"
    inputs = [package, *contents.values()]
    _require_capability_output_separate(destination, [stage, *inputs])
    _require_capability_output_separate(stage, inputs)
    if any(path.exists() or path.is_symlink() for path in (destination, stage)):
        raise ValueError("iOS metadata requires fresh diagnostics and product output")
    product_reuse._prepare_destination(stage, root).rmdir()
    environment, wrapper = product_reuse._runtime_worker_environment(
        root, current_producer, destination, environ)
    destination = product_reuse._prepare_destination(destination, root)
    fields = {
        "codexAgent.product": "sdk", "codexAgent.component": "sdk-ios",
        "codexAgent.phase": "metadata", "codexAgent.target": "ios",
        "codexAgent.candidateCommit": current_producer["commit"],
        "codexAgent.candidateTree": current_producer["tree"],
        "codexAgent.sdkVersion": version,
        "codexAgent.iosMetadataPackageStage": str(package),
        "codexAgent.iosMetadataDeviceValidationContent": str(contents["ios-arm64"]),
        "codexAgent.iosMetadataSimulatorValidationContent": str(contents["ios-simulator-arm64"]),
    }

    def unchanged():
        product_reuse._runtime_worker_checkout(root, current_producer)
        bytecode = destination / "python-bytecode"
        if bytecode.exists() or bytecode.is_symlink():
            raise ValueError("iOS metadata private bytecode namespace was modified")
        originals_unchanged()

    unchanged()
    command = product_reuse._runtime_worker_command(wrapper, fields, environment, build_directory=".")
    if command.count("ciProductPhase") != 1:
        raise ValueError("iOS metadata worker no longer runs the fixed product phase")
    started, return_code, launch_error = time.monotonic_ns(), None, None
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
            "producer": dict(current_producer), "buildKey": selected["buildKey"],
            "command": command, "workingDirectory": str(root), "returnCode": return_code,
            "launchError": launch_error, "elapsedNs": time.monotonic_ns() - started})
        unchanged()
    if return_code != 0:
        raise ValueError(f"iOS metadata failed with exit code {return_code}; see {destination / 'gradle.log'}")
    manifest = verify_output_manifest_identity(stage, "sdk", "sdk-ios", "metadata", "ios", version)
    if (len(manifest["outputs"]) != 1 or manifest["outputs"][0]["kind"] != OUTPUT_KIND
            or manifest["outputs"][0]["relativePath"] != OUTPUT_PATH):
        raise ValueError("iOS metadata canonical output is missing or ambiguous")
    inventory = regular_file_inventory(stage)
    unchanged()
    if regular_file_inventory(stage) != inventory:
        raise ValueError("iOS metadata output changed during verification")
    return {"stage": stage, "content": stage / OUTPUT_PATH,
            "outputInventory": inventory, "diagnostics": destination}


def execute(plan, discovery, state, destination, *, expected_build_key,
            repository_root, environ, trusted_workflow_sha, sdk_apple_validation_policy=None,
            sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None):
    """Finalize only after both signed validation gates and package lineage agree."""
    require_no_signing_secret(environ)
    if sdk_apple_validation_policy is None:
        raise ValueError("iOS metadata requires caller-owned Apple validation policy")
    root = Path(repository_root).resolve(strict=True)
    plan = Path(plan).absolute()
    discovery, state, destination = product_reuse._product_materialization_paths(
        root, discovery, state, destination)
    destination.relative_to(root)
    if destination.exists() or destination.is_symlink():
        raise ValueError("iOS metadata destination must not exist")
    tooling, policy_paths = _tooling(sdk_apple_validation_policy)
    admissions = {name: value for name, value in (
        ("sdk_facade_metadata_admission", sdk_facade_metadata_admission),
        ("sdk_android_metadata_admission", sdk_android_metadata_admission),
    ) if value is not None}
    controls = [plan, discovery, state,
                *(path for path in policy_paths.values() if isinstance(path, Path))]
    _require_capability_output_separate(destination, controls)
    _require_capability_output_separate(root / "build/product-stage/sdk/sdk-ios/metadata", controls)
    policy_bytes = canonical_json_bytes(sdk_apple_validation_policy)
    files = {plan, *(path for path in policy_paths.values() if isinstance(path, Path) and path.is_file())}
    directories = {discovery, state,
        *(path for path in policy_paths.values() if isinstance(path, Path) and path.is_dir())}
    file_bytes = {path: read_regular_file_bytes(path, max_bytes=128 * 1024 * 1024,
                  reject_symlink_parents=True) for path in files}
    inventories = {path: regular_file_inventory(path, allow_empty=True) for path in directories}
    if file_bytes[plan] != read_regular_file_bytes(policy_paths["plan"], max_bytes=_LIMIT,
                                                   reject_symlink_parents=True):
        raise ValueError("Apple metadata policy plan differs from the elected impact plan")

    def controls_unchanged():
        require_no_signing_secret(environ)
        if (canonical_json_bytes(sdk_apple_validation_policy) != policy_bytes
                or any(read_regular_file_bytes(path, max_bytes=128 * 1024 * 1024,
                    reject_symlink_parents=True) != value for path, value in file_bytes.items())
                or any(regular_file_inventory(path, allow_empty=True) != value
                       for path, value in inventories.items())):
            raise ValueError("iOS metadata election state or caller policy changed")

    verified = product_reuse._verified_product_state(plan, discovery, state, root, environ, tooling,
        sdk_original_workflow_sha=trusted_workflow_sha,
        sdk_apple_validation_policy=sdk_apple_validation_policy, **admissions)
    ready = verified.prior_ready_plans.get(_INSTANCE)
    if ready is None or ready["buildKey"] != expected_build_key:
        raise ValueError("iOS metadata is not ready with the elected build key")
    version = verified.expected_fixed["versions"]["sdk"]
    producer = verified.producer
    ready_bytes = canonical_json_bytes(ready)
    producer_bytes = canonical_json_bytes(producer)
    controls_unchanged()
    prepared = destination / "inputs"
    materialized = product_reuse.materialize_product_predecessors(plan, discovery, state, _INSTANCE, prepared,
        expected_build_key=expected_build_key, repository_root=root, environ=environ,
        sdk_validation_tooling=tooling, sdk_apple_validation_policy=sdk_apple_validation_policy,
        sdk_original_workflow_sha=trusted_workflow_sha,
        **admissions)
    controls_unchanged()
    if canonical_json_bytes(ready) != ready_bytes or canonical_json_bytes(producer) != producer_bytes:
        raise ValueError("iOS metadata election changed during predecessor materialization")
    if materialized != ready:
        raise ValueError("Materialized iOS metadata election differs from its authenticated state")
    prepared_inventory = regular_file_inventory(prepared, allow_empty=True)
    materialized_bytes = canonical_json_bytes(materialized)
    prepared_producer = product_reuse.validate_producer(product_reuse._canonical_control(
        prepared / "producer.json", "Elected iOS metadata producer"))
    if prepared_producer != producer:
        raise ValueError("Materialized iOS metadata producer differs from its authenticated state")

    validation_receipts = {}
    for target in _TARGETS:
        directory = prepared / f"sdk-sdk-ios-validation-{target}"
        receipt_path = directory / PHASE_RECEIPT_NAME
        raw = read_regular_file_bytes(receipt_path, max_bytes=_LIMIT, reject_symlink_parents=True)
        receipt = product_reuse.validate_phase_receipt(load_canonical_json_bytes(raw))
        if (tuple(receipt[name] for name in ("product", "component", "phase", "target")) !=
                ("sdk", "sdk-ios", "validation", target) or receipt["productVersion"] != version):
            raise ValueError("iOS metadata validation predecessor has the wrong identity or version")
        manifest = verify_output_manifest_identity(directory / "stage", "sdk", "sdk-ios", "validation", target, version)
        if manifest["outputs"] != receipt["outputs"]:
            raise ValueError("iOS metadata validation predecessor differs from its receipt")
        validation_receipts[target] = receipt_path

    records = {"sdkAppleValidationEvidence": list(
        verified.rebased_request.get("sdkAppleValidationEvidence", []))}
    product_reuse._merge_native_comparison_records(records,
        product_reuse._retained_apple_handoffs(state, root), key="sdkAppleValidationEvidence")
    by_digest = {record["receiptSha256"]: record for record in records.get("sdkAppleValidationEvidence", [])}
    selected_records = []
    for target in _TARGETS:
        digest = sha256_bytes(read_regular_file_bytes(validation_receipts[target]))
        record = by_digest.get(digest)
        if record is None or record["target"] != target:
            raise ValueError("iOS metadata lacks the exact signed validation carrier")
        selected_records.append(record)
    selected_records.sort(key=lambda record: record["receiptSha256"])

    def inputs_unchanged():
        controls_unchanged()
        if (regular_file_inventory(prepared, allow_empty=True) != prepared_inventory
                or canonical_json_bytes(ready) != ready_bytes
                or canonical_json_bytes(materialized) != materialized_bytes
                or canonical_json_bytes(producer) != producer_bytes
                or canonical_json_bytes(prepared_producer) != producer_bytes):
            raise ValueError("iOS metadata authenticated predecessors changed")

    with tempfile.TemporaryDirectory(prefix="sdk-ios-metadata-") as temporary:
        candidate = Path(temporary).resolve() / "shard"
        inputs_unchanged()
        with verified_sdk_apple_metadata_inputs(repository=root,
                validation_receipts=validation_receipts, evidence_root=root,
                evidence_records=selected_records, policy_revision=producer["commit"],
                policy=sdk_apple_validation_policy) as original:
            inputs_unchanged()
            result = _execute_metadata(ready, producer=producer, sdk_version=version,
                package_stage=original["package_stage"], validation_contents=original["validation_contents"],
                repository_root=root, destination=destination / "worker", environ=environ)
            expected_content = canonical_json_bytes(original["content"])
            if read_regular_file_bytes(result["content"], max_bytes=_LIMIT,
                                       reject_symlink_parents=True) != expected_content:
                raise ValueError("iOS metadata producer differs from authenticated original inputs")
            output_inventory = regular_file_inventory(result["stage"])
            diagnostics_inventory = regular_file_inventory(result["diagnostics"], allow_empty=True)
            inputs_unchanged()
        # The original full gates must exit successfully before a receipt exists.
        inputs_unchanged()
        if (regular_file_inventory(result["stage"]) != output_inventory
                or regular_file_inventory(result["diagnostics"], allow_empty=True) != diagnostics_inventory
                or read_regular_file_bytes(result["content"], max_bytes=_LIMIT,
                    reject_symlink_parents=True) != expected_content):
            raise ValueError("iOS metadata output changed after original admission")
        trust = "development" if producer["event"] == "pull_request" else "release"
        product_reuse._runtime_worker_checkout(root, producer)
        finalized = product_reuse.finalize_phase_object(stage_root=result["stage"], phase_plan=ready,
            producer=producer, product_version=version, trust_domain=trust, destination=candidate)
        candidate_inventory = regular_file_inventory(candidate)
        admitted, raw = verify_sdk_apple_metadata_admission(repository=root,
            metadata_stage=result["stage"], metadata_receipt=candidate / PHASE_RECEIPT_NAME,
            validation_receipts=validation_receipts, evidence_root=root,
            evidence_records=selected_records, policy_revision=producer["commit"],
            policy=sdk_apple_validation_policy)
        if admitted != finalized["receipt"] or raw != read_regular_file_bytes(candidate / PHASE_RECEIPT_NAME):
            raise ValueError("iOS metadata admission returned a different candidate receipt")
        inputs_unchanged()
        product_reuse._runtime_worker_checkout(root, producer)
        if (regular_file_inventory(result["stage"]) != output_inventory
                or regular_file_inventory(result["diagnostics"], allow_empty=True) != diagnostics_inventory
                or regular_file_inventory(candidate) != candidate_inventory
                or verify_phase_shard(candidate, _INSTANCE) != finalized):
            raise ValueError("iOS metadata candidate changed after full admission")
        publish_regular_tree(candidate, destination / "shard")
    return verify_phase_shard(destination / "shard", _INSTANCE)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("plan", "destination", "repository-root"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--discovery-root", dest="discovery", type=Path, required=True)
    parser.add_argument("--state-root", dest="state", type=Path, required=True)
    parser.add_argument("--expected-build-key", required=True)
    parser.add_argument("--trusted-workflow-sha", required=True)
    parser.add_argument("--sdk-apple-validation-policy", type=Path)
    add_metadata_admission_arguments(parser)
    arguments = vars(parser.parse_args(argv))
    try:
        with metadata_admission_options(arguments) as admissions:
            policy = arguments.pop("sdk_apple_validation_policy")
            if policy is not None:
                arguments["sdk_apple_validation_policy"] = product_reuse._canonical_control(
                    policy, "Caller Apple validation policy")
            execute(**arguments, environ=os.environ, **admissions)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
