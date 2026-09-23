"""Campaign Apple binary binding; signed full handoffs are mocked, never bypassed."""

from contextlib import contextmanager
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from ci.products.inventory import sha256_bytes
from ci.products.receipt import write_output_manifest
from ci.products.sdk_campaign_apple import verify_campaign_apple_binary
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
        self.package, _ = self.envelope("package", "ios")
        self.validations = {target: self.envelope("validation", target)[0] for target in _TARGETS}
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
                "receiptBytes": self.validations[target]["receiptBytes"],
                "package": {"original": predecessor.parent.parent,
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


if __name__ == "__main__":
    unittest.main()
