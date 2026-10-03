"""Transport-only deltas over authenticated immutable Runtime uploads.

References never grant phase admission. The existing original-CI observers,
object verifiers and complete planner replay still authenticate the resolved
bytes. Old full uploads remain valid and are never edited or replaced.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import tempfile

from products.inventory import (
    PRODUCT_JSON_LIMIT, _open_regular_file, _stat_identity,
    load_canonical_json_bytes, publish_regular_tree, read_regular_file_bytes,
    regular_file_inventory, require_exact_keys, require_integer,
    require_relative_path, require_sha256, require_sorted_unique_records,
    validate_file_record, write_canonical_json,
)

REFERENCE_NAME = "runtime-references.json"
_ROOTS = {"product-resume-inputs", "product-resume-state", "runtime-state"}


def _path(value):
    path = require_relative_path(value, "Runtime reference path")
    if path.split("/")[0] not in _ROOTS or "/" not in path:
        raise ValueError("Runtime reference is outside the original handoff roots")
    return path


def validate_references(value, state_wave):
    value = require_exact_keys(value, {"schemaVersion", "base", "inventory", "references"},
                               "Runtime references")
    if require_integer(value["schemaVersion"], "Runtime references schema", 1) != 1:
        raise ValueError("Unsupported Runtime references schema")
    base = require_exact_keys(value["base"], {"artifactId", "artifactSha256", "stateWave"},
                              "Runtime reference base")
    require_integer(base["artifactId"], "Runtime reference upload ID", 1)
    require_sha256(base["artifactSha256"], "Runtime reference upload digest")
    wave = require_integer(base["stateWave"], "Runtime reference base wave")
    if type(state_wave) is not int or not 0 <= wave < state_wave <= 5:
        raise ValueError("Runtime reference must identify a strictly earlier Runtime wave")
    inventory = require_sorted_unique_records(value["inventory"], "Runtime reference inventory")
    if not inventory or len(inventory) > 16_384:
        raise ValueError("Runtime reference inventory exceeds its fixed bound")
    files = {}
    for record in inventory:
        validate_file_record(record, "Runtime reference file", with_kind=False, allow_empty=True)
        files[_path(record["relativePath"])] = record
    if (sum(record["bytes"] for record in inventory) > 16 * 1024 * 1024 * 1024
            or any(record["bytes"] > 8 * 1024 * 1024 * 1024 for record in inventory)):
        raise ValueError("Expanded Runtime reference inventory exceeds the transport byte bounds")
    references = require_sorted_unique_records(value["references"], "Runtime references")
    if not references:
        raise ValueError("Runtime reference transport requires inherited files")
    for record in references:
        require_exact_keys(record, {"relativePath", "sourcePath", "bytes", "sha256"},
                           "Runtime reference")
        _path(record["sourcePath"])
        target = _path(record["relativePath"])
        if {key: record[key] for key in ("relativePath", "bytes", "sha256")} != files.get(target):
            raise ValueError("Runtime reference differs from its exact file inventory")
    return value


def _copy_exact(source, destination, record):
    descriptor, before = _open_regular_file(source, "Runtime reference source", reject_symlink_parents=True)
    try:
        if before.st_size != record["bytes"]:
            raise ValueError("Runtime reference source size differs from its immutable identity")
        destination.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        with os.fdopen(descriptor, "rb", closefd=False) as incoming, destination.open("xb") as outgoing:
            remaining = before.st_size
            while remaining:
                chunk = incoming.read(min(1024 * 1024, remaining))
                if not chunk:
                    raise ValueError("Runtime reference source was truncated")
                digest.update(chunk)
                outgoing.write(chunk)
                remaining -= len(chunk)
            if incoming.read(1) or _stat_identity(before) != _stat_identity(os.fstat(descriptor)):
                raise ValueError("Runtime reference source changed during resolution")
        if "sha256:" + digest.hexdigest() != record["sha256"]:
            raise ValueError("Runtime reference source digest differs from its immutable identity")
    finally:
        os.close(descriptor)


def stage_reference_handoff(handoff, base_root, base_capture, destination, *, state_wave):
    """Emit only changed files and exact references; never mutate the full handoff."""
    transport = load_canonical_json_bytes(read_regular_file_bytes(
        base_capture, max_bytes=PRODUCT_JSON_LIMIT, reject_symlink_parents=True))
    artifact = transport["artifact"]
    base = {"artifactId": artifact["id"], "artifactSha256": artifact["digest"],
            "stateWave": transport.get("stateWave", 0)}
    inventory = regular_file_inventory(handoff, allow_empty=True)
    original = regular_file_inventory(base_root, allow_empty=True)
    by_content = {}
    for record in original:
        by_content.setdefault((record["bytes"], record["sha256"]), record["relativePath"])
    references = [{**record, "sourcePath": by_content[(record["bytes"], record["sha256"])]}
                  for record in inventory if (record["bytes"], record["sha256"]) in by_content]
    if not references:
        raise ValueError("Runtime reference export has no existing immutable files")
    value = validate_references({"schemaVersion": 1, "base": base,
                                "inventory": inventory, "references": references}, state_wave)
    inherited = {record["relativePath"] for record in references}
    with tempfile.TemporaryDirectory(prefix="runtime-reference-export-") as temporary:
        prepared = Path(temporary).resolve() / "handoff"
        prepared.mkdir()
        for record in inventory:
            if record["relativePath"] not in inherited:
                _copy_exact(Path(handoff) / record["relativePath"], prepared / record["relativePath"], record)
        write_canonical_json(prepared / REFERENCE_NAME, value)
        if (regular_file_inventory(handoff, allow_empty=True) != inventory
                or regular_file_inventory(base_root, allow_empty=True) != original):
            raise ValueError("Runtime reference export inputs changed")
        publish_regular_tree(prepared, destination, allow_empty=True)
    return value


def resolve_reference_handoff(original, base_root, value, *, state_wave):
    """Resolve a freshly authenticated base; caller must still admit all phases."""
    value = validate_references(value, state_wave)
    referenced = {record["relativePath"] for record in value["references"]}
    materialized = regular_file_inventory(original, allow_empty=True, excluded_paths=(REFERENCE_NAME,))
    if materialized != [record for record in value["inventory"] if record["relativePath"] not in referenced]:
        raise ValueError("Runtime reference delta has missing, overlapping or unexpected files")
    for record in value["references"]:
        _copy_exact(Path(base_root) / record["sourcePath"], Path(original) / record["relativePath"], record)
    (Path(original) / REFERENCE_NAME).unlink()
    if regular_file_inventory(original, allow_empty=True) != value["inventory"]:
        raise ValueError("Resolved Runtime reference inventory differs from the frozen bytes")
    return value["inventory"]
