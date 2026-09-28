"""Execute the C# SDK binary from elected Contract and S858 originals."""

import argparse
from contextlib import contextmanager
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
    canonical_json_bytes, git_regular_blob_bytes, load_canonical_json_bytes, publish_regular_tree,
    read_regular_file_bytes, regular_file_inventory, sha256_file, snapshot_regular_tree,
)
from products.receipt import validate_phase_receipt, verify_output_manifest_identity
from products.registry import PhaseInstanceId
from products.restore import PHASE_PLAN_KEYS, PHASE_RECEIPT_NAME, restore_object, verify_phase_shard
from products.sdk_dotnet_toolchain import load_sdk_dotnet_profile_bytes
from products.sdk_inputs import COMPATIBILITY_NAME, REQUEST_NAME
from products.sdk_native_metadata import _inventory
from products.sdk_package import _require_capability_output_separate
from products.signing_isolation import require_no_signing_secret
from sdk_csharp_binary_phase import execute as execute_binary
from products.sdk_csharp_binary import verify_csharp_binary_stage
from products.plan import _contract_projection_from_request_components
from products.registry import phase_instance_dependencies
from products.reuse import _plan
from products.selection import phase_git_inventory
from sdk_metadata_policy import add_metadata_admission_arguments, metadata_admission_options


_INSTANCE = PhaseInstanceId("sdk", "csharp", "binary", "desktop")
_PACKAGE = {"product": "sdk", "component": "csharp", "phase": "package", "target": "desktop"}
_LIMIT = 16 * 1024 * 1024


def lookup_only_plan(plan, discovery, state, *, repository_root, environ,
                     sdk_validation_tooling=None, sdk_apple_validation_policy=None,
                     sdk_original_workflow_sha=None, sdk_facade_metadata_admission=None,
                     sdk_android_metadata_admission=None):
    """Derive a C# binary key from authenticated originals, without selecting a build."""
    root = Path(repository_root).resolve(strict=True)
    released_runtime = {}

    def capture_released_default(selected):
        if released_runtime:
            raise ValueError("Lookup-only C# Runtime default was elected twice")
        handoff = selected["handoff"]
        for identity, raw in handoff["receiptBytes"].items():
            if identity.product == "runtime":
                released_runtime[identity] = validate_phase_receipt(load_canonical_json_bytes(raw))

    verified = product_reuse._verified_product_state(
        Path(plan), Path(discovery), Path(state), root, environ, sdk_validation_tooling,
        sdk_runtime_consumer=capture_released_default,
        sdk_apple_validation_policy=sdk_apple_validation_policy,
        sdk_original_workflow_sha=sdk_original_workflow_sha,
        sdk_facade_metadata_admission=sdk_facade_metadata_admission,
        sdk_android_metadata_admission=sdk_android_metadata_admission)
    if _INSTANCE in verified.closure:
        raise ValueError("C# binary is already in the selected product closure")
    predecessors = phase_instance_dependencies(_INSTANCE)
    external = verified.rebased_request.get("sdkRuntimeSource") == "released-default"
    if any(instance not in (released_runtime if external and instance.product == "runtime" else verified.sources)
           for instance in predecessors):
        raise ValueError("Lookup-only C# binary lacks an authenticated original predecessor")
    revision = verified.plan["validationCommit"]
    versions = product_reuse._versions(root, revision)
    evidence = verified.rebased_request["contractEvidence"]
    if evidence is None or evidence["expectedTrustDomain"] != "release":
        raise ValueError("Lookup-only C# binary requires release-attested Contract evidence")
    projection = _contract_projection_from_request_components(versions, evidence, ("common",))
    receipts = []
    for instance in predecessors:
        if external and instance.product == "runtime":
            receipt = released_runtime[instance]
            if product_reuse._identity(receipt) != instance:
                raise ValueError("Lookup-only C# Runtime default identity differs from its original")
            receipts.append(receipt)
            continue
        record = verified.prior_by_instance[instance]
        original = product_reuse.verify_object(verified.sources[instance],
            build_key=record["buildKey"], receipt_sha256=record["receiptSha256"],
            object_sha256=record["objectSha256"])
        if product_reuse._identity(original["receipt"]) != instance:
            raise ValueError("Lookup-only C# predecessor identity differs from its original")
        receipts.append(original["receipt"])
    authorities, unavailable = product_reuse._authorities(root, revision, (_INSTANCE,))
    if authorities is None:
        raise ValueError(unavailable or "C# binary toolchain authority is unavailable")
    authority = authorities[0]
    return _plan(_INSTANCE, {_INSTANCE: {
        "inventory": phase_git_inventory(root, revision, _INSTANCE),
        "versions": versions,
        "toolchain_profile_digest": authority["toolchainProfileDigest"],
        "flags_digest": authority["flagsDigest"],
        "output_schema_version": authority["outputSchemaVersion"],
        "contract_projection": projection,
    }}, receipts, root, revision)


