#!/usr/bin/env python3
"""Execute existing Dart proof suites; authentication and final matching remain external.

Uses an already resolved local test runner, never pub/dependency resolution. Existing
native-boundary suites must emit their complete raw receipts; unsupported hosts fail
closed instead of treating skipped native execution as product acceptance.
The caller supplies authenticated SDK compatibility bytes; source native resources
are excluded and only that exact declaration is materialized in the private package.
Combined subprocess output is retained losslessly as Base64 in external
dart-execution.json, including empty output; it is not reusable product content
or an authenticated success receipt.
"""
from __future__ import annotations

import argparse
import base64
import csv
import json
import os
import shutil
import subprocess
import sys
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
CLASSIFIERS = {"macos-arm64", "macos-x64", "linux-arm64", "linux-x64", "windows-x64"}
LEAF_EVIDENCE = "leaf-real-sdk-evidence"
LEAF_EXECUTABLE = "real-leaf-boundary.exe" if os.name == "nt" else "real-leaf-boundary"
LEAF_FILES = {
    "real-leaf-boundary.c", LEAF_EXECUTABLE,
    "compiler-execution.json", "boundary-execution.json",
}
NATIVE_ENTRIES = NATIVE_RECEIPTS | {"host-classifier.txt", LEAF_EVIDENCE}
IGNORED = {"build", ".dart_tool", ".pub", ".git", "doc", "__pycache__"}
NATIVE_RESOURCE = Path("lib/src/native")


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
        if package["name"] == "codex_agent" and package.get("packageUri") != "lib/":
            raise ValueError("Dart codex_agent packageUri must select the private lib/ resources")
        roots[package["name"]] = root
        package["rootUri"] = root.as_uri() + "/"
    if roots["codex_agent"] != ROOT:
        raise ValueError("Dart package configuration must select this binding source tree")
    return value, _required(roots["test"] / "bin" / "test.dart")


def _source_files() -> list[Path]:
    files = []
    for directory, names, filenames in os.walk(ROOT, followlinks=False):
        names[:] = [name for name in names if name not in IGNORED]
        if Path(directory) == ROOT / NATIVE_RESOURCE.parent:
            names[:] = [name for name in names if name != NATIVE_RESOURCE.name]
            filenames[:] = [name for name in filenames if name != NATIVE_RESOURCE.name]
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


def _native_rows(path: Path, header: tuple[str, ...], classifier_column: int) -> list[list[str]]:
    data = _required(path).read_bytes()
    if not data.endswith(b"\n") or b"\r" in data:
        raise ValueError("Dart native evidence must use LF-delimited UTF-8")
    rows = list(csv.reader(data.decode("utf-8").splitlines(), delimiter="\t", strict=True))
    if not rows or tuple(rows[0]) != header or len(rows) == 1:
        raise ValueError("Dart native evidence header/inventory is invalid")
    records = rows[1:]
    if any(len(row) != len(header) or not all(row) for row in records):
        raise ValueError("Dart native evidence rows are incomplete")
    if records != sorted(records) or len({tuple(row) for row in records}) != len(records):
        raise ValueError("Dart native evidence rows must be sorted and unique")
    if any(row[classifier_column] not in CLASSIFIERS or row[-1] != "passed" for row in records):
        raise ValueError("Dart native evidence classifier/status is invalid")
    return records


