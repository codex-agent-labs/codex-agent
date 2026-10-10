"""Strict canonical Runtime native binary flag authority."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path
import re
import sys
from typing import Any

from .inventory import (
    canonical_json_bytes,
    load_canonical_json_bytes,
    read_regular_file_bytes,
    require_array,
    require_exact_keys,
    require_integer,
    require_relative_path,
    sha256_bytes,
)


SCHEMA_VERSION = 1
TARGETS = ("linux-arm64", "linux-x64", "macos-arm64", "macos-x64", "windows-x64")
ROLE_BASES = {
    "exportPolicy": "repository",
    "gnuImportLibraryOutput": "output",
    "msvcImportLibraryOutput": "output",
}
ROLE_TOKEN = re.compile(r"@role\(([A-Za-z][A-Za-z0-9]*)\)")
OPTION_NAME = re.compile(r"[A-Za-z][A-Za-z0-9-]*")
DRIVE_PATH = re.compile(r"(?:^|[,=:])[A-Za-z]:/")
ABSOLUTE_PATH = re.compile(r"(?:^|[,=:])/")
PATH_PART = re.compile(r"[,=:/]")
AT_REFERENCE = re.compile(r"@[A-Za-z][A-Za-z0-9]*")


@dataclass(frozen=True, slots=True)
class RuntimeBinaryFlags:
    target: str
    compiler_arguments: tuple[str, ...]
    supervisor_compiler_arguments: tuple[str, ...]
    linker_arguments: tuple[str, ...]
    msvc_import_library_options: tuple[tuple[str, str | None], ...]
    roles: tuple[tuple[str, str, str], ...]
    digest: str
    _canonical: bytes = field(repr=False)


def _argument(
    value: Any,
    label: str,
    *,
    allow_windows_switch: bool = False,
) -> tuple[str, frozenset[str]]:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > 1024
        or any(ord(character) < 0x20 or ord(character) > 0x7E for character in value)
    ):
        raise ValueError(f"{label} must be a nonempty printable ASCII argument")
    if "\\" in value or any(marker in value for marker in ("$", "{", "}", "%", "~")):
        raise ValueError(f"{label} contains an unsafe or unresolved placeholder")
    windows_switch = allow_windows_switch and re.fullmatch(r"/[A-Za-z][A-Za-z0-9]*", value) is not None
    if DRIVE_PATH.search(value) or (ABSOLUTE_PATH.search(value) and not windows_switch) or "://" in value:
        raise ValueError(f"{label} contains an absolute host path")
    if ".." in PATH_PART.split(value):
        raise ValueError(f"{label} contains path traversal")
    roles = frozenset(ROLE_TOKEN.findall(value))
    without_roles = ROLE_TOKEN.sub("", value)
    if "@role" in without_roles or any(
        reference != "@rpath" for reference in AT_REFERENCE.findall(without_roles)
    ):
        raise ValueError(f"{label} contains a malformed role token")
    return value, roles


def _arguments(
    value: Any,
    label: str,
    *,
    allow_windows_switches: bool = False,
) -> tuple[tuple[str, ...], frozenset[str]]:
    arguments = []
    roles: set[str] = set()
    for index, raw in enumerate(require_array(value, label)):
        argument, used = _argument(
            raw,
            f"{label}[{index}]",
            allow_windows_switch=allow_windows_switches,
        )
        arguments.append(argument)
        roles.update(used)
    if len(arguments) != len(set(arguments)):
        raise ValueError(f"{label} contains duplicate arguments")
    return tuple(arguments), frozenset(roles)


def _roles(value: Any, label: str) -> tuple[tuple[str, str, str], ...]:
    roles = []
    for index, raw in enumerate(require_array(value, label)):
        item_label = f"{label}[{index}]"
        role = require_exact_keys(raw, {"base", "name", "relativePath"}, item_label)
        name = role["name"]
        base = role["base"]
        if type(name) is not str or name not in ROLE_BASES or base != ROLE_BASES[name]:
            raise ValueError(f"{item_label} is not a supported path role")
        roles.append((name, base, require_relative_path(role["relativePath"], f"{item_label}.relativePath")))
    names = [name for name, _, _ in roles]
    if names != sorted(names) or len(names) != len(set(names)):
        raise ValueError(f"{label} must be sorted by name and unique")
    return tuple(roles)


def _msvc_options(value: Any, label: str) -> tuple[tuple[tuple[str, str | None], ...], frozenset[str]]:
    options = []
    roles: set[str] = set()
    for index, raw in enumerate(require_array(value, label)):
        item_label = f"{label}[{index}]"
        option = require_exact_keys(raw, {"name", "value"}, item_label)
        name = option["name"]
        if type(name) is not str or OPTION_NAME.fullmatch(name) is None:
            raise ValueError(f"{item_label}.name is not a canonical option name")
        option_value = option["value"]
        if option_value is not None:
            option_value, used = _argument(option_value, f"{item_label}.value")
            roles.update(used)
        options.append((name, option_value))
    names = [name for name, _ in options]
    if len(names) != len(set(names)):
        raise ValueError(f"{label} contains duplicate options")
    return tuple(options), frozenset(roles)


def _validate_target(value: Any) -> RuntimeBinaryFlags:
    record = require_exact_keys(
        value,
        {
            "target", "compilerArguments", "supervisorCompilerArguments", "linkerArguments",
            "msvcImportLibraryOptions", "roles",
        },
        "Runtime binary flags target",
    )
    target = record["target"]
    if type(target) is not str or target not in TARGETS:
        raise ValueError("Runtime binary flags target is unsupported")
    compiler, compiler_roles = _arguments(
        record["compilerArguments"],
        f"Runtime binary flags {target}.compilerArguments",
    )
    supervisor, supervisor_roles = _arguments(
        record["supervisorCompilerArguments"],
        f"Runtime binary flags {target}.supervisorCompilerArguments",
        allow_windows_switches=target == "windows-x64",
    )
    linker, linker_roles = _arguments(
        record["linkerArguments"],
        f"Runtime binary flags {target}.linkerArguments",
    )
    msvc, msvc_roles = _msvc_options(
        record["msvcImportLibraryOptions"],
        f"Runtime binary flags {target}.msvcImportLibraryOptions",
    )
    roles = _roles(record["roles"], f"Runtime binary flags {target}.roles")
    declared = {name for name, _, _ in roles}
    used = compiler_roles | supervisor_roles | linker_roles | msvc_roles
    expected = {"exportPolicy"} if target != "windows-x64" else set(ROLE_BASES)
    if compiler_roles or supervisor_roles or declared != expected or used != declared:
        raise ValueError(f"Runtime binary flags {target} path roles are incomplete or misplaced")
    if bool(msvc) != (target == "windows-x64"):
        raise ValueError("Only windows-x64 may define MSVC import-library options")
    if any("@rpath" in argument for argument in (*compiler, *supervisor)) or any(
        "@rpath" in (value or "") for _, value in msvc
    ) or (not target.startswith("macos-") and any("@rpath" in argument for argument in linker)):
        raise ValueError(f"Runtime binary flags {target} use @rpath outside the macOS linker")
    canonical = canonical_json_bytes({"schemaVersion": SCHEMA_VERSION, **record})
    return RuntimeBinaryFlags(
        target, compiler, supervisor, linker, msvc, roles, sha256_bytes(canonical), canonical,
    )


def load_runtime_binary_flags_bytes(contents: bytes) -> dict[str, RuntimeBinaryFlags]:
    if type(contents) is not bytes or len(contents) > 65_536:
        raise ValueError("Runtime binary flags bytes exceed the size limit")
    root = require_exact_keys(
        load_canonical_json_bytes(contents),
        {"schemaVersion", "targets"},
        "Runtime binary flags",
    )
    if require_integer(root["schemaVersion"], "Runtime binary flags.schemaVersion", 1) != SCHEMA_VERSION:
        raise ValueError("Unsupported Runtime binary flags schemaVersion")
    records = [_validate_target(value) for value in require_array(root["targets"], "Runtime binary flags.targets")]
    targets = [record.target for record in records]
    if tuple(targets) != TARGETS:
        raise ValueError("Runtime binary flags targets must be the exact sorted five-target set")
    return {record.target: record for record in records}


def load_runtime_binary_flags(path: Path) -> dict[str, RuntimeBinaryFlags]:
    return load_runtime_binary_flags_bytes(
        read_regular_file_bytes(Path(path), max_bytes=65_536, reject_symlink_parents=True)
    )


def describe_runtime_binary_flags(path: Path, target: str) -> dict[str, Any]:
    records = load_runtime_binary_flags(path)
    if target not in records:
        raise ValueError("Requested Runtime binary flags target is unsupported")
    record = records[target]
    value = load_canonical_json_bytes(record._canonical)
    return {**value, "flagsDigest": record.digest}


def describe_all_runtime_binary_flags(path: Path) -> dict[str, Any]:
    records = load_runtime_binary_flags(path)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "targets": [
            {
                **load_canonical_json_bytes(records[target]._canonical),
                "flagsDigest": records[target].digest,
            }
            for target in TARGETS
        ],
    }


def verify_runtime_binary_flags(path: Path) -> dict[str, Any]:
    records = load_runtime_binary_flags(path)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "targets": [
            {"flagsDigest": records[target].digest, "target": target}
            for target in TARGETS
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m ci.products.runtime_flags")
    commands = parser.add_subparsers(dest="command", required=True)
    describe = commands.add_parser("describe")
    describe.add_argument("--file", required=True, type=Path)
    describe.add_argument("--target", required=True, choices=TARGETS)
    describe_all = commands.add_parser("describe-all")
    describe_all.add_argument("--file", required=True, type=Path)
    verify = commands.add_parser("verify")
    verify.add_argument("--file", required=True, type=Path)
    arguments = parser.parse_args(argv)
    if arguments.command == "describe":
        value = describe_runtime_binary_flags(arguments.file, arguments.target)
    elif arguments.command == "describe-all":
        value = describe_all_runtime_binary_flags(arguments.file)
    else:
        value = verify_runtime_binary_flags(arguments.file)
    sys.stdout.buffer.write(canonical_json_bytes(value))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
