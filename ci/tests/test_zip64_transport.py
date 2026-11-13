from __future__ import annotations

from pathlib import Path
import stat
import struct
import tempfile
import unittest
import zipfile

from ci.products.inventory import verified_zip_contents


class Zip64TransportTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.archive = Path(self.temporary.name) / "transport.zip"
        info = zipfile.ZipInfo("payload.bin")
        info.create_system = 3
        info.external_attr = (stat.S_IFREG | 0o644) << 16
        with zipfile.ZipFile(self.archive, "w") as output:
            output.writestr(info, b"payload")
        original = self.archive.read_bytes()
        end = original[-22:]
        directory_size = struct.unpack_from("<I", end, 12)[0]
        directory_offset = struct.unpack_from("<I", end, 16)[0]
        self.record = struct.pack("<4sQHHIIQQQQ", b"PK\x06\x06", 44, 45, 45,
                                  0, 0, 1, 1, directory_size, directory_offset)
        locator = struct.pack("<4sIQI", b"PK\x06\x07", 0, len(original) - 22, 1)
        ordinary = bytearray(end)
        struct.pack_into("<HHII", ordinary, 8, 0xFFFF, 0xFFFF, 0xFFFFFFFF, 0xFFFFFFFF)
        self.archive.write_bytes(original[:-22] + self.record + locator + ordinary)

    def verify(self):
        return verified_zip_contents(self.archive, retained_paths=(),
            max_archive_bytes=1024, max_central_directory_bytes=1024,
            max_members=2, max_entry_bytes=1024, max_total_bytes=1024)

    def test_bounded_zip64_directory_is_accepted(self):
        records, _, _ = self.verify()
        self.assertEqual([{"relativePath": "payload.bin", "bytes": 7,
                           "sha256": records[0]["sha256"]}], records)

    def test_zip64_extensible_data_is_bounded_and_accepted(self):
        raw = self.archive.read_bytes()
        record_offset = raw.index(b"PK\x06\x06")
        locator_offset = raw.index(b"PK\x06\x07")
        record = bytearray(raw[record_offset:locator_offset])
        struct.pack_into("<Q", record, 4, 47)
        self.archive.write_bytes(raw[:record_offset] + record + b"ext" + raw[locator_offset:])
        self.assertEqual("payload.bin", self.verify()[0][0]["relativePath"])

    def test_excess_zip64_member_claim_fails_before_reader(self):
        raw = bytearray(self.archive.read_bytes())
        record_offset = raw.index(b"PK\x06\x06")
        struct.pack_into("<QQ", raw, record_offset + 24, 8193, 8193)
        self.archive.write_bytes(raw)
        with self.assertRaisesRegex(ValueError, "too many members"):
            self.verify()


if __name__ == "__main__":
    unittest.main()
