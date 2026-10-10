"""Campaign Apple binary binding; signed full handoffs are mocked, never bypassed."""

from contextlib import contextmanager
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from ci.products.inventory import sha256_bytes
from ci.products.receipt import write_output_manifest
from ci.products.sdk_campaign_apple import verify_campaign_apple_binary, verify_campaign_apple_family
from ci.tests.product_chain_support import write_receipt


_TARGETS = ("ios-arm64", "ios-simulator-arm64")


class AppleCampaignBinaryTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="apple-campaign-binary-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.producer = {"repository": "owner/repository", "workflowPath": ".github/workflows/product-validation.yml",
                         "commit": "a" * 40, "tree": "b" * 40, "event": "pull_request",
                         "runId": 3, "runAttempt": 1, "pullRequest": 31}
        self.binary, self.binary_stage = self.envelope("binary", "ios")
        self.package, self.package_stage = self.envelope("package", "ios")
        validation_rows = {target: self.envelope("validation", target) for target in _TARGETS}
        self.validations = {target: row[0] for target, row in validation_rows.items()}
        self.validation_stages = {target: row[1] for target, row in validation_rows.items()}
        self.metadata, self.metadata_stage = self.envelope("metadata", "ios")
        self.handoffs = {target: self.root / f"handoff-{target}" for target in _TARGETS}
        for path in self.handoffs.values():
            path.mkdir()
        self.originals = {}
        for target in _TARGETS:
            original = self.root / f"original-{target}"
            shard = original / "originals/binary/original/shard"
            shard.mkdir(parents=True)
            predecessor = self.root / f"package-{target}" / "inputs/sdk-sdk-ios-binary-ios"
            predecessor.mkdir(parents=True)
            (predecessor / "phase-receipt.json").write_bytes(self.binary["receiptBytes"])
            shutil.copytree(self.binary_stage, predecessor / "stage")
            self.originals[target] = {"original": original,
                "stage": self.validation_stages[target],
                "receiptBytes": self.validations[target]["receiptBytes"],
                "package": {"original": predecessor.parent.parent,
                            "stage": self.package_stage,
                            "receiptBytes": self.package["receiptBytes"]}}
        self.policy = {"plan": str(self.root / "plan.json"),
            "attestationPublicKey": str(self.root / "attestation.pub"),
            "attestationTrustDomain": "development", "keyring": str(self.root / "keyring.json"),
            "keysDirectory": str(self.root / "keys"), "toolingEvidence": str(self.root / "tooling"),
            "toolingPublicKey": str(self.root / "tooling.pub"), "javaExecutable": str(self.root / "java"),
            "toolingTrustDomain": "development", "toolingKeyring": None, "toolingKeysDirectory": None}
        self.events = []
        self.bad_shard = None
        self.fail_target = None
        self.records = {target: {"target": target,
            "receiptSha256": self.validations[target]["receiptSha256"],
            "evidenceRoot": self.handoffs[target].name} for target in _TARGETS}
        self.bad_metadata = False
        self.mutate_after_metadata = False
        self.late_mutation = None

    def envelope(self, phase, target):
        stage = self.root / f"{phase}-{target}-stage"
        output = stage / "outputs/evidence"
        output.mkdir(parents=True)
        (output / "content.json").write_bytes(f"{phase}-{target}".encode())
        manifest = write_output_manifest(stage, "sdk", "sdk-ios", phase, target, "0.8.0",
                                         {"evidence": "outputs/evidence"})
        receipt_path = self.root / f"{phase}-{target}.json"
        receipt = write_receipt(receipt_path, product="sdk", component="sdk-ios", phase=phase,
            target=target, version="0.8.0", version_identity="0.8.0", outputs=manifest["outputs"],
            upstream=[], context={"producer": self.producer})
        raw = receipt_path.read_bytes()
        return {"receipt": receipt, "receiptBytes": raw, "receiptSha256": sha256_bytes(raw),
                "objectSha256": "sha256:" + "1" * 64}, stage

    @contextmanager
    def full_handoff(self, path, *, target, expected_receipt_sha256, **_kwargs):
        self.assertEqual(self.handoffs[target], path)
        self.assertEqual(self.validations[target]["receiptSha256"], expected_receipt_sha256)
        self.events.append(f"enter-{target}")
        if target == self.fail_target:
            raise ValueError("full Apple validation replay failed")
        try:
            yield self.originals[target]
        finally:
            self.events.append(f"exit-{target}")

    def shard(self, _path, identity):
        selected = (self.binary if identity.phase == "binary" else
                    self.package if identity.phase == "package" else self.validations[identity.target])
        return {"receiptBytes": selected["receiptBytes"],
                "receiptSha256": selected["receiptSha256"],
                "objectSha256": self.bad_shard or "sha256:" + "1" * 64}

    def verify(self):
        with patch("ci.products.sdk_campaign_apple.verified_apple_validation_handoff", self.full_handoff), \
                patch("ci.products.sdk_campaign_apple.verify_phase_shard", self.shard):
            return verify_campaign_apple_binary(self.binary, self.binary_stage, self.package,
                self.validations, self.handoffs, repository=self.root,
                policy_revision="a" * 40, policy=self.policy)

    def test_both_full_handoffs_bind_one_selected_binary_and_package(self):
        self.assertEqual(self.binary["receiptBytes"], self.verify())
        self.assertEqual(["enter-ios-arm64", "enter-ios-simulator-arm64",
                          "exit-ios-simulator-arm64", "exit-ios-arm64"], self.events)

    def test_missing_target_or_wrong_binary_object_fails(self):
        with self.assertRaises(ValueError):
            verify_campaign_apple_binary(self.binary, self.binary_stage, self.package,
                {"ios-arm64": self.validations["ios-arm64"]}, self.handoffs,
                repository=self.root, policy_revision="a" * 40, policy=self.policy)
        self.assertEqual([], self.events)
        self.bad_shard = "sha256:" + "2" * 64
        with self.assertRaisesRegex(ValueError, "original shard"):
            self.verify()

    def test_other_package_lineage_or_failed_replay_cannot_admit_binary(self):
        self.originals["ios-simulator-arm64"]["package"]["receiptBytes"] = b"different package"
        with self.assertRaisesRegex(ValueError, "package lineage"):
            self.verify()
        self.originals["ios-simulator-arm64"]["package"]["receiptBytes"] = self.package["receiptBytes"]
        self.fail_target = "ios-simulator-arm64"
        with self.assertRaisesRegex(ValueError, "full Apple validation replay failed"):
            self.verify()

    def test_selected_package_object_must_match_original_shard(self):
        self.package["objectSha256"] = "sha256:" + "3" * 64
        with self.assertRaisesRegex(ValueError, "package differs from its original shard"):
            self.verify()

    def test_selected_stage_mutation_during_handoff_fails(self):
        original = self.full_handoff

        @contextmanager
        def mutate(*args, **kwargs):
            with original(*args, **kwargs) as verified:
                if kwargs["target"] == "ios-simulator-arm64":
                    (self.binary_stage / "outputs/evidence/content.json").write_bytes(b"changed")
                yield verified

        with patch("ci.products.sdk_campaign_apple.verified_apple_validation_handoff", mutate), \
                patch("ci.products.sdk_campaign_apple.verify_phase_shard", self.shard), \
                self.assertRaisesRegex(ValueError, "changed during full replay"):
            verify_campaign_apple_binary(self.binary, self.binary_stage, self.package,
                self.validations, self.handoffs, repository=self.root,
                policy_revision="a" * 40, policy=self.policy)

    def family(self):
        @contextmanager
        def package_original(stage, receipt, **_kwargs):
            self.assertEqual(self.package_stage, stage)
            self.assertEqual(self.package["receiptBytes"], receipt.read_bytes())
            self.events.append("package-enter")
            try:
                yield {"original": self.originals[_TARGETS[0]]["package"]["original"]}
            finally:
                self.events.append("package-exit")

        def metadata_original(**kwargs):
            self.events.append("metadata")
            self.assertEqual(self.metadata["receiptBytes"], kwargs["metadata_receipt"].read_bytes())
            self.assertEqual(self.records, {row["target"]: row for row in kwargs["evidence_records"]})
            if self.mutate_after_metadata:
                (self.validation_stages["ios-arm64"] / "outputs/evidence/content.json").write_bytes(b"changed")
            if self.late_mutation is not None:
                self.late_mutation()
            return self.metadata["receipt"], b"wrong" if self.bad_metadata else self.metadata["receiptBytes"]

        with patch("ci.products.sdk_campaign_apple.verified_selected_ios_package", package_original), \
                patch("ci.products.sdk_campaign_apple.verified_apple_validation_handoff", self.full_handoff), \
                patch("ci.products.sdk_campaign_apple.verify_phase_shard", self.shard), \
                patch("ci.products.sdk_campaign_apple.verify_sdk_apple_metadata_admission", metadata_original):
            return verify_campaign_apple_family(self.binary, self.binary_stage,
                self.package, self.package_stage, self.validations, self.validation_stages,
                self.metadata, self.metadata_stage, self.handoffs,
                package_capture=self.root / "package-capture", sdk_capture=self.root / "sdk-capture",
                metadata_evidence_root=self.root, metadata_evidence_records=self.records,
                repository=self.root, policy_revision="a" * 40, policy=self.policy)

    def test_family_replays_original_package_both_validations_and_metadata(self):
        result = self.family()
        self.assertEqual({"binary": self.binary["receiptBytes"],
            "package": self.package["receiptBytes"],
            "validation": {target: self.validations[target]["receiptBytes"] for target in _TARGETS},
            "metadata": self.metadata["receiptBytes"]}, result)
        self.assertEqual(["package-enter", "package-exit", "enter-ios-arm64",
                          "enter-ios-simulator-arm64", "exit-ios-simulator-arm64",
                          "exit-ios-arm64", "metadata"], self.events)

    def test_family_rejects_wrong_selected_validation_stage(self):
        (self.validation_stages["ios-arm64"] / "outputs/evidence/content.json").write_bytes(b"wrong")
        with self.assertRaisesRegex(ValueError, "Declared file inventory does not match"):
            self.family()
        self.assertNotIn("metadata", self.events)

    def test_family_rejects_wrong_original_package_or_metadata_selection(self):
        self.package["objectSha256"] = "sha256:" + "3" * 64
        with self.assertRaisesRegex(ValueError, "original package differs"):
            self.family()
        self.assertNotIn("metadata", self.events)
        self.package["objectSha256"] = "sha256:" + "1" * 64
        self.records["ios-arm64"]["receiptSha256"] = "sha256:" + "4" * 64
        with self.assertRaisesRegex(ValueError, "metadata evidence differs"):
            self.family()
        self.assertEqual([], [event for event in self.events if event == "metadata"])

    def test_family_rejects_metadata_mismatch_and_late_selected_stage_mutation(self):
        self.bad_metadata = True
        with self.assertRaisesRegex(ValueError, "metadata differs from the selected receipt"):
            self.family()
        self.bad_metadata = False
        self.mutate_after_metadata = True
        with self.assertRaisesRegex(ValueError, "selected evidence changed"):
            self.family()

    def test_family_rejects_late_binary_or_validation_slot_mutation(self):
        self.late_mutation = lambda: self.binary.update(objectSha256="sha256:" + "4" * 64)
        with self.assertRaisesRegex(ValueError, "selected evidence changed"):
            self.family()
        self.binary["objectSha256"] = "sha256:" + "1" * 64
        self.late_mutation = lambda: self.validations.__setitem__("ios-arm64", {
            **self.validations["ios-arm64"], "objectSha256": "sha256:" + "5" * 64})
        with self.assertRaisesRegex(ValueError, "selected evidence changed"):
            self.family()

    def test_family_rejects_late_handoff_or_metadata_evidence_mapping_mutation(self):
        self.late_mutation = lambda: self.handoffs.__setitem__(
            "ios-arm64", self.root / "different-handoff")
        with self.assertRaisesRegex(ValueError, "selected evidence changed"):
            self.family()
        self.handoffs["ios-arm64"] = self.root / "handoff-ios-arm64"
        self.late_mutation = lambda: self.records["ios-arm64"].update(
            evidenceRoot="different-handoff")
        with self.assertRaisesRegex(ValueError, "selected evidence changed"):
            self.family()


if __name__ == "__main__":
    unittest.main()
