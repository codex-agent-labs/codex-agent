"""Execute one native host validation within the original SDK input lifetime.

Transport does not admit content. The existing package gate runs before the
consumer, and the existing validation-evidence stager performs full final
admission. No receipt or retained carrier is published before both complete.
"""

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
import sdk_workflow
from native_wrappers import host_classifier
from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, publish_regular_tree,
    read_regular_file_bytes, regular_file_inventory, require_exact_keys,
    require_integer, require_semver, require_sha256, sha256_bytes,
    snapshot_regular_tree, write_canonical_json,
)
from products.registry import NATIVE_BINDINGS, NATIVE_TARGETS, PHASE_INSTANCE_IDS, PhaseInstanceId
from products.restore import PHASE_PLAN_KEYS, PHASE_RECEIPT_NAME, verify_phase_shard
from products.sdk_inputs import REQUEST_NAME
from products.sdk_native_metadata import _inventory
from products.sdk_package import _require_capability_output_separate, verify_sdk_package_inputs
from products.sdk_validation_inputs import _request_inventory, stage_sdk_validation_evidence
from products.signatures import load_keyring, public_key_path
from sdk_native_phase import _runtime_originals, _runtime_originals_unchanged


_LIMIT = 16 * 1024 * 1024


def _execute_validation(plan, *, producer, sdk_version, repository_root, destination,
                        runtime_stages, staged_sdks, compatibility_request, package,
                        predecessor, environ, dotnet_executable, dart_executable,
                        dart_package_config, protected_inputs):
    """Fixed imported-only Gradle consumer; no caller command or success input."""
    require_exact_keys(plan, PHASE_PLAN_KEYS, "Native SDK validation plan")
    if require_integer(plan["schemaVersion"], "Native SDK plan schema", 1) != 1:
        raise ValueError("Unsupported native SDK validation plan schema")
    identity = PhaseInstanceId(*(plan[name] for name in ("product", "component", "phase", "target")))
    if (identity not in PHASE_INSTANCE_IDS or identity.product != "sdk"
            or identity.component not in NATIVE_BINDINGS or identity.phase != "validation"
            or identity.target not in NATIVE_TARGETS or host_classifier() != identity.target):
        raise ValueError("Native SDK validation requires its exact elected actual host")
    require_sha256(plan["buildKey"], "Native SDK validation build key")
    require_semver(sdk_version, "Native SDK version")
    product_reuse.validate_producer(producer)
    root, destination = Path(repository_root).resolve(strict=True), Path(destination).absolute()
    runtime_stages, sdks, request = map(Path, (runtime_stages, staged_sdks, compatibility_request))
    package_stage, package_receipt = Path(package["stage"]), Path(package["receiptPath"])
    paths = [runtime_stages, sdks, request, package_stage, package_receipt]
    optional = {"codexAgent.dotnetExecutable": dotnet_executable,
                "codexAgent.dartExecutable": dart_executable,
                "codexAgent.dartPackageConfig": dart_package_config}
    if identity.component == "csharp" and dotnet_executable is None:
        raise ValueError("C# native validation requires an explicit dotnet executable")
    if ((identity.component != "csharp" and dotnet_executable is not None)
            or (identity.component != "dart" and any(value is not None for value in
                                                     (dart_executable, dart_package_config)))):
        raise ValueError("Native SDK executable inputs must match the selected language")
    paths += [Path(value) for value in optional.values() if value is not None]
    if any(not path.is_absolute() for path in paths):
        raise ValueError("Native SDK validation inputs must be explicit absolute paths")
    tools = {Path(value): read_regular_file_bytes(Path(value), max_bytes=128 * 1024 * 1024,
                                                 reject_symlink_parents=True)
             for value in optional.values() if value is not None}
    runtime_inventory, sdk_inventory = _inventory(runtime_stages), _inventory(sdks)
    package_inventory = _inventory(package_stage)
    raw_package = read_regular_file_bytes(package_receipt, max_bytes=_LIMIT, reject_symlink_parents=True)
    receipt = product_reuse.validate_phase_receipt(load_canonical_json_bytes(raw_package))
    manifest = product_reuse.verify_output_manifest_identity(package_stage, "sdk", identity.component,
                                                             "package", "desktop", sdk_version)
    if (receipt != package["receipt"] or receipt["productVersion"] != sdk_version
            or tuple(receipt[name] for name in ("product", "component", "phase", "target")) !=
            ("sdk", identity.component, "package", "desktop") or receipt["outputs"] != manifest["outputs"]):
        raise ValueError("Native SDK validation package differs from its original receipt")
    originals = _runtime_originals(runtime_stages, runtime_inventory, predecessor)
    request_bytes = read_regular_file_bytes(request, max_bytes=_LIMIT, reject_symlink_parents=True)
    request_inventory = _request_inventory(request)
    plan_bytes, producer_bytes = canonical_json_bytes(plan), canonical_json_bytes(producer)
    component, tree = identity.component, producer["tree"]
    build = root / "codex-agent-sdk/build"
    stage = build / f"product-stage/sdk/{component}/validation"
    # Both invalidators execute on the imported-only branch. None of these
    # cleanup roots may contain an original, even if Gradle has no output there.
    owned = (stage, build / f"imported-sdk-product-stages/{tree}/{component}-package",
             build / f"native-wrapper-capability-inputs/{tree}/{component}",
             build / f"imported-native-wrapper-runtime-stages/{tree}",
             build / f"native-wrapper-c-abi-sdks/{tree}",
             build / f"native-wrapper-package-assets/{tree}")
    if any(path.exists() or path.is_symlink() for path in (*owned, destination)):
        raise ValueError("Native SDK validation requires fresh task and diagnostic outputs")
    protected = [*paths, *request_inventory, *(Path(path) for path in protected_inputs),
                 *(path for original, _, raw, _ in originals for path in (original, raw))]
    _require_capability_output_separate(destination, [*protected, *owned])
    for output in owned:
        _require_capability_output_separate(output, protected)
    environment, wrapper = product_reuse._runtime_worker_environment(root, producer, destination, environ)

    def unchanged():
        product_reuse._runtime_worker_checkout(root, producer)
        bytecode = destination / "python-bytecode"
        if bytecode.exists() or bytecode.is_symlink():
            raise ValueError("Native SDK private bytecode namespace was modified")
        _runtime_originals_unchanged(runtime_stages, runtime_inventory, originals)
        if (canonical_json_bytes(plan) != plan_bytes or canonical_json_bytes(producer) != producer_bytes
                or _inventory(sdks) != sdk_inventory or _inventory(package_stage) != package_inventory
                or read_regular_file_bytes(package_receipt, reject_symlink_parents=True) != raw_package
                or read_regular_file_bytes(request, max_bytes=_LIMIT, reject_symlink_parents=True) != request_bytes
                or _request_inventory(request) != request_inventory
                or any(read_regular_file_bytes(path, max_bytes=128 * 1024 * 1024,
                       reject_symlink_parents=True) != raw for path, raw in tools.items())):
            raise ValueError("Native SDK validation originals or invocation policy changed")

    unchanged()
    for output in owned:
        product_reuse._prepare_destination(output, root).rmdir()
    destination = product_reuse._prepare_destination(destination, root)
    fields = {"codexAgent.product": "sdk", "codexAgent.component": component,
        "codexAgent.phase": "validation", "codexAgent.target": identity.target,
        "codexAgent.candidateCommit": producer["commit"], "codexAgent.candidateTree": tree,
        "codexAgent.nativeWrapperRuntimeStageRoot": str(runtime_stages),
        "codexAgent.nativeWrapperStagedSdkRoot": str(sdks),
        "codexAgent.sdkPackageStageRoot": str(package_stage),
        "codexAgent.sdkPackageReceipt": str(package_receipt),
        "codexAgent.sdkCompatibilityRequest": str(request),
        **{name: str(value) for name, value in optional.items() if value is not None}}
    command = product_reuse._runtime_worker_command(wrapper, fields, environment, build_directory=".")
    unchanged()
    if any(path.exists() or path.is_symlink() for path in owned):
        raise ValueError("Native SDK validation output appeared before execution")
    started, return_code, launch_error = time.monotonic_ns(), None, None
    try:
        with (destination / "gradle.log").open("xb") as log:
            return_code = subprocess.run(command, cwd=root, env=environment, stdout=log,
                                         stderr=subprocess.STDOUT, check=False).returncode
    except OSError as error:
        launch_error = str(error)
        raise
    finally:
        write_canonical_json(destination / "execution.json", {
            "schemaVersion": 1, "producer": dict(producer), "buildKey": plan["buildKey"],
            "command": command, "returnCode": return_code, "launchError": launch_error,
            "elapsedNs": time.monotonic_ns() - started})
        unchanged()
    if return_code != 0:
        raise ValueError(f"Native SDK validation failed with exit code {return_code}; see {destination / 'gradle.log'}")
    product_reuse.verify_output_manifest_identity(stage, "sdk", component, "validation", identity.target, sdk_version)
    inventory = _inventory(stage)
    unchanged()
    return {"stage": stage, "diagnostics": destination, "outputInventory": inventory}


