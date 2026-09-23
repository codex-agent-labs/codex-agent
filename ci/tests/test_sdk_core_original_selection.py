"""Selected Core validation requires an unchanged full original replay."""

from contextlib import contextmanager
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci.products.inventory import sha256_bytes, write_canonical_json
from ci.products.receipt import write_output_manifest
from ci.products.sdk_core_original_selection import verify_campaign_core_validation
from ci.tests.product_chain_support import write_receipt


class CoreOriginalSelectionTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="core-original-selection-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.repository = self.root / "repository"
        self.repository.mkdir()
        self.capture = self.root / "capture"
        self.original = self.capture / "original"
        (self.original / "context").mkdir(parents=True)
        (self.original / "shard").mkdir()
        self.stage = self.root / "stage"
        output = self.stage / "outputs/evidence.json"
        output.parent.mkdir(parents=True)
        output.write_bytes(b"evidence\n")
        self.plan = self.root / "plan.json"
        self.plan.write_bytes(b"{}\n")
        self.request = self.root / "request.json"
        self.request.write_bytes(b"{}\n")
        self.tooling = self.root / "tooling"
        self.tooling.mkdir()
        self.public_key = self.root / "tooling.pub"
        self.public_key.write_bytes(b"key\n")
        self.java = self.root / "java"
        self.java.write_bytes(b"launcher\n")
        self.context = {"repositoryRoot": "/runner/repository", "androidSdkDirectory": "/runner/android"}
        self.worker = "/runner/repository/build/core-worker"
        self.object_sha = "sha256:" + "1" * 64
        self.producer = {"repository": "owner/repository", "workflowPath": ".github/workflows/product-validation.yml",
            "commit": "a" * 40, "tree": "b" * 40, "event": "pull_request",
            "runId": 3, "runAttempt": 1, "pullRequest": 31}
        self.calls = []
        self.mutate_stage = False

    def selected(self, target="jvm"):
        manifest = write_output_manifest(self.stage, "sdk", "sdk-core", "validation", target,
            "0.8.0", {"evidence": "outputs/evidence.json"})
        receipt_path = self.root / "receipt.json"
        receipt = write_receipt(receipt_path, product="sdk", component="sdk-core", phase="validation",
            target=target, version="0.8.0", version_identity="0.8.0", outputs=manifest["outputs"],
            upstream=[], context={"producer": self.producer})
        raw = receipt_path.read_bytes()
        return {"receipt": receipt, "receiptBytes": raw, "receiptSha256": sha256_bytes(raw),
                "objectSha256": self.object_sha}

    @contextmanager
    def original_gate(self, plan, receipt, **kwargs):
        self.calls.append((plan, receipt.read_bytes(), kwargs))
        write_canonical_json(self.original / "context/execution-context.json", {
            "schemaVersion": 1, "target": self.envelope["receipt"]["target"],
            "buildKey": self.envelope["receipt"]["buildKey"],
            "producer": self.producer, "originalContext": self.context,
            "workerDirectory": self.actual_worker,
        })
        try:
            yield {"original": self.original, "stage": self.stage, "receiptBytes": receipt.read_bytes()}
        finally:
            if self.mutate_stage:
                (self.stage / "outputs/evidence.json").write_bytes(b"mutated\n")

    def shard(self, _path, identity):
        self.assertEqual((identity.product, identity.component, identity.phase, identity.target),
            ("sdk", "sdk-core", "validation", self.envelope["receipt"]["target"]))
        return {"receiptBytes": self.envelope["receiptBytes"],
                "receiptSha256": self.envelope["receiptSha256"],
                "objectSha256": self.actual_object_sha,
                "buildKey": self.envelope["receipt"]["buildKey"]}

    def verify(self, envelope, **changes):
        self.envelope = envelope
        self.actual_worker = self.worker
        self.actual_object_sha = self.object_sha
        arguments = dict(plan=self.plan, facade_request=self.request, repository_root=self.repository,
            original_context=self.context, original_worker_directory=self.worker,
            tooling_evidence=self.tooling, tooling_public_key=self.public_key,
            java_executable=self.java, policy_revision="a" * 40,
            required_trust_domain="release", environ={})
        arguments.update(changes)
        with patch("ci.sdk_facade_original_validation.verified_retained_sdk_facade_validation", self.original_gate), \
                patch("ci.products.sdk_core_original_selection.verify_phase_shard", self.shard):
            return verify_campaign_core_validation(envelope, self.stage, self.capture, **arguments)

    def test_exact_selected_original_returns_only_receipt_bytes(self):
        selected = self.selected()
        self.assertEqual(self.verify(selected), selected["receiptBytes"])
        plan, raw, policy = self.calls[-1]
        self.assertEqual((plan, raw, policy["capture_root"]),
                         (self.plan, selected["receiptBytes"], self.capture))
        self.assertEqual(policy["tooling_evidence"], self.tooling)

    def test_original_worker_and_object_must_match_independent_selection(self):
        selected = self.selected()
        with patch("ci.sdk_facade_original_validation.verified_retained_sdk_facade_validation", self.original_gate), \
                patch("ci.products.sdk_core_original_selection.verify_phase_shard", self.shard):
            self.envelope = selected
            self.actual_worker = "/different/worker"
            self.actual_object_sha = self.object_sha
            with self.assertRaisesRegex(ValueError, "independent caller pins"):
                verify_campaign_core_validation(selected, self.stage, self.capture, plan=self.plan,
                    facade_request=self.request, repository_root=self.repository,
                    original_context=self.context, original_worker_directory=self.worker,
                    tooling_evidence=self.tooling, tooling_public_key=self.public_key,
                    java_executable=self.java, policy_revision="a" * 40,
                    required_trust_domain="release", environ={})
        with patch("ci.products.sdk_core_original_selection.verify_phase_shard", return_value={
            "receiptBytes": selected["receiptBytes"], "receiptSha256": selected["receiptSha256"],
            "objectSha256": "sha256:" + "2" * 64, "buildKey": selected["receipt"]["buildKey"]}), \
                patch("ci.sdk_facade_original_validation.verified_retained_sdk_facade_validation", self.original_gate), \
                self.assertRaisesRegex(ValueError, "selected object"):
            self.envelope = selected
            self.actual_worker = self.worker
            verify_campaign_core_validation(selected, self.stage, self.capture, plan=self.plan,
                facade_request=self.request, repository_root=self.repository,
                original_context=self.context, original_worker_directory=self.worker,
                tooling_evidence=self.tooling, tooling_public_key=self.public_key,
                java_executable=self.java, policy_revision="a" * 40,
                required_trust_domain="release", environ={})

    def test_late_stage_mutation_and_missing_caller_pin_fail(self):
        selected = self.selected()
        self.mutate_stage = True
        with self.assertRaisesRegex(ValueError, "changed"):
            self.verify(selected)
        self.mutate_stage = False
        with self.assertRaises(ValueError):
            self.verify(selected, original_worker_directory="relative/worker")

    def test_other_phase_is_not_a_core_validation(self):
        selected = self.selected()
        changed = dict(selected, receipt=dict(selected["receipt"], phase="package"))
        with self.assertRaises(ValueError):
            self.verify(changed)
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
