"""Campaign Maven binding tests; the full original reader is mocked, not bypassed."""

from contextlib import contextmanager
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci.products.inventory import sha256_bytes
from ci.products.receipt import write_output_manifest
from ci.products.sdk_campaign_maven import verify_campaign_maven_phase
from ci.tests.product_chain_support import write_receipt


class CampaignMavenTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="campaign-maven-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.repository = self.root / "repository"
        self.repository.mkdir()
        self.plan = self.root / "plan.json"
        self.plan.write_bytes(b"{}\n")
        self.capture = self.root / "capture"
        self.capture.mkdir()
        self.original = self.capture / "original"
        (self.original / "shard").mkdir(parents=True)
        self.stage = self.root / "stage"
        output = self.stage / "outputs/evidence"
        output.mkdir(parents=True)
        (output / "original.json").write_bytes(b"original\n")
        self.producer = {"repository": "owner/repository", "workflowPath": ".github/workflows/product-validation.yml",
            "commit": "a" * 40, "tree": "b" * 40, "event": "pull_request",
            "runId": 3, "runAttempt": 1, "pullRequest": 31}
        self.calls = []
        self.object_sha = "sha256:" + "1" * 64
        self.mutate_stage = False
        self.fail_gate = False

    def selected(self, component="sdk-core", phase="binary"):
        target = "common" if component == "sdk-core" else "android"
        manifest = write_output_manifest(self.stage, "sdk", component, phase, target, "0.8.0",
                                         {"evidence": "outputs/evidence"})
        receipt_path = self.root / "receipt.json"
        receipt = write_receipt(receipt_path, product="sdk", component=component, phase=phase,
            target=target, version="0.8.0", version_identity="0.8.0", outputs=manifest["outputs"],
            upstream=[], context={"producer": self.producer})
        raw = receipt_path.read_bytes()
        return {"receipt": receipt, "receiptBytes": raw, "receiptSha256": sha256_bytes(raw),
                "objectSha256": self.object_sha}

    @contextmanager
    def original_gate(self, plan, receipt, **kwargs):
        self.calls.append((plan, receipt.read_bytes(), kwargs))
        if self.fail_gate:
            raise ValueError("full original gate failed")
        try:
            yield {"stage": self.stage, "original": self.original,
                   "receiptBytes": receipt.read_bytes()}
        finally:
            if self.mutate_stage:
                (self.stage / "outputs/evidence/original.json").write_bytes(b"changed\n")

    def shard(self, _path, identity):
        selected = self.envelope
        self.assertEqual((identity.product, identity.component, identity.phase, identity.target),
            tuple(selected["receipt"][field] for field in ("product", "component", "phase", "target")))
        return {"receiptBytes": selected["receiptBytes"], "receiptSha256": selected["receiptSha256"],
                "objectSha256": self.shard_object_sha, "buildKey": selected["receipt"]["buildKey"]}

    def verify(self, envelope, **overrides):
        self.envelope = envelope
        self.shard_object_sha = self.object_sha
        arguments = {"plan": self.plan, "repository_root": self.repository,
            "binary_contract_evidence": {"caller": "contract"},
            "original_context": {"caller": "context"}, "environ": {},
            "keyring": None, "keys_directory": None,
            "android_runtime_archive": None, "binary_original_context": None}
        arguments.update(overrides)
        with patch("ci.sdk_maven_original.verified_retained_maven_phase", self.original_gate), \
                patch("ci.products.sdk_campaign_maven.verify_phase_shard", self.shard):
            return verify_campaign_maven_phase(envelope, self.stage, self.capture, **arguments)

    def test_selected_core_and_android_originals_return_only_exact_receipt_bytes(self):
        for component, phase in (("sdk-core", "binary"), ("sdk-android", "package")):
            with self.subTest(component=component, phase=phase):
                selected = self.selected(component, phase)
                self.assertEqual(self.verify(selected), selected["receiptBytes"])
                plan, raw, policy = self.calls[-1]
                self.assertEqual((plan, raw, policy["capture_root"]),
                                 (self.plan, selected["receiptBytes"], self.capture))
                self.assertEqual(policy["binary_contract_evidence"], {"caller": "contract"})
                self.assertEqual(policy["original_context"], {"caller": "context"})

    def test_selected_object_and_full_gate_must_match(self):
        selected = self.selected()
        with patch("ci.sdk_maven_original.verified_retained_maven_phase", self.original_gate), \
                patch("ci.products.sdk_campaign_maven.verify_phase_shard", return_value={
                    "receiptBytes": selected["receiptBytes"], "receiptSha256": selected["receiptSha256"],
                    "objectSha256": "sha256:" + "2" * 64, "buildKey": selected["receipt"]["buildKey"]}), \
                self.assertRaisesRegex(ValueError, "selected object"):
            verify_campaign_maven_phase(selected, self.stage, self.capture, plan=self.plan,
                repository_root=self.repository, binary_contract_evidence={}, original_context={}, environ={})
        self.fail_gate = True
        with self.assertRaisesRegex(ValueError, "full original gate failed"):
            self.verify(selected)

    def test_late_selected_stage_mutation_fails_after_original_gate_exit(self):
        selected = self.selected()
        self.mutate_stage = True
        with self.assertRaisesRegex(ValueError, "changed during replay"):
            self.verify(selected)

    def test_other_phase_cannot_be_relabelled_as_maven(self):
        selected = self.selected("sdk-core", "binary")
        changed = dict(selected)
        changed["receipt"] = dict(selected["receipt"], phase="metadata")
        with self.assertRaises(ValueError):
            self.verify(changed)
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
