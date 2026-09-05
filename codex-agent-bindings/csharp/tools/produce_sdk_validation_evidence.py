#!/usr/bin/env python3
"""Run the complete C# binding suite and publish its raw evidence.

Input authentication, toolchain admission, and product receipts remain caller responsibilities.
"""

from __future__ import annotations

import argparse
import csv
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKOUT = ROOT.parents[1]
SUITE_ROOT = ROOT / "tests" / "CodexAgent.Tests"
PROJECT = SUITE_ROOT / "CodexAgent.Tests.csproj"
TEST_SOURCE = SUITE_ROOT / "Program.cs"
TEST_PROGRAM = "CodexAgent.Tests.dll"
SOURCE_ROOTS = (ROOT / "src", SUITE_ROOT, ROOT / "parity")
RESTORE_ASSETS = (
    ROOT / "src" / "CodexAgent" / "obj" / "project.assets.json",
    SUITE_ROOT / "obj" / "project.assets.json",
)
IGNORED_SOURCE_DIRECTORIES = {"bin", "artifacts", "__pycache__"}
NATIVE_EVIDENCE = {
    "agent-native-tests.tsv",
    "conversation-native-tests.tsv",
    "host-native-tests.tsv",
    "leaf-native-tests.tsv",
    "synchronous-native-tests.tsv",
}
COMPILER_HEADER = ("compilerEvidenceId", "publicSymbols")
TEST_HEADER = ("executedTestId", "status")


def _required_file(path: Path, label: str) -> Path:
    path = path.expanduser().absolute()
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} must be a regular file: {path}")
    return path.resolve()


def _required_directory(path: Path, label: str) -> Path:
    path = path.expanduser().absolute()
    if path.is_symlink() or not path.is_dir():
        raise ValueError(f"{label} must be a regular directory: {path}")
    return path.resolve()


def _required_sdk(path: Path) -> Path:
    path = _required_directory(path, "C SDK root")
    _required_file(path / "include" / "codex_agent.h", "C SDK header")
    return path


def _source_files() -> list[Path]:
    files: list[Path] = []
    for root in SOURCE_ROOTS:
        _required_directory(root, "C# evidence source root")
        for directory, names, filenames in os.walk(root, followlinks=False):
            directory_path = Path(directory)
            if directory_path.name == "obj":
                names[:] = []
            else:
                names[:] = [name for name in names if name not in IGNORED_SOURCE_DIRECTORIES]
            for name in names:
                _required_directory(directory_path / name, "C# evidence source directory")
            for name in filenames:
                files.append(_required_file(directory_path / name, "C# evidence source file"))
    return files


def _copy_sources(files: list[Path], destination: Path) -> None:
    destination.mkdir()
    for source in files:
        target = destination / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


def _values(value: str, label: str) -> tuple[str, ...]:
    values = tuple(value.split(","))
    if not value or any(not item for item in values) or list(values) != sorted(set(values)):
        raise ValueError(f"{label} must be a sorted, nonempty, duplicate-free list")
    return values


def _rows(path: Path, header: tuple[str, ...]) -> list[tuple[str, ...]]:
    data = _required_file(path, path.name).read_bytes()
    if not data.endswith(b"\n") or b"\r" in data:
        raise ValueError(f"{path.name} must use canonical LF-delimited UTF-8")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"{path.name} must be UTF-8") from error
    rows = list(csv.reader(text.splitlines(), delimiter="\t", strict=True))
    if not rows or tuple(rows[0]) != header:
        raise ValueError(f"{path.name} header is invalid")
    records = [tuple(row) for row in rows[1:]]
    if not records or any(len(row) != len(header) or any(not cell for cell in row) for row in records):
        raise ValueError(f"{path.name} contains an incomplete row")
    if records != sorted(set(records)):
        raise ValueError(f"{path.name} rows must be sorted and duplicate-free")
    return records


