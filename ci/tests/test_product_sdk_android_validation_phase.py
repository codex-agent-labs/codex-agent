"""Android validation staging orchestration; existing full gates are mocked."""

from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci.products import sdk_android_validation_phase as phase
from ci.products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, regular_file_inventory,
    sha256_bytes, sha256_file,
)
from ci.products.receipt import output_inventory_digest, verify_output_manifest_identity
from ci.tests.product_chain_support import write_receipt


class AndroidValidationPhaseTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="android-validation-phase-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.repository = self.root / "repository"
        self.repository.mkdir()
        self.package_stage = self.root / "package-stage"
        self.binary_stage = self.root / "binary-stage"
        (self.package_stage / "outputs/maven").mkdir(parents=True)
        (self.package_stage / "outputs/maven/package.bin").write_bytes(b"packaged bytes")
        self.version = "0.8.7"
        artifact = "codex-agent-runtime-android"
        self.aar = (self.binary_stage / "outputs/maven/io/github/codex-agent-labs" /
                    artifact / self.version / f"{artifact}-{self.version}.aar")
        self.aar.parent.mkdir(parents=True)
        self.aar.write_bytes(b"exact original Maven AAR bytes\x00")
        (self.binary_stage / "outputs/evidence").mkdir(parents=True)
        (self.binary_stage / "outputs/evidence/maven-primary-inventory.json").write_bytes(b"{}\n")
        self.original_producer = self.producer(1)
        self.capture_producer = self.producer(2)
        package_outputs = [{"kind": "maven", "relativePath": "outputs/maven/package.bin",
                            "bytes": 14, "sha256": sha256_bytes(b"packaged bytes")}]
        binary_outputs = [{"kind": "maven", "relativePath": self.aar.relative_to(self.binary_stage).as_posix(),
                           "bytes": len(self.aar.read_bytes()), "sha256": sha256_file(self.aar)}]
        self.package_receipt = self.root / "package.json"
        self.binary_receipt = self.root / "binary.json"
        self.package = write_receipt(
            self.package_receipt, product="sdk", component="sdk-android", phase="package",
            target="android", version=self.version, version_identity=self.version,
            outputs=package_outputs, upstream=[], context={"producer": self.original_producer})
        self.binary = write_receipt(
            self.binary_receipt, product="sdk", component="sdk-android", phase="binary",
            target="android", version=self.version, version_identity=self.version,
            outputs=binary_outputs, upstream=[], context={"producer": self.original_producer})
        self.compatibility = self.root / "sdk-compatibility-request.json"
        self.compatibility.write_bytes(b"{}\n")
        self.contract_stage = self.root / "contract-stage"
        self.contract_stage.mkdir()
        (self.contract_stage / "contract.bin").write_bytes(b"contract")
        self.contract = self.root / "contract"
        self.contract.mkdir()
        self.contract_files = {}
        for name in ("receipt.json", "attestation.json", "signature.sig", "public.pub"):
            path = self.contract / name
            path.write_bytes((name + "\n").encode())
            self.contract_files[name] = path
        closure = self.contract / phase.CONTRACT_EXECUTION_CLOSURE_DIRECTORY
        closure.mkdir()
        (closure / "original.txt").write_bytes(b"original closure")
        self.contract_evidence = {
            "stageRoot": str(self.contract_stage),
            "phaseReceipt": str(self.contract_files["receipt.json"]),
            "attestation": str(self.contract_files["attestation.json"]),
            "attestationSignature": str(self.contract_files["signature.sig"]),
            "publicKey": str(self.contract_files["public.pub"]),
            "expectedTrustDomain": "development", "keyring": None, "keysDirectory": None,
        }
        self.final = self.root / "final"
        verification = self.final / phase._VERIFICATION_PATH
        verification.parent.mkdir(parents=True)
        raw_aar = sha256_file(self.aar).removeprefix("sha256:")
        self.verification = {
            "schemaVersion": 1, "result": "passed",
            "evidenceSha256": "1" * 64, "firebaseMatrixSha256": "2" * 64,
            "testReportSha256": "3" * 64, "applicationApkSha256": "4" * 64,
            "testApkSha256": "5" * 64, "releaseAarSha256": raw_aar,
            "bundledRuntimeSha256": "6" * 64,
        }
        # Matches ReleaseIo.releaseJson: insertion order, four-space pretty print, trailing LF.
        verification.write_text(json.dumps(self.verification, indent=4) + "\n")
        self.protected = self.root / "protected"
        self.protected.mkdir()
        (self.protected / "observation.xml").write_bytes(b"protected raw evidence")
        self.tooling = self.root / "tooling"
        self.tooling.mkdir()
        (self.tooling / "attestation.json").write_bytes(b"{}\n")
        self.public_key = self.root / "tooling.pub"
        self.java = self.root / "tools/java"
        self.analyzer = self.root / "tools/apkanalyzer"
        self.java.parent.mkdir()
        for path, raw in ((self.public_key, b"public"), (self.java, b"java"),
                          (self.analyzer, b"analyzer")):
            path.write_bytes(raw)
        self.destination = self.root / "stage"
        self.events = []
        self.arguments = dict(
            repository=self.repository, package_stage=self.package_stage,
            package_receipt=self.package_receipt, binary_stage=self.binary_stage,
            binary_receipt=self.binary_receipt, compatibility_request=self.compatibility,
            binary_contract_evidence=self.contract_evidence,
            final_capture=self.final, protected_capture=self.protected,
            expected_capture_producer=self.capture_producer,
            expected_original_producer=self.original_producer,
            trusted_source_commit="c" * 40, trusted_source_tree="d" * 40,
            tooling_evidence=self.tooling, tooling_public_key=self.public_key,
            java_executable=self.java, apkanalyzer_executable=self.analyzer,
            policy_revision="e" * 40, required_trust_domain="development",
            destination=self.destination,
        )

    def producer(self, attempt):
        return {"repository": "codex-agent-labs/codex-agent",
            "workflowPath": ".github/workflows/ci.yml", "commit": "a" * 40,
            "tree": "b" * 40, "event": "pull_request", "runId": 17,
            "runAttempt": attempt, "pullRequest": 3}

    def package_gate(self, repository, stage, receipt, request, **kwargs):
        self.events.append("package")
        self.assertEqual(self.repository, repository)
        self.assertEqual(self.package_stage, stage)
        self.assertEqual(self.package_receipt, receipt)
        self.assertEqual(self.compatibility, request)
        self.assertEqual(self.binary_stage, kwargs["binary_stage_root"])
        self.assertEqual(self.binary_receipt, kwargs["binary_receipt_path"])
        self.assertIs(self.contract_evidence, kwargs["binary_contract_evidence"])
        return deepcopy(self.package), self.package_receipt.read_bytes()

    def validation_gate(self, **kwargs):
        self.events.append("validation")
        aar = Path(kwargs["expected_binary_aar"])
        self.assertEqual("codex-agent-runtime-android-release.aar", aar.name)
        self.assertEqual(self.aar.read_bytes(), aar.read_bytes())
        self.assertNotEqual(self.aar, aar)
        self.assertEqual(self.original_producer, kwargs["expected_original_producer"])
        self.assertEqual(self.capture_producer, kwargs["expected_capture_producer"])

    def call(self, *, package_gate=None, validation_gate=None, **changes):
        request_inventory = lambda path: {Path(path): sha256_file(Path(path))}
        with patch.object(phase, "_request_inventory", side_effect=request_inventory), \
                patch.object(phase, "verify_sdk_package_inputs",
                             side_effect=package_gate or self.package_gate) as package, \
                patch.object(phase, "verify_sdk_android_validation_original_content",
                             side_effect=validation_gate or self.validation_gate) as validation:
            result = phase.produce_sdk_android_validation_phase(**{**self.arguments, **changes})
        return result, package, validation

    def test_full_gate_order_exact_binary_bytes_and_single_content_stage(self):
        self.assertNotEqual(canonical_json_bytes(self.verification),
                            (self.final / phase._VERIFICATION_PATH).read_bytes())
        before = {"package": regular_file_inventory(self.package_stage),
                  "binary": regular_file_inventory(self.binary_stage),
                  "final": regular_file_inventory(self.final),
                  "protected": regular_file_inventory(self.protected)}
        manifest, package, validation = self.call()
        self.assertEqual(["package", "validation"], self.events)
        package.assert_called_once()
        validation.assert_called_once()
        self.assertEqual(manifest, verify_output_manifest_identity(
            self.destination, "sdk", "sdk-android", "validation", "android", self.version))
        self.assertEqual([phase.OUTPUT_KIND], [record["kind"] for record in manifest["outputs"]])
        self.assertEqual([phase.OUTPUT_PATH], [record["relativePath"] for record in manifest["outputs"]])
        content = load_canonical_json_bytes((self.destination / phase.OUTPUT_PATH).read_bytes())
        self.assertEqual(output_inventory_digest(self.package["outputs"]), content["packageOutputsDigest"])
        self.assertEqual(sha256_file(self.aar), content["releaseAarSha256"])
        self.assertEqual("sha256:" + "6" * 64, content["bundledRuntimeSha256"])
        self.assertEqual({"output-manifest.json", phase.OUTPUT_PATH},
                         {row["relativePath"] for row in regular_file_inventory(self.destination)})
        self.assertEqual(before, {"package": regular_file_inventory(self.package_stage),
                                  "binary": regular_file_inventory(self.binary_stage),
                                  "final": regular_file_inventory(self.final),
                                  "protected": regular_file_inventory(self.protected)})

    def test_destination_and_original_producer_fail_before_any_gate_or_write(self):
        self.destination.mkdir()
        with self.assertRaisesRegex(ValueError, "destination"):
            self.call()
        self.destination.rmdir()
        with self.assertRaisesRegex(ValueError, "original producer"):
            self.call(expected_original_producer=self.producer(3))
        with self.assertRaisesRegex(ValueError, "overlap"):
            self.call(destination=self.binary_stage / "nested")
        self.assertEqual([], self.events)
        self.assertFalse((self.binary_stage / "nested").exists())

    def test_gate_failure_and_malformed_or_mismatched_verification_never_publish(self):
        with self.assertRaisesRegex(ValueError, "package failed"):
            self.call(package_gate=lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("package failed")))
        self.assertFalse(self.destination.exists())
        with self.assertRaisesRegex(ValueError, "Firebase failed"):
            self.call(validation_gate=lambda **kwargs: (_ for _ in ()).throw(ValueError("Firebase failed")))
        self.assertFalse(self.destination.exists())
        record = self.final / phase._VERIFICATION_PATH
        original = record.read_bytes()
        for name, value in (
            ("quoted-schema", {**self.verification, "schemaVersion": "1"}),
            ("extra", {**self.verification, "producer": {}}),
            ("wrong-aar", {**self.verification, "releaseAarSha256": "f" * 64}),
            ("prefixed-runtime", {**self.verification, "bundledRuntimeSha256": "sha256:" + "6" * 64}),
        ):
            record.write_bytes(canonical_json_bytes(value))
            try:
                with self.subTest(name=name), self.assertRaises(ValueError):
                    self.call()
                self.assertFalse(self.destination.exists())
            finally:
                record.write_bytes(original)
        record.write_bytes(original.replace(
            b'    "schemaVersion": 1,',
            b'    "schemaVersion": 1,\n    "schemaVersion": 1,', 1))
        try:
            with self.assertRaisesRegex(ValueError, "duplicate key"):
                self.call()
            self.assertFalse(self.destination.exists())
        finally:
            record.write_bytes(original)

    def test_late_original_tool_policy_and_binary_mutations_reject_before_publication(self):
        cases = {
            "binary": self.aar,
            "protected": self.protected / "observation.xml",
            "tool": self.java,
            "contract": self.contract_files["attestation.json"],
            "request": self.compatibility,
        }
        for name, path in cases.items():
            raw = path.read_bytes()
            def mutate(**kwargs):
                self.validation_gate(**kwargs)
                path.write_bytes(raw + b"late")
            try:
                with self.subTest(name=name), self.assertRaisesRegex(ValueError, "changed"):
                    self.call(validation_gate=mutate)
                self.assertFalse(self.destination.exists())
            finally:
                path.write_bytes(raw)
                self.events.clear()
        original = deepcopy(self.capture_producer)
        def mutate_policy(**kwargs):
            self.validation_gate(**kwargs)
            self.capture_producer["runAttempt"] = 9
        try:
            with self.assertRaisesRegex(ValueError, "policy changed"):
                self.call(validation_gate=mutate_policy)
            self.assertFalse(self.destination.exists())
        finally:
            self.capture_producer.clear()
            self.capture_producer.update(original)

    def test_signing_secret_is_rejected_before_gates(self):
        with patch.dict(os.environ, {"CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY": ""}), \
                self.assertRaises(ValueError):
            self.call()
        self.assertEqual([], self.events)
        self.assertFalse(self.destination.exists())


if __name__ == "__main__":
    unittest.main()
