from __future__ import annotations

import csv
import os
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
    def test_full_build_and_two_run_sequence_publishes_exact_raw_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, Fixture(Path(temporary)) as fixture:
            fixture.output.mkdir()
            (fixture.output / "stale").write_text("stale\n")
            with patch.object(producer.subprocess, "run", side_effect=fixture.run) as runner:
                produce(*fixture.inputs, fixture.output)

            self.assertEqual(3, runner.call_count)
            build, native, complete = [call.args[0] for call in runner.call_args_list]
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
            self.assertEqual(
                {"compiler-evidence.tsv", "executed-tests.tsv", "test-program", "native-evidence"},
                {path.name for path in fixture.output.iterdir()},
            )
            self.assertEqual(
                producer.NATIVE_EVIDENCE,
                {path.name for path in (fixture.output / "native-evidence").iterdir()},
            )
            self.assertEqual("fixture compiled test program", (fixture.output / "test-program").read_text())
            self.assertTrue(all(cwd != producer.ROOT for cwd in fixture.working_directories))
            for call in runner.call_args_list:
                environment = call.kwargs["env"]
                private_root = Path(call.kwargs["cwd"]).parent
                self.assertTrue(Path(environment["DOTNET_CLI_HOME"]).is_relative_to(private_root))
                self.assertTrue(Path(environment["TMPDIR"]).is_relative_to(private_root))

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
        self.compatibility = self._file("sdk-compatibility.json", "{}\n")
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
        self.working_directories: list[Path] = []
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

    def run(self, command, *, cwd, env, check):
        self.working_directories.append(Path(cwd))
        self.calls += 1
        if self.calls == self.fail_at:
            raise subprocess.CalledProcessError(1, command)
        if command[1] == "build":
            program = Path(command[command.index("--output") + 1])
            self._file_at(program / "CodexAgent.Tests.dll", "fixture compiled test program")
        elif "--real-mcp-values" in command:
            program = Path(command[1]).parent
            artifacts = program / "artifacts"
            names = sorted(producer.NATIVE_EVIDENCE)
            if self.omit_native:
                names.pop()
            for name in names:
                self._file_at(artifacts / name, "testId\tstatus\nfixture\tpassed\n")
        else:
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
