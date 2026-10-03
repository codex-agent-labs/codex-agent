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
ORIGINAL_REFERENCE_NAME = "runtime-original-references.json"
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
    base_keys = {"artifactId", "artifactSha256", "stateWave"}
    if isinstance(value["base"], dict) and "referenceControlSha256" in value["base"]:
        base_keys.add("referenceControlSha256")
    base = require_exact_keys(value["base"], base_keys,
                              "Runtime reference base")
    require_integer(base["artifactId"], "Runtime reference upload ID", 1)
    require_sha256(base["artifactSha256"], "Runtime reference upload digest")
    if "referenceControlSha256" in base:
        require_sha256(base["referenceControlSha256"], "Runtime reference control digest")
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
    if "referenceControlSha256" in transport:
        base["referenceControlSha256"] = transport["referenceControlSha256"]
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


def validate_original_references(value):
    """Validate locators only; caller authenticates the enclosing upload first."""
    from products.receipt import validate_phase_receipt
    from products.registry import PHASE_INSTANCE_IDS, PhaseInstanceId
    value = require_exact_keys(value, {"schemaVersion", "inventory", "sources", "references"},
                               "Runtime original references")
    if value["schemaVersion"] != 1 or type(value["schemaVersion"]) is not int:
        raise ValueError("Unsupported Runtime original references schema")
    inventory = require_sorted_unique_records(value["inventory"], "Original reference inventory")
    if not inventory or len(inventory) > 16_384:
        raise ValueError("Original reference inventory exceeds its fixed bound")
    files = {}
    for record in inventory:
        validate_file_record(record, "Original reference file", with_kind=False, allow_empty=True)
        if record["relativePath"].split("/")[0] not in {"product-resume-inputs", "product-resume-state"}:
            raise ValueError("Original reference inventory has unexpected roots")
        files[_path(record["relativePath"])] = record
    if (sum(row["bytes"] for row in inventory) > 16 * 1024**3
            or any(row["bytes"] > 8 * 1024**3 for row in inventory)):
        raise ValueError("Original reference inventory exceeds the transport byte bounds")
    sources = require_sorted_unique_records(value["sources"], "Original reference sources")
    if len(sources) > 47:
        raise ValueError("Original references exceed the registered Runtime source bound")
    by_source = {}
    for source in sources:
        require_exact_keys(source, {"relativePath", "kind", "receipt", "artifactId", "artifactSha256"},
                           "Original reference source")
        receipt = validate_phase_receipt(source["receipt"])
        instance = PhaseInstanceId(*(receipt[key] for key in ("product", "component", "phase", "target")))
        if instance not in PHASE_INSTANCE_IDS or instance.product != "runtime":
            raise ValueError("Original reference is not a registered Runtime phase")
        if source["kind"] == "phase":
            prefix = (f"product-resume-state/prior-failed-runtime/{instance.component}/{instance.phase}/"
                      f"{instance.target}/phases/{instance.phase}/original")
        elif source["kind"] == "aggregate" and instance == PhaseInstanceId(
                "runtime", "runtime-aggregate", "metadata", "aggregate"):
            from products.inventory import canonical_json_bytes, sha256_bytes
            prefix = ("product-resume-state/runtime-aggregate-release-evidence/0/handoffs/"
                      + sha256_bytes(canonical_json_bytes(receipt))[7:])
        else:
            raise ValueError("Original reference source kind differs from its phase")
        if source["relativePath"] != prefix:
            raise ValueError("Original reference source changes its registered destination")
        require_integer(source["artifactId"], "Original reference upload ID", 1)
        require_sha256(source["artifactSha256"], "Original reference upload SHA")
        by_source[prefix] = source
    references = require_sorted_unique_records(value["references"], "Original member references")
    mappings = {row["relativePath"]: row for row in references}
    targets = {row["relativePath"] for row in references}
    if not references:
        raise ValueError("Original reference transport has no references")
    used = set()
    for row in references:
        require_exact_keys(row, {"relativePath", "source", "sourcePath", "bytes", "sha256"},
                           "Original member reference")
        target = _path(row["relativePath"])
        if {key: row[key] for key in ("relativePath", "bytes", "sha256")} != files.get(target):
            raise ValueError("Original member reference changes its qualified inventory")
        source_path = require_relative_path(row["sourcePath"], "Original reference member")
        if row["source"] is None:
            source = files.get(_path(source_path))
            if (source_path in targets or source is None
                    or any(source[key] != row[key] for key in ("bytes", "sha256"))):
                raise ValueError("Local reference is missing, cyclic or changes byte identity")
        else:
            prefix = _path(row["source"])
            primary = prefix + "/" + source_path
            primary_file = files.get(primary)
            primary_reference = mappings.get(primary)
            if (prefix not in by_source or primary_file is None or primary_reference is None
                    or primary_reference.get("source") != prefix
                    or primary_reference.get("sourcePath") != source_path
                    or any(primary_file[key] != row[key] for key in ("bytes", "sha256"))):
                raise ValueError("Original member reference changes its registered source path")
            if by_source[prefix]["kind"] == "phase" and source_path.startswith("inputs/"):
                raise ValueError("Original phase reference includes unretained predecessor inputs")
            used.add(prefix)
    if used != set(by_source):
        raise ValueError("Original reference transport has unused source locators")
    return value


