"""Content checks for a separately authenticated original ARM64 supervisor.

No record here authenticates a producer or transport. The caller must capture
the exact original upload under its existing run/job/artifact authority first.
"""
from __future__ import annotations

import os
from pathlib import Path
import struct
from typing import Any

from products.inventory import (
    canonical_json_bytes, git_regular_blob_bytes, load_canonical_json_bytes,
    read_regular_file_bytes, regular_file_inventory, require_exact_keys,
    require_integer, require_regular_directory, run_git, sha256_bytes,
)
from products.receipt import validate_producer
from products.runtime_identity import verify_runtime_binary_plan
from products.toolchain import _verification_record, validate_verification_record


TASK = ":codex-agent-runtime-desktop:compileDesktopProcessSupervisor"
SOURCE = "codex-agent-runtime-desktop/native/supervisor/codex_process_supervisor.c"
EXECUTABLE = "linuxArm64/codex-process-supervisor"
_LIMITS = {
    "runtime-binary-plan.json": 16 * 1024 * 1024,
    "toolchain-verification.json": 1024 * 1024,
    "source/codex_process_supervisor.c": 1024 * 1024,
    EXECUTABLE: 16 * 1024 * 1024,
    "gradle.log": 64 * 1024 * 1024,
    "execution.json": 1024 * 1024,
}


def _capture(root: Path) -> dict[str, bytes]:
    if not root.is_absolute() or Path(os.path.normpath(root)) != root:
        raise ValueError("Supervisor handoff root must be absolute and normalized")
    require_regular_directory(root, "Supervisor handoff")
    files, directories = set(), set()
    for current, children, names in os.walk(root, followlinks=False):
        relative = Path(current).relative_to(root)
        directories.update((relative / name).as_posix() for name in children)
        files.update((relative / name).as_posix() for name in names)
    if files != set(_LIMITS) or directories != {"source", "linuxArm64"}:
        raise ValueError("Supervisor handoff must contain exactly its declared original files")
    contents = {name: read_regular_file_bytes(root / name, max_bytes=limit, reject_symlink_parents=True)
                for name, limit in _LIMITS.items()}
    if any(not data for name, data in contents.items() if name != "gradle.log"):
        raise ValueError("Supervisor handoff has an empty required output")
    return contents


def _verify_arm64_executable(data: bytes) -> None:
    # Header/segment checks establish architecture, not execution or provenance.
    if len(data) < 64 or data[:7] != b"\x7fELF\x02\x01\x01":
        raise ValueError("Supervisor must be a Linux ELF64 little-endian ARM64 executable")
    kind, machine, version, entry, program_offset = struct.unpack_from("<HHIQQ", data, 16)
    header_size, program_size, program_count = struct.unpack_from("<HHH", data, 52)
    if (kind not in {2, 3} or machine != 183 or version != 1 or header_size != 64
            or program_size != 56 or not program_count or program_offset < 64
            or program_offset + program_count * program_size > len(data)):
        raise ValueError("Supervisor ELF architecture or program headers are invalid")
    executable_entry = False
    for index in range(program_count):
        segment, flags, offset, address, _, size, memory, _ = struct.unpack_from(
            "<IIQQQQQQ", data, program_offset + index * program_size)
        if segment == 1:
            if size > memory or offset + size > len(data):
                raise ValueError("Supervisor ELF load segment exceeds its original bytes")
            executable_entry |= bool(flags & 1 and address <= entry < address + size)
    if not executable_entry:
        raise ValueError("Supervisor ELF lacks a file-backed executable entry point")


def verify_supervisor_handoff(
    root: Path, *, repository_root: Path, revision: str, phase_plan: dict[str, Any],
    contract_manifest: dict[str, Any], producer: dict[str, Any], runtime_version: str,
) -> dict[str, Any]:
    """Return ordinary content data, never a producer/admission capability.

    All claims are checked against the caller's independently authenticated
    original producer and elected plan. Original bytes are never rewritten.
    """
    root = Path(root)
    captured = _capture(root)
    original = validate_producer(producer)
    if original["commit"] != revision or original["tree"] != run_git(
            repository_root, "rev-parse", f"{revision}^{{tree}}").strip():
        raise ValueError("Supervisor original producer differs from the exact Git revision/tree")
    saved_plan = load_canonical_json_bytes(captured["runtime-binary-plan.json"])
    if captured["runtime-binary-plan.json"] != canonical_json_bytes(phase_plan):
        raise ValueError("Supervisor full binary plan differs from the elected original plan")
    verify_runtime_binary_plan(
        repository_root, revision, saved_plan, contract_manifest,
        expected_target="linux-arm64", expected_runtime_version=runtime_version,
        expected_flags_digest=saved_plan["inputs"]["flagsDigest"])
    execution = require_exact_keys(load_canonical_json_bytes(captured["execution.json"]), {
        "schemaVersion", "kind", "producer", "buildKey", "task", "host",
        "returnCode", "elapsedNs", "files",
    }, "Supervisor raw execution")
    validate_producer(execution["producer"], "Supervisor execution producer")
    if (type(execution["schemaVersion"]) is not int or execution["schemaVersion"] != 1
            or execution["kind"] != "runtime-supervisor-execution"
            or canonical_json_bytes(execution["producer"]) != canonical_json_bytes(original)
            or execution["buildKey"] != saved_plan["buildKey"]
            or execution["task"] != TASK or execution["host"] != "linux-arm64"
            or type(execution["returnCode"]) is not int or execution["returnCode"] != 0):
        raise ValueError("Supervisor original execution identity or successful result is invalid")
    require_integer(execution["elapsedNs"], "Supervisor elapsed nanoseconds", 0)
    inventory = [{"relativePath": name, "bytes": len(data), "sha256": sha256_bytes(data)}
                 for name, data in sorted(captured.items()) if name != "execution.json"]
    if canonical_json_bytes(execution["files"]) != canonical_json_bytes(inventory):
        raise ValueError("Supervisor execution inventory differs from its exact original bytes")
    source = git_regular_blob_bytes(repository_root, revision, SOURCE, max_bytes=_LIMITS["source/codex_process_supervisor.c"])
    if captured["source/codex_process_supervisor.c"] != source or not any(
            item["relativePath"] == SOURCE and item["sha256"] == sha256_bytes(source)
            and item["bytes"] == len(source) for item in saved_plan["inputs"]["inventory"]):
        raise ValueError("Supervisor source is not the exact original keyed Git source")
    record = validate_verification_record(load_canonical_json_bytes(captured["toolchain-verification.json"]))
    if (record["profileId"] != "linux-arm64" or record["producer"]["role"] != "supervisor-builder"
            or record["producer"]["runner"] != {"os": "Linux", "arch": "ARM64"}):
        raise ValueError("Supervisor observation must identify the Linux ARM64 supervisor builder")
    observation = {key: value for key, value in record.items() if key != "profileDigest"}
    if _verification_record(repository_root, revision, saved_plan, observation) != record:
        raise ValueError("Supervisor toolchain observation differs from original profile authority")
    _verify_arm64_executable(captured[EXECUTABLE])
    if _capture(root) != captured or regular_file_inventory(root, allow_empty=True) != [
            {"relativePath": name, "bytes": len(data), "sha256": sha256_bytes(data)}
            for name, data in sorted(captured.items())]:
        raise ValueError("Supervisor original handoff changed during verification")
    return {"executable": root / EXECUTABLE, "sha256": sha256_bytes(captured[EXECUTABLE]),
            "bytes": len(captured[EXECUTABLE]), "execution": execution}
