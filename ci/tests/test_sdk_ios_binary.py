"""Pure iOS SDK binary property tests; inputs are synthetic caller-admitted data."""

import json
from pathlib import Path
import sys
import tempfile
import unittest


CI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CI_ROOT))

import sdk_ios_binary  # noqa: E402
from products.receipt import write_output_manifest  # noqa: E402
from ci.tests.product_chain_support import write_receipt


class SdkIosBinaryPropertiesTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="sdk-ios-binary-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.stage = self.root / "contract-metadata"
        self.handoff = self.root / "contract-handoff"
        self.native = self.root / "native-evidence"
        for directory in (self.stage, self.handoff, self.native):
            directory.mkdir()
        self.version = "0.8.0"
        self.payload_bytes = b"synthetic authenticated Contract bundle\x00\xff"
        payload = self.stage / f"outputs/codex-agent-contract-{self.version}.zip"
        payload.parent.mkdir()
        payload.write_bytes(self.payload_bytes)
        manifest = write_output_manifest(
            self.stage, "contract", "contract", "metadata", "common", self.version,
            {"contract-bundle": payload.relative_to(self.stage).as_posix()},
        )
        self.receipt_path = self.root / "contract-metadata-receipt.json"
        self.producer = {
            "repository": "owner/repository", "workflowPath": None,
            "commit": "b" * 40, "tree": "c" * 40, "event": "local",
            "runId": None, "runAttempt": None, "pullRequest": None,
        }
        self.receipt = write_receipt(
            self.receipt_path, product="contract", component="contract",
            phase="metadata", target="common", outputs=manifest["outputs"], upstream=[],
            context={"producer": self.producer}, version=self.version,
            version_identity=self.version,
        )
        stem = f"codex-agent-contract-{self.version}"
        (self.handoff / f"{stem}.zip").write_bytes(self.payload_bytes)
        (self.handoff / f"{stem}.attestation.json").write_bytes(b"attestation\n")
        (self.handoff / f"{stem}.attestation.sig").write_bytes(b"signature\x00")
        (self.handoff / "public-key.pub").write_bytes(b"public key\n")
        (self.native / "native-tests-proof.json").write_bytes(b"native proof\n")
        self.record = {
            "stage": self.stage, "receiptPath": self.receipt_path, "receipt": self.receipt,
        }
        self.plan = {
            "schemaVersion": 1, "product": "sdk", "component": "sdk-ios",
            "phase": "binary", "target": "ios",
            "buildKey": "sha256:" + "a" * 64, "inputs": {},
        }

    def invoke(self, **changes):
        arguments = {
            "producer": self.producer, "contract_metadata": self.record,
            "verified_contract_handoff": self.handoff, "native_evidence": self.native,
        }
        arguments.update(changes)
        return sdk_ios_binary.properties(self.plan, **arguments)

    def test_exact_existing_settings_and_phase_properties(self) -> None:
        actual = self.invoke()
        stem = f"codex-agent-contract-{self.version}"
        self.assertEqual({
            "codexAgent.product": "sdk",
            "codexAgent.component": "sdk-ios",
            "codexAgent.phase": "binary",
            "codexAgent.target": "ios",
            "codexAgent.candidateCommit": self.producer["commit"],
            "codexAgent.candidateTree": self.producer["tree"],
            "codexAgent.contractPayload": str(self.handoff / f"{stem}.zip"),
            "codexAgent.contractMetadataReceipt": str(self.receipt_path),
            "codexAgent.contractAttestation": str(self.handoff / f"{stem}.attestation.json"),
            "codexAgent.contractAttestationSignature": str(self.handoff / f"{stem}.attestation.sig"),
            "codexAgent.contractPublicKey": str(self.handoff / "public-key.pub"),
            "codexAgent.contractVersion": self.version,
            "codexAgent.iosNativeEvidenceDirectory": str(self.native),
        }, actual)

    def test_plan_and_candidate_identity_are_exact(self) -> None:
        for change in ({"component": "sdk-core"}, {"phase": "package"}, {"target": "desktop"}):
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, "identity"):
                sdk_ios_binary.properties(
                    {**self.plan, **change}, producer=self.producer,
                    contract_metadata=self.record, verified_contract_handoff=self.handoff,
                    native_evidence=self.native,
                )
        with self.assertRaisesRegex(ValueError, "fields are invalid"):
            sdk_ios_binary.properties(
                {**self.plan, "unexpected": True}, producer=self.producer,
                contract_metadata=self.record, verified_contract_handoff=self.handoff,
                native_evidence=self.native,
            )
        with self.assertRaises(ValueError):
            self.invoke(producer={**self.producer, "commit": "not-a-git-id"})

    def test_metadata_receipt_manifest_version_and_payload_are_bound(self) -> None:
        raw = self.receipt_path.read_bytes()
        wrong_record = {**self.record, "receipt": {**self.receipt, "phase": "validation"}}
        with self.assertRaisesRegex(ValueError, "authenticated receipt"):
            self.invoke(contract_metadata=wrong_record)
        self.assertEqual(raw, self.receipt_path.read_bytes())

        payload = self.handoff / f"codex-agent-contract-{self.version}.zip"
        payload.write_bytes(b"different verified payload")
        with self.assertRaisesRegex(ValueError, "differs from the authenticated metadata bundle"):
            self.invoke()

    def test_missing_empty_unsafe_and_overlapping_inputs_reject(self) -> None:
        proof = self.native / "native-tests-proof.json"
        proof.write_bytes(b"")
        with self.assertRaisesRegex(ValueError, "empty file"):
            self.invoke()
        proof.write_bytes(b"native proof\n")

        signature = self.handoff / f"codex-agent-contract-{self.version}.attestation.sig"
        signature.write_bytes(b"")
        with self.assertRaisesRegex(ValueError, "must be nonempty"):
            self.invoke()
        signature.write_bytes(b"signature\x00")

        with self.assertRaisesRegex(ValueError, "must not overlap"):
            self.invoke(native_evidence=self.handoff)

        relative = Path("relative/native")
        with self.assertRaisesRegex(ValueError, "absolute normalized"):
            self.invoke(native_evidence=relative)

    def test_raw_receipt_mutation_rejects_without_changing_inputs(self) -> None:
        before = self.receipt_path.read_bytes()
        value = json.loads(before)
        value["productVersion"] = "0.8.1"
        self.receipt_path.write_text(json.dumps(value, sort_keys=True) + "\n")
        with self.assertRaises(ValueError):
            self.invoke()
        self.assertEqual(json.dumps(value, sort_keys=True) + "\n",
                         self.receipt_path.read_text())


if __name__ == "__main__":
    unittest.main()
