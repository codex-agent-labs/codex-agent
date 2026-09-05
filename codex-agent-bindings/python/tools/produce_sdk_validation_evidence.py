#!/usr/bin/env python3
"""Run the complete Python binding proof suite and publish its raw evidence.

Input authentication and product receipt admission remain caller responsibilities.
"""

from __future__ import annotations

import argparse
import csv
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKOUT = ROOT.parents[1]
TEST_PROGRAM = ROOT / "tests" / "test_enum_parity.py"
EVIDENCE_ENV = "CODEX_AGENT_PYTHON_EVIDENCE_DIRECTORY"
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


def _verify_outputs(directory: Path) -> None:
    actual = {path.name for path in directory.iterdir() if path.is_file() and not path.is_symlink()}
    if actual != {"compiler-evidence.tsv", "executed-tests.tsv"} or any(
        path.is_symlink() or not path.is_file() for path in directory.iterdir()
    ):
        raise ValueError("Python evidence producer output inventory is not exact")
    compiler_rows = _rows(directory / "compiler-evidence.tsv", COMPILER_HEADER)
    if len(compiler_rows) != len({evidence_id for evidence_id, _ in compiler_rows}):
        raise ValueError("Python compiler evidence IDs are duplicated")
    for evidence_id, symbols in compiler_rows:
        _values(symbols, f"compiler evidence {evidence_id} symbols")
    test_rows = _rows(directory / "executed-tests.tsv", TEST_HEADER)
    if (len(test_rows) != 556 or len({test_id for test_id, _ in test_rows}) != 556 or
            any(status != "passed" for _, status in test_rows)):
        raise ValueError("Python executed-test evidence does not contain exactly 556 unique passed tests")


def _validate_output_scope(output: Path, inputs: tuple[Path, ...]) -> None:
    current = output
    while True:
        if current.is_symlink():
            raise ValueError(f"Python evidence output has a symbolic parent: {current}")
        if current == current.parent:
            break
        current = current.parent
    filesystem_root = Path(output.anchor)
    protected = {Path.home().resolve(), CHECKOUT, ROOT, ROOT.parent}
    if output == filesystem_root or any(root == output or root.is_relative_to(output) for root in protected):
        raise ValueError(f"Python evidence output is too broad: {output}")
    source_roots = (ROOT / "src", ROOT / "tests", ROOT / "parity", ROOT / "tools")
    if any(output == source or output.is_relative_to(source) for source in source_roots):
        raise ValueError(f"Python evidence output overlaps binding sources: {output}")
    if output.is_relative_to(CHECKOUT):
        relative = output.relative_to(CHECKOUT)
        if "build" not in relative.parts or relative.parts[-1] == "build":
            raise ValueError(f"Python evidence output inside the checkout must be owned by a build directory: {output}")
    if any(
        output == source or output.is_relative_to(source) or source.is_relative_to(output)
        for source in inputs
    ):
        raise ValueError(f"Python evidence output overlaps an input: {output}")


def _invalidate_output(output: Path) -> None:
    if output.is_symlink() or output.exists() and not output.is_dir():
        raise ValueError(f"unsafe Python evidence output: {output}")
    if output.exists():
        shutil.rmtree(output)


def produce(
    canonical_api: Path,
    c_abi_bootstrap: Path,
    c_sdk_root: Path,
    native_library: Path,
    output: Path,
) -> None:
    output = Path(os.path.abspath(output.expanduser()))
    canonical_api = _required_file(canonical_api, "canonical API report")
    c_abi_bootstrap = _required_file(c_abi_bootstrap, "C ABI bootstrap evidence")
    c_sdk_root = _required_sdk(c_sdk_root)
    native_library = _required_file(native_library, "native library")
    suite_root = _required_directory(ROOT / "tests", "Python test suite")
    test_program = _required_file(TEST_PROGRAM, "Python test program")
    _validate_output_scope(
        output,
        (canonical_api, c_abi_bootstrap, c_sdk_root, native_library, suite_root, test_program),
    )
    _invalidate_output(output)
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".python-binding-evidence-", dir=output.parent) as temporary:
            evidence = Path(temporary) / "evidence"
            evidence.mkdir()
            environment = os.environ.copy()
            environment.update({
                "PYTHONDONTWRITEBYTECODE": "1",
                "CODEX_AGENT_CANONICAL_API_REPORT": str(canonical_api),
                "CODEX_AGENT_C_ABI_BOOTSTRAP_EVIDENCE": str(c_abi_bootstrap),
                "CODEX_AGENT_C_SDK_ROOT": str(c_sdk_root),
                "CODEX_AGENT_LIBRARY": str(native_library),
                EVIDENCE_ENV: str(evidence),
            })
            subprocess.run(
                [sys.executable, "-m", "unittest", "discover", "-s", str(suite_root), "-v"],
                cwd=ROOT,
                env=environment,
                check=True,
            )
            _verify_outputs(evidence)
            shutil.copyfile(test_program, evidence / "test-program")
            if {path.name for path in evidence.iterdir()} != {
                "compiler-evidence.tsv", "executed-tests.tsv", "test-program",
            }:
                raise ValueError("Published Python evidence inventory is not exact")
            evidence.rename(output)
    except Exception:
        _invalidate_output(output)
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical-api", type=Path, required=True)
    parser.add_argument("--c-abi-bootstrap", type=Path, required=True)
    parser.add_argument("--c-sdk-root", type=Path, required=True)
    parser.add_argument("--native-library", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    arguments = parse_args()
    produce(
        arguments.canonical_api,
        arguments.c_abi_bootstrap,
        arguments.c_sdk_root,
        arguments.native_library,
        arguments.output,
    )


if __name__ == "__main__":
    main()
