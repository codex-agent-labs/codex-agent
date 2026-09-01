from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import io
from pathlib import Path
import re
import stat
import sys
from typing import Any, Iterable, Mapping
import xml.etree.ElementTree as ET
import zipfile

from .inventory import load_json, load_json_bytes, read_regular_file_bytes, write_canonical_json
from .test_results import read_canonical_test_report, read_canonical_test_results


SHA256 = re.compile(r"[0-9a-f]{64}\Z")
COMMIT = re.compile(r"[0-9a-f]{40}\Z")
LIBRARY_VERSION = re.compile(r"[A-Za-z0-9._-]+\Z")
MAVEN_GROUP_PATH = "io/github/codex-agent-labs"
LINUX_ARM64_RUNTIME_EVIDENCE_TASK = ":build-logic:executeLinuxArm64RuntimeEvidenceBundle"
DESKTOP_RUNTIME_TEST_CLASS = (
    "io.github.codex_agent_labs.codexagent.appserver.runtime.DesktopCodexRuntimeTest"
)
DESKTOP_RUNTIME_TEST_METHODS = (
    "closeDuringStartClosesNewProcessExactlyOnce",
    "initializesAndShutsDownOfficialAppServerWhenProvided",
    "rejectsRelativeExecutableBeforeStarting",
    "rejectsWrongTargetChecksum",
)
JVM_RUNTIME_RUNNER_ARCHIVE = "codex-agent-jvm-runtime-evidence-runner.zip"
JVM_RUNTIME_RUNNER_ENTRYPOINT = (
    "io.github.codex_agent_labs.codexagent.appserver.runtime.JvmRuntimeEvidenceMain"
)
IMPORTED_JVM_RUNTIME_EVIDENCE_TASK = (
    ":codex-agent-runtime-desktop:executeImportedJvmRuntimeEvidence"
)
PINNED_NODE_VERSION = "24.18.0"
NODE_RUNTIME_JS_BACKEND = "js"
NODE_RUNTIME_WASM_BACKEND = "wasm"
NODE_RUNTIME_TEST_CLASS = (
    "io.github.codex_agent_labs.codexagent.appserver.runtime.NodeCodexRuntimeTest"
)
NODE_RUNTIME_TEST_METHODS = DESKTOP_RUNTIME_TEST_METHODS
NODE_RUNTIME_RUNNER_ARCHIVE = "codex-agent-node-runtime-evidence-runner.zip"
NODE_RUNTIME_RUNNER_ENTRY = "codex-agent-codex-agent-runtime-desktop.js"
NODE_WASM_RUNTIME_RUNNER_ARCHIVE = "codex-agent-node-wasm-runtime-evidence-runner.zip"
NODE_WASM_RUNTIME_RUNNER_ENTRIES = frozenset(
    {
        "codex-agent-codex-agent-runtime-desktop.mjs",
        "codex-agent-codex-agent-runtime-desktop.uninstantiated.mjs",
        "codex-agent-codex-agent-runtime-desktop.wasm",
        "custom-formatters.js",
    }
)


@dataclass(frozen=True)
class RuntimeTarget:
    classifier: str
    runner_os: str
    runner_arch: str


RUNTIME_TARGETS: dict[str, RuntimeTarget] = {
    "macosArm64": RuntimeTarget("app-server-macos-arm64", "macOS", "ARM64"),
    "macosX64": RuntimeTarget("app-server-macos-x64", "macOS", "X64"),
    "linuxArm64": RuntimeTarget("app-server-linux-arm64", "Linux", "ARM64"),
    "linuxX64": RuntimeTarget("app-server-linux-x64", "Linux", "X64"),
    "mingwX64": RuntimeTarget("app-server-windows-x64", "Windows", "X64"),
}


@dataclass(frozen=True)
class Distribution:
    target: str
    classifier: str
    asset: str
    archive_sha256: str
    archive_entry: str
    binary_sha256: str
    executable_name: str
    supervisor_executable_name: str


@dataclass(frozen=True)
class DistributionManifest:
    version: str
    release_tag: str
    distributions: tuple[Distribution, ...]


@dataclass(frozen=True)
class ClassifierProof:
    target: str
    classifier: str
    library_version: str
    archive_file: Path
    archive_sha256: str
    archive_bytes: int
    executable_name: str
    binary_sha256: str
    supervisor_executable_name: str
    supervisor_sha256: str


def distribution_manifest_projection(manifest: DistributionManifest) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "version": manifest.version,
        "releaseTag": manifest.release_tag,
        "distributions": [
            {
                "target": record.target,
                "classifier": record.classifier,
                "asset": record.asset,
                "archiveSha256": record.archive_sha256,
                "archiveEntry": record.archive_entry,
                "binarySha256": record.binary_sha256,
                "executableName": record.executable_name,
                "supervisorExecutableName": record.supervisor_executable_name,
            }
            for target in RUNTIME_TARGETS
            for record in manifest.distributions
            if record.target == target
        ],
    }


