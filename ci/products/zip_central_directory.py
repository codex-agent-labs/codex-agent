"""Bounded ZIP64 central-directory preflight for imported archive verification.

This checks transport structure only; it does not define product payload bytes.
"""

import struct
from typing import BinaryIO


def verify_zip64_end_record(
    snapshot: BinaryIO,
    archive_size: int,
    tail: bytes,
    eocd: int,
    tail_size: int,
    member_count: int,
    central_size: int,
) -> tuple[int, int]:
    locator = eocd - 20
    if locator >= 0 and tail[locator:locator + 4] == b"PK\x06\x07":
        absolute_locator = archive_size - tail_size + locator
        _, disk, zip64_offset, disks = struct.unpack_from("<4sIQI", tail, locator)
        if disk != 0 or disks != 1 or zip64_offset + 56 > absolute_locator:
            raise ValueError("ZIP64 central-directory locator is unsafe")
        snapshot.seek(zip64_offset)
        record = snapshot.read(56)
        if len(record) != 56:
            raise ValueError("ZIP64 end-of-central-directory record is truncated")
        signature, record_size, _, _, disk, start_disk, count_disk, count, size, offset = struct.unpack(
            "<4sQHHIIQQQQ", record)
        if (signature != b"PK\x06\x06" or record_size < 44
                or zip64_offset + 12 + record_size != absolute_locator or disk != 0
                or start_disk != 0 or count_disk != count or offset + size != zip64_offset):
            raise ValueError("ZIP64 central directory is malformed")
        if ((member_count != 0xFFFF and member_count != count)
                or (central_size != 0xFFFFFFFF and central_size != size)):
            raise ValueError("ZIP64 central directory differs from the ordinary end record")
        return count, size
    if member_count == 0xFFFF or central_size == 0xFFFFFFFF:
        raise ValueError("ZIP64 central-directory locator is missing")
    return member_count, central_size
