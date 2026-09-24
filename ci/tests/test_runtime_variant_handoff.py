"""Synthetic signed phase-proof translation, not hosted or current-state admission."""

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci.tests import test_product_native_evidence_handoff as fixture
from ci.products import runtime_variant_handoff as capture
from ci.products.contract_attestation import build_contract_attestation
from ci.products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, regular_file_inventory,
    sha256_bytes, snapshot_regular_tree,
)
from ci.products.receipt import validate_phase_receipt
from ci.products.runtime_attestation import build_runtime_variant_attestation, read_runtime_variant_handoff
from ci.products.signatures import generate_development_key


TARGET = "linux-x64"
PHASES = ("binary", "package", "validation", "metadata")


class RuntimeVariantHandoffTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        support = fixture.NativeRuntimeEvidenceHandoffTest
        support.setUpClass()
        cls.addClassCleanup(support.doClassCleanups)
        cls.root, cls.chain = support.root, support.chain
        context = cls.chain["context"]
        cls.policy_root = cls.root / "caller-policy"
        cls.keys = cls.policy_root / "keys"
        cls.keys.mkdir(parents=True)
        cls.signing = {**context["signing"], "trustDomain": "release"}
        (cls.keys / f"{cls.signing['keyId']}.pub").write_bytes(context["public_key"].read_bytes())
        cls.policy = {"schemaVersion": 1, "namespace": cls.signing["namespace"],
            "algorithm": cls.signing["algorithm"], "trustDomain": "release",
            "activeKey": {name: cls.signing[name] for name in ("keyId", "fingerprint")}, "retiredKeys": []}
        cls.keyring = cls.policy_root / "product-signing-keys.json"
        cls.keyring.write_bytes(canonical_json_bytes(cls.policy))
        contract = cls.chain["contract"]
        cls.contract_trust = cls.root / "original-contract-release"
        build_contract_attestation(contract["payload"], contract["receipt"], cls.signing,
            context["private_key"], context["public_key"], cls.contract_trust,
            execution_closure=contract["execution_closure"], keyring=cls.keyring, keys_directory=cls.keys)
        cls.records, cls.original_handoffs = [], {}
        for target in (TARGET, "macos-arm64"):
            variants = cls.chain["variants"]
            receipts = variants["variant_phase_receipts"][target]
            original = cls.root / "original-release" / target
            build_runtime_variant_attestation(variants["variant_bundles"][target],
                *(receipts[phase] for phase in PHASES), variants["variant_validation_evidence"][target],
                cls.signing, context["private_key"], context["public_key"], original,
                keyring=cls.keyring, keys_directory=cls.keys, complete_handoff=True)
            record = deepcopy(support.record(target))
            record["contractEvidence"].update(
                expectedTrustDomain="release",
                attestation=(cls.contract_trust / contract["attestation"].name).relative_to(cls.root).as_posix(),
                attestationSignature=(cls.contract_trust / contract["signature"].name).relative_to(cls.root).as_posix())
            for name, value in (("attestation", original / variants["variant_attestations"][target].name),
                                ("attestationSignature", original / variants["variant_attestation_signatures"][target].name),
                                ("publicKey", original / "public-key.pub")):
                record["runtimeEvidence"][name] = value.relative_to(cls.root).as_posix()
            for name in ("contractEvidence", "runtimeEvidence"):
                record[name].update(keyring=cls.keyring.relative_to(cls.root).as_posix(),
                                    keysDirectory=cls.keys.relative_to(cls.root).as_posix())
            cls.records.append(record)
            cls.original_handoffs[target] = original
        cls.records.sort(key=lambda record: record["receiptSha256"])

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="retained-variant-test-")
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name).resolve()
        self.destination = self.work / "captured"
        self.phases = self.chain["variants"]["variant_phase_receipts"][TARGET]

    def invoke(self, records=None, **changes):
        return capture.capture_runtime_variant_handoffs(self.records if records is None else records, self.root,
            **{"destination": self.destination, "target": TARGET, "phase_receipts": self.phases,
               "keyring": self.keyring, "keys_directory": self.keys, **changes})

    def selected_campaign(self, matching):
        # Create separate explicitly synthetic selected receipts once; never
        # rewrite the original signed candidate or claim planner/source proof.
        result = {}
        for phase, source in self.phases.items():
            raw = source.read_bytes()
            if phase not in matching:
                value = load_canonical_json_bytes(raw)
                value["producer"]["runId"] += 1000
                raw = canonical_json_bytes(validate_phase_receipt(value))
            path = self.work / "selected" / f"{phase}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            result[phase] = path
        return result

    def test_exact_original_nine_bytes_retained_without_signing_or_ci(self):
        before = regular_file_inventory(self.root, allow_empty=True)
        pinned = {}
        with patch("ci.products.runtime_attestation.sign_manifest", side_effect=AssertionError("read signed")), \
                patch.object(capture, "read_runtime_variant_handoff", wraps=capture.read_runtime_variant_handoff) as reader:
            outputs = self.invoke(original_inventories=pinned)
        self.assertEqual(1, len(outputs))
        reader.assert_called_once()
        self.assertEqual(regular_file_inventory(self.original_handoffs[TARGET]), regular_file_inventory(outputs[0]))
        self.assertEqual(9, len(regular_file_inventory(outputs[0])))
        self.assertEqual({outputs[0]: regular_file_inventory(self.original_handoffs[TARGET])}, pinned)
        expected = sha256_bytes(self.phases["validation"].read_bytes()).removeprefix("sha256:")
        self.assertEqual(self.destination / expected, outputs[0])
        self.assertEqual(before, regular_file_inventory(self.root, allow_empty=True))

    def test_partial_original_phase_match_retains_full_proof_without_claiming_signature_reuse(self):
        selected = self.selected_campaign({"binary"})
        outputs = self.invoke(phase_receipts=selected)
        verified = read_runtime_variant_handoff(outputs[0], target=TARGET, keyring=self.keyring, keys_directory=self.keys)
        self.assertEqual(selected["binary"].read_bytes(), verified["receiptBytes"]["binary"])
        for phase in ("package", "validation", "metadata"):
            self.assertNotEqual(selected[phase].read_bytes(), verified["receiptBytes"][phase])
            self.assertEqual(self.phases[phase].read_bytes(), verified["receiptBytes"][phase])
        self.assertEqual(regular_file_inventory(self.original_handoffs[TARGET]), regular_file_inventory(outputs[0]))

    def test_absent_development_wrong_target_and_nonmatching_candidates_are_safe_misses(self):
        records = deepcopy(self.records)
        for record in records:
            record["contractEvidence"]["expectedTrustDomain"] = "development"
        other = [record for record in self.records if record["runtimeEvidence"]["target"] != TARGET]
        selected = self.selected_campaign(set())
        for candidates, phases in (([], self.phases), (records, self.phases), (other, self.phases), (self.records, selected)):
            with self.subTest(candidates=len(candidates)), patch.object(capture, "read_runtime_variant_handoff") as reader:
                self.assertEqual((), self.invoke(candidates, phase_receipts=phases))
            reader.assert_not_called()
            self.assertFalse(self.destination.exists())

    def test_retired_caller_policy_works_but_transport_policy_cannot_pin_the_reader(self):
        keyring = self.work / "retired.json"
        keyring.write_bytes(canonical_json_bytes({**self.policy, "activeKey": None,
                                                 "retiredKeys": [self.policy["activeKey"]]}))
        outputs = self.invoke(keyring=keyring)
        self.assertEqual(regular_file_inventory(self.original_handoffs[TARGET]), regular_file_inventory(outputs[0]))
        _, public, signing = generate_development_key(self.work / "wrong-key")
        keys = self.work / "wrong-policy/keys"
        keys.mkdir(parents=True)
        (keys / f"{signing['keyId']}.pub").write_bytes(public.read_bytes())
        wrong = keys.parent / "policy.json"
        wrong.write_bytes(canonical_json_bytes({**self.policy,
            "activeKey": {name: signing[name] for name in ("keyId", "fingerprint")}}))
        for pin in ({"keyring": None}, {"keyring": wrong, "keys_directory": keys}):
            destination = self.work / "wrong-output"
            with self.subTest(pin=pin), self.assertRaises(ValueError):
                self.invoke(destination=destination, **pin)
            self.assertFalse(destination.exists())

    def test_matching_invalid_signature_receipt_digest_and_raw_report_fail_closed(self):
        source = next(record for record in self.records if record["runtimeEvidence"]["target"] == TARGET)
        for field in ("signature", "receipt-digest", "raw-report"):
            record = deepcopy(source)
            if field == "receipt-digest":
                record["receiptSha256"] = "sha256:" + "f" * 64
                changed_path = None
            else:
                changed_path = (self.root / record["runtimeEvidence"]["attestationSignature"] if field == "signature" else
                    capture._native_desktop_report(self.root / record["runtimeEvidence"]["stageRoot"], TARGET))
                before = changed_path.read_bytes()
                changed_path.write_bytes(b"invalid SSH signature\n" if field == "signature" else before + b"invalid\n")
            try:
                with self.subTest(field=field), self.assertRaises(ValueError):
                    self.invoke([record])
                self.assertFalse(self.destination.exists())
            finally:
                if changed_path is not None:
                    changed_path.write_bytes(before)

    def test_late_original_private_receipt_and_caller_policy_changes_do_not_publish(self):
        original_reader = capture.read_runtime_variant_handoff
        for name in ("original", "private", "selected", "policy"):
            selected = self.selected_campaign({"binary"})
            restore = []
            def mutate(root, **kwargs):
                result = original_reader(root, **kwargs)
                path = {"original": self.original_handoffs[TARGET] / "public-key.pub",
                        "private": root / "public-key.pub", "selected": selected["binary"], "policy": self.keyring}[name]
                raw = path.read_bytes()
                restore.append((path, raw))
                path.write_bytes(raw + b"changed\n")
                return result
            try:
                with self.subTest(name=name), patch.object(capture, "read_runtime_variant_handoff", side_effect=mutate), \
                        self.assertRaises(ValueError):
                    self.invoke(phase_receipts=selected)
                self.assertFalse(self.destination.exists())
            finally:
                for path, raw in restore:
                    if path.exists():
                        path.write_bytes(raw)

    def test_late_final_publication_change_does_not_replace_verified_handoff(self):
        original_publish = capture.publish_regular_tree

        def mutate(source, destination, **kwargs):
            (source / sha256_bytes(self.phases["validation"].read_bytes()).removeprefix("sha256:") /
             "public-key.pub").write_bytes(b"late replacement\n")
            return original_publish(source, destination, **kwargs)

        with patch.object(capture, "publish_regular_tree", side_effect=mutate), self.assertRaises(ValueError):
            self.invoke()
        self.assertFalse(self.destination.exists())

    def test_caller_policy_and_original_copy_are_pinned_before_verification(self):
        pinned = {"product-signing-keys.json": self.keyring.read_bytes(),
                  f"keys/{self.signing['keyId']}.pub":
                      (self.keys / f"{self.signing['keyId']}.pub").read_bytes()}
        original_policy = capture._public_policy

        def swapped_policy(*args):
            paths, raw = original_policy(*args)
            return paths, {**raw, "product-signing-keys.json": b"transient swap"}

        with patch.object(capture, "_public_policy", side_effect=swapped_policy), \
                self.assertRaisesRegex(ValueError, "caller-pinned bytes"):
            self.invoke(expected_policy=pinned)
        self.assertFalse(self.destination.exists())

        def mutate_private_policy(*args):
            paths, raw = original_policy(*args)
            (args[2] / "product-signing-keys.json").write_bytes(b"changed private policy\n")
            return paths, raw

        with patch.object(capture, "_public_policy", side_effect=mutate_private_policy), \
                self.assertRaisesRegex(ValueError, "private policy"):
            self.invoke(expected_policy=pinned)
        self.assertFalse(self.destination.exists())

        original_copy = capture._copy_file

        def mutate_copy(source, destination, **kwargs):
            original_copy(source, destination, **kwargs)
            if destination.name == "public-key.pub":
                destination.write_bytes(b"changed copied source\n")

        with patch.object(capture, "_copy_file", side_effect=mutate_copy), self.assertRaises(ValueError):
            self.invoke(expected_policy=pinned)
        self.assertFalse(self.destination.exists())

    def test_unsafe_records_outputs_and_selected_identity_preserve_originals(self):
        before = regular_file_inventory(self.root, allow_empty=True)
        record = deepcopy(self.records[0])
        record["runtimeEvidence"]["payload"] = "../escape.zip"
        for records in ([record], [self.records[0], self.records[0]], list(reversed(self.records))):
            with self.subTest(records=len(records)), self.assertRaises(ValueError):
                self.invoke(records)
        link = self.work / "linked"
        link.symlink_to(self.original_handoffs[TARGET], target_is_directory=True)
        existing = self.work / "existing"
        existing.mkdir()
        (existing / "sentinel").write_bytes(b"original")
        for destination in (self.original_handoffs[TARGET] / "nested", self.phases["binary"].parent / "nested",
                            link / "nested", existing):
            with self.subTest(destination=destination), self.assertRaises(ValueError):
                self.invoke(destination=destination)
        with self.assertRaises(ValueError):
            self.invoke(target="windows-x64")
        self.assertEqual(before, regular_file_inventory(self.root, allow_empty=True))
        self.assertEqual(b"original", (existing / "sentinel").read_bytes())


if __name__ == "__main__":
    unittest.main()