@contextmanager
def verified_lookup_only_same_pr_original(plan, discovery, state, *,
        sdk_inputs_artifact_id, sdk_inputs_artifact_sha256, trusted_workflow_sha,
        keyring, keys_directory, repository_root, environ, token,
        sdk_validation_tooling=None, sdk_apple_validation_policy=None,
        sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None):
    """Expose an unselected C# original only during authenticated capture."""
    require_no_signing_secret(environ)
    root = Path(repository_root).resolve(strict=True)
    plan, discovery, state = Path(plan), Path(discovery), Path(state)
    control_plan_bytes = read_regular_file_bytes(plan, max_bytes=_LIMIT, reject_symlink_parents=True)
    controls = {path: regular_file_inventory(path, allow_empty=True)
        for path in (discovery, state)}

    def controls_unchanged():
        if (read_regular_file_bytes(plan, max_bytes=_LIMIT, reject_symlink_parents=True) != control_plan_bytes
                or any(regular_file_inventory(path, allow_empty=True) != inventory
                       for path, inventory in controls.items())):
            raise ValueError("Lookup-only C# plan or state controls changed")

    tooling = {"sdk_validation_tooling": sdk_validation_tooling,
        "sdk_apple_validation_policy": sdk_apple_validation_policy,
        "sdk_facade_metadata_admission": sdk_facade_metadata_admission,
        "sdk_android_metadata_admission": sdk_android_metadata_admission}
    elected = lookup_only_plan(plan, discovery, state, repository_root=root, environ=environ,
        sdk_original_workflow_sha=trusted_workflow_sha, **tooling)
    controls_unchanged()
    with tempfile.TemporaryDirectory(prefix="sdk-csharp-lookup-", dir=root) as temporary:
        private = Path(temporary).resolve()
        stage = private / "stage"
        captured = []
        with sdk_workflow.verified_inputs(plan, discovery, state,
                artifact_id=sdk_inputs_artifact_id, artifact_sha256=sdk_inputs_artifact_sha256,
                trusted_workflow_sha=trusted_workflow_sha, keyring=keyring,
                keys_directory=keys_directory, repository_root=root, environ=environ,
                token=token, **tooling) as inputs:
            def capture(session):
                if captured:
                    raise ValueError("Lookup-only C# original was captured twice")
                for source in ("promoted-main", "same-pr"):
                    found = session.capture(source, elected, stage)
                    if found.envelope is not None:
                        if found.transport_source is None:
                            raise ValueError("Authenticated C# binary original lacks transport provenance")
                        captured.append(found)
                        return
                raise ValueError("Authenticated C# binary original is unavailable")

            verified = product_reuse._verified_product_state(
                Path(plan), Path(discovery), Path(state), root, environ,
                sdk_validation_tooling, authenticated_lookup_consumer=capture,
                sdk_apple_validation_policy=sdk_apple_validation_policy,
                sdk_original_workflow_sha=trusted_workflow_sha,
                sdk_facade_metadata_admission=sdk_facade_metadata_admission,
                sdk_android_metadata_admission=sdk_android_metadata_admission)
            controls_unchanged()
            if len(captured) != 1:
                raise ValueError("Lookup-only C# original was not replay-authenticated")
            found = captured[0]
            receipt = found.envelope["receipt"]
            producer = receipt["producer"]
            source = found.transport_source["kind"]
            if (receipt["buildKey"] != elected["buildKey"]
                    or source not in {"promoted-main", "same-pr"}
                    or producer["repository"] != verified.producer["repository"]
                    or (source == "same-pr" and (producer["event"] != "pull_request"
                        or producer["pullRequest"] != verified.producer["pullRequest"]))
                    or (source == "promoted-main" and producer["event"] not in
                        {"pull_request", "push"})
                    or receipt["productVersion"] != inputs["selection"]["sdkVersion"]):
                raise ValueError("Lookup-only C# original differs from its authenticated source or SDK version")
            root_key = private / "sdk-runtime-root.pub"
            root_key.write_bytes(git_regular_blob_bytes(root, verified.plan["validationCommit"],
                "gradle/release/keys/sdk-runtime-root.pub", max_bytes=65_536))
            verify_csharp_binary_stage(stage, receipt,
                inputs["sdk"]["directory"] / COMPATIBILITY_NAME, root_key)
            before = regular_file_inventory(stage)
            receipt_bytes = found.envelope["receiptBytes"]
            elected_bytes = canonical_json_bytes(elected)
            transport_bytes = canonical_json_bytes(found.transport_source)
            try:
                yield {"plan": elected, "stage": stage, "receipt": receipt,
                    "receiptBytes": receipt_bytes,
                    "transportSource": found.transport_source,
                    "revision": verified.plan["validationCommit"]}
            finally:
                if (regular_file_inventory(stage) != before
                        or canonical_json_bytes(receipt) != receipt_bytes
                        or canonical_json_bytes(elected) != elected_bytes
                        or canonical_json_bytes(found.transport_source) != transport_bytes):
                    raise ValueError("Lookup-only C# original changed during use")
                controls_unchanged()
                require_no_signing_secret(environ)


