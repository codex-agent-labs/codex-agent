"""Synthetic controls for the fixed imported iOS SDK package worker."""

from contextlib import ExitStack
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


CI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CI_ROOT))

import product_reuse  # noqa: E402
import sdk_ios_package  # noqa: E402
from products.inventory import regular_file_inventory, sha256_bytes  # noqa: E402
from products.receipt import write_output_manifest  # noqa: E402
from ci.tests.product_chain_support import write_receipt  # noqa: E402


class SdkIosPackageExecutionTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sdk-ios-package-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.producer = {
            "repository": "owner/repository", "workflowPath": None,
            "commit": "a" * 40, "tree": "b" * 40, "event": "local",
            "runId": None, "runAttempt": None, "pullRequest": None,
        }
        self.plan = {
            "schemaVersion": 1, "product": "sdk", "component": "sdk-ios",
            "phase": "package", "target": "ios",
            "buildKey": "sha256:" + "c" * 64, "inputs": {},
        }
        self.contract = self.record("contract", "contract", "binary", "common", "0.2.0")
        self.binary = self.record("sdk", "sdk-ios", "binary", "ios", "0.8.0")
        self.distribution = self.root / "original/distribution"
        self.native = self.root / "original/native"
        self.distribution.mkdir(parents=True)
        self.native.mkdir(parents=True)
        (self.distribution / "verified-distribution-proof.json").write_bytes(b"synthetic proof\n")
        (self.distribution / "empty-raw-output.bin").write_bytes(b"")
        (self.native / "ios-native-evidence.json").write_bytes(b"synthetic native evidence\n")
        self.request_input = self.root / "original/request-input.json"
        self.request_input.write_bytes(b"synthetic authenticated request input\n")
        self.request = self.root / "original/request.json"
        self.request.write_bytes(b"synthetic authenticated compatibility request\n")
        self.compatibility = self.root / "original/sdk-compatibility.json"
        self.compatibility.write_bytes(b"synthetic caller compatibility\n")
        self.proof = self.root / "original/distribution-proof.json"
        self.proof.write_bytes(b"synthetic caller distribution proof\n")
        self.destination = self.root / "build/sdk-ios-package-worker"
        self.stage = self.root / "codex-agent-sdk/build/product-stage/sdk/sdk-ios/package"
        self.validation = (
            self.root / f"codex-agent-sdk/build/apple-sdk-package-tasks/{self.producer['tree']}/validation-evidence"
        )
        self.return_code = 0
        self.mutate = lambda: None
        self.create_outputs = True
        self.process_calls = []

    def record(self, product, component, phase, target, version):
        stage = self.root / f"original/{product}-{component}-{phase}-{target}"
        artifact = stage / "outputs/artifact.bin"
        artifact.parent.mkdir(parents=True)
        artifact.write_bytes(f"{product}/{component}/{phase}/{target}".encode())
        manifest = write_output_manifest(
            stage, product, component, phase, target, version,
            {f"{component}-{phase}": "outputs"},
        )
        receipt_path = self.root / f"original/{product}-{component}-{phase}-{target}.json"
        receipt = write_receipt(
            receipt_path, product=product, component=component, phase=phase, target=target,
            outputs=manifest["outputs"], upstream=[], context={"producer": self.producer},
            version=version, version_identity=version,
        )
        return {"stage": stage, "receiptPath": receipt_path, "receipt": receipt}

    def process(self, command, **arguments):
        self.process_calls.append(command)
        self.assertEqual(self.root, arguments["cwd"])
        self.assertEqual({"SAFE": "environment"}, arguments["env"])
        self.assertEqual(subprocess.STDOUT, arguments["stderr"])
        self.assertFalse(arguments["check"])
        self.assertEqual(".", command[command.index("-p") + 1])
        self.assertIn("ciProductPhase", command)
        self.assertNotIn("verifyTransportedCodexAgentIosSdkPackageClosure", " ".join(command))
        self.assertNotIn("exportCodexAgentIosVerifiedDistribution", " ".join(command))
        fields = dict(value[2:].split("=", 1) for value in command if value.startswith("-P"))
        self.assertEqual("package", fields["codexAgent.phase"])
        self.assertEqual(self.producer["commit"], fields["codexAgent.candidateCommit"])
        self.assertEqual(str(self.binary["stage"]), fields["codexAgent.sdkIosBinaryStageRoot"])
        self.assertEqual(str(self.distribution), fields["codexAgent.iosVerifiedDistributionDirectory"])
        arguments["stdout"].write(b"raw Gradle package diagnostics\x00\xff\n")
        if self.return_code == 0 and self.create_outputs:
            for name in ("apple", "evidence", "maven"):
                output = self.stage / f"outputs/{name}/artifact.bin"
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(f"synthetic {name}\n".encode())
            write_output_manifest(
                self.stage, "sdk", "sdk-ios", "package", "ios", "0.8.0",
                {name: f"outputs/{name}" for name in ("apple", "evidence", "maven")},
            )
            self.validation.mkdir(parents=True)
            (self.validation / "verification.json").write_bytes(b"synthetic validation\n")
            (self.validation / "stdout.bin").write_bytes(b"")
        self.mutate()
        return subprocess.CompletedProcess(command, self.return_code)

    def execute(self, **changes):
        arguments = {
            "producer": self.producer, "sdk_version": "0.8.0",
            "current_contract": self.contract, "sdk_binary": self.binary,
            "verified_distribution": self.distribution, "native_evidence": self.native,
            "compatibility_request": self.request,
            "expected_sdk_compatibility": self.compatibility,
            "expected_distribution_proof": self.proof,
            "repository_root": self.root, "destination": self.destination, "environ": {},
        }
        arguments.update(changes)
        request_inventory = {self.request_input: sha256_bytes(self.request_input.read_bytes())}
        with ExitStack() as stack:
            stack.enter_context(patch("native_wrappers.host_classifier", return_value="macos-arm64"))
            stack.enter_context(patch(
                "products.sdk_validation_inputs._request_inventory", return_value=request_inventory,
            ))
            stack.enter_context(patch.object(
                product_reuse, "_runtime_worker_environment",
                return_value=({"SAFE": "environment"}, self.root / "gradlew"),
            ))
            self.checkout = stack.enter_context(patch.object(product_reuse, "_runtime_worker_checkout"))
            stack.enter_context(patch.object(sdk_ios_package.subprocess, "run", side_effect=self.process))
            return sdk_ios_package.execute(self.plan, **arguments)

    def test_fixed_command_returns_canonical_stage_and_external_evidence(self):
        originals = {
            path: regular_file_inventory(path, allow_empty=True)
            for path in (self.contract["stage"], self.binary["stage"], self.distribution, self.native)
        }
        result = self.execute()
        self.assertEqual(self.stage, result["stage"])
        self.assertEqual(self.validation, result["validationEvidence"])
        self.assertEqual(regular_file_inventory(self.stage, allow_empty=True), result["outputInventory"])
        self.assertEqual(
            regular_file_inventory(self.validation, allow_empty=True),
            result["validationEvidenceInventory"],
        )
        self.assertEqual(b"raw Gradle package diagnostics\x00\xff\n",
                         (self.destination / "gradle.log").read_bytes())
        execution = json.loads((self.destination / "execution.json").read_bytes())
        self.assertEqual(0, execution["returnCode"])
        self.assertEqual(self.plan["buildKey"], execution["buildKey"])
        for path, inventory in originals.items():
            self.assertEqual(inventory, regular_file_inventory(path, allow_empty=True))

    def test_every_gradle_owned_cleanup_root_must_be_fresh_and_separate(self):
        sdk_build = self.root / "codex-agent-sdk/build"
        ios_build = self.root / "codex-agent-runtime-ios/build"
        roots = (
            sdk_build / "product-stage/sdk/sdk-ios/package",
            sdk_build / f"imported-sdk-binary-stages/{self.producer['tree']}/sdk-ios",
            sdk_build / f"sdk-compatibility/{self.producer['tree']}",
            sdk_build / f"apple-sdk-package-tasks/{self.producer['tree']}",
            ios_build / "imported-rust", ios_build / "imported-verified-apple",
            ios_build / "distributions", ios_build / "reports",
        )
        for root in roots:
            root.mkdir(parents=True)
            marker = root / "user-owned"
            marker.write_bytes(b"preserve\n")
            with self.subTest(root=root), self.assertRaisesRegex(ValueError, "fresh"):
                self.execute()
            self.assertEqual(b"preserve\n", marker.read_bytes())
            marker.unlink()
            root.rmdir()
        summary = ios_build / "swift-authentication-tests-summary.json"
        summary.parent.mkdir(parents=True, exist_ok=True)
        summary.write_bytes(b"preserve\n")
        with self.assertRaisesRegex(ValueError, "fresh"):
            self.execute()
        self.assertEqual(b"preserve\n", summary.read_bytes())
        self.assertEqual([], self.process_calls)

    def test_mapper_and_process_input_mutation_fail_closed(self):
        original_mapper = sdk_ios_package.package_properties
        before = self.compatibility.read_bytes()

        def mutate_mapper(*args, **kwargs):
            result = original_mapper(*args, **kwargs)
            self.compatibility.write_bytes(b"changed by mapper\n")
            return result

        with patch.object(sdk_ios_package, "package_properties", side_effect=mutate_mapper), \
                self.assertRaisesRegex(ValueError, "input changed"):
            self.execute()
        self.assertFalse(self.destination.exists())
        self.compatibility.write_bytes(before)

        native_before = (self.native / "ios-native-evidence.json").read_bytes()
        self.mutate = lambda: (self.native / "ios-native-evidence.json").write_bytes(b"changed\n")
        with self.assertRaisesRegex(ValueError, "input changed"):
            self.execute()
        self.assertFalse((self.stage / "phase-receipt.json").exists())
        (self.native / "ios-native-evidence.json").write_bytes(native_before)

    def test_elected_plan_mutation_during_process_fails_closed(self):
        original_key = self.plan["buildKey"]
        self.mutate = lambda: self.plan.__setitem__("buildKey", "sha256:" + "d" * 64)
        with self.assertRaisesRegex(ValueError, "input changed"):
            self.execute()
        self.assertNotEqual(original_key, self.plan["buildKey"])
        self.assertEqual(original_key, json.loads((self.destination / "execution.json").read_bytes())["buildKey"])
        self.assertFalse((self.stage / "phase-receipt.json").exists())

    def test_elected_producer_mutation_during_process_fails_closed(self):
        original_tree = self.producer["tree"]
        self.mutate = lambda: self.producer.__setitem__("tree", "d" * 40)
        with self.assertRaisesRegex(ValueError, "input changed"):
            self.execute()
        self.assertNotEqual(original_tree, self.producer["tree"])
        self.assertEqual(original_tree, json.loads((self.destination / "execution.json").read_bytes())["producer"]["tree"])
        self.assertFalse((self.stage / "phase-receipt.json").exists())

    def test_process_failure_preserves_raw_diagnostics_without_admission(self):
        self.return_code = 9
        with self.assertRaisesRegex(ValueError, "exit code 9"):
            self.execute()
        self.assertEqual(b"raw Gradle package diagnostics\x00\xff\n",
                         (self.destination / "gradle.log").read_bytes())
        self.assertEqual(9, json.loads((self.destination / "execution.json").read_bytes())["returnCode"])
        self.assertFalse((self.stage / "phase-receipt.json").exists())

    def test_identity_host_overlap_stale_and_incomplete_outputs_reject(self):
        with self.assertRaisesRegex(ValueError, "identity"):
            sdk_ios_package.execute(
                {**self.plan, "phase": "binary"}, producer=self.producer, sdk_version="0.8.0",
                current_contract=self.contract, sdk_binary=self.binary,
                verified_distribution=self.distribution, native_evidence=self.native,
                compatibility_request=self.request, expected_sdk_compatibility=self.compatibility,
                expected_distribution_proof=self.proof, repository_root=self.root,
                destination=self.destination, environ={},
            )
        with patch("native_wrappers.host_classifier", return_value="linux-x64"), \
                patch("products.sdk_validation_inputs._request_inventory", return_value={
                    self.request_input: sha256_bytes(self.request_input.read_bytes()),
                }), self.assertRaisesRegex(ValueError, "actual macOS ARM64"):
            sdk_ios_package.execute(
                self.plan, producer=self.producer, sdk_version="0.8.0",
                current_contract=self.contract, sdk_binary=self.binary,
                verified_distribution=self.distribution, native_evidence=self.native,
                compatibility_request=self.request, expected_sdk_compatibility=self.compatibility,
                expected_distribution_proof=self.proof, repository_root=self.root,
                destination=self.destination, environ={},
            )
        self.destination.mkdir(parents=True)
        marker = self.destination / "user-owned"
        marker.write_bytes(b"preserve\n")
        with self.assertRaisesRegex(ValueError, "fresh"):
            self.execute()
        self.assertEqual(b"preserve\n", marker.read_bytes())
        marker.unlink()
        self.destination.rmdir()

        self.create_outputs = False
        with self.assertRaises(ValueError):
            self.execute()


if __name__ == "__main__":
    unittest.main()
