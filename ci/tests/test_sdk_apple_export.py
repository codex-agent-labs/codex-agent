"""Fresh Apple exporter controls with explicitly simulated host/process only."""

from contextlib import ExitStack
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import product_reuse  # noqa: E402
import sdk_apple_export as worker  # noqa: E402
from products.inventory import load_canonical_json_bytes, regular_file_inventory  # noqa: E402
from products.receipt import write_output_manifest  # noqa: E402
from ci.tests.product_chain_support import write_receipt  # noqa: E402


class SdkAppleExportTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sdk-apple-export-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve() / "repository"
        self.root.mkdir()
        self.destination = self.root / "build/apple-export-worker"
        self.contract = self.root / "original-contract"
        self.native = self.root / "original-native"
        self.sdk = self.root / "verified-sdk-inputs"
        for directory in (self.contract, self.native, self.sdk):
            directory.mkdir()
        (self.contract / "payload.bin").write_bytes(b"current Contract\x00\xff")
        (self.native / "native.bin").write_bytes(b"current native\x00\xfe")
        self.request = self.sdk / worker.REQUEST_NAME
        self.request.write_bytes(b'{"caller":"verified S858"}\n')
        self.producer = {"repository": "owner/repository", "workflowPath": None,
                         "commit": "b" * 40, "tree": "c" * 40, "event": "local",
                         "runId": None, "runAttempt": None, "pullRequest": None}
        manifest = write_output_manifest(
            self.contract, "contract", "contract", "binary", "common", "0.8.0",
            {"contract-bundle": "payload.bin"},
        )
        self.receipt = self.root / "contract-receipt.json"
        receipt = write_receipt(
            self.receipt, component="contract", phase="binary", target="common",
            outputs=manifest["outputs"], upstream=[], context={"producer": self.producer},
            product="contract", version="0.8.0", version_identity="0.8.0",
        )
        self.record = {"stage": self.contract, "receiptPath": self.receipt, "receipt": receipt}
        self.plan = {"schemaVersion": 1, "product": "sdk", "component": "sdk-ios",
                     "phase": "package", "target": "ios",
                     "buildKey": "sha256:" + "a" * 64, "inputs": {}}
        self.process_exit = 0
        self.process_calls = 0
        self.after_process = lambda fields: None

    @property
    def distribution(self):
        return self.root / "codex-agent-runtime-ios/build/apple-verified-distribution"

    @property
    def execution(self):
        return self.root / "codex-agent-runtime-ios/build/apple-verified-distribution-execution"

    def process(self, command, **kwargs):
        self.process_calls += 1
        self.assertEqual(worker.FRESH_EXPORT_TASK, command[command.index(".") + 1])
        self.assertEqual(self.root, kwargs["cwd"])
        self.assertEqual(subprocess.STDOUT, kwargs["stderr"])
        self.assertFalse(kwargs["check"])
        fields = dict(value[2:].split("=", 1) for value in command if value.startswith("-P"))
        self.assertEqual({
            "codexAgent.candidateCommit", "codexAgent.candidateTree",
            "codexAgent.iosContractBinaryStage", "codexAgent.contractVersion",
            "codexAgent.iosNativeEvidenceDirectory", "codexAgent.sdkCompatibilityRequest",
        }, set(fields))
        for name in ("codexAgent.iosContractBinaryStage", "codexAgent.iosNativeEvidenceDirectory",
                     "codexAgent.sdkCompatibilityRequest"):
            self.assertFalse(Path(fields[name]).is_relative_to(self.destination))
        kwargs["stdout"].write(b"exact Gradle diagnostics\x00\xff\n")
        if self.process_exit == 0:
            self.distribution.mkdir(parents=True)
            (self.distribution / "verified-distribution-proof.json").write_bytes(b"proof\n")
            self.execution.mkdir(parents=True)
            (self.execution / "compiler-raw.bin").write_bytes(b"raw\x00\xfe")
            raw = self.execution / "xctest-raw/attempt-0/xcodebuild"
            raw.mkdir(parents=True)
            (raw / "stdout.bin").write_bytes(b"")
            (raw / "stderr.bin").write_bytes(b"")
        self.after_process(fields)
        return subprocess.CompletedProcess(command, self.process_exit)

    def invoke(self, **changes):
        phase_plan = changes.pop("phase_plan", self.plan)
        arguments = dict(
            producer=self.producer, current_contract=self.record,
            native_evidence=self.native, compatibility_request=self.request,
            destination=self.destination, repository_root=self.root, environ={},
        )
        arguments.update(changes)
        with ExitStack() as stack:
            stack.enter_context(patch("native_wrappers.host_classifier", return_value="macos-arm64"))
            stack.enter_context(patch.object(
                product_reuse, "_runtime_worker_environment",
                return_value=({}, self.root / "gradlew"),
            ))
            stack.enter_context(patch.object(product_reuse, "_runtime_worker_checkout"))
            stack.enter_context(patch.object(worker.subprocess, "run", side_effect=self.process))
            return worker.execute(phase_plan, **arguments)

    def test_fixed_export_retains_both_roots_and_lossless_diagnostics(self):
        originals = {"contract": regular_file_inventory(self.contract),
                     "native": regular_file_inventory(self.native),
                     "sdk": regular_file_inventory(self.sdk)}
        result = self.invoke()
        self.assertEqual(self.distribution, result["distribution"])
        self.assertEqual(self.execution, result["execution"])
        self.assertEqual(self.destination, result["diagnostics"])
        self.assertEqual(regular_file_inventory(self.distribution), result["inventories"]["distribution"])
        self.assertEqual(
            regular_file_inventory(self.execution, allow_empty=True),
            result["inventories"]["execution"],
        )
        self.assertEqual(b"", (self.execution / "xctest-raw/attempt-0/xcodebuild/stdout.bin").read_bytes())
        self.assertEqual(b"", (self.execution / "xctest-raw/attempt-0/xcodebuild/stderr.bin").read_bytes())
        self.assertEqual(b"exact Gradle diagnostics\x00\xff\n", (self.destination / "gradle.log").read_bytes())
        observed = load_canonical_json_bytes((self.destination / "execution.json").read_bytes())
        self.assertEqual(0, observed["returnCode"])
        self.assertIn(worker.FRESH_EXPORT_TASK, observed["command"])
        self.assertEqual(originals["contract"], regular_file_inventory(self.contract))
        self.assertEqual(originals["native"], regular_file_inventory(self.native))
        self.assertEqual(originals["sdk"], regular_file_inventory(self.sdk))

    def test_failure_keeps_raw_diagnostics_and_never_returns_outputs(self):
        self.process_exit = 7
        with self.assertRaisesRegex(ValueError, "exit code 7"):
            self.invoke()
        self.assertEqual(b"exact Gradle diagnostics\x00\xff\n", (self.destination / "gradle.log").read_bytes())
        self.assertEqual(7, load_canonical_json_bytes(
            (self.destination / "execution.json").read_bytes())["returnCode"])
        self.assertFalse(self.distribution.exists())
        self.assertFalse(self.execution.exists())

    def test_wrong_identity_host_or_stale_output_rejects_before_process(self):
        with patch("native_wrappers.host_classifier", return_value="macos-x64"), \
                patch.object(worker.subprocess, "run") as process, self.assertRaisesRegex(ValueError, "ARM64"):
            worker.execute(self.plan, producer=self.producer, current_contract=self.record,
                native_evidence=self.native, compatibility_request=self.request,
                destination=self.destination, repository_root=self.root, environ={})
        process.assert_not_called()
        for changes in ({"component": "sdk-core"}, {"target": "macos-arm64"}):
            with self.subTest(changes=changes), self.assertRaisesRegex(
                    ValueError, "Unsupported implemented iOS SDK phase identity"):
                self.invoke(phase_plan={**self.plan, **changes})
            self.assertEqual(0, self.process_calls)
            self.assertFalse(self.destination.exists())
        mismatched = {**self.record, "receipt": {**self.record["receipt"], "phase": "metadata"}}
        with self.assertRaisesRegex(ValueError, "authenticated original receipt"):
            self.invoke(current_contract=mismatched)
        self.assertEqual(0, self.process_calls)
        self.assertFalse(self.destination.exists())
        self.distribution.mkdir(parents=True)
        with patch.object(worker.subprocess, "run") as process, self.assertRaisesRegex(ValueError, "fresh"):
            self.invoke()
        process.assert_not_called()

    def test_original_input_mutation_after_process_rejects(self):
        for name in ("native", "contract", "sdk"):
            with self.subTest(name=name):
                self.destination = self.root / f"build/mutation-{name}"
                def mutate(fields):
                    path = {"native": self.native / "native.bin",
                            "contract": self.contract / "payload.bin",
                            "sdk": self.request}[name]
                    path.write_bytes(b"changed")
                self.after_process = mutate
                with self.assertRaisesRegex(ValueError, "input changed"):
                    self.invoke()
                {"native": self.native / "native.bin",
                 "contract": self.contract / "payload.bin",
                 "sdk": self.request}[name].write_bytes({
                     "native": b"current native\x00\xfe",
                     "contract": b"current Contract\x00\xff",
                     "sdk": b'{"caller":"verified S858"}\n',
                 }[name])
                for output in (self.distribution, self.execution):
                    if output.exists():
                        shutil.rmtree(output)


if __name__ == "__main__":
    unittest.main()
