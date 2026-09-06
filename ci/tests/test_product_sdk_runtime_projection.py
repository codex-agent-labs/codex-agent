"""Authenticated synthetic K/R fixtures; never evidence of hosted execution."""

import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci.products.contract_projection import verify_contract_component_projection
from ci.products.inventory import canonical_json_bytes, load_canonical_json_bytes, regular_file_inventory, snapshot_regular_tree
from ci.products.sdk_runtime_content import verify_native_runtime_validation_content
from ci.tests.test_product_native_chain import build_chain


class NativeRuntimeContentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="native-runtime-content-test-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name).resolve()
        cls.left = build_chain(cls.root / "left", 61)
        cls.right = build_chain(cls.root / "right", 62)
        cls.projections = {}
        for name, chain in (("left", cls.left), ("right", cls.right)):
            contract = chain["contract"]
            cls.projections[name] = verify_contract_component_projection(
                contract["payload"].parent.parent, contract["receipt"], contract["attestation"],
                contract["signature"], chain["context"]["public_key"], expected_trust_domain="development",
                expected_contract_version="0.2.0", required_components=(
                    "common", "macos-arm64", "macos-x64", "linux-arm64", "linux-x64", "windows-x64"),
            )

    def arguments(self, target="linux-x64", name="left", variants=None):
        chain = self.left if name == "left" else self.right
        variants = chain["variants"] if variants is None else variants
        return dict(
            target=target, runtime_stage_root=variants["stages"],
            phase_receipts=variants["variant_phase_receipts"][target],
            variant_payload=variants["variant_bundles"][target],
            attestation=variants["variant_attestations"][target],
            signature=variants["variant_attestation_signatures"][target],
            public_key=variants["variant_public_keys"][target],
            contract_projection=self.projections[name], contract_payload=chain["contract"]["payload"],
            required_trust_domain="development",
        )

    def test_four_nonbootstrap_targets_keep_content_across_real_signatures_and_producers(self):
        for target in ("macos-x64", "linux-arm64", "linux-x64", "windows-x64"):
            with self.subTest(target=target):
                left = self.arguments(target)
                before = regular_file_inventory(left["runtime_stage_root"] / target)
                content, receipt = verify_native_runtime_validation_content(**left)
                other_content, other_receipt = verify_native_runtime_validation_content(**self.arguments(target, "right"))
                self.assertEqual(canonical_json_bytes(content), canonical_json_bytes(other_content))
                self.assertNotEqual(receipt, other_receipt)
                self.assertEqual(left["phase_receipts"]["validation"].read_bytes(), receipt)
                self.assertEqual(before, regular_file_inventory(left["runtime_stage_root"] / target))
                self.assertIsNone(content["bootstrap"])
                self.assertEqual("runtime-native-validation-content", content["kind"])
                self.assertNotIn("producerCommit", content["cAbi"])
                self.assertTrue(all(set(item) == {"id"} for item in content["cAbi"]["tools"]))
                self.assertTrue(all(value.startswith("sha256:") for key, value in content["cAbi"].items()
                                    if key.endswith("Sha256")))
                self.assertTrue(all(item["sourceSha256"].startswith("sha256:")
                                    for item in content["cAbi"]["consumers"]))
                self.assertTrue(all(item["sha256"].startswith("sha256:")
                                    for item in content["cAbi"]["importLibraries"]))

    def test_old_mac_lifecycle_fixture_is_rejected_not_upgraded(self):
        with self.assertRaisesRegex(ValueError, "exact authenticated Contract coverage"):
            verify_native_runtime_validation_content(**self.arguments("macos-arm64"))

    def test_signed_original_consumer_source_change_changes_content(self):
        from ci.products.c_abi import STRICT_CONSUMERS
        from ci.tests.product_chain_variants import _CONSUMER_ROOT, build_variants

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            sources = root / "consumer"
            snapshot_regular_tree(_CONSUMER_ROOT, sources)
            source = sources / min(STRICT_CONSUMERS)
            source.write_bytes(source.read_bytes() + b"\n/* synthetic changed source input */\n")
            with patch("ci.tests.product_chain_variants._CONSUMER_ROOT", sources):
                changed = build_variants(root / "variants", self.left["contract"], self.left["context"])
            baseline, _ = verify_native_runtime_validation_content(**self.arguments())
            value, _ = verify_native_runtime_validation_content(**self.arguments(variants=changed))
            self.assertNotEqual(canonical_json_bytes(baseline), canonical_json_bytes(value))
            self.assertNotEqual(baseline["cAbi"]["consumers"], value["cAbi"]["consumers"])
            self.assertNotEqual(baseline["referenceFiles"], value["referenceFiles"])
            self.assertEqual(baseline["desktop"], value["desktop"])

    def test_signed_desktop_report_does_not_replace_exact_raw_junit(self):
        from ci.products.runtime_evidence import DESKTOP_RUNTIME_TEST_METHODS
        from ci.tests.product_chain_variants import build_variants

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            with patch("ci.tests.product_chain_variants.DESKTOP_RUNTIME_TEST_METHODS",
                       (*DESKTOP_RUNTIME_TEST_METHODS[:-1], "unexecutedReplacement")):
                changed = build_variants(root / "variants", self.left["contract"], self.left["context"])
            with self.assertRaisesRegex(ValueError, "methods or class"):
                verify_native_runtime_validation_content(**self.arguments(variants=changed))

    def test_untrusted_contract_and_altered_original_receipt_cannot_enter_gate(self):
        args = self.arguments()
        with self.assertRaisesRegex(ValueError, "authenticated Contract projection"):
            verify_native_runtime_validation_content(**{**args, "contract_projection": {}})
        receipt = args["phase_receipts"]["validation"]
        original = receipt.read_bytes()
        try:
            changed = load_canonical_json_bytes(original)
            changed["producer"]["runId"] += 1
            receipt.write_bytes(canonical_json_bytes(changed))
            with self.assertRaises(ValueError):
                verify_native_runtime_validation_content(**args)
        finally:
            receipt.write_bytes(original)

    def test_original_reference_junit_and_portable_gate_are_mandatory(self):
        args = self.arguments()
        root = args["runtime_stage_root"] / "linux-x64/validation/outputs"
        for path in (root / "c-abi-reference/include/codex_agent.h", *sorted((root / "native").glob("*.xml"))):
            original = path.read_bytes()
            try:
                path.write_bytes(original + b"tampered raw evidence")
                with self.subTest(path=path), self.assertRaises(ValueError):
                    verify_native_runtime_validation_content(**args)
            finally:
                path.write_bytes(original)
        with patch("ci.products.c_abi.portable_verify_c_abi_package_evidence", side_effect=ValueError("portable gate")):
            with self.assertRaisesRegex(ValueError, "portable gate"):
                verify_native_runtime_validation_content(**args)

    def test_signed_variant_for_another_contract_component_is_not_enough(self):
        from ci.products.contract_projection import VerifiedContractProjection, _VERIFIED
        # Explicit opaque-value negative fixture; no successful admission bypass.
        value = self.projections["left"].receipt_value()
        changed = copy.deepcopy(value)
        changed["componentDigests"] = [item for item in changed["componentDigests"] if item["component"] != "linux-x64"]
        args = self.arguments()
        args["contract_projection"] = VerifiedContractProjection(changed, _VERIFIED)
        with self.assertRaisesRegex(ValueError, "authenticated Contract components"):
            verify_native_runtime_validation_content(**args)

    def test_semantic_gate_uses_authenticated_capture_during_source_swap(self):
        from ci.products.c_abi import portable_verify_c_abi_package_evidence

        args = self.arguments()
        baseline, original_receipt = verify_native_runtime_validation_content(**args)
        original_stage = args["runtime_stage_root"] / "linux-x64/validation/outputs"
        original_header = original_stage / "c-abi-reference/include/codex_agent.h"
        header_bytes = original_header.read_bytes()
        def swap(*values, **kwargs):
            self.assertNotEqual(original_stage / "c-abi/c-abi-package-linux-x64.json", values[5])
            self.assertNotEqual(original_header, values[6])
            try:
                original_header.write_bytes(b"temporary untrusted source replacement")
                return portable_verify_c_abi_package_evidence(*values, **kwargs)
            finally:
                original_header.write_bytes(header_bytes)
        with patch("ci.products.c_abi.portable_verify_c_abi_package_evidence", side_effect=swap) as gate:
            content, receipt = verify_native_runtime_validation_content(**args)
            gate.assert_called_once()
        self.assertEqual(baseline, content)
        self.assertEqual(original_receipt, receipt)
        self.assertEqual(header_bytes, original_header.read_bytes())


if __name__ == "__main__":
    unittest.main()
