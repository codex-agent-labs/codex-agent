"""Android campaign composition; hosted readers are mocked, not accepted."""

from contextlib import contextmanager
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci.products.inventory import sha256_bytes
from ci.products.receipt import write_output_manifest
from ci.products.sdk_campaign_android import verify_campaign_android_family
from ci.tests.product_chain_support import write_receipt


class AndroidCampaignTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="android-campaign-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.repository = self.root / "repository"
        self.repository.mkdir()
        self.plan = self.root / "plan.json"
        self.plan.write_bytes(b"{}\n")
        self.envelopes, self.stages, self.receipts = {}, {}, {}
        producer = {"repository": "owner/repository", "workflowPath": ".github/workflows/product-validation.yml",
            "commit": "a" * 40, "tree": "b" * 40, "event": "pull_request",
            "runId": 3, "runAttempt": 1, "pullRequest": 31}
        for phase in ("binary", "package", "validation", "metadata"):
            stage = self.root / f"{phase}-stage"
            output = stage / "outputs/evidence.json"
            output.parent.mkdir(parents=True)
            output.write_bytes(phase.encode())
            manifest = write_output_manifest(stage, "sdk", "sdk-android", phase, "android", "0.8.0",
                                             {"evidence": "outputs/evidence.json"})
            receipt = self.root / f"{phase}-receipt.json"
            value = write_receipt(receipt, product="sdk", component="sdk-android", phase=phase,
                target="android", version="0.8.0", version_identity="0.8.0",
                outputs=manifest["outputs"], upstream=[], context={"producer": producer})
            raw = receipt.read_bytes()
            self.envelopes[phase] = {"receipt": value, "receiptBytes": raw,
                "receiptSha256": sha256_bytes(raw), "objectSha256": "sha256:" + "1" * 64}
            self.stages[phase] = stage
            if phase in ("binary", "package"):
                self.receipts[phase] = receipt
        self.validation_capture = self.root / "validation-capture"
        (self.validation_capture / "original").mkdir(parents=True)
        (self.validation_capture / "original/content").write_bytes(b"original\n")
        self.official_capture = self.root / "official-capture"
        (self.official_capture / "original/shard").mkdir(parents=True)
        (self.official_capture / "original/content").write_bytes(b"original\n")
        self.evidence_root = self.root / "metadata-evidence"
        self.evidence_root.mkdir()
        self.records = [{"receiptSha256": self.envelopes["metadata"]["receiptSha256"],
                         "captureRoot": "original-metadata"}]
        for name in ("compatibility", "tooling.pub", "java", "apkanalyzer"):
            (self.root / name).write_bytes(b"input\n")
        (self.root / "tooling").mkdir()
        common = {"compatibility_request": self.root / "compatibility",
            "binary_contract_evidence": {"source": "caller"}, "trusted_source_commit": "a" * 40,
            "trusted_source_tree": "b" * 40, "tooling_evidence": self.root / "tooling",
            "tooling_public_key": self.root / "tooling.pub", "java_executable": self.root / "java",
            "apkanalyzer_executable": self.root / "apkanalyzer", "required_trust_domain": "development",
            "tooling_keyring": None, "tooling_keys_directory": None}
        self.original = {**common, "validation_artifact_id": 4,
            "validation_artifact_sha256": "sha256:" + "2" * 64,
            "trusted_workflow_sha": "c" * 40, "trusted_android_workflow_sha": "d" * 40,
            "expected_original_run_id": 3, "expected_original_run_attempt": 1}
        self.metadata_policy = {"plan": str(self.plan), "validationCapture": str(self.validation_capture),
            "packageStage": str(self.stages["package"]), "packageReceipt": str(self.receipts["package"]),
            "binaryStage": str(self.stages["binary"]), "binaryReceipt": str(self.receipts["binary"]),
            "compatibilityRequest": str(common["compatibility_request"]),
            "binaryContractEvidence": common["binary_contract_evidence"],
            "trustedSourceCommit": common["trusted_source_commit"],
            "trustedSourceTree": common["trusted_source_tree"],
            "originalContext": {"repositoryRoot": "/runner/repository", "metadataRequest": "/runner/request"},
            "toolingEvidence": str(common["tooling_evidence"]),
            "toolingPublicKey": str(common["tooling_public_key"]),
            "javaExecutable": str(common["java_executable"]),
            "apkanalyzerExecutable": str(common["apkanalyzer_executable"]),
            "toolingTrustDomain": "development", "toolingKeyring": None,
            "toolingKeysDirectory": None}
        self.metadata_calls = []
        self.mutate = False

    @contextmanager
    def official(self, plan, receipt, **kwargs):
        self.assertEqual((plan, receipt.read_bytes()),
                         (self.plan, self.envelopes["validation"]["receiptBytes"]))
        self.assertEqual(kwargs["trusted_source_tree"], "b" * 40)
        try:
            yield {"original": self.official_capture / "original", "capture": self.official_capture,
                "stage": self.stages["validation"],
                "receiptBytes": self.envelopes["validation"]["receiptBytes"]}
        finally:
            if self.mutate:
                (self.stages["metadata"] / "outputs/evidence.json").write_bytes(b"changed")

    def shard(self, _root, identity):
        self.assertEqual((identity.component, identity.phase), ("sdk-android", "validation"))
        value = self.envelopes["validation"]
        return {"receiptBytes": value["receiptBytes"], "receiptSha256": value["receiptSha256"],
                "objectSha256": value["objectSha256"], "buildKey": value["receipt"]["buildKey"]}

    def verify(self):
        with patch("ci.sdk_android_firebase_original.verified_original_android_firebase_validation",
                   self.official), patch("ci.products.sdk_campaign_android.verify_phase_shard", self.shard), \
                patch("ci.products.sdk_campaign_android.AndroidMetadataAdmission") as admission:
            result = verify_campaign_android_family(envelopes=self.envelopes, stages=self.stages,
                receipts=self.receipts, plan=self.plan, repository=self.repository,
                original_validation=self.original, metadata_evidence_root=self.evidence_root,
                metadata_evidence_records=self.records, metadata_policy=self.metadata_policy,
                policy_revision="e" * 40, token="local-mock", environ={})
            admission.return_value.verify_metadata.assert_called_once_with(
                self.envelopes["metadata"], [self.envelopes["validation"]])
            return result

    def test_complete_family_returns_only_original_receipts(self):
        result = self.verify()
        self.assertEqual(result, {name: value["receiptBytes"] for name, value in self.envelopes.items()})

    def test_mismatched_original_authority_and_lineage_fail(self):
        self.metadata_policy["trustedSourceTree"] = "f" * 40
        with self.assertRaisesRegex(ValueError, "caller authority"):
            self.verify()
        self.metadata_policy["trustedSourceTree"] = "b" * 40
        (self.validation_capture / "original/content").write_bytes(b"different\n")
        with self.assertRaisesRegex(ValueError, "metadata lineage"):
            self.verify()

    def test_late_selected_stage_change_fails_after_full_reader(self):
        self.mutate = True
        with self.assertRaisesRegex(ValueError, "selected evidence"):
            self.verify()


if __name__ == "__main__":
    unittest.main()
