#!/usr/bin/env python3
"""Run existing C++ package tamper cases on a caller-authenticated imported root.

Retained files are raw execution evidence, not receipts or host acceptance.
CMake configuration may detect a compiler, but never installs or builds products.
Archive extraction and original package/receipt authentication belong to the caller.
package-tamper-results.tsv records all seven observed cases only after they pass;
the original command/return-code/stdout logs remain alongside it as raw evidence.
"""

from __future__ import annotations

import argparse
import ast
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import runpy
import shutil
import tempfile


ROOT = Path(__file__).resolve().parents[1]
CHECKOUT = ROOT.parents[1]
VERIFIER = ROOT / "tests/test_installed_package_tamper.py"
CASE_IDS = tuple(sorted(("baseline", "tampered-0", "tampered-1", "tampered-2", "tampered-3",
                         "missing-sidecar", "missing-loader")))
RESULT_HEADER = "caseId\texpectedExit\tactualExitCode\tstatus\tlogPath"
_MAX_EVIDENCE_FILE_BYTES = 16 * 1024 * 1024


def _regular(path: Path, *, directory: bool = False) -> Path:
    path = Path(os.path.abspath(path.expanduser()))
    if any(item.is_symlink() for item in (path, *path.parents)) or not (
        path.is_dir() if directory else path.is_file()
    ):
        raise ValueError(f"Required regular input is missing or symbolic: {path}")
    return path.resolve()


def _tree(path: Path) -> None:
    _regular(path, directory=True)
    if any(item.is_symlink() or not (item.is_file() or item.is_dir()) for item in path.rglob("*")):
        raise ValueError("Imported package/evidence contains a symbolic or special member")