def _verify_suite_outputs(program: Path) -> tuple[Path, Path, Path, Path]:
    artifacts = _required_directory(program / "artifacts", "C# suite artifact directory")
    expected = NATIVE_EVIDENCE | {"compiler-evidence.tsv", "executed-tests.tsv"}
    entries = list(artifacts.iterdir())
    if {entry.name for entry in entries} != expected or any(entry.is_symlink() or not entry.is_file() for entry in entries):
        raise ValueError("C# suite artifact inventory is not exact")
    for name in NATIVE_EVIDENCE:
        data = _required_file(artifacts / name, name).read_bytes()
        if not data or not data.endswith(b"\n") or b"\r" in data:
            raise ValueError(f"{name} is not canonical nonempty raw evidence")
    compiler = artifacts / "compiler-evidence.tsv"
    compiler_rows = _rows(compiler, COMPILER_HEADER)
    if len(compiler_rows) != len({evidence_id for evidence_id, _ in compiler_rows}):
        raise ValueError("C# compiler evidence IDs are duplicated")
    for evidence_id, symbols in compiler_rows:
        _values(symbols, f"compiler evidence {evidence_id} symbols")
    tests = artifacts / "executed-tests.tsv"
    test_rows = _rows(tests, TEST_HEADER)
    if (len(test_rows) != 556 or len({test_id for test_id, _ in test_rows}) != 556 or
            any(status != "passed" for _, status in test_rows)):
        raise ValueError("C# executed-test evidence does not contain exactly 556 unique passed tests")
    return compiler, tests, _required_file(program / TEST_PROGRAM, "C# test program"), artifacts


def _validate_output_scope(output: Path, inputs: tuple[Path, ...]) -> None:
    current = output
    while True:
        if current.is_symlink():
            raise ValueError(f"C# evidence output has a symbolic parent: {current}")
        if current == current.parent:
            break
        current = current.parent
    protected = {Path.home().resolve(), CHECKOUT, ROOT, ROOT.parent}
    if output == Path(output.anchor) or any(root == output or root.is_relative_to(output) for root in protected):
        raise ValueError(f"C# evidence output is too broad: {output}")
    source_roots = tuple(ROOT / name for name in ("src", "tests", "parity", "tools", "samples", "native"))
    if any(output == source or output.is_relative_to(source) for source in source_roots):
        raise ValueError(f"C# evidence output overlaps binding sources: {output}")
    if output.is_relative_to(CHECKOUT):
        relative = output.relative_to(CHECKOUT)
        if "build" not in relative.parts or relative.parts[-1] == "build":
            raise ValueError(f"C# evidence output inside the checkout must be owned by a build directory: {output}")
    if any(
        output == source or output.is_relative_to(source) or source.is_relative_to(output)
        for source in inputs
    ):
        raise ValueError(f"C# evidence output overlaps an input: {output}")


def _invalidate_output(output: Path) -> None:
    if output.is_symlink() or output.exists() and not output.is_dir():
        raise ValueError(f"unsafe C# evidence output: {output}")
    if output.exists():
        shutil.rmtree(output)