def _object(value: Any, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise ValueError(f"{label} must be an object")
    return value


def _array(value: Any, label: str) -> list[Any]:
    if type(value) is not list:
        raise ValueError(f"{label} must be an array")
    return value


def _string(value: Any, label: str) -> str:
    if type(value) is not str:
        raise ValueError(f"{label} must be a string")
    return value


def _integer(value: Any, label: str) -> int:
    if type(value) is not int:
        raise ValueError(f"{label} must be an integer")
    return value


def _boolean(value: Any, label: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{label} must be a boolean")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise ValueError(f"{label} schema fields mismatch")


def _safe_basename(value: str, label: str) -> str:
    if (
        not value
        or value in {".", ".."}
        or "/" in value
        or "\\" in value
        or ":" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
        or Path(value).name != value
    ):
        raise ValueError(f"{label} is unsafe")
    return value


def _hex(value: Any, pattern: re.Pattern[str], label: str) -> str:
    text = _string(value, label)
    if not pattern.fullmatch(text):
        raise ValueError(f"{label} is invalid")
    return text


def _sha256_bytes(contents: bytes) -> str:
    return hashlib.sha256(contents).hexdigest()


def _file_bytes(path: Path) -> bytes:
    contents = read_regular_file_bytes(Path(path))
    if not contents:
        raise ValueError(f"File is empty: {path}")
    return contents


def _zip_member_is_symlink(info: zipfile.ZipInfo) -> bool:
    return stat.S_IFMT(info.external_attr >> 16) == stat.S_IFLNK


def _zip_entries(path: Path, *, root_only: bool) -> tuple[bytes, zipfile.ZipFile, list[zipfile.ZipInfo]]:
    contents = _file_bytes(path)
    archive = zipfile.ZipFile(io.BytesIO(contents))
    try:
        entries = archive.infolist()
        names = [entry.filename for entry in entries]
        if not entries or len(names) != len(set(names)) or any(entry.is_dir() for entry in entries):
            raise ValueError("Archive has invalid or duplicate members")
        for entry in entries:
            parts = entry.filename.split("/")
            if (
                _zip_member_is_symlink(entry)
                or "\\" in entry.filename
                or ":" in entry.filename
                or any(ord(character) < 32 or ord(character) == 127 for character in entry.filename)
                or any(not part or part in {".", ".."} for part in parts)
                or (root_only and len(parts) != 1)
            ):
                raise ValueError(f"Archive contains unsafe member: {entry.filename}")
            if not archive.read(entry):
                raise ValueError(f"Archive member is empty: {entry.filename}")
        return contents, archive, entries
    except Exception:
        archive.close()
        raise


def read_distribution_manifest(path: Path) -> DistributionManifest:
    root = _object(load_json(Path(path)), "Desktop distribution manifest")
    _exact_keys(root, {"version", "releaseTag", "distributions"}, "Desktop distribution manifest")
    version = _string(root["version"], "Desktop version")
    release_tag = _string(root["releaseTag"], "Desktop release tag")
    if release_tag != f"rust-v{version}":
        raise ValueError("Desktop release tag/version mismatch")
    records: list[Distribution] = []
    keys = {
        "target", "classifier", "asset", "archiveSha256", "archiveEntry", "binarySha256",
        "executableName", "supervisorExecutableName",
    }
    for index, raw in enumerate(_array(root["distributions"], "Desktop distributions")):
        record = _object(raw, f"Desktop distribution {index}")
        _exact_keys(record, keys, f"Desktop distribution {index}")
        distribution = Distribution(
            target=_string(record["target"], "target"),
            classifier=_string(record["classifier"], "classifier"),
            asset=_safe_basename(_string(record["asset"], "asset"), "asset"),
            archive_sha256=_hex(record["archiveSha256"], SHA256, "archive SHA-256"),
            archive_entry=_safe_basename(_string(record["archiveEntry"], "archiveEntry"), "archiveEntry"),
            binary_sha256=_hex(record["binarySha256"], SHA256, "binary SHA-256"),
            executable_name=_safe_basename(_string(record["executableName"], "executableName"), "executableName"),
            supervisor_executable_name=_safe_basename(
                _string(record["supervisorExecutableName"], "supervisorExecutableName"),
                "supervisorExecutableName",
            ),
        )
        records.append(distribution)
    if (
        len(records) != 5
        or {record.target for record in records} != set(RUNTIME_TARGETS)
        or len({record.classifier for record in records}) != 5
    ):
        raise ValueError("Desktop distribution manifest must contain the exact five unique targets/classifiers")
    return DistributionManifest(version, release_tag, tuple(records))


def inspect_classifier(target: str, manifest: DistributionManifest, archive_path: Path) -> ClassifierProof:
    expected = RUNTIME_TARGETS.get(target)
    if expected is None:
        raise ValueError(f"Unsupported Runtime target: {target}")
    distribution = next(record for record in manifest.distributions if record.target == target)
    if distribution.classifier != expected.classifier:
        raise ValueError(f"Classifier identity mismatch for {target}")
    archive_path = Path(archive_path)
    if not (
        archive_path.name == f"{expected.classifier}.zip"
        or archive_path.name.endswith(f"-{expected.classifier}.zip")
    ):
        raise ValueError(f"Classifier archive filename mismatch for {target}")
    archive_contents, archive, entries = _zip_entries(archive_path, root_only=True)
    try:
        expected_names = {
            distribution.executable_name,
            distribution.supervisor_executable_name,
            "openai-codex-LICENSE.txt",
            "openai-codex-NOTICE.txt",
            "codex-runtime-manifest.json",
        }
        by_name = {entry.filename: entry for entry in entries}
        if set(by_name) != expected_names or len(by_name) != len(expected_names):
            raise ValueError(f"Classifier member set mismatch for {target}")
        runtime_manifest = _object(
            load_json_bytes(archive.read("codex-runtime-manifest.json")),
            "Classifier runtime manifest",
        )
        _exact_keys(
            runtime_manifest,
            {"schemaVersion", "libraryVersion", "appServerVersion", "target", "classifier", "members"},
            "Classifier runtime manifest",
        )
        library_version = _string(runtime_manifest["libraryVersion"], "libraryVersion")
        if (
            _integer(runtime_manifest["schemaVersion"], "schemaVersion") != 1
            or runtime_manifest["appServerVersion"] != manifest.version
            or runtime_manifest["target"] != target
            or runtime_manifest["classifier"] != distribution.classifier
            or not LIBRARY_VERSION.fullmatch(library_version)
        ):
            raise ValueError(f"Classifier runtime manifest identity is invalid for {target}")
        payload = {name: archive.read(name) for name in expected_names - {"codex-runtime-manifest.json"}}
        members: dict[str, dict[str, Any]] = {}
        for raw in _array(runtime_manifest["members"], "Classifier members"):
            member = _object(raw, "Classifier member")
            _exact_keys(member, {"name", "size", "sha256", "executable"}, "Classifier member")
            name = _safe_basename(_string(member["name"], "member name"), "member name")
            if name in members:
                raise ValueError("Classifier runtime manifest has duplicate members")
            members[name] = member
        if set(members) != set(payload):
            raise ValueError(f"Classifier runtime manifest members are invalid for {target}")
        executables = {distribution.executable_name, distribution.supervisor_executable_name}
        for name, contents in payload.items():
            member = members[name]
            if (
                _integer(member["size"], f"{name} size") != len(contents)
                or _hex(member["sha256"], SHA256, f"{name} SHA-256") != _sha256_bytes(contents)
                or _boolean(member["executable"], f"{name} executable") != (name in executables)
            ):
                raise ValueError(f"Classifier runtime manifest payload is invalid for {target}")
        binary_sha256 = _sha256_bytes(payload[distribution.executable_name])
        supervisor_sha256 = _sha256_bytes(payload[distribution.supervisor_executable_name])
    finally:
        archive.close()
    if binary_sha256 != distribution.binary_sha256:
        raise ValueError(f"App Server hash is not pinned for {target}")
    return ClassifierProof(
        target=target,
        classifier=distribution.classifier,
        library_version=library_version,
        archive_file=archive_path,
        archive_sha256=_sha256_bytes(archive_contents),
        archive_bytes=len(archive_contents),
        executable_name=distribution.executable_name,
        binary_sha256=binary_sha256,
        supervisor_executable_name=distribution.supervisor_executable_name,
        supervisor_sha256=supervisor_sha256,
    )


def inspect_jvm_runner(path: Path) -> tuple[str, ...]:
    path = Path(path)
    if path.name != JVM_RUNTIME_RUNNER_ARCHIVE:
        raise ValueError("Compiled JVM runtime archive is missing or misnamed")
    _, archive, entries = _zip_entries(path, root_only=False)
    try:
        names = [entry.filename for entry in entries]
        if any(not (name.startswith("classes/") or name.startswith("lib/")) for name in names):
            raise ValueError("Compiled JVM runtime archive has an unsafe layout")
        entrypoint = f"classes/{JVM_RUNTIME_RUNNER_ENTRYPOINT.replace('.', '/')}.class"
        if entrypoint not in names or not any(name.startswith("lib/") and name.endswith(".jar") for name in names):
            raise ValueError("Compiled JVM runtime entrypoint or dependencies are missing")
        return tuple(sorted(names))
    finally:
        archive.close()


def _node_runner_name(backend: str) -> str:
    if backend == NODE_RUNTIME_JS_BACKEND:
        return NODE_RUNTIME_RUNNER_ARCHIVE
    if backend == NODE_RUNTIME_WASM_BACKEND:
        return NODE_WASM_RUNTIME_RUNNER_ARCHIVE
    raise ValueError(f"Unsupported Node runtime backend: {backend}")


def inspect_node_runner(path: Path, backend: str) -> tuple[str, ...]:
    path = Path(path)
    if path.name != _node_runner_name(backend):
        raise ValueError("Compiled Node runtime archive is missing or misnamed")
    _, archive, entries = _zip_entries(path, root_only=True)
    try:
        names = [entry.filename for entry in entries]
        if backend == NODE_RUNTIME_JS_BACKEND:
            if NODE_RUNTIME_RUNNER_ENTRY not in names or any(not name.endswith(".js") for name in names):
                raise ValueError("Compiled Node runtime JavaScript entry is missing or invalid")
        elif set(names) != set(NODE_WASM_RUNTIME_RUNNER_ENTRIES):
            raise ValueError("Compiled Node Wasm runtime archive member set is invalid")
        return tuple(sorted(names))
    finally:
        archive.close()


def desktop_evidence_filename(target: str) -> str:
    return f"desktop-runtime-{target}.json"


def desktop_test_task(target: str) -> str:
    return LINUX_ARM64_RUNTIME_EVIDENCE_TASK if target == "linuxArm64" else f":codex-agent-runtime-desktop:{target}Test"


def imported_desktop_test_task(target: str) -> str:
    return f":codex-agent-runtime-desktop:executeImported{target[0].upper()}{target[1:]}NativeRuntimeEvidence"


def build_desktop_evidence(
    candidate_commit: str,
    target: str,
    binary_sha256: str,
    supervisor_sha256: str,
    classifier_archive_sha256: str,
    *,
    test_task: str | None = None,
) -> dict[str, Any]:
    expected = RUNTIME_TARGETS[target]
    return {
        "schemaVersion": 3,
        "candidateCommit": candidate_commit,
        "target": target,
        "classifier": expected.classifier,
        "runnerOs": expected.runner_os,
        "runnerArch": expected.runner_arch,
        "testTask": test_task or desktop_test_task(target),
        "testClass": DESKTOP_RUNTIME_TEST_CLASS,
        "testMethods": list(DESKTOP_RUNTIME_TEST_METHODS),
        "tests": len(DESKTOP_RUNTIME_TEST_METHODS),
        "skipped": 0,
        "failures": 0,
        "errors": 0,
        "binarySha256": binary_sha256,
        "supervisorSha256": supervisor_sha256,
        "classifierArchiveSha256": classifier_archive_sha256,
        "result": "passed",
    }


def jvm_evidence_filename(target: str) -> str:
    return f"jvm-runtime-{target}.json"


def jvm_test_task(target: str) -> str:
    return LINUX_ARM64_RUNTIME_EVIDENCE_TASK if target == "linuxArm64" else ":codex-agent-runtime-desktop:jvmTest"


def build_jvm_evidence(
    candidate_commit: str,
    target: str,
    classifier: ClassifierProof,
    runner: Path,
    *,
    test_task: str | None = None,
) -> dict[str, Any]:
    expected = RUNTIME_TARGETS[target]
    if classifier.target != target or classifier.classifier != expected.classifier:
        raise ValueError(f"JVM evidence classifier does not match {target}")
    inspect_jvm_runner(runner)
    runner_contents = _file_bytes(runner)
    return {
        "schemaVersion": 1,
        "candidateCommit": candidate_commit,
        "target": target,
        "classifier": expected.classifier,
        "runnerOs": expected.runner_os,
        "runnerArch": expected.runner_arch,
        "testTask": test_task or jvm_test_task(target),
        "testClass": DESKTOP_RUNTIME_TEST_CLASS,
        "testMethods": list(DESKTOP_RUNTIME_TEST_METHODS),
        "tests": len(DESKTOP_RUNTIME_TEST_METHODS),
        "skipped": 0,
        "failures": 0,
        "errors": 0,
        "classifierArchiveFileName": classifier.archive_file.name,
        "classifierArchiveBytes": classifier.archive_bytes,
        "classifierArchiveSha256": classifier.archive_sha256,
        "appServerBinarySha256": classifier.binary_sha256,
        "supervisorBinarySha256": classifier.supervisor_sha256,
        "compiledJvmTestRuntimeFileName": JVM_RUNTIME_RUNNER_ARCHIVE,
        "compiledJvmTestRuntimeBytes": len(runner_contents),
        "compiledJvmTestRuntimeSha256": _sha256_bytes(runner_contents),
        "result": "passed",
    }


def node_evidence_filename(target: str, backend: str = NODE_RUNTIME_JS_BACKEND) -> str:
    _node_runner_name(backend)
    return f"node-runtime-{target}.json" if backend == NODE_RUNTIME_JS_BACKEND else f"node-wasm-runtime-{target}.json"


def node_test_task(target: str, backend: str) -> str:
    _node_runner_name(backend)
    if target == "linuxArm64":
        return LINUX_ARM64_RUNTIME_EVIDENCE_TASK
    prefix = "nodeRuntime" if backend == NODE_RUNTIME_JS_BACKEND else "nodeWasmRuntime"
    return f":codex-agent-runtime-desktop:{prefix}{target[0].upper()}{target[1:]}Test"


def build_node_evidence(
    candidate_commit: str,
    target: str,
    backend: str,
    classifier: ClassifierProof,
    runner: Path,
) -> dict[str, Any]:
    expected = RUNTIME_TARGETS[target]
    if classifier.target != target or classifier.classifier != expected.classifier:
        raise ValueError(f"Node evidence classifier does not match {target}")
    inspect_node_runner(runner, backend)
    runner_contents = _file_bytes(runner)
    return {
        "schemaVersion": 2,
        "candidateCommit": candidate_commit,
        "target": target,
        "runtimeBackend": backend,
        "classifier": expected.classifier,
        "runnerOs": expected.runner_os,
        "runnerArch": expected.runner_arch,
        "nodeVersion": PINNED_NODE_VERSION,
        "testTask": node_test_task(target, backend),
        "testClass": NODE_RUNTIME_TEST_CLASS,
        "testMethods": list(NODE_RUNTIME_TEST_METHODS),
        "tests": len(NODE_RUNTIME_TEST_METHODS),
        "skipped": 0,
        "failures": 0,
        "errors": 0,
        "classifierArchiveFileName": classifier.archive_file.name,
        "classifierArchiveBytes": classifier.archive_bytes,
        "classifierArchiveSha256": classifier.archive_sha256,
        "appServerBinarySha256": classifier.binary_sha256,
        "processSupervisorSha256": classifier.supervisor_sha256,
        "compiledNodeTestRuntimeFileName": Path(runner).name,
        "compiledNodeTestRuntimeBytes": len(runner_contents),
        "compiledNodeTestRuntimeSha256": _sha256_bytes(runner_contents),
        "result": "passed",
    }


def write_evidence(path: Path, evidence: Mapping[str, Any]) -> None:
    write_canonical_json(Path(path), dict(evidence))


DESKTOP_KEYS = {
    "schemaVersion", "candidateCommit", "target", "classifier", "runnerOs", "runnerArch",
    "testTask", "testClass", "testMethods", "tests", "skipped", "failures", "errors",
    "binarySha256", "supervisorSha256", "classifierArchiveSha256", "result",
}
JVM_KEYS = {
    "schemaVersion", "candidateCommit", "target", "classifier", "runnerOs", "runnerArch",
    "testTask", "testClass", "testMethods", "tests", "skipped", "failures", "errors",
    "classifierArchiveFileName", "classifierArchiveBytes", "classifierArchiveSha256",
    "appServerBinarySha256", "supervisorBinarySha256", "compiledJvmTestRuntimeFileName",
    "compiledJvmTestRuntimeBytes", "compiledJvmTestRuntimeSha256", "result",
}
NODE_KEYS = {
    "schemaVersion", "candidateCommit", "target", "runtimeBackend", "classifier", "runnerOs",
    "runnerArch", "nodeVersion", "testTask", "testClass", "testMethods", "tests", "skipped",
    "failures", "errors", "classifierArchiveFileName", "classifierArchiveBytes",
    "classifierArchiveSha256", "appServerBinarySha256", "processSupervisorSha256",
    "compiledNodeTestRuntimeFileName", "compiledNodeTestRuntimeBytes",
    "compiledNodeTestRuntimeSha256", "result",
}


def _check_commits(expected_commits: Mapping[str, str]) -> None:
    if set(expected_commits) != set(RUNTIME_TARGETS) or any(not COMMIT.fullmatch(value) for value in expected_commits.values()):
        raise ValueError("candidate commit map is incomplete or non-immutable")


def _files_by_name(files: Iterable[Path], expected_names: set[str]) -> dict[str, Path]:
    paths = [Path(path) for path in files]
    names = [path.name for path in paths]
    if len(paths) != len(expected_names) or len(names) != len(set(names)) or set(names) != expected_names:
        raise ValueError("evidence file set mismatch")
    return dict(zip(names, paths, strict=True))


def _load_report(path: Path, keys: set[str]) -> dict[str, Any]:
    report = _object(load_json(path), "Runtime evidence")
    _exact_keys(report, keys, "Runtime evidence")
    return report


def _check_common_report(
    report: Mapping[str, Any],
    *,
    schema: int,
    target: str,
    commit: str,
    test_class: str,
    test_methods: tuple[str, ...],
) -> None:
    expected = RUNTIME_TARGETS[target]
    if (
        _integer(report["schemaVersion"], "schemaVersion") != schema
        or report["candidateCommit"] != commit
        or report["target"] != target
        or report["classifier"] != expected.classifier
        or report["runnerOs"] != expected.runner_os
        or report["runnerArch"] != expected.runner_arch
        or report["testClass"] != test_class
        or tuple(_array(report["testMethods"], "testMethods")) != test_methods
        or _integer(report["tests"], "tests") != len(test_methods)
        or any(_integer(report[name], name) != 0 for name in ("skipped", "failures", "errors"))
        or report["result"] != "passed"
    ):
        raise ValueError("Runtime evidence identity or test result mismatch")


def _classifier_proofs(
    manifest_path: Path,
    classifier_archives: Iterable[Path],
) -> tuple[DistributionManifest, dict[str, ClassifierProof]]:
    manifest = read_distribution_manifest(manifest_path)
    archives = [Path(path) for path in classifier_archives]
    if len(archives) != len(RUNTIME_TARGETS):
        raise ValueError("classifier archive set mismatch")
    proofs: dict[str, ClassifierProof] = {}
    for target in RUNTIME_TARGETS:
        matches: list[ClassifierProof] = []
        for archive in archives:
            try:
                matches.append(inspect_classifier(target, manifest, archive))
            except (KeyError, StopIteration, ValueError, zipfile.BadZipFile):
                pass
        if len(matches) != 1:
            raise ValueError(f"{target}: expected exactly one matching classifier archive")
        proofs[target] = matches[0]
    return manifest, proofs


def validate_desktop_evidence(
    files: Iterable[Path],
    expected_commits: Mapping[str, str],
    *,
    version: str | None = None,
    maven_inventory: Path | None = None,
    distribution_manifest: Path | None = None,
    classifier_archives: Iterable[Path] = (),
) -> list[str]:
    try:
        _check_commits(expected_commits)
        by_name = _files_by_name(files, {desktop_evidence_filename(target) for target in RUNTIME_TARGETS})
        manifest: DistributionManifest | None = None
        proofs: dict[str, ClassifierProof] = {}
        if distribution_manifest is not None:
            manifest = read_distribution_manifest(distribution_manifest)
            archives = list(classifier_archives)
            if archives:
                _, proofs = _classifier_proofs(distribution_manifest, archives)
        inventory: dict[str, str] = {}
        if maven_inventory is not None:
            raw = _object(load_json(maven_inventory), "Maven inventory")
            records = _array(raw.get("files"), "Maven inventory files")
            for record in records:
                item = _object(record, "Maven inventory record")
                path = _string(item.get("path"), "Maven inventory path")
                if path in inventory:
                    raise ValueError("Maven inventory contains duplicate paths")
                inventory[path] = _string(item.get("sha256"), "Maven inventory SHA-256")
        distributions = {record.target: record for record in manifest.distributions} if manifest else {}
        for target, expected in RUNTIME_TARGETS.items():
            report = _load_report(by_name[desktop_evidence_filename(target)], DESKTOP_KEYS)
            _check_common_report(
                report, schema=3, target=target, commit=expected_commits[target],
                test_class=DESKTOP_RUNTIME_TEST_CLASS, test_methods=DESKTOP_RUNTIME_TEST_METHODS,
            )
            if report["testTask"] not in {desktop_test_task(target), imported_desktop_test_task(target)}:
                raise ValueError(f"{target}: test task mismatch")
            binary = _hex(report["binarySha256"], SHA256, "binary SHA-256")
            supervisor = _hex(report["supervisorSha256"], SHA256, "supervisor SHA-256")
            archive = _hex(report["classifierArchiveSha256"], SHA256, "classifier SHA-256")
            if manifest and (distributions[target].classifier != expected.classifier or distributions[target].binary_sha256 != binary):
                raise ValueError(f"{target}: distribution identity mismatch")
            if target in proofs and (
                proofs[target].binary_sha256 != binary
                or proofs[target].supervisor_sha256 != supervisor
                or proofs[target].archive_sha256 != archive
            ):
                raise ValueError(f"{target}: classifier proof mismatch")
            if version is not None and maven_inventory is not None:
                path = (
                    f"{MAVEN_GROUP_PATH}/codex-agent-runtime-desktop/{version}/"
                    f"codex-agent-runtime-desktop-{version}-{expected.classifier}.zip"
                )
                if inventory.get(path) != archive:
                    raise ValueError(f"{target}: classifier hash is not bound to Maven inventory")
        return []
    except (KeyError, StopIteration, TypeError, ValueError, RuntimeError, zipfile.BadZipFile) as error:
        return [str(error)]


def validate_jvm_evidence(
    files: Iterable[Path],
    expected_commits: Mapping[str, str],
    distribution_manifest: Path,
    classifier_archives: Iterable[Path],
    runner: Path,
) -> list[str]:
    try:
        _check_commits(expected_commits)
        by_name = _files_by_name(files, {jvm_evidence_filename(target) for target in RUNTIME_TARGETS})
        _, proofs = _classifier_proofs(distribution_manifest, classifier_archives)
        inspect_jvm_runner(runner)
        runner_contents = _file_bytes(runner)
        for target in RUNTIME_TARGETS:
            report = _load_report(by_name[jvm_evidence_filename(target)], JVM_KEYS)
            _check_common_report(
                report, schema=1, target=target, commit=expected_commits[target],
                test_class=DESKTOP_RUNTIME_TEST_CLASS, test_methods=DESKTOP_RUNTIME_TEST_METHODS,
            )
            if report["testTask"] not in {jvm_test_task(target), IMPORTED_JVM_RUNTIME_EVIDENCE_TASK}:
                raise ValueError(f"{target}: test task mismatch")
            proof = proofs[target]
            _safe_basename(_string(report["classifierArchiveFileName"], "classifier archive filename"), "classifier archive filename")
            if (
                report["classifierArchiveBytes"] != proof.archive_bytes
                or report["classifierArchiveSha256"] != proof.archive_sha256
                or report["appServerBinarySha256"] != proof.binary_sha256
                or report["supervisorBinarySha256"] != proof.supervisor_sha256
                or report["compiledJvmTestRuntimeFileName"] != JVM_RUNTIME_RUNNER_ARCHIVE
                or report["compiledJvmTestRuntimeBytes"] != len(runner_contents)
                or report["compiledJvmTestRuntimeSha256"] != _sha256_bytes(runner_contents)
            ):
                raise ValueError(f"{target}: classifier or compiled JVM runtime mismatch")
        return []
    except (KeyError, StopIteration, TypeError, ValueError, RuntimeError, zipfile.BadZipFile) as error:
        return [str(error)]


def validate_node_evidence(
    files: Iterable[Path],
    expected_commits: Mapping[str, str],
    backend: str,
    distribution_manifest: Path,
    classifier_archives: Iterable[Path],
    runner: Path,
) -> list[str]:
    try:
        _node_runner_name(backend)
        _check_commits(expected_commits)
        by_name = _files_by_name(files, {node_evidence_filename(target, backend) for target in RUNTIME_TARGETS})
        _, proofs = _classifier_proofs(distribution_manifest, classifier_archives)
        inspect_node_runner(runner, backend)
        runner_contents = _file_bytes(runner)
        for target in RUNTIME_TARGETS:
            report = _load_report(by_name[node_evidence_filename(target, backend)], NODE_KEYS)
            _check_common_report(
                report, schema=2, target=target, commit=expected_commits[target],
                test_class=NODE_RUNTIME_TEST_CLASS, test_methods=NODE_RUNTIME_TEST_METHODS,
            )
            if (
                report["runtimeBackend"] != backend
                or report["nodeVersion"] != PINNED_NODE_VERSION
                or report["testTask"] != node_test_task(target, backend)
            ):
                raise ValueError(f"{target}: Node identity mismatch")
            proof = proofs[target]
            _safe_basename(_string(report["classifierArchiveFileName"], "classifier archive filename"), "classifier archive filename")
            _safe_basename(_string(report["compiledNodeTestRuntimeFileName"], "compiled artifact filename"), "compiled artifact filename")
            if (
                report["classifierArchiveBytes"] != proof.archive_bytes
                or report["classifierArchiveSha256"] != proof.archive_sha256
                or report["appServerBinarySha256"] != proof.binary_sha256
                or report["processSupervisorSha256"] != proof.supervisor_sha256
                or report["compiledNodeTestRuntimeFileName"] != Path(runner).name
                or report["compiledNodeTestRuntimeBytes"] != len(runner_contents)
                or report["compiledNodeTestRuntimeSha256"] != _sha256_bytes(runner_contents)
            ):
                raise ValueError(f"{target}: classifier or compiled Node runtime mismatch")
        return []
    except (KeyError, StopIteration, TypeError, ValueError, RuntimeError, zipfile.BadZipFile) as error:
        return [str(error)]


def verify_desktop_test_report(path: Path, target: str) -> None:
    contents = _file_bytes(path)
    if b"<!DOCTYPE" in contents.upper() or b"<!ENTITY" in contents.upper():
        raise ValueError("Desktop test report contains forbidden XML declarations")
    try:
        root = ET.fromstring(contents)
    except ET.ParseError as error:
        raise ValueError("Desktop test report is malformed") from error
    if root.tag != "testsuite" or any(
        _integer(int(root.get(name, "-1")), name) != expected
        for name, expected in (("tests", 4), ("skipped", 0), ("failures", 0), ("errors", 0))
    ):
        raise ValueError("Desktop smoke must run all exact tests without skips or failures")
    cases = list(root.iter("testcase"))
    expected_class = f"{target}Test.{DESKTOP_RUNTIME_TEST_CLASS}"
    methods = {case.get("name", "").split("[", 1)[0] for case in cases}
    if len(cases) != 4 or {case.get("classname") for case in cases} != {expected_class} or methods != set(DESKTOP_RUNTIME_TEST_METHODS):
        raise ValueError("Desktop smoke test methods or class are incomplete or unexpected")


def _target_commits(values: list[str]) -> dict[str, str]:
    commits: dict[str, str] = {}
    for value in values:
        target, separator, commit = value.partition("=")
        if not separator or target in commits:
            raise ValueError("Expected each --expected-commit exactly once as target=commit")
        commits[target] = commit
    _check_commits(commits)
    return commits


def _emit(value: Any, output: Path | None) -> None:
    if output is None:
        from .inventory import canonical_json_bytes

        sys.stdout.write(canonical_json_bytes(value).decode("utf-8"))
    else:
        write_canonical_json(output, value)


def _require_output_name(output: Path | None, expected: str) -> None:
    if output is not None and output.name != expected:
        raise ValueError(f"Evidence output must be named exactly {expected}")


def _result(command: str) -> dict[str, Any]:
    return {"schemaVersion": 1, "command": command, "result": "passed"}


def _validate_or_fail(errors: list[str]) -> None:
    if errors:
        raise ValueError("; ".join(errors))


def _add_output(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output", type=Path)


def _add_commits_and_files(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--expected-commit", action="append", default=[], required=True)
    parser.add_argument("--evidence", type=Path, action="append", default=[], required=True)


def _add_classifier_inputs(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--classifier", type=Path, action="append", default=[], required=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m ci.products.runtime_evidence")
    commands = parser.add_subparsers(dest="command", required=True)

    inspect = commands.add_parser("inspect-manifest")
    inspect.add_argument("--manifest", type=Path, required=True)
    _add_output(inspect)

    desktop = commands.add_parser("build-desktop")
    desktop.add_argument("--candidate-commit", required=True)
    desktop.add_argument("--target", choices=RUNTIME_TARGETS, required=True)
    desktop.add_argument("--binary-sha256", required=True)
    desktop.add_argument("--supervisor-sha256", required=True)
    desktop.add_argument("--classifier-archive-sha256", required=True)
    desktop.add_argument("--test-task")
    _add_output(desktop)

    jvm = commands.add_parser("build-jvm")
    jvm.add_argument("--candidate-commit", required=True)
    jvm.add_argument("--target", choices=RUNTIME_TARGETS, required=True)
    jvm.add_argument("--manifest", type=Path, required=True)
    jvm.add_argument("--classifier", type=Path, required=True)
    jvm.add_argument("--runner", type=Path, required=True)
    jvm.add_argument("--test-task")
    _add_output(jvm)

    node = commands.add_parser("build-node")
    node.add_argument("--candidate-commit", required=True)
    node.add_argument("--target", choices=RUNTIME_TARGETS, required=True)
    node.add_argument("--backend", choices=(NODE_RUNTIME_JS_BACKEND, NODE_RUNTIME_WASM_BACKEND), required=True)
    node.add_argument("--manifest", type=Path, required=True)
    node.add_argument("--classifier", type=Path, required=True)
    node.add_argument("--runner", type=Path, required=True)
    _add_output(node)

    desktop_validation = commands.add_parser("validate-desktop")
    _add_commits_and_files(desktop_validation)
    desktop_validation.add_argument("--version")
    desktop_validation.add_argument("--maven-inventory", type=Path)
    desktop_validation.add_argument("--manifest", type=Path)
    desktop_validation.add_argument("--classifier", type=Path, action="append", default=[])
    _add_output(desktop_validation)

    jvm_validation = commands.add_parser("validate-jvm")
    _add_commits_and_files(jvm_validation)
    _add_classifier_inputs(jvm_validation)
    jvm_validation.add_argument("--runner", type=Path, required=True)
    _add_output(jvm_validation)

    node_validation = commands.add_parser("validate-node")
    _add_commits_and_files(node_validation)
    _add_classifier_inputs(node_validation)
    node_validation.add_argument(
        "--backend",
        choices=(NODE_RUNTIME_JS_BACKEND, NODE_RUNTIME_WASM_BACKEND),
        required=True,
    )
    node_validation.add_argument("--runner", type=Path, required=True)
    _add_output(node_validation)

    report = commands.add_parser("verify-desktop-test-report")
    report.add_argument("--report", type=Path, required=True)
    report.add_argument("--target", choices=RUNTIME_TARGETS, required=True)
    _add_output(report)

    arguments = parser.parse_args(argv)
    if arguments.command == "inspect-manifest":
        value = distribution_manifest_projection(read_distribution_manifest(arguments.manifest))
    elif arguments.command == "build-desktop":
        _hex(arguments.candidate_commit, COMMIT, "candidate commit")
        _hex(arguments.binary_sha256, SHA256, "binary SHA-256")
        _hex(arguments.supervisor_sha256, SHA256, "supervisor SHA-256")
        _hex(arguments.classifier_archive_sha256, SHA256, "classifier archive SHA-256")
        _require_output_name(arguments.output, desktop_evidence_filename(arguments.target))
        value = build_desktop_evidence(
            arguments.candidate_commit,
            arguments.target,
            arguments.binary_sha256,
            arguments.supervisor_sha256,
            arguments.classifier_archive_sha256,
            test_task=arguments.test_task,
        )
    elif arguments.command == "build-jvm":
        _hex(arguments.candidate_commit, COMMIT, "candidate commit")
        manifest = read_distribution_manifest(arguments.manifest)
        proof = inspect_classifier(arguments.target, manifest, arguments.classifier)
        _require_output_name(arguments.output, jvm_evidence_filename(arguments.target))
        value = build_jvm_evidence(
            arguments.candidate_commit,
            arguments.target,
            proof,
            arguments.runner,
            test_task=arguments.test_task,
        )
    elif arguments.command == "build-node":
        _hex(arguments.candidate_commit, COMMIT, "candidate commit")
        manifest = read_distribution_manifest(arguments.manifest)
        proof = inspect_classifier(arguments.target, manifest, arguments.classifier)
        _require_output_name(arguments.output, node_evidence_filename(arguments.target, arguments.backend))
        value = build_node_evidence(
            arguments.candidate_commit,
            arguments.target,
            arguments.backend,
            proof,
            arguments.runner,
        )
    elif arguments.command == "validate-desktop":
        if (arguments.version is None) != (arguments.maven_inventory is None):
            parser.error("validate-desktop requires --version and --maven-inventory together")
        if arguments.classifier and arguments.manifest is None:
            parser.error("validate-desktop --classifier requires --manifest")
        _validate_or_fail(
            validate_desktop_evidence(
                arguments.evidence,
                _target_commits(arguments.expected_commit),
                version=arguments.version,
                maven_inventory=arguments.maven_inventory,
                distribution_manifest=arguments.manifest,
                classifier_archives=arguments.classifier,
            )
        )
        value = _result(arguments.command)
    elif arguments.command == "validate-jvm":
        _validate_or_fail(
            validate_jvm_evidence(
                arguments.evidence,
                _target_commits(arguments.expected_commit),
                arguments.manifest,
                arguments.classifier,
                arguments.runner,
            )
        )
        value = _result(arguments.command)
    elif arguments.command == "validate-node":
        _validate_or_fail(
            validate_node_evidence(
                arguments.evidence,
                _target_commits(arguments.expected_commit),
                arguments.backend,
                arguments.manifest,
                arguments.classifier,
                arguments.runner,
            )
        )
        value = _result(arguments.command)
    else:
        verify_desktop_test_report(arguments.report, arguments.target)
        value = _result(arguments.command)
    _emit(value, arguments.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