def execute(plan, discovery, state, destination, *, component, target, expected_build_key,
            preparation_component, preparation_build_key, preparation_state,
            prepared_artifact_id, prepared_artifact_sha256, sdk_inputs_artifact_id,
            sdk_inputs_artifact_sha256, trusted_workflow_sha, keyring, keys_directory,
            repository_root, environ, token, tooling_evidence, tooling_public_key,
            java_executable, policy_revision, required_trust_domain, tooling_keyring=None,
            tooling_keys_directory=None, dotnet_executable=None, dart_executable=None,
            dart_package_config=None, preparation_phase="package", preparation_target="desktop",
            sdk_apple_validation_policy=None, sdk_facade_metadata_admission=None,
            sdk_android_metadata_admission=None):
    """Admit a validation and established evidence carrier, without restaging SDKs.

    Original preparation election is independently replayed. Only the existing
    full validation stager may admit the private candidate. Failed executions
    retain Gradle diagnostics, but do not promise publication of private captures.
    """
    if (component not in NATIVE_BINDINGS or preparation_component not in NATIVE_BINDINGS
            or target not in NATIVE_TARGETS or host_classifier() != target):
        raise ValueError("Native SDK validation requires a fixed component and its actual host")
    root, plan = Path(repository_root).resolve(strict=True), Path(plan).absolute()
    discovery, state, destination = product_reuse._product_materialization_paths(root, discovery, state, destination)
    _, preparation_state, _ = product_reuse._product_materialization_paths(root, discovery, preparation_state, destination)
    tooling = {"evidence": str(tooling_evidence), "publicKey": str(tooling_public_key),
        "javaExecutable": str(java_executable), "requiredTrustDomain": required_trust_domain,
        "keyring": str(tooling_keyring) if tooling_keyring is not None else None,
        "keysDirectory": str(tooling_keys_directory) if tooling_keys_directory is not None else None}
    apple = {} if sdk_apple_validation_policy is None else {"sdk_apple_validation_policy": sdk_apple_validation_policy}
    if sdk_facade_metadata_admission is not None:
        apple["sdk_facade_metadata_admission"] = sdk_facade_metadata_admission
    if sdk_android_metadata_admission is not None:
        apple["sdk_android_metadata_admission"] = sdk_android_metadata_admission
    protected = [plan, discovery, state, preparation_state, Path(keyring), Path(keys_directory),
        Path(tooling_evidence), Path(tooling_public_key), Path(java_executable),
        *(Path(value) for value in (tooling_keyring, tooling_keys_directory,
           dotnet_executable, dart_executable, dart_package_config) if value is not None)]
    _require_capability_output_separate(destination, protected)
    destination.relative_to(root)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Native SDK validation destination must not exist")
    trees = {path: _inventory(path, allow_empty=True) for path in
             {discovery, state, preparation_state, Path(tooling_evidence)}}
    files = {plan, Path(tooling_public_key), Path(java_executable),
             *(Path(value) for value in (dotnet_executable, dart_executable, dart_package_config) if value is not None)}
    for policy, keys in ((keyring, keys_directory), (tooling_keyring, tooling_keys_directory)):
        if (policy is None) != (keys is None):
            raise ValueError("Native SDK caller public policy requires paired keys")
        if policy is not None:
            ring = load_keyring(Path(policy), Path(keys))
            files.add(Path(policy))
            files.update(public_key_path(Path(keys), record["keyId"]) for record in
                         ([ring["activeKey"]] if ring["activeKey"] else []) + ring["retiredKeys"])
    before_files = {path: read_regular_file_bytes(path, max_bytes=128 * 1024 * 1024,
                       reject_symlink_parents=True) for path in files}

    def controls_unchanged():
        if (any(_inventory(path, allow_empty=True) != value for path, value in trees.items())
                or any(read_regular_file_bytes(path, max_bytes=128 * 1024 * 1024,
                       reject_symlink_parents=True) != raw for path, raw in before_files.items())):
            raise ValueError("Native SDK original election or caller policy changed")

    instance = PhaseInstanceId("sdk", component, "validation", target)
    identity = {"product": "sdk", "component": component, "phase": "validation", "target": target}
    prep_identity = {"product": "sdk", "component": preparation_component,
                     "phase": preparation_phase, "target": preparation_target}
    prep_instance = product_reuse._identity(prep_identity)
    if (preparation_phase not in {"package", "validation", "metadata"}
            or not product_reuse._sdk_family_worker_instance(prep_instance, "native-" + preparation_phase)):
        raise ValueError("Native validation requires an exact preparation consumer anchor")
    with tempfile.TemporaryDirectory(prefix="sdk-native-validation-") as temporary:
        private = Path(temporary).resolve()
        publication, capture = private / "publication", private / "prepared-upload"
        candidate, evidence = publication / "shard", publication / "sdk-validation-evidence"
        with sdk_workflow.verified_inputs(plan, discovery, state,
                artifact_id=sdk_inputs_artifact_id, artifact_sha256=sdk_inputs_artifact_sha256,
                trusted_workflow_sha=trusted_workflow_sha, keyring=keyring, keys_directory=keys_directory,
                repository_root=root, environ=environ, token=token, sdk_validation_tooling=tooling, **apple) as inputs:
            controls_unchanged()
            selection = inputs["selection"]
            sdk_inventory = _inventory(inputs["sdk"]["directory"], allow_empty=True)
            if identity not in selection["consumers"]:
                raise ValueError("Native SDK validation is not selected")
            inspected = product_reuse.inspect_products(plan, discovery, preparation_state,
                repository_root=root, environ=environ, sdk_validation_tooling=tooling, **apple)
            elected = [row for row in inspected["readyPlans"] if all(row.get(name) == value for name, value in prep_identity.items())]
            if len(elected) != 1 or set(elected[0]) != PHASE_PLAN_KEYS or elected[0]["buildKey"] != preparation_build_key:
                raise ValueError("Original native preparation consumer is not uniquely ready with its elected key")
            prep_plan, prep_bytes = elected[0], canonical_json_bytes(elected[0])
            controls_unchanged()
            transport = product_reuse.capture_sdk_native_prepared_upload(plan, capture,
                expected_phase_plan=prep_plan, artifact_id=prepared_artifact_id,
                artifact_sha256=prepared_artifact_sha256, trusted_workflow_sha=trusted_workflow_sha,
                repository_root=root, environ=environ, token=token)
            capture_inventory = _inventory(capture, allow_empty=True)
            prepared = destination / "inputs"
            ready = product_reuse.materialize_product_predecessors(plan, discovery, state, instance, prepared,
                expected_build_key=expected_build_key, repository_root=root, environ=environ,
                sdk_validation_tooling=tooling, **apple)
            prepared_inventory = _inventory(prepared, allow_empty=True)
            producer = product_reuse.validate_producer(product_reuse._canonical_control(prepared / "producer.json", "Native validation producer"))
            ready_bytes, producer_bytes = canonical_json_bytes(ready), canonical_json_bytes(producer)
            if transport["captureProducer"] != producer:
                raise ValueError("Native preparation upload differs from the elected validation producer")
            contract = product_reuse.validate_phase_receipt(product_reuse._canonical_control(
                prepared / "contract-contract-metadata-common/phase-receipt.json", "Current Contract metadata"))
            bundles = [row for row in contract["outputs"] if row["kind"] == "contract-bundle"]
            if (tuple(contract[name] for name in ("product", "component", "phase", "target")) !=
                    ("contract", "contract", "metadata", "common") or len(bundles) != 1
                    or bundles[0]["sha256"] != selection["contractPayloadSha256"]):
                raise ValueError("Current Contract differs from authenticated native SDK inputs")

            def original(product, name, phase, original_target):
                original_identity = PhaseInstanceId(product, name, phase, original_target)
                if (product != "runtime" or name not in NATIVE_TARGETS or original_target != name
                        or phase not in {"package", "validation"}):
                    raise ValueError("Unexpected native validation Runtime predecessor")
                directory = prepared / "-".join((product, name, phase, original_target))
                receipt_path = directory / PHASE_RECEIPT_NAME
                raw = read_regular_file_bytes(receipt_path, reject_symlink_parents=True)
                receipt = product_reuse.validate_phase_receipt(load_canonical_json_bytes(raw))
                if (raw != inputs["runtime"]["receiptBytes"].get(original_identity)
                        or tuple(receipt[field] for field in ("product", "component", "phase", "target")) !=
                        (product, name, phase, original_target)):
                    raise ValueError("Native validation Runtime receipt differs from its verified original")
                manifest = product_reuse.verify_output_manifest_identity(directory / "stage", product, name,
                    phase, original_target, receipt["productVersion"])
                if manifest["outputs"] != receipt["outputs"]:
                    raise ValueError("Native validation Runtime stage differs from its original receipt")
                return {"stage": directory / "stage", "receiptPath": receipt_path, "receipt": receipt}

            runtime_stages = destination / "runtime-stages"
            for name in NATIVE_TARGETS:
                for phase in ("package", "validation"):
                    snapshot_regular_tree(original("runtime", name, phase, name)["stage"], runtime_stages / name / phase)
            runtime_inventory = _inventory(runtime_stages)
            package_directory = prepared / f"sdk-{component}-package-desktop"
            package = {"stage": package_directory / "stage", "receiptPath": package_directory / PHASE_RECEIPT_NAME}
            package_raw = read_regular_file_bytes(package["receiptPath"], reject_symlink_parents=True)
            package["receipt"] = product_reuse.validate_phase_receipt(load_canonical_json_bytes(package_raw))
            request = inputs["sdk"]["directory"] / REQUEST_NAME
            sdks = capture / "original/staged-sdks"

            def unchanged():
                controls_unchanged()
                if (_inventory(capture, allow_empty=True) != capture_inventory
                        or _inventory(prepared, allow_empty=True) != prepared_inventory
                        or _inventory(runtime_stages) != runtime_inventory
                        or canonical_json_bytes(prep_plan) != prep_bytes
                        or canonical_json_bytes(ready) != ready_bytes
                        or canonical_json_bytes(producer) != producer_bytes):
                    raise ValueError("Native validation original inputs or preparation capture changed")

            unchanged()
            receipt, raw = verify_sdk_package_inputs(root, package["stage"], package["receiptPath"], request,
                runtime_stage_root=runtime_stages, staged_sdks=sdks)
            if receipt != package["receipt"] or raw != package_raw:
                raise ValueError("Native validation package gate returned another original receipt")
            unchanged()
            result = _execute_validation(ready, producer=producer, sdk_version=selection["sdkVersion"],
                repository_root=root, destination=destination / "worker", runtime_stages=runtime_stages,
                staged_sdks=sdks, compatibility_request=request, package=package, predecessor=original,
                environ=environ, dotnet_executable=dotnet_executable, dart_executable=dart_executable,
                dart_package_config=dart_package_config,
                protected_inputs=[*protected, prepared, capture, inputs["sdk"]["directory"]])
            unchanged()
            finalized = product_reuse.finalize_phase_object(stage_root=result["stage"], phase_plan=ready,
                producer=producer, product_version=selection["sdkVersion"],
                trust_domain="development" if producer["event"] == "pull_request" else "release", destination=candidate)
            candidate_inventory = _inventory(candidate)
            # Existing decoder accepts relative paths only. Privately copy the
            # verified complete SDK directory, retaining its request path layout.
            source = private / "evidence-source"
            for name, path in {"packageStage": package["stage"], "runtimeStages": runtime_stages,
                    "stagedSdks": sdks, "validationStage": result["stage"], "inputs": inputs["sdk"]["directory"]}.items():
                snapshot_regular_tree(path, source / name, allow_empty=name == "inputs")
            if (_inventory(source / "inputs", allow_empty=True) != sdk_inventory
                    or _inventory(inputs["sdk"]["directory"], allow_empty=True) != sdk_inventory):
                raise ValueError("Native validation SDK input capture differs from its verified originals")
            (source / "packageReceipt").write_bytes(package_raw)
            candidate_raw = read_regular_file_bytes(candidate / PHASE_RECEIPT_NAME, reject_symlink_parents=True)
            (source / "validationReceipt").write_bytes(candidate_raw)
            record = {"receiptSha256": sha256_bytes(candidate_raw), "component": component, "target": target,
                **{name: name for name in ("packageStage", "runtimeStages", "stagedSdks", "validationStage", "packageReceipt", "validationReceipt")},
                "compatibilityRequest": f"inputs/{REQUEST_NAME}"}
            source_inventory = _inventory(source, allow_empty=True)
            stage_sdk_validation_evidence([record], source, evidence, repository=root,
                policy_revision=policy_revision, tooling=tooling)
            evidence_inventory = _inventory(evidence, allow_empty=True)

            def outputs_unchanged():
                product_reuse._runtime_worker_checkout(root, producer)
                if (_inventory(result["stage"]) != result["outputInventory"]
                        or _inventory(source, allow_empty=True) != source_inventory
                        or _inventory(candidate) != candidate_inventory
                        or _inventory(evidence, allow_empty=True) != evidence_inventory
                        or verify_phase_shard(candidate, instance) != finalized):
                    raise ValueError("Native validation outputs changed after full admission")

            unchanged()
            outputs_unchanged()
        unchanged()
        outputs_unchanged()
        snapshot_regular_tree(capture, publication / "prepared-upload", allow_empty=True)
        if _inventory(publication / "prepared-upload", allow_empty=True) != capture_inventory:
            raise ValueError("Native validation retained upload differs from its original")
        unchanged()
        outputs_unchanged()
        # External evidence alone is not success. The standard root shard is
        # published last, after all source contexts and retained-byte checks.
        publish_regular_tree(evidence, destination / "sdk-validation-evidence", allow_empty=True)
        publish_regular_tree(publication / "prepared-upload", destination / "prepared-upload", allow_empty=True)
        unchanged()
        outputs_unchanged()
        if (_inventory(destination / "sdk-validation-evidence", allow_empty=True) != evidence_inventory
                or _inventory(destination / "prepared-upload", allow_empty=True) != capture_inventory):
            raise ValueError("Native validation retained evidence changed before shard publication")
        _require_capability_output_separate(destination / "shard", protected)
        publish_regular_tree(candidate, destination / "shard")
    return verify_phase_shard(destination / "shard", instance)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("plan", "destination", "keyring", "keys-directory", "repository-root",
                 "tooling-evidence", "tooling-public-key", "java-executable"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    for flag, name in (("discovery-root", "discovery"), ("state-root", "state"),
                       ("preparation-state-root", "preparation_state")):
        parser.add_argument(f"--{flag}", dest=name, type=Path, required=True)
    for name in ("component", "preparation-component"):
        parser.add_argument(f"--{name}", choices=NATIVE_BINDINGS, required=True)
    parser.add_argument("--target", choices=NATIVE_TARGETS, required=True)
    parser.add_argument("--preparation-phase", choices=("package", "validation", "metadata"), default="package")
    parser.add_argument("--preparation-target", default="desktop")
    parser.add_argument("--required-trust-domain", choices=("development", "release"), required=True)
    for name in ("expected-build-key", "preparation-build-key", "prepared-artifact-sha256",
                 "sdk-inputs-artifact-sha256", "trusted-workflow-sha", "policy-revision"):
        parser.add_argument(f"--{name}", required=True)
    for name in ("prepared-artifact-id", "sdk-inputs-artifact-id"):
        parser.add_argument(f"--{name}", type=int, required=True)
    for name in ("tooling-keyring", "tooling-keys-directory", "dotnet-executable",
                 "dart-executable", "dart-package-config"):
        parser.add_argument(f"--{name}", type=Path)
    parser.add_argument("--sdk-apple-validation-policy", type=Path)
    arguments = vars(parser.parse_args(argv))
    try:
        apple_policy = arguments.pop("sdk_apple_validation_policy")
        if apple_policy is not None:
            arguments["sdk_apple_validation_policy"] = product_reuse._canonical_control(
                apple_policy, "Caller Apple validation policy")
        execute(**arguments, environ=os.environ, token=os.environ.get("GITHUB_TOKEN", ""))
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
