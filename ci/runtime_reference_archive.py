"""Read only digest-qualified members of an officially authenticated upload.

The caller freshly authenticates the original job/workflow/upload and supplies
member hashes from its fully authenticated reference envelope. This verifies
those member bytes, never asserts that an unread outer ZIP body was hashed,
and never admits a phase or replaces its signature/receipt/provenance gates.
"""
from contextlib import contextmanager
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
import hashlib
import http.client
import io
import os
import socket
import stat
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

from products.inventory import require_integer, require_relative_path, require_sha256
from products.zip_central_directory import verify_zip64_end_record
from reuse import OriginBoundRedirectHandler
from runtime_reference_transport import token_for, report_api_error

_READ_AHEAD = 256 * 1024
_DOWNLOAD_BLOCK_BYTES = 32 * 1024 * 1024
_PARALLEL_DOWNLOAD_MIN_BYTES = 256 * 1024 * 1024


class _Archive(io.RawIOBase):
    def __init__(self, artifact, token, *, max_bytes=16 * 1024**3):
        if type(max_bytes) is not int or not 0 < max_bytes <= 32 * 1024**3:
            raise ValueError('Reference archive caller bound is unsupported')
        self.size = require_integer(artifact['size_in_bytes'], 'Reference archive size', 1)
        if self.size > max_bytes:
            raise ValueError('Reference archive exceeds the transport bound')
        identifier = require_integer(artifact['id'], 'Reference artifact ID', 1)
        require_sha256(artifact['digest'], 'Reference artifact digest')
        self.url = f'https://api.github.com/repos/codex-agent-labs/codex-agent/actions/artifacts/{identifier}/zip'
        if artifact.get('archive_download_url') != self.url:
            raise ValueError('Reference archive is outside the official artifact endpoint')
        self.token, self.position, self.etag, self.transferred = token, 0, None, 0
        self.download_url = self.url
        self.opener = urllib.request.build_opener(OriginBoundRedirectHandler())
        self.buffer_start, self.buffer = 0, b''

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
        offset = self.position - self.buffer_start
        if 0 <= offset and offset + size <= len(self.buffer):
            self.position += size
            return self.buffer[offset:offset + size]
        begin = self.position
        fetched = min(self.size - begin, max(size, _READ_AHEAD))
        raw = self._read_range(begin, fetched)
        self.buffer_start, self.buffer = begin, raw
        self.position += size
        self.transferred += fetched
        return raw[:size]

    def _read_range(self, begin, size):
        end = begin + size - 1
        headers = {'Range': f'bytes={begin}-{end}'}
        if self.etag is not None:
            headers['If-Match'] = self.etag
        def open_range(url):
            request_headers = dict(headers)
            if self.etag is not None:
                request_headers['If-Match'] = self.etag
            if url == self.url:
                request_headers.update({'Accept': 'application/vnd.github+json',
                    'Authorization': f'Bearer {token_for(url, self.token)}', 'X-GitHub-Api-Version': '2022-11-28'})
            return self.opener.open(urllib.request.Request(url, headers=request_headers), timeout=60)
        waited_for_reset = False
        for attempt in range(3):
            try:
                try:
                    response = open_range(self.download_url)
                except urllib.error.HTTPError as error:
                    if error.code != 403 or self.download_url == self.url:
                        raise
                    error.close()
                    # Refresh an expired signed link without changing identity.
                    response = open_range(self.url)
                with response:
                    etag = response.headers.get('ETag')
                    if (response.status != 206 or response.headers.get('Content-Range') !=
                            f'bytes {begin}-{end}/{self.size}' or not etag or self.etag not in (None, etag)):
                        raise ValueError('Reference archive range identity changed or was not honored')
                    resolved = getattr(response, 'geturl', lambda: self.url)()
                    parsed = urllib.parse.urlsplit(resolved)
                    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
                        raise ValueError('Reference archive download URL is unsafe')
                    self.download_url = resolved
                    self.etag = etag
                    raw = bytearray()
                    while len(raw) <= size:
                        chunk = response.read(size + 1 - len(raw))
                        if not chunk:
                            break
                        raw.extend(chunk)
                    if len(raw) > size:
                        raise ValueError(f'Reference archive range was amplified: received {len(raw)}, expected {size}')
                    if len(raw) < size:
                        raise http.client.IncompleteRead(bytes(raw), size - len(raw))
                    return bytes(raw)
            except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.IncompleteRead) as error:
                from product_reuse import _primary_rate_limit_delay
                from runtime_reference_transport import count
                delay = None if waited_for_reset else _primary_rate_limit_delay(error)
                transient = (isinstance(error, (TimeoutError, ConnectionError, http.client.IncompleteRead))
                    or isinstance(error, urllib.error.HTTPError) and error.code in {408, 500, 502, 503, 504}
                    or isinstance(error, urllib.error.URLError)
                    and isinstance(error.reason, (TimeoutError, ConnectionError, socket.gaierror)))
                if isinstance(error, urllib.error.HTTPError):
                    if delay is not None and attempt < 2:
                        report_api_error(error)
                    error.close()
                if not transient and delay is None or attempt == 2:
                    if isinstance(error, http.client.IncompleteRead):
                        raise ValueError(f'Reference archive range was truncated: received {len(error.partial)}, '
                                         f'expected {size}; range {begin}-{end}, attempts {attempt + 1}') from error
                    raise
                if delay is not None:
                    waited_for_reset = True
                    count('primaryRateLimitRetries')
                    count('primaryRateLimitWaitSeconds', delay)
                time.sleep(2 ** attempt if delay is None else delay)


