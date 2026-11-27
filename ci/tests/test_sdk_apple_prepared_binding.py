"""Real prepared byte binding; enclosing upload authority is deliberately absent."""

from pathlib import Path
import unittest

from ci.products import sdk_apple_validation_attestation as binding
from ci.products.inventory import (
    canonical_json_bytes, regular_file_inventory, sha256_bytes, sha256_file,
    snapshot_regular_tree, write_canonical_json,
)
from ci.tests import test_sdk_apple_validation_inputs as fixtures


class ApplePreparedBindingTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.AppleValidationInputsTest(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.prepared = self.root / "prepared"
        self.capture = self.prepared / "capture"
        snapshot_regular_tree(self.fixture.entry() / "capture", self.capture, allow_empty=True)
        self.original = self.root / "independent"
        snapshot_regular_tree(self.capture, self.original, allow_empty=True)
        # Retrieval observations legitimately differ; original upload bytes do not.
        (self.original / "capture-transport.json").write_bytes(b'{"different":"observation"}\n')
        self.plan = self.root / "plan.json"
        self.plan.write_bytes((self.capture / "plan/impact-plan.json").read_bytes())
        self.receipt = self.root / "receipt.json"
        self.raw = (self.capture / "original/shard/phase-receipt.json").read_bytes()
        self.receipt.write_bytes(self.raw)
        self.arguments = dict(plan=self.plan, receipt_path=self.receipt, target="ios-arm64",
            expected_receipt_sha256=sha256_bytes(self.raw), artifact_id=91,
            artifact_sha256=sha256_file(self.capture / "transport.zip"))
        self.record = dict(schemaVersion=1, target="ios-arm64", receiptSha256=sha256_bytes(self.raw),
            captureDigest=sha256_bytes(canonical_json_bytes(regular_file_inventory(self.capture, allow_empty=True))),
            planSha256=sha256_file(self.plan), producer=self.fixture.producer,
            originalArtifact=dict(artifactId=91, artifactSha256=self.arguments["artifact_sha256"]))
        write_canonical_json(self.prepared / "preparation.json", self.record)

    def invoke(self, **changes):
        return binding.verified_prepared_apple_validation(
            self.prepared, self.original, **{**self.arguments, **changes})

    def test_preserves_exact_prepared_bytes_despite_new_transport_observation(self):
        before = regular_file_inventory(self.prepared, allow_empty=True)
        with self.invoke() as verified:
            private = verified["capture"]
            self.assertEqual(self.raw, verified["receiptBytes"])
            self.assertEqual(canonical_json_bytes(self.record), verified["preparationBytes"])
            self.assertEqual(regular_file_inventory(self.capture, allow_empty=True),
                             regular_file_inventory(private, allow_empty=True))
        self.assertFalse(private.exists())
        self.assertEqual(before, regular_file_inventory(self.prepared, allow_empty=True))

    def test_wrong_selected_identity_and_noncanonical_record_reject(self):
        for change in ({"target": "ios"}, {"target": "ios-simulator-arm64"}, {"artifact_id": True},
                       {"artifact_id": 92}, {"expected_receipt_sha256": "sha256:" + "0" * 64},
                       {"artifact_sha256": "sha256:" + "0" * 64}):
            with self.subTest(change=change), self.assertRaises(ValueError), self.invoke(**change):
                self.fail("invalid selection admitted")
        record = self.prepared / "preparation.json"
        for value in ({**self.record, "schemaVersion": True}, {**self.record, "extra": 1},
                      {**self.record, "producer": {**self.fixture.producer, "runId": 999}}):
            write_canonical_json(record, value)
            with self.assertRaises(ValueError), self.invoke():
                self.fail("invalid record admitted")

    def test_independent_raw_original_plan_or_receipt_mutation_rejects(self):
        for relative in ("transport.zip", "original/empty.log", "plan/impact-plan.json",
                         "original/shard/phase-receipt.json"):
            path = self.original / relative
            before = path.read_bytes()
            try:
                path.write_bytes(b"changed independently captured original")
                with self.subTest(relative=relative), self.assertRaises(ValueError), self.invoke():
                    self.fail("different original admitted")
            finally:
                path.write_bytes(before)

    def test_context_exit_rechecks_all_input_and_private_bytes(self):
        for name in ("prepared", "independent", "private", "plan", "receipt"):
            path, before = None, None
            try:
                with self.subTest(name=name), self.assertRaises(ValueError):
                    with self.invoke() as verified:
                        path = {"prepared": self.capture / "original/empty.log",
                            "independent": self.original / "capture-transport.json",
                            "private": verified["capture"] / "original/empty.log",
                            "plan": self.plan, "receipt": self.receipt}[name]
                        before = path.read_bytes()
                        path.write_bytes(b"late mutation")
            finally:
                if path is not None and path.exists():
                    path.write_bytes(before)
