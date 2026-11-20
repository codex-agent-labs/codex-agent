"""Prepared aggregate equality only; the existing fixture owns semantic admission."""

import copy
from pathlib import Path
import tempfile
import unittest

from ci import runtime_prepared_aggregate as prepared
from ci.tests import test_runtime_aggregate_release as fixture
from products.inventory import load_canonical_json_bytes, snapshot_regular_tree
from products.registry import PhaseInstanceId


class RuntimePreparedAggregateTest(unittest.TestCase):
    setUpClass = classmethod(fixture.RuntimeAggregateReleaseTest.setUpClass.__func__)

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="runtime-prepared-aggregate-")
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name).resolve()
        self.selected = self.work / "selected"
        snapshot_regular_tree(type(self).selected, self.selected, allow_empty=True)
        self.selection = copy.deepcopy(type(self).selection)
        self.authenticated = self.work / "authenticated"
        self.originals = {}
        for instance in prepared._dependency_closure((prepared._METADATA,)):
            identity = (instance.product, instance.component, instance.phase, instance.target)
            relative = "predecessors/" + "-".join(identity)
            source = self.selected / relative
            destination = self.authenticated / relative
            snapshot_regular_tree(source / "stage", destination / "stage")
            destination.mkdir(parents=True, exist_ok=True)
            receipt_bytes = (source / "phase-receipt.json").read_bytes()
            receipt_path = destination / "phase-receipt.json"
            receipt_path.write_bytes(receipt_bytes)
            self.originals[instance] = {
                "stage": destination / "stage", "receiptPath": receipt_path,
                "receipt": load_canonical_json_bytes(receipt_bytes), "receiptBytes": receipt_bytes,
            }

    def verify(self, **changes):
        arguments = dict(producer=self.base.producer, expected_build_key=self.build_key,
                         originals=self.originals)
        arguments.update(changes)
        return prepared.verify_aggregate_prepared_selection(self.selected, self.selection, **arguments)

    def test_exact_complete_authenticated_closure_is_accepted(self):
        result = self.verify()
        self.assertEqual(len(self.originals), len(result))
        self.assertIn(("runtime", "runtime-aggregate", "metadata", "aggregate"), result)

    def test_missing_extra_and_empty_original_maps_reject(self):
        missing = dict(self.originals)
        missing.pop(next(iter(missing)))
        extra = dict(self.originals)
        extra[PhaseInstanceId("sdk", "android", "binary", "android")] = next(iter(extra.values()))
        for originals in ({}, missing, extra):
            with self.subTest(size=len(originals)), self.assertRaisesRegex(ValueError, "exactly match"):
                self.verify(originals=originals)

    def test_mutated_authenticated_receipt_stage_or_declared_bytes_rejects(self):
        instance = next(iter(self.originals))
        original = self.originals[instance]
        receipt = original["receiptPath"]
        raw = receipt.read_bytes()
        try:
            receipt.write_bytes(raw + b"changed")
            with self.assertRaisesRegex(ValueError, "receipt path differs"):
                self.verify()
        finally:
            receipt.write_bytes(raw)
        original["receiptBytes"] = raw + b"changed"
        try:
            with self.assertRaisesRegex(ValueError, "receipt path differs"):
                self.verify()
        finally:
            original["receiptBytes"] = raw
        added = original["stage"] / "unexpected"
        added.write_bytes(b"changed")
        try:
            with self.assertRaisesRegex(ValueError, "differs from caller-authenticated"):
                self.verify()
        finally:
            added.unlink()

    def test_prepared_receipt_stage_and_selection_mutations_reject(self):
        first = self.selection["originals"][0]
        receipt = self.selected / first["directory"] / "phase-receipt.json"
        raw = receipt.read_bytes()
        try:
            receipt.write_bytes(raw + b"changed")
            with self.assertRaises(ValueError):
                self.verify()
        finally:
            receipt.write_bytes(raw)
        stage_file = next(path for path in (self.selected / first["directory"] / "stage").rglob("*")
                          if path.is_file())
        stage_raw = stage_file.read_bytes()
        try:
            stage_file.write_bytes(stage_raw + b"changed")
            with self.assertRaisesRegex(ValueError, "differs from caller-authenticated"):
                self.verify()
        finally:
            stage_file.write_bytes(stage_raw)
        changed = copy.deepcopy(self.selection)
        changed["aggregateManifest"] = "predecessors/wrong/manifest.json"
        (self.selected / "selection.json").write_bytes(fixture.canonical_json_bytes(changed))
        self.selection = changed
        with self.assertRaisesRegex(ValueError, "manifest differs"):
            self.verify()

    def test_contract_handoff_must_remain_the_exact_nonempty_directory(self):
        changed = copy.deepcopy(self.selection)
        changed["contractHandoff"] = "another-contract-input"
        (self.selected / "selection.json").write_bytes(fixture.canonical_json_bytes(changed))
        self.selection = changed
        with self.assertRaisesRegex(ValueError, "selected paths differ"):
            self.verify()


if __name__ == "__main__":
    unittest.main()
