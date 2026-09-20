"""Real structural carrier binding; opaque signatures confer no authentication."""

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci.products import sdk_apple_validation_inputs as carrier
from ci.products.inventory import canonical_json_bytes, regular_file_inventory, sha256_bytes, write_canonical_json
from ci.products.sdk_apple_validation_attestation import derive_apple_validation_attestation
from ci.tests.product_chain_support import output, write_receipt


class AppleValidationInputsTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="apple-validation-carrier-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.producer = {"repository": "owner/repository", "workflowPath": ".github/workflows/product-validation.yml",
                         "commit": "a" * 40, "tree": "b" * 40, "event": "pull_request",
                         "runId": 91, "runAttempt": 2, "pullRequest": 31}

    def entry(self, name="device", target="ios-arm64"):
        root = self.root / name
        capture = root / "capture"
        receipt_path = capture / "original/shard/phase-receipt.json"
        write_receipt(receipt_path, product="sdk", component="sdk-ios", phase="validation", target=target,
            version="0.8.0", version_identity="0.8.0", upstream=[], context={"producer": self.producer},
            outputs=[output("apple-validation-content", "outputs/validation/apple-validation.json", b"semantic fixture")])
        (capture / "plan").mkdir()
        (capture / "plan/impact-plan.json").write_bytes(b'{"fixture":"original plan"}\n')
        (capture / "transport.zip").write_bytes(b"opaque original ZIP; not verified by storage\n")
        (capture / "capture-transport.json").write_bytes(b'{"fixture":"unauthenticated recorded observation"}\n')
        (capture / "original/empty.log").write_bytes(b"")
        attestation = derive_apple_validation_attestation(capture, receipt_path.read_bytes(), {
            "algorithm": "ssh-ed25519", "namespace": "codex-agent-product-v1",
            "trustDomain": "development", "keyId": "fixture", "fingerprint": "sha256:" + "1" * 64})
        self.assertEqual(sha256_bytes(canonical_json_bytes(regular_file_inventory(capture, allow_empty=True))),
                         attestation["captureDigest"])
        write_canonical_json(root / carrier.ATTESTATION_NAME, attestation)
        (root / carrier.SIGNATURE_NAME).write_bytes(b"opaque signature: no verification claim\x00\xff")
        return root

    def test_capture_load_rebase_preserve_original_bytes_and_sort_both_targets(self):
        entries = [self.entry(), self.entry("simulator", "ios-simulator-arm64")]
        before = {entry: regular_file_inventory(entry, allow_empty=True) for entry in entries}
        destination = self.root / "artifact/evidence"
        records = carrier.capture_sdk_apple_validation_evidence(entries[::-1], destination)
        self.assertEqual(records, carrier.load_sdk_apple_validation_evidence(destination))
        self.assertEqual(sorted(record["receiptSha256"] for record in records), [record["receiptSha256"] for record in records])
        for entry in entries:
            digest = sha256_bytes((entry / "capture/original/shard/phase-receipt.json").read_bytes())
            record = next(record for record in records if record["receiptSha256"] == digest)
            self.assertEqual(before[entry], regular_file_inventory(destination / record["evidenceRoot"], allow_empty=True))
            self.assertEqual(before[entry], regular_file_inventory(entry, allow_empty=True))
        self.assertEqual([{**record, "evidenceRoot": "evidence/" + record["evidenceRoot"]} for record in records],
            carrier.rebase_sdk_apple_validation_records(records, destination, self.root / "artifact"))
        with self.assertRaises(ValueError):
            carrier.rebase_sdk_apple_validation_records(records, destination, self.root / "unrelated")

    def test_manifest_unknown_missing_duplicate_unsorted_and_path_escape_reject(self):
        destination = self.root / "carrier"
        records = carrier.capture_sdk_apple_validation_evidence(
            [self.entry(), self.entry("simulator", "ios-simulator-arm64")], destination)
        manifest = {"schemaVersion": 1, "records": records}
        changes = [lambda value: value.update(extra=True), lambda value: value.pop("schemaVersion"),
                   lambda value: value.update(schemaVersion=True),
                   lambda value: value["records"].append(copy.deepcopy(value["records"][0])),
                   lambda value: value["records"].reverse(),
                   lambda value: value["records"][0].update(evidenceRoot="../escape"),
                   lambda value: value["records"][0].update(target="ios"),
                   lambda value: value["records"][0].update(extra="unknown")]
        for index, mutate in enumerate(changes):
            value = copy.deepcopy(manifest)
            mutate(value)
            write_canonical_json(destination / carrier.REQUEST_NAME, value)
            with self.subTest(case=index), self.assertRaises(ValueError):
                carrier.load_sdk_apple_validation_evidence(destination)
        path = destination / carrier.REQUEST_NAME
        for raw in (json.dumps(manifest, indent=2).encode(),
                    b'{"schemaVersion":1,"schemaVersion":1,"records":[]}\n'):
            path.write_bytes(raw)
            with self.assertRaises(ValueError):
                carrier.load_sdk_apple_validation_evidence(destination)

    def test_rebase_two_enclosing_artifacts_checks_entries_without_parent_manifests(self):
        destination = self.root / "outer/inner/evidence"
        records = carrier.capture_sdk_apple_validation_evidence([self.entry()], destination)
        first = carrier.rebase_sdk_apple_validation_records(records, destination, self.root / "outer/inner")
        second = carrier.rebase_sdk_apple_validation_records(first, self.root / "outer/inner", self.root / "outer")
        self.assertEqual("evidence/" + records[0]["evidenceRoot"], first[0]["evidenceRoot"])
        self.assertEqual("inner/evidence/" + records[0]["evidenceRoot"], second[0]["evidenceRoot"])
        self.assertFalse((self.root / "outer/inner" / carrier.REQUEST_NAME).exists())
        self.assertFalse((self.root / "outer" / carrier.REQUEST_NAME).exists())
        self.assertEqual(records, carrier.load_sdk_apple_validation_evidence(destination))
        for field, value in (("target", "ios-simulator-arm64"), ("receiptSha256", "sha256:" + "0" * 64),
                             ("evidenceRoot", "../" + first[0]["evidenceRoot"]),
                             ("evidenceRoot", "/" + first[0]["evidenceRoot"]),
                             ("evidenceRoot", "./" + first[0]["evidenceRoot"]),
                             ("evidenceRoot", first[0]["evidenceRoot"].replace("evidence/", "evidence//"))):
            altered = [{**first[0], field: value}]
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                carrier.rebase_sdk_apple_validation_records(altered, self.root / "outer/inner", self.root / "outer")
        # Prefixed references are valid for routing, never in canonical storage.
        write_canonical_json(destination / carrier.REQUEST_NAME, {"schemaVersion": 1, "records": first})
        with self.assertRaises(ValueError):
            carrier.load_sdk_apple_validation_evidence(destination)

    def test_entry_missing_extra_bad_binding_and_symlink_reject_without_publication(self):
        for index, mutation in enumerate(("missing", "empty-sig", "extra", "capture-extra", "plan-extra",
                                          "receipt", "attestation", "symlink")):
            entry = self.entry(f"entry-{index}")
            if mutation == "missing":
                (entry / carrier.SIGNATURE_NAME).unlink()
            elif mutation == "empty-sig":
                (entry / carrier.SIGNATURE_NAME).write_bytes(b"")
            elif mutation == "extra":
                (entry / "unknown").mkdir()
            elif mutation == "capture-extra":
                (entry / "capture/unknown").mkdir()
            elif mutation == "plan-extra":
                (entry / "capture/plan/unknown").mkdir()
            elif mutation == "receipt":
                path = entry / "capture/original/shard/phase-receipt.json"
                value = json.loads(path.read_bytes())
                value["producer"]["runAttempt"] += 1
                write_canonical_json(path, value)
            elif mutation == "attestation":
                path = entry / carrier.ATTESTATION_NAME
                value = json.loads(path.read_bytes())
                value["target"] = "ios-simulator-arm64"
                write_canonical_json(path, value)
            else:
                path = entry / carrier.SIGNATURE_NAME
                path.unlink()
                path.symlink_to(entry / carrier.ATTESTATION_NAME)
            destination = self.root / f"output-{index}"
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                carrier.capture_sdk_apple_validation_evidence([entry], destination)
            self.assertFalse(destination.exists())

    def test_duplicate_overlap_existing_output_and_symlink_parent_reject(self):
        entry = self.entry()
        with self.assertRaises(ValueError):
            carrier.capture_sdk_apple_validation_evidence([entry, entry], self.root / "duplicate")
        self.assertFalse((self.root / "duplicate").exists())
        with self.assertRaises(ValueError):
            carrier.capture_sdk_apple_validation_evidence([entry], entry / "child")
        occupied = self.root / "occupied"
        occupied.mkdir()
        (occupied / "sentinel").write_bytes(b"keep")
        with self.assertRaises(ValueError):
            carrier.capture_sdk_apple_validation_evidence([entry], occupied)
        self.assertEqual(b"keep", (occupied / "sentinel").read_bytes())
        alias = self.root / "alias"
        alias.symlink_to(occupied, target_is_directory=True)
        with self.assertRaises(ValueError):
            carrier.capture_sdk_apple_validation_evidence([entry], alias / "output")
        self.assertFalse((occupied / "output").exists())

    def test_original_and_private_verifier_mutation_prevent_publication(self):
        for index, mutate_original in enumerate((True, False)):
            entry = self.entry(f"mutation-{index}")
            real_verify = carrier.verify_apple_validation_binding

            def verify(capture, raw, attestation):
                real_verify(capture, raw, attestation)
                target = entry / "capture/original/empty.log" if mutate_original else capture / "original/empty.log"
                target.write_bytes(b"late mutation")

            destination = self.root / f"mutation-output-{index}"
            with patch.object(carrier, "verify_apple_validation_binding", side_effect=verify):
                with self.subTest(original=mutate_original), self.assertRaises(ValueError):
                    carrier.capture_sdk_apple_validation_evidence([entry], destination)
            self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