@contextmanager
def verified_selected_csharp_original(plan, discovery, state, *,
        sdk_inputs_artifact_id, sdk_inputs_artifact_sha256, trusted_workflow_sha,
        keyring, keys_directory, repository_root, environ, token,
        sdk_validation_tooling=None, sdk_apple_validation_policy=None,
        sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None):
    """Hold the selected C# binary's exact carrier object, without rebuilding it."""
    require_no_signing_secret(environ)
    root = Path(repository_root).resolve(strict=True)
    plan, discovery, state = Path(plan), Path(discovery), Path(state)
    control_plan = read_regular_file_bytes(plan, max_bytes=_LIMIT, reject_symlink_parents=True)
    controls = {path: regular_file_inventory(path, allow_empty=True)
        for path in (discovery, state)}

    def controls_unchanged():
        if (read_regular_file_bytes(plan, max_bytes=_LIMIT, reject_symlink_parents=True) != control_plan
                or any(regular_file_inventory(path, allow_empty=True) != inventory
                       for path, inventory in controls.items())):
            raise ValueError("Selected C# plan or state controls changed")

    with tempfile.TemporaryDirectory(prefix="sdk-csharp-selected-", dir=root) as temporary:
        private = Path(temporary).resolve()
        stage = private / "stage"
        with sdk_workflow.verified_inputs(plan, discovery, state,
                artifact_id=sdk_inputs_artifact_id, artifact_sha256=sdk_inputs_artifact_sha256,
                trusted_workflow_sha=trusted_workflow_sha, keyring=keyring,
                keys_directory=keys_directory, repository_root=root, environ=environ,
                token=token, sdk_validation_tooling=sdk_validation_tooling,
                sdk_apple_validation_policy=sdk_apple_validation_policy,
                sdk_facade_metadata_admission=sdk_facade_metadata_admission,
                sdk_android_metadata_admission=sdk_android_metadata_admission) as inputs:
            verified = product_reuse._verified_product_state(
                plan, discovery, state, root, environ, sdk_validation_tooling,
                sdk_original_workflow_sha=trusted_workflow_sha,
                sdk_apple_validation_policy=sdk_apple_validation_policy,
                sdk_facade_metadata_admission=sdk_facade_metadata_admission,
                sdk_android_metadata_admission=sdk_android_metadata_admission)
            controls_unchanged()
            if _INSTANCE not in verified.closure or _INSTANCE not in verified.sources:
                raise ValueError("Selected C# binary lacks an authenticated carrier original")
            record = verified.prior_by_instance[_INSTANCE]
            if record["state"] not in {"retained", "reused"}:
                raise ValueError("Selected C# binary is not a completed original")
            restored = restore_object(verified.sources[_INSTANCE], stage,
                build_key=record["buildKey"], receipt_sha256=record["receiptSha256"],
                object_sha256=record["objectSha256"])
            receipt = restored["receipt"]
            elected = {name: receipt[name] for name in PHASE_PLAN_KEYS}
            producer = receipt["producer"]
            if (product_reuse._identity(receipt) != _INSTANCE
                    or elected["buildKey"] != record["buildKey"]
                    or producer["event"] != "pull_request"
                    or producer["repository"] != verified.producer["repository"]
                    or producer["pullRequest"] != verified.producer["pullRequest"]
                    or receipt["productVersion"] != inputs["selection"]["sdkVersion"]):
                raise ValueError("Selected C# original differs from its PR or SDK version")
            root_key = private / "sdk-runtime-root.pub"
            root_key.write_bytes(git_regular_blob_bytes(root, verified.plan["validationCommit"],
                "gradle/release/keys/sdk-runtime-root.pub", max_bytes=65_536))
            verify_csharp_binary_stage(stage, receipt,
                inputs["sdk"]["directory"] / COMPATIBILITY_NAME, root_key)
            before = regular_file_inventory(stage)
            receipt_bytes = restored["receiptBytes"]
            elected_bytes = canonical_json_bytes(elected)
            transport = verified.prior_carrier_phases[_INSTANCE]["transportSource"]
            transport_bytes = canonical_json_bytes(transport)
            try:
                yield {"plan": elected, "stage": stage, "receipt": receipt,
                    "receiptBytes": receipt_bytes, "transportSource": transport,
                    "revision": verified.plan["validationCommit"]}
            finally:
                if (regular_file_inventory(stage) != before
                        or canonical_json_bytes(receipt) != receipt_bytes
                        or canonical_json_bytes(elected) != elected_bytes
                        or canonical_json_bytes(transport) != transport_bytes):
                    raise ValueError("Selected C# original changed during use")
                controls_unchanged()
                require_no_signing_secret(environ)


