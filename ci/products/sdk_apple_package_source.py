"""Capture the fixed Apple package sources from one immutable Git tree."""

from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import tempfile

from .inventory import (
    git_file_inventory,
    git_regular_blob_bytes,
    publish_regular_tree,
    regular_file_inventory,
    require_relative_path,
    run_git,
    tree_entries,
)


_SINGLE_FILES = (
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    "legal/openai-codex/openai-codex-LICENSE.txt",
    "legal/openai-codex/openai-codex-NOTICE.txt",
    "codex-agent-runtime-ios/apple/Package.swift",
)
_SOURCE_TREES = tuple(
    f"codex-agent-runtime-ios/apple/{name}"
    for name in ("Sources", "Tests", "TestApp")
)
_PIN_FILE = "gradle/build-logic/src/main/kotlin/codexagent.ios-runtime.gradle.kts"
_REVISION = re.compile(r"[0-9a-f]{40}")
_NUMERIC_VERSION = re.compile(r"(?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*))+")
_BUILD = re.compile(r"(?:0|[1-9][0-9]*)[A-Z][0-9A-Za-z]+")


def _immutable_tree(repository: Path, revision: str) -> str:
    if type(revision) is not str or _REVISION.fullmatch(revision) is None:
        raise ValueError("Apple package source revision must be an exact Git object ID")
    try:
        kind = run_git(repository, "cat-file", "-t", revision).strip()
        tree = revision if kind == "tree" else run_git(repository, "rev-parse", f"{revision}^{{tree}}").strip()
    except subprocess.CalledProcessError as error:
        raise ValueError("Apple package source revision is unavailable") from error
    if kind not in {"commit", "tree"} or _REVISION.fullmatch(tree) is None:
        raise ValueError("Apple package source revision must identify a commit or tree")
    return tree


def _toolchain_expectations(contents: bytes) -> dict[str, str]:
    try:
        source = contents.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("Apple package toolchain source is not UTF-8") from error
    declarations = {
        "xcodeVersion": ("pinnedXcodeVersion", _NUMERIC_VERSION),
        "xcodeBuild": ("pinnedXcodeBuild", _BUILD),
        "swiftVersion": ("pinnedSwiftVersion", _NUMERIC_VERSION),
    }
    result = {}
    for key, (name, pattern) in declarations.items():
        matches = re.findall(rf'^private val {name} = "([^"\r\n]+)"$', source, re.MULTILINE)
        if len(matches) != 1 or pattern.fullmatch(matches[0]) is None:
            raise ValueError(f"Apple package {name} declaration is missing, duplicated, or invalid")
        result[key] = matches[0]
    return result


def capture_apple_package_sources(
    repository: Path,
    revision: str,
    output: Path,
) -> dict[str, str]:
    """Copy package inputs only; caller authentication and replay remain separate gates."""
    repository = Path(repository).resolve(strict=True)
    output = Path(output)
    if not output.is_absolute() or output != output.resolve(strict=False):
        raise ValueError("Apple package source output must be an absolute normalized path")
    if output.exists() or output.is_symlink():
        raise ValueError("Apple package source output already exists")
    if repository == output or repository in output.parents or output in repository.parents:
        raise ValueError("Apple package source output overlaps the repository")

    tree = _immutable_tree(repository, revision)
    entries = {path: record.split("\t", 3) for path, record in tree_entries(repository, tree)}
    paths = list(_SINGLE_FILES)
    for prefix in _SOURCE_TREES:
        members = sorted(path for path in entries if path.startswith(prefix + "/"))
        if not members:
            raise ValueError(f"Apple package source tree is empty: {prefix}")
        paths.extend(members)
    if len(paths) != len(set(paths)):
        raise ValueError("Apple package source paths are duplicated")
    for path in paths:
        require_relative_path(path, "Apple package source path")
        entry = entries.get(path)
        if entry is None or entry[0] not in {"100644", "100755"} or entry[1] != "blob" or entry[3] != path:
            raise ValueError(f"Apple package source is missing or nonregular: {path}")

    inventory = git_file_inventory(repository, tree, paths)
    if any(record["bytes"] == 0 for record in inventory):
        raise ValueError("Apple package source contains an empty blob")
    pin_bytes = git_regular_blob_bytes(repository, tree, _PIN_FILE, max_bytes=1024 * 1024)
    if not pin_bytes:
        raise ValueError("Apple package toolchain source is empty")
    expectations = _toolchain_expectations(pin_bytes)

    with tempfile.TemporaryDirectory(prefix="sdk-apple-package-source-") as temporary:
        captured = Path(temporary).resolve() / "source"
        captured.mkdir()
        modes = {path: entries[path][0] for path in paths}
        for record in inventory:
            relative = record["relativePath"]
            contents = git_regular_blob_bytes(repository, tree, relative, max_bytes=record["bytes"])
            if not contents:
                raise ValueError(f"Apple package source is empty: {relative}")
            destination = captured / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(contents)
            os.chmod(destination, 0o755 if modes[relative] == "100755" else 0o644)
        if regular_file_inventory(captured) != inventory or git_file_inventory(repository, tree, paths) != inventory:
            raise ValueError("Apple package source changed during capture")
        publish_regular_tree(captured, output)
    if regular_file_inventory(output) != inventory:
        raise ValueError("Apple package source changed during publication")
    return expectations
