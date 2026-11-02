"""Binary-only iOS package worker controls; mocked process execution is not host proof."""

from contextlib import ExitStack, contextmanager
import json
from pathlib import Path
import shutil
import subprocess
import unittest
from unittest.mock import patch

from ci.tests import test_sdk_ios_package as fixtures
import product_reuse
import sdk_ios_package
from products.inventory import regular_file_inventory, sha256_bytes
from products.receipt import write_output_manifest
from ci.tests.product_chain_support import write_receipt


class SdkIosBinaryPackageWorkerTest(unittest.TestCase):
    record = fixtures.SdkIosPackageExecutionTest.record

    def setUp(self):
        fixtures.SdkIosPackageExecutionTest.setUp(self)
        self.return_code = 0
        self.mutate = lambda: None
        self.process_calls = []
        self.owner_closed = False
        self.owner_exit_failure = False
        self.java = self.root / "tooling/java"
        self.java.parent.mkdir(); self.java.write_bytes(b"synthetic Java executable")
        self.jar = self.java.parent / "tooling.jar"; self.jar.write_bytes(b"synthetic signed JAR")
        self.developer = self.root / "Developer"; self.developer.mkdir()
        self.policy = self.root / "gradle/release/toolchains/sdk/ios-package.json"
        self.policy.parent.mkdir(parents=True); self.policy.write_bytes(b"{}\n")
        for target in ("ios-arm64", "ios-simulator-arm64"):
            file = self.binary["stage"] / f"outputs/apple-binary/{target}/CodexAgent.framework/CodexAgent"
            file.parent.mkdir(parents=True); file.write_bytes(b"synthetic unchanged archive")
        file = self.binary["stage"] / "outputs/maven/input.jar"
        file.parent.mkdir(); file.write_bytes(b"synthetic Maven")
        manifest = write_output_manifest(self.binary["stage"], "sdk", "sdk-ios", "binary", "ios", "0.8.0", {"fixture": "outputs"})
        self.binary["receipt"] = write_receipt(self.binary["receiptPath"], product="sdk", component="sdk-ios",
            phase="binary", target="ios", outputs=manifest["outputs"], upstream=[],
            context={"producer": self.producer}, version="0.8.0", version_identity="0.8.0")

    @contextmanager
    def tooling(self, *args, **kwargs):
        self.assertEqual("d" * 40, kwargs["policy_revision"])
        yield self.jar
        if self.owner_exit_failure:
            raise ValueError("signed tooling owner changed")
        self.owner_closed = True

    def sources(self, repository, revision, output):
        self.assertEqual(self.root, repository); self.assertEqual(self.producer["commit"], revision)
        output.mkdir(); (output / "source.txt").write_bytes(b"exact source fixture")
        return {"xcodeVersion": "26.6", "xcodeBuild": "17F1", "swiftVersion": "6.2"}

    def compatibility_producer(self, *, sdk_version, output):
        self.assertEqual("0.8.0", sdk_version)
        output.write_bytes(b"synthetic authenticated compatibility")

    def maven(self, source, output, compatibility, group, version, component):
        self.assertTrue(self.owner_closed)
        self.assertEqual(self.binary["stage"] / "outputs/maven", source)
        self.assertEqual(("io.github.codex-agent-labs", "0.8.0", "sdk-ios"), (group, version, component))
        output.mkdir(); (output / "artifact.bin").write_bytes(b"synthetic maven")

    def process(self, command, **arguments):
        self.process_calls.append(command)
        self.assertNotEqual(self.root, arguments["cwd"])
        self.assertEqual({"DEVELOPER_DIR": str(self.developer)}, arguments["env"])
        self.assertEqual(subprocess.STDOUT, arguments["stderr"])
        self.assertFalse(arguments["check"])
        self.assertEqual([str(self.java), "-cp", str(self.jar), "AppleSdkPackageMain", "0.8.0"], command[:5])
        self.assertEqual(str(self.stage / "outputs/apple"), command[9])
        self.assertEqual(str(self.policy), command[-1])
        self.assertNotIn("ciProductPhase", command)
        self.assertFalse(any("gradlew" in value for value in command))
        copied = Path(command[5]) / "ios-arm64/CodexAgent.framework/CodexAgent"
        original = self.binary["stage"] / "outputs/apple-binary/ios-arm64/CodexAgent.framework/CodexAgent"
        self.assertEqual(original.read_bytes(), copied.read_bytes())
        self.assertNotEqual((original.stat().st_dev, original.stat().st_ino), (copied.stat().st_dev, copied.stat().st_ino))
        arguments["stdout"].write(b"raw binary package diagnostics\x00\xff\n")
        if self.return_code == 0:
            output = self.stage / "outputs/apple/artifact.bin"
            output.parent.mkdir(); output.write_bytes(b"synthetic apple")
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
            "environ": {"DEVELOPER_DIR": str(self.developer)},
            "tooling_evidence": self.java.parent, "tooling_public_key": self.java,
            "java_executable": self.java, "policy_revision": "d" * 40,
            "required_trust_domain": "development",
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
                "_worker_process_environment",
                return_value={"DEVELOPER_DIR": str(self.developer)},
            ))
            stack.enter_context(patch.object(product_reuse, "_runtime_worker_environment", side_effect=AssertionError("Gradle bootstrap forbidden")))
            stack.enter_context(patch("products.inventory.git_regular_blob_bytes", return_value=self.policy.read_bytes()))
            stack.enter_context(patch("products.sdk_apple_package_source.capture_apple_package_sources", side_effect=self.sources))
            stack.enter_context(patch("products.sdk_compatibility.load_sdk_compatibility_request", return_value={"sdk_version": "0.8.0"}))
            stack.enter_context(patch("products.sdk_compatibility.produce_sdk_compatibility", side_effect=self.compatibility_producer))
            stack.enter_context(patch("products.sdk_maven.package_sdk_maven", side_effect=self.maven))
            stack.enter_context(patch("products.tooling.verified_tooling_capture", side_effect=self.tooling))
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
            (self.destination / "package.log").read_bytes(),
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

    def test_tampered_imported_binary_or_contract_rejects_before_gradle(self):
        for original in (self.binary, self.contract):
            artifact = original["stage"] / "outputs/artifact.bin"
            before = artifact.read_bytes()
            try:
                artifact.write_bytes(before + b"tampered")
                with self.subTest(component=original["receipt"]["component"]), \
                        self.assertRaisesRegex(ValueError, "Declared file inventory does not match"):
                    self.execute()
                self.assertEqual([], self.process_calls)
                self.assertFalse(self.destination.exists())
            finally:
                artifact.write_bytes(before)

    def test_every_standalone_owned_root_must_be_fresh_and_is_preserved(self):
        roots = (self.stage, self.destination)
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
            (self.destination / "package.log").read_bytes(),
        )
        self.assertEqual(7, json.loads((self.destination / "execution.json").read_bytes())["returnCode"])
        self.assertFalse(self.validation.exists())
        self.assertFalse((self.stage / "phase-receipt.json").exists())

    def test_late_tooling_exit_failure_keeps_produced_bytes_without_manifest(self):
        self.owner_exit_failure = True
        with self.assertRaisesRegex(ValueError, "owner changed"):
            self.execute()
        self.assertTrue((self.stage / "outputs/apple/artifact.bin").is_file())
        self.assertFalse((self.stage / "output-manifest.json").exists())
        self.assertFalse((self.stage / "phase-receipt.json").exists())

    def test_missing_or_invalid_tooling_policy_rejects_before_execution(self):
        with self.assertRaisesRegex(ValueError, "exact tooling policy"):
            self.execute(policy_revision="branch")
        self.assertEqual([], self.process_calls)


if __name__ == "__main__":
    unittest.main()
