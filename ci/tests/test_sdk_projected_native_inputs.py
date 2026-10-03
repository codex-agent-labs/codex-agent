"""Signed synthetic projected Runtime inputs; never hosted acceptance evidence."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci.products.c_abi import C_ABI_PACKAGE_MANIFEST, C_ABI_STAGED_EVIDENCE_PATH, TARGET_SPECS, _json_bytes
from ci.products.contract_projection import verify_contract_component_projection
from ci.products.inventory import canonical_json_bytes, load_json_bytes, regular_file_inventory, sha256_bytes, snapshot_regular_tree
from ci.products.receipt import write_output_manifest
from ci.products.runtime_validation_projection import project_native_validation_stage
from ci.products.sdk_native import INDEX_NAME, verify_staged_native_sdk_inputs
from ci.products.sdk_runtime_content import verify_native_runtime_validation_content
from ci.tests.test_product_native_chain import build_chain
from ci.tests.test_product_sdk_inputs import _request
from ci.tests.test_product_sdk_native import SDK_ROOT


class ProjectedNativeSdkInputsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="sdk-projected-native-test-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name).resolve()

        def projected_manifest(stage, product, component, phase, target, version, roots, **kwargs):
            result = write_output_manifest(stage, product, component, phase, target, version, roots, **kwargs)
            if phase != "validation":
                return result
            # Explicit synthetic execution, projected before receipts/signatures;
            # this never transforms existing accepted evidence.
            raw = load_json_bytes((stage / f"outputs/c-abi/c-abi-package-{target}.json").read_bytes())
            project_native_validation_stage(
                stage, stage.parent / "package", cls.root / "diagnostics" / target,
                target=target, version=version,
                producer={"commit": raw["producerCommit"], "tree": raw["producerTree"]},
            )
            return load_json_bytes((stage / "output-manifest.json").read_bytes())

        with patch("ci.tests.product_chain_variants.write_output_manifest", side_effect=projected_manifest):
            cls.chain = build_chain(cls.root / "products", 71, include_bootstrap=True)
        cls.request = cls.root / "request.json"
        cls.request.write_bytes(canonical_json_bytes(_request(cls.chain["compatibility_args"])))
        cls.sdks = cls.root / "sdks"
        cls.sdks.mkdir()
        compatibility = cls.chain["compatibility"].read_bytes()
        (cls.sdks / "sdk-compatibility.json").write_bytes(compatibility)
        (cls.sdks / "sdk-runtime-root.pub").write_bytes(SDK_ROOT.read_bytes())
        records = []
        for evidence_target, spec in sorted(TARGET_SPECS.items()):
            target = spec.classifier.removeprefix("c-abi-")
            snapshot_regular_tree(cls.chain["variants"]["raw_sdks"][target]["verified_sdk"], cls.sdks / target)
            evidence = (cls.chain["variants"]["stages"] / target / "validation/outputs/c-abi"
                        / f"c-abi-package-{target}.json").read_bytes()
            (cls.sdks / target / C_ABI_STAGED_EVIDENCE_PATH).write_bytes(evidence)
            report = load_json_bytes(evidence)
            producer = cls.chain["context"]["producer"]
            records.append({"target": evidence_target, "classifier": target,
                            "archiveSha256": report["archiveSha256"], "evidenceSha256": sha256_bytes(evidence)[7:],
                            "libraryPath": spec.library_path, "librarySha256": report["librarySha256"],
                            "manifestSha256": sha256_bytes((cls.sdks / target / C_ABI_PACKAGE_MANIFEST).read_bytes())[7:],
                            "producerCommit": producer["commit"], "producerTree": producer["tree"]})
        index = {"schemaVersion": 2, "libraryVersion": "0.2.0", "runtimeProductVersion": "0.2.7",
                 "sdkVersion": "0.2.9", "sdkCompatibilitySha256": sha256_bytes(compatibility)[7:],
                 "producerCommit": "9" * 40, "producerTree": "8" * 40, "targets": records}
        (cls.sdks / INDEX_NAME).write_bytes(_json_bytes(index))

    def test_five_target_staging_uses_original_receipt_producers(self):
        receipts = self.chain["variants"]["variant_phase_receipts"]
        before = {target: paths["validation"].read_bytes() for target, paths in receipts.items()}
        inventory = regular_file_inventory(self.sdks)
        index = verify_staged_native_sdk_inputs(
            self.sdks, self.request, self.chain["variants"]["stages"], SDK_ROOT.read_bytes(),
        )
        for record in index["targets"]:
            original = load_json_bytes(before[record["classifier"]])
            self.assertEqual(original["producer"]["commit"], record["producerCommit"])
            self.assertEqual(original["producer"]["tree"], record["producerTree"])
        self.assertEqual(before, {target: paths["validation"].read_bytes() for target, paths in receipts.items()})
        self.assertEqual(inventory, regular_file_inventory(self.sdks))

    def test_signed_projection_keeps_source_and_execution_checks(self):
        chain, target = self.chain, "linux-x64"
        contract = chain["contract"]
        projection = verify_contract_component_projection(
            contract["payload"].parent.parent, contract["receipt"], contract["attestation"],
            contract["signature"], chain["context"]["public_key"], expected_trust_domain="development",
            expected_contract_version="0.2.0", required_components=("common", target),
        )
        variants = chain["variants"]
        arguments = dict(
            target=target, runtime_stage_root=variants["stages"],
            phase_receipts=variants["variant_phase_receipts"][target],
            variant_payload=variants["variant_bundles"][target],
            attestation=variants["variant_attestations"][target],
            signature=variants["variant_attestation_signatures"][target],
            public_key=variants["variant_public_keys"][target], contract_projection=projection,
            contract_payload=contract["payload"], required_trust_domain="development",
        )
        content, receipt = verify_native_runtime_validation_content(**arguments)
        self.assertEqual(receipt, arguments["phase_receipts"]["validation"].read_bytes())
        self.assertEqual(2, content["cAbi"]["schemaVersion"])
        self.assertNotIn("producerCommit", content["cAbi"])
        with patch("ci.products.runtime_validation_projection.verify_projected_c_abi_evidence",
                   side_effect=ValueError("projected package gate")):
            with self.assertRaisesRegex(ValueError, "projected package gate"):
                verify_native_runtime_validation_content(**arguments)

    def test_receipt_changed_after_signed_admission_cannot_supply_producer(self):
        from ci.products.sdk_compatibility import produce_sdk_compatibility

        receipt = self.chain["variants"]["variant_phase_receipts"]["linux-x64"]["validation"]
        original = receipt.read_bytes()
        def replace_receipt(**arguments):
            result = produce_sdk_compatibility(**arguments)
            changed = load_json_bytes(original)
            changed["producer"]["commit"] = "f" * 40
            receipt.write_bytes(canonical_json_bytes(changed))
            return result
        try:
            with patch("ci.products.sdk_native.produce_sdk_compatibility", side_effect=replace_receipt):
                with self.assertRaisesRegex(ValueError, "receipts changed during authentication"):
                    verify_staged_native_sdk_inputs(
                        self.sdks, self.request, self.chain["variants"]["stages"], SDK_ROOT.read_bytes(),
                    )
        finally:
            receipt.write_bytes(original)


if __name__ == "__main__":
    unittest.main()
