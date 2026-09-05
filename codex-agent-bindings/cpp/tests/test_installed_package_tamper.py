#!/usr/bin/env python3
"""Prove the installed C++ package rejects missing or stale pinned members."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile


def run(command: list[str], *, succeed: bool, log: Path | None = None) -> None:
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if log is not None:
        log.write_text(f"command: {command!r}\nreturncode: {result.returncode}\n{result.stdout}", encoding="utf-8")
    if (result.returncode == 0) != succeed:
        raise SystemExit(f"unexpected command result {result.returncode}: {command}\n{result.stdout}")


def verify_package(cmake: str, baseline: Path, root: Path, libdir: str, library: str) -> None:
    """Run the original seven configure cases on an already materialized package.

    The caller owns input authentication, path safety and the private workspace.
    This performs no install, packaging, product build or receipt issuance.
    """
    source = root / "consumer"
    source.mkdir()
    (source / "CMakeLists.txt").write_text(
        "cmake_minimum_required(VERSION 3.24)\n"
        "project(CodexAgentPackageTamper LANGUAGES CXX)\n"
        "find_package(CodexAgent REQUIRED CONFIG NO_DEFAULT_PATH)\n",
        encoding="utf-8",
    )

    def configure(prefix: Path, name: str, *, succeed: bool) -> None:
        run([
            cmake,
            "-S", str(source),
            "-B", str(root / f"build-{name}"),
            f"-DCodexAgent_DIR={prefix / libdir / 'cmake/CodexAgent'}",
        ], succeed=succeed, log=root / f"configure-{name}.log")

    configure(baseline, "baseline", succeed=True)
    members = (
        Path("include/codex_agent.h"),
        Path(library),
        Path("share/CodexAgent/native/sdk-compatibility.json"),
        Path("share/CodexAgent/loader/native_loader.cpp"),
    )
    for index, member in enumerate(members):
        candidate = root / f"tampered-{index}"
        shutil.copytree(baseline, candidate)
        with (candidate / member).open("ab") as output:
            output.write(b"\0")
        configure(candidate, f"tampered-{index}", succeed=False)

    missing = root / "missing-sidecar"
    shutil.copytree(baseline, missing)
    (missing / "share/CodexAgent/native/sdk-compatibility.json").unlink()
    configure(missing, "missing-sidecar", succeed=False)

    missing_loader = root / "missing-loader"
    shutil.copytree(baseline, missing_loader)
    (missing_loader / "share/CodexAgent/loader/native_loader.cpp").unlink()
    configure(missing_loader, "missing-loader", succeed=False)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("cmake")
    parser.add_argument("build")
    parser.add_argument("config")
    parser.add_argument("libdir")
    parser.add_argument("library")
    arguments = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="codex-agent-cpp-package-") as temporary:
        root = Path(temporary)
        baseline = root / "baseline"
        run([
            arguments.cmake,
            "--install", arguments.build,
            "--config", arguments.config,
            "--prefix", str(baseline),
        ], succeed=True)
        verify_package(arguments.cmake, baseline, root, arguments.libdir, arguments.library)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
