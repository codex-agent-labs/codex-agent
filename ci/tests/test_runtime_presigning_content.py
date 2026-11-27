"""Synthetic original K/R semantics, not original CI or hosted execution authority."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci.products.contract_projection import verify_contract_component_projection
from ci.products.inventory import canonical_json_bytes, regular_file_inventory
from ci.products.sdk_runtime_content import (
    verify_native_runtime_presigning_content, verify_native_runtime_projection,
    verify_native_runtime_validation_content,
)
from ci.tests.test_product_native_chain import build_chain


class RuntimePresigningContentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="runtime-presigning-test-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name).resolve()
        cls.chain = build_chain(cls.root / "original", 81, include_bootstrap=True)
        contract = cls.chain["contract"]
        cls.projection = verify_contract_component_projection(
            contract["payload"].parent.parent, contract["receipt"], contract["attestation"],
            contract["signature"], cls.chain["context"]["public_key"],
            expected_trust_domain="development", expected_contract_version="0.2.0",
            required_components=("common", "macos-arm64", "macos-x64", "linux-arm64",
                                 "linux-x64", "windows-x64"),
        )

    def arguments(self, target="linux-x64", variants=None):
        variants = self.chain["variants"] if variants is None else variants
        return dict(target=target, runtime_stage_root=variants["stages"],
                    phase_receipts=variants["variant_phase_receipts"][target],
                    variant_payload=variants["variant_bundles"][target],
                    contract_projection=self.projection, contract_payload=self.chain["contract"]["payload"])

    def signed_arguments(self, target="linux-x64"):
        variants = self.chain["variants"]
        return dict(**self.arguments(target), attestation=variants["variant_attestations"][target],
                    signature=variants["variant_attestation_signatures"][target],
                    public_key=variants["variant_public_keys"][target], required_trust_domain="development")

    def test_all_five_targets_match_signed_content_and_preserve_originals(self):
        before = regular_file_inventory(self.root, allow_empty=True)
        for target in ("macos-arm64", "macos-x64", "linux-arm64", "linux-x64", "windows-x64"):
            with self.subTest(target=target):
                signed, receipt = verify_native_runtime_validation_content(**self.signed_arguments(target))
                content = verify_native_runtime_presigning_content(**self.arguments(target))
                self.assertIs(type(content), dict)
                self.assertEqual(canonical_json_bytes(signed), canonical_json_bytes(content))
                self.assertEqual(self.arguments(target)["phase_receipts"]["validation"].read_bytes(), receipt)
                self.assertEqual(target == "macos-arm64", content["bootstrap"] is not None)
        self.assertEqual(before, regular_file_inventory(self.root, allow_empty=True))

    def test_presigning_needs_no_runtime_signature_but_signed_factory_never_falls_back(self):
        signed = self.signed_arguments()
        signature = signed["signature"]
        hidden = signature.with_name(signature.name + ".hidden")
        signature.rename(hidden)
        try:
            with patch("ci.products.runtime_attestation.sign_manifest", side_effect=AssertionError("key access")), \
                    patch("ci.products.runtime_attestation.verify_runtime_variant_attestation",
                          side_effect=AssertionError("unsigned path attempted signature admission")):
                self.assertIs(type(verify_native_runtime_presigning_content(**self.arguments())), dict)
            with self.assertRaises((ValueError, OSError)):
                verify_native_runtime_projection(**signed)
        finally:
            hidden.rename(signature)
        invalid_root = self.root / "invalid-signature"
        invalid_root.mkdir()
        invalid = invalid_root / signature.name
        invalid.write_bytes(b"not a signature\n")
        try:
            with self.assertRaises((ValueError, OSError)):
                verify_native_runtime_validation_content(**{**signed, "signature": invalid})
        finally:
            invalid.unlink()
            invalid_root.rmdir()

    def test_contract_authority_target_and_exact_receipt_pairing_remain_required(self):
        args = self.arguments()
        with self.assertRaisesRegex(ValueError, "authenticated Contract projection"):
            verify_native_runtime_presigning_content(**{**args, "contract_projection": {}})
        with self.assertRaises(ValueError):
            verify_native_runtime_presigning_content(**{**args, "target": "node-js"})
        for phase in ("binary", "package", "validation", "metadata"):
            receipts = dict(args["phase_receipts"])
            receipts[phase] = self.arguments("windows-x64")["phase_receipts"][phase]
            with self.subTest(phase=phase), self.assertRaises(ValueError):
                verify_native_runtime_presigning_content(**{**args, "phase_receipts": receipts})
        with self.assertRaises(ValueError):
            verify_native_runtime_presigning_content(**{**args, "contract_payload": args["variant_payload"]})

    def test_original_raw_process_junit_reference_and_payload_cannot_be_modified(self):
        args = self.arguments()
        outputs = args["runtime_stage_root"] / "linux-x64/validation/outputs"
        paths = [*sorted((outputs / "execution").glob("*.json")),
                 *sorted((outputs / "native").glob("*.xml")),
                 outputs / "c-abi-reference/include/codex_agent.h", args["variant_payload"]]
        self.assertGreaterEqual(len(paths), 4)
        for path in paths:
            original, mode = path.read_bytes(), path.stat().st_mode
            try:
                path.chmod(0o600)
                path.write_bytes(original + b"invalid original\n")
                with self.subTest(path=path), self.assertRaises(ValueError):
                    verify_native_runtime_presigning_content(**args)
            finally:
                path.write_bytes(original)
                path.chmod(mode)

    def test_coherent_originals_without_execution_or_with_wrong_methods_are_rejected(self):
        from ci.products.runtime_evidence import DESKTOP_RUNTIME_TEST_METHODS
        from ci.tests.product_chain_variants import build_variants

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            missing = build_variants(root / "missing", self.chain["contract"], self.chain["context"],
                                     include_execution=False)
            with self.assertRaisesRegex(ValueError, "original Desktop process execution"):
                verify_native_runtime_presigning_content(**self.arguments(variants=missing))
            with patch("ci.tests.product_chain_variants.DESKTOP_RUNTIME_TEST_METHODS",
                       (*DESKTOP_RUNTIME_TEST_METHODS[:-1], "unexecutedReplacement")):
                wrong = build_variants(root / "wrong", self.chain["contract"], self.chain["context"])
            with self.assertRaisesRegex(ValueError, "raw process output is invalid"):
                verify_native_runtime_presigning_content(**self.arguments(variants=wrong))

    def test_private_originals_are_used_across_source_swap_and_rechecked(self):
        from ci.products.c_abi import portable_verify_c_abi_package_evidence

        args = self.arguments()
        baseline = verify_native_runtime_presigning_content(**args)
        source = args["runtime_stage_root"] / "linux-x64/validation/outputs/c-abi-reference/include/codex_agent.h"
        original = source.read_bytes()

        def swap(*values, **kwargs):
            self.assertNotEqual(source, values[6])
            try:
                source.write_bytes(b"temporarily replaced source\n")
                return portable_verify_c_abi_package_evidence(*values, **kwargs)
            finally:
                source.write_bytes(original)

        with patch("ci.products.c_abi.portable_verify_c_abi_package_evidence", side_effect=swap):
            self.assertEqual(baseline, verify_native_runtime_presigning_content(**args))

        def mutate_capture(*values, **kwargs):
            report = portable_verify_c_abi_package_evidence(*values, **kwargs)
            values[6].chmod(0o600)
            values[6].write_bytes(b"changed verified private source\n")
            return report

        with patch("ci.products.c_abi.portable_verify_c_abi_package_evidence", side_effect=mutate_capture), \
                self.assertRaisesRegex(ValueError, "changed during content verification"):
            verify_native_runtime_presigning_content(**args)
        self.assertEqual(original, source.read_bytes())


if __name__ == "__main__":
    unittest.main()
