from __future__ import annotations

import copy
import os
from pathlib import Path
import tempfile
import unittest

from ci.products.aggregate import RUNTIME_TARGETS
from ci.products.inventory import load_canonical_json, sha256_bytes, write_canonical_json
from ci.products.receipt import validate_phase_receipt
from ci.products.runtime_aggregate import produce_runtime_aggregate
from ci.products.signatures import generate_development_key
from ci.tests.test_products import runtime_aggregate_artifacts


class Fixture:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.private_key, self.public_key, self.signing = generate_development_key(root / "keys")
        values = runtime_aggregate_artifacts(
            root / "inputs", self.private_key, self.public_key, self.signing,
        )
        (
            _,
            _,
            _,
            self.contract_bundle,
            self.bundles,
            self.metadata_receipts,
            self.phase_receipts,
            self.validation_evidence,
            self.variant_keys,
            self.maven_inputs,
            self.adapters,
        ) = values
        for target_index, target in enumerate(RUNTIME_TARGETS):
            metadata = load_canonical_json(self.metadata_receipts[target])
            metadata["producer"]["runId"] = 100 + target_index
            write_canonical_json(self.metadata_receipts[target], metadata)
            for phase_index, receipt_path in enumerate(self.phase_receipts[target].values()):
                receipt = load_canonical_json(receipt_path)
                receipt["producer"]["runId"] = 200 + 10 * target_index + phase_index
                write_canonical_json(receipt_path, receipt)
    def arguments(self, output: Path) -> dict:
        return {
            "runtime_version": "0.2.2",
            "contract_bundle": self.contract_bundle,
            "contract_public_key": self.public_key,
            "required_trust_domain": "development",
            "variant_bundles": self.bundles,
            "phase_receipts": self.phase_receipts,
            "metadata_receipts": self.metadata_receipts,
            "validation_evidence": self.validation_evidence,
            "trusted_variant_keys": self.variant_keys,
            "runtime_maven_files": self.maven_inputs,
            "adapter_evidence": self.adapters,
            "signing_metadata": self.signing,
            "private_key": self.private_key,
            "public_key": self.public_key,
            "output_directory": output,
        }


