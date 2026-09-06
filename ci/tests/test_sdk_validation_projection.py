"""Proof orchestration negatives; mocked tooling is never full matcher/host evidence."""

from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from ci.products.inventory import canonical_json_bytes, load_canonical_json_bytes, regular_file_inventory, sha256_bytes
from ci.products.receipt import output_inventory_digest, write_output_manifest
from ci.products.sdk_validation import VerifiedSdkValidationProjection, verify_sdk_validation_projection
from ci.products.registry import PHASE_INSTANCE_IDS
from ci.products.selection import classify_paths, phase_inventory_paths
from ci.tests.product_chain_support import write_receipt


class SdkValidationProjectionTest(unittest.TestCase):
    def test_admission_control_replans_without_changing_payload_keys(self):
        path = "ci/products/sdk_validation.py"
        self.assertEqual(set(PHASE_INSTANCE_IDS), set(classify_paths((path,)).instances))
        for instance in PHASE_INSTANCE_IDS:
            self.assertEqual((), phase_inventory_paths((path,), instance))

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sdk-proof-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.java = self.root / "jdk/bin/java"
        self.java.parent.mkdir(parents=True)
        self.java.write_bytes(b"synthetic trusted Java, never executed")
        self.context = {"producer": {"repository": "fixture/repository", "workflowPath": None,
            "commit": "a" * 40, "tree": "b" * 40, "event": "local", "runId": None,
            "runAttempt": None, "pullRequest": None}}
        self.args = dict(repository=self.root, component="python", target="linux-x64",
            compatibility_request=self.root / "request.json", runtime_stages=self.root / "runtime",
            staged_sdks=self.root / "sdks", tooling_evidence=self.root / "tooling",
            tooling_public_key=self.root / "public.pub", java_executable=self.java,
            policy_revision="a" * 40, required_trust_domain="development")
        for phase, target in (("package", "desktop"), ("validation", "linux-x64")):
            stage = self.root / phase
            (stage / "outputs").mkdir(parents=True)
            (stage / "outputs/original.txt").write_bytes(f"original {phase} evidence\n".encode())
            manifest = write_output_manifest(stage, "sdk", "python", phase, target, "0.2.0", {"evidence": "outputs"})
            receipt = self.root / f"{phase}.json"
            write_receipt(receipt, product="sdk", component="python", phase=phase, target=target,
                          version="0.2.0", version_identity="0.2.0", upstream=[], context=self.context,
                          outputs=manifest["outputs"])
            self.args[f"{phase}_stage"], self.args[f"{phase}_receipt"] = stage, receipt
        self.package = load_canonical_json_bytes(self.args["package_receipt"].read_bytes())
        self.value = {"schemaVersion": 2, "kind": "sdk-native-validation-content", "component": "python",
            "target": "linux-x64", "sdkVersion": "0.2.0", "packageOutputsDigest": output_inventory_digest(self.package["outputs"]),
            **{key: "sha256:" + "c" * 64 for key in ("contractDigest", "canonicalApiDigest", "canonicalCoverageDigest")},
            "files": [], "packageNegativeCases": []}
        self.mutate = lambda fields: None
        self.calls = []

    @contextmanager
    def capture(self, evidence, repository, key, **policy):
        self.assertEqual(self.args["policy_revision"], policy["policy_revision"])
        self.assertEqual("development", policy["required_trust_domain"])
        yield self.root / "synthetic-private.jar"

    def execute(self, command, **kwargs):
        self.calls.append(command)
        self.assertEqual([str(self.java), "-jar", str(self.root / "synthetic-private.jar"),
                          "write-native-wrapper-validation-content"], command[:4])
        fields = {key: Path(value) for key, value in zip(command[4::2], command[5::2])}
        for phase in ("package", "validation"):
            self.assertNotEqual(fields[f"--{phase}-stage"], self.args[f"{phase}_stage"])
            self.assertNotEqual(fields[f"--{phase}-receipt"], self.args[f"{phase}_receipt"])
            self.assertEqual(fields[f"--{phase}-receipt"].read_bytes(), self.args[f"{phase}_receipt"].read_bytes())
        self.assertNotIn("JAVA_TOOL_OPTIONS", kwargs["env"])
        self.mutate(fields)
        fields["--content-output"].write_bytes(canonical_json_bytes(self.value))
        return subprocess.CompletedProcess(command, 0)

    def verify(self, **overrides):
        with patch("ci.products.tooling.verified_tooling_capture", self.capture), \
                patch("ci.products.sdk_validation.subprocess.run", side_effect=self.execute):
            return verify_sdk_validation_projection(**{**self.args, **overrides})

    def test_proof_binds_exact_original_receipt_inventory_and_all_six_identity_fields(self):
        before = regular_file_inventory(self.root)
        proof = self.verify()
        original = self.args["validation_receipt"].read_bytes()
        receipt = load_canonical_json_bytes(original)
        expected = proof.receipt_value(receipt, self.package)
        self.assertEqual(expected["receiptSha256"], sha256_bytes(original))
        self.assertEqual(expected["sha256"], sha256_bytes(canonical_json_bytes(self.value)))
        self.assertEqual(before, regular_file_inventory(self.root))
        with self.assertRaises(TypeError):
            VerifiedSdkValidationProjection(original, canonical_json_bytes(self.value), object())
        for field in ("product", "component", "phase", "target", "productVersion", "buildKey"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                proof.output_inventory(sha256_bytes(original), receipt["outputs"], identity={**receipt, field: "different"})
        with self.assertRaises(ValueError):
            proof.output_inventory(sha256_bytes(original), [], identity=receipt)
        with self.assertRaises(ValueError):
            proof.output_inventory("sha256:" + "0" * 64, receipt["outputs"], identity=receipt)
        for field in ("product", "component", "phase", "target", "productVersion", "outputs"):
            wrong = {**self.package, field: [] if field == "outputs" else "different"}
            with self.subTest(package_field=field), self.assertRaises(ValueError):
                proof.receipt_value(receipt, wrong)

    def test_different_original_producer_receipts_keep_equal_comparison_content(self):
        first = self.verify()
        original = self.args["validation_receipt"].read_bytes()
        receipt = load_canonical_json_bytes(original)
        changed = deepcopy(receipt)
        changed["producer"]["commit"] = "d" * 40
        changed["producer"]["tree"] = "e" * 40
        self.args["validation_receipt"].write_bytes(canonical_json_bytes(changed))
        second = self.verify()
        left = first.receipt_value(receipt, self.package)
        right = second.receipt_value(changed, self.package)
        self.assertEqual(left["sha256"], right["sha256"])
        self.assertNotEqual(left["receiptSha256"], right["receiptSha256"])
        with self.assertRaises(ValueError):
            second.receipt_value(receipt, self.package)
        # Preserve both originals: comparison does not mutate or relabel either proof.
        self.assertEqual(left, first.receipt_value(receipt, self.package))

    def test_wrong_full_gate_content_identity_never_mints_proof(self):
        original = dict(self.value)
        for field, value in (("schemaVersion", True), ("schemaVersion", 1), ("component", "rust"),
                             ("target", "macos-arm64"), ("sdkVersion", "0.2.1"),
                             ("packageOutputsDigest", "sha256:" + "d" * 64), ("producer", "unexpected")):
            self.value = {**original, field: value}
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.verify()

    def test_full_gate_failure_or_mutated_private_input_never_mints_proof(self):
        for phase in ("package", "validation"):
            for suffix in ("stage", "receipt"):
                def mutate(fields):
                    path = fields[f"--{phase}-{suffix}"]
                    if suffix == "stage":
                        path = path / "outputs/original.txt"
                    path.write_bytes(path.read_bytes() + b"changed during full gate\n")
                self.mutate = mutate
                with self.subTest(phase=phase, suffix=suffix), self.assertRaises(ValueError):
                    self.verify()
        def failure(fields):
            raise subprocess.CalledProcessError(1, "fixed verifier", b"actual failure")
        self.mutate = failure
        with self.assertRaises(subprocess.CalledProcessError):
            self.verify()

    def test_original_swap_and_restore_cannot_change_captured_proof(self):
        def swap(fields):
            path = self.args["validation_receipt"]
            original = path.read_bytes()
            try:
                path.write_bytes(b"temporary untrusted original replacement")
                self.assertEqual(original, fields["--validation-receipt"].read_bytes())
            finally:
                path.write_bytes(original)
        self.mutate = swap
        self.verify()
        self.assertEqual(1, len(self.calls))


if __name__ == "__main__":
    unittest.main()