def _relative(value: str) -> str:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or path.as_posix() != value or ".." in path.parts or (
        value == "." or "\\" in value or ":" in value
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise ValueError("Package member paths must be normalized POSIX relative paths")
    return value


def _output(path: Path, package: Path) -> Path:
    path = Path(os.path.abspath(path.expanduser()))
    if any(item.is_symlink() for item in (path, *path.parents)):
        raise ValueError("Imported package evidence output has a symbolic parent")
    if path == Path(path.anchor) or any(item == path or item.is_relative_to(path)
                                       for item in (Path.home().resolve(), CHECKOUT, ROOT, ROOT.parent)):
        raise ValueError("Imported package evidence output is too broad")
    if path.is_relative_to(package) or package.is_relative_to(path):
        raise ValueError("Imported package evidence output overlaps its input")
    if path.is_relative_to(ROOT) and not path.is_relative_to(ROOT / "build"):
        raise ValueError("Imported package evidence output overlaps C++ sources")
    if path.is_relative_to(CHECKOUT) and (
        "build" not in path.relative_to(CHECKOUT).parts or path.name == "build"
    ):
        raise ValueError("Checkout evidence output must be owned by a build directory")
    if path.exists() and not path.is_dir():
        raise ValueError("Imported package evidence output is not a directory")
    return path


def _evidence_bytes(path: Path) -> bytes:
    with _regular(path).open("rb") as stream:
        contents = stream.read(_MAX_EVIDENCE_FILE_BYTES + 1)
    if not contents or len(contents) > _MAX_EVIDENCE_FILE_BYTES:
        raise ValueError("C++ package evidence file is empty or exceeds its size limit")
    return contents


def verify_imported_package_evidence(evidence: Path, expected_test_program: bytes) -> None:
    """Check retained seven-case observations without executing or changing files.

    The caller supplies original Git-authoritative program bytes and authenticates
    package/source/toolchain/receipt provenance. Logs alone establish no authenticity
    or host acceptance; this function checks only their exact structural consistency.
    """
    evidence = _regular(evidence, directory=True)
    _tree(evidence)
    if type(expected_test_program) is not bytes or not expected_test_program or (
        _evidence_bytes(evidence / "test-program.py") != expected_test_program
    ):
        raise ValueError("Retained C++ test program differs from its original source")
    contents = _evidence_bytes(evidence / "package-tamper-results.tsv")
    if not contents.endswith(b"\n") or b"\r" in contents:
        raise ValueError("C++ package case results must use canonical LF encoding")
    rows = contents.decode("utf-8").split("\n")[:-1]
    records = [row.split("\t") for row in rows[1:]]
    if rows[0] != RESULT_HEADER or any(len(row) != 5 for row in records) or (
        tuple(row[0] for row in records) != CASE_IDS
    ):
        raise ValueError("C++ package case results must contain exactly seven sorted cases")
    expected_logs = {f"configure-{case}.log" for case in CASE_IDS}
    if {path.name for path in evidence.glob("configure-*.log")} != expected_logs:
        raise ValueError("C++ package configure log inventory is not exact")
    _regular(evidence / "consumer", directory=True)
    command_identity = None
    for case, expectation, exit_text, status, log_name in records:
        try:
            exit_code = int(exit_text)
        except ValueError as error:
            raise ValueError("C++ package case exit code is not an integer") from error
        if str(exit_code) != exit_text or expectation != ("zero" if case == "baseline" else "nonzero") or (
            status != "passed" or (exit_code == 0) != (case == "baseline")
            or log_name != f"configure-{case}.log"
        ):
            raise ValueError("C++ package case result does not match its expected outcome")
        _regular(evidence / case, directory=True)
        _regular(evidence / f"build-{case}", directory=True)
        lines = _evidence_bytes(evidence / log_name).decode("utf-8").splitlines()
        if len(lines) < 2 or not lines[0].startswith("command: ") or lines[1] != f"returncode: {exit_code}":
            raise ValueError("C++ package case log differs from its observed exit code")
        try:
            command = ast.literal_eval(lines[0].removeprefix("command: "))
        except (SyntaxError, ValueError, RecursionError) as error:
            raise ValueError("C++ package configure command is not a literal argument list") from error
        if type(command) is not list or len(command) != 6 or any(type(arg) is not str or not arg for arg in command) or (
            command[1] != "-S" or command[3] != "-B" or not command[5].startswith("-DCodexAgent_DIR=")
        ):
            raise ValueError("C++ package case did not retain the exact configure-only command")
        path_type = PureWindowsPath if PureWindowsPath(command[2]).drive else PurePosixPath
        source, build, prefix = map(path_type, (command[2], command[4], command[5].split("=", 1)[1]))
        if any(not path.is_absolute() or ".." in path.parts for path in (source, build, prefix)) or (
            source.name != "consumer" or build != source.parent / f"build-{case}"
            or not prefix.is_relative_to(source.parent / case) or prefix.parts[-2:] != ("cmake", "CodexAgent")
        ):
            raise ValueError("C++ configure log is cross-paired with another case")
        identity = (command[0], str(source), str(prefix.relative_to(source.parent / case)))
        if command_identity is not None and identity != command_identity:
            raise ValueError("C++ configure logs disagree on their original execution inputs")
        command_identity = identity


def verify_imported_package(package_root: Path, output: Path, *, cmake: str,
                            libdir: str, library: str) -> None:
    libdir, library = _relative(libdir), _relative(library)
    package = _regular(package_root, directory=True)
    for member in ("include/codex_agent.h", library,
                   "share/CodexAgent/native/sdk-compatibility.json",
                   "share/CodexAgent/loader/native_loader.cpp",
                   f"{libdir}/cmake/CodexAgent/CodexAgentConfig.cmake"):
        _regular(package / member)
    _tree(package)
    original_program = _evidence_bytes(VERIFIER)
    output = _output(output, package)
    # Invalid inputs never discard prior evidence. Only the task-owned output
    # may be replaced once the complete preflight has succeeded.
    if output.exists():
        shutil.rmtree(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".cpp-imported-package-", dir=output.parent) as temporary:
        evidence = Path(temporary).resolve() / "evidence"
        evidence.mkdir()
        baseline = evidence / "baseline"
        shutil.copytree(package, baseline, symlinks=True)
        _tree(baseline)
        verifier = evidence / "test-program.py"
        shutil.copyfile(VERIFIER, verifier)
        if _evidence_bytes(verifier) != original_program:
            raise ValueError("Copied C++ test program differs from its original source")
        # Execute the retained exact program, not a second negative-test model.
        cases = runpy.run_path(str(verifier))["verify_package"](cmake, baseline, evidence, libdir, library)
        contents = RESULT_HEADER + "\n" + "".join(
            "\t".join(map(str, case)) + "\n" for case in cases
        )
        (evidence / "package-tamper-results.tsv").write_bytes(contents.encode("utf-8"))
        verify_imported_package_evidence(evidence, original_program)
        evidence.rename(output)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--package-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    for name in ("cmake", "libdir", "library"):
        parser.add_argument(f"--{name}", required=True)
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    verify_imported_package(args.package_root, args.output, cmake=args.cmake,
                            libdir=args.libdir, library=args.library)


if __name__ == "__main__":
    main()
