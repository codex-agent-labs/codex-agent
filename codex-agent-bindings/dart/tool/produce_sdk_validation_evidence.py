#!/usr/bin/env python3
"""Execute existing Dart proof suites; authentication and final matching remain external.

Uses an already resolved local test runner, never pub/dependency resolution. Existing
native-boundary suites must emit their complete raw receipts; unsupported hosts fail
closed instead of treating skipped native execution as product acceptance.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import url2pathname

ROOT = Path(__file__).resolve().parents[1]
CHECKOUT = ROOT.parents[1]
EVIDENCE_ENV = "CODEX_AGENT_DART_EVIDENCE_DIRECTORY"
NATIVE_RECEIPTS = {
    "agent-native-tests.tsv", "host-native-tests.tsv",
    "leaf-real-sdk-receipt.tsv", "conversation-real-sdk-receipt.tsv",
}
IGNORED = {"build", ".dart_tool", ".pub", ".git", "doc", "__pycache__"}


def _no_links(path: Path) -> None:
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise ValueError(f"Symbolic path is not allowed: {path}")


def _required(path: Path, *, directory: bool = False) -> Path:
    path = path.expanduser().absolute()
    _no_links(path)
    if not (path.is_dir() if directory else path.is_file()):
        raise ValueError(f"Required regular {'directory' if directory else 'file'} is missing: {path}")
    return path.resolve()


def _package_root(config: Path, value: str) -> Path:
    uri = urlparse(urljoin(config.as_uri(), value))
    if uri.scheme != "file" or uri.netloc or uri.query or uri.fragment:
        raise ValueError("Dart package roots must resolve to local file directories")
    return _required(Path(url2pathname(uri.path)), directory=True)


def _resolved_runner(config: Path) -> tuple[dict, Path]:
    value = json.loads(config.read_text(encoding="utf-8"))
    if value.get("configVersion") != 2 or not isinstance(value.get("packages"), list):
        raise ValueError("An existing Dart package-config version 2 is required")
    packages = value["packages"]
    names = [package["name"] for package in packages]
    if len(names) != len(set(names)) or names.count("test") != 1 or names.count("codex_agent") != 1:
        raise ValueError("Dart package configuration must resolve test and codex_agent exactly once")
    roots = {}
    for package in packages:
        root = _package_root(config, package["rootUri"])
        roots[package["name"]] = root
        package["rootUri"] = root.as_uri() + "/"
    if roots["codex_agent"] != ROOT:
        raise ValueError("Dart package configuration must select this binding source tree")
    return value, _required(roots["test"] / "bin" / "test.dart")


def _source_files() -> list[Path]:
    files = []
    for directory, names, filenames in os.walk(ROOT, followlinks=False):
        names[:] = [name for name in names if name not in IGNORED]
        for name in names:
            _required(Path(directory) / name, directory=True)
        for name in filenames:
            files.append(_required(Path(directory) / name))
    return files


def _output_scope(output: Path, inputs: tuple[Path, ...]) -> Path:
    output = output.expanduser().absolute()
    _no_links(output)
    output = Path(os.path.abspath(output))
    protected = (Path.home().resolve(), CHECKOUT, ROOT, ROOT.parent)
    if output == Path(output.anchor) or any(root == output or root.is_relative_to(output) for root in protected):
        raise ValueError("Dart evidence output is too broad")
    sources = tuple(ROOT / name for name in ("lib", "test", "tool", "parity", "consumer", "example"))
    if any(output == root or output.is_relative_to(root) for root in sources):
        raise ValueError("Dart evidence output overlaps source files")
    if output.is_relative_to(CHECKOUT):
        parts = output.relative_to(CHECKOUT).parts
        if "build" not in parts or parts[-1] == "build":
            raise ValueError("Dart evidence output must be inside an owned build directory")
    if any(output == path or output.is_relative_to(path) or path.is_relative_to(output) for path in inputs):
        raise ValueError("Dart evidence output overlaps an input")
    return output


def _invalidate(output: Path) -> None:
    _no_links(output)
    if output.exists():
        if not output.is_dir():
            raise ValueError("Dart evidence output must be a directory")
        shutil.rmtree(output)


def _rows(path: Path, header: tuple[str, str]) -> list[list[str]]:
    data = _required(path).read_bytes()
    if not data.endswith(b"\n") or b"\r" in data:
        raise ValueError("Dart raw evidence must use LF-delimited UTF-8")
    rows = list(csv.reader(data.decode("utf-8").splitlines(), delimiter="\t", strict=True))
    if not rows or tuple(rows[0]) != header or len(rows) == 1:
        raise ValueError("Dart raw evidence header/inventory is invalid")
    records = rows[1:]
    if any(len(row) != 2 or not all(row) for row in records) or records != sorted(records):
        raise ValueError("Dart raw evidence rows are incomplete or unsorted")
    if len({row[0] for row in records}) != len(records):
        raise ValueError("Dart raw evidence identifiers are duplicated")
    return records


def _verify_raw(evidence: Path) -> None:
    if {path.name for path in evidence.iterdir()} != {"compiler-evidence.tsv", "executed-tests.tsv"}:
        raise ValueError("Dart raw evidence inventory is not exact")
    for _, symbols in _rows(evidence / "compiler-evidence.tsv", ("compilerEvidenceId", "publicSymbols")):
        values = symbols.split(",")
        if not all(values) or values != sorted(set(values)):
            raise ValueError("Dart compiler symbols must be sorted and unique")
    tests = _rows(evidence / "executed-tests.tsv", ("executedTestId", "status"))
    if len(tests) != 556 or any(status != "passed" for _, status in tests):
        raise ValueError("Dart raw evidence requires exactly 556 unique passed tests")


def produce(canonical_api: Path, c_abi_bootstrap: Path, c_sdk_root: Path,
            native_library: Path, output: Path, *, dart_executable: str = "dart",
            package_config: Path | None = None) -> None:
    api, bootstrap, library = map(_required, (canonical_api, c_abi_bootstrap, native_library))
    sdk = _required(c_sdk_root, directory=True)
    _required(sdk / "include" / "codex_agent.h")
    config = _required(package_config or ROOT / ".dart_tool" / "package_config.json")
    configuration, runner = _resolved_runner(config)
    test_program = _required(ROOT / "test" / "enum_parity_test.dart")
    marker = _required(CHECKOUT / "settings.gradle.kts")
    files = _source_files()
    output = _output_scope(output, (api, bootstrap, sdk, library, config, runner, marker, *files))
    _invalidate(output)
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".dart-binding-evidence-", dir=output.parent) as temporary:
            work = Path(temporary)
            repository = work / "repository"
            source = repository / "codex-agent-bindings" / "dart"
            source.mkdir(parents=True)
            shutil.copyfile(marker, repository / "settings.gradle.kts")
            for original in files:
                target = source / original.relative_to(ROOT)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(original, target)
            for package in configuration["packages"]:
                if package["name"] == "codex_agent":
                    package["rootUri"] = source.as_uri() + "/"
            private_config = source / ".dart_tool" / "package_config.json"
            private_config.parent.mkdir()
            private_config.write_text(json.dumps(configuration) + "\n", encoding="utf-8")
            evidence = work / "evidence"
            evidence.mkdir()
            environment = {**os.environ,
                "CODEX_AGENT_CANONICAL_API_REPORT": str(api),
                "CODEX_AGENT_C_ABI_BOOTSTRAP_EVIDENCE": str(bootstrap),
                "CODEX_AGENT_C_SDK_ROOT": str(sdk),
                "CODEX_AGENT_REAL_LIBRARY": str(library),
                EVIDENCE_ENV: str(evidence),
            }
            subprocess.run(
                [dart_executable, f"--packages={private_config}", str(runner), "--reporter", "expanded", "test"],
                cwd=source, env=environment, check=True,
            )
            _verify_raw(evidence)
            native = source / "build" / "parity"
            if not native.is_dir() or {path.name for path in native.iterdir()} != NATIVE_RECEIPTS:
                raise ValueError("Dart native auxiliary evidence is incomplete; host acceptance is unavailable")
            native_output = evidence / "native-evidence"
            native_output.mkdir()
            for name in sorted(NATIVE_RECEIPTS):
                original = _required(native / name)
                if not original.stat().st_size:
                    raise ValueError("Dart native auxiliary evidence is empty")
                shutil.copyfile(original, native_output / name)
            shutil.copyfile(source / test_program.relative_to(ROOT), evidence / "test-program")
            evidence.rename(output)
    except Exception:
        _invalidate(output)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("canonical-api", "c-abi-bootstrap", "c-sdk-root", "native-library", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--dart-executable", default="dart")
    parser.add_argument("--package-config", type=Path)
    args = parser.parse_args()
    produce(args.canonical_api, args.c_abi_bootstrap, args.c_sdk_root, args.native_library,
            args.output, dart_executable=args.dart_executable, package_config=args.package_config)


if __name__ == "__main__":
    main()
