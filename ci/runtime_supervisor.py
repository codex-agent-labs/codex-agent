"""Content checks for a separately authenticated original ARM64 supervisor.

No record here authenticates a producer or transport. The caller must capture
the exact original upload under its existing run/job/artifact authority first.
"""
from __future__ import annotations

import os
from pathlib import Path
import struct
import subprocess
import tempfile
import time
from typing import Any

from products.inventory import (
    canonical_json_bytes, git_regular_blob_bytes, load_canonical_json_bytes,
    read_regular_file_bytes, regular_file_inventory, require_exact_keys,
    require_integer, require_regular_directory, run_git, sha256_bytes,
    publish_regular_tree, snapshot_regular_tree, write_canonical_json,
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


def execute_supervisor(
    *, repository_root: Path, producer: dict[str, Any], properties: dict[str, str],
    phase_plan: dict[str, Any], contract_manifest: dict[str, Any], runtime_version: str,
    destination: Path, environ: dict[str, str],
) -> dict[str, Any]:
    """Run the sole existing Gradle producer after the root's authenticated replay.

    This entry has no caller-selected command, observer, executor or success
    result. Transport authentication remains separate from local execution.
    """
    from native_wrappers import host_classifier
    from product_reuse import (
        _prepare_destination, _runtime_worker_checkout,
        _runtime_worker_command, _runtime_worker_environment,
    )

    root = Path(repository_root).resolve()
    original = validate_producer(producer)
    if host_classifier() != "linux-arm64":
        raise ValueError("Supervisor production requires the actual Linux ARM64 host")
    verify_runtime_binary_plan(
        root, original["commit"], phase_plan, contract_manifest,
        expected_target="linux-arm64", expected_runtime_version=runtime_version,
        expected_flags_digest=phase_plan["inputs"]["flagsDigest"])
    fixed = {
        "codexAgent.product": "runtime", "codexAgent.component": "linux-arm64",
        "codexAgent.phase": "binary", "codexAgent.target": "linux-arm64",
        "codexAgent.runtimeVersion": runtime_version,
        "codexAgent.contractVersion": contract_manifest["contractVersion"],
        "codexAgent.candidateCommit": original["commit"], "codexAgent.candidateTree": original["tree"],
        "codexAgent.repositoryRevision": original["commit"],
        "codexAgent.runtimeBinaryFlagsDigest": phase_plan["inputs"]["flagsDigest"],
    }
    paths = {"codexAgent.runtimeBinaryPlan", "codexAgent.contractPayload",
             "codexAgent.contractMetadataReceipt", "codexAgent.contractAttestation",
             "codexAgent.contractAttestationSignature", "codexAgent.contractPublicKey"}
    require_exact_keys(properties, set(fixed) | paths, "Prepared supervisor properties")
    if any(properties[key] != value for key, value in fixed.items()):
        raise ValueError("Supervisor properties differ from authenticated source/plan/version")
    input_paths = {}
    for key in paths:
        value = properties[key]
        if type(value) is not str or not value or not Path(value).is_absolute() or os.path.normpath(value) != value:
            raise ValueError("Supervisor prepared inputs must be absolute normalized paths")
        path = Path(value)
        read_regular_file_bytes(path, reject_symlink_parents=True, max_bytes=512 * 1024 * 1024)
        input_paths[key] = path
    inputs = input_paths["codexAgent.runtimeBinaryPlan"].parent
    if inputs == root or root not in inputs.parents or any(inputs not in path.parents for path in input_paths.values()):
        raise ValueError("Supervisor requires one private prepared input tree inside the repository")
    if read_regular_file_bytes(input_paths["codexAgent.runtimeBinaryPlan"]) != canonical_json_bytes(phase_plan):
        raise ValueError("Supervisor prepared full binary plan differs from the elected plan")
    input_inventory = regular_file_inventory(inputs, allow_empty=True)
    real_inputs = inputs.resolve(strict=True)
    destination = Path(destination)
    diagnostics = destination.with_name(destination.name + "-diagnostics")
    output_directory = root / "codex-agent-runtime-desktop/build/supervisor/linuxArm64"
    toolchain_file = root / "codex-agent-runtime-desktop/build/toolchain-verification/linux-arm64-supervisor-builder.json"
    outputs = (destination, diagnostics, output_directory, toolchain_file)
    for path in outputs:
        if not path.is_absolute() or Path(os.path.normpath(path)) != path or root not in path.parents:
            raise ValueError("Supervisor output must be an absolute normalized repository path")
        if path.exists() or path.is_symlink():
            raise ValueError("Supervisor refuses a pre-existing output or diagnostic path")
        for parent in path.parents:
            if parent.exists() or parent.is_symlink():
                require_regular_directory(parent, "Supervisor output ancestor")
        resolved = path.resolve(strict=False)
        if resolved == real_inputs or resolved in real_inputs.parents or real_inputs in resolved.parents:
            raise ValueError("Supervisor outputs overlap original prepared inputs")
    for index, left in enumerate(outputs):
        for right in outputs[index + 1:]:
            if left == right or left in right.parents or right in left.parents:
                raise ValueError("Supervisor output scopes overlap")
    environment, wrapper = _runtime_worker_environment(root, original, diagnostics, environ)
    _prepare_destination(destination, root).rmdir()
    diagnostics = _prepare_destination(diagnostics, root)
    private_inputs = diagnostics / "inputs"
    snapshot_regular_tree(inputs, private_inputs, allow_empty=True)
    if input_inventory != regular_file_inventory(private_inputs, allow_empty=True):
        raise ValueError("Supervisor private inputs differ from authenticated originals")
    selected = {key: str(private_inputs / input_paths[key].relative_to(inputs)) if key in paths else value
                for key, value in properties.items()
                if key not in {"codexAgent.product", "codexAgent.component", "codexAgent.phase"}}
    command = _runtime_worker_command(wrapper, selected, environment)
    if command.count("ciProductPhase") != 1:
        raise ValueError("Supervisor worker command no longer has the fixed phase task")
    command[command.index("ciProductPhase")] = TASK
    _runtime_worker_checkout(root, original)
    if output_directory.exists() or output_directory.is_symlink() or toolchain_file.exists() or toolchain_file.is_symlink():
        raise ValueError("Supervisor output appeared before execution")
    started = time.monotonic_ns()
    with (diagnostics / "gradle.log").open("xb") as log:
        completed = subprocess.run(command, cwd=root, env=environment, stdout=log,
                                   stderr=subprocess.STDOUT, check=False)
    elapsed = time.monotonic_ns() - started
    write_canonical_json(diagnostics / "process.json", {
        "schemaVersion": 1, "producer": original, "buildKey": phase_plan["buildKey"],
        "command": command, "host": "linux-arm64", "returnCode": completed.returncode, "elapsedNs": elapsed,
    })
    if completed.returncode != 0:
        raise ValueError(f"Supervisor task failed with exit code {completed.returncode}; see {diagnostics / 'gradle.log'}")
    _runtime_worker_checkout(root, original)
    if (diagnostics / "python-bytecode").exists() or (diagnostics / "python-bytecode").is_symlink():
        raise ValueError("Supervisor private Python bytecode namespace was modified")
    if any(regular_file_inventory(path, allow_empty=True) != input_inventory for path in (inputs, private_inputs)):
        raise ValueError("Supervisor original or private inputs changed during execution")
    executable = output_directory / "codex-process-supervisor"
    if [record["relativePath"] for record in regular_file_inventory(output_directory)] != [executable.name]:
        raise ValueError("Supervisor producer output directory must contain exactly one executable")
    originals = {
        "runtime-binary-plan.json": input_paths["codexAgent.runtimeBinaryPlan"],
        "toolchain-verification.json": toolchain_file,
        "source/codex_process_supervisor.c": root / SOURCE,
        EXECUTABLE: executable, "gradle.log": diagnostics / "gradle.log",
    }
    captured = {name: read_regular_file_bytes(path, max_bytes=_LIMITS[name], reject_symlink_parents=True)
                for name, path in originals.items()}
    with tempfile.TemporaryDirectory(prefix="supervisor-handoff-", dir=diagnostics) as temporary:
        staged = Path(temporary).resolve()
        for name, data in captured.items():
            path = staged / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        write_canonical_json(staged / "execution.json", {
            "schemaVersion": 1, "kind": "runtime-supervisor-execution", "producer": original,
            "buildKey": phase_plan["buildKey"], "task": TASK, "host": "linux-arm64",
            "returnCode": completed.returncode, "elapsedNs": elapsed,
            "files": regular_file_inventory(staged, allow_empty=True),
        })
        result = verify_supervisor_handoff(staged, repository_root=root, revision=original["commit"],
                                           phase_plan=phase_plan, contract_manifest=contract_manifest,
                                           producer=original, runtime_version=runtime_version)
        if any(read_regular_file_bytes(path, max_bytes=_LIMITS[name], reject_symlink_parents=True) != captured[name]
               for name, path in originals.items()):
            raise ValueError("Supervisor original outputs changed during capture")
        _runtime_worker_checkout(root, original)
        if any(regular_file_inventory(path, allow_empty=True) != input_inventory for path in (inputs, private_inputs)):
            raise ValueError("Supervisor original or private inputs changed before publication")
        publish_regular_tree(staged, destination, allow_empty=True)
    return {**result, "executable": destination / EXECUTABLE}
