from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
import hashlib
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tomllib
from typing import Any
import xml.etree.ElementTree as ElementTree

from .inventory import (
    canonical_json_bytes,
    git_regular_blob_bytes,
    load_canonical_json_bytes,
    read_regular_file_bytes,
    require_array,
    require_exact_keys,
    require_identifier,
    require_integer,
    require_string,
    require_sha256,
    run_git,
    sha256_bytes,
    write_canonical_json,
)


SCHEMA_VERSION = 2
PRODUCER_ROLES = {"builder", "cross-builder", "supervisor-builder"}
RUNNER_OS = {"Linux", "macOS", "Windows"}
RUNNER_ARCH = {"ARM64", "X64"}
PROFILE_SHAPES = {
    "linux-arm64": (
        ("cross-builder", "Linux", "X64"),
        ("supervisor-builder", "Linux", "ARM64"),
    ),
    "linux-x64": (("builder", "Linux", "X64"),),
    "macos-arm64": (("builder", "macOS", "ARM64"),),
    "macos-x64": (("builder", "macOS", "X64"),),
    "windows-x64": (("builder", "Windows", "X64"),),
}
NATIVE_BUILD_TOOLS = (
    "gradleWrapper",
    "javaRuntime",
    "konanDependencies",
    "kotlinNativeCompiler",
    "kotlinPlugin",
)
PROFILE_TOOL_NAMES = {
    **{
        (profile_id, "builder"): (*NATIVE_BUILD_TOOLS, "supervisorCompiler")
        for profile_id in PROFILE_SHAPES
        if profile_id != "linux-arm64"
    },
    ("linux-arm64", "cross-builder"): NATIVE_BUILD_TOOLS,
    ("linux-arm64", "supervisor-builder"): (
        "gradleWrapper",
        "javaRuntime",
        "supervisorCompiler",
    ),
}
NAME = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:[._-][A-Za-z0-9]+)*")
GIT_OBJECT_ID = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
HEX_FINGERPRINT = re.compile(r"[0-9a-f]+")
PROFILE_ROOT = "gradle/release/toolchains/runtime"
WRAPPER_PROPERTIES = "gradle/wrapper/gradle-wrapper.properties"
VERSION_CATALOG = "gradle/libs.versions.toml"
RUNTIME_VERIFICATION_METADATA = "runtime/gradle/verification-metadata.xml"
OBSERVATION_KEYS = {
    "gradleWrapper": {"distributionSha256", "launcherSha256", "version"},
    "javaRuntime": {
        "arch", "binarySha256", "runtimeVersion", "vendor", "vendorVersion", "vmName", "vmVersion",
    },
    "konanDependencies": {"entries", "host", "target"},
    "kotlinNativeCompiler": {
        "archiveName", "archiveSha256", "compilerFingerprint", "compilerTreeSha256",
        "compilerVersion", "host",
    },
    "kotlinPlugin": {"artifactName", "artifactSha256", "version"},
    "supervisorCompiler": {
        "compilerBinarySha256", "compilerVersion", "family", "linkerBinarySha256",
        "linkerVersion", "platformBuild", "platformVersion", "target",
    },
}
HOSTS = {
    ("Linux", "X64"): ("linux_x64", "linux-x86_64"),
    ("macOS", "ARM64"): ("macos_arm64", "macos-aarch64"),
    ("macOS", "X64"): ("macos_x64", "macos-x86_64"),
    ("Windows", "X64"): ("mingw_x64", "windows-x86_64"),
}
TARGETS = {
    "linux-arm64": "linux_arm64",
    "linux-x64": "linux_x64",
    "macos-arm64": "macos_arm64",
    "macos-x64": "macos_x64",
    "windows-x64": "mingw_x64",
}


@dataclass(frozen=True, slots=True)
class ToolchainProducer:
    role: str
    runner_os: str
    runner_arch: str
    tools: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class ToolchainProfile:
    id: str
    producers: tuple[ToolchainProducer, ...]
    digest: str
    _canonical: bytes = field(repr=False)


def _identity(value: Any, label: str) -> str:
    if type(value) is not str or not value or value != value.strip() or len(value.splitlines()) != 1 or any(
        ord(character) < 0x20 or 0x7F <= ord(character) <= 0x9F for character in value
    ):
        raise ValueError(f"{label} must be a nonempty canonical single-line identity")
    return value


def _name(value: Any, label: str) -> str:
    if type(value) is not str or NAME.fullmatch(value) is None:
        raise ValueError(f"{label} is not a canonical name")
    return value


def _runner(value: Any, label: str) -> tuple[str, str]:
    runner = require_exact_keys(value, {"os", "arch"}, label)
    if (
        type(runner["os"]) is not str
        or type(runner["arch"]) is not str
        or runner["os"] not in RUNNER_OS
        or runner["arch"] not in RUNNER_ARCH
    ):
        raise ValueError(f"{label} is unsupported")
    return runner["os"], runner["arch"]


def _tools(value: Any, label: str) -> tuple[tuple[str, str], ...]:
    records = require_array(value, label)
    if not records:
        raise ValueError(f"{label} must not be empty")
    tools = []
    for index, value in enumerate(records):
        item_label = f"{label}[{index}]"
        item = require_exact_keys(value, {"name", "identity"}, item_label)
        tools.append((
            _name(item["name"], f"{item_label}.name"),
            _identity(item["identity"], f"{item_label}.identity"),
        ))
    if tools != sorted(tools) or len({name for name, _ in tools}) != len(tools):
        raise ValueError(f"{label} must be sorted by name and unique")
    return tuple(tools)


