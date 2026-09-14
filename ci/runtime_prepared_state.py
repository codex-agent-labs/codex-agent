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
    require_array, require_exact_keys, require_regular_directory, require_sha256,
)
from products.receipt import validate_producer
from products.registry import NATIVE_TARGETS, PhaseInstanceId
from products.restore import object_relative_path, restore_object, verify_carrier
from products.sdk_release_selection import sdk_runtime_source


def restore_prepared_runtime_originals(plan, original_root, destination, *, producer, target,
                                      expected_build_key, selection, state_wave, repository_root):
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
    output = _destination(destination, (original_root,))
    before = regular_file_inventory(original_root, allow_empty=True)
    control_bytes = canonical_json_bytes({"plan": plan, "producer": producer, "selection": selection})
    discovery = original_root / "product-resume-state"
    state = original_root / ("runtime-state" if state_wave else "product-resume-state")
    recorded_producer = products._canonical_control(discovery / "producer.json", "Original discovery producer")
    if validate_producer(recorded_producer) != producer:
        raise ValueError("Prepared Runtime original producer differs from the current caller")
    repository = Path(repository_root).resolve(strict=True)
    request = products._relocated_wave_control(discovery / "reuse-wave-request.json", "Original reuse request", repository)
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
    carrier = verify_carrier(carrier_root, materialized, consumer)
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
            original = restore_object(carrier_root / object_relative_path(record["buildKey"], record["receiptSha256"]),
                directory / "stage", build_key=record["buildKey"], receipt_sha256=record["receiptSha256"],
                object_sha256=record["objectSha256"])
            if original["receiptBytes"] != record["receiptBytes"] or original["receipt"] != record["receipt"]:
                raise ValueError("Prepared Runtime restore changed an original receipt")
            (directory / "phase-receipt.json").write_bytes(original["receiptBytes"])
            restored[identity] = {"stage": output / name / "stage", "receiptPath": output / name / "phase-receipt.json",
                "receipt": original["receipt"], "receiptBytes": original["receiptBytes"]}
        unchanged()
        _destination(output, (original_root,))
        publish_regular_tree(prepared, output)
    return restored