def _execution(path: Path, classifier: str, library: Path) -> list[str]:
    raw = _required(path).read_bytes()
    try:
        def object_pairs(pairs):
            value = dict(pairs)
            if len(value) != len(pairs):
                raise ValueError("Dart native execution evidence has duplicate keys")
            return value
        value = json.loads(raw, object_pairs_hook=object_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Dart native execution evidence is invalid JSON") from error
    keys = {
        "classifier", "command", "exitCode", "runtimeLibraryDirectory",
        "schemaVersion", "stderrBase64", "stdoutBase64",
    }
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError("Dart native execution evidence keys are invalid")
    command = value["command"]
    if (type(value["schemaVersion"]) is not int or value["schemaVersion"] != 1 or
            type(value["exitCode"]) is not int or value["exitCode"] != 0 or
            value["classifier"] != classifier or
            value["runtimeLibraryDirectory"] != str(library.absolute().parent) or
            not isinstance(command, list) or not command or
            any(not isinstance(item, str) or not item for item in command)):
        raise ValueError("Dart native execution evidence identity is invalid")
    for name in ("stderrBase64", "stdoutBase64"):
        if not isinstance(value[name], str):
            raise ValueError("Dart native execution bytes are invalid")
        try:
            decoded = base64.b64decode(value[name], validate=True)
        except (ValueError, TypeError) as error:
            raise ValueError("Dart native execution bytes are invalid") from error
        if base64.b64encode(decoded).decode("ascii") != value[name]:
            raise ValueError("Dart native execution bytes are not canonical Base64")
    return command


def _verify_native(native: Path, source: Path, sdk: Path, library: Path) -> None:
    if not native.is_dir() or {path.name for path in native.iterdir()} != NATIVE_ENTRIES:
        raise ValueError("Dart native auxiliary evidence is incomplete; host acceptance is unavailable")
    classifier_bytes = _required(native / "host-classifier.txt").read_bytes()
    if not classifier_bytes.endswith(b"\n") or b"\r" in classifier_bytes:
        raise ValueError("Dart host classifier is not canonical")
    try:
        classifier = classifier_bytes[:-1].decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("Dart host classifier is not UTF-8") from error
    if classifier not in CLASSIFIERS:
        raise ValueError("Dart host classifier is unsupported")
    receipts = {
        "agent-native-tests.tsv": (("capabilityKey", "cSymbol", "classifier", "status"), 2),
        "host-native-tests.tsv": (("executedTestId", "nativeSymbol", "classifier", "status"), 2),
        "conversation-real-sdk-receipt.tsv": (
            ("capabilityKey", "publicSymbol", "exactNativeCalls", "classifier", "boundary", "status"), 3),
        "leaf-real-sdk-receipt.tsv": (
            ("capabilityKey", "publicSymbol", "exactNativeCalls", "classifier", "boundary", "status"), 3),
    }
    for name, (header, column) in receipts.items():
        rows = _native_rows(native / name, header, column)
        if any(row[column] != classifier for row in rows):
            raise ValueError("Dart native evidence does not match its host classifier")
    leaf = _required(native / LEAF_EVIDENCE, directory=True)
    if {path.name for path in leaf.iterdir()} != LEAF_FILES:
        raise ValueError("Dart real leaf boundary evidence inventory is not exact")
    for name in LEAF_FILES:
        item = _required(leaf / name)
        if item.stat().st_size == 0:
            raise ValueError("Dart real leaf boundary evidence is empty")
    if (leaf / "real-leaf-boundary.c").read_bytes() != source.read_bytes():
        raise ValueError("Dart retained real leaf boundary source changed")
    if os.name != "nt" and not os.access(leaf / LEAF_EXECUTABLE, os.X_OK):
        raise ValueError("Dart retained real leaf boundary executable is not executable")
    compiler = _execution(leaf / "compiler-execution.json", classifier, library)
    boundary = _execution(leaf / "boundary-execution.json", classifier, library)
    retained_source = str(leaf / "real-leaf-boundary.c")
    executable = str(leaf / LEAF_EXECUTABLE)
    if retained_source not in compiler or boundary != [executable]:
        raise ValueError("Dart real leaf boundary command identity is invalid")
    if classifier == "windows-x64":
        imported = str(sdk / "lib" / "codex_agent.lib")
        compiler_name = Path(compiler[0]).name.lower()
        if (imported not in compiler or compiler_name not in {"cl", "cl.exe", "clang", "clang.exe"} or
                "-fPIC" in compiler or any(value.startswith("-Wl,-rpath") for value in compiler)):
            raise ValueError("Dart Windows real leaf import command is invalid")
        expected_warning = "/WX" if compiler_name in {"cl", "cl.exe"} else "-Werror"
        if expected_warning not in compiler:
            raise ValueError("Dart Windows real leaf compiler flags are invalid")
    elif (str(library.absolute()) not in compiler or "-fPIC" not in compiler or
          not any(value.startswith("-Wl,-rpath") for value in compiler)):
        raise ValueError("Dart POSIX real leaf library command is invalid")


def produce(canonical_api: Path, c_abi_bootstrap: Path, c_sdk_root: Path,
            native_library: Path, output: Path, *, sdk_compatibility: Path,
            dart_executable: str = "dart",
            package_config: Path | None = None) -> None:
    api, bootstrap, library = map(_required, (canonical_api, c_abi_bootstrap, native_library))
    compatibility = _required(sdk_compatibility)
    compatibility_bytes = compatibility.read_bytes()
    if not compatibility_bytes:
        raise ValueError("Imported Dart SDK compatibility declaration is empty")
    sdk = _required(c_sdk_root, directory=True)
    _required(sdk / "include" / "codex_agent.h")
    config = _required(package_config or ROOT / ".dart_tool" / "package_config.json")
    configuration, runner = _resolved_runner(config)
    test_program = _required(ROOT / "test" / "enum_parity_test.dart")
    marker = _required(CHECKOUT / "settings.gradle.kts")
    files = _source_files()
    output = _output_scope(output, (api, bootstrap, sdk, library, compatibility, config, runner, marker, *files))
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
            # Both the public loader's package URI and the existing security
            # suite's relative path now resolve the exact imported declaration.
            native_resource = source / NATIVE_RESOURCE
            native_resource.mkdir(parents=True)
            (native_resource / "sdk-compatibility.json").write_bytes(compatibility_bytes)
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
            log = work / "dart-test.log"
            with log.open("w+b") as raw_output:
                try:
                    subprocess.run(
                        [dart_executable, f"--packages={private_config}", str(runner), "--reporter", "expanded", "test"],
                        cwd=source, env=environment, check=True,
                        stdout=raw_output, stderr=subprocess.STDOUT,
                    )
                except subprocess.CalledProcessError:
                    raw_output.flush()
                    raw_output.seek(0)
                    shutil.copyfileobj(raw_output, sys.stderr.buffer)
                    sys.stderr.buffer.flush()
                    raise
            _verify_raw(evidence)
            native = source / "build" / "parity"
            private_leaf_source = source / "test" / "native" / "real_leaf_boundary.c"
            _verify_native(native, private_leaf_source, sdk, library)
            native_output = evidence / "native-evidence"
            shutil.copytree(native, native_output, copy_function=shutil.copy2)
            shutil.copyfile(source / test_program.relative_to(ROOT), evidence / "test-program")
            execution = {"schemaVersion": 1, "exitCode": 0,
                         "outputBase64": base64.b64encode(_required(log).read_bytes()).decode("ascii")}
            (evidence / "dart-execution.json").write_bytes(
                (json.dumps(execution, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))
            evidence.rename(output)
    except Exception:
        _invalidate(output)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("canonical-api", "c-abi-bootstrap", "c-sdk-root", "native-library", "sdk-compatibility", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--dart-executable", default="dart")
    parser.add_argument("--package-config", type=Path)
    args = parser.parse_args()
    produce(args.canonical_api, args.c_abi_bootstrap, args.c_sdk_root, args.native_library,
            args.output, sdk_compatibility=args.sdk_compatibility,
            dart_executable=args.dart_executable, package_config=args.package_config)


if __name__ == "__main__":
    main()