@contextmanager
def verified_csharp_original(plan, discovery, state, **kwargs):
    """Use a selected carrier, or a signed promoted/same-PR original."""
    root = Path(kwargs["repository_root"]).resolve(strict=True)
    verified = product_reuse._verified_product_state(
        Path(plan), Path(discovery), Path(state), root, kwargs["environ"],
        kwargs.get("sdk_validation_tooling"),
        sdk_original_workflow_sha=kwargs["trusted_workflow_sha"],
        sdk_apple_validation_policy=kwargs.get("sdk_apple_validation_policy"),
        sdk_facade_metadata_admission=kwargs.get("sdk_facade_metadata_admission"),
        sdk_android_metadata_admission=kwargs.get("sdk_android_metadata_admission"))
    route = (verified_selected_csharp_original if _INSTANCE in verified.closure
             else verified_lookup_only_same_pr_original)
    with route(plan, discovery, state, **kwargs) as original:
        yield original


def stage_csharp_original(plan, discovery, state, destination, **kwargs):
    """Publish only checked C# package inputs after their original context exits."""
    require_no_signing_secret(kwargs["environ"])
    root = Path(kwargs["repository_root"]).resolve(strict=True)
    _, _, destination = product_reuse._product_materialization_paths(
        root, discovery, state, destination)
    if (root not in destination.parents or destination.resolve(strict=False) != destination
            or destination.exists() or destination.is_symlink()):
        raise ValueError("C# original handoff destination must be fresh inside checkout")
    with tempfile.TemporaryDirectory(prefix="sdk-csharp-handoff-", dir=root) as temporary:
        prepared = Path(temporary).resolve() / "handoff"
        prepared.mkdir()
        with verified_csharp_original(plan, discovery, state, **kwargs) as original:
            source = original["stage"] / "outputs/csharp"
            source_files = regular_file_inventory(source)
            snapshot_regular_tree(source, prepared / "csharp-binary")
            if regular_file_inventory(prepared / "csharp-binary") != source_files:
                raise ValueError("C# original binary changed during handoff copy")
            profile_bytes = git_regular_blob_bytes(root, original["revision"],
                "gradle/release/toolchains/sdk/csharp.json", max_bytes=65_536)
            profile = load_sdk_dotnet_profile_bytes(profile_bytes)
            if profile.digest != original["plan"]["inputs"]["toolchainProfileDigest"]:
                raise ValueError("C# original differs from its pinned .NET toolchain profile")
            (prepared / "sdk-csharp-toolchain.json").write_bytes(profile_bytes)
            evidence = prepared / "original"
            evidence.mkdir()
            (evidence / "phase-receipt.json").write_bytes(original["receiptBytes"])
            (evidence / "phase-plan.json").write_bytes(canonical_json_bytes(original["plan"]))
            (evidence / "transport-source.json").write_bytes(canonical_json_bytes(
                original["transportSource"]))
            handoff_inventory = regular_file_inventory(prepared)
        if regular_file_inventory(prepared) != handoff_inventory:
            raise ValueError("C# original handoff changed after verification")
        publish_regular_tree(prepared, destination, expected_inventory=handoff_inventory)
    return {"csharpBinary": destination / "csharp-binary",
            "dotnetProfile": destination / "sdk-csharp-toolchain.json",
            "receipt": destination / "original/phase-receipt.json",
            "plan": destination / "original/phase-plan.json",
            "transport": destination / "original/transport-source.json"}


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
    argv = list(sys.argv[1:] if argv is None else argv)
    stage_original = bool(argv and argv[0] == "stage-original")
    if stage_original:
        argv.pop(0)
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("plan", "destination", "keyring", "keys-directory", "repository-root"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    for flag, name in (("discovery-root", "discovery"), ("state-root", "state")):
        parser.add_argument(f"--{flag}", dest=name, type=Path, required=True)
    if not stage_original:
        parser.add_argument("--expected-build-key", required=True)
    for name in ("sdk-inputs-artifact-sha256", "trusted-workflow-sha"):
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
            worker = stage_csharp_original if stage_original else execute
            worker(**arguments, environ=os.environ, token=os.environ.get("GITHUB_TOKEN", ""), **admissions)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
