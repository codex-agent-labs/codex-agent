"""Read only digest-qualified members of an officially authenticated upload.

The caller freshly authenticates the original job/workflow/upload and supplies
member hashes from its fully authenticated reference envelope. This verifies
those member bytes, never asserts that an unread outer ZIP body was hashed,
and never admits a phase or replaces its signature/receipt/provenance gates.
"""
from contextlib import contextmanager
import hashlib
import io
import stat
import urllib.request
import zipfile

from products.inventory import require_integer, require_relative_path, require_sha256
from products.zip_central_directory import verify_zip64_end_record
from reuse import OriginBoundRedirectHandler


class _Archive(io.RawIOBase):
    def __init__(self, artifact, token):
        self.size = require_integer(artifact['size_in_bytes'], 'Reference archive size', 1)
        if self.size > 16 * 1024**3:
            raise ValueError('Reference archive exceeds the transport bound')
        identifier = require_integer(artifact['id'], 'Reference artifact ID', 1)
        require_sha256(artifact['digest'], 'Reference artifact digest')
        self.url = f'https://api.github.com/repos/codex-agent-labs/codex-agent/actions/artifacts/{identifier}/zip'
        if artifact.get('archive_download_url') != self.url:
            raise ValueError('Reference archive is outside the official artifact endpoint')
        self.token, self.position, self.etag, self.transferred = token, 0, None, 0
        self.opener = urllib.request.build_opener(OriginBoundRedirectHandler())

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=0):
        if whence not in (0, 1, 2):
            raise ValueError('Invalid reference archive seek')
        position = offset + (0 if whence == 0 else self.position if whence == 1 else self.size)
        if not 0 <= position <= self.size:
            raise ValueError('Reference archive seek is outside its immutable size')
        self.position = position
        return position

    def read(self, size=-1):
        if size < 0:
            size = self.size - self.position
        if not 0 <= size <= 32 * 1024**2:
            raise ValueError('Reference archive read exceeds the bounded request size')
        size = min(size, self.size - self.position)
        if not size:
            return b''
        begin, end = self.position, self.position + size - 1
        headers = {'Range': f'bytes={begin}-{end}', 'Accept': 'application/vnd.github+json',
                   'Authorization': f'Bearer {self.token}', 'X-GitHub-Api-Version': '2022-11-28'}
        if self.etag is not None:
            headers['If-Match'] = self.etag
        with self.opener.open(urllib.request.Request(self.url, headers=headers), timeout=60) as response:
            etag = response.headers.get('ETag')
            if (response.status != 206 or response.headers.get('Content-Range') !=
                    f'bytes {begin}-{end}/{self.size}' or not etag or self.etag not in (None, etag)):
                raise ValueError('Reference archive range identity changed or was not honored')
            raw = response.read(size + 1)
            if len(raw) != size:
                raise ValueError('Reference archive range was truncated or amplified')
            self.etag = etag
        self.position += size
        self.transferred += size
        return raw


@contextmanager
def open_reference_archive(artifact, token):
    stream = _Archive(artifact, token)
    try:
        tail_size = min(stream.size, 22 + 65535)
        stream.seek(stream.size - tail_size)
        tail = stream.read(tail_size)
        end = tail.rfind(b'PK\x05\x06')
        if end < 0 or end + 22 > len(tail) or end + 22 + int.from_bytes(tail[end+20:end+22], 'little') != len(tail):
            raise ValueError('Reference ZIP end record is malformed')
        if (int.from_bytes(tail[end+4:end+6], 'little') != 0
                or int.from_bytes(tail[end+6:end+8], 'little') != 0
                or tail[end+8:end+10] != tail[end+10:end+12]):
            raise ValueError('Reference ZIP cannot span multiple disks')
        count, size = verify_zip64_end_record(stream, stream.size, tail, end, tail_size,
            int.from_bytes(tail[end+10:end+12], 'little'), int.from_bytes(tail[end+12:end+16], 'little'))
        if count > 16384 or size > 32 * 1024**2:
            raise ValueError('Reference ZIP directory exceeds the fixed bounds')
        stream.seek(0)
        with zipfile.ZipFile(stream) as archive:
            names, folded = set(), set()
            total = 0
            for entry in archive.infolist():
                path = require_relative_path(entry.filename.rstrip('/') if entry.is_dir() else entry.filename,
                                             'Reference ZIP member')
                mode = stat.S_IFMT(entry.external_attr >> 16)
                if (path in names or path.casefold() in folded or entry.flag_bits & 1
                        or entry.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
                        or mode not in (0, stat.S_IFREG, stat.S_IFDIR)
                        or (mode == stat.S_IFDIR) != entry.is_dir() and mode != 0
                        or entry.file_size > 8 * 1024**3
                        or entry.file_size > max(1, entry.compress_size) * 200):
                    raise ValueError('Reference ZIP member is duplicate, unsafe or oversized')
                names.add(path)
                folded.add(path.casefold())
                total += entry.file_size
            if total > 16 * 1024**3 or len(archive.infolist()) != count:
                raise ValueError('Reference ZIP expanded inventory exceeds its fixed bound')
            yield archive, stream
    finally:
        stream.close()


def copy_reference_member(archive, name, destination, record):
    name = require_relative_path(name, 'Original reference member')
    entry = archive.getinfo(name)
    if entry.is_dir() or entry.file_size != record['bytes']:
        raise ValueError('Original reference member size differs from its immutable identity')
    digest = hashlib.sha256()
    total = 0
    destination.parent.mkdir(parents=True, exist_ok=True)
    with archive.open(entry) as incoming, destination.open('xb') as outgoing:
        while chunk := incoming.read(16 * 1024 * 1024):
            total += len(chunk)
            if total > record['bytes']:
                raise ValueError('Original reference member exceeds its immutable size')
            digest.update(chunk)
            outgoing.write(chunk)
    if total != record['bytes'] or 'sha256:' + digest.hexdigest() != record['sha256']:
        raise ValueError('Original reference member differs from its immutable digest')
