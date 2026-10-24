"""Real Maven/S858 fixtures with a mocked original-execution leaf, not host proof."""

import subprocess
import unittest
from unittest.mock import patch

from ci.products.inventory import load_canonical_json_bytes, regular_file_inventory
from ci.products.sdk_maven import (
    verify_packaged_sdk_maven_phase,
    verify_sdk_maven_binary_predecessor,
)
import ci.tests.test_sdk_maven_apple_binary as binary_fixture


class SdkMavenAppleOriginalTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        binary_fixture.SdkMavenAppleBinaryTest.setUpClass.__func__(cls)

    copy_phase = binary_fixture.SdkMavenAppleBinaryTest.copy_phase
    rebind = binary_fixture.SdkMavenAppleBinaryTest.rebind

    def setUp(self):
        binary_fixture.SdkMavenAppleBinaryTest.setUp(self)
        self.original_options = {
            key: value for key, value in self.binary_options.items()
            if key != "developer_directory"
        } | {
            "evidence_directory": self.work / "original-events",
            "execution_binding_file": self.work / "input-binding.json",
            "expected_binding_sha256": "sha256:" + "b" * 64,
            "expected_execution_files": self.work / "original-event-inventory.json",
        }
        self.original_calls = []
        self.original_mutate = lambda arguments: None

    def original_gate(self, **arguments):
        self.original_calls.append(arguments)
        self.assertEqual("0.2.9", arguments["sdk_version"])
        self.assertEqual(
            load_canonical_json_bytes(self.receipt.read_bytes())["producer"]["commit"],
            arguments["source_revision"],
        )
        for field, source in (
            ("product_directory", self.package / "outputs/apple"),
            ("binary_frameworks", self.binary / "outputs/apple-binary"),
        ):
            self.assertNotEqual(source, arguments[field])
            self.assertEqual(regular_file_inventory(source), regular_file_inventory(arguments[field]))
        self.assertNotEqual(self.chain["compatibility"], arguments["expected_sdk_compatibility"])
        self.assertEqual(self.chain["compatibility"].read_bytes(),
                         arguments["expected_sdk_compatibility"].read_bytes())
        dynamic = {"product_directory", "binary_frameworks", "sdk_version",
                   "source_revision", "expected_sdk_compatibility"}
        self.assertEqual(self.original_options,
                         {key: value for key, value in arguments.items() if key not in dynamic})
        self.original_mutate(arguments)
        return regular_file_inventory(arguments["product_directory"])

    def verify(self, predecessor=False, **changes):
        options = changes.pop("apple_original_verification", self.original_options)
        with patch("ci.products.sdk_apple_package_replay.verify_sdk_apple_original_package_content",
                   side_effect=self.original_gate):
            if predecessor:
                return verify_sdk_maven_binary_predecessor(
                    self.binary, self.binary_receipt, self.package, self.receipt,
                    self.chain["compatibility"], apple_original_verification=options, **changes,
                )
            return verify_packaged_sdk_maven_phase(
                self.package, self.receipt, self.request,
                binary_stage_root=changes.pop("binary_stage_root", self.binary),
                binary_receipt_path=changes.pop("binary_receipt_path", self.binary_receipt),
                apple_original_verification=options, **changes,
            )

    def test_both_entries_invoke_original_gate_once_and_preserve_originals(self):
        before = regular_file_inventory(self.work)
        for predecessor in (False, True):
            with self.subTest(predecessor=predecessor):
                calls = len(self.original_calls)
                value, raw = self.verify(predecessor)
                expected = self.binary_receipt if predecessor else self.receipt
                self.assertEqual(expected.read_bytes(), raw)
                self.assertEqual(load_canonical_json_bytes(raw), value)
                self.assertEqual(calls + 1, len(self.original_calls))
        self.assertEqual(before, regular_file_inventory(self.work))

    def test_policy_is_exact_and_cannot_override_derived_inputs(self):
        invalid = [None, {}, {
            key: value for key, value in self.original_options.items()
            if key != "expected_binding_sha256"
        }]
        invalid.extend({**self.original_options, field: value} for field, value in {
            "source_revision": "c" * 40,
            "sdk_version": "0.2.10",
            "product_directory": self.package / "outputs/apple",
            "binary_frameworks": self.binary / "outputs/apple-binary",
            "expected_sdk_compatibility": self.chain["compatibility"],
            "developer_directory": self.work / "Developer",
        }.items())
        for options in invalid:
            for predecessor in (False, True):
                with self.subTest(options=options, predecessor=predecessor), self.assertRaises(ValueError):
                    self.verify(predecessor, apple_original_verification=options)
        self.assertEqual([], self.original_calls)

    def test_modes_and_execution_capture_are_mutually_exclusive(self):
        before = regular_file_inventory(self.work)
        capture = self.work / "forbidden-capture"
        for changes in (
            {"apple_verification": self.options},
            {"apple_binary_verification": self.binary_options},
            {"apple_verification": self.options, "apple_binary_verification": self.binary_options},
            {"apple_execution_capture_directory": capture},
        ):
            for predecessor in (False, True):
                with self.subTest(changes=changes, predecessor=predecessor), self.assertRaises(ValueError):
                    self.verify(predecessor, **changes)
        self.assertFalse(capture.exists())
        self.assertEqual([], self.original_calls)
        self.assertEqual(before, regular_file_inventory(self.work))

    def test_requires_complete_exact_original_binary_predecessor(self):
        with patch("ci.products.sdk_apple_package_replay.verify_sdk_apple_original_package_content",
                   side_effect=AssertionError("original leaf before binary prerequisite")):
            for inputs in ({}, {"binary_stage_root": self.binary},
                           {"binary_receipt_path": self.binary_receipt}):
                with self.subTest(inputs=inputs), self.assertRaises(ValueError):
                    verify_packaged_sdk_maven_phase(
                        self.package, self.receipt, self.request,
                        apple_original_verification=self.original_options, **inputs,
                    )
        android, android_receipt = self.copy_phase("binary", "sdk-android")
        with self.assertRaises(ValueError):
            self.verify(binary_stage_root=android, binary_receipt_path=android_receipt)
        framework = self.binary / "outputs/apple-binary/ios-arm64/CodexAgent.framework/CodexAgent"
        framework.write_bytes(framework.read_bytes() + b"changed\n")
        with self.assertRaises(ValueError):
            self.verify()
        self.assertEqual([], self.original_calls)

    def test_leaf_failure_and_private_mutation_cannot_return_original_receipt(self):
        before = regular_file_inventory(self.work)
        for field, relative in (
            ("product_directory", "CodexAgentPackage-0.2.9.zip"),
            ("binary_frameworks", "ios-arm64/CodexAgent.framework/CodexAgent"),
            ("expected_sdk_compatibility", None),
        ):
            def mutate(arguments, field=field, relative=relative):
                path = arguments[field] if relative is None else arguments[field] / relative
                path.write_bytes(path.read_bytes() + b"changed\n")
            self.original_mutate = mutate
            for predecessor in (False, True):
                with self.subTest(field=field, predecessor=predecessor), self.assertRaises(ValueError):
                    self.verify(predecessor)

        def fail(_arguments):
            raise subprocess.CalledProcessError(1, "authenticated original package replay")

        self.original_mutate = fail
        for predecessor in (False, True):
            with self.subTest(predecessor=predecessor), self.assertRaises(subprocess.CalledProcessError):
                self.verify(predecessor)
        self.assertEqual(before, regular_file_inventory(self.work))

    def test_original_gate_success_does_not_bypass_maven_checksum_verification(self):
        checksum = next((self.package / "outputs/maven").rglob("*.sha256"))
        checksum.chmod(0o600)
        checksum.write_bytes(b"0" * 64 + b"\n")
        self.rebind(self.package, self.receipt)
        for predecessor in (False, True):
            with self.subTest(predecessor=predecessor), self.assertRaises(ValueError):
                self.verify(predecessor)


if __name__ == "__main__":
    unittest.main()