class RuntimeAggregateProducerTest(unittest.TestCase):
    def test_is_deterministic_and_preserves_mixed_original_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            fixture = Fixture(root)
            first_output = root / "first"
            second_output = root / "second"
            first_output.mkdir()
            second_output.mkdir()
            bundle_bytes = {target: path.read_bytes() for target, path in fixture.bundles.items()}

            first = produce_runtime_aggregate(**fixture.arguments(first_output))
            second = produce_runtime_aggregate(**fixture.arguments(second_output))
            self.assertEqual(first["manifestPath"].read_bytes(), second["manifestPath"].read_bytes())
            self.assertEqual(first["signaturePath"].read_bytes(), second["signaturePath"].read_bytes())
            self.assertEqual(bundle_bytes, {
                target: path.read_bytes() for target, path in fixture.bundles.items()
            })
            records = {record["target"]: record for record in first["manifest"]["variants"]}
            self.assertEqual({"0.2.0", "0.2.1"}, {
                record["sourceRuntimeVersion"] for record in records.values()
            })
            self.assertEqual(5, len({
                record["producer"]["runId"] for record in records.values()
            }))
            self.assertEqual(15, len({
                phase_record["producer"]["runId"]
                for record in records.values()
                for phase_record in record["phaseReceipts"].values()
            }))
            self.assertTrue(all("reused" not in record for record in records.values()))
            for target, record in records.items():
                metadata = validate_phase_receipt(load_canonical_json(fixture.metadata_receipts[target]))
                self.assertEqual(metadata["producer"], record["producer"])
                for phase, path in fixture.phase_receipts[target].items():
                    receipt = validate_phase_receipt(load_canonical_json(path))
                    self.assertEqual(receipt["producer"], record["phaseReceipts"][phase]["producer"])
            maven = {record["component"]: record for record in first["manifest"]["runtimeMavenFiles"]}
            for value in fixture.maven_inputs:
                self.assertEqual(
                    sha256_bytes(Path(value["file"]).read_bytes()),
                    maven[value["component"]]["sha256"],
                )
            adapters = {record["target"]: record for record in first["manifest"]["adapterEvidence"]}
            for target, path in fixture.adapters.items():
                self.assertEqual(sha256_bytes(path.read_bytes()), adapters[target]["sha256"])

    def test_missing_extra_and_nonempty_output_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            fixture = Fixture(root)
            cases = []
            output = root / "missing"
            output.mkdir()
            arguments = fixture.arguments(output)
            arguments["variant_bundles"] = dict(fixture.bundles)
            arguments["variant_bundles"].pop("windows-x64")
            cases.append(arguments)

            output = root / "extra"
            output.mkdir()
            arguments = fixture.arguments(output)
            arguments["trusted_variant_keys"] = {**fixture.variant_keys, "android": fixture.public_key}
            cases.append(arguments)

            output = root / "nonempty"
            output.mkdir()
            (output / "stale").write_text("stale")
            cases.append(fixture.arguments(output))
            for arguments in cases:
                with self.assertRaises(ValueError):
                    produce_runtime_aggregate(**arguments)
                self.assertFalse(any(
                    path.name.startswith("codex-agent-runtime-") for path in arguments["output_directory"].iterdir()
                ))

    def test_reuse_claim_cannot_be_accepted_or_signed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            fixture = Fixture(root)
            output = root / "output"
            output.mkdir()
            arguments = fixture.arguments(output)
            arguments["reused_variants"] = {target: True for target in RUNTIME_TARGETS}
            with self.assertRaisesRegex(TypeError, "unexpected keyword argument 'reused_variants'"):
                produce_runtime_aggregate(**arguments)
            self.assertFalse(any(output.iterdir()))

    @unittest.skipIf(os.name == "nt", "symlink creation requires elevated Windows privileges")
    def test_symlink_and_receipt_tampering_are_rejected_without_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            fixture = Fixture(root)
            output = root / "symlink-output"
            output.mkdir()
            linked = root / "linked-maven"
            linked.symlink_to(fixture.maven_inputs[0]["file"])
            inputs = copy.deepcopy(fixture.maven_inputs)
            inputs[0]["file"] = linked
            arguments = fixture.arguments(output)
            arguments["runtime_maven_files"] = inputs
            with self.assertRaises(ValueError):
                produce_runtime_aggregate(**arguments)
            self.assertFalse(any(output.iterdir()))

            output = root / "signature-output"
            output.mkdir()
            _, wrong_public_key, _ = generate_development_key(root / "wrong-key")
            arguments = fixture.arguments(output)
            arguments["contract_public_key"] = wrong_public_key
            with self.assertRaises(ValueError):
                produce_runtime_aggregate(**arguments)
            self.assertFalse(any(output.iterdir()))

            target = RUNTIME_TARGETS[0]
            keys = dict(fixture.variant_keys)
            keys[target] = wrong_public_key
            arguments = fixture.arguments(output)
            arguments["trusted_variant_keys"] = keys
            with self.assertRaises(ValueError):
                produce_runtime_aggregate(**arguments)
            self.assertFalse(any(output.iterdir()))

            output = root / "tamper-output"
            output.mkdir()
            receipt = load_canonical_json(fixture.metadata_receipts[target])
            receipt["outputs"][0]["sha256"] = sha256_bytes(b"tampered")
            write_canonical_json(fixture.metadata_receipts[target], receipt)
            with self.assertRaises(ValueError):
                produce_runtime_aggregate(**fixture.arguments(output))
            self.assertFalse(any(output.iterdir()))


if __name__ == "__main__":
    unittest.main()
