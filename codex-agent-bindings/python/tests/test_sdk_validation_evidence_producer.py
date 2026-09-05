from __future__ import annotations

import csv
import os
import subprocess
import sys
import tempfile
import unittest
from collections import defaultdict
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import produce_sdk_validation_evidence as producer  # noqa: E402
from produce_sdk_validation_evidence import EVIDENCE_ENV, produce  # noqa: E402


class PythonSdkValidationEvidenceProducerTest(unittest.TestCase):
    # Subprocesses are replaced only to test orchestration and cleanup. These
    # fixtures are not compiler, native-library, behavior, or product evidence.
    def test_complete_suite_isolated_evidence_is_published_exactly(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Fixture(Path(temporary))
            fixture.output.mkdir()
            (fixture.output / "stale").write_text("stale\n")

            with patch("produce_sdk_validation_evidence.subprocess.run", side_effect=fixture.run) as runner:
                produce(*fixture.inputs, fixture.output)

            runner.assert_called_once()
            command = runner.call_args.args[0]
            self.assertEqual(
                [sys.executable, "-m", "unittest", "discover", "-s", str(ROOT / "tests"), "-v"],
                command,
            )
            environment = runner.call_args.kwargs["env"]
            self.assertEqual(str(fixture.canonical), environment["CODEX_AGENT_CANONICAL_API_REPORT"])
            self.assertEqual(str(fixture.bootstrap), environment["CODEX_AGENT_C_ABI_BOOTSTRAP_EVIDENCE"])
            self.assertEqual(str(fixture.sdk), environment["CODEX_AGENT_C_SDK_ROOT"])
            self.assertEqual(str(fixture.library), environment["CODEX_AGENT_LIBRARY"])
            self.assertEqual("1", environment["PYTHONDONTWRITEBYTECODE"])
            self.assertEqual(
                {"compiler-evidence.tsv", "executed-tests.tsv", "test-program"},
                {path.name for path in fixture.output.iterdir()},
            )
            self.assertEqual((ROOT / "tests/test_enum_parity.py").read_bytes(),
                             (fixture.output / "test-program").read_bytes())

    def test_failed_or_incomplete_suite_cannot_leave_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Fixture(Path(temporary))
            fixture.output.mkdir()
            (fixture.output / "stale").write_text("stale\n")
            with patch(
                "produce_sdk_validation_evidence.subprocess.run",
                side_effect=subprocess.CalledProcessError(1, [sys.executable]),
            ), self.assertRaises(subprocess.CalledProcessError):
                produce(*fixture.inputs, fixture.output)
            self.assertFalse(fixture.output.exists())

            with patch("produce_sdk_validation_evidence.subprocess.run", side_effect=fixture.run_incomplete), \
                    self.assertRaisesRegex(ValueError, "exactly 556 unique passed"):
                produce(*fixture.inputs, fixture.output)
            self.assertFalse(fixture.output.exists())

    def test_missing_native_input_never_runs_the_suite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Fixture(Path(temporary))
            fixture.library.unlink()
            with patch("produce_sdk_validation_evidence.subprocess.run") as runner, \
                    self.assertRaisesRegex(ValueError, "native library must be a regular file"):
                produce(*fixture.inputs, fixture.output)
            runner.assert_not_called()
            self.assertFalse(fixture.output.exists())

    def test_missing_test_program_preserves_existing_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Fixture(Path(temporary))
            fixture.output.mkdir()
            marker = fixture.output / "preserve.txt"
            marker.write_text("preserve\n")
            required_file = producer._required_file

            def reject_test_program(path: Path, label: str) -> Path:
                if label == "Python test program":
                    raise ValueError("missing Python test program")
                return required_file(path, label)

            with patch.object(producer, "_required_file", side_effect=reject_test_program), \
                    patch.object(producer.subprocess, "run") as runner, \
                    self.assertRaisesRegex(ValueError, "missing Python test program"):
                produce(*fixture.inputs, fixture.output)
            runner.assert_not_called()
            self.assertEqual("preserve\n", marker.read_text())

    def test_unsafe_or_input_overlapping_output_is_preserved_without_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Fixture(Path(temporary))
            marker = fixture.root / "preserve.txt"
            marker.write_text("preserve\n")
            with patch("produce_sdk_validation_evidence.subprocess.run") as runner, \
                    self.assertRaisesRegex(ValueError, "overlaps an input"):
                produce(*fixture.inputs, fixture.root)
            runner.assert_not_called()
            self.assertEqual("preserve\n", marker.read_text())

            sdk_marker = fixture.sdk / "preserve.txt"
            sdk_marker.write_text("sdk\n")
            with patch("produce_sdk_validation_evidence.subprocess.run") as runner, \
                    self.assertRaisesRegex(ValueError, "overlaps an input"):
                produce(*fixture.inputs, fixture.sdk)
            runner.assert_not_called()
            self.assertEqual("sdk\n", sdk_marker.read_text())

    def test_symbolic_output_parent_is_rejected_without_deletion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Fixture(Path(temporary))
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
            with patch("produce_sdk_validation_evidence.subprocess.run") as runner, \
                    self.assertRaisesRegex(ValueError, "symbolic parent"):
                produce(*fixture.inputs, linked_parent / "output")
            runner.assert_not_called()
            self.assertEqual("preserve\n", marker.read_text())

    def test_broad_checkout_and_source_roots_reject_before_deletion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Fixture(Path(temporary))
            for output, message in (
                (Path(ROOT.anchor), "too broad"),
                (Path.home().resolve().parent, "too broad"),
                (ROOT.parents[2], "too broad"),
                (ROOT.parents[1], "too broad"),
                (ROOT, "too broad"),
                (ROOT / "tests", "overlaps binding sources"),
            ):
                with self.subTest(output=output), \
                        patch("produce_sdk_validation_evidence._invalidate_output") as invalidator, \
                        patch("produce_sdk_validation_evidence.subprocess.run") as runner, \
                        self.assertRaisesRegex(ValueError, message):
                    produce(*fixture.inputs, output)
                invalidator.assert_not_called()
                runner.assert_not_called()
            self.assertTrue((ROOT / "tests/test_enum_parity.py").is_file())

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
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.canonical = self._file("canonical-api.json", "{}\n")
        self.bootstrap = self._file("bootstrap.json", "{}\n")
        self.sdk = self.root / "c-sdk"
        self._file("c-sdk/include/codex_agent.h", "/* reviewed fixture header */\n")
        self.library = self._file("libcodex_agent.so", "fixture library")
        self.output = self.root / "output"
        self.inputs = (self.canonical, self.bootstrap, self.sdk, self.library)

    def _file(self, relative: str, contents: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents)
        return path

    def run(self, command, *, cwd, env, check):
        self._write_evidence(Path(env[EVIDENCE_ENV]), omit_test=False)
        return subprocess.CompletedProcess(command, 0)

    def run_incomplete(self, command, *, cwd, env, check):
        self._write_evidence(Path(env[EVIDENCE_ENV]), omit_test=True)
        return subprocess.CompletedProcess(command, 0)

    def _write_evidence(self, output: Path, omit_test: bool) -> None:
        with (ROOT / "parity/capability-claims.tsv").open(newline="", encoding="utf-8") as source:
            rows = list(csv.reader(source, delimiter="\t", strict=True))[1:]
        compiler: dict[str, set[str]] = defaultdict(set)
        tests = set()
        for _, symbols, test_ids, evidence_ids, _ in rows:
            for evidence_id in evidence_ids.split(","):
                compiler[evidence_id].update(symbols.split(","))
            tests.update(test_ids.split(","))
        if omit_test:
            tests.remove(sorted(tests)[0])
        self._tsv(
            output / "compiler-evidence.tsv",
            ("compilerEvidenceId", "publicSymbols"),
            [(evidence_id, ",".join(sorted(symbols))) for evidence_id, symbols in compiler.items()],
        )
        self._tsv(
            output / "executed-tests.tsv",
            ("executedTestId", "status"),
            [(test_id, "passed") for test_id in tests],
        )

    @staticmethod
    def _tsv(path: Path, header: tuple[str, str], rows: list[tuple[str, str]]) -> None:
        with path.open("w", encoding="utf-8", newline="\n") as destination:
            writer = csv.writer(destination, delimiter="\t", lineterminator="\n")
            writer.writerow(header)
            writer.writerows(sorted(rows))


if __name__ == "__main__":
    unittest.main()
