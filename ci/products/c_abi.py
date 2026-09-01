"""Canonical raw Runtime C ABI packages and package evidence."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from types import MappingProxyType
from typing import Any, Iterable, Mapping
import zipfile

from .inventory import (
    canonical_json_bytes,
    load_canonical_json_bytes,
    load_json_bytes,
    read_regular_file_bytes,
    require_exact_keys,
    require_integer,
    verified_zip_contents,
)


C_ABI_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
C_ABI_CONTRACT_PATH = (
    C_ABI_REPOSITORY_ROOT / "codex-agent-runtime-desktop/native/c-api/abi-contract.json"
)
C_ABI_REVIEWED_HEADER_PATH = (
    C_ABI_REPOSITORY_ROOT / "codex-agent-runtime-desktop/native/c-api/include/codex_agent.h"
)
C_ABI_REVIEWED_EXPORT_PATHS = MappingProxyType({
    "elf": C_ABI_REPOSITORY_ROOT / "codex-agent-runtime-desktop/native/c-api/exports/linux.map",
    "mach-o": C_ABI_REPOSITORY_ROOT / "codex-agent-runtime-desktop/native/c-api/exports/macos.exports",
    "pe": C_ABI_REPOSITORY_ROOT / "codex-agent-runtime-desktop/native/c-api/exports/windows.def",
})
C_ABI_PACKAGE_MANIFEST = "codex-agent-c-abi-manifest.json"
C_ABI_HEADER_PATH = "include/codex_agent.h"
C_ABI_STAGED_EVIDENCE_PATH = "codex-agent-c-abi-evidence.json"
C_ABI_FILE_MODE = stat.S_IFREG | 0o644
C_ABI_ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)

_SYMBOL = re.compile(r"(?<![A-Za-z0-9_])(_?codex_agent_[A-Za-z0-9_]+)(?![A-Za-z0-9_])")
_HEADER_SYMBOL = re.compile(r"\b(codex_agent_[A-Za-z0-9_]+)\s*\(")
_HEADER_INTEGER_MACRO = re.compile(
    r"^#define[ \t]+(?P<name>CODEX_AGENT_ABI_VERSION_(?:MAJOR|MINOR|PATCH))"
    r"[ \t]+UINT32_C\((?P<value>[0-9]+)\)[ \t]*$",
    re.MULTILINE,
)
_HEADER_CURRENT_MACRO = re.compile(
    r"^#define[ \t]+CODEX_AGENT_ABI_VERSION_CURRENT[ \t]+"
    r"CODEX_AGENT_ABI_VERSION_ENCODE\([ \t]*CODEX_AGENT_ABI_VERSION_MAJOR[ \t]*,[ \t]*"
    r"CODEX_AGENT_ABI_VERSION_MINOR[ \t]*,[ \t]*CODEX_AGENT_ABI_VERSION_PATCH[ \t]*\)[ \t]*$",
    re.MULTILINE,
)
_HEADER_MINIMUM_MACRO = re.compile(
    r"^#define[ \t]+CODEX_AGENT_ABI_VERSION_MINIMUM_COMPATIBLE[ \t]+"
    r"CODEX_AGENT_ABI_VERSION_ENCODE\([ \t]*(?P<major>[0-9]+)[ \t]*,[ \t]*"
    r"(?P<minor>[0-9]+)[ \t]*,[ \t]*(?P<patch>[0-9]+)[ \t]*\)[ \t]*$",
    re.MULTILINE,
)
_HEADER_AUTHORITY_DEFINE = re.compile(
    r"^#define[ \t]+(?P<name>CODEX_AGENT_ABI_VERSION_"
    r"(?:MAJOR|MINOR|PATCH|CURRENT|MINIMUM_COMPATIBLE))\b.*$",
    re.MULTILINE,
)


@dataclass(frozen=True)
class CAbiVersion:
    major: int
    minor: int
    patch: int

    @property
    def semver(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    @property
    def line(self) -> str:
        return f"{self.major}.{self.minor}"

    @property
    def encoded(self) -> int:
        return (self.major << 24) | (self.minor << 16) | self.patch

    @property
    def encoded_hex(self) -> str:
        return f"0x{self.encoded:08x}"


@dataclass(frozen=True)
class CAbiContract:
    current: CAbiVersion
    minimum_compatible: CAbiVersion
    runtime_identity_schema_version: int


def _abi_version(value: Any, label: str) -> CAbiVersion:
    record = require_exact_keys(value, {"major", "minor", "patch"}, label)
    major = require_integer(record["major"], f"{label}.major", 1)
    minor = require_integer(record["minor"], f"{label}.minor")
    patch = require_integer(record["patch"], f"{label}.patch")
    if major > 0xFF or minor > 0xFF or patch > 0xFFFF:
        raise ValueError(f"{label} cannot be represented by CODEX_AGENT_ABI_VERSION_ENCODE")
    return CAbiVersion(major, minor, patch)


def load_c_abi_contract(path: Path) -> CAbiContract:
    contents = read_regular_file_bytes(
        Path(path),
        max_bytes=4096,
    )
    value = require_exact_keys(
        load_canonical_json_bytes(contents),
        {"schemaVersion", "current", "minimumCompatible", "runtimeIdentitySchemaVersion"},
        "C ABI contract",
    )
    if require_integer(value["schemaVersion"], "C ABI contract.schemaVersion", 1) != 1:
        raise ValueError("Unsupported C ABI contract schemaVersion")
    current = _abi_version(value["current"], "C ABI contract.current")
    minimum = _abi_version(value["minimumCompatible"], "C ABI contract.minimumCompatible")
    if minimum.major != current.major or (
        minimum.major, minimum.minor, minimum.patch
    ) > (current.major, current.minor, current.patch):
        raise ValueError("C ABI contract minimumCompatible is not on or below the current ABI line")
    identity_schema = require_integer(
        value["runtimeIdentitySchemaVersion"],
        "C ABI contract.runtimeIdentitySchemaVersion",
        1,
    )
    if identity_schema > 0xFFFFFFFF:
        raise ValueError("C ABI contract runtimeIdentitySchemaVersion is out of range")
    return CAbiContract(current, minimum, identity_schema)


def _version_document(version: CAbiVersion) -> dict[str, Any]:
    return {
        "major": version.major,
        "minor": version.minor,
        "patch": version.patch,
        "semver": version.semver,
        "line": version.line,
        "encoded": version.encoded_hex,
    }


def describe_c_abi_contract(path: Path) -> dict[str, Any]:
    contract = load_c_abi_contract(path)
    return {
        "schemaVersion": 1,
        "current": _version_document(contract.current),
        "minimumCompatible": _version_document(contract.minimum_compatible),
        "runtimeIdentitySchemaVersion": contract.runtime_identity_schema_version,
    }


def _policy_symbols(path: Path, label: str) -> frozenset[str]:
    try:
        text = read_regular_file_bytes(
            Path(path),
            max_bytes=4 * 1024 * 1024,
        ).decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ValueError(f"{label} is not UTF-8") from error
    occurrences = [match.group(1).removeprefix("_") for match in _SYMBOL.finditer(text)]
    if not occurrences:
        raise ValueError(f"{label} contains no public C ABI symbols")
    if len(occurrences) != len(set(occurrences)):
        raise ValueError(f"{label} contains duplicate public C ABI symbols")
    return frozenset(occurrences)


def _reviewed_symbol_set(paths: Mapping[str, Path]) -> frozenset[str]:
    if type(paths) not in {dict, MappingProxyType} or set(paths) != {"mach-o", "elf", "pe"}:
        raise ValueError("Reviewed C ABI export policies must contain exactly mach-o, elf, and pe")
    by_format = {
        format: _policy_symbols(path, f"C ABI {format} export policy")
        for format, path in paths.items()
    }
    first = by_format["mach-o"]
    if any(symbols != first for symbols in by_format.values()):
        raise ValueError("Reviewed C ABI export policy symbol sets differ")
    return first


@lru_cache(maxsize=1)
def _repository_contract() -> CAbiContract:
    return load_c_abi_contract(C_ABI_CONTRACT_PATH)


@lru_cache(maxsize=1)
def _repository_symbol_set() -> frozenset[str]:
    return _reviewed_symbol_set(C_ABI_REVIEWED_EXPORT_PATHS)


def __getattr__(name: str) -> Any:
    """Retain legacy imports without reading repository authorities at module import."""
    contract = None
    if name in {
        "C_ABI_CONTRACT",
        "C_ABI_CURRENT",
        "C_ABI_CURRENT_SEMVER",
        "C_ABI_MINIMUM",
        "C_ABI_MINIMUM_SEMVER",
        "C_ABI_ENCODED",
        "C_ABI_MINIMUM_ENCODED",
        "C_ABI_IDENTITY_SCHEMA_VERSION",
    }:
        contract = _repository_contract()
    values = {
        "C_ABI_CONTRACT": contract,
        "C_ABI_CURRENT": contract.current.line if contract else None,
        "C_ABI_CURRENT_SEMVER": contract.current.semver if contract else None,
        "C_ABI_MINIMUM": contract.minimum_compatible.line if contract else None,
        "C_ABI_MINIMUM_SEMVER": contract.minimum_compatible.semver if contract else None,
        "C_ABI_ENCODED": contract.current.encoded_hex if contract else None,
        "C_ABI_MINIMUM_ENCODED": contract.minimum_compatible.encoded_hex if contract else None,
        "C_ABI_IDENTITY_SCHEMA_VERSION": (
            contract.runtime_identity_schema_version if contract else None
        ),
        "C_ABI_SYMBOL_COUNT": len(_repository_symbol_set()) if name == "C_ABI_SYMBOL_COUNT" else None,
    }
    if name not in values:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return values[name]


@dataclass(frozen=True)
class CAbiTargetSpec:
    target: str
    classifier: str
    runner_os: str
    runner_arch: str
    format: str
    architecture: str
    library_path: str
    loader_identity: str
    import_library_paths: tuple[str, ...] = ()

    @property
    def proof_id(self) -> str:
        return f"c-abi-package-{self.classifier.removeprefix('c-abi-')}"

    @property
    def version_identity(self) -> str:
        contract = _repository_contract()
        if self.format == "mach-o":
            return (
                f"compatibility={contract.minimum_compatible.semver},"
                f"current={contract.current.semver}"
            )
        if self.format == "elf":
            return ",".join(_expected_linux_version_nodes(contract))
        return f"abi={contract.current.line}"

    @property
    def required_tool_ids(self) -> frozenset[str]:
        if self.format in {"mach-o", "elf"}:
            return frozenset({"c", "cpp", "file", "architecture", "symbols", "loader", "versions"})
        return frozenset({"c", "cpp", "gnuC", "gnuCpp", "architecture", "symbols", "msvcImport", "gnuImport"})


TARGET_SPECS: Mapping[str, CAbiTargetSpec] = MappingProxyType({
    spec.target: spec
    for spec in (
        CAbiTargetSpec(
            "macosArm64", "c-abi-macos-arm64", "macOS", "ARM64", "mach-o", "arm64",
            "lib/libcodex_agent.dylib", "@rpath/libcodex_agent.dylib",
        ),
        CAbiTargetSpec(
            "macosX64", "c-abi-macos-x64", "macOS", "X64", "mach-o", "x86_64",
            "lib/libcodex_agent.dylib", "@rpath/libcodex_agent.dylib",
        ),
        CAbiTargetSpec(
            "linuxArm64", "c-abi-linux-arm64", "Linux", "ARM64", "elf", "aarch64",
            "lib/libcodex_agent.so", "libcodex_agent.so.1",
        ),
        CAbiTargetSpec(
            "linuxX64", "c-abi-linux-x64", "Linux", "X64", "elf", "x86_64",
            "lib/libcodex_agent.so", "libcodex_agent.so.1",
        ),
        CAbiTargetSpec(
            "mingwX64", "c-abi-windows-x64", "Windows", "X64", "pe", "x86_64",
            "bin/codex_agent.dll", "codex_agent.dll",
            ("lib/libcodex_agent.dll.a", "lib/codex_agent.lib"),
        ),
    )
})

COMPILE_ONLY_CONSUMERS = frozenset({"codex_agent_lifecycle_compile.cpp"})
STRICT_CONSUMERS = frozenset({
    "codex_agent_abi_smoke.c",
    "codex_agent_authentication_configuration_values_compile.c",
    "codex_agent_configuration_values_compile.c",
    "codex_agent_conversation_aggregate_values_compile.c",
    "codex_agent_conversation_values_compile.c",
    "codex_agent_elicitation_behavior_values_compile.c",
    "codex_agent_elicitation_interaction_values_compile.c",
    "codex_agent_form_hook_values_compile.c",
    "codex_agent_header_smoke.cpp",
    "codex_agent_hook_catalog_values_compile.c",
    "codex_agent_integration_mcp_values_compile.c",
    "codex_agent_integration_state_values_compile.c",
    "codex_agent_integration_values_compile.c",
    "codex_agent_interaction_identity_compile.c",
    "codex_agent_invocation_auth_values_compile.c",
    "codex_agent_lifecycle_compile.c",
    "codex_agent_lifecycle_compile.cpp",
    "codex_agent_list_leaf_values_compile.c",
    "codex_agent_mcp_server_configuration_values_compile.c",
    "codex_agent_mcp_server_values_compile.c",
    "codex_agent_mcp_transport_values_compile.c",
    "codex_agent_ordinary_enums_compile.c",
    "codex_agent_progress_list_values_compile.c",
    "codex_agent_resource_list_values_compile.c",
    "codex_agent_resource_values_compile.c",
    "codex_agent_root_value_accessors_compile.c",
    "codex_agent_sealed_base_property_values_compile.c",
    "codex_agent_service_handles_compile.c",
    "codex_agent_state_flows_compile.c",
    "codex_agent_suspend_operations_compile.c",
})
GNU_CONSUMERS = frozenset({"codex_agent_abi_smoke.c", "codex_agent_header_smoke.cpp"})
HOST_MAPPINGS = (
    ("mac", ("aarch64", "arm64"), "macosArm64"),
    ("mac", ("amd64", "x86_64"), "macosX64"),
    ("linux", ("aarch64", "arm64"), "linuxArm64"),
    ("linux", ("amd64", "x86_64"), "linuxX64"),
    ("windows", ("amd64", "x86_64"), "mingwX64"),
)


@dataclass(frozen=True)
class CAbiPackageInput:
    target: str
    classifier: str
    library_version: str
    producer_commit: str
    producer_tree: str
    reviewed_header: Path
    license: Path
    notice: Path
    library: Path
    export_policy: Path
    gnu_import_library: Path | None = None
    msvc_import_library: Path | None = None


@dataclass(frozen=True)
class CAbiPackageSnapshot:
    target: str
    classifier: str
    archive_sha256: str
    header_sha256: str
    library_sha256: str
    public_symbols_sha256: str
    members: Mapping[str, str]


@dataclass(frozen=True)
class CAbiConsumerProof:
    source: str
    source_sha256: str
    language: str
    compiler_identity_sha256: str
    compile_output_sha256: str
    artifact_sha256: str
    linked: bool
    executed: bool
    exit_code: int


@dataclass(frozen=True)
class CAbiEvidenceValues:
    target: str
    classifier: str
    library_version: str
    producer_commit: str
    producer_tree: str
    runner_os: str
    runner_arch: str
    archive_sha256: str
    header_sha256: str
    library_sha256: str
    public_symbols: frozenset[str]
    public_symbol_versions: Mapping[str, str]
    format: str
    architecture: str
    loader_identity: str
    version_identity: str
    import_libraries: Mapping[str, str]
    tool_proofs: Mapping[str, str]
    consumers: tuple[CAbiConsumerProof, ...]
    gnu_consumers: tuple[CAbiConsumerProof, ...] = ()


@dataclass(frozen=True)
class _PackageMember:
    path: str
    role: str
    contents: bytes

    @property
    def sha256(self) -> str:
        return _sha256(self.contents)


_LINUX_VERSION_NODE = re.compile(r"^(CODEX_AGENT_[0-9]+\.[0-9]+) \{$")
_LINUX_VERSION_SYMBOL = re.compile(r"^(codex_agent_[A-Za-z0-9_]+);$")
_VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?")
_GIT_ID = re.compile(r"[0-9a-f]{40}")
_SHA256 = re.compile(r"[0-9a-f]{64}")


def c_abi_host_target(os_name: str, os_arch: str) -> str | None:
    operating_system = os_name.lower()
    architecture = os_arch.lower()
    for os_fragment, architectures, target in HOST_MAPPINGS:
        if os_fragment in operating_system and architecture in architectures:
            return target
    return None


def describe_c_abi() -> dict[str, Any]:
    """Return the complete canonical catalog consumed by non-Python build clients."""
    contract = _repository_contract()
    return {
        "schemaVersion": 1,
        "abi": {
            "current": contract.current.line,
            "minimum": contract.minimum_compatible.line,
            "encoded": contract.current.encoded_hex,
            "identitySchemaVersion": contract.runtime_identity_schema_version,
            "publicSymbolCount": len(_repository_symbol_set()),
        },
        "paths": {
            "header": C_ABI_HEADER_PATH,
            "packageManifest": C_ABI_PACKAGE_MANIFEST,
            "stagedEvidence": C_ABI_STAGED_EVIDENCE_PATH,
        },
        "consumers": {
            "strict": sorted(STRICT_CONSUMERS),
            "compileOnly": sorted(COMPILE_ONLY_CONSUMERS),
            "gnu": sorted(GNU_CONSUMERS),
        },
        "hostMappings": [
            {
                "osContains": os_fragment,
                "architectures": list(architectures),
                "target": target,
            }
            for os_fragment, architectures, target in HOST_MAPPINGS
        ],
        "targets": [
            {
                "target": spec.target,
                "component": spec.classifier.removeprefix("c-abi-"),
                "classifier": spec.classifier,
                "runnerOs": spec.runner_os,
                "runnerArch": spec.runner_arch,
                "format": spec.format,
                "architecture": spec.architecture,
                "libraryPath": spec.library_path,
                "loaderIdentity": spec.loader_identity,
                "importLibraryPaths": list(spec.import_library_paths),
                "proofId": spec.proof_id,
                "evidenceFileName": c_abi_evidence_file_name(spec.target),
                "archiveFileNameTemplate": (
                    f"codex-agent-runtime-desktop-{{libraryVersion}}-{spec.classifier}.zip"
                ),
                "versionIdentity": spec.version_identity,
                "requiredToolIds": sorted(spec.required_tool_ids),
            }
            for spec in sorted(TARGET_SPECS.values(), key=lambda value: value.target)
        ],
    }


def c_abi_archive_file_name(library_version: str, target: str) -> str:
    spec = _target(target)
    return f"codex-agent-runtime-desktop-{library_version}-{spec.classifier}.zip"


def c_abi_evidence_file_name(target: str) -> str:
    return f"{_target(target).proof_id}.json"


def c_abi_expected_symbols(export_policy: Path) -> frozenset[str]:
    symbols = _policy_symbols(Path(export_policy), "C ABI export policy")
    expected_count = len(_repository_symbol_set())
    if len(symbols) != expected_count:
        raise ValueError(
            "C ABI export policy does not contain the exact canonical symbol count: "
            f"expected {expected_count}, found {len(symbols)}",
        )
    return symbols


def _expected_linux_version_nodes(contract: CAbiContract | None = None) -> tuple[str, ...]:
    if contract is None:
        contract = _repository_contract()
    current = contract.current
    minimum = contract.minimum_compatible
    if current.major != minimum.major:
        raise ValueError("C ABI Linux version lineage cannot cross ABI majors")
    return tuple(
        f"CODEX_AGENT_{current.major}.{minor}"
        for minor in range(minimum.minor, current.minor + 1)
    )


def _header_macro_values(path: Path) -> tuple[CAbiVersion, CAbiVersion, frozenset[str]]:
    try:
        text = read_regular_file_bytes(
            Path(path),
            max_bytes=8 * 1024 * 1024,
        ).decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ValueError("Reviewed C ABI header is not UTF-8") from error
    logical = text.replace("\\\r\n", " ").replace("\\\n", " ")
    authority_defines = [match.group("name") for match in _HEADER_AUTHORITY_DEFINE.finditer(logical)]
    expected_names = {
        "CODEX_AGENT_ABI_VERSION_MAJOR",
        "CODEX_AGENT_ABI_VERSION_MINOR",
        "CODEX_AGENT_ABI_VERSION_PATCH",
        "CODEX_AGENT_ABI_VERSION_CURRENT",
        "CODEX_AGENT_ABI_VERSION_MINIMUM_COMPATIBLE",
    }
    if set(authority_defines) != expected_names or len(authority_defines) != len(expected_names):
        raise ValueError("Reviewed C ABI header authority macros are missing or duplicated")
    macros: dict[str, int] = {}
    for match in _HEADER_INTEGER_MACRO.finditer(logical):
        name = match.group("name")
        if name in macros:
            raise ValueError(f"Reviewed C ABI header contains duplicate macro: {name}")
        macros[name] = int(match.group("value"))
    component_names = {
        "CODEX_AGENT_ABI_VERSION_MAJOR",
        "CODEX_AGENT_ABI_VERSION_MINOR",
        "CODEX_AGENT_ABI_VERSION_PATCH",
    }
    if set(macros) != component_names:
        raise ValueError("Reviewed C ABI header version component macros are missing or malformed")
    current = CAbiVersion(
        macros["CODEX_AGENT_ABI_VERSION_MAJOR"],
        macros["CODEX_AGENT_ABI_VERSION_MINOR"],
        macros["CODEX_AGENT_ABI_VERSION_PATCH"],
    )
    if len(list(_HEADER_CURRENT_MACRO.finditer(logical))) != 1:
        raise ValueError("Reviewed C ABI header current-version macro is missing or malformed")
    minimum_matches = list(_HEADER_MINIMUM_MACRO.finditer(logical))
    if len(minimum_matches) != 1:
        raise ValueError("Reviewed C ABI header minimum-compatible macro is missing or duplicated")
    minimum_match = minimum_matches[0]
    minimum = CAbiVersion(*(
        int(minimum_match.group(name)) for name in ("major", "minor", "patch")
    ))
    symbols = frozenset(match.group(1) for match in _HEADER_SYMBOL.finditer(text))
    if not symbols:
        raise ValueError("Reviewed C ABI header contains no public function declarations")
    return current, minimum, symbols


def verify_c_abi_contract(
    abi_contract: Path,
    header: Path,
    macos_exports: Path,
    linux_map: Path,
    windows_def: Path,
) -> dict[str, Any]:
    contract = load_c_abi_contract(abi_contract)
    current, minimum, header_symbols = _header_macro_values(header)
    if current != contract.current or minimum != contract.minimum_compatible:
        raise ValueError("Reviewed C ABI header macros do not match the canonical ABI contract")
    paths = {
        "mach-o": Path(macos_exports),
        "elf": Path(linux_map),
        "pe": Path(windows_def),
    }
    symbols = _reviewed_symbol_set(paths)
    if header_symbols != symbols:
        raise ValueError("Reviewed C ABI header/export policy symbol sets differ")
    versions = c_abi_linux_symbol_versions(Path(linux_map), contract=contract, expected_symbols=symbols)
    if set(versions) != set(symbols):
        raise ValueError("Reviewed C ABI Linux policy does not version the exact public symbol set")
    return {
        **describe_c_abi_contract(abi_contract),
        "publicSymbolCount": len(symbols),
        "publicSymbolsSha256": _sorted_newline_sha256(symbols),
    }


def c_abi_linux_symbol_versions(
    export_policy: Path,
    *,
    contract: CAbiContract | None = None,
    expected_symbols: frozenset[str] | None = None,
) -> dict[str, str]:
    if contract is None:
        contract = _repository_contract()
    text = _regular_bytes(export_policy, "C ABI Linux export policy").decode("utf-8", errors="strict")
    node: str | None = None
    assignments: dict[str, str] = {}
    for line in text.splitlines():
        trimmed = line.strip()
        match = _LINUX_VERSION_NODE.fullmatch(trimmed)
        if match:
            if node is not None:
                raise ValueError("Nested C ABI Linux version node")
            node = match.group(1)
            continue
        if trimmed.startswith("}"):
            node = None
        symbol_match = _LINUX_VERSION_SYMBOL.fullmatch(trimmed)
        if symbol_match:
            symbol = symbol_match.group(1)
            if node is None:
                raise ValueError(f"C ABI Linux symbol is outside a version node: {symbol}")
            if symbol in assignments:
                raise ValueError(f"Duplicate C ABI Linux symbol assignment: {symbol}")
            assignments[symbol] = node
    symbols = c_abi_expected_symbols(export_policy) if expected_symbols is None else expected_symbols
    expected_nodes = set(_expected_linux_version_nodes(contract))
    if (
        len(assignments) != len(symbols)
        or set(assignments) != set(symbols)
        or set(assignments.values()) != expected_nodes
    ):
        raise ValueError(
            "C ABI Linux export policy must assign every exact symbol to the canonical ABI lineage"
        )
    return dict(sorted(assignments.items()))


def describe_c_abi_export_policy(export_policy: Path, format: str) -> dict[str, Any]:
    if format not in {"mach-o", "elf", "pe"}:
        raise ValueError(f"Unsupported C ABI export-policy format: {format}")
    symbols = c_abi_expected_symbols(Path(export_policy))
    versions = c_abi_linux_symbol_versions(Path(export_policy)) if format == "elf" else {}
    return {
        "schemaVersion": 1,
        "format": format,
        "publicSymbols": sorted(symbols),
        "publicSymbolVersions": [
            {"symbol": symbol, "version": version}
            for symbol, version in sorted(versions.items())
        ],
    }


def package_c_abi_sdk(package_input: CAbiPackageInput, output: Path) -> CAbiPackageSnapshot:
    spec, symbols, payload = _validated_package_inputs(package_input)
    archive = Path(output)
    archive.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{archive.name}-", suffix=".tmp", dir=archive.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        _write_package(temporary, package_input, symbols, payload)
        snapshot = inspect_c_abi_package(temporary, package_input)
        os.replace(temporary, archive)
        return CAbiPackageSnapshot(
            snapshot.target,
            snapshot.classifier,
            _sha256(read_regular_file_bytes(archive)),
            snapshot.header_sha256,
            snapshot.library_sha256,
            snapshot.public_symbols_sha256,
            snapshot.members,
        )
    finally:
        temporary.unlink(missing_ok=True)


def inspect_c_abi_package(
    archive: Path,
    expected: CAbiPackageInput,
    output_directory: Path | None = None,
) -> CAbiPackageSnapshot:
    output = Path(os.path.abspath(output_directory)) if output_directory is not None else None
    if output is not None:
        _require_absent_output_directory(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".codex-agent-c-abi-inspect-", dir=output.parent) as temporary:
            workspace = Path(temporary)
            archive_snapshot = workspace / "package.zip"
            _snapshot_c_abi_archive(Path(archive), archive_snapshot)
            extracted = workspace / "sdk"
            _extract_package(archive_snapshot, extracted)
            spec = _checked_target(expected.target, expected.classifier)
            staged_expected = CAbiPackageInput(
                expected.target,
                expected.classifier,
                expected.library_version,
                expected.producer_commit,
                expected.producer_tree,
                expected.reviewed_header,
                expected.license,
                expected.notice,
                extracted / spec.library_path,
                expected.export_policy,
                extracted / spec.import_library_paths[0] if spec.import_library_paths else None,
                extracted / spec.import_library_paths[1] if len(spec.import_library_paths) > 1 else None,
            )
            snapshot = inspect_c_abi_package(archive_snapshot, staged_expected)
            _publish_immutable_directory(extracted, output)
            return snapshot
    spec, symbols, payload = _validated_package_inputs(expected)
    expected_paths = {member.path for member in payload} | {C_ABI_PACKAGE_MANIFEST}
    records, contents, archive_identity = verified_zip_contents(
        Path(archive),
        max_archive_bytes=1024 * 1024 * 1024,
        max_central_directory_bytes=16 * 1024 * 1024,
        max_members=16,
        max_entry_bytes=512 * 1024 * 1024,
        max_total_bytes=1024 * 1024 * 1024,
        max_compression_ratio=1000,
    )
    if set(contents) != expected_paths or len(records) != len(expected_paths):
        raise ValueError(
            f"C ABI package member set mismatch: expected={sorted(expected_paths)} actual={sorted(contents)}",
        )
    with zipfile.ZipFile(archive) as source:
        for entry in source.infolist():
            if (
                entry.date_time != C_ABI_ZIP_EPOCH
                or entry.compress_type != zipfile.ZIP_DEFLATED
                or entry.extra
                or entry.comment
                or entry.create_system != 3
                or ((entry.external_attr >> 16) & 0xFFFF) != C_ABI_FILE_MODE
            ):
                raise ValueError(f"C ABI package member encoding is not canonical: {entry.filename}")
    digests = {member.path: _sha256(contents[member.path]) for member in payload}
    for member in payload:
        if contents[member.path] != member.contents:
            raise ValueError(f"C ABI package member digest mismatch: {member.path}")
    if spec.format == "elf" and contents[spec.library_path] != contents[f"lib/{spec.loader_identity}"]:
        raise ValueError("Linux C ABI linker and SONAME entries must be byte-identical")
    manifest = load_json_bytes(contents[C_ABI_PACKAGE_MANIFEST])
    _verify_package_manifest(manifest, expected, spec, symbols, payload, digests)
    with tempfile.TemporaryDirectory(prefix="codex-agent-c-abi-canonical-") as temporary:
        canonical = Path(temporary) / "canonical.zip"
        _write_package(canonical, expected, symbols, payload)
        if read_regular_file_bytes(Path(archive)) != read_regular_file_bytes(canonical):
            raise ValueError("C ABI package bytes are not canonical")
    return CAbiPackageSnapshot(
        spec.target,
        spec.classifier,
        _without_prefix(archive_identity["sha256"]),
        digests[C_ABI_HEADER_PATH],
        digests[spec.library_path],
        _sorted_newline_sha256(symbols),
        MappingProxyType(dict(sorted(digests.items()))),
    )


def build_c_abi_package_evidence(values: CAbiEvidenceValues) -> dict[str, Any]:
    spec = _checked_target(values.target, values.classifier)
    contract = _repository_contract()
    return {
        "schemaVersion": 1,
        "artifactId": spec.proof_id,
        "target": values.target,
        "classifier": values.classifier,
        "libraryVersion": values.library_version,
        "producerCommit": values.producer_commit,
        "producerTree": values.producer_tree,
        "runnerOs": values.runner_os,
        "runnerArch": values.runner_arch,
        "abiCurrent": contract.current.line,
        "abiMinimum": contract.minimum_compatible.line,
        "abiEncoded": contract.current.encoded_hex,
        "archiveSha256": values.archive_sha256,
        "headerSha256": values.header_sha256,
        "libraryPath": spec.library_path,
        "librarySha256": values.library_sha256,
        "publicSymbolCount": len(values.public_symbols),
        "publicSymbolsSha256": _sorted_newline_sha256(values.public_symbols),
        "publicSymbols": sorted(values.public_symbols),
        "publicSymbolVersions": [
            {"symbol": symbol, "version": version}
            for symbol, version in sorted(values.public_symbol_versions.items())
        ],
        "format": values.format,
        "architecture": values.architecture,
        "loaderIdentity": values.loader_identity,
        "versionIdentity": values.version_identity,
        "importLibraries": [
            {"path": path, "sha256": digest}
            for path, digest in sorted(values.import_libraries.items())
        ],
        "tools": [
            {"id": tool_id, "outputSha256": digest}
            for tool_id, digest in sorted(values.tool_proofs.items())
        ],
        "consumers": [_consumer_json(proof) for proof in sorted(values.consumers, key=lambda value: value.source)],
        "gnuConsumers": [
            _consumer_json(proof) for proof in sorted(values.gnu_consumers, key=lambda value: value.source)
        ],
        "result": "passed",
    }


def write_c_abi_package_evidence(values: CAbiEvidenceValues, output: Path) -> dict[str, Any]:
    report = build_c_abi_package_evidence(values)
    _atomic_write(Path(output), _json_bytes(report))
    return report


def verify_c_abi_package_evidence(
    report: Mapping[str, Any],
    archive: Path,
    expected: CAbiPackageInput,
    expected_runner_os: str,
    expected_runner_arch: str,
    expected_consumers: Mapping[str, str],
) -> None:
    spec = _checked_target(expected.target, expected.classifier)
    contract = _repository_contract()
    if set(expected_consumers) != set(STRICT_CONSUMERS):
        raise ValueError("C ABI strict consumer source inventory is incomplete or unexpected")
    package = inspect_c_abi_package(Path(archive), expected)
    exact_keys = {
        "schemaVersion", "artifactId", "target", "classifier", "libraryVersion", "producerCommit",
        "producerTree", "runnerOs", "runnerArch", "abiCurrent", "abiMinimum", "abiEncoded",
        "archiveSha256", "headerSha256", "libraryPath", "librarySha256", "publicSymbolCount",
        "publicSymbolsSha256", "publicSymbols", "publicSymbolVersions", "format", "architecture",
        "loaderIdentity", "versionIdentity", "importLibraries", "tools", "consumers", "gnuConsumers",
        "result",
    }
    if set(report) != exact_keys or _strict_int(report, "schemaVersion") != 1:
        raise ValueError("C ABI evidence schema mismatch")
    if _strict_string(report, "artifactId") != spec.proof_id:
        raise ValueError("C ABI evidence artifact identity mismatch")
    if _strict_string(report, "target") != spec.target or _strict_string(report, "classifier") != spec.classifier:
        raise ValueError("C ABI evidence target/classifier mismatch")
    if (
        _strict_string(report, "libraryVersion") != expected.library_version
        or _strict_string(report, "producerCommit") != expected.producer_commit
        or _strict_string(report, "producerTree") != expected.producer_tree
    ):
        raise ValueError("C ABI evidence producer identity mismatch")
    if (
        _strict_string(report, "runnerOs") != expected_runner_os
        or _strict_string(report, "runnerArch") != expected_runner_arch
        or expected_runner_os != spec.runner_os
        or expected_runner_arch != spec.runner_arch
    ):
        raise ValueError("C ABI evidence runner identity mismatch")
    if (
        _strict_string(report, "abiCurrent") != contract.current.line
        or _strict_string(report, "abiMinimum") != contract.minimum_compatible.line
        or _strict_string(report, "abiEncoded") != contract.current.encoded_hex
    ):
        raise ValueError("C ABI evidence ABI version mismatch")
    if (
        _strict_string(report, "archiveSha256") != package.archive_sha256
        or _strict_string(report, "headerSha256") != package.header_sha256
        or _strict_string(report, "libraryPath") != spec.library_path
        or _strict_string(report, "librarySha256") != package.library_sha256
    ):
        raise ValueError("C ABI evidence artifact digest mismatch")
    symbols = c_abi_expected_symbols(expected.export_policy)
    reported_symbols = _strict_string_list(report, "publicSymbols")
    if (
        reported_symbols != sorted(reported_symbols)
        or len(reported_symbols) != len(set(reported_symbols))
        or set(reported_symbols) != set(symbols)
        or _strict_int(report, "publicSymbolCount") != len(_repository_symbol_set())
        or _strict_string(report, "publicSymbolsSha256") != _sorted_newline_sha256(symbols)
    ):
        raise ValueError("C ABI evidence public symbol inventory mismatch")
    versions = _record_pairs(report, "publicSymbolVersions", {"symbol", "version"}, "symbol", "version")
    expected_versions = c_abi_linux_symbol_versions(expected.export_policy) if spec.format == "elf" else {}
    if not _exact_sorted_pairs(versions, expected_versions):
        raise ValueError("C ABI evidence symbol-version assignments mismatch")
    if (
        _strict_string(report, "format") != spec.format
        or _strict_string(report, "architecture") != spec.architecture
        or _strict_string(report, "loaderIdentity") != spec.loader_identity
        or _strict_string(report, "versionIdentity") != spec.version_identity
    ):
        raise ValueError("C ABI evidence architecture/loader/version mismatch")
    imports = _record_pairs(report, "importLibraries", {"path", "sha256"}, "path", "sha256", sha_value=True)
    if (
        not _exact_sorted_pairs(imports, {path: package.members[path] for path in spec.import_library_paths})
    ):
        raise ValueError("C ABI evidence import-library mismatch")
    tools = _record_pairs(report, "tools", {"id", "outputSha256"}, "id", "outputSha256", sha_value=True)
    if set(key for key, _ in tools) != set(spec.required_tool_ids) or not _pairs_sorted_unique(tools):
        raise ValueError("C ABI tool evidence inventory mismatch")
    tool_by_id = dict(tools)
    consumers = [_parse_consumer(value) for value in _strict_array(report, "consumers")]
    if [proof.source for proof in consumers] != sorted(expected_consumers) or len(consumers) != len(expected_consumers):
        raise ValueError("C ABI strict consumer evidence inventory mismatch")
    for proof in consumers:
        language = "c++17" if proof.source.endswith(".cpp") else "c11"
        valid_execution = (proof.linked and proof.executed) or (
            not proof.linked and not proof.executed and proof.source in COMPILE_ONLY_CONSUMERS
        )
        if (
            proof.source != Path(proof.source).name
            or proof.source_sha256 != expected_consumers.get(proof.source)
            or proof.language != language
            or proof.compiler_identity_sha256 != tool_by_id["cpp" if language == "c++17" else "c"]
            or not _is_sha256(proof.compile_output_sha256)
            or not _is_sha256(proof.artifact_sha256)
            or proof.exit_code != 0
            or not valid_execution
        ):
            raise ValueError(f"C ABI strict consumer proof failed: {proof.source}")
    if {proof.source for proof in consumers if not proof.executed} != set(expected_consumers) & set(COMPILE_ONLY_CONSUMERS):
        raise ValueError("C ABI strict consumer execution boundary mismatch")
    gnu_consumers = [_parse_consumer(value) for value in _strict_array(report, "gnuConsumers")]
    expected_gnu = GNU_CONSUMERS if spec.format == "pe" else frozenset()
    if [proof.source for proof in gnu_consumers] != sorted(expected_gnu) or len(gnu_consumers) != len(expected_gnu):
        raise ValueError("C ABI GNU strict consumer evidence inventory mismatch")
    for proof in gnu_consumers:
        language = "c++17" if proof.source.endswith(".cpp") else "c11"
        if (
            proof.source_sha256 != expected_consumers[proof.source]
            or proof.language != language
            or proof.compiler_identity_sha256 != tool_by_id["gnuCpp" if language == "c++17" else "gnuC"]
            or not _is_sha256(proof.compile_output_sha256)
            or not _is_sha256(proof.artifact_sha256)
            or not proof.linked
            or not proof.executed
            or proof.exit_code != 0
        ):
            raise ValueError(f"C ABI GNU strict consumer proof failed: {proof.source}")
    if _strict_string(report, "result") != "passed":
        raise ValueError("C ABI package evidence did not pass")


def portable_verify_c_abi_package_evidence(
    target: str,
    library_version: str,
    producer_commit: str,
    producer_tree: str,
    archive: Path,
    evidence: Path,
    reviewed_header: Path,
    license: Path,
    notice: Path,
    export_policy: Path,
    consumer_sources: Iterable[Path],
    output_directory: Path | None = None,
) -> dict[str, Any]:
    spec = _target(target)
    sources = sorted((Path(source) for source in consumer_sources), key=lambda path: path.name)
    if (
        len(sources) != len(STRICT_CONSUMERS)
        or {source.name for source in sources} != set(STRICT_CONSUMERS)
        or any(not _regular_bytes(source, "C ABI strict consumer source") for source in sources)
    ):
        raise ValueError("C ABI strict consumer sources are missing or duplicated")
    evidence_bytes = _regular_bytes(Path(evidence), "C ABI package evidence")
    report = load_json_bytes(evidence_bytes)
    if type(report) is not dict or evidence_bytes != _json_bytes(report):
        raise ValueError("C ABI package evidence is not canonically encoded")
    output = Path(os.path.abspath(output_directory)) if output_directory is not None else None
    if output is not None:
        _require_absent_output_directory(output)
        output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=f".codex-agent-c-abi-portable-{target}-",
        dir=output.parent if output is not None else None,
    ) as temporary:
        workspace = Path(temporary)
        archive_snapshot = workspace / "package.zip"
        _snapshot_c_abi_archive(Path(archive), archive_snapshot)
        root = workspace / "sdk"
        _extract_package(archive_snapshot, root)
        package_input = CAbiPackageInput(
            target,
            spec.classifier,
            library_version,
            producer_commit,
            producer_tree,
            Path(reviewed_header),
            Path(license),
            Path(notice),
            root / spec.library_path,
            Path(export_policy),
            root / spec.import_library_paths[0] if spec.import_library_paths else None,
            root / spec.import_library_paths[1] if len(spec.import_library_paths) > 1 else None,
        )
        verify_c_abi_package_evidence(
            report,
            archive_snapshot,
            package_input,
            spec.runner_os,
            spec.runner_arch,
            {source.name: _sha256(_regular_bytes(source, "C ABI strict consumer source")) for source in sources},
        )
        if output is not None:
            _atomic_write(root / C_ABI_STAGED_EVIDENCE_PATH, evidence_bytes)
            _publish_immutable_directory(root, output)
    return report


def read_c_abi_evidence_values(path: Path) -> CAbiEvidenceValues:
    """Read the canonical, strict input document used by ``evidence-write``."""
    document = load_canonical_json_bytes(_regular_bytes(Path(path), "C ABI evidence values"))
    keys = {
        "schemaVersion", "target", "classifier", "libraryVersion", "producerCommit", "producerTree",
        "runnerOs", "runnerArch", "archiveSha256", "headerSha256", "librarySha256", "publicSymbols",
        "publicSymbolVersions", "format", "architecture", "loaderIdentity", "versionIdentity",
        "importLibraries", "toolProofs", "consumers", "gnuConsumers",
    }
    if type(document) is not dict or set(document) != keys or _strict_int(document, "schemaVersion") != 1:
        raise ValueError("C ABI evidence values schema mismatch")
    target = _strict_string(document, "target")
    classifier = _strict_string(document, "classifier")
    _checked_target(target, classifier)
    library_version = _strict_string(document, "libraryVersion")
    producer_commit = _strict_string(document, "producerCommit")
    producer_tree = _strict_string(document, "producerTree")
    _check_identity(library_version, producer_commit, producer_tree)
    symbols = _strict_string_list(document, "publicSymbols")
    if symbols != sorted(symbols) or len(symbols) != len(set(symbols)):
        raise ValueError("C ABI evidence values public symbols are not sorted and unique")
    versions = _record_pairs(
        document, "publicSymbolVersions", {"symbol", "version"}, "symbol", "version",
    )
    imports = _record_pairs(
        document, "importLibraries", {"path", "sha256"}, "path", "sha256", sha_value=True,
    )
    tools = _record_pairs(
        document, "toolProofs", {"id", "outputSha256"}, "id", "outputSha256", sha_value=True,
    )
    if not all(_pairs_sorted_unique(pairs) for pairs in (versions, imports, tools)):
        raise ValueError("C ABI evidence values record inventories are not sorted and unique")
    consumers = tuple(_parse_consumer(value) for value in _strict_array(document, "consumers"))
    gnu_consumers = tuple(_parse_consumer(value) for value in _strict_array(document, "gnuConsumers"))
    for name, proofs in (("consumers", consumers), ("gnuConsumers", gnu_consumers)):
        sources = [proof.source for proof in proofs]
        if sources != sorted(sources) or len(sources) != len(set(sources)):
            raise ValueError(f"C ABI evidence values {name} inventory is not sorted and unique")
    return CAbiEvidenceValues(
        target=target,
        classifier=classifier,
        library_version=library_version,
        producer_commit=producer_commit,
        producer_tree=producer_tree,
        runner_os=_strict_string(document, "runnerOs"),
        runner_arch=_strict_string(document, "runnerArch"),
        archive_sha256=_strict_sha(document, "archiveSha256"),
        header_sha256=_strict_sha(document, "headerSha256"),
        library_sha256=_strict_sha(document, "librarySha256"),
        public_symbols=frozenset(symbols),
        public_symbol_versions=dict(versions),
        format=_strict_string(document, "format"),
        architecture=_strict_string(document, "architecture"),
        loader_identity=_strict_string(document, "loaderIdentity"),
        version_identity=_strict_string(document, "versionIdentity"),
        import_libraries=dict(imports),
        tool_proofs=dict(tools),
        consumers=consumers,
        gnu_consumers=gnu_consumers,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m ci.products.c_abi")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("describe", aliases=["specs"])

    describe_contract = commands.add_parser("describe-abi-contract")
    describe_contract.add_argument("--abi-contract", type=Path, required=True)

    verify_contract = commands.add_parser("verify-abi-contract")
    verify_contract.add_argument("--abi-contract", type=Path, required=True)
    verify_contract.add_argument("--header", type=Path, required=True)
    verify_contract.add_argument("--macos-exports", type=Path, required=True)
    verify_contract.add_argument("--linux-map", type=Path, required=True)
    verify_contract.add_argument("--windows-def", type=Path, required=True)

    export_policy = commands.add_parser("describe-export-policy")
    export_policy.add_argument("--export-policy", type=Path, required=True)
    export_policy.add_argument("--format", choices=("mach-o", "elf", "pe"), required=True)

    package = commands.add_parser("package")
    _add_package_arguments(package)
    package.add_argument("--output", type=Path, required=True)

    inspect = commands.add_parser("inspect")
    _add_package_arguments(inspect, library_required=False)
    inspect.add_argument("--archive", type=Path, required=True)
    inspect.add_argument("--output-directory", type=Path)

    evidence_write = commands.add_parser("evidence-write")
    _add_package_arguments(evidence_write)
    _add_evidence_verification_arguments(evidence_write)
    evidence_write.add_argument("--values", type=Path, required=True)
    evidence_write.add_argument("--output", type=Path, required=True)

    evidence_verify = commands.add_parser("evidence-verify")
    _add_package_arguments(evidence_verify)
    _add_evidence_verification_arguments(evidence_verify)
    evidence_verify.add_argument("--evidence", type=Path, required=True)

    portable = commands.add_parser("portable-verify")
    portable.add_argument("--target", required=True)
    portable.add_argument("--library-version", required=True)
    portable.add_argument("--producer-commit", required=True)
    portable.add_argument("--producer-tree", required=True)
    portable.add_argument("--archive", type=Path, required=True)
    portable.add_argument("--evidence", type=Path, required=True)
    portable.add_argument("--reviewed-header", type=Path, required=True)
    portable.add_argument("--license", type=Path, required=True)
    portable.add_argument("--notice", type=Path, required=True)
    portable.add_argument("--export-policy", type=Path, required=True)
    portable.add_argument("--consumer-source", type=Path, action="append", required=True)
    portable.add_argument("--output-directory", type=Path)

    arguments = parser.parse_args(argv)
    try:
        if arguments.command in {"describe", "specs"}:
            _write_stdout(describe_c_abi())
        elif arguments.command == "describe-abi-contract":
            _write_stdout(describe_c_abi_contract(arguments.abi_contract))
        elif arguments.command == "verify-abi-contract":
            _write_stdout(verify_c_abi_contract(
                arguments.abi_contract,
                arguments.header,
                arguments.macos_exports,
                arguments.linux_map,
                arguments.windows_def,
            ))
        elif arguments.command == "describe-export-policy":
            _write_stdout(describe_c_abi_export_policy(arguments.export_policy, arguments.format))
        elif arguments.command == "package":
            snapshot = package_c_abi_sdk(_package_input_from_arguments(arguments), arguments.output)
            _write_stdout(_snapshot_document(snapshot))
        elif arguments.command == "inspect":
            if arguments.output_directory is None and arguments.library is None:
                raise ValueError("C ABI inspect requires --library unless --output-directory is supplied")
            snapshot = inspect_c_abi_package(
                arguments.archive,
                _package_input_from_arguments(arguments),
                arguments.output_directory,
            )
            _write_stdout(_snapshot_document(snapshot))
        elif arguments.command == "evidence-write":
            package_input = _package_input_from_arguments(arguments)
            values = read_c_abi_evidence_values(arguments.values)
            report = build_c_abi_package_evidence(values)
            verify_c_abi_package_evidence(
                report,
                arguments.archive,
                package_input,
                arguments.expected_runner_os,
                arguments.expected_runner_arch,
                _consumer_source_digests(arguments.consumer_source),
            )
            _atomic_write(arguments.output, _json_bytes(report))
            _write_stdout(report)
        elif arguments.command == "evidence-verify":
            evidence_bytes = _regular_bytes(arguments.evidence, "C ABI package evidence")
            report = load_json_bytes(evidence_bytes)
            if type(report) is not dict or evidence_bytes != _json_bytes(report):
                raise ValueError("C ABI package evidence is not canonically encoded")
            verify_c_abi_package_evidence(
                report,
                arguments.archive,
                _package_input_from_arguments(arguments),
                arguments.expected_runner_os,
                arguments.expected_runner_arch,
                _consumer_source_digests(arguments.consumer_source),
            )
            _write_stdout(report)
        else:
            report = portable_verify_c_abi_package_evidence(
                arguments.target,
                arguments.library_version,
                arguments.producer_commit,
                arguments.producer_tree,
                arguments.archive,
                arguments.evidence,
                arguments.reviewed_header,
                arguments.license,
                arguments.notice,
                arguments.export_policy,
                arguments.consumer_source,
                arguments.output_directory,
            )
            _write_stdout(report)
        return 0
    except (OSError, ValueError) as error:
        sys.stderr.write(f"c_abi: {error}\n")
        return 1


def _add_package_arguments(parser: argparse.ArgumentParser, *, library_required: bool = True) -> None:
    parser.add_argument("--target", required=True)
    parser.add_argument("--classifier", required=True)
    parser.add_argument("--library-version", required=True)
    parser.add_argument("--producer-commit", required=True)
    parser.add_argument("--producer-tree", required=True)
    parser.add_argument("--reviewed-header", type=Path, required=True)
    parser.add_argument("--license", type=Path, required=True)
    parser.add_argument("--notice", type=Path, required=True)
    parser.add_argument("--library", type=Path, required=library_required)
    parser.add_argument("--export-policy", type=Path, required=True)
    parser.add_argument("--gnu-import-library", type=Path)
    parser.add_argument("--msvc-import-library", type=Path)


def _add_evidence_verification_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--expected-runner-os", required=True)
    parser.add_argument("--expected-runner-arch", required=True)
    parser.add_argument("--consumer-source", type=Path, action="append", required=True)


def _package_input_from_arguments(arguments: argparse.Namespace) -> CAbiPackageInput:
    return CAbiPackageInput(
        arguments.target,
        arguments.classifier,
        arguments.library_version,
        arguments.producer_commit,
        arguments.producer_tree,
        arguments.reviewed_header,
        arguments.license,
        arguments.notice,
        arguments.library,
        arguments.export_policy,
        arguments.gnu_import_library,
        arguments.msvc_import_library,
    )


def _consumer_source_digests(sources: Iterable[Path]) -> dict[str, str]:
    paths = sorted((Path(source) for source in sources), key=lambda source: source.name)
    names = [path.name for path in paths]
    if names != sorted(STRICT_CONSUMERS) or len(names) != len(set(names)):
        raise ValueError("C ABI strict consumer sources are missing or duplicated")
    return {path.name: _sha256(_regular_bytes(path, "C ABI strict consumer source")) for path in paths}


def _snapshot_document(snapshot: CAbiPackageSnapshot) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "target": snapshot.target,
        "classifier": snapshot.classifier,
        "archiveSha256": snapshot.archive_sha256,
        "headerSha256": snapshot.header_sha256,
        "librarySha256": snapshot.library_sha256,
        "publicSymbolsSha256": snapshot.public_symbols_sha256,
        "members": [
            {"path": path, "sha256": digest} for path, digest in sorted(snapshot.members.items())
        ],
    }


def _write_stdout(value: Any) -> None:
    sys.stdout.write(canonical_json_bytes(value).decode("utf-8"))


def _require_absent_output_directory(output: Path) -> None:
    try:
        output.lstat()
    except FileNotFoundError:
        return
    except OSError as error:
        raise ValueError(f"C ABI output directory is unsafe: {output}") from error
    raise ValueError(f"C ABI output directory already exists: {output}")


def _publish_immutable_directory(source: Path, output: Path) -> None:
    _require_absent_output_directory(output)
    try:
        os.rename(source, output)
    except OSError as error:
        try:
            output.lstat()
        except FileNotFoundError:
            raise ValueError(f"C ABI output directory could not be published: {output}") from error
        except OSError:
            raise ValueError(f"C ABI output directory is unsafe: {output}") from error
        raise ValueError(f"C ABI output directory already exists: {output}") from error


def _snapshot_c_abi_archive(source: Path, destination: Path) -> None:
    archive_bytes = read_regular_file_bytes(Path(source), max_bytes=1024 * 1024 * 1024)
    if not archive_bytes:
        raise ValueError("C ABI package archive is empty")
    _atomic_write(destination, archive_bytes)


def _target(target: str) -> CAbiTargetSpec:
    try:
        return TARGET_SPECS[target]
    except KeyError as error:
        raise ValueError(f"Unsupported C ABI package target: {target}") from error


def _checked_target(target: str, classifier: str) -> CAbiTargetSpec:
    if set(TARGET_SPECS) != {"macosArm64", "macosX64", "linuxArm64", "linuxX64", "mingwX64"}:
        raise ValueError("C ABI package target inventory drift")
    spec = _target(target)
    if classifier != spec.classifier:
        raise ValueError("C ABI package target/classifier mismatch")
    return spec


def _check_identity(version: str, commit: str, tree: str) -> None:
    if not _VERSION.fullmatch(version):
        raise ValueError("C ABI package library version is invalid")
    if not _GIT_ID.fullmatch(commit):
        raise ValueError("C ABI package producer commit is not immutable")
    if not _GIT_ID.fullmatch(tree):
        raise ValueError("C ABI package producer tree is not immutable")


def _regular_bytes(path: Path, label: str) -> bytes:
    try:
        contents = read_regular_file_bytes(Path(path))
    except ValueError as error:
        raise ValueError(f"{label} is missing or symbolic: {path}") from error
    if not contents:
        raise ValueError(f"{label} is missing or symbolic: {path}")
    return contents


def _validated_package_inputs(
    package_input: CAbiPackageInput,
) -> tuple[CAbiTargetSpec, frozenset[str], list[_PackageMember]]:
    spec = _checked_target(package_input.target, package_input.classifier)
    _check_identity(package_input.library_version, package_input.producer_commit, package_input.producer_tree)
    header = _regular_bytes(package_input.reviewed_header, "C ABI package input")
    license_bytes = _regular_bytes(package_input.license, "C ABI package input")
    notice = _regular_bytes(package_input.notice, "C ABI package input")
    library = _regular_bytes(package_input.library, "C ABI package input")
    _regular_bytes(package_input.export_policy, "C ABI package input")
    symbols = c_abi_expected_symbols(package_input.export_policy)
    header_symbols = frozenset(
        match.group(1) for match in _HEADER_SYMBOL.finditer(header.decode("utf-8", errors="strict"))
    )
    if header_symbols != symbols:
        raise ValueError("Reviewed C ABI header/export policy symbol mismatch")
    payload = [
        _PackageMember(C_ABI_HEADER_PATH, "header", header),
        _PackageMember("LICENSE.txt", "license", license_bytes),
        _PackageMember("THIRD_PARTY_NOTICES.md", "notice", notice),
        _PackageMember(spec.library_path, "shared-library", library),
    ]
    if spec.format == "elf":
        payload.append(_PackageMember(f"lib/{spec.loader_identity}", "soname-library", library))
    if spec.format == "pe":
        if package_input.gnu_import_library is None or package_input.msvc_import_library is None:
            raise ValueError("Windows C ABI package requires a GNU and MSVC import library")
        payload.extend((
            _PackageMember(
                spec.import_library_paths[0],
                "gnu-import-library",
                _regular_bytes(package_input.gnu_import_library, "Windows C ABI package GNU import library"),
            ),
            _PackageMember(
                spec.import_library_paths[1],
                "msvc-import-library",
                _regular_bytes(package_input.msvc_import_library, "Windows C ABI package MSVC import library"),
            ),
        ))
    elif package_input.gnu_import_library is not None or package_input.msvc_import_library is not None:
        raise ValueError("Non-Windows C ABI package must not contain import libraries")
    if any(not _safe_path(member.path) for member in payload) or len({member.path for member in payload}) != len(payload):
        raise ValueError("C ABI package payload paths are invalid")
    return spec, symbols, sorted(payload, key=lambda member: member.path)


def _package_manifest(
    package_input: CAbiPackageInput,
    symbols: frozenset[str],
    payload: list[_PackageMember],
) -> dict[str, Any]:
    contract = _repository_contract()
    return {
        "schemaVersion": 1,
        "libraryVersion": package_input.library_version,
        "target": package_input.target,
        "classifier": package_input.classifier,
        "producerCommit": package_input.producer_commit,
        "producerTree": package_input.producer_tree,
        "abiCurrent": contract.current.line,
        "abiMinimum": contract.minimum_compatible.line,
        "abiEncoded": contract.current.encoded_hex,
        "publicSymbolCount": len(symbols),
        "publicSymbolsSha256": _sorted_newline_sha256(symbols),
        "exportPolicySha256": _sha256(_regular_bytes(package_input.export_policy, "C ABI export policy")),
        "members": [
            {"path": member.path, "role": member.role, "bytes": len(member.contents), "sha256": member.sha256}
            for member in payload
        ],
    }


def _write_package(
    target: Path,
    package_input: CAbiPackageInput,
    symbols: frozenset[str],
    payload: list[_PackageMember],
) -> None:
    members = [(member.path, member.contents) for member in payload]
    members.append((C_ABI_PACKAGE_MANIFEST, _json_bytes(_package_manifest(package_input, symbols, payload))))
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path, contents in sorted(members):
            info = zipfile.ZipInfo(path, C_ABI_ZIP_EPOCH)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = C_ABI_FILE_MODE << 16
            archive.writestr(info, contents, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def _verify_package_manifest(
    manifest: Any,
    expected: CAbiPackageInput,
    spec: CAbiTargetSpec,
    symbols: frozenset[str],
    payload: list[_PackageMember],
    digests: Mapping[str, str],
) -> None:
    contract = _repository_contract()
    keys = {
        "schemaVersion", "libraryVersion", "target", "classifier", "producerCommit", "producerTree",
        "abiCurrent", "abiMinimum", "abiEncoded", "publicSymbolCount", "publicSymbolsSha256",
        "exportPolicySha256", "members",
    }
    if type(manifest) is not dict or set(manifest) != keys or _strict_int(manifest, "schemaVersion") != 1:
        raise ValueError("C ABI package manifest schema mismatch")
    if (
        _strict_string(manifest, "libraryVersion") != expected.library_version
        or _strict_string(manifest, "target") != spec.target
        or _strict_string(manifest, "classifier") != spec.classifier
        or _strict_string(manifest, "producerCommit") != expected.producer_commit
        or _strict_string(manifest, "producerTree") != expected.producer_tree
    ):
        raise ValueError("C ABI package manifest producer identity mismatch")
    if (
        _strict_string(manifest, "abiCurrent") != contract.current.line
        or _strict_string(manifest, "abiMinimum") != contract.minimum_compatible.line
        or _strict_string(manifest, "abiEncoded") != contract.current.encoded_hex
    ):
        raise ValueError("C ABI package manifest ABI version mismatch")
    if (
        _strict_int(manifest, "publicSymbolCount") != len(_repository_symbol_set())
        or _strict_string(manifest, "publicSymbolsSha256") != _sorted_newline_sha256(symbols)
        or _strict_string(manifest, "exportPolicySha256")
        != _sha256(_regular_bytes(expected.export_policy, "C ABI export policy"))
    ):
        raise ValueError("C ABI package manifest public symbol identity mismatch")
    records = _strict_array(manifest, "members")
    parsed: list[tuple[str, str, int, str]] = []
    for value in records:
        if type(value) is not dict or set(value) != {"path", "role", "bytes", "sha256"}:
            raise ValueError("C ABI package member record schema mismatch")
        path = _strict_string(value, "path")
        if not _safe_path(path):
            raise ValueError(f"Unsafe C ABI manifest member: {path}")
        parsed.append((path, _strict_string(value, "role"), _strict_int(value, "bytes"), _strict_sha(value, "sha256")))
    expected_by_path = {member.path: member for member in payload}
    if (
        [record[0] for record in parsed] != sorted(expected_by_path)
        or set(record[0] for record in parsed) != set(expected_by_path)
        or any(
            role != expected_by_path[path].role
            or size != len(expected_by_path[path].contents)
            or digest != digests[path]
            for path, role, size, digest in parsed
        )
    ):
        raise ValueError("C ABI package manifest member inventory mismatch")


def _extract_package(archive: Path, root: Path) -> None:
    _, contents, _ = verified_zip_contents(
        archive,
        max_archive_bytes=1024 * 1024 * 1024,
        max_members=16,
        max_entry_bytes=512 * 1024 * 1024,
        max_total_bytes=1024 * 1024 * 1024,
        max_compression_ratio=1000,
    )
    root.mkdir(parents=True, exist_ok=False)
    for path, contents_bytes in contents.items():
        output = root.joinpath(*path.split("/"))
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(contents_bytes)


def _consumer_json(proof: CAbiConsumerProof) -> dict[str, Any]:
    return {
        "source": proof.source,
        "sourceSha256": proof.source_sha256,
        "language": proof.language,
        "compilerIdentitySha256": proof.compiler_identity_sha256,
        "compileOutputSha256": proof.compile_output_sha256,
        "artifactSha256": proof.artifact_sha256,
        "linked": proof.linked,
        "executed": proof.executed,
        "exitCode": proof.exit_code,
    }


def _parse_consumer(value: Any) -> CAbiConsumerProof:
    keys = {
        "source", "sourceSha256", "language", "compilerIdentitySha256", "compileOutputSha256",
        "artifactSha256", "linked", "executed", "exitCode",
    }
    if type(value) is not dict or set(value) != keys:
        raise ValueError("C ABI strict consumer evidence schema mismatch")
    return CAbiConsumerProof(
        _strict_string(value, "source"),
        _strict_sha(value, "sourceSha256"),
        _strict_string(value, "language"),
        _strict_sha(value, "compilerIdentitySha256"),
        _strict_sha(value, "compileOutputSha256"),
        _strict_sha(value, "artifactSha256"),
        _strict_bool(value, "linked"),
        _strict_bool(value, "executed"),
        _strict_int(value, "exitCode"),
    )


def _record_pairs(
    report: Mapping[str, Any],
    field: str,
    keys: set[str],
    key_field: str,
    value_field: str,
    *,
    sha_value: bool = False,
) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for value in _strict_array(report, field):
        if type(value) is not dict or set(value) != keys:
            raise ValueError(f"C ABI {field} evidence schema mismatch")
        pairs.append((
            _strict_string(value, key_field),
            _strict_sha(value, value_field) if sha_value else _strict_string(value, value_field),
        ))
    return pairs


def _pairs_sorted_unique(pairs: list[tuple[str, str]]) -> bool:
    keys = [key for key, _ in pairs]
    return keys == sorted(keys) and len(keys) == len(set(keys))


def _exact_sorted_pairs(pairs: list[tuple[str, str]], expected: Mapping[str, str]) -> bool:
    return _pairs_sorted_unique(pairs) and len(pairs) == len(expected) and dict(pairs) == dict(expected)


def _strict_string(record: Mapping[str, Any], name: str) -> str:
    value = record.get(name)
    if type(value) is not str:
        raise ValueError(f"C ABI evidence field is not a string: {name}")
    return value


def _strict_sha(record: Mapping[str, Any], name: str) -> str:
    value = _strict_string(record, name)
    if not _is_sha256(value):
        raise ValueError(f"C ABI evidence SHA-256 is invalid: {name}")
    return value


def _strict_int(record: Mapping[str, Any], name: str) -> int:
    value = record.get(name)
    if type(value) is not int:
        raise ValueError(f"C ABI evidence field is not an integer: {name}")
    return value


def _strict_bool(record: Mapping[str, Any], name: str) -> bool:
    value = record.get(name)
    if type(value) is not bool:
        raise ValueError(f"C ABI evidence field is not a boolean: {name}")
    return value


def _strict_array(record: Mapping[str, Any], name: str) -> list[Any]:
    value = record.get(name)
    if type(value) is not list:
        raise ValueError(f"C ABI evidence field is not an array: {name}")
    return value


def _strict_string_list(record: Mapping[str, Any], name: str) -> list[str]:
    values = _strict_array(record, name)
    if any(type(value) is not str for value in values):
        raise ValueError(f"C ABI evidence field contains a non-string: {name}")
    return values


def _safe_path(path: str) -> bool:
    if not path or not path.strip() or path[0] in "/\\" or "\\" in path or ":" in path:
        return False
    parts = path.split("/")
    return all(part not in {"", ".", ".."} for part in parts)


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, allow_nan=False, indent=4, separators=(",", ": "))
        .encode("utf-8")
        + b"\n"
    )


def _atomic_write(path: Path, contents: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(contents)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _sha256(contents: bytes) -> str:
    return hashlib.sha256(contents).hexdigest()


def _sorted_newline_sha256(values: Iterable[str]) -> str:
    return _sha256("".join(f"{value}\n" for value in sorted(values)).encode("utf-8"))


def _is_sha256(value: str) -> bool:
    return bool(_SHA256.fullmatch(value))


def _without_prefix(value: str) -> str:
    return value.removeprefix("sha256:")


if __name__ == "__main__":
    raise SystemExit(main())
