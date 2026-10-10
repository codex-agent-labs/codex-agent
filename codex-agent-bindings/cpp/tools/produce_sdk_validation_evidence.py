#!/usr/bin/env python3
"""Run the existing complete C++ capability/compiler/behavior suite on imported inputs.

These are raw execution outputs, not authenticated phase/host receipts. The caller
authenticates inputs and applies the existing exact capability/14-scenario matcher.
This excludes codex_agent_cpp_installed_package_tamper, which installs/repackages.
That separate installed-package gate remains mandatory; this grants no acceptance.
The explicit SDK declaration is overlaid only in a private copy of the raw C SDK,
because CMake consumes the package resource layout, not the classifier transport.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKOUT = ROOT.parents[1]
SOURCE_DIRECTORIES = ("include", "src", "tests", "tools", "parity", "cmake")
SOURCE_FILES = ("CMakeLists.txt", "README.md")
REPORTS = ("compiler-evidence.tsv", "executed-tests.tsv")
FAMILIES = ("leaf", "conversation", "agent", "host")
AUXILIARIES = tuple(f"{family}-{suffix}.tsv" for family in FAMILIES
                    for suffix in ("executed-tests", "real-boundaries"))
VALUE_TEST = "codex_agent_cpp_value_test"
LOADER_TESTS = {
    "codex_agent_native_loader_" + case for case in (
        "embedded", "hash_mismatch", "external_component", "old_abi", "actual_abi_mismatch",
        "wrong_abi_major", "incompatible_runtime", "compatible_patch", "next_minor",
        "wrong_contract", "wrong_target",
        "missing_identity", "no_fallback", "missing_compatibility_sidecar", "relative_override",
        "external_no_evidence", "signed_external", "abi_major_alias", "abi_minor_alias", "abi_patch_alias",
        "noncanonical_json", "reordered_json", "duplicate_json_key", "reordered_variants",
        "duplicate_component", "duplicate_manifest", "invalid_sdk_version", "valid_sdk_prerelease",
        "invalid_sdk_prerelease", "invalid_identity_schema", "invalid_abi_major", "invalid_abi_minor",
        "source_aba", "snapshot_aba", "parent_symlink_library", "final_symlink_library",
        "parent_symlink_compatibility", "final_symlink_compatibility", "zero_leaks",
    )
}
REQUIRED_TESTS = {VALUE_TEST, "codex_agent_cpp_enum_test", "codex_agent_cpp_test",
                  "codex_agent_native_dispatch_generated"} | {
    f"codex_agent_cpp_{family}{suffix}_test" for family in FAMILIES for suffix in ("", "_real")
} | LOADER_TESTS
CLASSIFIERS = ("macos-arm64", "macos-x64", "linux-arm64", "linux-x64", "windows-x64")
COMPATIBILITY_RESOURCE = Path("share/CodexAgent/native/sdk-compatibility.json")


def _required(path: Path, *, directory: bool = False) -> Path:
    path = Path(os.path.abspath(path.expanduser()))
    if any(item.is_symlink() for item in (path, *path.parents)) or not (
        path.is_dir() if directory else path.is_file()
    ):
        raise ValueError(f"Required regular {'directory' if directory else 'file'} is missing: {path}")
    return path.resolve()


def _tree(path: Path) -> None:
    _required(path, directory=True)
    if any(item.is_symlink() or not (item.is_file() or item.is_dir()) for item in path.rglob("*")):
        raise ValueError("C++ evidence source/output contains a symbolic or special file")


def _sources() -> None:
    for name in SOURCE_FILES:
        _required(ROOT / name)
    for name in SOURCE_DIRECTORIES:
        _tree(ROOT / name)
    _required(ROOT / "tests/value_parity_test.cpp")


def _validate_output(output: Path, inputs: tuple[Path, ...]) -> None:
    if any(path.is_symlink() for path in (output, *output.parents)):
        raise ValueError("C++ evidence output has a symbolic parent")
    protected = (Path.home().resolve(), CHECKOUT, ROOT, ROOT.parent)
    if output == Path(output.anchor) or any(path == output or path.is_relative_to(output) for path in protected):
        raise ValueError("C++ evidence output is too broad")
    if output.is_relative_to(ROOT) and not output.is_relative_to(ROOT / "build"):
        raise ValueError("C++ evidence output overlaps binding sources")
    if output.is_relative_to(CHECKOUT):
        relative = output.relative_to(CHECKOUT)
        if "build" not in relative.parts or relative.parts[-1] == "build":
            raise ValueError("C++ evidence output in checkout must be owned by a build directory")
    if any(output == path or output.is_relative_to(path) or path.is_relative_to(output) for path in inputs):
        raise ValueError("C++ evidence output overlaps an input")


def _invalidate(output: Path) -> None:
    if output.is_symlink() or output.exists() and not output.is_dir():
        raise ValueError("Unsafe C++ evidence output")
    if output.exists():
        shutil.rmtree(output)


def _rows(path: Path, header: str) -> list[list[str]]:
    data = _required(path).read_bytes()
    if not data.endswith(b"\n") or b"\r" in data:
        raise ValueError(f"C++ {path.name} must use LF-delimited UTF-8")
    lines = data.decode("utf-8").splitlines()
    rows = [line.split("\t") for line in lines[1:]]
    if not lines or lines[0] != header or not rows or any(
        len(row) != 2 or any(not cell for cell in row) for row in rows
    ) or rows != sorted(rows) or len({row[0] for row in rows}) != len(rows):
        raise ValueError(f"C++ {path.name} has invalid or duplicate raw rows")
    return rows


def _verify_raw(build: Path, evidence: Path, classifier: str) -> None:
    raw = build / "parity"
    _tree(raw)
    if {path.name for path in raw.iterdir()} != set(REPORTS + AUXILIARIES):
        raise ValueError("C++ raw evidence inventory is missing or unexpected")
    for name in AUXILIARIES:
        if not _required(raw / name).read_bytes():
            raise ValueError("C++ native/behavior auxiliary evidence is empty")
    _rows(raw / REPORTS[0], "compilerEvidenceId\tpublicSymbols")
    tests = _rows(raw / REPORTS[1], "executedTestId\tstatus")
    if len(tests) != 556 or any(status != "passed" for _, status in tests):
        raise ValueError("C++ raw evidence must contain exactly 556 unique passed tests")
    names: set[str] = set()
    for report in ("ctest-suite.xml", "ctest-value.xml"):
        suite = ET.fromstring(_required(evidence / report).read_bytes())
        cases = suite.findall("testcase")
        observed = {case.get("name") for case in cases}
        if suite.tag != "testsuite" or not cases or len(observed) != len(cases) or (
            int(suite.get("tests", "-1")) != len(cases)
        ) or any(int(suite.get(key, "0")) != 0 for key in ("failures", "errors", "skipped", "disabled")) or any(
            case.find(tag) is not None for case in cases for tag in ("failure", "error", "skipped")
        ) or None in observed or names.intersection(observed):
            raise ValueError("C++ CTest evidence contains missing, duplicate, failed or skipped tests")
        if (report == "ctest-value.xml" and observed != {VALUE_TEST}) or (
            report == "ctest-suite.xml" and VALUE_TEST in observed
        ):
            raise ValueError("C++ CTest split does not isolate the final full-value proof")
        names.update(observed)
    required = REQUIRED_TESTS | ({"codex_agent_native_loader_no_test_root_symbol"}
                                 if classifier != "windows-x64" else set())
    if not required.issubset(names):
        raise ValueError("C++ CTest evidence omits an existing capability/native proof")


def produce(canonical_api: Path, c_abi_bootstrap: Path, c_sdk_root: Path,
            native_library: Path, output: Path, *, classifier: str, sdk_compatibility: Path) -> None:
    if classifier not in CLASSIFIERS:
        raise ValueError("C++ requires an exact supported native classifier (not a host attestation)")
    canonical_api, c_abi_bootstrap, native_library = map(_required, (canonical_api, c_abi_bootstrap, native_library))
    sdk_compatibility = _required(sdk_compatibility)
    compatibility_bytes = sdk_compatibility.read_bytes()
    if not compatibility_bytes:
        raise ValueError("Imported C++ SDK compatibility declaration is empty")
    c_sdk_root = _required(c_sdk_root, directory=True)
    _tree(c_sdk_root)
    _required(c_sdk_root / "include/codex_agent.h")
    existing_compatibility = c_sdk_root / COMPATIBILITY_RESOURCE
    for parent in existing_compatibility.parents:
        if parent == c_sdk_root:
            break
        if parent.exists() or parent.is_symlink():
            _required(parent, directory=True)
    if existing_compatibility.exists() and _required(existing_compatibility).read_bytes() != compatibility_bytes:
        raise ValueError("C++ C SDK compatibility differs from the explicit imported declaration")
    relative = ("lib/libcodex_agent.dylib" if classifier.startswith("macos-") else
                "lib/libcodex_agent.so" if classifier.startswith("linux-") else "bin/codex_agent.dll")
    if native_library != _required(c_sdk_root / relative):
        raise ValueError("Explicit native library must be the exact CMake-selected C SDK member")
    for name in (("lib/libcodex_agent.so.1",) if classifier.startswith("linux-") else
                 ("lib/libcodex_agent.dll.a", "lib/codex_agent.lib") if classifier == "windows-x64" else ()):
        _required(c_sdk_root / name)
    output = Path(os.path.abspath(output.expanduser()))
    _validate_output(output, (canonical_api, c_abi_bootstrap, c_sdk_root, native_library, sdk_compatibility))
    _sources()
    _invalidate(output)
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".cpp-binding-evidence-", dir=output.parent) as temporary:
            evidence = Path(temporary).resolve() / "evidence"
            source, build, scratch = evidence / "source", evidence / "build", evidence / "scratch"
            source.mkdir(parents=True)
            scratch.mkdir()
            for name in SOURCE_FILES:
                shutil.copyfile(ROOT / name, source / name)
            for name in SOURCE_DIRECTORIES:
                shutil.copytree(ROOT / name, source / name, symlinks=True,
                                ignore=shutil.ignore_patterns("__pycache__"))
            _tree(source)
            private_sdk = evidence / "imported-c-sdk"
            shutil.copytree(c_sdk_root, private_sdk, symlinks=True)
            _tree(private_sdk)
            private_compatibility = private_sdk / COMPATIBILITY_RESOURCE
            if private_compatibility.exists() and private_compatibility.read_bytes() != compatibility_bytes:
                raise ValueError("C++ C SDK compatibility changed during private capture")
            private_compatibility.parent.mkdir(parents=True, exist_ok=True)
            private_compatibility.write_bytes(compatibility_bytes)
            environment = os.environ.copy()
            environment.update({"TMPDIR": str(scratch), "TMP": str(scratch), "TEMP": str(scratch)})
            if classifier == "windows-x64":
                # Only the private imported DLL directory is added. The source
                # tree and installed/system runtimes cannot supply this input.
                environment["PATH"] = str(private_sdk / "bin") + os.pathsep + environment.get("PATH", "")
            commands = (
                ("configure.log", ["cmake", "-S", str(source), "-B", str(build),
                    "-DCMAKE_BUILD_TYPE=Release", "-DCODEX_AGENT_CPP_BUILD_TESTS=ON",
                    "-DCODEX_AGENT_CPP_PACKAGE_ONLY=OFF", "-DCODEX_AGENT_CPP_INSTALL_PACKAGE=OFF",
                    f"-DCodexAgent_C_SDK_ROOT={private_sdk}", f"-DCodexAgent_NATIVE_CLASSIFIER={classifier}",
                    f"-DCodexAgent_CANONICAL_API_REPORT={canonical_api}",
                    f"-DCodexAgent_C_ABI_BOOTSTRAP_EVIDENCE={c_abi_bootstrap}"]),
                ("build.log", ["cmake", "--build", str(build), "--config", "Release"]),
                # Enum and full-value tests write the same TSVs. Finish the complete
                # prerequisite suite first, then publish the existing full union.
                ("ctest-suite.log", ["ctest", "--test-dir", str(build), "-C", "Release", "--parallel", "1",
                    "--output-on-failure", "--no-tests=error", "-E", f"^{VALUE_TEST}$",
                    "--output-junit", str(evidence / "ctest-suite.xml")]),
                ("ctest-value.log", ["ctest", "--test-dir", str(build), "-C", "Release", "--parallel", "1",
                    "--output-on-failure", "--no-tests=error", "-R", f"^{VALUE_TEST}$",
                    "--output-junit", str(evidence / "ctest-value.xml")]),
            )
            for name, command in commands:
                with (evidence / name).open("w+b") as log:
                    try:
                        subprocess.run(command, cwd=source, env=environment, stdout=log,
                                       stderr=subprocess.STDOUT, check=True)
                    except subprocess.CalledProcessError:
                        log.flush()
                        log.seek(0)
                        shutil.copyfileobj(log, sys.stderr.buffer)
                        sys.stderr.buffer.flush()
                        raise
                if name == "ctest-suite.log":
                    # The next CTest call overwrites both the enum TSVs and CTest's
                    # last-run log. Keep those original outputs before proceeding.
                    for original, retained in ((build / "parity", "prerequisite-evidence"),
                                               (build / "Testing", "prerequisite-ctest")):
                        _tree(original)
                        shutil.copytree(original, evidence / retained, symlinks=True)
            _verify_raw(build, evidence, classifier)
            for name in REPORTS:
                shutil.copyfile(build / "parity" / name, evidence / name)
            shutil.copyfile(source / "tests/value_parity_test.cpp", evidence / "test-program")
            # Original source, compiled consumers, CTest records and all native
            # auxiliaries remain execution evidence, never reusable product bytes.
            _tree(evidence)
            evidence.rename(output)
    except Exception:
        _invalidate(output)
        raise


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("canonical-api", "c-abi-bootstrap", "c-sdk-root", "native-library", "sdk-compatibility", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--classifier", choices=CLASSIFIERS, required=True)
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    produce(args.canonical_api, args.c_abi_bootstrap, args.c_sdk_root, args.native_library,
            args.output, classifier=args.classifier, sdk_compatibility=args.sdk_compatibility)


if __name__ == "__main__":
    main()
