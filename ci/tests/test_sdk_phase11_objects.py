"""SDK candidate requires independently pinned original object bytes, not index alone."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci import sdk_phase11_objects as candidate
from ci.products.inventory import canonical_json_bytes, sha256_bytes, sha256_file
from ci.products.restore import object_relative_path
from ci.products.sdk_campaign_selection import SDK_CAMPAIGN_INSTANCES


class SdkPhase11ObjectsTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.capture = self.root / "phase10-index"
        (self.capture / "signed-pair").mkdir(parents=True)
        (self.capture / "replay-evidence/keys").mkdir(parents=True)
        (self.capture / "signed-pair/product-index.json").write_bytes(b"signed index\n")
        (self.capture / "signed-pair/product-index.sig").write_bytes(b"signature\n")
        (self.capture / "replay-evidence/product-signing-keys.json").write_bytes(b"keyring\n")
        (self.capture / "replay-evidence/keys/release.pub").write_bytes(b"public\n")
        self.objects = self.root / "objects"
        self.objects.mkdir()
        self.checkout = self.root / "landed"
        self.checkout.mkdir()
        self.destination = self.root / "candidate"
        self.rows = []
        self.entries = []
        self.receipts = {}
        for position, instance in enumerate(sorted(SDK_CAMPAIGN_INSTANCES)):
            build_key = sha256_bytes(f"build {position}".encode())
            receipt_sha = sha256_bytes(f"receipt {position}".encode())
            relative = object_relative_path(build_key, receipt_sha)
            archive = self.objects / relative
            archive.parent.mkdir(parents=True, exist_ok=True)
            archive.write_bytes(f"original object {position}\n".encode())
            row = {"product": instance.product, "component": instance.component,
                "phase": instance.phase, "target": instance.target,
                "buildKey": build_key, "receiptSha256": receipt_sha,
                "objectSha256": sha256_file(archive), "relativePath": relative}
            outputs = [{"kind": "package", "relativePath": "outputs/package.zip",
                "bytes": 1, "sha256": sha256_bytes(b"x")}]
            self.rows.append(row)
            self.entries.append({**{field: row[field] for field in (
                "product", "component", "phase", "target", "buildKey", "receiptSha256")},
                "productVersion": "0.8.0", "outputs": outputs})
            self.receipts[relative] = {"receiptBytes": f"receipt {position}".encode(),
                "receipt": {"outputs": outputs, "productVersion": "0.8.0"},
                "objectBytes": archive.stat().st_size}
        self.pins = self.root / "object-pins.json"
        self._write_pins()
        self.index_sha = sha256_file(self.capture / "signed-pair/product-index.json")

    def _write_pins(self, rows=None):
        self.pins.write_bytes(canonical_json_bytes({"schemaVersion": 1,
            "signedIndexSha256": sha256_bytes(b"signed index\n"),
            "objects": self.rows if rows is None else rows}))

    def forward(self, **changes):
        index = {"entries": self.entries}

        def copy_index(source, destination, **_pins):
            candidate.snapshot_regular_tree(source, destination)

        def verify_object(archive, *, build_key, receipt_sha256, object_sha256):
            self.assertTrue(archive.is_file())
            if object_sha256 != sha256_file(archive):
                raise ValueError("SDK phase object differs from approved bytes")
            row = self.receipts[archive.relative_to(self.objects).as_posix()]
            self.assertEqual(receipt_sha256, sha256_bytes(row["receiptBytes"]))
            return row

        args = dict(expected_object_pins_sha256=sha256_file(self.pins),
            landed_repository=self.checkout, expected_index_sha256=self.index_sha,
            expected_validation_tree="a" * 40)
        with patch.object(candidate, "forward_verified_sdk_phase10_bytes",
                          side_effect=copy_index) as index_copy, \
                patch.object(candidate, "verify_release_product_index",
                             return_value=(index, b"signed index\n")), \
                patch.object(candidate, "verify_object", side_effect=verify_object), \
                patch.object(candidate, "_landed_tree", return_value="a" * 40):
            result = candidate.forward_verified_sdk_phase10_objects(
                self.capture, self.objects, self.pins, self.destination,
                **{**args, **changes})
        return result, index_copy

    def test_all_62_original_objects_and_index_forward_exactly(self):
        result, copy_index = self.forward()
        self.assertEqual(62, result["objectCount"])
        copy_index.assert_called_once()
        self.assertEqual((self.capture / "signed-pair/product-index.json").read_bytes(),
            (self.destination / "signed-campaign/signed-pair/product-index.json").read_bytes())
        for row in self.rows:
            self.assertEqual((self.objects / row["relativePath"]).read_bytes(),
                (self.destination / "objects" / row["relativePath"]).read_bytes())
        self.assertEqual(self.pins.read_bytes(),
                         (self.destination / "object-pins.json").read_bytes())

    def test_missing_or_self_selected_pins_cannot_forward(self):
        self._write_pins([])
        with self.assertRaisesRegex(ValueError, "62-phase"):
            self.forward()
        self.assertFalse(self.destination.exists())
        self._write_pins()
        with self.assertRaisesRegex(ValueError, "independent S1048 approval"):
            self.forward(expected_object_pins_sha256=sha256_bytes(b"not approved"))
        self.assertFalse(self.destination.exists())

    def test_archive_tamper_and_wrong_signed_receipt_reject(self):
        archive = self.objects / self.rows[0]["relativePath"]
        archive.write_bytes(b"tampered archive\n")
        with self.assertRaisesRegex(ValueError, "approved bytes"):
            self.forward()
        self.assertFalse(self.destination.exists())
        archive.write_bytes(b"original object 0\n")
        changed = [dict(row) for row in self.rows]
        changed[0]["receiptSha256"] = sha256_bytes(b"wrong receipt")
        self._write_pins(changed)
        with self.assertRaisesRegex(ValueError, "pin path differs"):
            self.forward()
        self.assertFalse(self.destination.exists())

    def test_source_mutation_after_snapshot_leaves_no_candidate(self):
        original = candidate.snapshot_regular_tree

        def mutate(source, destination):
            original(source, destination)
            if source == self.objects:
                (source / self.rows[0]["relativePath"]).write_bytes(b"late source change\n")

        with patch.object(candidate, "snapshot_regular_tree", side_effect=mutate), \
                self.assertRaisesRegex(ValueError, "changed before publication"):
            self.forward()
        self.assertFalse(self.destination.exists())


if __name__ == "__main__":
    unittest.main()