def validate_toolchain_profile(value: Any, digest: str) -> ToolchainProfile:
    profile = require_exact_keys(value, {"schemaVersion", "id", "producers"}, "Toolchain profile")
    if require_integer(profile["schemaVersion"], "Toolchain profile.schemaVersion", 1) != SCHEMA_VERSION:
        raise ValueError("Unsupported Toolchain profile schemaVersion")
    profile_id = require_identifier(profile["id"], "Toolchain profile.id")
    if profile_id not in PROFILE_SHAPES:
        raise ValueError("Toolchain profile ID is unsupported")

    records = require_array(profile["producers"], "Toolchain profile.producers")
    producers = []
    for index, value in enumerate(records):
        label = f"Toolchain profile.producers[{index}]"
        producer = require_exact_keys(value, {"role", "runner", "tools"}, label)
        role = producer["role"]
        if type(role) is not str or role not in PRODUCER_ROLES:
            raise ValueError(f"{label}.role is unsupported")
        runner_os, runner_arch = _runner(producer["runner"], f"{label}.runner")
        tools = _tools(producer["tools"], f"{label}.tools")
        expected_tools = PROFILE_TOOL_NAMES.get((profile_id, role))
        if expected_tools is None or tuple(name for name, _ in tools) != expected_tools:
            raise ValueError(f"{label}.tools do not match the exact producer tool set")
        producers.append(ToolchainProducer(
            role,
            runner_os,
            runner_arch,
            tools,
        ))
    if [producer.role for producer in producers] != sorted(producer.role for producer in producers) \
            or len({producer.role for producer in producers}) != len(producers):
        raise ValueError("Toolchain profile producers must be sorted by role and unique")
    if tuple(
        (producer.role, producer.runner_os, producer.runner_arch)
        for producer in producers
    ) != PROFILE_SHAPES[profile_id]:
        raise ValueError("Toolchain profile producer topology does not match its target")

    canonical = canonical_json_bytes(profile)
    validated_digest = require_sha256(digest, "Toolchain profile digest")
    if sha256_bytes(canonical) != validated_digest:
        raise ValueError("Toolchain profile digest does not match its canonical bytes")
    return ToolchainProfile(profile_id, tuple(producers), validated_digest, canonical)


def load_toolchain_profile_bytes(contents: bytes, expected_id: str) -> ToolchainProfile:
    selected = require_identifier(expected_id, "Selected toolchain profile")
    profile = validate_toolchain_profile(
        load_canonical_json_bytes(contents),
        sha256_bytes(contents),
    )
    if profile.id != selected:
        raise ValueError("Selected toolchain profile ID does not match its authority or file name")
    return profile


def load_toolchain_profile(directory: Path, profile_id: str) -> ToolchainProfile:
    selected = require_identifier(profile_id, "Selected toolchain profile")
    contents = read_regular_file_bytes(
        Path(directory) / f"{selected}.json",
        max_bytes=65_536,
        reject_symlink_parents=True,
    )
    return load_toolchain_profile_bytes(contents, selected)


def _validate_image_provenance(value: Mapping[str, str] | None) -> None:
    if value is None:
        return
    if type(value) is not dict:
        raise ValueError("Image provenance must be an object")
    for name, identity in value.items():
        _name(name, "Image provenance field")
        _identity(identity, f"Image provenance.{name}")


def verify_toolchain_profile(
    profile: ToolchainProfile,
    expected_digest: str,
    producer_role: str,
    runner: Mapping[str, str],
    tools: Mapping[str, str],
    *,
    image_provenance: Mapping[str, str] | None = None,
    executor: Callable[[], Any] | None = None,
) -> str:
    if type(profile) is not ToolchainProfile:
        raise ValueError("Selected toolchain profile is invalid")
    validated = validate_toolchain_profile(
        load_canonical_json_bytes(profile._canonical),
        profile.digest,
    )
    if validated != profile:
        raise ValueError("Selected toolchain profile does not match its canonical bytes")
    expected = require_sha256(expected_digest, "Expected toolchain profile digest")
    if profile.digest != expected:
        raise ValueError("Selected toolchain profile digest mismatch")
    matches = [producer for producer in profile.producers if producer.role == producer_role]
    if len(matches) != 1:
        raise ValueError("Actual producer role does not match the selected toolchain profile")
    producer = matches[0]
    if type(runner) is not dict or set(runner) != {"os", "arch"}:
        raise ValueError("Actual runner fields are invalid")
    if (runner["os"], runner["arch"]) != (producer.runner_os, producer.runner_arch):
        raise ValueError("Actual runner does not match the selected toolchain producer")
    if type(tools) is not dict or set(tools) != {name for name, _ in producer.tools}:
        raise ValueError("Actual tool fields do not match the selected toolchain producer")
    actual = tuple(sorted(
        (name, _identity(identity, f"Actual {name} identity"))
        for name, identity in tools.items()
    ))
    if actual != producer.tools:
        raise ValueError("Actual tool identities do not match the selected toolchain producer")
    _validate_image_provenance(image_provenance)
    if executor is not None:
        if not callable(executor):
            raise ValueError("Toolchain executor must be callable")
        executor()
    return profile.digest


def load_and_verify_toolchain_profile(
    directory: Path,
    profile_id: str,
    expected_digest: str,
    producer_role: str,
    runner: Mapping[str, str],
    tools: Mapping[str, str],
    *,
    image_provenance: Mapping[str, str] | None = None,
    executor: Callable[[], Any] | None = None,
) -> str:
    return verify_toolchain_profile(
        load_toolchain_profile(directory, profile_id),
        expected_digest,
        producer_role,
        runner,
        tools,
        image_provenance=image_provenance,
        executor=executor,
    )


