"""Apple binary replay orchestration tests; the mocked leaf is not host or source proof."""

import subprocess
import unittest
from unittest.mock import patch

from ci.products.inventory import load_canonical_json_bytes, regular_file_inventory
from ci.products.sdk_maven import (
    verify_packaged_sdk_maven_phase,
    verify_sdk_maven_binary_predecessor,
)
import ci.tests.test_sdk_maven_apple as apple_fixture


class SdkMavenAppleBinaryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        apple_fixture.SdkMavenAppleTest.setUpClass.__func__(cls)

    copy_phase = apple_fixture.SdkMavenAppleTest.copy_phase
    rebind = apple_fixture.SdkMavenAppleTest.rebind

    def setUp(self):
        apple_fixture.SdkMavenAppleTest.setUp(self)
        self.binary_options = {
            "repository": self.root,
            "tooling_evidence": self.work / "tooling",
            "tooling_public_key": self.work / "pinned.pub",
            "java_executable": self.work / "java",
            "policy_revision": "a" * 40,
            "required_trust_domain": "development",
            "tooling_keyring": None,
            "tooling_keys_directory": None,
            "developer_directory": self.work / "Developer",
        }
        self.binary_calls = []
        self.binary_mutate = lambda arguments: None

    def apple_binary_gate(self, **arguments):
        self.binary_calls.append(arguments)
        self.assertEqual("0.2.9", arguments["sdk_version"])
        self.assertNotEqual(self.package / "outputs/apple", arguments["product_directory"])
        self.assertNotEqual(self.binary / "outputs/apple-binary", arguments["binary_frameworks"])
        self.assertEqual(
            regular_file_inventory(self.package / "outputs/apple"),
            regular_file_inventory(arguments["product_directory"]),
        )
        self.assertEqual(
            regular_file_inventory(self.binary / "outputs/apple-binary"),
            regular_file_inventory(arguments["binary_frameworks"]),
        )
        self.assertNotEqual(self.chain["compatibility"], arguments["expected_sdk_compatibility"])
        self.assertEqual(
            self.chain["compatibility"].read_bytes(),
            arguments["expected_sdk_compatibility"].read_bytes(),
        )
        producer = load_canonical_json_bytes(self.receipt.read_bytes())["producer"]
        self.assertEqual(producer["commit"], arguments["source_revision"])
        dynamic = {
            "product_directory", "binary_frameworks", "sdk_version",
            "expected_sdk_compatibility", "source_revision",
            "execution_capture_directory",
        }
        self.assertEqual(self.binary_options, {
            key: value for key, value in arguments.items() if key not in dynamic
        })
        self.binary_mutate(arguments)
        return regular_file_inventory(arguments["product_directory"])

    def verify(self, predecessor=False, **changes):
        options = changes.pop("apple_binary_verification", self.binary_options)
        with patch(
            "ci.products.sdk_apple_content.verify_sdk_apple_binary_package_content",
            side_effect=self.apple_binary_gate,
        ):
            if predecessor:
                return verify_sdk_maven_binary_predecessor(
                    self.binary,
                    self.binary_receipt,
                    self.package,
                    self.receipt,
                    self.chain["compatibility"],
                    apple_binary_verification=options,
                    **changes,
                )
            return verify_packaged_sdk_maven_phase(
                self.package,
                self.receipt,
                self.request,
                binary_stage_root=changes.pop("binary_stage_root", self.binary),
                binary_receipt_path=changes.pop("binary_receipt_path", self.binary_receipt),
                apple_binary_verification=options,
                **changes,
            )

    def test_both_phase_entries_replay_once_and_preserve_every_original(self):
        before = regular_file_inventory(self.work)
        receipts = {False: self.receipt.read_bytes(), True: self.binary_receipt.read_bytes()}

        for predecessor in (False, True):
            value, encoded = self.verify(predecessor)
            self.assertEqual(receipts[predecessor], encoded)
            self.assertEqual(load_canonical_json_bytes(encoded), value)

        self.assertEqual(2, len(self.binary_calls))
        self.assertEqual(before, regular_file_inventory(self.work))

    def test_capture_destination_is_forwarded_once_and_cannot_overlap_originals(self):
        for predecessor in (False, True):
            capture = self.work / f"external-capture-{predecessor}"
            self.verify(predecessor, apple_execution_capture_directory=capture)
            self.assertEqual(capture, self.binary_calls[-1]["execution_capture_directory"])
        self.assertEqual(2, len(self.binary_calls))
        for capture in (self.binary / "new", self.package / "new", self.receipt):
            with self.subTest(capture=capture), self.assertRaisesRegex(ValueError, "overlaps an original input"):
                self.verify(apple_execution_capture_directory=capture)
        self.assertEqual(2, len(self.binary_calls))

    def test_rejects_caller_supplied_leaf_fields_and_legacy_mixing(self):
        forbidden = {
            "source_revision": "b" * 40,
            "binary_frameworks": self.binary / "outputs/apple-binary",
            "expected_sdk_compatibility": self.chain["compatibility"],
        }
        for field, value in forbidden.items():
            for predecessor in (False, True):
                with self.subTest(field=field, predecessor=predecessor), self.assertRaises(ValueError):
                    self.verify(
                        predecessor,
                        apple_binary_verification={**self.binary_options, field: value},
                    )
        for predecessor in (False, True):
            with self.subTest(mixing=predecessor), self.assertRaises(ValueError):
                self.verify(predecessor, apple_verification=self.options)
        self.assertEqual([], self.binary_calls)

    def test_requires_exact_binary_context_identity_and_raw_manifest(self):
        with patch(
            "ci.products.sdk_apple_content.verify_sdk_apple_binary_package_content",
            side_effect=AssertionError("leaf before binary context"),
        ):
            for arguments in (
                {},
                {"binary_stage_root": self.binary},
                {"binary_receipt_path": self.binary_receipt},
            ):
                with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                    verify_packaged_sdk_maven_phase(
                        self.package,
                        self.receipt,
                        self.request,
                        apple_binary_verification=self.binary_options,
                        **arguments,
                    )

        android, android_receipt = self.copy_phase("binary", "sdk-android")
        with self.assertRaises(ValueError):
            self.verify(binary_stage_root=android, binary_receipt_path=android_receipt)

        binary = self.binary / "outputs/apple-binary/ios-arm64/CodexAgent.framework/CodexAgent"
        binary.write_bytes(binary.read_bytes() + b"stale\n")
        with self.assertRaises(ValueError):
            self.verify()
        self.assertEqual([], self.binary_calls)

    def test_private_snapshot_changes_and_leaf_failure_cannot_return_a_receipt(self):
        for field, relative in (
            ("product_directory", "CodexAgentPackage-0.2.9.zip"),
            ("binary_frameworks", "ios-arm64/CodexAgent.framework/CodexAgent"),
            ("expected_sdk_compatibility", None),
        ):
            def mutate(arguments, field=field, relative=relative):
                path = arguments[field]
                if relative is not None:
                    path /= relative
                path.write_bytes(path.read_bytes() + b"changed\n")

            self.binary_mutate = mutate
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.verify()

        def fail(_arguments):
            raise subprocess.CalledProcessError(1, "authenticated Apple binary verifier")

        self.binary_mutate = fail
        for predecessor in (False, True):
            with self.subTest(predecessor=predecessor), self.assertRaises(subprocess.CalledProcessError):
                self.verify(predecessor)

    def test_binary_replay_success_does_not_bypass_maven_tamper(self):
        checksum = next((self.package / "outputs/maven").rglob("*.sha256"))
        checksum.chmod(0o600)
        checksum.write_bytes(b"0" * 64 + b"\n")
        self.rebind(self.package, self.receipt)

        for predecessor in (False, True):
            with self.subTest(predecessor=predecessor), self.assertRaises(ValueError):
                self.verify(predecessor)


if __name__ == "__main__":
    unittest.main()
