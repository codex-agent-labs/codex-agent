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
from sdk_phase import NATIVE_RUNTIME_PREDECESSORS
from sdk_metadata_policy import add_metadata_admission_arguments, metadata_admission_options
from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, publish_regular_tree,
    read_regular_file_bytes, regular_file_inventory, snapshot_regular_tree,
)
from products.registry import NATIVE_BINDINGS, NATIVE_TARGETS, PhaseInstanceId
from products.restore import PHASE_PLAN_KEYS, PHASE_RECEIPT_NAME, verify_phase_shard
from products.sdk_inputs import REQUEST_NAME
from products.sdk_package import _require_capability_output_separate
from products.sdk_validation_inputs import collection_admission_scope


def completed_validation_recovery(completed, request, tooling, context):
    """Recover full host gates, not projections asserted by a retained report.

    One private verification session owns shared K/R, package and host categories.
    Only consumed, independently qualified objects and caller-pinned sidecars are
    fetched; newly collected hosts use their ordinary full admission instead.
    Original receipts are never rewritten; nothing here is persisted as
    authentication authority or exported into a product payload.
    """
    from reuse_qualification import CompletedFrozenReuse
    from products.inventory import git_regular_blob_bytes, load_json_bytes, sha256_bytes
    from products.plan import sdk_validation_dependencies
    from products.restore import _VERIFICATION_SESSION, restore_object, memoized_file_inventory
    from products.sdk_native import SDK_ROOT_PATH, stage_native_sdk_inputs
    from products.sdk_compatibility import load_sdk_compatibility_request
    from products.sdk_validation_inputs import decode_sdk_validation_records, sdk_validation_provider
    from sdk_native_validation_workflow import capture_runtime_authorization
    from runtime_reference_transport import count, measured

    if completed is None or tooling is None or context is None or request.get("sdkRuntimeSource") is not None:
        return None
    if type(completed) is not CompletedFrozenReuse:
        raise TypeError("Native SDK recovery requires concrete completed authority")
    session = _VERIFICATION_SESSION.get()
    if session is None:
        raise ValueError("Native SDK recovery requires a private verification lifetime")
    environment = context["environ"]
    source_path = environment.get("CODEX_AGENT_RETAINED_SDK_INPUTS_SOURCE")
    authorization_raw = environment.get("CODEX_AGENT_SDK_RUNTIME_VALIDATION_AUTHORIZATION")
    if not source_path or not authorization_raw:
        return None  # Ordinary transported host evidence remains usable.
    source_raw = read_regular_file_bytes(Path(source_path), max_bytes=16 * 1024**2,
                                         reject_symlink_parents=True)
    binding_source = load_canonical_json_bytes(source_raw)
    authorization = load_json_bytes(authorization_raw.encode())
    root = Path(context["repository_root"]).resolve(strict=True)
    plan = product_reuse._validate_plan(context["plan_path"], root,
        expected_revision=request["repositoryRevision"])
    producer = product_reuse._consumer(plan, environment)["producer"]
    completed.check_request(request)
    completed.check_consumer({"kind": "ci", "producer": producer})
    _, phases = completed._values()
    sdk = completed.sdk_original()
    if sdk is None or binding_source != sdk["spec"]["sdkInputs"]["source"]:
        raise ValueError("Native SDK recovery input source differs from caller policy")
    binding = {"source": binding_source, "runtimeSource": sdk["spec"]["sdkInputs"]["runtimeSource"]}
    # sdk_receipts below additionally joins this signed source to the exact
    # current Contract and Runtime aggregate admitted by this capability.
    policy = product_reuse.require_exact_keys(dict(tooling),
        {"evidence", "publicKey", "javaExecutable", "requiredTrustDomain", "keyring", "keysDirectory"},
        "Native SDK recovery tooling")
    arguments = {name: Path(policy[field]) if policy[field] is not None else None for field, name in (
        ("evidence", "tooling_evidence"), ("publicKey", "tooling_public_key"),
        ("javaExecutable", "java_executable"), ("keyring", "tooling_keyring"),
        ("keysDirectory", "tooling_keys_directory"))}

    def authority():
        files = {name: (None if value is None else
            memoized_file_inventory(value, allow_empty=True) if name in {"tooling_evidence", "tooling_keys_directory"}
            else sha256_bytes(read_regular_file_bytes(value, reject_symlink_parents=True)))
            for name, value in arguments.items()}
        return sha256_bytes(canonical_json_bytes(dict(versions=request["versions"], revision=request["repositoryRevision"],
            plan=plan, producer=producer,
            workflow=context["trusted_workflow_sha"], tooling=policy, files=files,
            hostEvidence=request.get("sdkValidationEvidence", []),
            source=read_regular_file_bytes(Path(source_path), reject_symlink_parents=True).decode(),
            authorization=environment.get("CODEX_AGENT_SDK_RUNTIME_VALIDATION_AUTHORIZATION"))))

    original_authority = authority()
    pool = session.setdefault("completedNativeSdkRecovery", {})
    key = completed, original_authority
    if key in pool:
        count("nativeSdkRecoveryReuses")
        return pool[key]
    private = session["root"] / ("native-sdk-recovery-" + str(len(pool)))
    private.mkdir()
    stages, authorizations, captured_authorizations = {}, {}, {}
    common = {}
    ordinary_records = request.get("sdkValidationEvidence", [])
    ordinary = decode_sdk_validation_records(root, ordinary_records)

    def check():
        if _VERIFICATION_SESSION.get() is not session or authority() != original_authority:
            raise ValueError("Native SDK recovery outlived or changed its caller authority")

    def original(instance):
        record = phases[instance]
        envelope = completed.envelope(record)
        if instance not in stages:
            directory = private / "originals" / "-".join((instance.product, instance.component, instance.phase, instance.target))
            directory.mkdir(parents=True)
            obj = directory / "object.zip"
            completed.capture_object(record, obj, plan=plan, producer=producer,
                trusted_workflow_sha=context["trusted_workflow_sha"], token=context["token"])
            stage = (private / "runtime" / instance.target / instance.phase
                     if instance.product == "runtime" else directory / "stage")
            restored = restore_object(obj, stage, build_key=record["buildKey"],
                receipt_sha256=record["receiptSha256"], object_sha256=record["objectSha256"])
            if restored["receiptBytes"] != envelope["receiptBytes"]:
                raise ValueError("Recovered SDK input differs from its qualified receipt")
            if instance.product == "sdk":
                from sdk_handoff import _ensure_observed_sdk_commit
                _ensure_observed_sdk_commit(root, envelope["receipt"]["producer"], context["token"])
            receipt = directory / "phase-receipt.json"
            receipt.write_bytes(envelope["receiptBytes"])
            stages[instance] = (dict(stage=stage, receiptPath=receipt, receipt=envelope["receipt"]),
                                memoized_file_inventory(stage))
            count("nativeSdkRecoveryObjects")
        value, inventory = stages[instance]
        if (memoized_file_inventory(value["stage"]) != inventory or
                read_regular_file_bytes(value["receiptPath"], reject_symlink_parents=True) != envelope["receiptBytes"]):
            raise ValueError("Recovered SDK input changed during its private lifetime")
        return value

    def common_inputs():
        if common:
            return common
        capture = private / "common"
        completed.capture_sdk_input_members(binding, capture / "original", context["token"])
        trust = product_reuse._release_trust(root, request["repositoryRevision"], private / "policy")
        if trust is None:
            raise ValueError("Native SDK recovery requires current Git public-key policy")
        sdk_root = capture / "original/sdk-inputs"
        contract_path = load_sdk_compatibility_request(sdk_root / REQUEST_NAME)["contract_metadata_receipt"]
        contract_path.resolve(strict=True).relative_to(sdk_root)
        contract = completed.envelope(phases[PhaseInstanceId("contract", "contract", "metadata", "common")],
            read_regular_file_bytes(contract_path, reject_symlink_parents=True))
        payload, = [row for row in contract["receipt"]["outputs"] if row["kind"] == "contract-bundle"]
        with sdk_workflow._completed_sdk_inputs(capture, completed_frozen=completed,
                keyring=trust.keyring, keys_directory=trust.keys, selection_repository_root=root,
                selection_revision=request["repositoryRevision"], expected_contract_payload_sha256=payload["sha256"]) as inputs:
            for target in NATIVE_TARGETS:
                for phase in ("package", "validation"):
                    identity = PhaseInstanceId("runtime", target, phase, target)
                    value = original(identity)
                    if read_regular_file_bytes(value["receiptPath"]) != inputs["runtime"]["receiptBytes"][identity]:
                        raise ValueError("Native SDK recovery Runtime differs from signed SDK inputs")
            request_path = inputs["sdk"]["directory"] / REQUEST_NAME
            compatibility = inputs["sdk"]["compatibility"]
            stage_native_sdk_inputs(private / "staged-sdks", request_path, private / "runtime",
                git_regular_blob_bytes(root, request["repositoryRevision"], SDK_ROOT_PATH, max_bytes=4096),
                identity=dict(libraryVersion=original(PhaseInstanceId("runtime", "macos-arm64", "package", "macos-arm64"))["receipt"]["productVersion"],
                    runtimeProductVersion=compatibility["runtime"]["defaultRuntimeVersion"], sdkVersion=compatibility["sdkVersion"],
                    producerCommit=producer["commit"], producerTree=producer["tree"]),
                expected_compatibility=canonical_json_bytes(compatibility))
            common.update(compatibility_request=request_path, runtime_stages=private / "runtime", staged_sdks=private / "staged-sdks")
        count("nativeSdkRecoveryCommonCaptures")
        return common

    @measured
    def verify_completed_sdk_hosts(instance, envelopes, package):
        check()
        dependencies = sdk_validation_dependencies(instance)
        package_id = PhaseInstanceId("sdk", instance.component, "package", "desktop")
        required = (package_id,
            *((PhaseInstanceId("sdk", "csharp", "binary", "desktop"),) if instance.component == "csharp" else ()))
        if not dependencies or any(identity not in phases for identity in required):
            return None
        if len(envelopes) != len(dependencies):
            raise ValueError("Native SDK recovery requires exactly five selected hosts")
        for identity, envelope in zip((*dependencies, package_id), (*envelopes, package), strict=True):
            if identity not in phases:
                if envelope["receiptSha256"] not in ordinary:
                    return None
            elif completed.envelope(phases[identity], envelope["receiptBytes"]) != envelope:
                raise ValueError("Native SDK recovery differs from the selected original")
        shared = common_inputs()
        package_value = original(package_id)
        binary = original(required[-1]) if instance.component == "csharp" else None
        records = []
        for identity, envelope in zip(dependencies, envelopes, strict=True):
            if envelope["receiptSha256"] in ordinary:
                authorizations[identity.target] = ordinary[envelope["receiptSha256"]]["runtimeAuthorization"]
                continue
            validation = original(identity)
            if identity.target not in captured_authorizations:
                directory = private / "authorizations" / identity.target
                capture_runtime_authorization(authorization, identity.target, directory, token=context["token"])
                captured_authorizations[identity.target] = directory
            authorizations[identity.target] = captured_authorizations[identity.target]
            paths = dict(packageStage=package_value["stage"], packageReceipt=package_value["receiptPath"],
                compatibilityRequest=shared["compatibility_request"], runtimeStages=shared["runtime_stages"],
                stagedSdks=shared["staged_sdks"], validationStage=validation["stage"],
                validationReceipt=validation["receiptPath"], runtimeAuthorization=authorizations[identity.target])
            if binary is not None:
                paths.update(binaryStage=binary["stage"], binaryReceipt=binary["receiptPath"])
            records.append(dict(receiptSha256=envelope["receiptSha256"], component=instance.component,
                target=identity.target, **{name: path.relative_to(private).as_posix() for name, path in paths.items()}))
        records.sort(key=lambda record: record["receiptSha256"])
        provider = sdk_validation_provider(private, records, repository=root,
            policy_revision=request["repositoryRevision"], tooling=policy)
        # Recovery categories may outlive a nested admission scope. Bind this
        # provider to the current scope, never a previous scope's expired cache.
        ordinary_provider = sdk_validation_provider(root, ordinary_records, repository=root,
            policy_revision=request["repositoryRevision"], tooling=policy)
        result = tuple((ordinary_provider if envelope["receiptSha256"] in ordinary else provider)(
                           {**envelope["receipt"], "receiptSha256": envelope["receiptSha256"]})
                       for envelope in envelopes)
        for proof, envelope in zip(result, envelopes, strict=True):
            proof.output_inventory(envelope["receiptSha256"], envelope["receipt"]["outputs"], identity=envelope["receipt"])
            proof.receipt_value(envelope["receipt"], package["receipt"])
        check()
        return tuple(result)

    result = dict(verify=verify_completed_sdk_hosts, authorizations=authorizations)
    pool[key] = result
    return result


