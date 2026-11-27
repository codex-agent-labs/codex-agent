"""Bind a prepared native selection to caller-authenticated original phases.

No state replay, source authorization, signature verification or signing occurs
here. The existing native leaf still admits Contract trust and full semantics.
"""

from pathlib import Path
import re
import sys

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from products.inventory import (
    load_canonical_json_bytes, read_regular_file_bytes, regular_file_inventory,
    require_array, require_exact_keys, require_relative_path, require_regular_directory,
    require_semver, require_sha256, sha256_bytes,
)
from products.receipt import validate_phase_receipt, validate_producer, verify_output_manifest_identity
from products.registry import NATIVE_TARGETS, PhaseInstanceId
from products.restore import CARRIER_PHASE_KEYS


_PHASES = ("binary", "package", "validation", "metadata")
_IDENTITY = ("product", "component", "phase", "target")
_JSON_LIMIT = 16 * 1024 * 1024


def verify_native_prepared_selection(root, selection, *, producer, target, expected_build_key, originals):
    """Return existing native leaf arguments scoped to the supplied private root."""
    if target not in NATIVE_TARGETS:
        raise ValueError("Prepared native selection requires an exact native target")
    require_sha256(expected_build_key, "Prepared native metadata key")
    producer = validate_producer(producer)
    root = Path(root)
    for directory in (root, *root.parents):
        require_regular_directory(directory, "Prepared native selection ancestry")
    before = regular_file_inventory(root, allow_empty=True)
    selection_raw = read_regular_file_bytes(root / "selection.json", max_bytes=_JSON_LIMIT, reject_symlink_parents=True)
    require_exact_keys(selection, {"schemaVersion", "target", "metadata", "producer", "contractVersion",
        "contract", "contractReceiptSha256", "receiptSha256s", "phaseReceipts", "runtimeStageRoot",
        "variantPayload", "releaseHandoffs"}, "Prepared native selection")
    if (load_canonical_json_bytes(selection_raw) != selection or type(selection["schemaVersion"]) is not int
            or selection["schemaVersion"] != 1 or selection["producer"] != producer or selection["target"] != target):
        raise ValueError("Prepared native selection differs from its canonical caller identity")
    version = require_semver(selection["contractVersion"], "Prepared Contract version")
    require_exact_keys(selection["phaseReceipts"], _PHASES, "Prepared native receipt paths")
    require_exact_keys(selection["receiptSha256s"], _PHASES, "Prepared native receipt digests")

    def path(value, expected):
        if require_relative_path(value, "Prepared native path") != expected:
            raise ValueError("Prepared native path differs from the original selection layout")
        return root / expected

    runtime_root = path(selection["runtimeStageRoot"], "runtime")
    receipts, originals_by_identity, inventories = {}, {}, {}
    for product, component, original_target in (("contract", "contract", "common"), ("runtime", target, target)):
        for phase in _PHASES:
            identity = PhaseInstanceId(product, component, phase, original_target)
            if identity not in originals:
                raise ValueError("Prepared native selection lacks an authenticated original phase")
            original = originals[identity]
            raw = original["receiptBytes"]
            receipt = validate_phase_receipt(load_canonical_json_bytes(raw))
            if (receipt != original["receipt"] or tuple(receipt[name] for name in _IDENTITY) !=
                    (product, component, phase, original_target)
                    or read_regular_file_bytes(original["receiptPath"], max_bytes=_JSON_LIMIT,
                        reject_symlink_parents=True) != raw):
                raise ValueError("Prepared native original receipt identity or bytes differ")
            relative = f"predecessors/{product}-{component}-{phase}-{original_target}"
            receipt_path = root / relative / "phase-receipt.json"
            if product == "runtime":
                receipt_path = path(selection["phaseReceipts"][phase], relative + "/phase-receipt.json")
                if require_sha256(selection["receiptSha256s"][phase], "Prepared Runtime receipt digest") != sha256_bytes(raw):
                    raise ValueError("Prepared Runtime receipt digest differs from its original")
                stage = runtime_root / target / phase
                receipts[phase] = receipt_path
            else:
                stage = root / relative / "stage"
                if read_regular_file_bytes(root / f"contract-input/execution-closure/receipts/{phase}.json",
                        max_bytes=_JSON_LIMIT, reject_symlink_parents=True) != raw:
                    raise ValueError("Prepared Contract execution closure rewrites an original receipt")
            if read_regular_file_bytes(receipt_path, max_bytes=_JSON_LIMIT, reject_symlink_parents=True) != raw:
                raise ValueError("Prepared phase receipt differs from its authenticated original")
            manifest = verify_output_manifest_identity(stage, product, component, phase, original_target,
                receipt["productVersion"])
            inventory = regular_file_inventory(original["stage"])
            if manifest["outputs"] != receipt["outputs"] or regular_file_inventory(stage) != inventory:
                raise ValueError("Prepared phase stage differs from its authenticated original")
            originals_by_identity[identity] = receipt
            inventories[Path(original["stage"])] = inventory

    metadata_id = PhaseInstanceId("runtime", target, "metadata", target)
    metadata = originals_by_identity[metadata_id]
    selected = require_exact_keys(selection["metadata"], CARRIER_PHASE_KEYS, "Prepared native metadata selection")
    if (tuple(selected[name] for name in _IDENTITY) != ("runtime", target, "metadata", target)
            or selected["state"] not in {"retained", "reused"} or selected["buildKey"] != expected_build_key
            or metadata["buildKey"] != expected_build_key
            or selected["receiptSha256"] != selection["receiptSha256s"]["metadata"]):
        raise ValueError("Prepared native metadata differs from its exact original election")
    require_sha256(selected["objectSha256"], "Prepared native original object digest")
    payloads = [output for output in metadata["outputs"] if output["kind"] == "runtime-variant"]
    if len(payloads) != 1:
        raise ValueError("Prepared native metadata requires one original variant payload")
    payload = path(selection["variantPayload"], f"runtime/{target}/metadata/" + payloads[0]["relativePath"])
    expected_runtime = sorted(({
        **record, "relativePath": f"{target}/{phase}/" + record["relativePath"]}
        for phase in _PHASES for record in inventories[Path(originals[
            PhaseInstanceId("runtime", target, phase, target)]["stage"]) ]), key=lambda record: record["relativePath"])
    if regular_file_inventory(runtime_root) != expected_runtime:
        raise ValueError("Prepared native runtime root contains unrelated original stages")

    contract_id = PhaseInstanceId("contract", "contract", "metadata", "common")
    contract_receipt = originals_by_identity[contract_id]
    contract_sha = sha256_bytes(originals[contract_id]["receiptBytes"])
    if contract_receipt["productVersion"] != version or require_sha256(
            selection["contractReceiptSha256"], "Prepared Contract receipt digest") != contract_sha:
        raise ValueError("Prepared Contract version or receipt digest differs from its original")
    stem = f"codex-agent-contract-{version}"
    contract_paths = {"stage": "predecessors/contract-contract-metadata-common/stage",
        "receipt": "predecessors/contract-contract-metadata-common/phase-receipt.json",
        "payload": f"contract-input/{stem}.zip", "attestation": f"contract-input/{stem}.attestation.json",
        "signature": f"contract-input/{stem}.attestation.sig", "public_key": "contract-input/public-key.pub"}
    require_exact_keys(selection["contract"], contract_paths, "Prepared Contract paths")
    contract = {name: path(selection["contract"][name], relative) for name, relative in contract_paths.items()}
    release_paths = require_array(selection["releaseHandoffs"], "Prepared native retained handoffs")
    if len(release_paths) != len(set(require_relative_path(value, "Prepared retained handoff") for value in release_paths)):
        raise ValueError("Prepared retained handoffs must be unique")
    handoffs = []
    for relative in release_paths:
        if re.fullmatch(r"retained-release-handoffs/[0-9a-f]{64}", relative) is None:
            raise ValueError("Prepared retained handoff differs from its prescribed original layout")
        handoff = root / relative
        regular_file_inventory(handoff)
        handoffs.append(handoff)
    if (regular_file_inventory(root, allow_empty=True) != before or any(
            regular_file_inventory(stage) != inventory for stage, inventory in inventories.items())
            or any(read_regular_file_bytes(originals[identity]["receiptPath"], max_bytes=_JSON_LIMIT,
                reject_symlink_parents=True) != originals[identity]["receiptBytes"] for identity in originals_by_identity)):
        raise ValueError("Prepared native or authenticated originals changed during binding")
    return {"runtime_stage_root": runtime_root, "phase_receipts": receipts, "variant_payload": payload,
        "contract": contract, "contract_version": version, "release_handoffs": tuple(handoffs),
        "expected_receipt_sha256s": dict(selection["receiptSha256s"]),
        "expected_contract_receipt_sha256": contract_sha, "expected_build_key": expected_build_key}
