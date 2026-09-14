"""Real Maven replay/S858 fixtures; mocked Apple leaf is orchestration, not host proof."""

from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from ci.products.inventory import canonical_json_bytes, load_canonical_json_bytes, regular_file_inventory, snapshot_regular_tree
from ci.products.receipt import write_output_manifest
from ci.products.sdk_maven import verify_packaged_sdk_maven_phase, verify_sdk_maven_binary_predecessor
import ci.tests.test_product_sdk_maven as fixtures


class SdkMavenAppleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.SdkMavenPhaseVerificationTest.setUpClass.__func__(cls)

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sdk-maven-apple-test-")
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name).resolve()
        self.package, self.receipt = self.copy_phase("package")
        self.binary, self.binary_receipt = self.copy_phase("binary")
        apple = self.package / "outputs/apple"
        apple.mkdir()
        for name in ("CodexAgentPackage-0.2.9.zip", "CodexAgent-0.2.9.xcframework.zip",
                     "CodexAgent-0.2.9.xcframework.zip.sha256"):
            (apple / name).write_bytes(f"synthetic original Apple {name}\n".encode())
        self.rebind(self.package, self.receipt)
        self.expectation = self.work / "sdk-compatibility.json"
        self.expectation.write_bytes(self.chain["compatibility"].read_bytes())
        self.options = dict(validation_evidence_directory=self.work / "original-apple-evidence",
            expected_sdk_compatibility=self.expectation, expected_distribution_proof=self.work / "original-proof.json",
            repository=self.root, tooling_evidence=self.work / "tooling", tooling_public_key=self.work / "pinned.pub",
            java_executable=self.work / "java", policy_revision="a" * 40, required_trust_domain="development",
            tooling_keyring=None, tooling_keys_directory=None)
        self.calls = []
        self.mutate = lambda arguments: None

    def copy_phase(self, phase, component="sdk-ios"):
        source, receipt = (self.stages if phase == "package" else self.binary_stages)[component]
        copied = self.work / f"{component}-{phase}"
        snapshot_regular_tree(source, copied)
        copied_receipt = self.work / f"{component}-{phase}-receipt.json"
        copied_receipt.write_bytes(receipt.read_bytes())
        return copied, copied_receipt

    def rebind(self, stage, receipt, kind="apple"):
        value = load_canonical_json_bytes(receipt.read_bytes())
        roots = {"maven": "outputs/maven", "evidence": "outputs/evidence"}
        if (stage / "outputs/apple-binary").exists():
            roots["apple-binary"] = "outputs/apple-binary"
        if (stage / "outputs/apple").exists():
            roots[kind] = "outputs/apple"
        manifest = write_output_manifest(stage, value["product"], value["component"], value["phase"],
                                         value["target"], value["productVersion"], roots)
        value["outputs"] = manifest["outputs"]
        receipt.write_bytes(canonical_json_bytes(value))

    def apple_gate(self, **arguments):
        self.calls.append(arguments)
        self.assertEqual("0.2.9", arguments["sdk_version"])
        self.assertNotEqual(self.package / "outputs/apple", arguments["product_directory"])
        self.assertNotEqual(self.expectation, arguments["expected_sdk_compatibility"])
        self.assertEqual(self.chain["compatibility"].read_bytes(), arguments["expected_sdk_compatibility"].read_bytes())
        self.assertEqual({key: value for key, value in self.options.items() if key != "expected_sdk_compatibility"},
                         {key: value for key, value in arguments.items()
                          if key not in {"product_directory", "sdk_version", "expected_sdk_compatibility"}})
        self.mutate(arguments)
        return regular_file_inventory(arguments["product_directory"])

    def verify(self, predecessor=False, **changes):
        options = changes.pop("apple_verification", self.options)
        with patch("ci.products.sdk_apple_content.verify_sdk_apple_package_content", side_effect=self.apple_gate):
            if predecessor:
                return verify_sdk_maven_binary_predecessor(
                    self.binary, self.binary_receipt, self.package, self.receipt, self.chain["compatibility"],
                    apple_verification=options, **changes,
                )
            return verify_packaged_sdk_maven_phase(self.package, self.receipt, self.request,
                                                  apple_verification=options, **changes)

    def test_both_entries_require_gate_and_preserve_original_maven_apple_and_receipts(self):
        before = regular_file_inventory(self.work)
        for predecessor in (False, True):
            value, original = self.verify(predecessor)
            expected = self.binary_receipt if predecessor else self.receipt
            self.assertEqual(expected.read_bytes(), original)
            self.assertEqual(load_canonical_json_bytes(original), value)
        self.assertEqual(2, len(self.calls))
        self.assertEqual(before, regular_file_inventory(self.work))

    def test_absent_incomplete_or_overridden_inputs_never_allow_apple_outputs(self):
        missing = {key: value for key, value in self.options.items() if key != "expected_distribution_proof"}
        for options in (None, {}, missing, {**self.options, "product_directory": self.package / "outputs/apple"}):
            for predecessor in (False, True):
                with self.subTest(options=options, predecessor=predecessor), self.assertRaises(ValueError):
                    self.verify(predecessor, apple_verification=options)
        self.assertEqual([], self.calls)

    def test_missing_compatibility_fails_structural_preflight_before_any_semantic_gate(self):
        android, android_receipt = self.copy_phase("package", "sdk-android")
        for stage, receipt, options in ((self.package, self.receipt, self.options),
                                        (android, android_receipt, None)):
            (stage / "outputs/evidence/sdk-compatibility.json").unlink()
            with self.subTest(component=stage.name), \
                    patch("ci.products.sdk_compatibility.produce_sdk_compatibility",
                          side_effect=AssertionError("compatibility producer before structural validation")), \
                    patch("ci.products.sdk_apple_content.verify_sdk_apple_package_content",
                          side_effect=AssertionError("Apple gate before structural validation")), \
                    self.assertRaises(ValueError):
                verify_packaged_sdk_maven_phase(stage, receipt, self.request, apple_verification=options)

    def test_non_ios_package_and_binary_outputs_remain_strict(self):
        stage, receipt = self.copy_phase("package", "sdk-android")
        with self.assertRaisesRegex(ValueError, "exact sdk-ios"):
            verify_packaged_sdk_maven_phase(stage, receipt, self.request, apple_verification=self.options)
        apple = self.binary / "outputs/apple"
        apple.mkdir()
        (apple / "unexpected.zip").write_bytes(b"not a Maven original\n")
        self.rebind(self.binary, self.binary_receipt)
        with self.assertRaisesRegex(ValueError, "binary output kinds"):
            self.verify(True)
        self.assertEqual([], self.calls)

    def test_missing_extra_or_wrong_kind_apple_files_never_pass_receipt_rebinding(self):
        extra = self.package / "outputs/apple/extra.zip"
        extra.write_bytes(b"extra\n")
        self.rebind(self.package, self.receipt)
        with self.assertRaisesRegex(ValueError, "exact original SDK package"):
            self.verify()
        extra.unlink()
        self.rebind(self.package, self.receipt, kind="extra")
        with self.assertRaisesRegex(ValueError, "exact receipt outputs"):
            self.verify(True)
        (self.package / "outputs/apple/CodexAgentPackage-0.2.9.zip").unlink()
        self.rebind(self.package, self.receipt)
        with self.assertRaisesRegex(ValueError, "exact original SDK package"):
            self.verify(True)

    def test_compatibility_crosspair_fails_before_apple_gate_and_uses_exact_capture(self):
        original = self.expectation.read_bytes()
        try:
            self.expectation.write_bytes(b"different caller compatibility\n")
            for predecessor in (False, True):
                with self.subTest(predecessor=predecessor), self.assertRaisesRegex(ValueError, "caller compatibility differs"):
                    self.verify(predecessor)
            self.assertEqual([], self.calls)
        finally:
            self.expectation.write_bytes(original)
        def swap(arguments):
            try:
                self.expectation.write_bytes(b"temporary different expectation\n")
                self.assertEqual(original, arguments["expected_sdk_compatibility"].read_bytes())
            finally:
                self.expectation.write_bytes(original)
        self.mutate = swap
        self.verify()
        self.verify(True)

    def test_gate_failure_and_private_changes_cannot_return_a_receipt(self):
        def fail(arguments):
            raise subprocess.CalledProcessError(1, "authenticated Apple verifier")
        self.mutate = fail
        for predecessor in (False, True):
            with self.subTest(predecessor=predecessor), self.assertRaises(subprocess.CalledProcessError):
                self.verify(predecessor)
        def mutate(arguments):
            arguments["expected_sdk_compatibility"].write_bytes(b"modified authenticated expectation\n")
        self.mutate = mutate
        with self.assertRaisesRegex(ValueError, "Captured Apple compatibility changed"):
            self.verify()

    def test_apple_success_does_not_bypass_existing_maven_checks_or_raw_replay(self):
        checksum = next((self.package / "outputs/maven").rglob("*.sha256"))
        original = checksum.read_bytes()
        try:
            checksum.chmod(0o600)
            checksum.write_bytes(b"0" * 64 + b"\n")
            self.rebind(self.package, self.receipt)
            for predecessor in (False, True):
                with self.subTest(predecessor=predecessor), self.assertRaises(ValueError):
                    self.verify(predecessor)
        finally:
            checksum.write_bytes(original)
            self.rebind(self.package, self.receipt)
        checksum = next((self.binary / "outputs/maven").rglob("*.sha256"))
        checksum.chmod(0o600)
        checksum.write_bytes(b"0" * 64 + b"\n")
        self.rebind(self.binary, self.binary_receipt)
        with self.assertRaises(ValueError):
            self.verify(True)


if __name__ == "__main__":
    unittest.main()