def produce(
    dotnet: Path,
    canonical_api: Path,
    c_abi_bootstrap: Path,
    sdk_compatibility: Path,
    c_sdk_root: Path,
    native_library: Path,
    output: Path,
) -> None:
    output = Path(os.path.abspath(output.expanduser()))
    dotnet = _required_file(dotnet, "dotnet executable")
    canonical_api = _required_file(canonical_api, "canonical API report")
    c_abi_bootstrap = _required_file(c_abi_bootstrap, "C ABI bootstrap evidence")
    sdk_compatibility = _required_file(sdk_compatibility, "SDK compatibility")
    c_sdk_root = _required_sdk(c_sdk_root)
    native_library = _required_file(native_library, "native library")
    suite_root = _required_directory(SUITE_ROOT, "C# test suite")
    project = _required_file(PROJECT, "C# test project")
    test_source = _required_file(TEST_SOURCE, "C# test program source")
    restore_assets = tuple(_required_file(path, "C# no-restore assets") for path in RESTORE_ASSETS)
    source_files = _source_files()
    _validate_output_scope(
        output,
        (dotnet, canonical_api, c_abi_bootstrap, sdk_compatibility, c_sdk_root,
         native_library, suite_root, project, test_source, *restore_assets, *SOURCE_ROOTS, *source_files),
    )
    _invalidate_output(output)
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".csharp-binding-evidence-", dir=output.parent) as temporary:
            work = Path(temporary)
            source = work / "source"
            program = work / "program"
            scratch = work / "scratch"
            dotnet_home = work / "dotnet-home"
            scratch.mkdir()
            dotnet_home.mkdir()
            _copy_sources(source_files, source)
            private_project = source / project.relative_to(ROOT)
            environment = {
                **os.environ,
                "DOTNET_CLI_TELEMETRY_OPTOUT": "1",
                "DOTNET_NOLOGO": "1",
                "DOTNET_SKIP_FIRST_TIME_EXPERIENCE": "1",
                "DOTNET_CLI_WORKLOAD_UPDATE_NOTIFY_DISABLE": "1",
                "DOTNET_CLI_HOME": str(dotnet_home),
                "TMPDIR": str(scratch),
                "TMP": str(scratch),
                "TEMP": str(scratch),
            }
            subprocess.run(
                [
                    str(dotnet), "build", str(private_project), "--configuration", "Release",
                    "--no-restore", "--no-incremental",
                    "--output", str(program),
                    f"-p:CodexAgentRealSdkPath={native_library}",
                    f"-p:CodexAgentCanonicalApiReport={canonical_api}",
                    f"-p:CodexAgentCAbiBootstrapEvidence={c_abi_bootstrap}",
                    f"-p:CodexAgentCSdkRoot={c_sdk_root}",
                    f"-p:CodexAgentSdkCompatibility={sdk_compatibility}",
                ],
                cwd=source,
                env=environment,
                check=True,
            )
            test_program = _required_file(program / TEST_PROGRAM, "C# test program")
            subprocess.run(
                [str(dotnet), str(test_program), "--real-mcp-values", str(native_library)],
                cwd=source,
                env=environment,
                check=True,
            )
            subprocess.run(
                [str(dotnet), str(test_program)],
                cwd=source,
                env=environment,
                check=True,
            )
            compiler, tests, test_program, native = _verify_suite_outputs(program)
            evidence = Path(temporary) / "evidence"
            evidence.mkdir()
            for raw in (compiler, tests):
                shutil.copyfile(raw, evidence / raw.name)
            shutil.copyfile(test_program, evidence / "test-program")
            native_output = evidence / "native-evidence"
            native_output.mkdir()
            for name in sorted(NATIVE_EVIDENCE):
                shutil.copyfile(native / name, native_output / name)
            if {path.name for path in evidence.iterdir()} != {
                "compiler-evidence.tsv", "executed-tests.tsv", "test-program", "native-evidence",
            } or {path.name for path in native_output.iterdir()} != NATIVE_EVIDENCE:
                raise ValueError("Published C# evidence inventory is not exact")
            evidence.rename(output)
    except Exception:
        _invalidate_output(output)
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dotnet", type=Path, required=True)
    parser.add_argument("--canonical-api", type=Path, required=True)
    parser.add_argument("--c-abi-bootstrap", type=Path, required=True)
    parser.add_argument("--sdk-compatibility", type=Path, required=True)
    parser.add_argument("--c-sdk-root", type=Path, required=True)
    parser.add_argument("--native-library", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    arguments = parse_args()
    produce(
        arguments.dotnet,
        arguments.canonical_api,
        arguments.c_abi_bootstrap,
        arguments.sdk_compatibility,
        arguments.c_sdk_root,
        arguments.native_library,
        arguments.output,
    )


if __name__ == "__main__":
    main()