def _revision(value: str) -> str:
    if type(value) is not str or GIT_OBJECT_ID.fullmatch(value) is None:
        raise ValueError("Repository revision must be an exact lowercase Git object ID")
    return value


def _authority(root: Path, revision: str, relative_path: str) -> bytes:
    exact = git_regular_blob_bytes(root, revision, relative_path, max_bytes=4 * 1024 * 1024)
    checked_out = read_regular_file_bytes(
        root / relative_path,
        max_bytes=4 * 1024 * 1024,
        reject_symlink_parents=True,
    )
    if checked_out != exact:
        raise ValueError(f"Checked-out toolchain authority differs from the exact Git revision: {relative_path}")
    return exact


def _command(command: tuple[str, ...], root: Path) -> str:
    invocation = command
    if os.name == "nt" and command[0].lower().endswith((".bat", ".cmd")):
        invocation = (
            os.environ.get("ComSpec", "cmd.exe"),
            "/d", "/s", "/c", subprocess.list2cmdline(command),
        )
    result = subprocess.run(
        invocation,
        cwd=root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if result.returncode:
        raise ValueError(f"Toolchain observation command failed: {command[0]}")
    return result.stdout.replace("\r", "")


def _one_line(value: str, label: str) -> str:
    result = " ".join(value.split())
    return _identity(result, label)


def _match(pattern: str, value: str, label: str) -> str:
    match = re.search(pattern, value, re.MULTILINE)
    if match is None:
        raise ValueError(f"Could not observe {label}")
    return _one_line(match.group(1), label)


def _sha256_file(path: Path, label: str) -> str:
    try:
        before = path.lstat()
    except OSError as error:
        raise ValueError(f"{label} is missing or unsafe") from error
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise ValueError(f"{label} is missing or unsafe")
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        after = path.lstat()
    except OSError as error:
        raise ValueError(f"{label} could not be read safely") from error
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
    ):
        raise ValueError(f"{label} changed during observation")
    return f"sha256:{digest.hexdigest()}"


def _unique_file(root: Path, name: str, label: str) -> Path:
    if not root.is_dir() or root.is_symlink():
        raise ValueError(f"{label} cache is missing or unsafe")
    matches = [path for path in root.rglob(name) if path.name == name]
    if len(matches) != 1:
        raise ValueError(f"{label} cache must contain exactly one {name}")
    _sha256_file(matches[0], label)
    return matches[0]


def _metadata_checksum(contents: bytes, artifact_name: str) -> str:
    try:
        root = ElementTree.fromstring(contents)
    except ElementTree.ParseError as error:
        raise ValueError("Runtime verification metadata is malformed") from error
    checksums = []
    for artifact in root.iter():
        if artifact.tag.rsplit("}", 1)[-1] != "artifact" or artifact.get("name") != artifact_name:
            continue
        values = [
            child.get("value")
            for child in artifact
            if child.tag.rsplit("}", 1)[-1] == "sha256"
        ]
        if len(values) != 1 or type(values[0]) is not str or re.fullmatch(r"[0-9a-f]{64}", values[0]) is None:
            raise ValueError(f"Runtime verification metadata lacks one exact checksum for {artifact_name}")
        checksums.append(f"sha256:{values[0]}")
    if len(checksums) != 1:
        raise ValueError(f"Runtime verification metadata lacks one exact checksum for {artifact_name}")
    return checksums[0]


def _properties(contents: bytes, label: str) -> dict[str, str]:
    try:
        lines = contents.decode("utf-8", errors="strict").splitlines()
    except UnicodeDecodeError as error:
        raise ValueError(f"{label} is not UTF-8") from error
    logical: list[str] = []
    current = ""
    for raw in lines:
        stripped = raw.strip()
        if not current and (not stripped or stripped.startswith(("#", "!"))):
            continue
        current += stripped
        if current.endswith("\\"):
            current = current[:-1] + " "
            continue
        logical.append(current)
        current = ""
    if current:
        raise ValueError(f"{label} has an unterminated continuation")
    result: dict[str, str] = {}
    for line in logical:
        separator = min((index for index in (line.find("="), line.find(":")) if index >= 0), default=-1)
        if separator < 1:
            raise ValueError(f"{label} contains a malformed property")
        key, value = line[:separator].strip(), line[separator + 1:].strip()
        if key in result:
            raise ValueError(f"{label} contains a duplicate property: {key}")
        result[key] = value
    return result


def _expand_property(properties: Mapping[str, str], key: str, seen: frozenset[str] = frozenset()) -> str:
    if key in seen or key not in properties:
        raise ValueError(f"Kotlin/Native property is missing or recursive: {key}")
    pattern = re.compile(r"\$([A-Za-z0-9_.-]+)")
    value = properties[key]
    while True:
        match = pattern.search(value)
        if match is None:
            return value
        replacement = _expand_property(properties, match.group(1), seen | {key})
        value = value[:match.start()] + replacement + value[match.end():]


