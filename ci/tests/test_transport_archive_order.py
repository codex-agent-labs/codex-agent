"""Outer upload order is not canonical product byte identity."""

from pathlib import Path
import tempfile
import unittest
import zipfile

from ci.products.inventory import sha256_bytes, verified_zip_contents


class TransportArchiveOrderTest(unittest.TestCase):
    def test_transport_preserves_unsorted_bytes_but_products_require_canonical_order(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "upload.zip"
            with zipfile.ZipFile(archive, "w") as output:
                output.writestr("z/file", b"z")
                output.writestr("a/file", b"a")
            original = archive.read_bytes()
            records, files, identity = verified_zip_contents(archive, require_sorted=False)
            self.assertEqual(["a/file", "z/file"], [row["relativePath"] for row in records])
            self.assertEqual({"a/file": b"a", "z/file": b"z"}, files)
            self.assertEqual(sha256_bytes(original), identity["sha256"])
            self.assertEqual(original, archive.read_bytes())
            for options in ({}, {"require_sorted": False, "canonical_stored": True}, {"require_sorted": 0}):
                with self.subTest(options=options), self.assertRaises(ValueError):
                    verified_zip_contents(archive, **options)

    def test_transport_order_exception_does_not_allow_unsafe_or_duplicate_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "upload.zip"
            for name in ("../escape", "/absolute", "a\\b", "same"):
                with zipfile.ZipFile(archive, "w") as output:
                    output.writestr("same", b"one")
                    with self.assertWarns(UserWarning) if name == "same" else self.subTest(name=name):
                        output.writestr(name, b"two")
                with self.subTest(name=name), self.assertRaises(ValueError):
                    verified_zip_contents(archive, require_sorted=False)

    def test_ancestor_file_conflicts_reject_in_both_transport_orders(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "upload.zip"
            for paths in (("a", "a/b"), ("a/b", "a")):
                with zipfile.ZipFile(archive, "w") as output:
                    for path in paths:
                        output.writestr(path, b"data")
                with self.subTest(paths=paths), self.assertRaisesRegex(ValueError, "descends from a file"):
                    verified_zip_contents(archive, require_sorted=False)


if __name__ == "__main__":
    unittest.main()
