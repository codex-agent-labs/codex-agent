"""Bind a prepared aggregate selection to caller-authenticated originals."""

from collections.abc import Mapping
from pathlib import Path
import sys

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from product_reuse import _dependency_closure
from runtime_aggregate_release import _METADATA, _selected_originals
from products.inventory import (
    load_canonical_json_bytes, read_regular_file_bytes, regular_file_inventory,
    require_exact_keys, require_regular_directory, require_relative_path, sha256_bytes,
)
from products.receipt import validate_phase_receipt
from products.registry import PhaseInstanceId


_ORIGINAL_FIELDS = {"stage", "receiptPath", "receipt", "receiptBytes"}


def _exact_directory(value, label):
    path = Path(value)
    if not path.is_absolute() or path != path.resolve(strict=True):
        raise ValueError(f"{label} must be an exact normalized directory")
    return require_regular_directory(path, label)


def _exact_file(value, label):
    path = Path(value)
    if not path.is_absolute() or path != path.resolve(strict=True):
        raise ValueError(f"{label} must be an exact normalized file")
    return path


def verify_aggregate_prepared_selection(
    root: Path, selection: dict, *, producer: dict, expected_build_key: str,
    originals: Mapping[PhaseInstanceId, dict],
):
    """Verify prepared bytes equal the caller's independently authenticated closure."""
    root = _exact_directory(root, "Prepared aggregate selection")
    identities = _dependency_closure((_METADATA,))
    if not isinstance(originals, Mapping) or set(originals) != set(identities):
        raise ValueError("Prepared aggregate caller originals must exactly match the dependency closure")
    selected = _selected_originals(root, selection, producer, expected_build_key)
    snapshots = {}
    for instance in identities:
        caller = require_exact_keys(originals[instance], _ORIGINAL_FIELDS,
                                    "Authenticated aggregate original")
        receipt_bytes = caller["receiptBytes"]
        if type(receipt_bytes) is not bytes:
            raise ValueError("Authenticated aggregate receipt bytes must be bytes")
        receipt_path = _exact_file(caller["receiptPath"], "Authenticated aggregate receipt")
        source_stage = _exact_directory(caller["stage"], "Authenticated aggregate stage")
        for source in (source_stage, receipt_path):
            if source == root or source in root.parents or root in source.parents:
                raise ValueError("Prepared aggregate selection overlaps an authenticated original")
        if read_regular_file_bytes(receipt_path, reject_symlink_parents=True) != receipt_bytes:
            raise ValueError("Authenticated aggregate receipt path differs from its original bytes")
        receipt = validate_phase_receipt(load_canonical_json_bytes(receipt_bytes))
        identity = (instance.product, instance.component, instance.phase, instance.target)
        if caller["receipt"] != receipt or tuple(receipt[name] for name in
                ("product", "component", "phase", "target")) != identity:
            raise ValueError("Authenticated aggregate receipt value or identity differs")
        source_inventory = regular_file_inventory(source_stage)
        prepared = selected[identity]
        prepared_receipt = read_regular_file_bytes(prepared["receiptPath"], reject_symlink_parents=True)
        prepared_inventory = regular_file_inventory(prepared["stage"])
        if (prepared_receipt != receipt_bytes or prepared["receipt"] != receipt
                or prepared_inventory != source_inventory):
            raise ValueError("Prepared aggregate original differs from caller-authenticated bytes")
        snapshots[instance] = (source_stage, source_inventory, receipt_path, receipt_bytes,
                               prepared["stage"], prepared_inventory, prepared["receiptPath"])

    aggregate_identity = (_METADATA.product, _METADATA.component, _METADATA.phase, _METADATA.target)
    aggregate = selected[aggregate_identity]
    outputs = [record for record in aggregate["receipt"]["outputs"] if record["kind"] == "runtime-aggregate"]
    if len(outputs) != 1:
        raise ValueError("Prepared aggregate receipt must declare exactly one aggregate manifest")
    output = outputs[0]
    relative = require_relative_path(output["relativePath"], "Prepared aggregate manifest path")
    manifest = aggregate["stage"] / relative
    if selection["aggregateManifest"] != manifest.relative_to(root).as_posix():
        raise ValueError("Prepared aggregate manifest differs from its declared receipt output")
    manifest_bytes = read_regular_file_bytes(manifest, reject_symlink_parents=True)
    if len(manifest_bytes) != output["bytes"] or sha256_bytes(manifest_bytes) != output["sha256"]:
        raise ValueError("Prepared aggregate manifest bytes differ from its declared receipt output")
    handoff = _exact_directory(root / selection["contractHandoff"],
                               "Prepared aggregate Contract handoff")
    if not regular_file_inventory(handoff, allow_empty=True):
        raise ValueError("Prepared aggregate Contract handoff is empty")

    for source_stage, source_inventory, receipt_path, receipt_bytes, prepared_stage, \
            prepared_inventory, prepared_receipt in snapshots.values():
        if (regular_file_inventory(source_stage) != source_inventory
                or read_regular_file_bytes(receipt_path, reject_symlink_parents=True) != receipt_bytes
                or regular_file_inventory(prepared_stage) != prepared_inventory
                or read_regular_file_bytes(prepared_receipt, reject_symlink_parents=True) != receipt_bytes):
            raise ValueError("Prepared aggregate or authenticated original changed during verification")
    return selected
