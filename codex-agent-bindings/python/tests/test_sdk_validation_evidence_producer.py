from __future__ import annotations

import csv
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import produce_sdk_validation_evidence as producer  # noqa: E402
from produce_sdk_validation_evidence import EVIDENCE_ENV, produce  # noqa: E402


class PythonSdkValidationEvidenceProducerTest(unittest.TestCase):
    # Subprocesses are replaced only to test orchestration and cleanup. These
    # fixtures are not compiler, native-library, behavior, or product evidence.
    def test_complete_private_suite_and_original_native_evidence_are_published(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, Fixture(Path(temporary)) as fixture:
            fixture.output.mkdir()
            (fixture.output / "stale").write_text("stale\n")

            with patch.object(producer.subprocess, "run", side_effect=fixture.run) as runner:
                produce(*fixture.inputs, fixture.output)

            runner.assert_called_once()
            command = runner.call_args.args[0]
            self.assertEqual(
                [sys.executable, "-m", "unittest", "discover", "-s", str(fixture.private_tests), "-v"],
                command,
            )
            self.assertNotEqual(producer.ROOT, runner.call_args.kwargs["cwd"])
            self.assertIs(runner.call_args.kwargs["stderr"], subprocess.STDOUT)
            environment = runner.call_args.kwargs["env"]
            self.assertEqual(str(fixture.canonical), environment["CODEX_AGENT_CANONICAL_API_REPORT"])
            self.assertEqual(str(fixture.bootstrap), environment["CODEX_AGENT_C_ABI_BOOTSTRAP_EVIDENCE"])
            self.assertEqual(str(fixture.sdk), environment["CODEX_AGENT_C_SDK_ROOT"])
            self.assertEqual(str(fixture.library), environment["CODEX_AGENT_LIBRARY"])
            self.assertEqual("1", environment["PYTHONDONTWRITEBYTECODE"])
            self.assertEqual(environment["TMPDIR"], environment["TMP"])
            self.assertEqual(environment["TMPDIR"], environment["TEMP"])
            self.assertEqual(
                {
                    "compiler-evidence.tsv", "executed-tests.tsv", "test-program",
                    "python-test.log", "native-evidence",
                },
                {path.name for path in fixture.output.iterdir()},
            )
            self.assertEqual(
                {"enum-evidence", "mcp-value-evidence", "host-surface-evidence", "loader-security-evidence"},
                {path.name for path in (fixture.output / "native-evidence").iterdir()},
            )
            self.assertEqual(
                b"original enum program",
                (fixture.output / "native-evidence/enum-evidence" / fixture.enum_program).read_bytes(),
            )
            self.assertEqual(
                b"original MCP fixture",
                (fixture.output / "native-evidence/mcp-value-evidence" / fixture.mcp_library).read_bytes(),
            )
            self.assertEqual(
                b"synthetic unittest log; no suite executed\n",
                (fixture.output / "python-test.log").read_bytes(),
            )
            self.assertEqual(fixture.test_program.read_bytes(), (fixture.output / "test-program").read_bytes())
            self.assertEqual(b"original host object",
                             (fixture.output / "native-evidence/host-surface-evidence/host_surface.o").read_bytes())
            self.assertEqual({"schemaVersion": 1, "exitCode": 0, "outputBase64": ""}, json.loads(
                (fixture.output / "native-evidence/host-surface-evidence/compiler-execution.json").read_bytes()))
            self.assertEqual("stale source compatibility\n", fixture.source_compatibility.read_text())
            self.assertTrue(all(path.read_text() == "stale source Runtime\n" for path in fixture.source_runtimes))

    def test_enum_original_program_and_both_raw_streams_are_mandatory(self) -> None:
        executable = "codex-agent-enum-evidence" + (".exe" if os.name == "nt" else "")
        for name in ("enum_evidence.c", executable, "compiler-execution.json", "compiler-stderr-execution.json",
                     "runtime-execution.json", "runtime-stderr-execution.json"):
            for empty in (False, True):
                with self.subTest(name=name, empty=empty), tempfile.TemporaryDirectory() as temporary, Fixture(Path(temporary)) as fixture:
                    def run(*arguments, **kwargs):
                        result = fixture.run(*arguments, **kwargs)
                        path = Path(kwargs["cwd"]) / "build/enum-evidence" / name
                        if empty:
                            path.write_bytes(b"")
                        else:
                            path.unlink()
                        return result
                    with patch.object(producer.subprocess, "run", side_effect=run), self.assertRaises(ValueError):
                        produce(*fixture.inputs, fixture.output)
                    self.assertFalse(fixture.output.exists())

    def test_failed_or_incomplete_suite_cannot_leave_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, Fixture(Path(temporary)) as fixture:
            fixture.output.mkdir()
            (fixture.output / "stale").write_text("stale\n")
            with patch.object(
                producer.subprocess,
                "run",
                side_effect=subprocess.CalledProcessError(1, [sys.executable]),
            ), self.assertRaises(subprocess.CalledProcessError):
                produce(*fixture.inputs, fixture.output)
            self.assertFalse(fixture.output.exists())

            with patch.object(producer.subprocess, "run", side_effect=fixture.run_incomplete), \
                    self.assertRaisesRegex(ValueError, "exactly 556 unique passed"):
                produce(*fixture.inputs, fixture.output)
            self.assertFalse(fixture.output.exists())

            fixture.omit_native = True
            with patch.object(producer.subprocess, "run", side_effect=fixture.run), \
                    self.assertRaisesRegex(ValueError, "native evidence inventory is not exact"):
                produce(*fixture.inputs, fixture.output)
            self.assertFalse(fixture.output.exists())

    def test_failed_suite_forwards_exact_binary_diagnostics_before_cleanup(self) -> None:
        for raw in (b"failure\xff\x00\r\n", b""):
            with self.subTest(raw=raw), tempfile.TemporaryDirectory() as temporary, \
                    Fixture(Path(temporary)) as fixture:
                fixture.output.mkdir()
                (fixture.output / "stale").write_bytes(b"old evidence")
                diagnostics = io.BytesIO()
                failure = subprocess.CalledProcessError(7, [sys.executable])
                original_program = fixture.test_program.read_bytes()

                def fail(command, **kwargs):
                    kwargs["stdout"].write(raw)
                    raise failure

                with patch.object(producer.subprocess, "run", side_effect=fail) as runner, \
                        patch.object(producer.sys, "stderr", SimpleNamespace(buffer=diagnostics)), \
                        self.assertRaises(subprocess.CalledProcessError) as caught:
                    produce(*fixture.inputs, fixture.output)
                runner.assert_called_once()
                self.assertIs(failure, caught.exception)
                self.assertEqual(raw, diagnostics.getvalue())
                self.assertFalse(fixture.output.exists())
                self.assertEqual(original_program, fixture.test_program.read_bytes())
                self.assertFalse(any(fixture.output.parent.glob(".python-binding-evidence-*")))

    def test_missing_host_artifacts_or_diagnostics_cannot_publish_partial_evidence(self) -> None:
        for name in ("host_surface.c", "host_surface.o", "compiler-execution.json"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary, Fixture(Path(temporary)) as fixture:
                def run(*arguments, **kwargs):
                    result = fixture.run(*arguments, **kwargs)
                    (Path(kwargs["cwd"]) / "build/host-surface-evidence" / name).unlink()
                    return result
                with patch.object(producer.subprocess, "run", side_effect=run), self.assertRaises(ValueError):
                    produce(*fixture.inputs, fixture.output)
                self.assertFalse(fixture.output.exists())

    def test_loader_child_and_compiler_originals_are_mandatory_and_nonempty(self) -> None:
        case = "test_noncanonical_native_identity_fails"
        library = "noncanonical.dll" if sys.platform == "win32" else "libnoncanonical" + (
            ".dylib" if sys.platform == "darwin" else ".so")
        for name in ("child-execution.json", "noncanonical.c", "noncanonical-compiler-execution.json", library):
            for empty in (False, True):
                with self.subTest(name=name, empty=empty), tempfile.TemporaryDirectory() as temporary, Fixture(Path(temporary)) as fixture:
                    def run(*arguments, **kwargs):
                        result = fixture.run(*arguments, **kwargs)
                        path = Path(kwargs["cwd"]) / "build/loader-security-evidence" / case / name
                        if empty:
                            path.write_bytes(b"")
                        else:
                            path.unlink()
                        return result
                    with patch.object(producer.subprocess, "run", side_effect=run), self.assertRaises(ValueError):
                        produce(*fixture.inputs, fixture.output)
                    self.assertFalse(fixture.output.exists())

    def test_missing_mcp_library_cannot_publish_otherwise_complete_native_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, Fixture(Path(temporary)) as fixture:
            def run(*arguments, **kwargs):
                result = fixture.run(*arguments, **kwargs)
                (Path(kwargs["cwd"]) / "build/mcp-value-evidence" / fixture.mcp_library).unlink()
                return result
            with patch.object(producer.subprocess, "run", side_effect=run), \
                    self.assertRaisesRegex(ValueError, "MCP compiler evidence"):
                produce(*fixture.inputs, fixture.output)
            self.assertFalse(fixture.output.exists())

    def test_missing_import_or_program_preserves_existing_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, Fixture(Path(temporary)) as fixture:
            fixture.output.mkdir()
            marker = fixture.output / "preserve.txt"
            marker.write_text("preserve\n")
            fixture.compatibility.unlink()
            with patch.object(producer.subprocess, "run") as runner, \
                    self.assertRaisesRegex(ValueError, "SDK compatibility must be a regular file"):
                produce(*fixture.inputs, fixture.output)
            runner.assert_not_called()
            self.assertEqual("preserve\n", marker.read_text())

            fixture._file_at(fixture.compatibility, "explicit compatibility\n")
            fixture.test_program.unlink()
            with patch.object(producer.subprocess, "run") as runner, \
                    self.assertRaisesRegex(ValueError, "Python test program must be a regular file"):
                produce(*fixture.inputs, fixture.output)
            runner.assert_not_called()
            self.assertEqual("preserve\n", marker.read_text())

    def test_unsafe_or_input_overlapping_output_is_preserved_without_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, Fixture(Path(temporary)) as fixture:
            marker = fixture.imports / "preserve.txt"
            marker.write_text("preserve\n")
            with patch.object(producer.subprocess, "run") as runner, \
                    self.assertRaisesRegex(ValueError, "overlaps an input"):
                produce(*fixture.inputs, fixture.imports)
            runner.assert_not_called()
            self.assertEqual("preserve\n", marker.read_text())

            sdk_marker = fixture.sdk / "preserve.txt"
            sdk_marker.write_text("sdk\n")
            with patch.object(producer.subprocess, "run") as runner, \
                    self.assertRaisesRegex(ValueError, "overlaps an input"):
                produce(*fixture.inputs, fixture.sdk)
            runner.assert_not_called()
            self.assertEqual("sdk\n", sdk_marker.read_text())

    def test_symbolic_and_broad_outputs_reject_before_deletion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, Fixture(Path(temporary)) as fixture:
            for output, message in (
                (Path(ROOT.anchor), "too broad"),
                (Path.home().resolve().parent, "too broad"),
                (producer.CHECKOUT.parent, "too broad"),
                (producer.CHECKOUT, "too broad"),
                (producer.ROOT, "too broad"),
                (producer.ROOT / "tests", "overlaps binding sources"),
                (producer.ROOT / "consumer" / "build" / "proof", "overlaps binding sources"),
            ):
                with self.subTest(output=output), patch.object(producer, "_invalidate_output") as invalidator, \
                        patch.object(producer.subprocess, "run") as runner, \
                        self.assertRaisesRegex(ValueError, message):
                    produce(*fixture.inputs, output)
                invalidator.assert_not_called()
                runner.assert_not_called()

            real_parent = fixture.root / "real-parent"
            output = real_parent / "output"
            output.mkdir(parents=True)
            marker = output / "preserve.txt"
            marker.write_text("preserve\n")
            linked_parent = fixture.root / "linked-parent"
            try:
                os.symlink(real_parent, linked_parent, target_is_directory=True)
            except OSError as error:
                self.skipTest(f"directory symlinks unavailable: {error}")
            with patch.object(producer.subprocess, "run") as runner, \
                    self.assertRaisesRegex(ValueError, "symbolic parent"):
                produce(*fixture.inputs, linked_parent / "output")
            runner.assert_not_called()
            self.assertEqual("preserve\n", marker.read_text())

    def test_real_unittest_discovery_still_loads_the_existing_suite(self) -> None:
        result = subprocess.run(
            [
                sys.executable, "-m", "unittest", "discover", "-s", str(ROOT / "tests"),
                "-p", "test_enum_parity.py", "-k", "malformed_claims_fail_closed", "-v",
            ],
            cwd=ROOT,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertIn("test_malformed_claims_fail_closed", result.stdout)


class Fixture:
    mcp_library = "codex_agent_python_fixture.dll" if sys.platform == "win32" else "libcodex_agent_python_fixture" + (
        ".dylib" if sys.platform == "darwin" else ".so")
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.checkout = self.root / "checkout"
        self.binding = self.checkout / "codex-agent-bindings" / "python"
        self.test_program = self._file_at(self.binding / "tests/test_enum_parity.py", "# fixture program\n")
        self._file_at(self.binding / "tests/fixture.py", "# fixture suite\n")
        self._file_at(self.binding / "src/codex_agent/__init__.py", "# fixture package\n")
        source_native = self.binding / "src/codex_agent/native"
        self.source_compatibility = self._file_at(
            source_native / "sdk-compatibility.json", "stale source compatibility\n",
        )
        self.source_runtimes = []
        for classifier, library in (
            ("macos-arm64", "libcodex_agent.dylib"),
            ("macos-x64", "libcodex_agent.dylib"),
            ("linux-arm64", "libcodex_agent.so"),
            ("linux-x64", "libcodex_agent.so"),
            ("windows-x64", "codex_agent.dll"),
        ):
            self.source_runtimes.append(
                self._file_at(source_native / classifier / library, "stale source Runtime\n")
            )
        self._file_at(self.binding / "parity/capability-claims.tsv", "fixture\n")
        self._file_at(self.binding / "consumer/lifecycle_example.py", "# fixture consumer\n")
        self._file_at(self.binding / "tools/produce_sdk_validation_evidence.py", "# fixture tool\n")
        self._file_at(self.binding / "pyproject.toml", "[project]\nname='fixture'\n")
        self.imports = self.root / "imports"
        self.canonical = self._file("canonical-api.json", "{}\n")
        self.bootstrap = self._file("bootstrap.json", "{}\n")
        self.compatibility = self._file("sdk-compatibility.json", "explicit compatibility\n")
        self.sdk = self.imports / "c-sdk"
        self._file("c-sdk/include/codex_agent.h", "/* reviewed fixture header */\n")
        self.library = self._file("libcodex_agent.so", "fixture library")
        self.output = self.root / "output"
        self.inputs = (self.canonical, self.bootstrap, self.compatibility, self.sdk, self.library)
        self.private_tests: Path | None = None
        self.omit_native = False
        self._producer_scope = patch.multiple(
            producer,
            ROOT=self.binding,
            CHECKOUT=self.checkout,
            TEST_PROGRAM=self.test_program,
        )

    def __enter__(self):
        self._producer_scope.start()
        return self

    def __exit__(self, exception_type, exception, traceback):
        self._producer_scope.stop()

    def _file(self, relative: str, contents: str) -> Path:
        return self._file_at(self.imports / relative, contents)

    def run(self, command, *, cwd, env, stdout, stderr, check):
        source = Path(cwd)
        self.private_tests = source / "tests"
        native = source / "src/codex_agent/native"
        self.assert_equal({"sdk-compatibility.json"}, {path.name for path in native.iterdir()})
        self.assert_equal(self.compatibility.read_bytes(), (native / "sdk-compatibility.json").read_bytes())
        self._write_evidence(Path(env[EVIDENCE_ENV]), omit_test=False)
        self._write_native(source / "build")
        stdout.write(b"synthetic unittest log; no suite executed\n")
        return subprocess.CompletedProcess(command, 0)

    def run_incomplete(self, command, *, cwd, env, stdout, stderr, check):
        source = Path(cwd)
        self.private_tests = source / "tests"
        self._write_evidence(Path(env[EVIDENCE_ENV]), omit_test=True)
        self._write_native(source / "build")
        stdout.write(b"synthetic incomplete unittest log\n")
        return subprocess.CompletedProcess(command, 0)

    def _write_native(self, build: Path) -> None:
        self.enum_program = "codex-agent-enum-evidence" + (".exe" if os.name == "nt" else "")
        self._file_at(build / "enum-evidence" / self.enum_program, "original enum program")
        self._file_at(build / "enum-evidence/enum_evidence.c", "original enum source")
        for name in ("compiler-execution.json", "compiler-stderr-execution.json",
                     "runtime-execution.json", "runtime-stderr-execution.json"):
            self._file_at(build / "enum-evidence" / name,
                          '{"exitCode":0,"outputBase64":"","schemaVersion":1}\n')
        self._file_at(build / "host-surface-evidence/host_surface.c", "original host source")
        self._file_at(build / "host-surface-evidence/host_surface.o", "original host object")
        for directory in (("host-surface-evidence", "mcp-value-evidence") if not self.omit_native
                          else ("host-surface-evidence",)):
            self._file_at(build / directory / "compiler-execution.json",
                          '{"exitCode":0,"outputBase64":"","schemaVersion":1}\n')
        for case, names in producer.LOADER_NATIVE_CASES.items():
            self._file_at(build / "loader-security-evidence" / case / "child-execution.json",
                          '{"exitCode":0,"outputBase64":"","schemaVersion":1}\n')
            for name in names:
                library = name + ".dll" if sys.platform == "win32" else "lib" + name + (
                    ".dylib" if sys.platform == "darwin" else ".so")
                for member in (name + ".c", name + "-compiler-execution.json", library):
                    self._file_at(build / "loader-security-evidence" / case / member, "synthetic original native proof")
        if not self.omit_native:
            self._file_at(build / "mcp-value-evidence/real_mcp_value_fixture.c", "original MCP source")
            self._file_at(
                build / "mcp-value-evidence" / self.mcp_library,
                "original MCP fixture",
            )

    @staticmethod
    def assert_equal(expected, actual) -> None:
        if expected != actual:
            raise AssertionError(f"{expected!r} != {actual!r}")

    def _write_evidence(self, output: Path, omit_test: bool) -> None:
        self._tsv(
            output / "compiler-evidence.tsv",
            ("compilerEvidenceId", "publicSymbols"),
            [("python-analyzer:fixture", "codex_agent.Fixture")],
        )
        tests = [(f"python.fixture:{index:03d}", "passed") for index in range(556)]
        if omit_test:
            tests.pop()
        self._tsv(output / "executed-tests.tsv", ("executedTestId", "status"), tests)

    @staticmethod
    def _file_at(path: Path, contents: str) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents)
        return path

    @staticmethod
    def _tsv(path: Path, header: tuple[str, str], rows: list[tuple[str, str]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="\n") as destination:
            writer = csv.writer(destination, delimiter="\t", lineterminator="\n")
            writer.writerow(header)
            writer.writerows(sorted(rows))


if __name__ == "__main__":
    unittest.main()
