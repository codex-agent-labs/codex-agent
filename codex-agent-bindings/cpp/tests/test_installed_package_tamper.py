#!/usr/bin/env python3
"""Prove the installed C++ package rejects missing or stale pinned members."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile


def run(command: list[str], *, succeed: bool, log: Path | None = None) -> int:
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if log is not None:
        log.write_text(f"command: {command!r}\nreturncode: {result.returncode}\n{result.stdout}", encoding="utf-8")
    if (result.returncode == 0) != succeed:
        raise SystemExit(f"unexpected command result {result.returncode}: {command}\n{result.stdout}")
    return result.returncode


def verify_package(cmake: str, baseline: Path, root: Path, libdir: str,
                   library: str) -> list[tuple[str, str, int, str, str]]:
    """Run the original seven configure cases on an already materialized package.

    The caller owns input authentication, path safety and the private workspace.
    This performs no install, packaging, product build or receipt issuance.
    Returned rows record observed execution; they are not authenticated receipts.
    """
    source = root / "consumer"
    source.mkdir()
    (source / "CMakeLists.txt").write_text(
        "cmake_minimum_required(VERSION 3.24)\n"
        "project(CodexAgentPackageTamper LANGUAGES CXX)\n"
        "find_package(CodexAgent REQUIRED CONFIG NO_DEFAULT_PATH)\n",
        encoding="utf-8",
    )

    results: list[tuple[str, str, int, str, str]] = []

    def configure(prefix: Path, name: str, *, succeed: bool) -> None:
        log = root / f"configure-{name}.log"
        returncode = run([
            cmake,
            "-S", str(source),
            "-B", str(root / f"build-{name}"),
            f"-DCodexAgent_DIR={prefix / libdir / 'cmake/CodexAgent'}",
        ], succeed=succeed, log=log)
        results.append((name, "zero" if succeed else "nonzero", returncode, "passed", log.name))

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
    return sorted(results)


def verify_installed_loader(cmake: str, baseline: Path, root: Path, libdir: str,
                            config: str, pinned_root: Path) -> None:
    """Use the installed CMake target; an unsigned override must fail before dlopen."""
    installed_root = baseline / "share/CodexAgent/native/sdk-runtime-root.pub"
    if not installed_root.is_file() or installed_root.read_bytes() != pinned_root.read_bytes():
        raise SystemExit("installed SDK does not pin the production Runtime root")
    source = root / "installed-consumer"
    source.mkdir()
    (source / "CMakeLists.txt").write_text(
        "cmake_minimum_required(VERSION 3.24)\n"
        "project(CodexAgentInstalledTrust LANGUAGES CXX)\n"
        "find_package(CodexAgent REQUIRED CONFIG NO_DEFAULT_PATH)\n"
        "add_executable(installed_trust main.cpp)\n"
        "target_link_libraries(installed_trust PRIVATE CodexAgent::CodexAgent)\n",
        encoding="utf-8",
    )
    (source / "main.cpp").write_text(
        "#include <codex_agent/native_dispatch.hpp>\n"
        "#include <exception>\n"
        "#include <iostream>\n"
        "#include <string_view>\n"
        "int main(int argc, char** argv) {\n"
        "  if (argc != 2) return 64;\n"
        "  try {\n"
        "    codex_agent::CodexNativeLibrary::configure(argv[1]);\n"
        "    (void)codex_agent::detail::resolve_native_symbol(\n"
        "        codex_agent::detail::NativeSymbol::s000,\n"
        "        CODEX_AGENT_CPP_DEFAULT_LIBRARY_PATH, CODEX_AGENT_CPP_COMPATIBILITY_PATH);\n"
        "    return 1;\n"
        "  } catch (const std::exception& error) {\n"
        "    std::cerr << error.what() << '\\n';\n"
        "    return std::string_view(error.what()).find(\n"
        "        \"trusted release evidence\") != std::string_view::npos ? 0 : 2;\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    build = root / "installed-consumer-build"
    run([cmake, "-S", str(source), "-B", str(build),
         f"-DCodexAgent_DIR={baseline / libdir / 'cmake/CodexAgent'}"], succeed=True)
    build_command = [cmake, "--build", str(build)]
    if config:
        build_command.extend(("--config", config))
    run(build_command, succeed=True)
    external = root / "unsigned-external-library"
    external.write_bytes(b"not a native library; loading this would fail")
    executable = build / "installed_trust"
    if not executable.is_file():
        executable = build / config / "installed_trust.exe"
    run([str(executable), str(external)], succeed=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("cmake")
    parser.add_argument("build")
    parser.add_argument("config")
    parser.add_argument("libdir")
    parser.add_argument("library")
    parser.add_argument("pinned_root")
    arguments = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="codex-agent-cpp-package-") as temporary:
        root = Path(temporary).resolve()
        baseline = root / "baseline"
        run([
            arguments.cmake,
            "--install", arguments.build,
            "--config", arguments.config,
            "--prefix", str(baseline),
        ], succeed=True)
        verify_package(arguments.cmake, baseline, root, arguments.libdir, arguments.library)
        verify_installed_loader(arguments.cmake, baseline, root, arguments.libdir,
                                arguments.config,
                                Path(arguments.pinned_root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
