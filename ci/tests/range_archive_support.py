"""In-memory stand-in for the official ranged artifact reader (tests only)."""

from contextlib import contextmanager
import io
from unittest.mock import patch


class BytesRangeArchive(io.RawIOBase):
    """Same surface as runtime_reference_archive._Archive over fixed bytes."""

    def __init__(self, owner, artifact, token, *, max_bytes=16 * 1024**3):
        self.owner, self.raw = owner, owner.raw
        self.size = artifact["size_in_bytes"]
        self.position, self.etag, self.transferred = 0, None, 0
        self.download_url = artifact["archive_download_url"]
        self.buffer_start, self.buffer = 0, b""
        owner.range_readers += 1

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=0):
        self.position = offset + (0 if whence == 0 else self.position if whence == 1 else self.size)
        return self.position

    def read(self, size=-1):
        size = self.size - self.position if size < 0 else min(size, self.size - self.position)
        raw = self._read_range(self.position, size) if size else b""
        self.position += len(raw)
        return raw

    def _read_range(self, begin, size):
        etag = self.owner.range_etag
        if self.etag not in (None, etag):
            raise ValueError("Reference archive range identity changed or was not honored")
        self.etag = etag
        self.owner.range_bytes += size
        return self.owner.range_body(begin, size)


@contextmanager
def official_ranges(owner):
    """Patch the ranged reader; ``owner`` provides raw, range_etag and range_body."""
    import runtime_reference_archive
    owner.range_readers, owner.range_bytes = 0, 0
    if not hasattr(owner, "range_etag"):
        owner.range_etag = '"fixture-etag"'
    if not hasattr(owner, "range_body"):
        owner.range_body = lambda begin, size: owner.raw[begin:begin + size]
    with patch.object(runtime_reference_archive, "_Archive",
                      side_effect=lambda artifact, token, **kwargs: BytesRangeArchive(owner, artifact, token, **kwargs)):
        yield
