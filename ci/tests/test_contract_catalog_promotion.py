"""Offline four-object Contract catalog composition; no hosted trust claim."""

from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest

from ci.contract_catalog_promotion import stage_promoted_contract_catalog
from ci.products.contract_attestation import build_contract_attestation, capture_contract_execution_closure
from ci.products.inventory import canonical_json_bytes, load_canonical_json_bytes, sha256_bytes
from ci.products.restore import store_local_object
from ci.products.signatures import generate_development_key
from ci.tests.test_contract_execution_closure import execution_closure_fixture


@unittest.skipUnless(shutil.which("ssh-keygen"), "ssh-keygen is required")
class ContractCatalogPromotionTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="contract-catalog-promotion-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.payload, receipts, archive = execution_closure_fixture(self.root / "source")
        version = load_canonical_json_bytes(receipts["metadata"].read_bytes())["productVersion"]
        closure = self.root / "closure"
        capture_contract_execution_closure(self.payload, receipts, archive, closure)
        private, public, signing = generate_development_key(self.root / "signer")
        self.private = private
        self.keys = self.root / "keys"
        self.keys.mkdir()
        (self.keys / f"{signing['keyId']}.pub").write_bytes(public.read_bytes())
        self.keyring = self.root / "product-signing-keys.json"
        self.keyring.write_bytes(canonical_json_bytes({
            "schemaVersion": 1, "namespace": signing["namespace"],
            "algorithm": signing["algorithm"], "trustDomain": "release",
            "activeKey": {"keyId": signing["keyId"], "fingerprint": signing["fingerprint"]},
            "retiredKeys": [],
        }))
        self.handoff = self.root / "handoff"
        build_contract_attestation(self.payload, receipts["metadata"],
            {**signing, "trustDomain": "release"}, private, public, self.handoff,
            execution_closure=closure, keyring=self.keyring,
            keys_directory=self.keys, complete_handoff=True)
        self.objects = {}
        self.pins = {}
        for phase in ("binary", "package", "validation", "metadata"):
            receipt_path = receipts[phase]
            receipt = load_canonical_json_bytes(receipt_path.read_bytes())
            output = store_local_object(self.root / f"source/{phase}-stage",
                                        receipt_path, self.root / "cache")
            self.objects[phase] = output["path"]
            self.pins[phase] = {
                "buildKey": receipt["buildKey"],
                "receiptSha256": sha256_bytes(receipt_path.read_bytes()),
                "objectSha256": output["objectSha256"],
                "artifactPath": receipt["outputs"][0]["relativePath"],
                "producer": receipt["producer"],
            }
        self.version = version
        self.destination = self.root / "promoted"
        self.producer = {
            "repository": "codex-agent-labs/codex-agent", "workflowPath": ".github/workflows/promote.yml",
            "event": "push", "commit": "a" * 40, "tree": "b" * 40,
            "pullRequest": None, "runId": 71, "runAttempt": 1,
        }
        self.context = {"kind": "promoted-main", "commit": "a" * 40,
                        "tree": "b" * 40, "promotionRunId": 71,
                        "promotionRunAttempt": 1}

    def stage(self, **changes):
        values = dict(handoff=self.handoff, phase_objects=self.objects,
            phase_pins=self.pins, destination=self.destination,
            repository="codex-agent-labs/codex-agent", context=self.context,
            producer=self.producer, keyring=self.keyring,
            keys_directory=self.keys, private_key=self.private)
        values.update(changes)
        return stage_promoted_contract_catalog(**values)

    def test_exact_four_original_objects_and_receipts_are_preserved(self):
        originals = {phase: path.read_bytes() for phase, path in self.objects.items()}
        receipts = {phase: (self.handoff / f"execution-closure/receipts/{phase}.json").read_bytes()
                    for phase in self.objects}
        handoff = {path.name: path.read_bytes() for path in self.handoff.iterdir() if path.is_file()}
        index = self.stage()
        self.assertEqual(4, len(index["entries"]))
        self.assertEqual(set(self.objects), {entry["phase"] for entry in index["entries"]})
        for phase, pin in self.pins.items():
            relative = f"v1/objects/sha256/{pin['buildKey'][7:]}/{pin['receiptSha256'][7:]}.zip"
            self.assertEqual(originals[phase], (self.destination / relative).read_bytes())
            self.assertEqual(receipts[phase],
                (self.destination / f"execution-closure/receipts/{phase}.json").read_bytes())
        self.assertEqual(originals, {phase: path.read_bytes() for phase, path in self.objects.items()})
        self.assertEqual(handoff, {path.name: path.read_bytes() for path in self.handoff.iterdir() if path.is_file()})

    def test_missing_replaced_or_mispinned_object_fails_without_publication(self):
        missing = dict(self.objects)
        missing.pop("binary")
        with self.assertRaisesRegex(ValueError, "exactly four"):
            self.stage(phase_objects=missing)
        self.assertFalse(self.destination.exists())
        other = self.root / "other.zip"
        other.write_bytes(self.objects["package"].read_bytes())
        with self.assertRaises(ValueError):
            self.stage(phase_objects={**self.objects, "binary": other})
        self.assertFalse(self.destination.exists())
        pins = {phase: dict(pin) for phase, pin in self.pins.items()}
        pins["binary"]["receiptSha256"] = sha256_bytes(b"substituted")
        with self.assertRaises(ValueError):
            self.stage(phase_pins=pins)
        self.assertFalse(self.destination.exists())

    def test_changed_original_producer_is_not_rewritten_to_promotion(self):
        pins = {phase: dict(pin) for phase, pin in self.pins.items()}
        pins["binary"]["producer"] = self.producer
        with self.assertRaisesRegex(ValueError, "original receipt differs"):
            self.stage(phase_pins=pins)
        self.assertFalse(self.destination.exists())

    def test_extra_handoff_byte_is_not_silently_discarded(self):
        (self.handoff / "unselected.txt").write_text("not selected\n")
        with self.assertRaisesRegex(ValueError, "missing or unexpected"):
            self.stage()
        self.assertFalse(self.destination.exists())