def _tree_digest(path: Path, label: str) -> str:
    if not path.is_dir() or path.is_symlink():
        raise ValueError(f"{label} dependency is missing or unsafe")
    root = path.resolve()
    records: list[dict[str, Any]] = []
    for candidate in sorted(path.rglob("*"), key=lambda item: item.relative_to(path).as_posix()):
        relative = candidate.relative_to(path).as_posix()
        metadata = candidate.lstat()
        if stat.S_ISDIR(metadata.st_mode):
            continue
        if stat.S_ISLNK(metadata.st_mode):
            target = os.readlink(candidate)
            if os.path.isabs(target) or (candidate.parent / target).resolve().is_relative_to(root) is False:
                raise ValueError(f"{label} contains an unsafe symlink: {relative}")
            records.append({"kind": "symlink", "relativePath": relative, "target": target})
        elif stat.S_ISREG(metadata.st_mode):
            records.append({
                "bytes": metadata.st_size,
                "kind": "file",
                "relativePath": relative,
                "sha256": _sha256_file(candidate, f"{label}/{relative}"),
            })
        else:
            raise ValueError(f"{label} contains an unsupported entry: {relative}")
    if not records:
        raise ValueError(f"{label} dependency is empty")
    return sha256_bytes(canonical_json_bytes(records))


def _tool_observation(name: str, value: dict[str, Any]) -> dict[str, Any]:
    expected = OBSERVATION_KEYS.get(name)
    if expected is None:
        raise ValueError(f"Unsupported tool observation: {name}")
    observation = require_exact_keys(value, expected, f"{name} observation")
    if name == "konanDependencies":
        require_string(observation["host"], "Kotlin/Native dependency host")
        require_string(observation["target"], "Kotlin/Native dependency target")
        entries = require_array(observation["entries"], "Kotlin/Native dependency entries")
        names = []
        for index, entry in enumerate(entries):
            record = require_exact_keys(entry, {"name", "treeSha256"}, f"Kotlin/Native dependency[{index}]")
            names.append(require_string(record["name"], f"Kotlin/Native dependency[{index}].name"))
            require_sha256(record["treeSha256"], f"Kotlin/Native dependency[{index}].treeSha256")
        if not names or names != sorted(set(names)):
            raise ValueError("Kotlin/Native dependency entries must be sorted, unique, and nonempty")
    else:
        for key, member in observation.items():
            if key.endswith("Sha256"):
                require_sha256(member, f"{name} observation.{key}")
            else:
                _identity(member, f"{name} observation.{key}")
    return {
        "identity": sha256_bytes(canonical_json_bytes({"name": name, "value": observation})),
        "name": name,
        "value": observation,
    }


def _validate_tool_record(value: Any, label: str) -> dict[str, Any]:
    record = require_exact_keys(value, {"identity", "name", "value"}, label)
    name = _name(record["name"], f"{label}.name")
    expected = _tool_observation(name, record["value"])
    if record != expected:
        raise ValueError(f"{label} identity does not match its canonical observation")
    return record


def _konan_dependencies(
    properties: Mapping[str, str], host: str, target: str, directory: Path,
) -> dict[str, Any]:
    keys = [f"llvmHome.{host}", f"libffiDir.{host}"]
    target_key = f"dependencies.{target}" if host == target else f"dependencies.{host}-{target}"
    keys.append(target_key)
    names: set[str] = set()
    for key in keys:
        for value in _expand_property(properties, key).split():
            name = value.replace("\\", "/").split("/", 1)[0]
            if not name or name in {".", ".."} or "/" in name or "\\" in name:
                raise ValueError(f"Kotlin/Native dependency property is unsafe: {key}")
            names.add(name)
    return {
        "entries": [
            {"name": name, "treeSha256": _tree_digest(directory / name, f"Kotlin/Native {name}")}
            for name in sorted(names)
        ],
        "host": host,
        "target": target,
    }


def _supervisor_observation(
    root: Path,
    runner_os: str,
    compiler: str,
    environment: Mapping[str, str],
    execute: Callable[[tuple[str, ...], Path], str],
    find_executable: Callable[[str], str | None],
) -> dict[str, Any]:
    compiler_path_value = find_executable(compiler)
    if compiler_path_value is None:
        raise ValueError("Supervisor compiler is missing")
    compiler_path = Path(compiler_path_value).resolve()
    if runner_os == "Windows":
        linker_path_value = find_executable("link")
        if linker_path_value is None:
            raise ValueError("MSVC linker is missing")
        linker_path = Path(linker_path_value).resolve()
        compiler_version = _one_line(execute((str(compiler_path), "/Bv", "/?"), root), "MSVC version")
        linker_version = _one_line(execute((str(linker_path), "/?"), root), "MSVC linker version")
        family = "msvc"
        target = "x86_64-pc-windows-msvc"
        platform_version = _identity(environment.get("VCToolsVersion", ""), "MSVC toolset version")
        platform_build = _identity(environment.get("WindowsSDKVersion", "").rstrip("\\/"), "Windows SDK version")
    else:
        compiler_version = _one_line(execute((str(compiler_path), "--version"), root), "compiler version")
        target = _one_line(execute((str(compiler_path), "-dumpmachine"), root), "compiler target")
        linker_value = _one_line(execute((str(compiler_path), "-print-prog-name=ld"), root), "linker path")
        linker_path_value = linker_value if os.path.isabs(linker_value) else find_executable(linker_value)
        if linker_path_value is None:
            raise ValueError("Supervisor linker is missing")
        linker_path = Path(linker_path_value).resolve()
        linker_version = _one_line(
            execute((str(linker_path), "-v" if runner_os == "macOS" else "--version"), root),
            "linker version",
        )
        if runner_os == "macOS":
            family = "apple-clang"
            xcode = _one_line(execute(("xcodebuild", "-version"), root), "Xcode version")
            sdk_version = _one_line(
                execute(("xcrun", "--sdk", "macosx", "--show-sdk-version"), root),
                "macOS SDK version",
            )
            sdk_build = _one_line(
                execute(("xcrun", "--sdk", "macosx", "--show-sdk-build-version"), root),
                "macOS SDK build",
            )
            platform_version = f"{xcode};macOS SDK {sdk_version}"
            platform_build = sdk_build
        else:
            family = compiler_path.name
            platform_version = "none"
            platform_build = "none"
    return {
        "compilerBinarySha256": _sha256_file(compiler_path, "Supervisor compiler"),
        "compilerVersion": compiler_version,
        "family": family,
        "linkerBinarySha256": _sha256_file(linker_path, "Supervisor linker"),
        "linkerVersion": linker_version,
        "platformBuild": platform_build,
        "platformVersion": platform_version,
        "target": target,
    }


