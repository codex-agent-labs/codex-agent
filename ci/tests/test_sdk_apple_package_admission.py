"""Selected-package binding fixtures; original semantic gate is deliberately mocked."""

from contextlib import contextmanager
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci.products.inventory import canonical_json_bytes, sha256_bytes
from ci.products.receipt import write_output_manifest
from ci.products.sdk_apple_package_admission import ApplePackageAdmission, verified_selected_ios_package
from ci.tests.product_chain_support import write_receipt


class ApplePackageAdmissionTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="apple-package-admission-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.stage = self.root / "stage"
        (self.stage / "outputs/apple").mkdir(parents=True)
        self.artifact = self.stage / "outputs/apple/package.zip"
        self.artifact.write_bytes(b"original package bytes")
        manifest = write_output_manifest(self.stage, "sdk", "sdk-ios", "package", "ios", "0.8.0",
                                         {"apple": "outputs/apple"})
        self.receipt_path = self.root / "receipt.json"
        self.receipt = write_receipt(self.receipt_path, product="sdk", component="sdk-ios",
            phase="package", target="ios", version="0.8.0", version_identity="0.8.0",
            outputs=manifest["outputs"], upstream=[], context={"producer": {
                "repository": "owner/repository", "workflowPath": ".github/workflows/product-validation.yml",
                "commit": "a" * 40, "tree": "b" * 40, "event": "pull_request",
                "runId": 3, "runAttempt": 1, "pullRequest": 31,
            }})
        self.raw = self.receipt_path.read_bytes()
        self.options = dict(plan=self.root / "plan.json", package_capture=self.root / "package-capture",
            sdk_capture=self.root / "sdk-capture", keyring=self.root / "keyring.json",
            keys_directory=self.root / "keys", repository_root=self.root,
            tooling_evidence=self.root / "tooling.json", tooling_public_key=self.root / "tooling.pub",
            java_executable=self.root / "java", policy_revision="c" * 40,
            required_trust_domain="release")
        self.events = []
        self.original_stage = self.stage
        self.original_receipt = self.receipt
        self.original_raw = self.raw
        self.on_exit = lambda: None

    @contextmanager
    def original_gate(self, plan, receipt, **arguments):
        self.assertEqual(self.options["plan"], plan)
        self.assertEqual(self.receipt_path, receipt)
        self.assertEqual({**{name: value for name, value in self.options.items() if name != "plan"},
                          "tooling_keyring": None, "tooling_keys_directory": None}, arguments)
        self.events.append("original-enter")
        try:
            yield {"stage": self.original_stage, "receipt": self.original_receipt,
                   "receiptBytes": self.original_raw}
        finally:
            self.on_exit()
            self.events.append("original-exit")

    def admit(self):
        return verified_selected_ios_package(self.stage, self.receipt_path, **self.options)

    def reuse_admission(self):
        for path in (self.options["plan"], self.options["keyring"], self.options["tooling_evidence"],
                     self.options["tooling_public_key"], self.options["java_executable"]):
            path.touch()
        for path in (self.options["package_capture"], self.options["sdk_capture"],
                     self.options["keys_directory"]):
            path.mkdir(exist_ok=True)
        return ApplePackageAdmission([{
            "receiptSha256": sha256_bytes(self.raw), "selectedStage": str(self.stage),
            "selectedReceipt": str(self.receipt_path), "plan": str(self.options["plan"]),
            "packageCapture": str(self.options["package_capture"]),
            "sdkCapture": str(self.options["sdk_capture"]),
        }], repository_root=self.root, keyring=self.options["keyring"],
            keys_directory=self.options["keys_directory"],
            tooling_evidence=self.options["tooling_evidence"],
            tooling_public_key=self.options["tooling_public_key"],
            java_executable=self.options["java_executable"], policy_revision="c" * 40,
            required_trust_domain="release")

    def reuse_envelope(self):
        return {"receipt": self.receipt, "receiptBytes": self.raw,
                "receiptSha256": sha256_bytes(self.raw), "objectSha256": "sha256:" + "1" * 64}

    def test_exact_selected_bytes_are_held_through_original_gate_exit(self):
        with patch("ci.sdk_ios_original_package.verified_retained_ios_package", self.original_gate):
            with self.admit() as original:
                self.assertEqual(self.raw, original["receiptBytes"])
                self.events.append("consumer")
        self.assertEqual(["original-enter", "consumer", "original-exit"], self.events)

    def test_selected_stage_manifest_must_match_receipt_before_original_gate(self):
        self.artifact.write_bytes(b"changed")
        with patch("ci.sdk_ios_original_package.verified_retained_ios_package", self.original_gate):
            with self.assertRaisesRegex(ValueError, "inventory|differs"):
                with self.admit():
                    self.fail("changed stage admitted")
        self.assertEqual([], self.events)

    def test_replayed_original_must_be_exact_selected_stage(self):
        other = self.root / "other"
        (other / "outputs/apple").mkdir(parents=True)
        (other / "outputs/apple/package.zip").write_bytes(b"different original package")
        self.original_stage = other
        with patch("ci.sdk_ios_original_package.verified_retained_ios_package", self.original_gate):
            with self.assertRaisesRegex(ValueError, "exact selected package"):
                with self.admit():
                    self.fail("different original admitted")
        self.assertEqual(["original-enter", "original-exit"], self.events)

    def test_original_receipt_must_match_selected_receipt(self):
        self.original_raw = b"different original receipt"
        with patch("ci.sdk_ios_original_package.verified_retained_ios_package", self.original_gate):
            with self.assertRaisesRegex(ValueError, "exact selected package"):
                with self.admit():
                    self.fail("different original admitted")

    def test_original_semantic_gate_failure_cannot_become_admission(self):
        @contextmanager
        def rejected(*_args, **_kwargs):
            raise ValueError("original Apple package semantic replay failed")
            yield  # pragma: no cover

        with patch("ci.sdk_ios_original_package.verified_retained_ios_package", rejected):
            with self.assertRaisesRegex(ValueError, "semantic replay failed"):
                with self.admit():
                    self.fail("failed original replay admitted")

    def test_selected_stage_mutation_during_consumer_fails(self):
        with patch("ci.sdk_ios_original_package.verified_retained_ios_package", self.original_gate):
            with self.assertRaisesRegex(ValueError, "changed during original replay"):
                with self.admit():
                    self.artifact.write_bytes(b"mutated during consumer")
        self.assertIn("original-exit", self.events)

    def test_selected_receipt_mutation_on_gate_exit_fails(self):
        self.on_exit = lambda: self.receipt_path.write_bytes(canonical_json_bytes({"mutated": True}))
        with patch("ci.sdk_ios_original_package.verified_retained_ios_package", self.original_gate):
            with self.assertRaisesRegex(ValueError, "changed during original replay"):
                with self.admit():
                    pass
        self.assertIn("original-exit", self.events)

    def test_reuse_requires_original_shard_object_as_well_as_full_replay(self):
        admission = self.reuse_admission()
        envelope = self.reuse_envelope()
        original = self.root / "original"
        original.mkdir()

        @contextmanager
        def complete(*_args, **_kwargs):
            self.events.append("replay")
            yield {"original": original}

        selected = {"receiptBytes": self.raw, "receiptSha256": sha256_bytes(self.raw),
                    "objectSha256": envelope["objectSha256"]}
        with patch("ci.products.sdk_apple_package_admission.verified_selected_ios_package", complete), \
                patch("ci.products.sdk_apple_package_admission.verify_phase_shard", return_value=selected):
            admission.verify(envelope)
        self.assertEqual(["replay"], self.events)

        with patch("ci.products.sdk_apple_package_admission.verified_selected_ios_package", complete), \
                patch("ci.products.sdk_apple_package_admission.verify_phase_shard",
                      return_value={**selected, "objectSha256": "sha256:" + "2" * 64}), \
                self.assertRaisesRegex(ValueError, "shard differs"):
            admission.verify(envelope)

    def test_reuse_never_admits_missing_evidence_or_failed_full_gate(self):
        admission = self.reuse_admission()
        envelope = self.reuse_envelope()
        admission._records.clear()
        with patch("ci.products.sdk_apple_package_admission.verified_selected_ios_package") as gate, \
                self.assertRaisesRegex(ValueError, "lacks authenticated original evidence"):
            admission.verify(envelope)
        gate.assert_not_called()

        admission = self.reuse_admission()

        @contextmanager
        def rejected(*_args, **_kwargs):
            raise ValueError("full original package replay failed")
            yield  # pragma: no cover

        with patch("ci.products.sdk_apple_package_admission.verified_selected_ios_package", rejected), \
                self.assertRaisesRegex(ValueError, "full original package replay failed"):
            admission.verify(envelope)


if __name__ == "__main__":
    unittest.main()
