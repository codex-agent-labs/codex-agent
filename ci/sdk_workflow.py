"""Compose SDK handoff routes from the existing authenticated product replay."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import os
from pathlib import Path
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse
import sdk_handoff
from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, read_regular_file_bytes,
    regular_file_inventory, sha256_bytes, snapshot_regular_tree, publish_regular_tree,
)
from products.registry import NATIVE_BINDINGS, NATIVE_TARGETS, PhaseInstanceId
from products.runtime_aggregate_handoff import verified_runtime_aggregate_handoff
from products.sdk_inputs_verification import verified_sdk_inputs
from products.sdk_protected_runtime import _original_carrier
from products.sdk_inputs import REQUEST_NAME
from reuse import github_output


def _selection(plan, discovery, state, repository_root, environ, sdk_validation_tooling=None):
    plan_bytes = read_regular_file_bytes(plan, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
    validated = product_reuse._validate_plan(plan, repository_root)
    inspected = product_reuse.inspect_products(plan, discovery, state,
        repository_root=repository_root, environ=environ, include_sdk_selection=True,
        **({"sdk_validation_tooling": sdk_validation_tooling} if sdk_validation_tooling is not None else {}))
    selection = inspected.get("sdkInputSelection")
    if not isinstance(selection, dict):
        raise ValueError("SDK workflow requires selected SDK consumer work")
    if read_regular_file_bytes(plan, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True) != plan_bytes:
        raise ValueError("SDK workflow plan changed during inspection")
    return validated, selection, plan_bytes


def stage(plan, discovery, state, destination, *, keyring, keys_directory,
          repository_root, environ, token, trusted_workflow_sha=None, artifact_id=None,
          artifact_sha256=None, expected_build_key=None, expected_metadata_receipt_sha256=None):
    """Delegate source selection and both destination policies, never grant trust."""
    validated, selection, _ = _selection(plan, discovery, state, repository_root, environ)
    if selection.get("source") == "released-default":
        return product_reuse.materialize_sdk_default_inputs(plan, discovery, state, destination,
            keyring=keyring, keys_directory=keys_directory, repository_root=repository_root, environ=environ)
    if selection.get("source") != "current-runtime":
        raise ValueError("SDK workflow has an unsupported replayed Runtime source")
    if any(value is None for value in (trusted_workflow_sha, artifact_id, artifact_sha256,
                                      expected_build_key, expected_metadata_receipt_sha256)):
        raise ValueError("Current Runtime SDK handoff requires complete authenticated upload identity")
    return sdk_handoff.capture_sdk_handoff(plan, destination,
        artifact_id=artifact_id, artifact_sha256=artifact_sha256, trusted_workflow_sha=trusted_workflow_sha,
        expected_build_key=expected_build_key, expected_metadata_receipt_sha256=expected_metadata_receipt_sha256,
        sdk_version=selection["sdkVersion"], compatible_release_range=selection["compatibleReleaseRange"],
        compatible_runtime_compatibility_range=selection["compatibleRuntimeCompatibilityRange"],
        expected_contract_payload_sha256=selection["contractPayloadSha256"],
        keyring=keyring, keys_directory=keys_directory, selection_repository_root=repository_root,
        selection_revision=validated["validationCommit"], repository_root=repository_root, environ=environ, token=token)


@contextmanager
def verified_inputs(plan, discovery, state, *, artifact_id, artifact_sha256,
                    trusted_workflow_sha, keyring, keys_directory, repository_root, environ, token,
                    sdk_validation_tooling=None):
    """Keep upload, SDK policy and raw Runtime originals verified through consumer use.

    Returned paths expire on exit. Consumers must finish using them inside the
    context and admit their outputs only after its final checks succeed. The
    Runtime carrier's Contract receipts remain its originals, not replacements
    for the current candidate's independently selected Contract predecessors.
    """
    validated, selection, plan_bytes = _selection(plan, discovery, state, repository_root, environ,
                                                sdk_validation_tooling=sdk_validation_tooling)
    with tempfile.TemporaryDirectory(prefix="sdk-consumer-inputs-") as temporary:
        capture = Path(temporary).resolve() / "capture"
        product_reuse.capture_sdk_inputs_upload(plan, capture, artifact_id=artifact_id,
            artifact_sha256=artifact_sha256, trusted_workflow_sha=trusted_workflow_sha,
            expected_source=selection["source"], repository_root=repository_root, environ=environ, token=token)
        inventory = regular_file_inventory(capture, allow_empty=True)

        def unchanged():
            if (regular_file_inventory(capture, allow_empty=True) != inventory
                    or read_regular_file_bytes(plan, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True) != plan_bytes):
                raise ValueError("SDK consumer original plan or captured upload changed during use")

        with verified_sdk_inputs(capture / "original/sdk-inputs", keyring=keyring, keys_directory=keys_directory,
                selection_repository_root=repository_root, selection_revision=validated["validationCommit"],
                expected_contract_payload_sha256=selection["contractPayloadSha256"]) as sdk:
            arguments = sdk["arguments"]
            raw = read_regular_file_bytes(arguments["runtime_metadata_receipt"])
            receipt = load_canonical_json_bytes(raw)
            carrier = (capture / "original/runtime-original" if selection["source"] == "released-default"
                       else capture / "original/runtime-capture/original")
            carrier = _original_carrier(carrier, sha256_bytes(raw), receipt["buildKey"])
            with verified_runtime_aggregate_handoff(carrier, keyring=arguments["runtime_keyring"],
                    keys_directory=arguments["runtime_keys_directory"]) as runtime:
                if read_regular_file_bytes(runtime["indexInputs"]["attestation"]) != read_regular_file_bytes(
                        arguments["runtime_attestation"]):
                    raise ValueError("SDK inputs and raw Runtime carrier have different original attestations")
                for product, component, target in (("contract", "contract", "common"),
                                                    ("runtime", "runtime-aggregate", "aggregate")):
                    identity = PhaseInstanceId(product, component, "metadata", target)
                    if runtime["receiptBytes"][identity] != read_regular_file_bytes(arguments[f"{product}_metadata_receipt"]):
                        raise ValueError("SDK inputs and raw Runtime carrier have different original receipts")
                unchanged()
                yield {"selection": selection, "capture": capture, "sdk": sdk, "runtime": runtime}
        unchanged()


@contextmanager
def verified_ios_binary_inputs(plan, discovery, state, destination, *, expected_build_key,
                               native_uploads, trusted_workflow_sha, repository_root, environ, token):
    """Keep elected iOS binary Contract/native originals verified through use.

    This is not package readiness or output admission. The caller must execute
    the binary phase inside this lifetime and finalize only after successful exit.
    """
    from products.contract_projection import verify_contract_component_projection
    from sdk_apple_native import verified_sdk_apple_native_inputs

    root = Path(repository_root).resolve(strict=True)
    discovery, state, destination = product_reuse._product_materialization_paths(root, discovery, state, destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("SDK iOS binary inputs require a fresh destination")
    plan_bytes = read_regular_file_bytes(plan, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
    verified = product_reuse._verified_product_state(plan, discovery, state, root, environ, None)
    instance = PhaseInstanceId("sdk", "sdk-ios", "binary", "ios")
    elected = verified.prior_ready_plans.get(instance)
    if elected is None or elected["buildKey"] != expected_build_key:
        raise ValueError("SDK iOS binary is not ready with the expected elected key")
    evidence = verified.rebased_request.get("contractEvidence")
    if evidence is None or evidence["expectedTrustDomain"] != "release":
        raise ValueError("SDK iOS binary requires authenticated release Contract evidence")
    destination = product_reuse._prepare_destination(destination, root)
    trust = product_reuse._release_trust(root, verified.plan["validationCommit"], destination / "policy")
    if trust is None:
        raise ValueError("SDK iOS binary requires Git-authoritative release policy")
    predecessors = destination / "predecessors"
    ready = product_reuse._materialize_product_predecessors(
        verified, instance, predecessors, expected_build_key, root)

    def original(product, component, phase, target):
        if (product, component, target) != ("contract", "contract", "common"):
            raise ValueError("SDK iOS binary requested an unrelated Contract predecessor")
        directory = predecessors / "-".join((product, component, phase, target))
        receipt_path = directory / "phase-receipt.json"
        receipt = product_reuse.validate_phase_receipt(product_reuse._canonical_control(receipt_path, "Original Contract receipt"))
        manifest = product_reuse.verify_output_manifest_identity(
            directory / "stage", product, component, phase, target, receipt["productVersion"])
        if manifest["outputs"] != receipt["outputs"]:
            raise ValueError("SDK iOS Contract stage differs from its original receipt")
        return {"stage": directory / "stage", "receiptPath": receipt_path, "receipt": receipt}

    def one_output(record, kind):
        outputs = [row for row in record["receipt"]["outputs"] if row["kind"] == kind]
        if len(outputs) != 1:
            raise ValueError("SDK iOS binary requires one original Contract payload")
        return record["stage"] / outputs[0]["relativePath"]

    contract, version, handoff, _ = product_reuse._capture_runtime_contract(
        root, evidence, original, one_output, destination, trust)
    stem = f"codex-agent-contract-{version}"
    before = regular_file_inventory(destination, allow_empty=True)
    verify_contract_component_projection(contract["stage"], contract["receiptPath"],
        handoff / f"{stem}.attestation.json", handoff / f"{stem}.attestation.sig", handoff / "public-key.pub",
        expected_trust_domain="release", expected_contract_version=version,
        required_components=("ios-arm64", "ios-simulator-arm64"), keyring=trust.keyring, keys_directory=trust.keys)

    def unchanged():
        if (regular_file_inventory(destination, allow_empty=True) != before or
                read_regular_file_bytes(plan, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True) != plan_bytes):
            raise ValueError("SDK iOS binary original inputs changed during use")

    unchanged()
    with verified_sdk_apple_native_inputs(plan, uploads=native_uploads,
            trusted_workflow_sha=trusted_workflow_sha, repository_root=root, environ=environ, token=token) as native:
        if native["producer"] != verified.producer:
            raise ValueError("SDK iOS native evidence differs from the elected producer")
        unchanged()
        try:
            yield {"ready": ready, "producer": verified.producer,
                   "sdkVersion": verified.expected_fixed["versions"]["sdk"], "contract": contract,
                   "contractHandoff": handoff, "native": native["directory"], "inputs": destination}
        finally:
            unchanged()
    unchanged()


def execute_ios_binary(plan, discovery, state, destination, *, expected_build_key,
                       native_uploads, trusted_workflow_sha, repository_root, environ, token):
    """Execute an elected binary; receipt creation follows every input exit check."""
    from sdk_ios_binary import execute

    root = Path(repository_root).resolve(strict=True)
    discovery, state, destination = product_reuse._product_materialization_paths(root, discovery, state, destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("SDK iOS binary worker requires a fresh destination")
    with verified_ios_binary_inputs(plan, discovery, state, destination / "inputs",
            expected_build_key=expected_build_key, native_uploads=native_uploads,
            trusted_workflow_sha=trusted_workflow_sha, repository_root=root, environ=environ, token=token) as inputs:
        ready, producer, version = inputs["ready"], inputs["producer"], inputs["sdkVersion"]
        result = execute(ready, producer=producer, sdk_version=version,
            contract_metadata=inputs["contract"], verified_contract_handoff=inputs["contractHandoff"],
            native_evidence=inputs["native"], repository_root=root, destination=destination / "worker", environ=environ)
    if regular_file_inventory(result["stage"]) != result["outputInventory"]:
        raise ValueError("SDK iOS binary output changed before finalization")
    trust = "development" if producer["event"] == "pull_request" else "release"
    return product_reuse.finalize_phase_object(stage_root=result["stage"], phase_plan=ready,
        producer=producer, product_version=version, trust_domain=trust, destination=destination / "shard")


def matrix(plan, discovery, state, github_output_path, *, repository_root=None, environ=None, ios_binary=False, family=None,
           sdk_validation_tooling=None):
    """Expose only the fixed replay-elected SDK family before platform setup."""
    from sdk_phase import route

    if type(ios_binary) is not bool:
        raise ValueError("SDK binary projection must be boolean")
    if family is not None:
        product_reuse._sdk_family_worker_instance(None, family)
        if ios_binary:
            raise ValueError("SDK family and binary projection are mutually exclusive")
    def selected(instance):
        if family is not None:
            return product_reuse._sdk_family_worker_instance(instance, family)
        return (product_reuse._sdk_ios_binary_worker_instance if ios_binary else
                product_reuse._sdk_javascript_worker_instance)(instance)

    def worker_route(ready):
        if family in ("native-validation", "native-metadata"):
            from runtime_native_phase import _HOSTS
            host = ready["target"] if family == "native-validation" else "linux-x64"
            label, os_name, arch = _HOSTS[host]
            return {"runner": label, "runnerOs": os_name, "runnerArch": arch}
        if family == "native-package":
            from sdk_native_phase import route as native_route
            return native_route(ready)
        if ios_binary or family == "ios-package":
            return {"runner": "macos-26", "runnerOs": "macOS", "runnerArch": "ARM64"}
        if family == "javascript-metadata":
            return {"runner": "ubuntu-24.04", "runnerOs": "Linux", "runnerArch": "X64"}
        return route(ready)
    inspected = product_reuse.inspect_products(plan, discovery, state,
        repository_root=repository_root, environ=environ,
        **({"sdk_validation_tooling": sdk_validation_tooling} if sdk_validation_tooling is not None else {}))
    rows = [{**{field: ready[field] for field in ("product", "component", "phase", "target", "buildKey")},
             **worker_route(ready)}
            for ready in inspected["readyPlans"]
            if selected(product_reuse._identity(ready))]
    value = {"include": rows}
    github_output(github_output_path, {"sdk_matrix": canonical_json_bytes(value).decode().strip(),
                                      "sdk_workers_required": bool(rows)})
    return value


def capture(plan, destination, github_output_path, *, artifact_id, artifact_sha256,
            trusted_workflow_sha, state_wave=0, sdk_state_wave=None,
            repository_root=None, environ=None, token, ios_binary=False, family=None, sdk_validation_tooling=None):
    """Capture exact original state, then replay SDK readiness independently."""
    if type(ios_binary) is not bool:
        raise ValueError("SDK binary projection must be boolean")
    if family is not None:
        product_reuse._sdk_family_worker_instance(None, family)
        if ios_binary:
            raise ValueError("SDK family and binary projection are mutually exclusive")
    product_reuse.capture_runtime_resume_upload(plan, destination, artifact_id=artifact_id,
        artifact_sha256=artifact_sha256, trusted_workflow_sha=trusted_workflow_sha,
        state_wave=state_wave, **({"sdk_state_wave": sdk_state_wave} if sdk_state_wave is not None else {}),
        repository_root=repository_root, environ=environ, token=token)
    original = destination / "original"
    paths = {"input_root": original,
        "plan_path": original / "product-resume-inputs/plan/impact-plan.json",
        "discovery_root": original / "product-resume-state",
        "state_root": original / ("runtime-state" if state_wave or sdk_state_wave is not None else "product-resume-state")}
    value = matrix(paths["plan_path"], paths["discovery_root"], paths["state_root"], github_output_path,
                   repository_root=repository_root, environ=environ, **({"ios_binary": True} if ios_binary else {}),
                   **({"sdk_validation_tooling": sdk_validation_tooling} if sdk_validation_tooling is not None else {}),
                   **({"family": family} if family is not None else {}))
    github_output(github_output_path, {name: str(path) for name, path in paths.items()})
    return {**paths, "matrix": value}


def collect(input_root, destination, github_output_path, *, wave, trusted_workflow_sha,
            repository_root=None, environ=None, token, ios_binary=False, family=None, sdk_validation_tooling=None):
    """Advance only the exact elected SDK partition using the shared collector."""
    family_waves = {"native-package": 4, "ios-package": 5, "javascript-metadata": 6,
                    "native-validation": 7, "native-metadata": 8}
    if family is not None:
        product_reuse._sdk_family_worker_instance(None, family)
    allowed = (family_waves[family],) if family is not None else (3,) if ios_binary else (1, 2)
    if type(ios_binary) is not bool or (ios_binary and family is not None) or type(wave) is not int or wave not in allowed:
        raise ValueError("SDK collection requires its exact family wave: JavaScript1/2, iOS binary3, native package4, iOS package5, JS metadata6, native validation7, native metadata8")
    scope = ({"sdk_family": family} if family is not None else
             {"sdk_ios_binary_only": True} if ios_binary else {"sdk_javascript_only": True})
    tooling = {"sdk_validation_tooling": sdk_validation_tooling} if sdk_validation_tooling is not None else {}
    root = Path(repository_root or Path(__file__).resolve().parents[1]).resolve()
    input_root, _, destination = product_reuse._product_materialization_paths(root, input_root, input_root, destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("SDK collection destination must not exist")
    plan = input_root / "product-resume-inputs/plan/impact-plan.json"
    discovery = input_root / "product-resume-state"
    state = input_root / "runtime-state" if (input_root / "runtime-state").exists() else discovery
    collection = product_reuse.collect_runtime_workers(plan, discovery, state, destination / "collection",
        trusted_workflow_sha=trusted_workflow_sha, repository_root=root, environ=environ, token=token,
        **scope, **tooling)
    shards = [destination / "collection" / row["shardDirectory"]
              for row in collection["rows"] if row["result"] == "success"]
    failed = tuple(product_reuse._identity(row) for row in collection["rows"] if row["result"] != "success")
    evidence = tuple(destination / "collection" / row["sdkValidationEvidenceDirectory"]
                     for row in collection["rows"] if row["result"] == "success") if family == "native-validation" else ()
    handoff = destination / "handoff"
    advanced = product_reuse.advance_products(plan, discovery, state, shards, handoff / "runtime-state",
        github_output_path, repository_root=root, environ=environ, failed_instances=failed, **scope, **tooling,
        **({"sdk_evidence_roots": evidence} if family == "native-validation" else {}))
    for name in ("product-resume-inputs", "product-resume-state"):
        snapshot_regular_tree(input_root / name, handoff / name, allow_empty=True)
    if failed:
        github_output(github_output_path, {"sdk_matrix": '{"include":[]}', "sdk_workers_required": False})
    else:
        ready = matrix(handoff / "product-resume-inputs/plan/impact-plan.json", handoff / "product-resume-state",
                       handoff / "runtime-state", github_output_path, repository_root=root, environ=environ,
                       **tooling,
                       **({"ios_binary": True} if ios_binary else {}),
                       **({"family": family} if family is not None else {}))
        if wave >= 2 and ready["include"]:
            raise ValueError("SDK workers remain after their final collection wave")
    return advanced


def prepare_native(plan, discovery, state, destination, *, component, expected_build_key,
                   artifact_id, artifact_sha256, trusted_workflow_sha, keyring, keys_directory,
                   repository_root, environ, token, sdk_validation_tooling=None):
    """Prepare once from elected original inputs; this does not admit an upload.

    The transport caller must bind these outputs and the retained original plan
    to the observed preparation producer before any independent language job.
    No new product phase or receipt is manufactured for shared preparation.
    """
    from sdk_native_prepare import execute

    if component not in NATIVE_BINDINGS:
        raise ValueError("Unsupported native SDK preparation component")
    root = Path(repository_root).resolve(strict=True)
    discovery, state, destination = product_reuse._product_materialization_paths(
        root, discovery, state, destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("SDK native preparation destination must not exist")
    plan_bytes = read_regular_file_bytes(plan, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
    instance = PhaseInstanceId("sdk", component, "package", "desktop")
    fields = {"product": "sdk", "component": component, "phase": "package", "target": "desktop"}
    tooling = {"sdk_validation_tooling": sdk_validation_tooling} if sdk_validation_tooling is not None else {}
    with verified_inputs(plan, discovery, state, artifact_id=artifact_id, artifact_sha256=artifact_sha256,
            trusted_workflow_sha=trusted_workflow_sha, keyring=keyring, keys_directory=keys_directory,
            repository_root=root, environ=environ, token=token, **tooling) as inputs:
        selection = inputs["selection"]
        if fields not in selection["consumers"]:
            raise ValueError("SDK native preparation package is not selected")
        prepared = destination / "inputs"
        ready = product_reuse.materialize_product_predecessors(plan, discovery, state, instance, prepared,
            expected_build_key=expected_build_key, repository_root=root, environ=environ, **tooling)
        producer = product_reuse.validate_producer(product_reuse._canonical_control(
            prepared / "producer.json", "Elected native SDK producer"))
        contract = product_reuse.validate_phase_receipt(product_reuse._canonical_control(
            prepared / "contract-contract-metadata-common/phase-receipt.json", "Current Contract metadata"))
        bundles = [row for row in contract["outputs"] if row["kind"] == "contract-bundle"]
        if (tuple(contract[name] for name in ("product", "component", "phase", "target")) !=
                ("contract", "contract", "metadata", "common") or len(bundles) != 1
                or bundles[0]["sha256"] != selection["contractPayloadSha256"]):
            raise ValueError("Elected current Contract differs from verified native SDK inputs")
        before = regular_file_inventory(prepared, allow_empty=True)

        def original(product, runtime_component, phase, target):
            identity = PhaseInstanceId(product, runtime_component, phase, target)
            directory = prepared / "-".join((product, runtime_component, phase, target))
            receipt_path = directory / "phase-receipt.json"
            raw = read_regular_file_bytes(receipt_path)
            receipt = product_reuse.validate_phase_receipt(load_canonical_json_bytes(raw))
            if (product != "runtime" or runtime_component not in NATIVE_TARGETS or target != runtime_component
                    or phase not in {"package", "validation"}
                    or raw != inputs["runtime"]["receiptBytes"].get(identity)
                    or tuple(receipt[name] for name in ("product", "component", "phase", "target")) !=
                    (product, runtime_component, phase, target)):
                raise ValueError("Native preparation predecessor differs from its verified original")
            manifest = product_reuse.verify_output_manifest_identity(
                directory / "stage", product, runtime_component, phase, target, receipt["productVersion"])
            if manifest["outputs"] != receipt["outputs"]:
                raise ValueError("Native preparation stage differs from its original receipt")
            return {"stage": directory / "stage", "receiptPath": receipt_path, "receipt": receipt}

        runtime_stages = destination / "runtime-stages"
        for target in NATIVE_TARGETS:
            for phase in ("package", "validation"):
                record = original("runtime", target, phase, target)
                snapshot_regular_tree(record["stage"], runtime_stages / target / phase)
        runtime_before = regular_file_inventory(runtime_stages)

        def unchanged():
            if (regular_file_inventory(prepared, allow_empty=True) != before
                    or regular_file_inventory(runtime_stages) != runtime_before):
                raise ValueError("Native preparation original predecessor inputs changed")

        unchanged()
        result = execute(ready, producer=producer, sdk_version=selection["sdkVersion"],
            repository_root=root, destination=destination / "worker", runtime_stages=runtime_stages,
            compatibility_request=inputs["sdk"]["directory"] / REQUEST_NAME,
            predecessor=original, environ=environ)
        unchanged()
    unchanged()
    def outputs_unchanged():
        if (regular_file_inventory(result["preparedSources"]) != result["preparedSourcesInventory"]
                or regular_file_inventory(result["stagedSdks"]) != result["stagedSdkInventory"]
                or read_regular_file_bytes(plan, max_bytes=16 * 1024 * 1024,
                                           reject_symlink_parents=True) != plan_bytes):
            raise ValueError("Native SDK preparation outputs or original plan changed before handoff")

    outputs_unchanged()
    diagnostics = {name: read_regular_file_bytes(result["diagnostics"] / name,
                   reject_symlink_parents=True) for name in ("gradle.log", "execution.json")}
    # This is an external transport envelope, not a product phase or receipt.
    # The receiving worker must authenticate its upload owner and original plan.
    with tempfile.TemporaryDirectory(prefix="sdk-native-prepared-") as temporary:
        upload = Path(temporary).resolve() / "upload"
        (upload / "original-plan").mkdir(parents=True)
        (upload / "original-plan/impact-plan.json").write_bytes(plan_bytes)
        phase_bytes = read_regular_file_bytes(prepared / "phase-plan.json", reject_symlink_parents=True)
        if phase_bytes != canonical_json_bytes(ready):
            raise ValueError("Native preparation elected phase plan changed before handoff")
        (upload / "original-plan/phase-plan.json").write_bytes(phase_bytes)
        for name, source, inventory in (
                ("prepared-sources", result["preparedSources"], result["preparedSourcesInventory"]),
                ("staged-sdks", result["stagedSdks"], result["stagedSdkInventory"])):
            snapshot_regular_tree(source, upload / name)
            if regular_file_inventory(upload / name) != inventory:
                raise ValueError("Native preparation output changed during transport capture")
        (upload / "diagnostics").mkdir()
        for name, raw in diagnostics.items():
            (upload / "diagnostics" / name).write_bytes(raw)
        unchanged()
        outputs_unchanged()
        if any(read_regular_file_bytes(result["diagnostics"] / name, reject_symlink_parents=True) != raw
               for name, raw in diagnostics.items()):
            raise ValueError("Native preparation diagnostics changed during transport capture")
        publish_regular_tree(upload, destination / "upload", allow_empty=True)
    return result


def execute_javascript(plan, discovery, state, destination, *, phase, expected_build_key,
                       artifact_id, artifact_sha256, trusted_workflow_sha, keyring, keys_directory,
                       repository_root, environ, token, sdk_validation_tooling=None):
    """Execute elected SDK work; finalize only after original input contexts close."""
    from sdk_javascript_phase import execute

    if phase not in {"package", "validation"}:
        raise ValueError("Unsupported SDK JavaScript worker phase")
    root = Path(repository_root).resolve(strict=True)
    discovery, state, destination = product_reuse._product_materialization_paths(
        root, discovery, state, destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("SDK JavaScript worker destination must not exist")
    instance = PhaseInstanceId("sdk", "javascript", phase, "node")
    fields = {"product": "sdk", "component": "javascript", "phase": phase, "target": "node"}
    tooling = {"sdk_validation_tooling": sdk_validation_tooling} if sdk_validation_tooling is not None else {}
    with verified_inputs(plan, discovery, state, artifact_id=artifact_id, artifact_sha256=artifact_sha256,
            trusted_workflow_sha=trusted_workflow_sha, keyring=keyring, keys_directory=keys_directory,
            repository_root=root, environ=environ, token=token, **tooling) as inputs:
        selection = inputs["selection"]
        if fields not in selection["consumers"]:
            raise ValueError("SDK JavaScript worker is not selected")
        prepared = destination / "inputs"
        ready = product_reuse.materialize_product_predecessors(plan, discovery, state, instance, prepared,
            expected_build_key=expected_build_key, repository_root=root, environ=environ, **tooling)
        producer = product_reuse.validate_producer(product_reuse._canonical_control(
            prepared / "producer.json", "Elected SDK producer"))
        contract = product_reuse.validate_phase_receipt(product_reuse._canonical_control(
            prepared / "contract-contract-metadata-common/phase-receipt.json", "Current Contract metadata"))
        bundles = [row for row in contract["outputs"] if row["kind"] == "contract-bundle"]
        if len(bundles) != 1 or bundles[0]["sha256"] != selection["contractPayloadSha256"]:
            raise ValueError("Elected current Contract differs from verified SDK inputs")
        before = regular_file_inventory(prepared, allow_empty=True)

        def original(product, component, source_phase, target):
            identity = PhaseInstanceId(product, component, source_phase, target)
            directory = prepared / "-".join((product, component, source_phase, target))
            receipt_path = directory / "phase-receipt.json"
            raw = read_regular_file_bytes(receipt_path)
            receipt = product_reuse.validate_phase_receipt(load_canonical_json_bytes(raw))
            if product == "runtime" and raw != inputs["runtime"]["receiptBytes"].get(identity):
                raise ValueError("Elected SDK Runtime predecessor differs from the verified original")
            return {"stage": directory / "stage", "receiptPath": receipt_path, "receipt": receipt}

        trust = "development" if producer["event"] == "pull_request" else "release"
        result = execute(ready, producer=producer, sdk_version=selection["sdkVersion"], trust_domain=trust,
            repository_root=root, destination=destination / "worker", predecessor=original, environ=environ,
            compatibility_request=inputs["sdk"]["directory"] / REQUEST_NAME if phase == "package" else None)
        if regular_file_inventory(prepared, allow_empty=True) != before:
            raise ValueError("Elected SDK predecessor inputs changed during execution")
    if regular_file_inventory(prepared, allow_empty=True) != before:
        raise ValueError("Elected SDK predecessor inputs changed before finalization")
    if regular_file_inventory(result["stage"]) != result["outputInventory"]:
        raise ValueError("SDK JavaScript output changed before finalization")
    return product_reuse.finalize_phase_object(stage_root=result["stage"], phase_plan=ready,
        producer=producer, product_version=selection["sdkVersion"], trust_domain=trust,
        destination=destination / "shard")


def _workflow_main(argv):
    parser = argparse.ArgumentParser(description="Replay, capture and collect exact SDK phase work", allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    parsers = {name: commands.add_parser(name, allow_abbrev=False) for name in ("matrix", "capture", "collect")}
    for name, command in parsers.items():
        scope = command.add_mutually_exclusive_group()
        scope.add_argument("--ios-binary", action="store_true")
        scope.add_argument("--family", choices=product_reuse.SDK_WORKER_FAMILIES)
        command.add_argument("--github-output", dest="github_output_path", type=Path, required=True)
        command.add_argument("--repository-root", type=Path)
        command.add_argument("--sdk-validation-tooling", type=Path)
        if name == "matrix":
            for flag, dest in (("plan", "plan"), ("discovery-root", "discovery"), ("state-root", "state")):
                command.add_argument(f"--{flag}", dest=dest, type=Path, required=True)
        else:
            command.add_argument("--destination", type=Path, required=True)
            command.add_argument("--trusted-workflow-sha", required=True)
    captured = parsers["capture"]
    captured.add_argument("--plan", type=Path, required=True)
    captured.add_argument("--artifact-id", type=int, required=True)
    captured.add_argument("--artifact-sha256", required=True)
    captured.add_argument("--state-wave", type=int, default=0)
    captured.add_argument("--sdk-state-wave", type=int)
    parsers["collect"].add_argument("--input-root", type=Path, required=True)
    parsers["collect"].add_argument("--wave", type=int, choices=(1, 2, 3, 4, 5, 6, 7, 8), required=True)
    arguments = vars(parser.parse_args(argv))
    command = arguments.pop("command")
    try:
        policy = arguments.pop("sdk_validation_tooling")
        if policy is not None:
            arguments["sdk_validation_tooling"] = product_reuse._canonical_control(policy, "Caller SDK tooling policy")
        return {"matrix": matrix, "capture": capture, "collect": collect}[command](**arguments,
            environ=os.environ, **({"token": os.environ.get("GITHUB_TOKEN", "")} if command != "matrix" else {}))
    except (OSError, ValueError) as error:
        parser.error(str(error))


def _ios_binary_main(argv):
    parser = argparse.ArgumentParser(description="Execute only the elected SDK iOS binary phase")
    for name in ("plan", "discovery-root", "state-root", "destination", "repository-root"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    for name in ("trusted-workflow-sha", "expected-build-key"):
        parser.add_argument(f"--{name}", required=True)
    lanes = ("native-tests", "rust-device", "rust-simulator")
    for lane in lanes:
        parser.add_argument(f"--{lane}-artifact-id", type=int, required=True)
        parser.add_argument(f"--{lane}-artifact-sha256", required=True)
    arguments = vars(parser.parse_args(argv))
    uploads = {f"ios-{lane}": {
        "artifactId": arguments.pop(lane.replace("-", "_") + "_artifact_id"),
        "artifactSha256": arguments.pop(lane.replace("-", "_") + "_artifact_sha256"),
    } for lane in lanes}
    plan, discovery, state, destination = (arguments.pop(name) for name in (
        "plan", "discovery_root", "state_root", "destination"))
    try:
        execute_ios_binary(plan, discovery, state, destination, **arguments,
            native_uploads=uploads, environ=os.environ, token=os.environ.get("GITHUB_TOKEN", ""))
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "native-validation":
        from sdk_native_validation_workflow import main as validation_main
        return validation_main(argv[1:])
    if argv and argv[0] == "native-metadata":
        from sdk_native_metadata_workflow import main as metadata_main
        return metadata_main(argv[1:])
    if argv and argv[0] == "javascript-metadata":
        from sdk_javascript_metadata_workflow import main as metadata_main
        return metadata_main(argv[1:])
    if argv and argv[0] == "ios-package":
        from sdk_ios_package_workflow import main as ios_package_main
        return ios_package_main(argv[1:])
    if argv and argv[0] == "native-package":
        from sdk_native_package_workflow import main as native_package_main
        return native_package_main(argv[1:])
    if argv and argv[0] == "ios-binary":
        return _ios_binary_main(argv[1:])
    if argv and argv[0] in {"matrix", "capture", "collect"}:
        _workflow_main(argv)
        return 0
    javascript = bool(argv and argv[0] == "javascript")
    native_prepare = bool(argv and argv[0] == "native-prepare")
    worker = javascript or native_prepare
    if worker:
        argv.pop(0)
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("plan", "discovery-root", "state-root", "destination", "keyring", "keys-directory", "repository-root"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--artifact-id", type=int, required=worker)
    for name in ("trusted-workflow-sha", "artifact-sha256", "expected-build-key"):
        parser.add_argument(f"--{name}", required=worker)
    if javascript:
        parser.add_argument("--phase", choices=("package", "validation"), required=True)
    elif native_prepare:
        parser.add_argument("--component", choices=NATIVE_BINDINGS, required=True)
    else:
        parser.add_argument("--expected-metadata-receipt-sha256")
    if worker:
        parser.add_argument("--sdk-validation-tooling", type=Path)
    arguments = vars(parser.parse_args(argv))
    plan, discovery, state, destination = (arguments.pop(name) for name in ("plan", "discovery_root", "state_root", "destination"))
    try:
        action = prepare_native if native_prepare else execute_javascript if javascript else stage
        if worker:
            policy = arguments.pop("sdk_validation_tooling")
            if policy is not None:
                arguments["sdk_validation_tooling"] = product_reuse._canonical_control(policy, "Caller SDK tooling policy")
        action(plan, discovery, state, destination, **arguments,
            environ=os.environ, token=os.environ.get("GITHUB_TOKEN", ""))
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
