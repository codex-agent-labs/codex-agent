#!/usr/bin/env python3
"""Execute the complete Rust proof suite against explicit imported artifacts.

Outputs are raw execution evidence, not deterministic product payloads or receipts.
Input authentication and final compiler/behavior/parity admission belong to the caller.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKOUT = ROOT.parents[1]
SOURCE_MEMBERS = ("Cargo.toml", "Cargo.lock", "build.rs", "src", "tests", "parity", "README.md", "LICENSE")
SOURCE_DIRECTORIES = frozenset(("src", "tests", "parity"))
REPORTS = ("compiler-evidence.tsv", "executed-tests.tsv")


def _required(path: Path, *, directory: bool = False) -> Path:
    path = Path(os.path.abspath(path.expanduser()))
    if path.is_symlink() or not (path.is_dir() if directory else path.is_file()):
        raise ValueError(f"Required regular {'directory' if directory else 'file'} is missing: {path}")
    return path.resolve()


def _validate_output(output: Path, inputs: tuple[Path, ...]) -> None:
    if any(path.is_symlink() for path in (output, *output.parents)):
        raise ValueError("Rust evidence output has a symbolic parent")
    protected = (Path.home().resolve(), CHECKOUT, ROOT, ROOT.parent)
    if output == Path(output.anchor) or any(path == output or path.is_relative_to(output) for path in protected):
        raise ValueError("Rust evidence output is too broad")
    if output.is_relative_to(ROOT) and not output.is_relative_to(ROOT / "build"):
        raise ValueError("Rust evidence output overlaps binding sources")
    if output.is_relative_to(CHECKOUT):
        relative = output.relative_to(CHECKOUT)
        if "build" not in relative.parts or relative.parts[-1] == "build":
            raise ValueError("Rust evidence output in the checkout must be owned by a build directory")
    if any(output == path or output.is_relative_to(path) or path.is_relative_to(output) for path in inputs):
        raise ValueError("Rust evidence output overlaps an input")


def _invalidate(output: Path) -> None:
    if output.is_symlink() or output.exists() and not output.is_dir():
        raise ValueError("Unsafe Rust evidence output")
    if output.exists():
        shutil.rmtree(output)


def _validate_tree(source: Path) -> None:
    _required(source, directory=True)
    if any(path.is_symlink() or not (path.is_file() or path.is_dir()) for path in source.rglob("*")):
        raise ValueError("Rust evidence tree contains a symbolic or special file")


def _validate_sources(source_root: Path) -> None:
    for name in SOURCE_MEMBERS:
        source = _required(source_root / name, directory=name in SOURCE_DIRECTORIES)
        if name in SOURCE_DIRECTORIES:
            _validate_tree(source)
    _required(source_root / "tests/enum_parity.rs")


def _copy_sources(destination: Path, source_root: Path) -> None:
    _validate_sources(source_root)
    destination.mkdir()
    for name in SOURCE_MEMBERS:
        source = source_root / name
        if name in SOURCE_DIRECTORIES:
            shutil.copytree(source, destination / name, symlinks=True,
                            ignore=shutil.ignore_patterns("target", "__pycache__"))
        else:
            shutil.copyfile(source, destination / name)
    _validate_tree(destination)


def _retain_tree(source: Path, destination: Path) -> None:
    _validate_tree(source)
    shutil.copytree(source, destination, symlinks=True)
    _validate_tree(destination)


def _rows(path: Path, header: str) -> list[list[str]]:
    data = _required(path).read_bytes()
    if not data.endswith(b"\n") or b"\r" in data:
        raise ValueError(f"Rust {path.name} must use LF-delimited UTF-8")
    lines = data.decode("utf-8").splitlines()
    rows = [line.split("\t") for line in lines[1:]]
    if not lines or lines[0] != header or not rows or any(
        len(row) != 2 or any(not cell for cell in row) for row in rows
    ) or rows != sorted(rows) or len({row[0] for row in rows}) != len(rows):
        raise ValueError(f"Rust {path.name} has invalid or duplicate raw rows")
    return rows


def _verify_reports(directory: Path) -> None:
    compiler = _rows(directory / REPORTS[0], "compilerEvidenceId\tpublicSymbols")
    if any(symbols.split(",") != sorted(set(symbols.split(","))) or
           any(not symbol for symbol in symbols.split(",")) for _, symbols in compiler):
        raise ValueError("Rust compiler evidence symbols are not exact sorted sets")
    tests = _rows(directory / REPORTS[1], "executedTestId\tstatus")
    if len(tests) != 556 or any(status != "passed" for _, status in tests):
        raise ValueError("Rust raw evidence must contain exactly 556 unique passed tests")


def produce(canonical_api: Path, c_abi_bootstrap: Path, c_sdk_root: Path,
            native_library: Path, sdk_compatibility: Path, output: Path) -> None:
    canonical_api, c_abi_bootstrap, native_library, sdk_compatibility = map(
        _required, (canonical_api, c_abi_bootstrap, native_library, sdk_compatibility))
    compatibility_bytes = sdk_compatibility.read_bytes()
    c_sdk_root = _required(c_sdk_root, directory=True)
    _required(c_sdk_root / "include/codex_agent.h")
    output = Path(os.path.abspath(output.expanduser()))
    _validate_output(output, (canonical_api, c_abi_bootstrap, c_sdk_root, native_library, sdk_compatibility))
    _validate_sources(ROOT)
    _invalidate(output)
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".rust-binding-evidence-", dir=output.parent) as temporary:
            workspace = Path(temporary).resolve()
            source, evidence, scratch = workspace / "source", workspace / "evidence", workspace / "scratch"
            _copy_sources(source, ROOT)
            # Never copy source native/ payloads: build.rs must emit its absent
            # marker and all real-library execution must use the explicit import.
            (source / "native").mkdir()
            (source / "native/sdk-compatibility.json").write_bytes(compatibility_bytes)
            evidence.mkdir()
            scratch.mkdir()
            environment = os.environ.copy()
            environment.update({
                "CARGO_NET_OFFLINE": "true", "CARGO_TARGET_DIR": str(source / "target"),
                "CODEX_AGENT_CANONICAL_API_REPORT": str(canonical_api),
                "CODEX_AGENT_C_ABI_BOOTSTRAP_EVIDENCE": str(c_abi_bootstrap),
                "CODEX_AGENT_C_SDK_ROOT": str(c_sdk_root),
                "CODEX_AGENT_REAL_SDK": str(native_library), "CODEX_AGENT_LIBRARY": str(native_library),
                "TMPDIR": str(scratch), "TMP": str(scratch), "TEMP": str(scratch),
            })
            # Include the existing ignored macOS real-library tests, not just mock/unit proofs.
            with (evidence / "cargo-test.log").open("wb") as log:
                subprocess.run(["cargo", "test", "--locked", "--offline", "--", "--include-ignored"],
                               cwd=source, env=environment, stdout=log, stderr=subprocess.STDOUT, check=True)
            raw = source / "target/cross-language-evidence"
            _verify_reports(raw)
            for name in REPORTS:
                shutil.copyfile(raw / name, evidence / name)
            shutil.copyfile(source / "tests/enum_parity.rs", evidence / "test-program")
            # Keep original generated programs, binaries and native boundary receipts,
            # not only the summary rows. These are execution evidence, not payloads.
            _retain_tree(raw, evidence / "cross-language-evidence")
            real_values = source / "target/real-value-graph"
            if real_values.exists() or real_values.is_symlink():
                _retain_tree(real_values, evidence / "real-value-graph")
            _retain_tree(scratch, evidence / "scratch")
            _copy_sources(evidence / "source", source)
            _retain_tree(source / "native", evidence / "source/native")
            evidence.rename(output)
    except Exception:
        _invalidate(output)
        raise


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("canonical-api", "c-abi-bootstrap", "c-sdk-root", "native-library", "sdk-compatibility", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    produce(args.canonical_api, args.c_abi_bootstrap, args.c_sdk_root, args.native_library,
            args.sdk_compatibility, args.output)


if __name__ == "__main__":
    main()
