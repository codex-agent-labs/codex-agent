"""Compiler-free orchestration fixtures, never actual Rust/native acceptance."""

import importlib.util
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location("rust_evidence_producer", Path(__file__).with_name("produce_sdk_validation_evidence.py"))
producer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(producer)


class RustEvidenceProducerTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.inputs = tuple(self.root / name for name in ("canonical.json", "bootstrap.json", "sdk", "native.dylib", "compatibility.json"))
        for path in (self.inputs[0], self.inputs[1], self.inputs[3], self.inputs[4]):
            path.write_text("declared fixture")
        (self.inputs[2] / "include").mkdir(parents=True)
        (self.inputs[2] / "include/codex_agent.h").write_text("fixture header")
        self.output = self.root / "output"

    def run_fixture(self, command, **kwargs):
        source = kwargs["cwd"]
        self.assertNotEqual(producer.ROOT, source)
        self.assertEqual((producer.ROOT / "tests/enum_parity.rs").read_bytes(),
                         (source / "tests/enum_parity.rs").read_bytes())
        self.assertFalse((source / "target").exists())
        self.assertEqual({"sdk-compatibility.json"}, {path.name for path in (source / "native").iterdir()})
        self.assertEqual(self.inputs[4].read_bytes(), (source / "native/sdk-compatibility.json").read_bytes())
        raw = source / "target/cross-language-evidence"
        raw.mkdir(parents=True)
        (raw / "compiler-evidence.tsv").write_text("compilerEvidenceId\tpublicSymbols\nfixture\tSymbol\n")
        (raw / "executed-tests.tsv").write_text("executedTestId\tstatus\n" +
            "".join(f"fixture-{index:03d}\tpassed\n" for index in range(556)))
        for name in ("real-sdk-leaf-service-null-boundary.c", "real-sdk-leaf-service-null-boundary.tsv",
                     "real-sdk-leaf-service-null-boundary", "value-header-evidence.c", "value-header-evidence.o"):
            (raw / name).write_bytes(b"original raw native fixture\x00" + name.encode())
        real_values = source / "target/real-value-graph"
        real_values.mkdir()
        (real_values / "libcodex_agent_rust_value_fixture.dylib").write_bytes(b"original real-value fixture")
        scratch = Path(kwargs["env"]["TMPDIR"]) / "codex-agent-rust-enum-evidence-123"
        scratch.mkdir()
        (scratch / "codex-agent-enum-evidence").write_bytes(b"original enum executable")
        kwargs["stdout"].write(b"synthetic Cargo command output; no compiler executed\n")

    def test_complete_offline_command_explicit_inputs_and_raw_only_outputs(self):
        self.output.mkdir()
        (self.output / "stale").write_text("stale")
        with patch.object(producer.subprocess, "run", side_effect=self.run_fixture) as run:
            producer.produce(*self.inputs, self.output)
        run.assert_called_once()
        self.assertEqual(["cargo", "test", "--locked", "--offline", "--", "--include-ignored"], run.call_args.args[0])
        env = run.call_args.kwargs["env"]
        for name, value in zip(("CODEX_AGENT_CANONICAL_API_REPORT", "CODEX_AGENT_C_ABI_BOOTSTRAP_EVIDENCE",
                                "CODEX_AGENT_C_SDK_ROOT", "CODEX_AGENT_REAL_SDK"), self.inputs):
            self.assertEqual(str(value), env[name])
        self.assertEqual(str(self.inputs[3]), env["CODEX_AGENT_LIBRARY"])
        self.assertEqual("true", env["CARGO_NET_OFFLINE"])
        self.assertEqual(str(run.call_args.kwargs["cwd"] / "target"), env["CARGO_TARGET_DIR"])
        self.assertEqual(env["TMPDIR"], env["TMP"])
        self.assertEqual(env["TMPDIR"], env["TEMP"])
        self.assertTrue(run.call_args.kwargs["check"])
        self.assertEqual({"compiler-evidence.tsv", "executed-tests.tsv", "test-program", "cargo-test.log",
                          "cross-language-evidence", "real-value-graph", "scratch", "source"},
                         {path.name for path in self.output.iterdir()})
        self.assertEqual((producer.ROOT / "tests/enum_parity.rs").read_bytes(), (self.output / "test-program").read_bytes())
        for name in ("real-sdk-leaf-service-null-boundary.c", "real-sdk-leaf-service-null-boundary.tsv",
                     "real-sdk-leaf-service-null-boundary", "value-header-evidence.c", "value-header-evidence.o"):
            self.assertEqual(b"original raw native fixture\x00" + name.encode(),
                             (self.output / "cross-language-evidence" / name).read_bytes())
        self.assertEqual(b"original real-value fixture",
                         (self.output / "real-value-graph/libcodex_agent_rust_value_fixture.dylib").read_bytes())
        self.assertEqual(b"original enum executable",
                         (self.output / "scratch/codex-agent-rust-enum-evidence-123/codex-agent-enum-evidence").read_bytes())
        for directory in ("src", "tests", "parity"):
            for path in (producer.ROOT / directory).rglob("*"):
                if path.is_file():
                    self.assertEqual(path.read_bytes(), (self.output / "source" / path.relative_to(producer.ROOT)).read_bytes())
        self.assertFalse((self.output / "source/target").exists())
        self.assertEqual(self.inputs[4].read_bytes(), (self.output / "source/native/sdk-compatibility.json").read_bytes())

    def test_source_native_payloads_are_excluded_and_only_explicit_compatibility_is_materialized(self):
        source = self.root / "stale-source"
        producer._copy_sources(source, producer.ROOT)
        native = source / "native"
        native.mkdir()
        (native / "sdk-compatibility.json").write_bytes(b"stale source declaration")
        for classifier in ("osx-arm64", "osx-x64", "linux-arm64", "linux-x64", "win-x64"):
            (native / classifier).mkdir()
            for library in ("libcodex_agent.dylib", "libcodex_agent.so", "codex_agent.dll"):
                (native / classifier / library).write_bytes(b"stale source runtime")
        with patch.object(producer, "ROOT", source), patch.object(producer.subprocess, "run", side_effect=self.run_fixture):
            producer.produce(*self.inputs, self.output)
        self.assertEqual({"sdk-compatibility.json"},
                         {path.name for path in (self.output / "source/native").iterdir()})
        self.assertEqual(self.inputs[4].read_bytes(), (self.output / "source/native/sdk-compatibility.json").read_bytes())
        self.assertEqual(b"stale source declaration", (native / "sdk-compatibility.json").read_bytes())

    def test_missing_explicit_compatibility_preserves_previous_evidence(self):
        self.output.mkdir()
        sentinel = self.output / "previous-proof"
        sentinel.write_bytes(b"original evidence")
        self.inputs[4].unlink()
        with patch.object(producer, "_invalidate") as invalidate, patch.object(producer.subprocess, "run") as run, \
                self.assertRaisesRegex(ValueError, "Required regular"):
            producer.produce(*self.inputs, self.output)
        invalidate.assert_not_called()
        run.assert_not_called()
        self.assertEqual(b"original evidence", sentinel.read_bytes())

    def test_missing_source_or_exact_program_preserves_previous_evidence_before_deletion(self):
        self.output.mkdir()
        sentinel = self.output / "previous-proof"
        sentinel.write_bytes(b"original evidence")
        for index, missing in enumerate((*producer.SOURCE_MEMBERS, "tests/enum_parity.rs")):
            with self.subTest(missing=missing):
                source = self.root / f"source-{index}"
                source.mkdir()
                for name in producer.SOURCE_MEMBERS:
                    if name == missing:
                        continue
                    if name in producer.SOURCE_DIRECTORIES:
                        (source / name).mkdir()
                    else:
                        (source / name).write_text("source fixture")
                if missing not in ("tests", "tests/enum_parity.rs"):
                    (source / "tests/enum_parity.rs").write_text("exact program fixture")
                with patch.object(producer, "ROOT", source), patch.object(producer, "_invalidate") as invalidate, \
                        patch.object(producer.subprocess, "run") as run, self.assertRaisesRegex(ValueError, "Required regular"):
                    producer.produce(*self.inputs, self.output)
                invalidate.assert_not_called()
                run.assert_not_called()
                self.assertEqual(b"original evidence", sentinel.read_bytes())

    def test_symbolic_auxiliary_evidence_is_not_followed_or_published(self):
        def symbolic(command, **kwargs):
            self.run_fixture(command, **kwargs)
            (kwargs["cwd"] / "target/cross-language-evidence/untrusted-link").symlink_to(self.inputs[0])
        with patch.object(producer.subprocess, "run", side_effect=symbolic), self.assertRaisesRegex(ValueError, "symbolic"):
            producer.produce(*self.inputs, self.output)
        self.assertFalse(self.output.exists())
        self.assertEqual("declared fixture", self.inputs[0].read_text())

    def test_failed_or_incomplete_run_clears_stale_evidence(self):
        self.output.mkdir()
        (self.output / "stale").write_text("stale")
        with patch.object(producer.subprocess, "run", side_effect=subprocess.CalledProcessError(1, ["cargo"])), \
                self.assertRaises(subprocess.CalledProcessError):
            producer.produce(*self.inputs, self.output)
        self.assertFalse(self.output.exists())

        def incomplete(command, **kwargs):
            self.run_fixture(command, **kwargs)
            (kwargs["cwd"] / "target/cross-language-evidence/executed-tests.tsv").write_text(
                "executedTestId\tstatus\nfixture\tpassed\n")
        with patch.object(producer.subprocess, "run", side_effect=incomplete), self.assertRaisesRegex(ValueError, "556"):
            producer.produce(*self.inputs, self.output)
        self.assertFalse(self.output.exists())
        self.assertFalse(any(path.name.startswith(".rust-binding-evidence-") for path in self.root.iterdir()))

    def test_failed_cargo_forwards_exact_binary_diagnostics_before_cleanup(self):
        original_program = (producer.ROOT / "tests/enum_parity.rs").read_bytes()
        for raw in (b"failure\xff\x00\r\n", b""):
            with self.subTest(raw=raw):
                self.output.mkdir()
                (self.output / "stale").write_bytes(b"old evidence")
                diagnostics = io.BytesIO()
                failure = subprocess.CalledProcessError(7, ["cargo"])

                def fail(command, **kwargs):
                    kwargs["stdout"].write(raw)
                    raise failure

                with patch.object(producer.subprocess, "run", side_effect=fail) as runner, \
                        patch.object(producer.sys, "stderr", SimpleNamespace(buffer=diagnostics)), \
                        self.assertRaises(subprocess.CalledProcessError) as caught:
                    producer.produce(*self.inputs, self.output)
                runner.assert_called_once()
                self.assertIs(failure, caught.exception)
                self.assertEqual(raw, diagnostics.getvalue())
                self.assertFalse(self.output.exists())
                self.assertEqual(original_program, (producer.ROOT / "tests/enum_parity.rs").read_bytes())
                self.assertFalse(any(self.root.glob(".rust-binding-evidence-*")))

    def test_missing_artifact_and_unsafe_outputs_never_start_cargo(self):
        with patch.object(producer.subprocess, "run") as run:
            for output in (self.root, self.inputs[2], producer.ROOT, producer.ROOT / "tests", producer.CHECKOUT):
                with self.assertRaises(ValueError):
                    producer.produce(*self.inputs, output)
            symbolic = self.root / "symbolic"
            symbolic.symlink_to(self.inputs[2], target_is_directory=True)
            with self.assertRaises(ValueError):
                producer.produce(*self.inputs, symbolic / "child")
            self.inputs[0].unlink()
            with self.assertRaises(ValueError):
                producer.produce(*self.inputs, self.output)
        run.assert_not_called()
        self.assertTrue((self.inputs[2] / "include/codex_agent.h").is_file())

    def test_all_artifact_arguments_required(self):
        args = [part for option, value in zip(("canonical-api", "c-abi-bootstrap", "c-sdk-root", "native-library", "sdk-compatibility", "output"),
                                              (*self.inputs, self.output)) for part in (f"--{option}", str(value))]
        self.assertEqual(self.output, producer.parse_args(args).output)
        for offset in range(0, len(args), 2):
            with patch("sys.stderr"), self.assertRaises(SystemExit):
                producer.parse_args(args[:offset] + args[offset + 2:])


if __name__ == "__main__":
    unittest.main()
