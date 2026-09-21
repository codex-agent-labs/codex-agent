"""Real carrier/ZIP/shard parsing; original Git/signature gates mocked explicitly.

These tests cover transport preservation and held-reader composition, not hosted
compiler evidence or acceptance into a catalog/collector family.
"""

from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

from ci import sdk_maven_evidence as evidence
from ci.tests import test_sdk_facade_capture as fixtures
from products.inventory import (
    regular_file_inventory, snapshot_regular_tree, write_canonical_json,
)


class MavenEvidenceTest(unittest.TestCase):
    def prepare(self, fixture_type=fixtures.CoreBinaryCaptureTest):
        fixture = fixture_type(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.call()  # This fixture mocks all HTTP and current Git authority.
        self.fixture = fixture
        self.destination = fixture.work / "carrier"
        self.context = {"repositoryRoot": "/independent/original-checkout",
                        "workerRoot": "/independent/original-checkout/build/worker"}
        if fixture.phase == "package":
            self.context["compatibilityRequest"] = "/independent/caller-request.json"
        self.binary_context = {"repositoryRoot": "/independent/binary-checkout",
                              "workerRoot": "/independent/binary-checkout/build/worker"}
        proof = fixture.work / "caller-proof"
        proof.mkdir()
        for name in ("stage", "execution-closure", "keys"):
            (proof / name).mkdir()
            (proof / name / "retained").write_bytes(b"caller-owned proof")
        for name in ("receipt.json", "attestation.json", "attestation.sig", "public.pub", "keyring.json"):
            (proof / name).write_bytes(b"caller-owned public policy")
        self.contract = {"stageRoot": str(proof / "stage"), "phaseReceipt": str(proof / "receipt.json"),
            "attestation": str(proof / "attestation.json"), "attestationSignature": str(proof / "attestation.sig"),
            "publicKey": str(proof / "public.pub"), "expectedTrustDomain": "release",
            "keyring": str(proof / "keyring.json"), "keysDirectory": str(proof / "keys")}
        self.archive = proof / "android.tar.gz"
        self.archive.write_bytes(b"caller-pinned archive")
        self.events = []
        self.on_exit = None
        self.wrong_receipt = False

    @contextmanager
    def reader(self, plan, receipt_path, **kwargs):
        self.events.append("enter")
        self.assertEqual(self.fixture.plan_path, plan)
        self.assertEqual(self.fixture.receipt_path, receipt_path)
        self.assertEqual(self.fixture.output, kwargs["capture_root"])
        self.assertEqual(self.contract, kwargs["binary_contract_evidence"])
        self.assertIs(self.context, kwargs["original_context"])
        self.assertEqual(self.fixture.root, kwargs["repository_root"])
        package = self.fixture.phase == "package"
        self.assertEqual(Path(self.contract["keyring"]) if package else None, kwargs["keyring"])
        self.assertEqual(Path(self.contract["keysDirectory"]) if package else None, kwargs["keys_directory"])
        self.assertEqual(self.binary_context if package else None, kwargs["binary_original_context"])
        self.assertEqual(self.archive if self.fixture.component == "sdk-android" else None,
                         kwargs["android_runtime_archive"])
        try:
            receipt = deepcopy(self.fixture.receipt)
            if self.wrong_receipt:
                receipt["producer"]["runAttempt"] += 1
            yield {"receipt": receipt, "receiptBytes": self.fixture.receipt_bytes,
                   "receiptPath": receipt_path, "capture": self.fixture.output}
        finally:
            self.events.append("exit")
            self.assertFalse(self.destination.exists())
            if self.on_exit is not None:
                self.on_exit()

    def call(self, **changes):
        kwargs = dict(binary_contract_evidence=self.contract, original_context=self.context,
                      repository_root=self.fixture.root, environ={})
        if self.fixture.phase == "package":
            kwargs.update(keyring=Path(self.contract["keyring"]), keys_directory=Path(self.contract["keysDirectory"]),
                          binary_original_context=self.binary_context)
        if self.fixture.component == "sdk-android":
            kwargs["android_runtime_archive"] = self.archive
        kwargs.update(changes)
        with patch.object(evidence, "verified_retained_maven_phase", side_effect=self.reader) as held:
            result = evidence.stage_sdk_maven_evidence(self.fixture.plan_path, self.fixture.receipt_path,
                self.fixture.output, self.destination, **kwargs)
            held.assert_called_once()
            return result

    def test_four_routes_preserve_complete_originals_without_policy_serialization(self):
        for fixture_type in (fixtures.CoreBinaryCaptureTest, fixtures.AndroidBinaryCaptureTest,
                             fixtures.CorePackageCaptureTest, fixtures.AndroidPackageCaptureTest):
            with self.subTest(route=fixture_type.__name__):
                self.prepare(fixture_type)
                before = regular_file_inventory(self.fixture.output, allow_empty=True)
                records = self.call()
                self.assertEqual(["enter", "exit"], self.events)
                self.assertEqual(records, evidence.load_sdk_maven_evidence(self.destination))
                record, = records
                self.assertEqual(before, regular_file_inventory(self.destination / record["capture"], allow_empty=True))
                self.assertEqual(self.fixture.receipt_bytes, (self.destination / record["receipt"]).read_bytes())
                self.assertEqual(b"", (self.destination / record["capture"] / "original/worker/gradle.log").read_bytes())
                self.assertEqual((self.fixture.output / "transport.zip").read_bytes(),
                                 (self.destination / record["capture"] / "transport.zip").read_bytes())
                self.assertEqual({"component", "phase", "target", "receiptSha256", "receipt", "capture"}, set(record))
                self.assertNotIn(b"independent/original", (self.destination / evidence.REQUEST_NAME).read_bytes())
                self.assertEqual(before, regular_file_inventory(self.fixture.output, allow_empty=True))

    def test_loader_rejects_unknown_duplicate_unsafe_and_mismatched_records(self):
        self.prepare()
        records = self.call()
        changes = (
            lambda rows: rows[0].update(policy={}),
            lambda rows: rows.append(deepcopy(rows[0])),
            lambda rows: rows[0].update(capture="../capture"),
            lambda rows: rows[0].update(receipt="/absolute/receipt.json"),
            lambda rows: rows[0].update(component="sdk-android"),
            lambda rows: rows[0].update(phase="validation"),
            lambda rows: rows.clear(),
        )
        for change in changes:
            rows = deepcopy(records)
            change(rows)
            write_canonical_json(self.destination / evidence.REQUEST_NAME, rows)
            with self.subTest(records=rows), self.assertRaises(ValueError):
                evidence.load_sdk_maven_evidence(self.destination)
        (self.destination / evidence.REQUEST_NAME).write_bytes(b"[]")
        with self.assertRaises(ValueError):
            evidence.load_sdk_maven_evidence(self.destination)

    def test_loader_rejects_extra_missing_and_changed_raw_capture(self):
        self.prepare()
        record, = self.call()
        for number, change in enumerate((
                lambda root: (root / "extra").write_bytes(b"unlisted"),
                lambda root: (root / record["receipt"]).unlink(),
                lambda root: (root / record["capture"] / "transport.zip").write_bytes(b"different"),
                lambda root: (root / record["capture"] / "original/worker/gradle.log").write_bytes(b"changed"))):
            candidate = self.fixture.work / str(number)
            snapshot_regular_tree(self.destination, candidate, allow_empty=True)
            change(candidate)
            with self.subTest(change=number), self.assertRaises((ValueError, OSError)):
                evidence.load_sdk_maven_evidence(candidate)

    def test_multiple_originals_have_one_sorted_unique_receipt_index(self):
        self.prepare()
        first, = self.call()
        first_carrier = self.destination
        self.prepare(fixtures.AndroidBinaryCaptureTest)
        second, = self.call()
        combined = self.fixture.work / "combined"
        snapshot_regular_tree(first_carrier, combined, allow_empty=True)
        prefix = Path(second["capture"]).parent
        snapshot_regular_tree(self.destination / prefix, combined / prefix, allow_empty=True)
        records = sorted((first, second), key=lambda value: value["receiptSha256"])
        write_canonical_json(combined / evidence.REQUEST_NAME, records)
        self.assertEqual(records, evidence.load_sdk_maven_evidence(combined))
        write_canonical_json(combined / evidence.REQUEST_NAME, list(reversed(records)))
        with self.assertRaisesRegex(ValueError, "unique and sorted"):
            evidence.load_sdk_maven_evidence(combined)

    def test_loader_rechecks_complete_original_lifetime(self):
        self.prepare()
        record, = self.call()
        verify = evidence.verify_retained_sdk_phase_upload
        def mutate(capture, receipt):
            verify(capture, receipt)
            (capture / "original/worker/gradle.log").write_bytes(b"changed after ZIP check")
        with patch.object(evidence, "verify_retained_sdk_phase_upload", side_effect=mutate), \
                self.assertRaisesRegex(ValueError, "changed during loading"):
            evidence.load_sdk_maven_evidence(self.destination)

    def test_held_receipt_mismatch_and_context_exit_failure_never_publish(self):
        self.prepare()
        self.wrong_receipt = True
        with self.assertRaisesRegex(ValueError, "Held Maven original"):
            self.call()
        self.assertFalse(self.destination.exists())
        self.wrong_receipt = False
        def reject():
            raise ValueError("original gate exit failed")
        self.on_exit = reject
        with self.assertRaisesRegex(ValueError, "original gate exit failed"):
            self.call()
        self.assertFalse(self.destination.exists())

    def test_late_policy_original_receipt_or_key_mutation_never_publishes(self):
        for name in ("context", "receipt", "key", "capture"):
            with self.subTest(source=name):
                self.prepare()
                def mutate():
                    if name == "context":
                        self.context["workerRoot"] += "-changed"
                    else:
                        path = {"receipt": self.fixture.receipt_path,
                                "key": Path(self.contract["publicKey"]),
                                "capture": self.fixture.output / "original/worker/gradle.log"}[name]
                        path.write_bytes(b"changed at context exit")
                self.on_exit = mutate
                with self.assertRaisesRegex(ValueError, "changed during staging"):
                    self.call()
                self.assertFalse(self.destination.exists())

    def test_destination_freshness_overlap_and_secret_reject_before_replay(self):
        self.prepare()
        original_destination = self.destination
        self.destination.mkdir()
        (self.destination / "keep").write_bytes(b"preserved")
        for destination in (self.destination, self.fixture.output / "child",
                            Path(self.contract["stageRoot"]) / "child", self.fixture.root / "carrier"):
            self.destination = destination
            with patch.object(evidence, "verified_retained_maven_phase") as held, self.assertRaises(ValueError):
                evidence.stage_sdk_maven_evidence(self.fixture.plan_path, self.fixture.receipt_path,
                    self.fixture.output, destination, binary_contract_evidence=self.contract,
                    original_context=self.context, repository_root=self.fixture.root, environ={})
            held.assert_not_called()
        self.assertEqual(b"preserved", (original_destination / "keep").read_bytes())
        self.destination = self.fixture.work / "secret-carrier"
        with self.assertRaisesRegex(ValueError, "signing-secret"):
            self.call(environ={"CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY": ""})

    def test_symbolic_capture_member_rejected(self):
        self.prepare()
        record, = self.call()
        path = self.destination / record["capture"] / "original/worker/gradle.log"
        path.unlink()
        path.symlink_to(self.fixture.output / "original/worker/gradle.log")
        with self.assertRaises(ValueError):
            evidence.load_sdk_maven_evidence(self.destination)


if __name__ == "__main__":
    unittest.main()
