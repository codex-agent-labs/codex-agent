"""Binary-only iOS package worker controls; mocked process execution is not host proof."""

from contextlib import ExitStack
import json
import shutil
import subprocess
import unittest
from unittest.mock import patch

from ci.tests import test_sdk_ios_package as fixtures
import product_reuse
import sdk_ios_package
from products.inventory import regular_file_inventory, sha256_bytes
from products.receipt import write_output_manifest


class SdkIosBinaryPackageWorkerTest(unittest.TestCase):
    record = fixtures.SdkIosPackageExecutionTest.record

    def setUp(self):
        fixtures.SdkIosPackageExecutionTest.setUp(self)
        self.return_code = 0
        self.mutate = lambda: None
        self.process_calls = []

    def process(self, command, **arguments):
        self.process_calls.append(command)
        self.assertEqual(self.root, arguments["cwd"])
        self.assertEqual({"SAFE": "environment"}, arguments["env"])
        self.assertEqual(subprocess.STDOUT, arguments["stderr"])
        self.assertFalse(arguments["check"])
        fields = dict(value[2:].split("=", 1) for value in command if value.startswith("-P"))
        self.assertEqual("true", fields["codexAgent.iosPackageFromBinary"])
        self.assertEqual(str(self.binary["stage"]), fields["codexAgent.sdkIosBinaryStageRoot"])
        self.assertEqual(str(self.contract["stage"]), fields["codexAgent.contractBinaryStage"])
        self.assertEqual("0.2.0", fields["codexAgent.contractVersion"])
        self.assertEqual(str(self.request), fields["codexAgent.sdkCompatibilityRequest"])
        self.assertEqual(self.producer["commit"], fields["codexAgent.candidateCommit"])
        self.assertEqual(self.producer["tree"], fields["codexAgent.candidateTree"])
        self.assertEqual(
            ("sdk", "sdk-ios", "package", "ios"),
            tuple(fields[f"codexAgent.{name}"] for name in ("product", "component", "phase", "target")),
        )
        self.assertTrue({
            "codexAgent.iosVerifiedDistributionDirectory",
            "codexAgent.iosNativeEvidenceDirectory",
            "codexAgent.iosExpectedSdkCompatibility",
            "codexAgent.iosExpectedDistributionProof",
        }.isdisjoint(fields))
        arguments["stdout"].write(b"raw binary package diagnostics\x00\xff\n")
        if self.return_code == 0:
            for name in ("apple", "evidence", "maven"):
                output = self.stage / f"outputs/{name}/artifact.bin"
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(f"synthetic {name}\n".encode())
            write_output_manifest(
                self.stage, "sdk", "sdk-ios", "package", "ios", "0.8.0",
                {name: f"outputs/{name}" for name in ("apple", "evidence", "maven")},
            )
        self.mutate()
        return subprocess.CompletedProcess(command, self.return_code)

    def execute(self, **changes):
        arguments = {
            "producer": self.producer,
            "sdk_version": "0.8.0",
            "current_contract": self.contract,
            "sdk_binary": self.binary,
            "compatibility_request": self.request,
            "repository_root": self.root,
            "destination": self.destination,
            "environ": {},
        }
        arguments.update(changes)
        request_inventory = {self.request_input: sha256_bytes(self.request_input.read_bytes())}
        with ExitStack() as stack:
            stack.enter_context(patch("native_wrappers.host_classifier", return_value="macos-arm64"))
            stack.enter_context(patch(
                "products.sdk_validation_inputs._request_inventory",
                return_value=request_inventory,
            ))
            stack.enter_context(patch.object(
                product_reuse,
                "_runtime_worker_environment",
                return_value=({"SAFE": "environment"}, self.root / "gradlew"),
            ))
            self.checkout = stack.enter_context(patch.object(product_reuse, "_runtime_worker_checkout"))
            stack.enter_context(patch.object(sdk_ios_package.subprocess, "run", side_effect=self.process))
            return sdk_ios_package.execute(self.plan, **arguments)

    def test_binary_mode_needs_no_legacy_apple_or_validation_inputs(self):
        shutil.rmtree(self.distribution)
        shutil.rmtree(self.native)
        self.compatibility.unlink()
        self.proof.unlink()
        originals = {
            path: regular_file_inventory(path)
            for path in (self.contract["stage"], self.binary["stage"])
        }

        result = self.execute()

        self.assertEqual({"stage", "diagnostics", "outputInventory"}, set(result))
        self.assertEqual(self.stage, result["stage"])
        self.assertEqual(self.destination, result["diagnostics"])
        self.assertEqual(regular_file_inventory(self.stage), result["outputInventory"])
        self.assertFalse(self.validation.exists())
        self.assertEqual(
            b"raw binary package diagnostics\x00\xff\n",
            (self.destination / "gradle.log").read_bytes(),
        )
        self.assertEqual(0, json.loads((self.destination / "execution.json").read_bytes())["returnCode"])
        for path, inventory in originals.items():
            self.assertEqual(inventory, regular_file_inventory(path))

    def test_partial_legacy_contexts_reject_before_mapping_or_process(self):
        legacy = {
            "verified_distribution": self.distribution,
            "native_evidence": self.native,
            "expected_sdk_compatibility": self.compatibility,
            "expected_distribution_proof": self.proof,
        }
        for name, value in legacy.items():
            with self.subTest(name=name), patch.object(
                sdk_ios_package,
                "binary_package_properties",
                side_effect=AssertionError("mapper called for partial legacy context"),
            ), self.assertRaisesRegex(ValueError, "supplied together"):
                self.execute(**{name: value})
        self.assertEqual([], self.process_calls)

    def test_every_binary_gradle_owned_root_must_be_fresh_and_is_preserved(self):
        sdk_build = self.root / "codex-agent-sdk/build"
        ios_build = self.root / "codex-agent-runtime-ios/build"
        roots = (
            self.stage,
            sdk_build / f"imported-sdk-binary-stages/{self.producer['tree']}/sdk-ios",
            sdk_build / f"sdk-compatibility/{self.producer['tree']}",
            sdk_build / f"apple-sdk-package-tasks/{self.producer['tree']}",
            ios_build / "imported-frameworks",
            ios_build / "XCFrameworks/release",
            ios_build / "release-xcframework",
            ios_build / "apple-distribution",
            ios_build / "distributions",
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
        self.assertEqual([], self.process_calls)

    def test_mapper_and_process_mutations_fail_closed(self):
        original_mapper = sdk_ios_package.binary_package_properties
        request_before = self.request.read_bytes()

        def mutate_mapper(*args, **kwargs):
            result = original_mapper(*args, **kwargs)
            self.request.write_bytes(b"changed by mapper\n")
            return result

        with patch.object(sdk_ios_package, "binary_package_properties", side_effect=mutate_mapper), \
                self.assertRaisesRegex(ValueError, "input changed"):
            self.execute()
        self.assertFalse(self.destination.exists())
        self.request.write_bytes(request_before)

        binary_file = self.binary["stage"] / "outputs/artifact.bin"
        binary_before = binary_file.read_bytes()
        self.mutate = lambda: binary_file.write_bytes(b"changed by process\n")
        with self.assertRaisesRegex(ValueError, "input changed"):
            self.execute()
        self.assertFalse((self.stage / "phase-receipt.json").exists())
        binary_file.write_bytes(binary_before)

    def test_process_failure_preserves_diagnostics_without_validation_or_admission(self):
        self.return_code = 7

        with self.assertRaisesRegex(ValueError, "exit code 7"):
            self.execute()

        self.assertEqual(
            b"raw binary package diagnostics\x00\xff\n",
            (self.destination / "gradle.log").read_bytes(),
        )
        self.assertEqual(7, json.loads((self.destination / "execution.json").read_bytes())["returnCode"])
        self.assertFalse(self.validation.exists())
        self.assertFalse((self.stage / "phase-receipt.json").exists())


if __name__ == "__main__":
    unittest.main()
