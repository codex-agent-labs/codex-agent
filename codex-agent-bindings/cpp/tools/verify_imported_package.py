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
import os
from pathlib import Path, PurePosixPath
import runpy
import shutil
import tempfile


ROOT = Path(__file__).resolve().parents[1]
CHECKOUT = ROOT.parents[1]
VERIFIER = ROOT / "tests/test_installed_package_tamper.py"


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
    _regular(VERIFIER)
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
        # Execute the retained exact program, not a second negative-test model.
        cases = runpy.run_path(str(verifier))["verify_package"](cmake, baseline, evidence, libdir, library)
        contents = "caseId\texpectedExit\tactualExitCode\tstatus\tlogPath\n" + "".join(
            "\t".join(map(str, case)) + "\n" for case in cases
        )
        (evidence / "package-tamper-results.tsv").write_bytes(contents.encode("utf-8"))
        _tree(evidence)
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