@collection_admission_scope
def execute(plan, discovery, state, destination, *, component, expected_build_key,
            preparation_component, preparation_build_key, preparation_state,
            prepared_artifact_id, prepared_artifact_sha256,
            sdk_inputs_artifact_id, sdk_inputs_artifact_sha256, trusted_workflow_sha,
            keyring, keys_directory, repository_root, environ, token,
            tooling_evidence, tooling_public_key, java_executable,
            required_trust_domain, tooling_keyring=None, tooling_keys_directory=None,
            preparation_phase="package", preparation_target="desktop", sdk_apple_validation_policy=None,
            sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None, retained_sdk_inputs_source=None, completed_frozen=None):
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

    apple = {} if sdk_apple_validation_policy is None else {"sdk_apple_validation_policy": sdk_apple_validation_policy}
    if sdk_facade_metadata_admission is not None:
        apple["sdk_facade_metadata_admission"] = sdk_facade_metadata_admission
    if sdk_android_metadata_admission is not None:
        apple["sdk_android_metadata_admission"] = sdk_android_metadata_admission
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
                requested_scope=(instance,),
                artifact_id=sdk_inputs_artifact_id, artifact_sha256=sdk_inputs_artifact_sha256,
                trusted_workflow_sha=trusted_workflow_sha, keyring=keyring, keys_directory=keys_directory,
                repository_root=root, environ=environ, token=token, sdk_validation_tooling=tooling, **apple,
                **({"retained_sdk_inputs_source": retained_sdk_inputs_source} if retained_sdk_inputs_source is not None else {}),
                **({"completed_frozen": completed_frozen} if completed_frozen is not None else {})) as inputs:
            controls_unchanged()
            selection = inputs["selection"]
            if identity not in selection["consumers"]:
                raise ValueError("Native SDK metadata is not selected")
            inspected = product_reuse.inspect_products(plan, discovery, preparation_state,
                requested_scope=(preparation_instance,),
                repository_root=root, environ=environ, sdk_validation_tooling=tooling,
                sdk_original_workflow_sha=trusted_workflow_sha, **apple,
                **({"completed_frozen": completed_frozen} if completed_frozen is not None else {}))
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
                materialized_scope=NATIVE_RUNTIME_PREDECESSORS,
                sdk_validation_tooling=tooling, sdk_original_workflow_sha=trusted_workflow_sha, **apple,
                **({"completed_frozen": completed_frozen} if completed_frozen is not None else {}))
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
                sdk_validation_tooling=tooling, repository_root=root, environ=environ,
                sdk_original_workflow_sha=trusted_workflow_sha, **apple,
                **({"completed_frozen": completed_frozen} if completed_frozen is not None else {}))
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
    from reuse_qualification import add_completed_frozen_argument, completed_frozen_options
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
    parser.add_argument("--sdk-apple-validation-policy", type=Path)
    add_metadata_admission_arguments(parser)
    add_completed_frozen_argument(parser)
    parser.add_argument("--retained-sdk-inputs-source", type=Path, default=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    arguments = {name: value for name, value in vars(args).items()
                 if name not in {"sdk_facade_metadata_policy", "sdk_android_metadata_policy"}}
    if (arguments["tooling_keyring"] is None) != (arguments["tooling_keys_directory"] is None):
        parser.error("Native metadata tooling keyring and keys directory must be supplied together")
    try:
        if "retained_sdk_inputs_source" in arguments:
            arguments["retained_sdk_inputs_source"] = product_reuse._canonical_control(
                arguments["retained_sdk_inputs_source"], "Caller retained SDK input source")
        apple_policy = arguments.pop("sdk_apple_validation_policy")
        if apple_policy is not None:
            arguments["sdk_apple_validation_policy"] = product_reuse._canonical_control(
                apple_policy, "Caller Apple validation policy")
        with metadata_admission_options(args) as admissions, completed_frozen_options(arguments) as semantic:
            execute(**arguments, environ=os.environ, token=os.environ.get("GITHUB_TOKEN", ""), **admissions, **semantic)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