def observe_producer(
    repository_root: Path,
    repository_revision: str,
    profile_id: str,
    producer_role: str,
    target: str,
    *,
    gradle_user_home: Path | None = None,
    konan_data_dir: Path | None = None,
    supervisor_compiler: str | None = None,
    environment: Mapping[str, str] = os.environ,
    execute: Callable[[tuple[str, ...], Path], str] = _command,
    find_executable: Callable[[str], str | None] = shutil.which,
) -> dict[str, Any]:
    root = Path(repository_root).resolve()
    revision = _revision(repository_revision)
    selected = require_identifier(profile_id, "Toolchain profile ID")
    if selected not in PROFILE_SHAPES or target != selected:
        raise ValueError("Toolchain observation target does not match a supported profile")
    roles = {role: (runner_os, runner_arch) for role, runner_os, runner_arch in PROFILE_SHAPES[selected]}
    if producer_role not in roles:
        raise ValueError("Toolchain observation producer role does not match its profile")
    runner_os = _identity(environment.get("RUNNER_OS", ""), "RUNNER_OS")
    runner_arch = _identity(environment.get("RUNNER_ARCH", ""), "RUNNER_ARCH")
    if (runner_os, runner_arch) != roles[producer_role]:
        raise ValueError("Actual runner does not match the selected toolchain producer")
    expected_names = PROFILE_TOOL_NAMES[(selected, producer_role)]

    wrapper = _properties(_authority(root, revision, WRAPPER_PROPERTIES), "Gradle wrapper properties")
    wrapper_sha = wrapper.get("distributionSha256Sum", "")
    if re.fullmatch(r"[0-9a-f]{64}", wrapper_sha) is None:
        raise ValueError("Gradle wrapper distribution checksum is missing or invalid")
    wrapper_executable = root / ("gradlew.bat" if runner_os == "Windows" else "gradlew")
    launcher_sha = sha256_bytes(_authority(root, revision, wrapper_executable.name))
    gradle_output = execute((str(wrapper_executable), "--version", "--no-daemon"), root)
    gradle = {
        "distributionSha256": f"sha256:{wrapper_sha}",
        "launcherSha256": launcher_sha,
        "version": _match(r"^Gradle ([^\s]+)$", gradle_output, "Gradle version"),
    }
    distribution = wrapper.get("distributionUrl", "")
    distribution_match = re.search(r"/gradle-([^/]+)-(?:bin|all)\.zip$", distribution)
    if distribution_match is None or gradle["version"] != distribution_match.group(1):
        raise ValueError("Observed Gradle version does not match the exact wrapper distribution")
    java_path_value = find_executable("java")
    if java_path_value is None:
        raise ValueError("Java runtime is missing")
    java_path = Path(java_path_value).resolve()
    java_output = execute((str(java_path), "-XshowSettings:properties", "-version"), root)
    observations = {
        "gradleWrapper": gradle,
        "javaRuntime": {
            "arch": _match(r"^\s*os\.arch = (.+)$", java_output, "Java architecture"),
            "binarySha256": _sha256_file(java_path, "Java runtime"),
            "runtimeVersion": _match(r"^\s*java\.runtime\.version = (.+)$", java_output, "Java runtime"),
            "vendor": _match(r"^\s*java\.vendor = (.+)$", java_output, "Java vendor"),
            "vendorVersion": _match(r"^\s*java\.vendor\.version = (.+)$", java_output, "Java vendor version"),
            "vmName": _match(r"^\s*java\.vm\.name = (.+)$", java_output, "Java VM name"),
            "vmVersion": _match(r"^\s*java\.vm\.version = (.+)$", java_output, "Java VM version"),
        },
    }
    if "kotlinPlugin" in expected_names:
        catalog = tomllib.loads(_authority(root, revision, VERSION_CATALOG).decode("utf-8"))
        kotlin_version = catalog.get("versions", {}).get("kotlin")
        if type(kotlin_version) is not str:
            raise ValueError("Kotlin plugin version is missing from the exact catalog")
        metadata = _authority(root, revision, RUNTIME_VERIFICATION_METADATA)
        gradle_home = Path(
            gradle_user_home or environment.get("GRADLE_USER_HOME", Path.home() / ".gradle")
        ).resolve()
        kgp_root = (
            gradle_home
            / "caches/modules-2/files-2.1/org.jetbrains.kotlin/kotlin-gradle-plugin"
            / kotlin_version
        )
        kgp_matches = sorted(path for path in
            kgp_root.rglob(f"kotlin-gradle-plugin-{kotlin_version}-*.jar")
            if not path.name.endswith(("-sources.jar", "-javadoc.jar"))
        ) if kgp_root.is_dir() else []
        if len(kgp_matches) != 1:
            raise ValueError("Kotlin plugin cache must contain exactly one resolved implementation jar")
        kgp_name = kgp_matches[0].name
        kgp_sha = _sha256_file(kgp_matches[0], "Kotlin plugin")
        if _metadata_checksum(metadata, kgp_name) != kgp_sha:
            raise ValueError("Kotlin plugin cache does not match Runtime verification metadata")
        observations["kotlinPlugin"] = {
            "artifactName": kgp_name,
            "artifactSha256": kgp_sha,
            "version": kotlin_version,
        }
    if "kotlinNativeCompiler" in expected_names:
        host, classifier = HOSTS[(runner_os, runner_arch)]
        native_target = TARGETS[selected]
        konan_root = Path(konan_data_dir or environment.get("KONAN_DATA_DIR", Path.home() / ".konan")).resolve()
        compiler_home = konan_root / f"kotlin-native-prebuilt-{classifier}-{kotlin_version}"
        if not compiler_home.is_dir() or compiler_home.is_symlink():
            raise ValueError("Kotlin/Native compiler cache is missing or unsafe")
        extension = "zip" if runner_os == "Windows" else "tar.gz"
        archive_name = f"kotlin-native-prebuilt-{kotlin_version}-{classifier}.{extension}"
        archive_root = gradle_home / "caches/modules-2/files-2.1/org.jetbrains.kotlin/kotlin-native-prebuilt" / kotlin_version
        archive = _unique_file(archive_root, archive_name, "Kotlin/Native archive")
        archive_sha = _sha256_file(archive, "Kotlin/Native archive")
        if _metadata_checksum(metadata, archive_name) != archive_sha:
            raise ValueError("Kotlin/Native archive does not match Runtime verification metadata")
        konanc = compiler_home / "bin" / ("konanc.bat" if runner_os == "Windows" else "konanc")
        compiler_output = execute((str(konanc), "-version"), root)
        properties_path = compiler_home / "konan/konan.properties"
        properties = _properties(
            read_regular_file_bytes(properties_path, max_bytes=1024 * 1024, reject_symlink_parents=True),
            "Kotlin/Native properties",
        )
        fingerprint = read_regular_file_bytes(
            compiler_home / "konan/compiler.fingerprint",
            max_bytes=1024,
            reject_symlink_parents=True,
        ).decode("ascii").strip()
        if HEX_FINGERPRINT.fullmatch(fingerprint) is None:
            raise ValueError("Kotlin/Native compiler fingerprint is invalid")
        observations["kotlinNativeCompiler"] = {
            "archiveName": archive_name,
            "archiveSha256": archive_sha,
            "compilerFingerprint": fingerprint,
            "compilerTreeSha256": _tree_digest(compiler_home, "Kotlin/Native compiler"),
            "compilerVersion": _match(r"^Kotlin/Native: ([^\s]+)$", compiler_output, "Kotlin/Native version"),
            "host": host,
        }
        if observations["kotlinNativeCompiler"]["compilerVersion"] != kotlin_version:
            raise ValueError("Kotlin/Native compiler version does not match the Kotlin plugin")
        observations["konanDependencies"] = _konan_dependencies(
            properties, host, native_target, konan_root / "dependencies",
        )
    if "supervisorCompiler" in expected_names:
        observations["supervisorCompiler"] = _supervisor_observation(
            root,
            runner_os,
            supervisor_compiler or ("cl" if runner_os == "Windows" else "cc"),
            environment,
            execute,
            find_executable,
        )
    records = [_tool_observation(name, observations[name]) for name in sorted(observations)]
    if tuple(record["name"] for record in records) != expected_names:
        raise ValueError("Observed tools do not match the exact producer tool set")
    producer = {
        "role": producer_role,
        "runner": {"arch": runner_arch, "os": runner_os},
        "tools": [{"identity": record["identity"], "name": record["name"]} for record in records],
    }
    tree = run_git(root, "rev-parse", f"{revision}^{{tree}}").strip()
    if GIT_OBJECT_ID.fullmatch(tree) is None:
        raise ValueError("Repository tree is not an exact Git object ID")
    return {
        "imageProvenance": {
            "image": _identity(environment.get("ImageOS", "unavailable"), "runner image"),
            "imageVersion": _identity(environment.get("ImageVersion", "unavailable"), "runner image version"),
        },
        "producer": producer,
        "profileId": selected,
        "repositoryRevision": revision,
        "repositoryTree": tree,
        "schemaVersion": 1,
        "toolObservations": records,
    }


