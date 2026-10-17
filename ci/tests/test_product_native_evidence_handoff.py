"""Real K/R authentication over synthetic bytes, never compiler/host evidence."""

import copy
from pathlib import Path
import tempfile
import unittest

from ci.products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, regular_file_inventory,
    sha256_bytes, snapshot_regular_tree,
)
from ci.products.contract_attestation import build_contract_attestation
from ci.products.native_runtime_inputs import (
    load_native_runtime_evidence, stage_native_runtime_evidence,
)
from ci.products.reuse import _native_comparison_provider
from ci.products.runtime_attestation import build_runtime_variant_attestation
from ci.products.signatures import generate_development_key
from ci.tests.test_product_native_chain import build_chain


class NativeRuntimeEvidenceHandoffTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="native-evidence-handoff-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name).resolve()
        cls.chain = build_chain(cls.root / "source", 193, include_bootstrap=True)
        cls.records = sorted(
            (cls.record(target) for target in ("macos-arm64", "linux-x64")),
            key=lambda record: record["receiptSha256"],
        )

    @classmethod
    def record(cls, target):
        def relative(path):
            return Path(path).relative_to(cls.root).as_posix()

        contract, variants = cls.chain["contract"], cls.chain["variants"]
        phases = variants["variant_phase_receipts"][target]
        return {
            "receiptSha256": sha256_bytes(phases["validation"].read_bytes()),
            "contractEvidence": {
                "stageRoot": relative(contract["payload"].parent.parent),
                "phaseReceipt": relative(contract["receipt"]),
                "attestation": relative(contract["attestation"]),
                "attestationSignature": relative(contract["signature"]),
                "publicKey": relative(cls.chain["context"]["public_key"]),
                "expectedTrustDomain": "development", "keyring": None, "keysDirectory": None,
            },
            "runtimeEvidence": {
                "target": target, "stageRoot": relative(variants["stages"]),
                "phaseReceipts": {phase: relative(path) for phase, path in phases.items()},
                "payload": relative(variants["variant_bundles"][target]),
                "attestation": relative(variants["variant_attestations"][target]),
                "attestationSignature": relative(variants["variant_attestation_signatures"][target]),
                "publicKey": relative(variants["variant_public_keys"][target]),
                "keyring": None, "keysDirectory": None,
            },
        }

    def assert_exact_capture(self, records, destination):
        expected = {"native-runtime-evidence.json"}

        def file(original, captured):
            self.assertEqual((self.root / original).read_bytes(), (destination / captured).read_bytes())
            expected.add(captured)

        def tree(original, captured):
            original_inventory = regular_file_inventory(self.root / original)
            self.assertEqual(original_inventory, regular_file_inventory(destination / captured))
            expected.update((Path(captured) / value["relativePath"]).as_posix()
                            for value in original_inventory)

        for original, captured in zip(self.records, records, strict=True):
            self.assertEqual(original["receiptSha256"], captured["receiptSha256"])
            prefix = Path("originals") / captured["receiptSha256"].removeprefix("sha256:")
            for key in ("contractEvidence", "runtimeEvidence"):
                old, new = original[key], captured[key]
                for field in ("attestation", "attestationSignature", "publicKey"):
                    self.assertTrue(Path(new[field]).is_relative_to(
                        prefix if key == "runtimeEvidence" else Path("originals")))
                    file(old[field], new[field])
                self.assertIsNone(new["keyring"])
                self.assertIsNone(new["keysDirectory"])
            old, new = original["contractEvidence"], captured["contractEvidence"]
            self.assertEqual(old["expectedTrustDomain"], new["expectedTrustDomain"])
            file(old["phaseReceipt"], new["phaseReceipt"])
            tree(old["stageRoot"], new["stageRoot"])
            tree(Path(old["attestation"]).parent / "execution-closure",
                 Path(new["attestation"]).parent / "execution-closure")
            old, new = original["runtimeEvidence"], captured["runtimeEvidence"]
            self.assertEqual(old["target"], new["target"])
            self.assertEqual(set(new["phaseReceipts"]), {"binary", "package", "validation", "metadata"})
            file(old["payload"], new["payload"])
            for phase in new["phaseReceipts"]:
                file(old["phaseReceipts"][phase], new["phaseReceipts"][phase])
            for phase in ("package", "validation"):
                tree(Path(old["stageRoot"]) / old["target"] / phase,
                     Path(new["stageRoot"]) / new["target"] / phase)
        self.assertEqual(expected, {value["relativePath"] for value in regular_file_inventory(destination)})

    def assert_rejected(self, records, destination):
        with self.assertRaises((ValueError, OSError)):
            stage_native_runtime_evidence(records, self.root, destination)
        self.assertFalse(destination.exists(), "Failed verification must not publish a partial handoff")

    def test_exact_capture_relocates_without_original_sources_or_sdk_inputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary).resolve()
            destination = workspace / "handoff"
            before_source = regular_file_inventory(self.chain["root"], allow_empty=True)
            before_records = canonical_json_bytes(self.records)
            records = stage_native_runtime_evidence(self.records, self.root, destination)
            self.assertEqual(1, len({record["contractEvidence"]["stageRoot"] for record in records}))
            self.assertEqual((destination / "native-runtime-evidence.json").read_bytes(),
                             canonical_json_bytes(records))
            self.assert_exact_capture(records, destination)
            self.assertEqual(before_source, regular_file_inventory(self.chain["root"], allow_empty=True))
            self.assertEqual(before_records, canonical_json_bytes(self.records))
            unrelated = destination / "unrequested-private-key"
            unrelated.write_bytes(b"synthetic unrelated bytes, not a real key")
            with self.assertRaisesRegex(ValueError, "unexpected files"):
                load_native_runtime_evidence(destination)
            unrelated.unlink()

            # Both original paths and the first handoff location cease to exist.
            relocated = workspace / "relocated"
            destination.rename(relocated)
            hidden_source = self.root / "original-source-unavailable"
            self.chain["root"].rename(hidden_source)
            try:
                self.assertFalse(self.chain["root"].exists())
                loaded = load_native_runtime_evidence(relocated)
                self.assertEqual(records, loaded)
                provider = _native_comparison_provider(relocated, loaded)
                for record in loaded:
                    receipt = load_canonical_json_bytes((relocated / record["runtimeEvidence"]
                                                         ["phaseReceipts"]["validation"]).read_bytes())
                    proof = provider({"receiptSha256": record["receiptSha256"],
                                      "target": record["runtimeEvidence"]["target"]}, None)
                    self.assertTrue(proof.output_inventory(record["receiptSha256"], receipt["outputs"]))
            finally:
                hidden_source.rename(self.chain["root"])
            self.assertEqual(before_source, regular_file_inventory(self.chain["root"], allow_empty=True))

    def test_unsafe_paths_duplicate_records_and_unsorted_records_fail_before_publication(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary).resolve()
            for index, unsafe in enumerate((str(self.chain["contract"]["attestation"]),
                                             "../outside.json", "source\\attestation.json")):
                changed = copy.deepcopy(self.records)
                changed[0]["contractEvidence"]["attestation"] = unsafe
                with self.subTest(path=unsafe):
                    self.assert_rejected(changed, workspace / f"unsafe-{index}")
            self.assert_rejected([self.records[0], self.records[0]], workspace / "duplicate")
            self.assert_rejected(list(reversed(self.records)), workspace / "unsorted")
            overlap = self.root / self.records[0]["contractEvidence"]["stageRoot"] / "nested-handoff"
            with self.assertRaisesRegex(ValueError, "overlaps original"):
                stage_native_runtime_evidence(self.records, self.root, overlap)
            self.assertFalse(overlap.exists())

    def test_symbolic_source_receipt_is_not_followed(self):
        with tempfile.TemporaryDirectory(dir=self.root) as temporary, tempfile.TemporaryDirectory() as output:
            workspace = Path(temporary)
            alias = workspace / "receipt.json"
            alias.symlink_to(self.root / self.records[0]["contractEvidence"]["phaseReceipt"])
            changed = copy.deepcopy(self.records)
            changed[0]["contractEvidence"]["phaseReceipt"] = alias.relative_to(self.root).as_posix()
            self.assert_rejected(changed, Path(output).resolve() / "handoff")

    def test_cross_paired_original_receipts_or_signatures_are_not_authenticated(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary).resolve()
            for index, field in enumerate(("receiptSha256", "package", "attestationSignature")):
                changed = copy.deepcopy(self.records[:1])
                if field == "receiptSha256":
                    changed[0][field] = self.records[1][field]
                elif field == "package":
                    changed[0]["runtimeEvidence"]["phaseReceipts"][field] = (
                        self.records[1]["runtimeEvidence"]["phaseReceipts"][field])
                else:
                    changed[0]["runtimeEvidence"][field] = self.records[1]["runtimeEvidence"][field]
                with self.subTest(field=field):
                    self.assert_rejected(changed, workspace / f"cross-pair-{index}")

    def test_tampered_variant_payload_is_not_published(self):
        with tempfile.TemporaryDirectory(dir=self.root) as temporary, tempfile.TemporaryDirectory() as output:
            workspace = Path(temporary)
            changed = copy.deepcopy(self.records[:1])
            payload = workspace / Path(changed[0]["runtimeEvidence"]["payload"]).name
            payload.write_bytes((self.root / changed[0]["runtimeEvidence"]["payload"]).read_bytes() + b"tampered")
            changed[0]["runtimeEvidence"]["payload"] = payload.relative_to(self.root).as_posix()
            self.assert_rejected(changed, Path(output).resolve() / "handoff")

    def test_tampered_raw_junit_stage_is_not_published(self):
        with tempfile.TemporaryDirectory(dir=self.root) as temporary, tempfile.TemporaryDirectory() as output:
            workspace = Path(temporary)
            original = next(record for record in self.records
                            if record["runtimeEvidence"]["target"] == "macos-arm64")
            changed = copy.deepcopy([original])
            stage = workspace / "stages"
            for phase in ("package", "validation"):
                snapshot_regular_tree(self.root / original["runtimeEvidence"]["stageRoot"] / "macos-arm64" / phase,
                                      stage / "macos-arm64" / phase)
            reports = list((stage / "macos-arm64" / "validation" / "outputs" / "native").glob("TEST-*.xml"))
            self.assertEqual(len(reports), 1)
            reports[0].write_bytes(reports[0].read_bytes() + b"\n<!-- changed raw evidence -->\n")
            changed[0]["runtimeEvidence"]["stageRoot"] = stage.relative_to(self.root).as_posix()
            self.assert_rejected(changed, Path(output).resolve() / "handoff")

    def test_tampered_contract_execution_closure_is_not_published(self):
        with tempfile.TemporaryDirectory(dir=self.root) as temporary, tempfile.TemporaryDirectory() as output:
            workspace = Path(temporary)
            changed = copy.deepcopy(self.records[:1])
            original = self.root / changed[0]["contractEvidence"]["attestation"]
            trust = workspace / "trust"
            snapshot_regular_tree(original.parent, trust)
            execution = trust / "execution-closure" / "execution" / "contract-execution.zip"
            execution.write_bytes(execution.read_bytes() + b"tampered")
            changed[0]["contractEvidence"]["attestation"] = (trust / original.name).relative_to(self.root).as_posix()
            self.assert_rejected(changed, Path(output).resolve() / "handoff")

    def test_synthetic_release_attestations_require_caller_pin_not_transported_keys(self):
        # These locally generated keys exercise release-metadata verification,
        # not protected signing or hosted acceptance. Only external attestations
        # are added: all original product payloads and phase receipts stay intact.
        with tempfile.TemporaryDirectory(dir=self.root) as temporary, tempfile.TemporaryDirectory() as output:
            workspace, destination_root = Path(temporary), Path(output).resolve()
            before_originals = regular_file_inventory(self.chain["root"], allow_empty=True)
            context, contract, variants = self.chain["context"], self.chain["contract"], self.chain["variants"]
            target = "macos-arm64"
            signing = {**context["signing"], "trustDomain": "release", "keyId": "handoff-fixture"}

            def keyring(directory, public_key, metadata):
                directory.mkdir()
                keys = directory / "keys"
                keys.mkdir()
                (keys / "handoff-fixture.pub").write_bytes(public_key.read_bytes())
                path = directory / "keyring.json"
                path.write_bytes(canonical_json_bytes({
                    "schemaVersion": 1, "namespace": metadata["namespace"],
                    "algorithm": metadata["algorithm"], "trustDomain": "release",
                    "activeKey": {"keyId": "handoff-fixture", "fingerprint": metadata["fingerprint"]},
                    "retiredKeys": [],
                }))
                return {"keyring": path, "keys_directory": keys}

            pin = keyring(workspace / "caller-pin", context["public_key"], signing)
            _, wrong_public, wrong_signing = generate_development_key(workspace / "unrelated-key-material")
            wrong_pin = keyring(workspace / "wrong-pin", wrong_public, wrong_signing)
            contract_trust, runtime_trust = workspace / "contract-trust", workspace / "runtime-trust"
            build_contract_attestation(
                contract["payload"], contract["receipt"], signing, context["private_key"],
                context["public_key"], contract_trust, execution_closure=contract["execution_closure"], **pin,
            )
            phases = variants["variant_phase_receipts"][target]
            build_runtime_variant_attestation(
                variants["variant_bundles"][target], phases["binary"], phases["package"], phases["validation"],
                phases["metadata"], variants["variant_validation_evidence"][target], signing,
                context["private_key"], context["public_key"], runtime_trust, **pin,
            )
            records = copy.deepcopy([next(record for record in self.records
                                         if record["runtimeEvidence"]["target"] == target)])
            for name, trust, original_attestation, original_signature in (
                ("contractEvidence", contract_trust, contract["attestation"], contract["signature"]),
                ("runtimeEvidence", runtime_trust, variants["variant_attestations"][target],
                 variants["variant_attestation_signatures"][target]),
            ):
                records[0][name].update({
                    "attestation": (trust / original_attestation.name).relative_to(self.root).as_posix(),
                    "attestationSignature": (trust / original_signature.name).relative_to(self.root).as_posix(),
                    "keyring": pin["keyring"].relative_to(self.root).as_posix(),
                    "keysDirectory": pin["keys_directory"].relative_to(self.root).as_posix(),
                })
            records[0]["contractEvidence"]["expectedTrustDomain"] = "release"
            entry = {"receiptSha256": records[0]["receiptSha256"], "target": target}
            receipt = load_canonical_json_bytes(phases["validation"].read_bytes())
            before_records = canonical_json_bytes(records)
            for label, supplied_pin in (("self-keyed", {}), ("wrong-caller-key", wrong_pin)):
                with self.subTest(pin=label):
                    with self.assertRaises(ValueError):
                        provider = _native_comparison_provider(self.root, records, **supplied_pin)
                        provider(entry, None).output_inventory(entry["receiptSha256"], receipt["outputs"])
                    destination = destination_root / label
                    with self.assertRaises(ValueError):
                        stage_native_runtime_evidence(records, self.root, destination, **supplied_pin)
                    self.assertFalse(destination.exists())
            self.assertEqual(before_records, canonical_json_bytes(records))

            # A transported keyring is not the caller's authority, even when it
            # names another well-formed key. The explicit matching pin wins.
            supplied = copy.deepcopy(records)
            for name in ("contractEvidence", "runtimeEvidence"):
                supplied[0][name]["keyring"] = wrong_pin["keyring"].relative_to(self.root).as_posix()
                supplied[0][name]["keysDirectory"] = wrong_pin["keys_directory"].relative_to(self.root).as_posix()
            proof = _native_comparison_provider(self.root, supplied, **pin)(entry, None)
            self.assertTrue(proof.output_inventory(entry["receiptSha256"], receipt["outputs"]))
            destination = destination_root / "caller-pinned"
            staged = stage_native_runtime_evidence(supplied, self.root, destination, **pin)
            self.assertEqual(staged, load_native_runtime_evidence(destination))
            proof = _native_comparison_provider(destination, staged, **pin)(entry, None)
            self.assertTrue(proof.output_inventory(entry["receiptSha256"], receipt["outputs"]))
            # Transported matching keys still must not authorize a later reader.
            with self.assertRaises(ValueError):
                provider = _native_comparison_provider(destination, staged)
                provider(entry, None).output_inventory(entry["receiptSha256"], receipt["outputs"])
            for name in ("contractEvidence", "runtimeEvidence"):
                captured = staged[0][name]
                self.assertEqual(pin["keyring"].read_bytes(), (destination / captured["keyring"]).read_bytes())
                for field in ("attestation", "attestationSignature"):
                    self.assertEqual((self.root / records[0][name][field]).read_bytes(),
                                     (destination / captured[field]).read_bytes())
            for phase, original in phases.items():
                self.assertEqual(original.read_bytes(),
                                 (destination / staged[0]["runtimeEvidence"]["phaseReceipts"][phase]).read_bytes())
            self.assertEqual(before_originals, regular_file_inventory(self.chain["root"], allow_empty=True))


if __name__ == "__main__":
    unittest.main()