def stage_original_reference_handoff(roots, sources, destination):
    """Keep one concrete copy of local bytes; leave immutable originals upstream."""
    if set(roots) != {"product-resume-inputs", "product-resume-state"}:
        raise ValueError("Initial original references require both original roots")
    inventory, paths = [], {}
    for name, root in roots.items():
        if name not in {"product-resume-inputs", "product-resume-state"}:
            raise ValueError("Initial original reference has unexpected roots")
        for row in regular_file_inventory(root, allow_empty=True):
            path = name + "/" + row["relativePath"]
            inventory.append({**row, "relativePath": path})
            paths[path] = Path(root) / row["relativePath"]
    inventory.sort(key=lambda row: row["relativePath"])
    upstream = {}
    for row in inventory:
        prefix = next((source["relativePath"] for source in sources
                       if row["relativePath"].startswith(source["relativePath"] + "/")), None)
        if prefix is not None:
            upstream.setdefault((row["bytes"], row["sha256"]),
                                (prefix, row["relativePath"][len(prefix) + 1:]))
    references, concrete, contents, used = [], [], {}, set()
    for row in inventory:
        prefix = next((source["relativePath"] for source in sources
                       if row["relativePath"].startswith(source["relativePath"] + "/")), None)
        identity = row["bytes"], row["sha256"]
        if prefix is not None:
            references.append({**row, "source": prefix,
                               "sourcePath": row["relativePath"][len(prefix) + 1:]})
            used.add(prefix)
        elif identity in upstream:
            source, path = upstream[identity]
            references.append({**row, "source": source, "sourcePath": path})
            used.add(source)
        elif identity in contents:
            references.append({**row, "source": None, "sourcePath": contents[identity]})
        else:
            concrete.append(row)
            contents[identity] = row["relativePath"]
    value = validate_original_references({"schemaVersion": 1, "inventory": inventory,
        "sources": sorted((source for source in sources if source["relativePath"] in used),
                          key=lambda row: row["relativePath"]), "references": references})
    with tempfile.TemporaryDirectory(prefix="runtime-original-reference-export-") as temporary:
        prepared = Path(temporary).resolve() / "handoff"
        prepared.mkdir()
        for row in concrete:
            _copy_exact(paths[row["relativePath"]], prepared / row["relativePath"], row)
        write_canonical_json(prepared / ORIGINAL_REFERENCE_NAME, value)
        after = sorted(({**row, "relativePath": name + "/" + row["relativePath"]}
                        for name, root in roots.items()
                        for row in regular_file_inventory(root, allow_empty=True)),
                       key=lambda row: row["relativePath"])
        if after != inventory:
            raise ValueError("Original reference export inputs changed")
        publish_regular_tree(prepared, destination, allow_empty=True)
    return value


def resolve_original_reference_handoff(original, value, capture_source):
    """Resolve qualified members, then let existing admission replay authenticate phases."""
    value = validate_original_references(value)
    targets = {row["relativePath"] for row in value["references"]}
    if regular_file_inventory(original, allow_empty=True, excluded_paths=(ORIGINAL_REFERENCE_NAME,)) != [
            row for row in value["inventory"] if row["relativePath"] not in targets]:
        raise ValueError("Original reference delta has missing, overlapping or unexpected files")
    for source in value["sources"]:
        capture_source(source, [row for row in value["references"] if row["source"] == source["relativePath"]],
                       Path(original))
    for row in value["references"]:
        if row["source"] is None:
            _copy_exact(Path(original) / row["sourcePath"], Path(original) / row["relativePath"], row)
    if regular_file_inventory(original, allow_empty=True, excluded_paths=(ORIGINAL_REFERENCE_NAME,)) != value["inventory"]:
        raise ValueError("Resolved original reference inventory differs from its frozen bytes")
    (Path(original) / ORIGINAL_REFERENCE_NAME).unlink()
    return value["inventory"]