def validate_producer_observation(value: Any) -> dict[str, Any]:
    record = require_exact_keys(value, {
        "imageProvenance", "producer", "profileId", "repositoryRevision", "repositoryTree",
        "schemaVersion", "toolObservations",
    }, "Toolchain producer observation")
    if require_integer(record["schemaVersion"], "Toolchain producer observation.schemaVersion", 1) != 1:
        raise ValueError("Unsupported toolchain producer observation schemaVersion")
    profile_id = require_identifier(record["profileId"], "Toolchain producer observation.profileId")
    if profile_id not in PROFILE_SHAPES:
        raise ValueError("Toolchain producer observation profile is unsupported")
    _revision(record["repositoryRevision"])
    _revision(record["repositoryTree"])
    image = require_exact_keys(record["imageProvenance"], {"image", "imageVersion"}, "Image provenance")
    _validate_image_provenance(image)
    producer = require_exact_keys(record["producer"], {"role", "runner", "tools"}, "Observed producer")
    role = producer["role"]
    runner_os, runner_arch = _runner(producer["runner"], "Observed producer.runner")
    if (role, runner_os, runner_arch) not in PROFILE_SHAPES[profile_id]:
        raise ValueError("Observed producer topology does not match its profile")
    tools = _tools(producer["tools"], "Observed producer.tools")
    detailed = [
        _validate_tool_record(member, f"Toolchain observation[{index}]")
        for index, member in enumerate(require_array(record["toolObservations"], "Toolchain observations"))
    ]
    expected = PROFILE_TOOL_NAMES[(profile_id, role)]
    if (
        tuple(member["name"] for member in detailed) != expected
        or tools != tuple((member["name"], member["identity"]) for member in detailed)
    ):
        raise ValueError("Observed tool details do not match the exact producer tools")
    return record


