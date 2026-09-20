"""Raw ZIP inventory fixtures only; no compiler or run authentication is asserted."""

from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock
import warnings
import zipfile

from ci.products.inventory import sha256_bytes
from ci.products import sdk_apple_validation_evidence as evidence


class SdkAppleValidationEvidenceTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="apple-validation-zip-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.archive = self.root / "raw.zip"
        self.members = [("compiler/execution.json", b"original command\n"),
                        ("compiler/stderr.bin", b""), ("compiler/stdout.bin", b"\x00\xff\r\n"),
                        ("xctest/attempt-0/stdout.bin", b""),
                        ("xctest/attempt-1/stdout.bin", b"original retry\n")]

    def write(self, members, *, mode=stat.S_IFREG | 0o644):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)  # Deliberately duplicated ZIP-member fixture.
            with zipfile.ZipFile(self.archive, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for name, raw in members:
                    entry = zipfile.ZipInfo(name)
                    entry.create_system = 3
                    entry.external_attr = mode << 16
                    archive.writestr(entry, raw)

    def verify(self, roots=("compiler", "xctest")):
        return evidence.verify_apple_validation_evidence_archive(self.archive, roots)

    def test_preserves_empty_binary_and_retry_stream_inventory_without_rewriting_archive(self):
        self.write(self.members)
        before = self.archive.read_bytes()
        expected = [{"relativePath": name, "bytes": len(raw), "sha256": sha256_bytes(raw)}
                    for name, raw in self.members]
        self.assertEqual(expected, self.verify())
        self.assertEqual(expected, self.verify(("xctest", "compiler")))
        self.assertEqual(before, self.archive.read_bytes())
        self.assertEqual([self.archive], list(self.root.iterdir()))

    def test_roots_require_unique_safe_single_component_prefixes_before_archive_read(self):
        for roots in ((), [], "compiler", ("compiler", "compiler"), ("",), (None,), ("a/b",),
                      ("..",), (".",), ("/compiler",), ("a\\b",), ("C:raw",), ("bad\nroot",)):
            with self.subTest(roots=roots), mock.patch.object(evidence, "verified_zip_contents") as reader:
                with self.assertRaises(ValueError):
                    self.verify(roots)
                reader.assert_not_called()

    def test_missing_extra_empty_archive_and_root_file_instead_of_prefix_reject(self):
        for members in ([], self.members[:3], self.members + [("zzextra/raw", b"extra")],
                        [("compiler", b"not a directory prefix"), ("xctest/raw", b"test")]):
            with self.subTest(members=members):
                self.write(members)
                with self.assertRaises(ValueError):
                    self.verify()
        # A root is nonempty when it has a file, even if the original stream is empty.
        self.write([("compiler/stderr", b"")])
        self.assertEqual(0, self.verify(("compiler",))[0]["bytes"])

    def test_existing_reader_rejects_duplicate_unsorted_traversal_directory_and_file_ancestor_members(self):
        invalid = [
            [("compiler/raw", b"a"), ("compiler/raw", b"b")],
            [("compiler/z", b"z"), ("compiler/a", b"a")],
            [("compiler/../escape", b"x")], [("/compiler/raw", b"x")],
            [("compiler\\raw", b"x")], [("compiler/", b"")],
            [("compiler/a", b"a"), ("compiler/a/b", b"b")],
            [("compiler/a/b", b"b"), ("compiler/a", b"a")],
        ]
        for members in invalid:
            with self.subTest(members=members):
                self.write(members)
                with self.assertRaises(ValueError):
                    self.verify(("compiler",))
        for mode in (stat.S_IFLNK | 0o777, stat.S_IFIFO | 0o600):
            with self.subTest(mode=mode):
                self.write([("compiler/raw", b"target")], mode=mode)
                with self.assertRaises(ValueError):
                    self.verify(("compiler",))

    def test_existing_archive_path_safety_and_finite_limits_are_retained(self):
        self.write(self.members)
        alias = self.root / "alias.zip"
        alias.symlink_to(self.archive)
        with self.assertRaises(ValueError):
            evidence.verify_apple_validation_evidence_archive(alias, ("compiler", "xctest"))
        with mock.patch.dict(evidence.OBJECT_ZIP_LIMITS, {"max_members": 1}):
            with self.assertRaisesRegex(ValueError, "too many members"):
                self.verify()
        with mock.patch.dict(evidence.OBJECT_ZIP_LIMITS, {"max_entry_bytes": 1}):
            with self.assertRaisesRegex(ValueError, "too large"):
                self.verify()


if __name__ == "__main__":
    unittest.main()
