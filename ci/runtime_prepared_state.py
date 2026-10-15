"""Restore authenticated prepared Runtime state without planner/tooling execution.

The caller authenticates the original upload and validates the current plan and
producer first. Recorded results are checked, not replanned or newly authorized.
"""

from pathlib import Path
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse as products
from runtime_aggregate_release import _destination
from products.inventory import (
    canonical_json_bytes, publish_regular_tree, regular_file_inventory,
    read_regular_file_bytes, require_array, require_exact_keys, require_regular_directory,
    require_sha256, snapshot_regular_tree,
)
from products.receipt import validate_producer, verify_output_manifest_identity
from products.registry import NATIVE_TARGETS, PhaseInstanceId
from products.restore import object_relative_path, restore_object, verify_carrier
from products.sdk_release_selection import sdk_runtime_source


def restore_prepared_runtime_originals(plan, original_root, destination, *, producer, target,
                                      expected_build_key, selection, state_wave, repository_root,
                                      completed_frozen=None, selected_root=None):
    """Return restored original phases only after the recorded carrier is bound."""
    if target not in (*NATIVE_TARGETS, "aggregate") or type(state_wave) is not int or not 0 <= state_wave <= 5:
        raise ValueError("Prepared Runtime state requires an exact target and original wave")
    require_sha256(expected_build_key, "Prepared Runtime metadata key")
    producer = validate_producer(producer)
    consumer = products._consumer(plan, {"GITHUB_RUN_ID": str(producer["runId"]),
                                       "GITHUB_RUN_ATTEMPT": str(producer["runAttempt"])})
    if consumer["producer"] != producer:
        raise ValueError("Prepared Runtime producer differs from the current plan")
    original_root = Path(original_root)
    for directory in (original_root, *original_root.parents):
        require_regular_directory(directory, "Prepared Runtime original ancestry")
    semantic = {}
    protected = (original_root,)
    if completed_frozen is not None:
        from reuse_qualification import CompletedFrozenReuse
        if type(completed_frozen) is not CompletedFrozenReuse or selected_root is None:
            raise ValueError("Prepared native reuse requires authenticated completion and selected bytes")
        selected_root = Path(selected_root)
        if not selected_root.is_absolute() or selected_root.resolve(strict=True) != selected_root:
            raise ValueError("Prepared native reuse selection must be an exact absolute directory")
        for directory in (selected_root, *selected_root.parents):
            require_regular_directory(directory, "Prepared native selection ancestry")
        if selected_root == original_root or selected_root in original_root.parents or original_root in selected_root.parents:
            raise ValueError("Prepared native selection must be separate from original controls")
        semantic["completed_frozen"] = completed_frozen
        protected += (selected_root,)
    elif selected_root is not None:
        raise ValueError("Prepared selection cannot replace unauthenticated original bodies")
    output = _destination(destination, protected)
    before = regular_file_inventory(original_root, allow_empty=True)
    control_bytes = canonical_json_bytes({"plan": plan, "producer": producer, "selection": selection})
    discovery = original_root / "product-resume-state"
    state = original_root / ("runtime-state" if state_wave else "product-resume-state")
    recorded_producer = products._canonical_control(discovery / "producer.json", "Original discovery producer")
    if validate_producer(recorded_producer) != producer:
        raise ValueError("Prepared Runtime original producer differs from the current caller")
    repository = Path(repository_root).resolve(strict=True)
    request = products._relocated_wave_control(discovery / "reuse-wave-request.json", "Original reuse request", repository)
    if completed_frozen is not None:
        completed_frozen.check_request(request)
    requested = tuple(products._identity(require_exact_keys(value, products._IDENTITY_KEYS,
        "Original requested phase")) for value in require_array(request["requested"], "Original requested phases"))
    if requested != tuple(sorted(set(requested))) or requested != products._requested(plan):
        raise ValueError("Prepared Runtime request differs from the current plan selection")
    versions = products._versions(repository, plan["validationCommit"])
    source = sdk_runtime_source(repository, plan["validationCommit"], instances=products._dependency_closure(requested),
        runtime_version=versions["runtime-release"], sdk_version=versions["sdk"])
    if (request.get("sdkRuntimeSource") != source or request["versions"] != versions
            or request["repositoryRevision"] != plan["validationCommit"]
            or request["repository"] != plan["repository"] or request["pullRequest"] != plan["pullRequest"]
            or type(request["schemaVersion"]) is not int or request["schemaVersion"] != 1
            or request["requestType"] != "reuse-wave"):
        raise ValueError("Prepared Runtime request differs from original Git or plan policy")
    result = products._canonical_control(state / "reuse-wave-result.json", "Original reuse result")
    _, materialized, _ = products._validate_reuse_result(result, requested,
        require_complete=False, sdk_runtime_external=source is not None)
    phases = {products._identity(value): value for value in result["phases"]}
    metadata = PhaseInstanceId("runtime", "runtime-aggregate" if target == "aggregate" else target, "metadata", target)
    needed = products._dependency_closure((metadata,))
    if (metadata not in phases or selection["metadata"] != phases[metadata]
            or selection["producer"] != producer or selection["target"] != target
            or phases[metadata]["buildKey"] != expected_build_key
            or not set(needed).issubset(materialized)):
        raise ValueError("Prepared Runtime selection lacks its exact completed original metadata closure")
    carrier_root = state / ("carrier" if result["fullReuse"] else "reused-carrier")
    carrier = verify_carrier(carrier_root, materialized, consumer, object_root=state, **semantic)
    carrier_phases = {products._identity(value): value for value in carrier["resolution"]["phases"]}
    fields = (*products._IDENTITY_KEYS, "buildKey", "receiptSha256", "objectSha256")
    if any(any(carrier_phases[identity][field] != phases[identity][field] for field in fields)
           for identity in materialized):
        raise ValueError("Prepared Runtime carrier differs from its recorded original result")
    objects = {products._identity(value): value for value in carrier["objects"]}

    def unchanged():
        if (regular_file_inventory(original_root, allow_empty=True) != before
                or canonical_json_bytes({"plan": plan, "producer": producer, "selection": selection}) != control_bytes):
            raise ValueError("Prepared Runtime originals changed during restoration")

    unchanged()
    restored = {}
    with tempfile.TemporaryDirectory(prefix="runtime-prepared-originals-") as temporary:
        prepared = Path(temporary).resolve() / "originals"
        for identity in needed:
            record = objects[identity]
            name = "-".join((identity.product, identity.component, identity.phase, identity.target))
            directory = prepared / name
            source = (state / record["originalObjectPath"] if "originalObjectPath" in record else
                carrier_root / object_relative_path(record["buildKey"], record["receiptSha256"]))
            original = completed_frozen.envelope(record) if completed_frozen is not None else None
            if original is None:
                original = restore_object(source,
                    directory / "stage", build_key=record["buildKey"], receipt_sha256=record["receiptSha256"],
                    object_sha256=record["objectSha256"])
            else:
                # Native completion authenticates the original receipt and object;
                # hash every supplied stage byte against that receipt before use.
                selected = selected_root / "predecessors" / name
                stage = (selected_root / "runtime" / target / identity.phase
                         if target != "aggregate" and identity.product == "runtime"
                         and identity.component == target and identity.target == target else selected / "stage")
                raw = read_regular_file_bytes(selected / "phase-receipt.json", reject_symlink_parents=True)
                receipt = original["receipt"]
                manifest = verify_output_manifest_identity(stage, identity.product, identity.component,
                    identity.phase, identity.target, receipt["productVersion"])
                if raw != original["receiptBytes"] or manifest["outputs"] != receipt["outputs"]:
                    raise ValueError("Prepared stage differs from its native-qualified original receipt")
                inventory = regular_file_inventory(stage)
                snapshot_regular_tree(stage, directory / "stage")
                copied = verify_output_manifest_identity(directory / "stage", identity.product, identity.component,
                    identity.phase, identity.target, receipt["productVersion"])
                if (copied["outputs"] != receipt["outputs"] or regular_file_inventory(stage) != inventory
                        or regular_file_inventory(directory / "stage") != inventory
                        or read_regular_file_bytes(selected / "phase-receipt.json", reject_symlink_parents=True) != raw):
                    raise ValueError("Prepared native stage changed during private capture")
            if original["receiptBytes"] != record["receiptBytes"] or original["receipt"] != record["receipt"]:
                raise ValueError("Prepared Runtime restore changed an original receipt")
            (directory / "phase-receipt.json").write_bytes(original["receiptBytes"])
            restored[identity] = {"stage": output / name / "stage", "receiptPath": output / name / "phase-receipt.json",
                "receipt": original["receipt"], "receiptBytes": original["receiptBytes"]}
        unchanged()
        _destination(output, protected)
        publish_regular_tree(prepared, output)
    return restored