def assemble_profile(observations: list[dict[str, Any]], profile_id: str) -> dict[str, Any]:
    selected = require_identifier(profile_id, "Toolchain profile ID")
    if selected not in PROFILE_SHAPES:
        raise ValueError("Toolchain profile ID is unsupported")
    records = [validate_producer_observation(value) for value in observations]
    if any(record["profileId"] != selected for record in records):
        raise ValueError("Producer observation belongs to a different profile")
    if len({(record["repositoryRevision"], record["repositoryTree"]) for record in records}) != 1:
        raise ValueError("Producer observations do not bind one exact repository revision and tree")
    producers = sorted((record["producer"] for record in records), key=lambda value: value["role"])
    profile = {"id": selected, "producers": producers, "schemaVersion": SCHEMA_VERSION}
    validate_toolchain_profile(profile, sha256_bytes(canonical_json_bytes(profile)))
    return profile


def _binary_plan(value: Any, profile_id: str) -> dict[str, Any]:
    from .receipt import compute_build_key, validate_receipt_inputs
    from .runtime_identity import validate_runtime_identity

    values = require_exact_keys(value, {
        "buildKey", "component", "inputs", "phase", "product", "runtimeBinaryIdentity",
        "schemaVersion", "target",
    }, "Runtime binary plan")
    if (
        values["schemaVersion"] != 1
        or values["product"] != "runtime"
        or values["component"] != profile_id
        or values["phase"] != "binary"
        or values["target"] != profile_id
    ):
        raise ValueError("Runtime binary plan identity does not match the selected profile")
    inputs = validate_receipt_inputs(values["inputs"])
    expected_key = compute_build_key(
        product="runtime", component=profile_id, phase="binary", target=profile_id, inputs=inputs,
    )
    if values["buildKey"] != expected_key:
        raise ValueError("Runtime binary plan build key is invalid")
    identity = validate_runtime_identity(values["runtimeBinaryIdentity"])
    if (
        identity["target"] != profile_id
        or identity["binaryBuildKey"] != values["buildKey"]
        or identity["runtimeCompatibilityVersion"] != inputs["versionIdentity"]
        or identity["toolchainProfile"] != {
            "id": profile_id,
            "digest": inputs["toolchainProfileDigest"],
        }
    ):
        raise ValueError("Runtime binary plan identity does not match its canonical inputs")
    return values


def _verification_record(
    repository_root: Path,
    repository_revision: str,
    binary_plan: Any,
    observation: dict[str, Any],
) -> dict[str, Any]:
    root = Path(repository_root).resolve()
    revision = _revision(repository_revision)
    record = validate_producer_observation(observation)
    if record["repositoryRevision"] != revision:
        raise ValueError("Toolchain observation revision does not match the requested revision")
    actual_tree = run_git(root, "rev-parse", f"{revision}^{{tree}}").strip()
    if record["repositoryTree"] != actual_tree:
        raise ValueError("Toolchain observation tree does not match the requested revision")
    profile_id = record["profileId"]
    plan = _binary_plan(binary_plan, profile_id)
    profile_bytes = git_regular_blob_bytes(
        root, revision, f"{PROFILE_ROOT}/{profile_id}.json", max_bytes=65_536,
    )
    checked_out = read_regular_file_bytes(
        root / PROFILE_ROOT / f"{profile_id}.json", max_bytes=65_536, reject_symlink_parents=True,
    )
    if checked_out != profile_bytes:
        raise ValueError("Checked-out toolchain profile differs from the exact Git revision")
    profile = load_toolchain_profile_bytes(profile_bytes, profile_id)
    producer = record["producer"]
    verify_toolchain_profile(
        profile,
        plan["inputs"]["toolchainProfileDigest"],
        producer["role"],
        producer["runner"],
        {tool["name"]: tool["identity"] for tool in producer["tools"]},
        image_provenance=record["imageProvenance"],
    )
    return {
        **record,
        "profileDigest": profile.digest,
        "schemaVersion": 1,
    }


def validate_verification_record(value: Any) -> dict[str, Any]:
    record = require_exact_keys(value, {
        "imageProvenance", "producer", "profileDigest", "profileId", "repositoryRevision",
        "repositoryTree", "schemaVersion", "toolObservations",
    }, "Toolchain verification record")
    require_sha256(record["profileDigest"], "Toolchain verification record.profileDigest")
    observation = {key: value for key, value in record.items() if key != "profileDigest"}
    validate_producer_observation(observation)
    return record


def verify_capture(
    directory: Path,
    repository_revision: str,
    repository_tree: str,
) -> None:
    root = Path(directory)
    revision, tree = _revision(repository_revision), _revision(repository_tree)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("Toolchain capture directory is missing or unsafe")
    expected = {f"profiles/{profile_id}.json" for profile_id in PROFILE_SHAPES}
    expected.update(
        f"observations/{profile_id}/{role}.json"
        for profile_id, shapes in PROFILE_SHAPES.items()
        for role, _, _ in shapes
    )
    actual = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() or path.is_symlink()
    }
    if actual != expected:
        raise ValueError("Toolchain capture file inventory is not exact")
    for profile_id, shapes in PROFILE_SHAPES.items():
        observations = []
        for role, _, _ in shapes:
            path = root / "observations" / profile_id / f"{role}.json"
            value = validate_producer_observation(load_canonical_json_bytes(read_regular_file_bytes(
                path, max_bytes=1024 * 1024, reject_symlink_parents=True,
            )))
            if value["repositoryRevision"] != revision or value["repositoryTree"] != tree:
                raise ValueError("Toolchain capture provenance does not match the requested revision/tree")
            observations.append(value)
        expected_profile = canonical_json_bytes(assemble_profile(observations, profile_id))
        actual_profile = read_regular_file_bytes(
            root / "profiles" / f"{profile_id}.json", max_bytes=65_536, reject_symlink_parents=True,
        )
        if actual_profile != expected_profile:
            raise ValueError("Captured toolchain profile does not match its exact producer observations")