def download_archive(artifact, token, destination, *, max_bytes):
    """Resume bounded ranges under one ETag, then hash the complete original."""
    if type(max_bytes) is not int or not 0 < max_bytes <= 32 * 1024**3:
        raise ValueError('Original archive exceeds its fixed transport bound')
    stream = _Archive(artifact, token, max_bytes=max(16 * 1024**3, max_bytes))
    if type(max_bytes) is not int or not 0 < stream.size <= max_bytes:
        raise ValueError('Original archive exceeds its fixed transport bound')
    # Exclusive creation preserves every pre-existing caller artifact.
    with destination.open('xb') as output:
        identity = os.fstat(output.fileno())
        try:
            digest = hashlib.sha256()
            def write(chunk):
                output.write(chunk)
                digest.update(chunk)

            # The first authenticated range pins the ETag and signed download URL.
            write(stream.read(min(_DOWNLOAD_BLOCK_BYTES, stream.size)))
            if stream.size < _PARALLEL_DOWNLOAD_MIN_BYTES:
                while stream.tell() < stream.size:
                    write(stream.read(min(_DOWNLOAD_BLOCK_BYTES, stream.size - stream.tell())))
            else:
                stream.buffer = b''
                def read_range(begin, url):
                    with _Archive(artifact, token, max_bytes=max(16 * 1024**3, max_bytes)) as reader:
                        reader.etag, reader.download_url = stream.etag, url
                        raw = reader._read_range(begin, min(_DOWNLOAD_BLOCK_BYTES, stream.size - begin))
                        return raw, reader.download_url

                # Four in-flight blocks bound memory; ordered writes preserve the full SHA.
                offsets = iter(range(stream.tell(), stream.size, _DOWNLOAD_BLOCK_BYTES))
                with ThreadPoolExecutor(max_workers=4) as pool:
                    pending = deque()
                    def submit():
                        begin = next(offsets, None)
                        if begin is not None:
                            pending.append(pool.submit(copy_context().run, read_range, begin, stream.download_url))
                    for _ in range(4):
                        submit()
                    while pending:
                        chunk, stream.download_url = pending.popleft().result()
                        write(chunk)
                        del chunk
                        submit()
            if 'sha256:' + digest.hexdigest() != artifact['digest']:
                raise ValueError('Original archive differs from its full transport digest')
            output.flush()
            os.fsync(output.fileno())
        except BaseException:
            output.close()
            try:
                current = destination.lstat()
                if (current.st_dev, current.st_ino) == (identity.st_dev, identity.st_ino):
                    destination.unlink()
            except FileNotFoundError:
                pass
            raise
        finally:
            stream.close()


