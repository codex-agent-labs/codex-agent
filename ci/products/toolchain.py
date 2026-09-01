from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Any

from .inventory import (
    canonical_json_bytes,
    load_canonical_json_bytes,
    read_regular_file_bytes,
    require_array,
    require_exact_keys,
    require_identifier,
    require_integer,
    require_sha256,
    sha256_bytes,
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