def _remove_output(value: str | None) -> None:
    if value is None:
        return
    path = Path(value)
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return
    if stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        path.unlink()


def _write(path: str, value: Any) -> None:
    _remove_output(path)
    write_canonical_json(Path(path), value)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python3 -m ci.products.toolchain")
    commands = parser.add_subparsers(dest="command", required=True)
    observe = commands.add_parser("observe-producer")
    verify = commands.add_parser("verify-producer")
    for command in (observe, verify):
        command.add_argument("--repository-root", required=True)
        command.add_argument("--repository-revision", required=True)
        command.add_argument("--profile-id", required=True)
        command.add_argument("--producer-role", required=True)
        command.add_argument("--target", required=True)
        command.add_argument("--gradle-user-home")
        command.add_argument("--konan-data-dir")
        command.add_argument("--supervisor-compiler")
        command.add_argument("--output", required=True)
    verify.add_argument("--binary-plan", required=True)
    verify.add_argument("--verified-contract-manifest", required=True)
    verify.add_argument("--expected-runtime-version", required=True)
    verify.add_argument("--expected-flags-digest", required=True)
    assemble = commands.add_parser("assemble-profile")
    assemble.add_argument("--profile-id", required=True)
    assemble.add_argument("--producer", action="append", required=True)
    assemble.add_argument("--output", required=True)
    record = commands.add_parser("verify-record")
    record.add_argument("--repository-root", required=True)
    record.add_argument("--repository-revision", required=True)
    record.add_argument("--profile-id", required=True)
    record.add_argument("--binary-plan", required=True)
    record.add_argument("--verified-contract-manifest", required=True)
    record.add_argument("--expected-runtime-version", required=True)
    record.add_argument("--expected-flags-digest", required=True)
    record.add_argument("--record", required=True)
    record.add_argument("--output")
    capture = commands.add_parser("verify-capture")
    capture.add_argument("--directory", required=True)
    capture.add_argument("--repository-revision", required=True)
    capture.add_argument("--repository-tree", required=True)
    return parser


def _read_observation(path: str) -> dict[str, Any]:
    return validate_producer_observation(load_canonical_json_bytes(read_regular_file_bytes(
        Path(path), max_bytes=1024 * 1024, reject_symlink_parents=True,
    )))


def _read_json(path: str) -> dict[str, Any]:
    return load_canonical_json_bytes(read_regular_file_bytes(
        Path(path), max_bytes=16 * 1024 * 1024, reject_symlink_parents=True,
    ))


def _verified_binary_plan(arguments: argparse.Namespace) -> dict[str, Any]:
    from .runtime_identity import verify_runtime_binary_plan

    plan = _read_json(arguments.binary_plan)
    manifest = _read_json(arguments.verified_contract_manifest)
    verify_runtime_binary_plan(
        Path(arguments.repository_root),
        arguments.repository_revision,
        plan,
        manifest,
        expected_target=arguments.profile_id,
        expected_runtime_version=arguments.expected_runtime_version,
        expected_flags_digest=arguments.expected_flags_digest,
    )
    return plan


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    arguments = parser.parse_args(argv)
    output = getattr(arguments, "output", None)
    try:
        if arguments.command in {"observe-producer", "verify-producer"}:
            plan = _verified_binary_plan(arguments) if arguments.command == "verify-producer" else None
            observation = observe_producer(
                Path(arguments.repository_root),
                arguments.repository_revision,
                arguments.profile_id,
                arguments.producer_role,
                arguments.target,
                gradle_user_home=Path(arguments.gradle_user_home) if arguments.gradle_user_home else None,
                konan_data_dir=Path(arguments.konan_data_dir) if arguments.konan_data_dir else None,
                supervisor_compiler=arguments.supervisor_compiler,
            )
            value = observation if arguments.command == "observe-producer" else _verification_record(
                Path(arguments.repository_root), arguments.repository_revision,
                plan, observation,
            )
            _write(arguments.output, value)
        elif arguments.command == "assemble-profile":
            _write(arguments.output, assemble_profile(
                [_read_observation(path) for path in arguments.producer], arguments.profile_id,
            ))
        elif arguments.command == "verify-record":
            plan = _verified_binary_plan(arguments)
            value = validate_verification_record(load_canonical_json_bytes(read_regular_file_bytes(
                Path(arguments.record), max_bytes=1024 * 1024, reject_symlink_parents=True,
            )))
            observation = {key: member for key, member in value.items() if key != "profileDigest"}
            verified = _verification_record(
                Path(arguments.repository_root), arguments.repository_revision,
                plan, observation,
            )
            if verified != value:
                raise ValueError("Toolchain verification record does not match current authorities")
            if arguments.output:
                _write(arguments.output, value)
        else:
            verify_capture(Path(arguments.directory), arguments.repository_revision, arguments.repository_tree)
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        _remove_output(output)
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
