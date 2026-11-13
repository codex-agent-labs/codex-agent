from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

from ci.products.contract_attestation import build_contract_attestation
from ci.products.contract_phase10_inventory import (
    capture_contract_phase10_inventory, verify_contract_phase10_inventory,
)
from ci.products.inventory import (
    load_canonical_json, publish_regular_tree, regular_file_inventory,
    snapshot_regular_tree, write_canonical_json,
)
from ci.products.signatures import generate_development_key
from ci.tests.test_contract_attestation import VERSION, _closure, _payload, _producer, _receipt


@unittest.skipUnless(shutil.which("ssh-keygen"), "ssh-keygen is required")
class ContractPhase10InventoryTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="contract-phase10-inventory-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.payload = self.root / f"codex-agent-contract-{VERSION}.zip"
        _payload(self.payload)
        self.receipt = self.root / "receipt.json"
        _receipt(self.receipt, self.payload, _producer(7), "development")
        self.closure = _closure(self.payload, self.receipt, self.root / "closure")
        private, public, signing = generate_development_key(self.root / "key")
        self.private_key, self.public_key, self.signing = private, public, signing
        self.keyring = self.root / "keyring.json"
        self.keys = self.root / "release-keys"
        self.keys.mkdir()
        (self.keys / f"{signing['keyId']}.pub").write_bytes(public.read_bytes())
        write_canonical_json(self.keyring, {
            "schemaVersion": 1, "namespace": signing["namespace"],
            "algorithm": signing["algorithm"], "trustDomain": "release",
            "activeKey": {"keyId": signing["keyId"], "fingerprint": signing["fingerprint"]},
            "retiredKeys": [],
        })
        self.handoff = self.root / "handoff"
        build_contract_attestation(
            self.payload, self.receipt, {**signing, "trustDomain": "release"}, private, public,
            self.handoff, execution_closure=self.closure, keyring=self.keyring,
            keys_directory=self.keys, complete_handoff=True,
        )

    def test_captures_exact_attested_bytes_and_rejects_tampering(self) -> None:
        output = self.root / "phase10"
        record = capture_contract_phase10_inventory(self.handoff, self.keyring, self.keys, output)
        self.assertEqual(record, verify_contract_phase10_inventory(output))
        self.assertEqual(10, len(record["handoffFiles"]))
        self.assertEqual(1, len(record["verifierKeys"]))
        self.assertEqual(self.keyring.read_bytes(), (output / "policy/keyring.json").read_bytes())
        self.assertEqual(regular_file_inventory(self.handoff), regular_file_inventory(output / "handoff"))
        self.assertFalse(any(record["relativePath"].endswith(".key") for record in regular_file_inventory(output)))

        key = output / "policy/keys" / next(iter(self.keys.iterdir())).name
        before = key.read_bytes()
        key.write_bytes(b"different key\n")
        with self.assertRaises(ValueError):
            verify_contract_phase10_inventory(output)
        key.write_bytes(before)

        extra = output / "handoff/unexpected.txt"
        extra.write_bytes(b"unexpected")
        with self.assertRaises(ValueError):
            verify_contract_phase10_inventory(output)
        extra.unlink()

        # An attacker cannot bless an extra file merely by rewriting the
        # unsigned external inventory to match it.
        extra.write_bytes(b"unexpected")
        inventory = output / "inventory.json"
        value = load_canonical_json(inventory)
        value["handoffFiles"] = regular_file_inventory(output / "handoff")
        write_canonical_json(inventory, value)
        with self.assertRaisesRegex(ValueError, "not exact"):
            verify_contract_phase10_inventory(output)
        extra.unlink()
        value["handoffFiles"] = regular_file_inventory(output / "handoff")
        write_canonical_json(inventory, value)

        unexpected_key = output / "policy/keys/unexpected.pub"
        unexpected_key.write_bytes(before)
        value["verifierKeys"] = regular_file_inventory(output / "policy/keys")
        write_canonical_json(inventory, value)
        with self.assertRaisesRegex(ValueError, "not exact"):
            verify_contract_phase10_inventory(output)
        unexpected_key.unlink()
        value["verifierKeys"] = regular_file_inventory(output / "policy/keys")
        write_canonical_json(inventory, value)

        signature = output / "handoff" / f"codex-agent-contract-{VERSION}.attestation.sig"
        signature.write_bytes(b"changed")
        with self.assertRaises(ValueError):
            verify_contract_phase10_inventory(output)

    def test_rejects_overlap_and_non_release_attestation(self) -> None:
        with self.assertRaisesRegex(ValueError, "overlaps"):
            capture_contract_phase10_inventory(self.handoff, self.keyring, self.keys,
                                               self.handoff / "nested")
        with self.assertRaisesRegex(ValueError, "destination must not exist"):
            capture_contract_phase10_inventory(self.handoff, self.keyring, self.keys, self.handoff)

        private, public, signing = generate_development_key(self.root / "other-key")
        development = self.root / "development"
        build_contract_attestation(self.payload, self.receipt, signing, private, public,
                                   development, execution_closure=self.closure, complete_handoff=True)
        with self.assertRaisesRegex(ValueError, "release trust"):
            capture_contract_phase10_inventory(development, self.keyring, self.keys,
                                               self.root / "rejected-development")
        self.assertFalse((self.root / "rejected-development").exists())

    def test_coherent_alternate_handoff_cannot_replace_the_inventoried_source(self) -> None:
        alternate_payload = self.root / "alternate" / self.payload.name
        _payload(alternate_payload, marker="different valid Contract")
        alternate_receipt = self.root / "alternate-receipt.json"
        _receipt(alternate_receipt, alternate_payload, _producer(8), "development")
        alternate_closure = _closure(alternate_payload, alternate_receipt, self.root / "alternate-closure")
        alternate = self.root / "alternate-handoff"
        build_contract_attestation(
            alternate_payload, alternate_receipt, {**self.signing, "trustDomain": "release"},
            self.private_key, self.public_key, alternate, execution_closure=alternate_closure,
            keyring=self.keyring, keys_directory=self.keys, complete_handoff=True,
        )
        self.assertNotEqual(regular_file_inventory(self.handoff), regular_file_inventory(alternate))

        def substituted_snapshot(source: Path, destination: Path) -> None:
            snapshot_regular_tree(alternate if Path(source) == self.handoff else source, destination)

        destination = self.root / "rejected-swap"
        with mock.patch("ci.products.contract_phase10_inventory.snapshot_regular_tree",
                        side_effect=substituted_snapshot), \
                self.assertRaisesRegex(ValueError, "differs from its original inventory"):
            capture_contract_phase10_inventory(self.handoff, self.keyring, self.keys, destination)
        self.assertFalse(destination.exists())

    def test_late_mutation_of_verified_handoff_fails_before_publication(self) -> None:
        destination = self.root / "rejected-late-mutation"

        def mutate_before_copy(source: Path, output: Path, *, expected_inventory):
            (source / "handoff" / f"codex-agent-contract-{VERSION}.attestation.sig").write_bytes(b"changed")
            publish_regular_tree(source, output, expected_inventory=expected_inventory)

        with mock.patch("ci.products.contract_phase10_inventory.publish_regular_tree",
                        side_effect=mutate_before_copy), \
                self.assertRaisesRegex(ValueError, "pinned inventory"):
            capture_contract_phase10_inventory(self.handoff, self.keyring, self.keys, destination)
        self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
