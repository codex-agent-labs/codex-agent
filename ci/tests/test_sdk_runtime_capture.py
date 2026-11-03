"""Original-byte capture only; synthetic inputs do not authenticate selection."""

import copy
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import product_reuse
from ci.tests.product_chain_support import write_receipt
from ci.tests.test_product_plan import PRODUCER
from products.inventory import canonical_json_bytes, regular_file_inventory
from products.receipt import verify_output_manifest_identity, write_output_manifest
from products.registry import PhaseInstanceId


class SdkRuntimeCaptureTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sdk-runtime-capture-")
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name).resolve()
        self.source = self.work / "originals"
        self.destination = self.work / "capture"
        self.jvm = PhaseInstanceId("runtime", "jvm", "package", "jvm")
        self.node = PhaseInstanceId("runtime", "node-js", "validation", "node-js-binding")
        self.contract = PhaseInstanceId("contract", "contract", "binary", "common")
        phases, receipts = {}, {}
        for instance in (self.jvm, self.node, self.contract):
            root = self.source / "-".join((instance.product, instance.component, instance.phase, instance.target))
            stage = root / "stage"
            (stage / "outputs").mkdir(parents=True)
            # Not a compiled library or test success claim; exercise exact binary copying.
            (stage / "outputs/synthetic.bin").write_bytes(b"synthetic original\x00\xff\n")
            version = "0.2.0" if instance.product == "contract" else "0.2.7"
            manifest = write_output_manifest(stage, instance.product, instance.component, instance.phase,
                instance.target, version, {"fixture": "outputs"})
            path = root / "phase-receipt.json"
            receipt = write_receipt(path, product=instance.product, component=instance.component,
                phase=instance.phase, target=instance.target, version=version,
                outputs=manifest["outputs"], upstream=[], context={"producer": PRODUCER})
            phases[instance] = {"stage": stage, "receiptPath": path, "receipt": receipt}
            receipts[instance] = path.read_bytes()
        self.selected = {"handoff": {"originalPhases": phases, "receiptBytes": receipts}}

    def capture(self, selected=None, destination=None):
        return product_reuse._capture_sdk_runtime_predecessors(
            self.selected if selected is None else selected,
            self.destination if destination is None else destination)

    def test_captures_only_runtime_originals_and_worker_can_revalidate_exact_outputs(self):
        before = regular_file_inventory(self.source)
        result = self.capture()
        self.assertEqual({self.jvm, self.node}, set(result))
        for instance, original in result.items():
            self.assertEqual({"stage", "receiptPath", "receipt", "receiptBytes"}, set(original))
            source = self.selected["handoff"]["originalPhases"][instance]
            self.assertTrue(original["stage"].is_relative_to(self.destination))
            self.assertTrue(original["receiptPath"].is_relative_to(self.destination))
            self.assertNotEqual(source["stage"], original["stage"])
            self.assertEqual(regular_file_inventory(source["stage"]), regular_file_inventory(original["stage"]))
            expected = self.selected["handoff"]["receiptBytes"][instance]
            self.assertEqual(expected, original["receiptBytes"])
            self.assertEqual(expected, original["receiptPath"].read_bytes())
            self.assertEqual(expected, canonical_json_bytes(original["receipt"]))
            manifest = verify_output_manifest_identity(original["stage"], instance.product, instance.component,
                instance.phase, instance.target, original["receipt"]["productVersion"])
            self.assertEqual(original["receipt"]["outputs"], manifest["outputs"])
        self.assertEqual(before, regular_file_inventory(self.source))

    def test_contract_is_not_recaptured_or_required_by_runtime_only_copy(self):
        selected = copy.deepcopy(self.selected)
        selected["handoff"]["originalPhases"][self.contract] = {
            "stage": self.work / "absent-contract-stage", "receiptPath": self.work / "absent-contract-receipt",
            "receipt": self.selected["handoff"]["originalPhases"][self.contract]["receipt"],
        }
        del selected["handoff"]["receiptBytes"][self.contract]
        self.assertEqual({self.jvm, self.node}, set(self.capture(selected)))

    def test_receipt_mapping_and_original_bytes_must_match(self):
        before = regular_file_inventory(self.source)
        for mutation in ("expected-bytes", "identity"):
            selected = copy.deepcopy(self.selected)
            original = selected["handoff"]["originalPhases"][self.jvm]
            if mutation == "expected-bytes":
                selected["handoff"]["receiptBytes"][self.jvm] += b"\n"
            else:
                selected["handoff"]["originalPhases"][self.jvm] = selected["handoff"]["originalPhases"][self.node]
                selected["handoff"]["receiptBytes"][self.jvm] = selected["handoff"]["receiptBytes"][self.node]
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.capture(selected, self.work / mutation)
            self.assertEqual(before, regular_file_inventory(self.source))

    def test_returned_receipt_is_parsed_from_bound_bytes_not_a_separate_mutable_dict(self):
        selected = copy.deepcopy(self.selected)
        selected["handoff"]["originalPhases"][self.jvm]["receipt"]["producer"]["runId"] += 1
        result = self.capture(selected)
        self.assertEqual(self.selected["handoff"]["receiptBytes"][self.jvm], canonical_json_bytes(result[self.jvm]["receipt"]))

    def test_changed_original_receipt_stage_and_symbolic_member_are_rejected_without_original_cleanup(self):
        original = self.selected["handoff"]["originalPhases"][self.jvm]
        receipt_path = original["receiptPath"]
        binary = original["stage"] / "outputs/synthetic.bin"
        for mutation in ("receipt", "payload", "extra", "symlink"):
            path = receipt_path if mutation == "receipt" else binary if mutation == "payload" else original["stage"] / "outputs/extra"
            previous = path.read_bytes() if path.exists() else None
            if mutation == "symlink":
                path.symlink_to(binary)
            else:
                path.write_bytes((previous or b"") + b"unexpected")
            try:
                before = path.read_bytes()
                with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                    self.capture(destination=self.work / mutation)
                self.assertEqual(before, path.read_bytes())
                if mutation == "symlink":
                    self.assertTrue(path.is_symlink())
            finally:
                if previous is None:
                    path.unlink()
                else:
                    path.write_bytes(previous)


if __name__ == "__main__":
    unittest.main()