@contextmanager
def open_reference_archive(artifact, token, *, max_bytes=16 * 1024**3, max_members=16_384):
    if type(max_members) is not int or max_members not in (16_384, 65_536):
        raise ValueError('Unsupported caller-owned reference ZIP member bound')
    stream = _Archive(artifact, token, max_bytes=max_bytes)
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
        if count > max_members or size > 32 * 1024**2:
            raise ValueError('Reference ZIP directory exceeds the fixed bounds')
        stream.seek(0)
        with zipfile.ZipFile(stream) as archive:
            _validate_reference_members(archive, max_bytes=max_bytes, max_members=max_members)
            if len(archive.infolist()) != count:
                raise ValueError('Reference ZIP expanded inventory exceeds its fixed bound')
            yield archive, stream
    finally:
        stream.close()


def _validate_reference_members(archive, *, max_bytes, max_members):
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
    if total > max_bytes or len(names) > max_members:
        raise ValueError('Reference ZIP expanded inventory exceeds its fixed bound')


class _MemberRange(io.RawIOBase):
    """Seek within a stored ZIP member without reading unrelated preceding bytes."""

    def __init__(self, stream, start, size):
        self.stream, self.start, self.size, self.position = stream, start, size, 0

    def seekable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=0):
        if whence not in (0, 1, 2):
            raise ValueError('Invalid stored member seek')
        position = offset + (0 if whence == 0 else self.position if whence == 1 else self.size)
        if not 0 <= position <= self.size:
            raise ValueError('Stored member seek exceeds its immutable size')
        self.position = position
        return position

    def read(self, size=-1):
        size = self.size - self.position if size < 0 else min(size, self.size - self.position)
        if size > 32 * 1024**2:
            raise ValueError('Stored member read exceeds the bounded request size')
        self.stream.seek(self.start + self.position)
        raw = self.stream.read(size)
        if len(raw) != size:
            raise ValueError('Stored member range was truncated')
        self.position += size
        return raw


@contextmanager
def open_stored_reference_archive(archive, name, *, expected_bytes):
    """Transport only: callers must independently authenticate every consumed leaf.

    Opening checks the local header through zipfile. The outer ETag and bounded
    offsets stay fixed; neither unread archive's whole digest/CRC is claimed.
    """
    entry = archive.getinfo(require_relative_path(name, 'Stored reference archive'))
    if (entry.is_dir() or entry.compress_type != zipfile.ZIP_STORED
            or entry.file_size != require_integer(expected_bytes, 'Stored archive size', 1)
            or entry.compress_size != expected_bytes):
        raise ValueError('Nested reference requires the exact stored archive size')
    with archive.open(entry):
        start = archive.fp.tell()
        with _MemberRange(archive.fp, start, expected_bytes) as stream, zipfile.ZipFile(stream) as nested:
            _validate_reference_members(nested, max_bytes=16 * 1024**3, max_members=16_384)
            yield nested


def copy_reference_member(archive, name, destination, record):
    name = require_relative_path(name, 'Original reference member')
    entry = archive.getinfo(name)
    if entry.is_dir() or entry.file_size != record['bytes']:
        raise ValueError('Original reference member size differs from its immutable identity')
    digest = hashlib.sha256()
    total = 0
    destination.parent.mkdir(parents=True, exist_ok=True)
    with archive.open(entry) as incoming, destination.open('xb') as outgoing:
        while chunk := incoming.read(_DOWNLOAD_BLOCK_BYTES):
            total += len(chunk)
            if total > record['bytes']:
                raise ValueError('Original reference member exceeds its immutable size')
            digest.update(chunk)
            outgoing.write(chunk)
    if total != record['bytes'] or 'sha256:' + digest.hexdigest() != record['sha256']:
        raise ValueError('Original reference member differs from its immutable digest')
