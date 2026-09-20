"""Real shard/storage pairing; mocked full handoff is not hosted/native proof."""

from contextlib import contextmanager
from copy import deepcopy
import os
import unittest
from unittest.mock import patch

from ci.products import sdk_apple_validation_admission as admission
from ci.products.inventory import regular_file_inventory
from ci.products.receipt import write_output_manifest
from ci.products.restore import PHASE_PLAN_KEYS, finalize_phase_object
from ci.tests import test_sdk_apple_validation_admission as fixtures


class AppleCollectedAdmissionTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.AppleValidationAdmissionTest(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        f = self.fixture
        self.repository = f.root / "repository"
        self.repository.mkdir()
        stage = f.root / "stage"
        content = stage / "outputs/validation/apple-validation.json"
        content.parent.mkdir(parents=True)
        content.write_bytes(b"semantic fixture")
        write_output_manifest(stage, "sdk", "sdk-ios", "validation", "ios-arm64", "0.8.0",
                              {"apple-validation-content": "outputs/validation"})
        self.shard = f.root / "shard"
        result = finalize_phase_object(stage_root=stage,
            phase_plan={name: f.receipt[name] for name in PHASE_PLAN_KEYS},
            producer=f.receipt["producer"], product_version="0.8.0", trust_domain="development",
            destination=self.shard)
        self.assertEqual(f.raw, result["receiptBytes"])
        self.destination = f.root / "result"
        self.events = []
        self.mutation = None
        self.gate = self.enterContext(patch.object(admission, "verified_apple_validation_handoff",
                                                 side_effect=self.handoff))

    @contextmanager
    def handoff(self, root, **arguments):
        self.events.append("enter")
        self.assertEqual("ios-arm64", arguments["target"])
        self.assertEqual(self.fixture.envelope["receiptSha256"], arguments["expected_receipt_sha256"])
        self.assertFalse(self.destination.exists())
        if self.mutation == "entry":
            raise ValueError("original gate rejected")
        yield {"receiptBytes": self.fixture.raw, "receipt": deepcopy(self.fixture.receipt)}
        self.events.append("exit")
        self.assertFalse(self.destination.exists())
        if self.mutation == "exit":
            raise ValueError("original gate exit rejected")
        if self.mutation == "private":
            (root / "capture/original/empty.log").write_bytes(b"changed")
        elif self.mutation == "carrier":
            (self.fixture.carrier / self.fixture.records[0]["evidenceRoot"] / "capture/original/empty.log").write_bytes(b"changed")
        elif self.mutation == "shard":
            (self.shard / "phase-receipt.json").write_bytes(b"changed")
        elif self.mutation == "policy":
            self.fixture.policy["plan"] += "-changed"

    def invoke(self, **changes):
        return admission.stage_collected_apple_validation(self.shard, self.fixture.carrier, self.destination,
            **{ "target": "ios-arm64", "repository": self.repository,
                "policy_revision": "c" * 40, "policy": self.fixture.policy, **changes})

    def test_full_gate_completes_before_byte_identical_publication(self):
        before = regular_file_inventory(self.fixture.carrier, allow_empty=True)
        self.assertEqual(self.fixture.records, self.invoke())
        self.assertEqual(["enter", "exit"], self.events)
        self.assertEqual(before, regular_file_inventory(self.destination, allow_empty=True))
        self.assertEqual(before, regular_file_inventory(self.fixture.carrier, allow_empty=True))
        self.gate.assert_called_once()

    def test_gate_failure_and_late_mutation_never_publish(self):
        receipt = self.shard / "phase-receipt.json"
        evidence = self.fixture.carrier / self.fixture.records[0]["evidenceRoot"] / "capture/original/empty.log"
        for mutation in ("entry", "exit", "private", "carrier", "shard", "policy"):
            self.mutation = mutation
            before = {path: path.read_bytes() for path in (receipt, evidence)}
            policy = dict(self.fixture.policy)
            try:
                with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                    self.invoke()
                self.assertFalse(self.destination.exists())
            finally:
                for path, raw in before.items():
                    path.write_bytes(raw)
                self.fixture.policy = policy

    def test_wrong_target_and_output_overlap_do_not_enter_gate(self):
        for target in ("ios", "ios-simulator-arm64"):
            with self.subTest(target=target), self.assertRaises(ValueError):
                self.invoke(target=target)
            self.gate.assert_not_called()
        for source in (self.repository, self.shard, self.fixture.carrier):
            self.destination = source / "nested"
            with self.subTest(source=source), self.assertRaises(ValueError):
                self.invoke()
            self.gate.assert_not_called()

    def test_admission_rejects_signing_secret_before_executable_replay(self):
        with patch.dict(os.environ, {"CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY": ""}), \
                self.assertRaises(ValueError):
            self.invoke()
        self.gate.assert_not_called()
        self.assertFalse(self.destination.exists())
