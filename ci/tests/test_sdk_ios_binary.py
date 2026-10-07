"""iOS SDK binary controls; execution and caller authority are synthetic."""

from contextlib import ExitStack
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


CI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CI_ROOT))

import sdk_ios_binary  # noqa: E402
import product_reuse  # noqa: E402
from products.inventory import load_canonical_json_bytes, regular_file_inventory  # noqa: E402
from products.receipt import write_output_manifest  # noqa: E402
from ci.tests.product_chain_support import write_receipt


class SdkIosBinaryPropertiesTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="sdk-ios-binary-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.stage = self.root / "contract-metadata"
        self.handoff = self.root / "contract-handoff"
        self.native = self.root / "native-evidence"
        for directory in (self.stage, self.handoff, self.native):
            directory.mkdir()
        self.version = "0.8.0"
        self.payload_bytes = b"synthetic authenticated Contract bundle\x00\xff"
        payload = self.stage / f"outputs/codex-agent-contract-{self.version}.zip"
        payload.parent.mkdir()
        payload.write_bytes(self.payload_bytes)
        manifest = write_output_manifest(
            self.stage, "contract", "contract", "metadata", "common", self.version,
            {"contract-bundle": payload.relative_to(self.stage).as_posix()},
        )
        self.receipt_path = self.root / "contract-metadata-receipt.json"
        self.producer = {
            "repository": "owner/repository", "workflowPath": None,
            "commit": "b" * 40, "tree": "c" * 40, "event": "local",
            "runId": None, "runAttempt": None, "pullRequest": None,
        }
        self.receipt = write_receipt(
            self.receipt_path, product="contract", component="contract",
            phase="metadata", target="common", outputs=manifest["outputs"], upstream=[],
            context={"producer": self.producer}, version=self.version,
            version_identity=self.version,
        )
        stem = f"codex-agent-contract-{self.version}"
        (self.handoff / f"{stem}.zip").write_bytes(self.payload_bytes)
        (self.handoff / f"{stem}.attestation.json").write_bytes(b"attestation\n")
        (self.handoff / f"{stem}.attestation.sig").write_bytes(b"signature\x00")
        (self.handoff / "public-key.pub").write_bytes(b"public key\n")
        (self.native / "native-tests-proof.json").write_bytes(b"native proof\n")
        self.record = {
            "stage": self.stage, "receiptPath": self.receipt_path, "receipt": self.receipt,
        }
        self.plan = {
            "schemaVersion": 1, "product": "sdk", "component": "sdk-ios",
            "phase": "binary", "target": "ios",
            "buildKey": "sha256:" + "a" * 64, "inputs": {},
        }
        self.destination = self.root / "build/ios-binary-worker"
        self.product_stage = self.root / "build/product-stage/sdk/sdk-ios/binary"
        self.return_code = 0
        self.launch_error = False
        self.after_process = lambda fields: None
        self.process_calls = []

    def invoke(self, **changes):
        arguments = {
            "producer": self.producer, "contract_metadata": self.record,
            "verified_contract_handoff": self.handoff, "native_evidence": self.native,
        }
        arguments.update(changes)
        return sdk_ios_binary.properties(self.plan, **arguments)

    def process(self, command, **arguments):
        self.process_calls.append(command)
        self.assertEqual(self.root, arguments["cwd"])
        self.assertEqual({"SAFE": "fixed environment"}, arguments["env"])
        self.assertEqual(subprocess.STDOUT, arguments["stderr"])
        self.assertFalse(arguments["check"])
        self.assertEqual(".", command[command.index("-p") + 1])
        self.assertIn("ciProductPhase", command)
        fields = dict(value[2:].split("=", 1) for value in command if value.startswith("-P"))
        self.assertEqual("sdk-ios", fields["codexAgent.component"])
        self.assertEqual("binary", fields["codexAgent.phase"])
        arguments["stdout"].write(b"raw Gradle diagnostics\x00\xff\n")
        if self.launch_error:
            raise OSError("synthetic launch failure")
        if self.return_code == 0:
            (self.product_stage / "outputs").mkdir(parents=True)
            (self.product_stage / "outputs/sdk-ios.klib").write_bytes(b"synthetic iOS binary\n")
            write_output_manifest(
                self.product_stage, "sdk", "sdk-ios", "binary", "ios", "0.8.0",
                {"sdk-binary": "outputs"},
            )
        self.after_process(fields)
        return subprocess.CompletedProcess(command, self.return_code)

    def execute(self, **changes):
        arguments = {
            "producer": self.producer, "sdk_version": "0.8.0",
            "contract_metadata": self.record,
            "verified_contract_handoff": self.handoff,
            "native_evidence": self.native, "repository_root": self.root,
            "destination": self.destination, "environ": {},
        }
        arguments.update(changes)
        with ExitStack() as stack:
            stack.enter_context(patch("native_wrappers.host_classifier", return_value="macos-arm64"))
            self.environment = stack.enter_context(patch.object(
                product_reuse, "_runtime_worker_environment",
                return_value=({"SAFE": "fixed environment"}, self.root / "gradlew"),
            ))
            self.checkout = stack.enter_context(patch.object(product_reuse, "_runtime_worker_checkout"))
            stack.enter_context(patch.object(sdk_ios_binary.subprocess, "run", side_effect=self.process))
            return sdk_ios_binary.execute(self.plan, **arguments)

    def test_exact_existing_settings_and_phase_properties(self) -> None:
        actual = self.invoke()
        stem = f"codex-agent-contract-{self.version}"
        self.assertEqual({
            "codexAgent.product": "sdk",
            "codexAgent.component": "sdk-ios",
            "codexAgent.phase": "binary",
            "codexAgent.target": "ios",
            "codexAgent.candidateCommit": self.producer["commit"],
            "codexAgent.candidateTree": self.producer["tree"],
            "codexAgent.contractPayload": str(self.handoff / f"{stem}.zip"),
            "codexAgent.contractMetadataReceipt": str(self.receipt_path),
            "codexAgent.contractAttestation": str(self.handoff / f"{stem}.attestation.json"),
            "codexAgent.contractAttestationSignature": str(self.handoff / f"{stem}.attestation.sig"),
            "codexAgent.contractPublicKey": str(self.handoff / "public-key.pub"),
            "codexAgent.contractVersion": self.version,
            "codexAgent.iosNativeEvidenceDirectory": str(self.native),
        }, actual)

    def test_plan_and_candidate_identity_are_exact(self) -> None:
        for change in ({"component": "sdk-core"}, {"phase": "package"}, {"target": "desktop"}):
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, "identity"):
                sdk_ios_binary.properties(
                    {**self.plan, **change}, producer=self.producer,
                    contract_metadata=self.record, verified_contract_handoff=self.handoff,
                    native_evidence=self.native,
                )
        with self.assertRaisesRegex(ValueError, "fields are invalid"):
            sdk_ios_binary.properties(
                {**self.plan, "unexpected": True}, producer=self.producer,
                contract_metadata=self.record, verified_contract_handoff=self.handoff,
                native_evidence=self.native,
            )
        with self.assertRaises(ValueError):
            self.invoke(producer={**self.producer, "commit": "not-a-git-id"})

    def test_metadata_receipt_manifest_version_and_payload_are_bound(self) -> None:
        raw = self.receipt_path.read_bytes()
        wrong_record = {**self.record, "receipt": {**self.receipt, "phase": "validation"}}
        with self.assertRaisesRegex(ValueError, "authenticated receipt"):
            self.invoke(contract_metadata=wrong_record)
        self.assertEqual(raw, self.receipt_path.read_bytes())

        payload = self.handoff / f"codex-agent-contract-{self.version}.zip"
        payload.write_bytes(b"different verified payload")
        with self.assertRaisesRegex(ValueError, "differs from the authenticated metadata bundle"):
            self.invoke()

    def test_missing_empty_unsafe_and_overlapping_inputs_reject(self) -> None:
        proof = self.native / "native-tests-proof.json"
        proof.write_bytes(b"")
        with self.assertRaisesRegex(ValueError, "empty file"):
            self.invoke()
        proof.write_bytes(b"native proof\n")

        signature = self.handoff / f"codex-agent-contract-{self.version}.attestation.sig"
        signature.write_bytes(b"")
        with self.assertRaisesRegex(ValueError, "must be nonempty"):
            self.invoke()
        signature.write_bytes(b"signature\x00")

        with self.assertRaisesRegex(ValueError, "must not overlap"):
            self.invoke(native_evidence=self.handoff)

        relative = Path("relative/native")
        with self.assertRaisesRegex(ValueError, "absolute normalized"):
            self.invoke(native_evidence=relative)

    def test_raw_receipt_mutation_rejects_without_changing_inputs(self) -> None:
        before = self.receipt_path.read_bytes()
        value = json.loads(before)
        value["productVersion"] = "0.8.1"
        self.receipt_path.write_text(json.dumps(value, sort_keys=True) + "\n")
        with self.assertRaises(ValueError):
            self.invoke()
        self.assertEqual(json.dumps(value, sort_keys=True) + "\n",
                         self.receipt_path.read_text())

    def test_execute_uses_fixed_command_and_returns_unadmitted_output(self) -> None:
        before = {
            "metadata": regular_file_inventory(self.stage),
            "handoff": regular_file_inventory(self.handoff),
            "native": regular_file_inventory(self.native),
        }
        result = self.execute()
        self.environment.assert_called_once_with(
            self.root, self.producer, self.destination, {}, build_directory=".")
        self.assertEqual({"stage", "diagnostics", "outputInventory"}, set(result))
        self.assertEqual(self.product_stage, result["stage"])
        self.assertEqual(self.destination, result["diagnostics"])
        self.assertEqual(regular_file_inventory(self.product_stage), result["outputInventory"])
        self.assertEqual(b"raw Gradle diagnostics\x00\xff\n", (self.destination / "gradle.log").read_bytes())
        execution = load_canonical_json_bytes((self.destination / "execution.json").read_bytes())
        self.assertEqual(0, execution["returnCode"])
        self.assertIsNone(execution["launchError"])
        self.assertEqual(before["metadata"], regular_file_inventory(self.stage))
        self.assertEqual(before["handoff"], regular_file_inventory(self.handoff))
        self.assertEqual(before["native"], regular_file_inventory(self.native))
        self.assertGreaterEqual(self.checkout.call_count, 3)

    def test_nonzero_and_launch_failure_keep_lossless_external_diagnostics(self) -> None:
        for launch in (False, True):
            with self.subTest(launch=launch):
                self.destination = self.root / f"build/failure-{launch}"
                self.return_code, self.launch_error = 7, launch
                with self.assertRaisesRegex(
                        OSError if launch else ValueError,
                        "launch failure" if launch else "exit code 7"):
                    self.execute()
                self.assertEqual(b"raw Gradle diagnostics\x00\xff\n", (self.destination / "gradle.log").read_bytes())
                execution = load_canonical_json_bytes((self.destination / "execution.json").read_bytes())
                self.assertEqual(None if launch else 7, execution["returnCode"])
                self.assertEqual("synthetic launch failure" if launch else None, execution["launchError"])
                self.assertFalse(self.product_stage.exists())

    def test_inputs_and_private_bytecode_are_rechecked_after_process(self) -> None:
        paths = {
            "metadata-receipt": self.receipt_path,
            "native": self.native / "native-tests-proof.json",
            "handoff": self.handoff / "public-key.pub",
            "bytecode": self.destination / "python-bytecode/injected.pyc",
        }
        for name, path in paths.items():
            with self.subTest(name=name):
                original = path.read_bytes() if path.exists() else None
                def mutate(fields, target=path):
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(b"changed during execution\n")
                self.after_process = mutate
                with self.assertRaisesRegex(ValueError, "changed|bytecode"):
                    self.execute()
                if original is None:
                    shutil.rmtree(self.destination / "python-bytecode", ignore_errors=True)
                else:
                    path.write_bytes(original)
                shutil.rmtree(self.destination, ignore_errors=True)
                shutil.rmtree(self.product_stage, ignore_errors=True)

    def test_mapper_cannot_mutate_an_original_before_the_execution_baseline(self) -> None:
        original = (self.native / "native-tests-proof.json").read_bytes()
        real_properties = sdk_ios_binary.properties

        def mutate(*args, **kwargs):
            result = real_properties(*args, **kwargs)
            (self.native / "native-tests-proof.json").write_bytes(b"changed by mapper\n")
            return result

        try:
            with patch.object(sdk_ios_binary, "properties", side_effect=mutate), \
                    self.assertRaisesRegex(ValueError, "input changed"):
                self.execute()
        finally:
            (self.native / "native-tests-proof.json").write_bytes(original)
        self.assertEqual([], self.process_calls)
        self.assertFalse(self.destination.exists())

    def test_wrong_host_version_and_stale_outputs_never_run(self) -> None:
        with patch("native_wrappers.host_classifier", return_value="macos-x64"), \
                patch.object(sdk_ios_binary.subprocess, "run") as process, \
                self.assertRaisesRegex(ValueError, "macOS ARM64"):
            sdk_ios_binary.execute(
                self.plan, producer=self.producer, sdk_version="0.8.0",
                contract_metadata=self.record, verified_contract_handoff=self.handoff,
                native_evidence=self.native, repository_root=self.root,
                destination=self.destination, environ={},
            )
        process.assert_not_called()
        with self.assertRaisesRegex(ValueError, "canonical SemVer"):
            self.execute(sdk_version="not-a-version")
        self.assertEqual([], self.process_calls)
        self.product_stage.mkdir(parents=True)
        sentinel = self.product_stage / "sentinel"
        sentinel.write_bytes(b"preserve me")
        with self.assertRaisesRegex(ValueError, "fresh"):
            self.execute()
        self.assertEqual(b"preserve me", sentinel.read_bytes())
        self.assertEqual([], self.process_calls)


if __name__ == "__main__":
    unittest.main()
