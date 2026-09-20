"""Signed-plan/Maven forwarding checks; the separately tested Apple Java gate is mocked."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from ci.products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, regular_file_inventory,
    snapshot_regular_tree,
)
from ci.products.receipt import write_output_manifest
from ci.products.sdk_maven import MAVEN_GROUPS, package_sdk_maven
from ci.products.sdk_package import verify_sdk_package_inputs
from ci.tests import test_product_sdk_maven as maven_fixture
from ci.tests import test_product_sdk_package as plan_fixture
from ci.tests.product_chain_support import write_receipt


_DEFAULT = object()


@unittest.skipUnless(shutil.which("ssh-keygen"), "OpenSSH signing tool unavailable")
class SdkPackageAppleInputsTest(unittest.TestCase):
    @classmethod
    def bind(cls, path, upstream, evidence):
        return plan_fixture.SdkPackagePlanTest.bind.__func__(cls, path, upstream, evidence)

    @classmethod
    def setUpClass(cls):
        plan_fixture.SdkPackagePlanTest.setUpClass.__func__(cls)
        component, version = "sdk-ios", "0.2.9"
        cls.ios_binary = cls.root / "apple-forwarding/binary"
        snapshot_regular_tree(
            maven_fixture._repository(cls.root / "apple-forwarding", component, version),
            cls.ios_binary / "outputs/maven",
        )
        maven_fixture._write_binary_inventory(cls.ios_binary, component, version)
        maven_fixture._write_apple_binary(cls.ios_binary)
        cls.ios_package = cls.root / "apple-forwarding/package"
        compatibility = cls.ios_package / "outputs/evidence/sdk-compatibility.json"
        compatibility.parent.mkdir(parents=True)
        compatibility.write_bytes(cls.chain["compatibility"].read_bytes())
        package_sdk_maven(
            cls.ios_binary / "outputs/maven", cls.ios_package / "outputs/maven",
            compatibility, MAVEN_GROUPS[component], version, component,
        )
        apple = cls.ios_package / "outputs/apple"
        apple.mkdir()
        for name in (
            f"CodexAgentPackage-{version}.zip",
            f"CodexAgent-{version}.xcframework.zip",
            f"CodexAgent-{version}.xcframework.zip.sha256",
        ):
            (apple / name).write_bytes(f"synthetic caller-authenticated {name}\n".encode())
        for phase, stage in (("binary", cls.ios_binary), ("package", cls.ios_package)):
            roots = {"maven": "outputs/maven", "evidence": "outputs/evidence"}
            if phase == "package":
                roots["apple"] = "outputs/apple"
            else:
                roots["apple-binary"] = "outputs/apple-binary"
            outputs = write_output_manifest(
                stage, "sdk", component, phase, "ios", version, roots,
            )["outputs"]
            receipt = cls.root / f"apple-forwarding/{phase}-receipt.json"
            write_receipt(
                receipt, product="sdk", component=component, phase=phase, target="ios",
                version=version, version_identity=version, outputs=outputs, upstream=[],
                context={"producer": cls.producer},
            )
            if phase == "binary":
                original_contract = load_canonical_json_bytes(cls.older["contract"]["receipt"].read_bytes())
                cls.ios_binary_receipt = receipt
                cls.bind(receipt, {plan_fixture.identity(original_contract): original_contract}, cls.older_evidence)
            else:
                binary = load_canonical_json_bytes(cls.ios_binary_receipt.read_bytes())
                cls.ios_receipt = receipt
                cls.bind(receipt, {**cls.upstream, plan_fixture.identity(binary): binary}, cls.evidence)

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sdk-package-apple-inputs-")
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name).resolve()
        self.expectation = self.work / "sdk-compatibility.json"
        self.expectation.write_bytes(self.chain["compatibility"].read_bytes())
        self.options = {
            "validation_evidence_directory": self.work / "validation-evidence",
            "expected_sdk_compatibility": self.expectation,
            "expected_distribution_proof": self.work / "verified-distribution-proof.json",
            "repository": self.repository,
            "tooling_evidence": self.work / "tooling",
            "tooling_public_key": self.work / "tooling.pub",
            "java_executable": self.work / "java",
            "policy_revision": "a" * 40,
            "required_trust_domain": "development",
            "tooling_keyring": None,
            "tooling_keys_directory": None,
        }
        self.calls = []

    def apple_gate(self, **arguments):
        self.calls.append(arguments)
        self.assertEqual("0.2.9", arguments["sdk_version"])
        self.assertNotEqual(self.ios_package / "outputs/apple", arguments["product_directory"])
        self.assertEqual(
            self.chain["compatibility"].read_bytes(),
            arguments["expected_sdk_compatibility"].read_bytes(),
        )
        expected = {key: value for key, value in self.options.items()
                    if key != "expected_sdk_compatibility"}
        actual = {key: value for key, value in arguments.items()
                  if key not in {"product_directory", "sdk_version", "expected_sdk_compatibility"}}
        self.assertEqual(expected, actual)
        return regular_file_inventory(arguments["product_directory"])

    def verify(self, options=_DEFAULT):
        return verify_sdk_package_inputs(
            self.repository, self.ios_package, self.ios_receipt, self.request,
            binary_stage_root=self.ios_binary, binary_receipt_path=self.ios_binary_receipt,
            binary_contract_evidence=self.older_evidence,
            apple_verification=self.options if options is _DEFAULT else options,
        )

    def binary_policy(self):
        return {**{key: value for key, value in self.options.items() if key not in {
            "validation_evidence_directory", "expected_distribution_proof", "expected_sdk_compatibility",
        }}, "developer_directory": self.work / "Developer"}

    def verify_binary(self, **changes):
        return verify_sdk_package_inputs(
            self.repository, self.ios_package, self.ios_receipt, self.request,
            binary_stage_root=self.ios_binary, binary_receipt_path=self.ios_binary_receipt,
            binary_contract_evidence=self.older_evidence,
            **{"apple_binary_verification": self.binary_policy(), **changes},
        )

    def test_binary_replay_binds_original_receipts_source_and_compatibility_once(self):
        from ci.products.sdk_maven import verify_packaged_sdk_maven_phase
        before = regular_file_inventory(self.root / "apple-forwarding")
        binary_bytes = self.ios_binary_receipt.read_bytes()
        capture = self.root / "external-package-capture"
        def verify_captured(*args, **kwargs):
            self.assertNotEqual(self.ios_binary_receipt, kwargs["binary_receipt_path"])
            self.assertEqual(binary_bytes, kwargs["binary_receipt_path"].read_bytes())
            self.ios_binary_receipt.write_bytes(b"transient replacement\n")
            try:
                return verify_packaged_sdk_maven_phase(*args, **kwargs)
            finally:
                self.ios_binary_receipt.write_bytes(binary_bytes)
        def gate(**arguments):
            self.calls.append(arguments)
            self.assertEqual(capture, arguments["execution_capture_directory"])
            self.assertEqual(load_canonical_json_bytes(self.ios_receipt.read_bytes())["producer"]["commit"],
                             arguments["source_revision"])
            self.assertNotEqual(self.ios_binary / "outputs/apple-binary", arguments["binary_frameworks"])
            self.assertEqual(regular_file_inventory(self.ios_binary / "outputs/apple-binary"),
                             regular_file_inventory(arguments["binary_frameworks"]))
            self.assertEqual(self.chain["compatibility"].read_bytes(), arguments["expected_sdk_compatibility"].read_bytes())
            self.assertEqual(self.binary_policy(), {key: arguments[key] for key in self.binary_policy()})
            return regular_file_inventory(arguments["product_directory"])
        with patch("ci.products.sdk_apple_content.verify_sdk_apple_binary_package_content", side_effect=gate), \
                patch("ci.products.sdk_maven.verify_packaged_sdk_maven_phase", side_effect=verify_captured):
            value, raw = self.verify_binary(apple_execution_capture_directory=capture)
        self.assertEqual(self.ios_receipt.read_bytes(), raw)
        self.assertEqual(load_canonical_json_bytes(raw), value)
        self.assertEqual(1, len(self.calls))
        self.assertEqual(before, regular_file_inventory(self.root / "apple-forwarding"))

    def test_binary_replay_rejects_policy_crosspair_and_source_plan_before_tools(self):
        with patch("ci.products.sdk_apple_content.verify_sdk_apple_binary_package_content",
                   side_effect=AssertionError("unverified native replay")):
            for options in ({}, {**self.binary_policy(), "source_revision": "f" * 40},
                            {**self.binary_policy(), "binary_frameworks": self.work},
                            {**self.binary_policy(), "repository": self.work},
                            {**self.binary_policy(), "required_trust_domain": "release"}):
                with self.subTest(options=options), self.assertRaises(ValueError):
                    self.verify_binary(apple_binary_verification=options)
            with self.assertRaisesRegex(ValueError, "mutually exclusive"):
                self.verify_binary(apple_verification=self.options)
            original = self.ios_receipt.read_bytes()
            changed = load_canonical_json_bytes(original)
            changed["producer"]["tree"] = "f" * 40
            self.ios_receipt.write_bytes(canonical_json_bytes(changed))
            try:
                with self.assertRaisesRegex(ValueError, "commit|authenticated plan"):
                    self.verify_binary()
            finally:
                self.ios_receipt.write_bytes(original)

    def test_signed_plan_forwards_the_same_apple_authority_through_both_real_maven_gates(self):
        before = regular_file_inventory(self.root / "apple-forwarding")
        original = self.ios_receipt.read_bytes()
        with patch(
            "ci.products.sdk_apple_content.verify_sdk_apple_package_content",
            side_effect=self.apple_gate,
        ):
            value, raw = self.verify()
        self.assertEqual(load_canonical_json_bytes(original), value)
        self.assertEqual(original, raw)
        self.assertEqual(2, len(self.calls))
        self.assertEqual(before, regular_file_inventory(self.root / "apple-forwarding"))

    def test_missing_crossfamily_or_changed_authority_never_reaches_the_apple_gate(self):
        incomplete = {key: value for key, value in self.options.items()
                      if key != "expected_distribution_proof"}
        cases = (
            None, {}, incomplete,
            {**self.options, "repository": self.work},
            {**self.options, "required_trust_domain": "release"},
        )
        with patch(
            "ci.products.sdk_apple_content.verify_sdk_apple_package_content",
            side_effect=AssertionError("Apple gate received rejected caller authority"),
        ):
            for options in cases:
                with self.subTest(options=options), self.assertRaises(ValueError):
                    self.verify(options)
            with self.assertRaisesRegex(ValueError, "exact iOS identity"):
                verify_sdk_package_inputs(
                    self.repository, self.maven_stage, self.maven_receipt, self.request,
                    binary_stage_root=self.binary_stage, binary_receipt_path=self.binary_receipt,
                    binary_contract_evidence=self.older_evidence, apple_verification=self.options,
                )

    def test_apple_gate_failure_and_original_plan_change_cannot_return_a_receipt(self):
        with patch(
            "ci.products.sdk_apple_content.verify_sdk_apple_package_content",
            side_effect=subprocess.CalledProcessError(1, "authenticated Apple verifier"),
        ), self.assertRaises(subprocess.CalledProcessError):
            self.verify()

        original = self.ios_receipt.read_bytes()
        changed = load_canonical_json_bytes(original)
        changed["producer"]["tree"] = "f" * 40
        self.ios_receipt.write_bytes(canonical_json_bytes(changed))
        try:
            with patch(
                "ci.products.sdk_apple_content.verify_sdk_apple_package_content",
                side_effect=self.apple_gate,
            ), self.assertRaisesRegex(ValueError, "commit|authenticated plan"):
                self.verify()
            self.assertEqual(2, len(self.calls))
        finally:
            self.ios_receipt.write_bytes(original)


if __name__ == "__main__":
    unittest.main()
