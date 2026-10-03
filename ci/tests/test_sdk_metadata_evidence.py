"""Real receipt/shard/ZIP checks; synthetic observations grant no admission.

Metadata payloads are deliberately opaque transport fixtures, not evidence that
the Core eleven-input or Android Firebase semantic gates have run.
"""

from copy import deepcopy
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from ci import sdk_metadata_evidence as evidence
from ci.tests import test_sdk_facade_capture as fixtures
from products.inventory import (
    canonical_json_bytes, regular_file_inventory, snapshot_regular_tree,
    write_canonical_json,
)


class MetadataEvidenceTest(unittest.TestCase):
    def prepare(self, fixture_type=fixtures.FacadeMetadataCaptureTest):
        fixture = fixture_type(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.call()  # Existing fixture mocks HTTP and Git authority only.
        self.fixture = fixture
        self.destination = fixture.work / "metadata-carrier"
        return fixture

    def call(self, **changes):
        arguments = {"receipt_path": self.fixture.receipt_path,
            "capture_root": self.fixture.output, "destination": self.destination}
        arguments.update(changes)
        with patch("reuse.api_request", side_effect=AssertionError("structural retention must be offline")):
            return evidence.retain_sdk_metadata_evidence(**arguments)

    def test_both_metadata_routes_preserve_every_original_byte_without_policy(self):
        for fixture_type in (fixtures.FacadeMetadataCaptureTest, fixtures.AndroidMetadataCaptureTest):
            with self.subTest(route=fixture_type.__name__):
                fixture = self.prepare(fixture_type)
                before = regular_file_inventory(fixture.output, allow_empty=True)
                records = self.call()
                self.assertEqual(records, evidence.load_sdk_metadata_evidence(self.destination))
                record, = records
                self.assertEqual({"component", "phase", "target", "receiptSha256", "receipt", "capture"}, set(record))
                self.assertEqual(before, regular_file_inventory(self.destination / record["capture"], allow_empty=True))
                self.assertEqual(fixture.receipt_bytes, (self.destination / record["receipt"]).read_bytes())
                self.assertEqual((fixture.output / "transport.zip").read_bytes(),
                                 (self.destination / record["capture"] / "transport.zip").read_bytes())
                self.assertEqual(b"", (self.destination / record["capture"] / "original/worker/gradle.log").read_bytes())
                self.assertEqual(before, regular_file_inventory(fixture.output, allow_empty=True))
                self.assertNotIn("policy", record)
                self.assertNotIn("admission", record)

    def test_nonmetadata_receipts_and_wrong_original_producer_are_rejected(self):
        self.prepare(fixtures.CoreBinaryCaptureTest)
        with self.assertRaisesRegex(ValueError, "metadata"):
            self.call()
        self.assertFalse(self.destination.exists())
        self.prepare()
        receipt = deepcopy(self.fixture.receipt)
        receipt["producer"]["runAttempt"] += 1
        self.fixture.receipt_path.write_bytes(canonical_json_bytes(receipt))
        with self.assertRaisesRegex(ValueError, "exact original receipt"):
            self.call()
        self.assertFalse(self.destination.exists())

    def test_loader_rejects_unknown_duplicate_unsorted_unsafe_and_mismatched_records(self):
        self.prepare()
        records = self.call()
        mutations = (
            lambda rows: rows[0].update(policy={}),
            lambda rows: rows.append(deepcopy(rows[0])),
            lambda rows: rows[0].update(capture="../capture"),
            lambda rows: rows[0].update(receipt="/absolute/receipt.json"),
            lambda rows: rows[0].update(component="sdk-android"),
            lambda rows: rows[0].update(phase="binary"),
            lambda rows: rows[0].update(target="android"),
            lambda rows: rows.clear(),
        )
        for mutate in mutations:
            changed = deepcopy(records)
            mutate(changed)
            write_canonical_json(self.destination / evidence.REQUEST_NAME, changed)
            with self.subTest(records=changed), self.assertRaises(ValueError):
                evidence.load_sdk_metadata_evidence(self.destination)

    def test_loader_supports_sorted_multiple_originals_without_collapsing_producers(self):
        first = self.prepare()
        left = self.call()[0]
        left_carrier = self.destination
        second = self.prepare(fixtures.AndroidMetadataCaptureTest)
        right = self.call()[0]
        combined = second.work / "combined"
        records = sorted([left, right], key=lambda record: record["receiptSha256"])
        for root, record in ((left_carrier, left), (self.destination, right)):
            parent = Path(record["receipt"]).parent
            snapshot_regular_tree(root / parent, combined / parent, allow_empty=True)
        write_canonical_json(combined / evidence.REQUEST_NAME, records)
        self.assertEqual(records, evidence.load_sdk_metadata_evidence(combined))
        self.assertEqual(first.receipt_bytes, (combined / left["receipt"]).read_bytes())
        self.assertEqual(second.receipt_bytes, (combined / right["receipt"]).read_bytes())
        write_canonical_json(combined / evidence.REQUEST_NAME, list(reversed(records)))
        with self.assertRaisesRegex(ValueError, "unique and sorted"):
            evidence.load_sdk_metadata_evidence(combined)

    def test_loader_requires_canonical_index_and_exact_allowlist(self):
        self.prepare()
        records = self.call()
        path = self.destination / evidence.REQUEST_NAME
        path.write_text(json.dumps(records, indent=2) + "\n")
        with self.assertRaises(ValueError):
            evidence.load_sdk_metadata_evidence(self.destination)
        write_canonical_json(path, records)
        (self.destination / "policy.json").write_bytes(b"{}\n")
        with self.assertRaisesRegex(ValueError, "unexpected files"):
            evidence.load_sdk_metadata_evidence(self.destination)

    def test_raw_archive_extracted_original_and_receipt_cannot_change(self):
        for changed in ("archive", "original", "receipt"):
            self.prepare()
            record, = self.call()
            root = self.destination / record["capture"]
            if changed == "archive":
                (root / "transport.zip").write_bytes(b"different archive")
            elif changed == "original":
                (root / "original/worker/gradle.log").write_bytes(b"rewritten log")
            else:
                (self.destination / record["receipt"]).write_bytes(b"{}\n")
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                evidence.load_sdk_metadata_evidence(self.destination)

    def test_source_mutation_during_snapshot_never_publishes(self):
        for changed in ("receipt", "capture", "candidate"):
            self.prepare()
            snapshot = evidence.snapshot_regular_tree
            def mutate(source, destination, **kwargs):
                result = snapshot(source, destination, **kwargs)
                if changed == "receipt":
                    self.fixture.receipt_path.write_bytes(b"{}\n")
                elif changed == "capture":
                    (source / "original/worker/gradle.log").write_bytes(b"changed source")
                else:
                    (destination / "original/worker/gradle.log").write_bytes(b"changed candidate")
                return result
            with self.subTest(changed=changed), patch.object(evidence, "snapshot_regular_tree", side_effect=mutate), \
                    self.assertRaises(ValueError):
                self.call()
            self.assertFalse(self.destination.exists())

    def test_loader_rechecks_originals_even_when_transport_verification_fails(self):
        self.prepare()
        record, = self.call()
        def mutate(*args):
            (self.destination / record["receipt"]).write_bytes(b"{}\n")
            raise ValueError("injected verification failure")
        with patch.object(evidence, "verify_retained_sdk_phase_upload", side_effect=mutate), \
                self.assertRaisesRegex(ValueError, "changed during loading"):
            evidence.load_sdk_metadata_evidence(self.destination)

    def test_fresh_disjoint_nonsymbolic_paths_and_no_secret_are_required(self):
        self.prepare()
        for destination in (self.fixture.output, self.fixture.output / "nested", self.fixture.receipt_path):
            with self.subTest(destination=destination), self.assertRaises(ValueError):
                self.call(destination=destination)
        self.destination.mkdir()
        with self.assertRaisesRegex(ValueError, "fresh"):
            self.call()
        link = self.fixture.work / "symbolic-capture"
        link.symlink_to(self.fixture.output, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "non-symbolic"):
            self.call(capture_root=link, destination=self.fixture.work / "fresh")
        with patch.dict(os.environ, {"CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY": ""}), \
                self.assertRaises(ValueError):
            self.call(destination=self.fixture.work / "secret-forbidden")
        self.assertFalse((self.fixture.work / "secret-forbidden").exists())


if __name__ == "__main__":
    unittest.main()
