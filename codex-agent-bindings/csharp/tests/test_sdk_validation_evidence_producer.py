from __future__ import annotations

import base64
import csv
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import produce_sdk_validation_evidence as producer  # noqa: E402
from produce_sdk_validation_evidence import produce  # noqa: E402


class CSharpSdkValidationEvidenceProducerTest(unittest.TestCase):
    # Mocked subprocesses test orchestration only; they are not compiler,
    # native-library, behavior, or product evidence.
    def test_full_build_and_three_run_sequence_publishes_exact_raw_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, Fixture(Path(temporary)) as fixture:
            fixture.output.mkdir()
            (fixture.output / "stale").write_text("stale\n")
            with patch.object(producer.subprocess, "run", side_effect=fixture.run) as runner:
                produce(*fixture.inputs, fixture.output)

            self.assertEqual(4, runner.call_count)
            build, native, complete, security = [call.args[0] for call in runner.call_args_list]
            self.assertEqual([str(fixture.dotnet), "build"], build[:2])
            self.assertIn("--no-restore", build)
            self.assertIn("--no-incremental", build)
            self.assertNotEqual(producer.PROJECT, Path(build[2]))
            self.assertEqual(str(fixture.library), build[-5].split("=", 1)[1])
            self.assertEqual(str(fixture.canonical), build[-4].split("=", 1)[1])
            self.assertEqual(str(fixture.bootstrap), build[-3].split("=", 1)[1])
            self.assertEqual(str(fixture.sdk), build[-2].split("=", 1)[1])
            self.assertEqual(str(fixture.compatibility), build[-1].split("=", 1)[1])
            self.assertEqual(["--real-mcp-values", str(fixture.library)], native[-2:])
            self.assertEqual(2, len(complete))
            self.assertEqual([*complete, "--runtime-loader-security"], security)
            self.assertEqual(
                {
                    "compiler-evidence.tsv", "executed-tests.tsv", "test-program", "native-evidence",
                    "dotnet-build-execution.json", "native-values-execution.json",
                    "complete-suite-execution.json", "loader-security-execution.json", "program",
                },
                {path.name for path in fixture.output.iterdir()},
            )
            for name, expected in zip(
                ("dotnet-build-execution.json", "native-values-execution.json", "complete-suite-execution.json",
                 "loader-security-execution.json"),
                fixture.command_outputs,
            ):
                raw = (fixture.output / name).read_bytes()
                envelope = json.loads(raw)
                self.assertEqual({"schemaVersion", "exitCode", "outputBase64"}, set(envelope))
                self.assertEqual(1, envelope["schemaVersion"])
                self.assertEqual(0, envelope["exitCode"])
                self.assertEqual(expected, base64.b64decode(envelope["outputBase64"], validate=True))
                self.assertEqual(
                    json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode() + b"\n",
                    raw,
                )
            self.assertEqual(
                producer.NATIVE_EVIDENCE,
                {path.name for path in (fixture.output / "native-evidence").iterdir()},
            )
            self.assertEqual("fixture compiled test program", (fixture.output / "test-program").read_text())
            for name in (*producer._native_program_files(), "CodexAgent.dll", "CodexAgent.Tests.deps.json",
                         "CodexAgent.Tests.runtimeconfig.json"):
                self.assertEqual("fixture retained dependency\n", (fixture.output / "program" / name).read_text())
            self.assertEqual((fixture.output / "test-program").read_bytes(),
                             (fixture.output / "program" / producer.TEST_PROGRAM).read_bytes())
            self.assertTrue(all(cwd != producer.ROOT for cwd in fixture.working_directories))
            for call in runner.call_args_list:
                environment = call.kwargs["env"]
                private_root = Path(call.kwargs["cwd"]).parent
                self.assertTrue(Path(environment["DOTNET_CLI_HOME"]).is_relative_to(private_root))
                self.assertTrue(Path(environment["TMPDIR"]).is_relative_to(private_root))
                declaration = json.loads(fixture.compatibility.read_bytes())
                for variant in declaration["runtime"]["embeddedVariants"]:
                    key = "CODEX_AGENT_TEST_IDENTITY_" + variant["target"].upper().replace("-", "_")
                    identity = json.loads(environment[key])
                    self.assertEqual(declaration["contract"]["digest"], identity["contractDigest"])
                    self.assertEqual(variant["componentId"], identity["componentId"])
                    self.assertEqual(variant["target"], identity["target"])

    def test_execution_failure_or_incomplete_results_leave_no_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, Fixture(Path(temporary)) as fixture:
            fixture.fail_at = 2
            with patch.object(producer.subprocess, "run", side_effect=fixture.run), \
                    self.assertRaises(subprocess.CalledProcessError):
                produce(*fixture.inputs, fixture.output)
            self.assertFalse(fixture.output.exists())

            fixture.fail_at = None
            fixture.omit_test = True
            with patch.object(producer.subprocess, "run", side_effect=fixture.run), \
                    self.assertRaisesRegex(ValueError, "exactly 556 unique passed"):
                produce(*fixture.inputs, fixture.output)
            self.assertFalse(fixture.output.exists())

            fixture.omit_test = False
            fixture.omit_native = True
            with patch.object(producer.subprocess, "run", side_effect=fixture.run), \
                    self.assertRaisesRegex(ValueError, "artifact inventory is not exact"):
                produce(*fixture.inputs, fixture.output)
            self.assertFalse(fixture.output.exists())

    def test_each_failed_command_surfaces_exact_binary_diagnostics_before_cleanup(self) -> None:
        diagnostics = (b"build failure\xff\n", b"native failure\x00\n", b"suite failure\r\n", b"security failure\xff\x00\n")
        for fail_at, expected in enumerate(diagnostics, 1):
            with self.subTest(fail_at=fail_at), tempfile.TemporaryDirectory() as temporary, \
                    Fixture(Path(temporary)) as fixture:
                fixture.command_outputs = diagnostics
                fixture.fail_at = fail_at
                parent_stderr = io.BytesIO()
                stderr = type("BinaryStderr", (), {"buffer": parent_stderr})()
                with patch.object(producer.sys, "stderr", stderr), \
                        patch.object(producer.subprocess, "run", side_effect=fixture.run), \
                        self.assertRaises(subprocess.CalledProcessError):
                    produce(*fixture.inputs, fixture.output)
                self.assertEqual(expected, parent_stderr.getvalue())
                self.assertFalse(fixture.output.exists())

    def test_missing_native_fixture_cannot_publish_otherwise_complete_results(self) -> None:
        for missing in producer._native_program_files():
            with self.subTest(missing=missing), tempfile.TemporaryDirectory() as temporary, Fixture(Path(temporary)) as fixture:
                fixture.omit_program_file = missing
                with patch.object(producer.subprocess, "run", side_effect=fixture.run), \
                        self.assertRaisesRegex(ValueError, "runnable/native program closure"):
                    produce(*fixture.inputs, fixture.output)
                self.assertFalse(fixture.output.exists())

    def test_windows_requires_import_library_before_invalidating_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, Fixture(Path(temporary)) as fixture:
            fixture.output.mkdir()
            sentinel = fixture.output / "preserve"
            sentinel.write_bytes(b"original output")
            with patch.object(producer.sys, "platform", "win32"), \
                    patch.object(producer.subprocess, "run") as runner, \
                    self.assertRaisesRegex(ValueError, "Windows C SDK import library"):
                produce(*fixture.inputs, fixture.output)
            runner.assert_not_called()
            self.assertEqual(b"original output", sentinel.read_bytes())

    def test_invalid_imported_identity_preserves_existing_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, Fixture(Path(temporary)) as fixture:
            fixture.output.mkdir()
            sentinel = fixture.output / "preserve"
            sentinel.write_bytes(b"original output")
            declaration = json.loads(fixture.compatibility.read_bytes())
            declaration["contract"]["digest"] = "not a digest"
            fixture.compatibility.write_text(json.dumps(declaration))
            with patch.object(producer.subprocess, "run") as runner, \
                    self.assertRaisesRegex(ValueError, "Contract digest is invalid"):
                produce(*fixture.inputs, fixture.output)
            runner.assert_not_called()
            self.assertEqual(b"original output", sentinel.read_bytes())

    def test_windows_native_build_and_loader_use_actual_dll_boundary(self) -> None:
        # Source wiring only: this is not Windows compiler/runtime evidence.
        import xml.etree.ElementTree as ET
        project = ET.parse(ROOT / "tests/CodexAgent.Tests/CodexAgent.Tests.csproj").getroot()
        targets = {target.attrib["Name"]: target for target in project.findall("Target")}
        commands = [entry.attrib["Command"] for entry in
                    targets["BuildFakeCodexAgentNativeLibraryWindows"].findall("Exec")]
        self.assertEqual(3, len(commands))
        for command, suffix in zip(commands, ("", "_missing_identity", "_abi_mismatch")):
            self.assertIn("-DCODEX_AGENT_BUILD", command)
            self.assertIn(f"codex_agent{suffix}.dll", command)
        real = targets["BuildRealMcpValueFixtureWindows"].find("Exec").attrib["Command"]
        self.assertIn("$(CodexAgentCSdkRoot)/lib/codex_agent.lib", real)
        self.assertNotIn("-DCODEX_AGENT_BUILD", real)
        self.assertIn("codex_agent_csharp_fixture.dll", real)
        source = (ROOT / "tests/CodexAgent.Tests/native/real_mcp_value_fixture.c").read_text()
        self.assertIn("#define CODEX_AGENT_FIXTURE_API __declspec(dllexport)", source)
        security = (ROOT / "tests/CodexAgent.Tests/RuntimeLoaderSecurity.cs").read_text()
        for suffix in ("_missing_identity", "_abi_mismatch"):
            self.assertIn(f'NativeName("{suffix}")', security)
        self.assertIn('DifferentDigest(value["contractDigest"]!.GetValue<string>())', security)
        fake = (ROOT / "tests/CodexAgent.Tests/native/fake_codex_agent.c").read_text()
        for target in producer.TARGETS:
            self.assertIn("CODEX_AGENT_TEST_IDENTITY_" + target.upper().replace("-", "_"), fake)

    def test_every_managed_fake_helper_import_has_an_explicit_native_export(self) -> None:
        suite = ROOT / "tests/CodexAgent.Tests"
        imports = {
            symbol
            for source in suite.glob("*.cs")
            for symbol in re.findall(
                r'\[DllImport\("codex_agent",\s*EntryPoint\s*=\s*"(codex_agent_test_[a-z_]+)"',
                source.read_text(),
            )
        }
        exports = re.findall(
            r"^CODEX_AGENT_API\s+\w+\s+(codex_agent_test_[a-z_]+)\([^;]*?\)\s*\{",
            (suite / "native/fake_codex_agent.c").read_text(),
            re.MULTILINE,
        )
        self.assertEqual(8, len(imports))
        self.assertEqual(len(exports), len(set(exports)))
        self.assertEqual(imports, set(exports))

    def test_invalid_input_preserves_existing_output_without_execution(self) -> None:
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

            fixture._file_at(fixture.compatibility, "{}\n")
            with patch.object(producer, "RESTORE_ASSETS", (fixture.root / "missing-assets.json",)), \
                    patch.object(producer.subprocess, "run") as runner, \
                    self.assertRaisesRegex(ValueError, "C# no-restore assets must be a regular file"):
                produce(*fixture.inputs, fixture.output)
            runner.assert_not_called()
            self.assertEqual("preserve\n", marker.read_text())

            fixture.test_source.unlink()
            with patch.object(producer.subprocess, "run") as runner, \
                    self.assertRaisesRegex(ValueError, "C# test program source must be a regular file"):
                produce(*fixture.inputs, fixture.output)
            runner.assert_not_called()
            self.assertEqual("preserve\n", marker.read_text())

    def test_unsafe_source_input_and_symbolic_scopes_never_delete(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, Fixture(Path(temporary)) as fixture:
            marker = fixture.imports / "preserve.txt"
            marker.write_text("preserve\n")
            with patch.object(producer.subprocess, "run") as runner, \
                    self.assertRaisesRegex(ValueError, "overlaps an input"):
                produce(*fixture.inputs, fixture.imports)
            runner.assert_not_called()
            self.assertEqual("preserve\n", marker.read_text())

            for output, message in (
                (Path(ROOT.anchor), "too broad"),
                (Path.home().resolve().parent, "too broad"),
                (producer.CHECKOUT.parent, "too broad"),
                (producer.CHECKOUT, "too broad"),
                (producer.ROOT, "too broad"),
                (producer.ROOT / "tests", "overlaps binding sources"),
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
            symbolic_marker = output / "preserve.txt"
            symbolic_marker.write_text("preserve\n")
            linked_parent = fixture.root / "linked-parent"
            try:
                os.symlink(real_parent, linked_parent, target_is_directory=True)
            except OSError as error:
                self.skipTest(f"directory symlinks unavailable: {error}")
            with patch.object(producer.subprocess, "run") as runner, \
                    self.assertRaisesRegex(ValueError, "symbolic parent"):
                produce(*fixture.inputs, linked_parent / "output")
            runner.assert_not_called()
            self.assertEqual("preserve\n", symbolic_marker.read_text())


class Fixture:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.checkout = self.root / "checkout"
        self.binding = self.checkout / "codex-agent-bindings" / "csharp"
        self.suite = self.binding / "tests" / "CodexAgent.Tests"
        self.project = self._file_at(self.suite / "CodexAgent.Tests.csproj", "<Project />\n")
        self.test_source = self._file_at(self.suite / "Program.cs", "// fixture suite\n")
        self._file_at(self.suite / "native" / "fixture.c", "/* fixture native source */\n")
        self.source_project = self._file_at(
            self.binding / "src" / "CodexAgent" / "CodexAgent.csproj", "<Project />\n",
        )
        self._file_at(self.binding / "src" / "CodexAgent" / "CodexAgent.cs", "// fixture binding\n")
        self._file_at(self.binding / "parity" / "capability-claims.tsv", "fixture\n")
        self.restore_assets = (
            self._file_at(self.source_project.parent / "obj" / "project.assets.json", "{}\n"),
            self._file_at(self.project.parent / "obj" / "project.assets.json", "{}\n"),
        )
        self.imports = self.root / "imports"
        self.dotnet = self._file("dotnet", "fixture tool")
        self.canonical = self._file("canonical-api.json", "{}\n")
        self.bootstrap = self._file("bootstrap.json", "{}\n")
        self.compatibility = self._file("sdk-compatibility.json", json.dumps({
            "contract": {"digest": "sha256:" + "b" * 64},
            "runtime": {"embeddedVariants": [
                {"target": target, "componentId": "sha256:" + str(index + 5) * 64}
                for index, target in enumerate(producer.TARGETS)
            ]},
        }) + "\n")
        self.sdk = self.imports / "c-sdk"
        self._file("c-sdk/include/codex_agent.h", "/* reviewed fixture header */\n")
        self.library = self._file("libcodex_agent.so", "fixture library")
        self.output = self.root / "output"
        self.inputs = (
            self.dotnet, self.canonical, self.bootstrap, self.compatibility, self.sdk, self.library,
        )
        self.calls = 0
        self.fail_at: int | None = None
        self.omit_test = False
        self.omit_native = False
        self.omit_program_file: str | None = None
        self.working_directories: list[Path] = []
        self.command_outputs = (b"build stdout\n\xffstderr\n", b"native values\x00\n", b"", b"security\xff\x00\n")
        self._producer_scope = patch.multiple(
            producer,
            ROOT=self.binding,
            CHECKOUT=self.checkout,
            SUITE_ROOT=self.suite,
            PROJECT=self.project,
            TEST_SOURCE=self.test_source,
            SOURCE_ROOTS=(self.binding / "src", self.suite, self.binding / "parity"),
            RESTORE_ASSETS=self.restore_assets,
        )

    def __enter__(self):
        self._producer_scope.start()
        return self

    def __exit__(self, exception_type, exception, traceback):
        self._producer_scope.stop()

    def _file(self, relative: str, contents: str) -> Path:
        return self._file_at(self.imports / relative, contents)

    def run(self, command, *, cwd, env, stdout, stderr, check):
        self.working_directories.append(Path(cwd))
        self.calls += 1
        if stderr is not subprocess.STDOUT:
            raise AssertionError("C# evidence command stderr is not combined with stdout")
        output_index = (0 if command[1] == "build" else 1 if "--real-mcp-values" in command
                        else 3 if "--runtime-loader-security" in command else 2)
        stdout.write(self.command_outputs[output_index])
        if self.calls == self.fail_at:
            raise subprocess.CalledProcessError(1, command)
        if command[1] == "build":
            program = Path(command[command.index("--output") + 1])
            self._file_at(program / "CodexAgent.Tests.dll", "fixture compiled test program")
            for name in (*producer._native_program_files(), "CodexAgent.dll", "CodexAgent.Tests.deps.json",
                         "CodexAgent.Tests.runtimeconfig.json"):
                if name != self.omit_program_file:
                    self._file_at(program / name, "fixture retained dependency\n")
        elif "--real-mcp-values" in command:
            program = Path(command[1]).parent
            artifacts = program / "artifacts"
            names = sorted(producer.NATIVE_EVIDENCE)
            if self.omit_native:
                names.pop()
            for name in names:
                self._file_at(artifacts / name, "testId\tstatus\nfixture\tpassed\n")
        elif "--runtime-loader-security" not in command:
            program = Path(command[1]).parent
            artifacts = program / "artifacts"
            self._tsv(
                artifacts / "compiler-evidence.tsv",
                ("compilerEvidenceId", "publicSymbols"),
                [("c-header:fixture", "CodexAgent.Fixture")],
            )
            tests = [(f"csharp.fixture:{index:03d}", "passed") for index in range(556)]
            if self.omit_test:
                tests.pop()
            self._tsv(artifacts / "executed-tests.tsv", ("executedTestId", "status"), tests)
        return subprocess.CompletedProcess(command, 0)

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
