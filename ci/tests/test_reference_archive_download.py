"""Per-open transport reuse retains immutable range and member authentication."""
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import urllib.error
import zipfile
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import runtime_reference_archive as transport


class ReferenceDownloadTest(unittest.TestCase):
    def test_parallel_full_archive_bounds_work_and_preserves_order_etag_and_cleanup(self):
        from threading import Barrier, Lock
        from products.inventory import sha256_bytes
        raw = bytes(range(64))
        artifact = dict(id=1, size_in_bytes=len(raw), digest=sha256_bytes(raw),
            archive_download_url='https://api.github.com/repos/codex-agent-labs/codex-agent/actions/artifacts/1/zip')
        for defect in (None, 'etag', 'digest'):
            barrier, lock = Barrier(4), Lock()
            active = peak = 0
            requests = []
            def open_range(request, timeout):
                nonlocal active, peak
                begin, end = map(int, request.get_header('Range')[6:].split('-'))
                with lock:
                    requests.append(request)
                    active += 1
                    peak = max(peak, active)
                try:
                    if 8 <= begin < 40:
                        barrier.wait(timeout=10)  # Four independent ranges must overlap.
                    if begin:
                        self.assertEqual('"same"', request.get_header('If-match'))
                        self.assertIsNone(request.get_header('Authorization'))
                    response = io.BytesIO(raw[begin:end + 1])
                    response.status = 206
                    response.headers = {'ETag': '"other"' if defect == 'etag' and begin == 8 else '"same"',
                                        'Content-Range': f'bytes {begin}-{end}/{len(raw)}'}
                    response.geturl = lambda: 'https://blob.example.invalid/pinned-download'
                    return response
                finally:
                    with lock:
                        active -= 1
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as temporary, \
                    mock.patch.object(transport.urllib.request, 'build_opener') as factory, \
                    mock.patch.object(transport, '_READ_AHEAD', 0), \
                    mock.patch.object(transport, '_DOWNLOAD_BLOCK_BYTES', 8), \
                    mock.patch.object(transport, '_PARALLEL_DOWNLOAD_MIN_BYTES', 0):
                factory.return_value.open.side_effect = open_range
                output = Path(temporary) / 'original.zip'
                selected = {**artifact, 'digest': 'sha256:' + '0' * 64} if defect == 'digest' else artifact
                if defect:
                    with self.assertRaisesRegex(ValueError, 'identity changed|full transport digest'):
                        transport.download_archive(selected, 'exact-token', output, max_bytes=len(raw))
                    self.assertFalse(output.exists())
                else:
                    transport.download_archive(selected, 'exact-token', output, max_bytes=len(raw))
                    self.assertEqual(raw, output.read_bytes())
                    self.assertEqual([f'bytes={begin}-{begin+7}' for begin in range(0, 64, 8)],
                                     sorted((r.get_header('Range') for r in requests),
                                            key=lambda r: int(r[6:].split('-')[0])))
                self.assertEqual(4, peak)
                self.assertEqual(artifact['archive_download_url'], requests[0].full_url)
                self.assertEqual('Bearer exact-token', requests[0].get_header('Authorization'))

    def test_nested_stored_archive_reads_only_pinned_leaves_and_keeps_digest_and_path_gates(self):
        from ci.tests.test_runtime_reference_transport import RangeOpener
        from products.inventory import sha256_bytes
        for defect in (None, "digest", "compressed", "unsafe", "duplicate", "symlink"):
            import stat
            import warnings
            inner = io.BytesIO()
            body = b"original executed parity receipt"
            with zipfile.ZipFile(inner, "w") as archive, warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                archive.writestr("unconsumed.bin", b"x" * (8 * 1024**2))
                name = "../report.json" if defect == "unsafe" else "report.json"
                entry = zipfile.ZipInfo(name)
                if defect == "symlink":
                    entry.external_attr = (stat.S_IFLNK | 0o777) << 16
                archive.writestr(entry, body)
                if defect == "duplicate":
                    archive.writestr(name, body)
            outer = io.BytesIO()
            with zipfile.ZipFile(outer, "w") as archive:
                archive.writestr("execution.zip", inner.getvalue(), compress_type=(
                    zipfile.ZIP_DEFLATED if defect == "compressed" else zipfile.ZIP_STORED))
            raw = outer.getvalue()
            artifact = dict(id=1, size_in_bytes=len(raw), digest=sha256_bytes(raw),
                archive_download_url="https://api.github.com/repos/codex-agent-labs/codex-agent/actions/artifacts/1/zip")
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as temporary, \
                    mock.patch.object(transport.urllib.request, "build_opener",
                        return_value=RangeOpener({1: raw})):
                def consume():
                    with transport.open_reference_archive(artifact, "fixture") as (archive, stream), \
                            transport.open_stored_reference_archive(archive, "execution.zip",
                                expected_bytes=len(inner.getvalue())) as nested:
                        output = Path(temporary) / "report.json"
                        transport.copy_reference_member(nested, "report.json", output, {
                            "bytes": len(body), "sha256": sha256_bytes(body if defect != "digest" else b"wrong")})
                        self.assertEqual(body, output.read_bytes())
                        self.assertLess(stream.transferred, 1024**2)
                if defect:
                    with self.assertRaises(ValueError):
                        consume()
                else:
                    consume()

    def test_large_directory_requires_explicit_bounded_policy_and_keeps_path_checks(self):
        from ci.tests.test_runtime_reference_transport import RangeOpener
        from products.inventory import sha256_bytes
        for count, unsafe in ((16_385, False), (65_537, False), (1, True)):
            data = io.BytesIO()
            with zipfile.ZipFile(data, 'w') as archive:
                for number in range(count):
                    archive.writestr('../escape' if unsafe else f'evidence/{number}', b'')
            raw = data.getvalue()
            artifact = dict(id=1, size_in_bytes=len(raw), digest=sha256_bytes(raw),
                archive_download_url='https://api.github.com/repos/codex-agent-labs/codex-agent/actions/artifacts/1/zip')
            with self.subTest(count=count, unsafe=unsafe), \
                    mock.patch.object(transport.urllib.request, 'build_opener', return_value=RangeOpener({1: raw})):
                with self.assertRaises(ValueError), transport.open_reference_archive(artifact, 'fixture'):
                    self.fail('Default bounds and unsafe paths must still reject')
                if count <= 65_536 and not unsafe:
                    with transport.open_reference_archive(artifact, 'fixture', max_members=65_536) as (archive, _):
                        self.assertEqual(count, len(archive.infolist()))
                else:
                    with self.assertRaises(ValueError), transport.open_reference_archive(
                            artifact, 'fixture', max_members=65_536):
                        self.fail('Explicit policy must retain fixed bounds and safe paths')
        for bound in (True, 0, 65_537):
            with self.subTest(bound=bound), mock.patch.object(transport, '_Archive') as fetch, \
                    self.assertRaisesRegex(ValueError, 'caller-owned'):
                with transport.open_reference_archive(artifact, 'fixture', max_members=bound):
                    pass
            fetch.assert_not_called()

    def test_primary_quota_wait_retries_only_the_same_authenticated_range(self):
        from ci.tests.test_runtime_reference_transport import RangeOpener
        from products.inventory import sha256_bytes
        raw = b'original bytes'
        artifact = dict(id=1, size_in_bytes=len(raw), digest=sha256_bytes(raw),
            archive_download_url='https://api.github.com/repos/codex-agent-labs/codex-agent/actions/artifacts/1/zip')
        headers = {'x-ratelimit-limit': '5000', 'x-ratelimit-remaining': '0',
                   'x-ratelimit-used': '5000', 'x-ratelimit-reset': '1120'}
        for repeated in (False, True):
            requests = []
            opener = RangeOpener({1: raw})
            def open_range(request, timeout):
                requests.append(request)
                if repeated or len(requests) == 1:
                    raise urllib.error.HTTPError(request.full_url, 403, 'limited',
                        headers, io.BytesIO(b'private body secret'))
                return opener.open(request, timeout)
            with mock.patch.object(transport.urllib.request, 'build_opener') as factory, \
                    mock.patch.object(transport.time, 'time', return_value=1000), \
                    mock.patch.object(transport.time, 'sleep') as sleep, \
                    mock.patch.object(sys, 'stderr', new_callable=io.StringIO) as log:
                factory.return_value.open.side_effect = open_range
                stream = transport._Archive(artifact, 'secret')
                if repeated:
                    with self.assertRaises(urllib.error.HTTPError):
                        stream.read(len(raw))
                    self.assertEqual(0, stream.tell())
                else:
                    self.assertEqual(raw, stream.read(len(raw)))
                self.assertEqual(2, len(requests))
                self.assertEqual(requests[0].full_url, requests[1].full_url)
                self.assertEqual(requests[0].headers, requests[1].headers)
                sleep.assert_called_once_with(122)
                self.assertNotIn('secret', log.getvalue())
                self.assertNotIn('private body', log.getvalue())
                self.assertNotIn(artifact['archive_download_url'], log.getvalue())
                diagnostics = [json.loads(line.removeprefix('github-api-error '))
                               for line in log.getvalue().splitlines()]
                self.assertEqual([{'status': 403, 'messageKind': 'unclassified',
                    'rateLimit': {name: int(value) for name, value in headers.items()}}], diagnostics)

    def test_large_stored_member_uses_two_bounded_ranges_and_keeps_exact_digest(self):
        from ci.tests.test_runtime_reference_transport import RangeOpener
        from products.inventory import sha256_bytes
        body = b'p' * (33 * 1024**2)
        data = io.BytesIO()
        with zipfile.ZipFile(data, 'w', compression=zipfile.ZIP_STORED) as archive:
            archive.writestr('object.zip', body)
        raw = data.getvalue()
        artifact = dict(id=1, size_in_bytes=len(raw), digest=sha256_bytes(raw),
            archive_download_url='https://api.github.com/repos/codex-agent-labs/codex-agent/actions/artifacts/1/zip')
        for corrupt in (False, True):
            opener = RangeOpener({1: raw})
            sizes = []
            def open_range(request, timeout):
                first, last = map(int, request.get_header('Range')[6:].split('-'))
                sizes.append(last - first + 1)
                return opener.open(request, timeout)
            with tempfile.TemporaryDirectory() as temporary, \
                    mock.patch.object(transport.urllib.request, 'build_opener') as factory:
                factory.return_value.open.side_effect = open_range
                destination = Path(temporary) / 'object.zip'
                row = dict(bytes=len(body), sha256='sha256:' + '0' * 64 if corrupt else sha256_bytes(body))
                with transport.open_reference_archive(artifact, 'fixture') as (archive, stream):
                    if corrupt:
                        with self.assertRaisesRegex(ValueError, 'immutable digest'):
                            transport.copy_reference_member(archive, 'object.zip', destination, row)
                    else:
                        transport.copy_reference_member(archive, 'object.zip', destination, row)
                        self.assertEqual(body, destination.read_bytes())
                    self.assertEqual(2, len([size for size in sizes if size >= 1024**2]))
                    self.assertLessEqual(max(sizes), 32 * 1024**2)

    def test_observed_apple_package_envelope_needs_explicit_bounded_caller_policy(self):
        artifact = dict(id=1, size_in_bytes=22117834439, digest='sha256:'+'a'*64,
            archive_download_url='https://api.github.com/repos/codex-agent-labs/codex-agent/actions/artifacts/1/zip')
        with self.assertRaisesRegex(ValueError, 'transport bound'):
            transport._Archive(artifact, 'fixture')
        with mock.patch.object(transport.urllib.request, 'build_opener'):
            stream = transport._Archive(artifact, 'fixture', max_bytes=32*1024**3)
            self.assertEqual(22117834439, stream.size)
            stream.close()
        for bound in (True, 0, 32*1024**3+1):
            with self.subTest(bound=bound), self.assertRaisesRegex(ValueError, 'caller bound'):
                transport._Archive(artifact, 'fixture', max_bytes=bound)

    def test_full_original_retries_only_interrupted_range_and_checks_entire_digest(self):
        from ci.tests.test_runtime_reference_transport import RangeOpener
        from products.inventory import sha256_bytes
        import http.client
        raw = b'original retained artifact bytes'
        artifact = dict(id=1, size_in_bytes=len(raw), digest=sha256_bytes(raw),
            archive_download_url='https://api.github.com/repos/codex-agent-labs/codex-agent/actions/artifacts/1/zip')
        for corrupt in (False, True):
            ranges = []
            opener = RangeOpener({1: raw})
            def open_range(request, timeout):
                ranges.append(request.get_header('Range'))
                if len(ranges) == 3:
                    raise http.client.IncompleteRead(b'partial')
                return opener.open(request, timeout)
            with tempfile.TemporaryDirectory() as temporary, \
                    mock.patch.object(transport.urllib.request, 'build_opener') as factory, \
                    mock.patch.object(transport, '_READ_AHEAD', 0), \
                    mock.patch.object(transport, '_DOWNLOAD_BLOCK_BYTES', 8), \
                    mock.patch.object(transport.time, 'sleep'):
                factory.return_value.open.side_effect = open_range
                target = Path(temporary) / 'original.zip'
                selected = {**artifact, 'digest': 'sha256:' + '0' * 64} if corrupt else artifact
                if corrupt:
                    with self.assertRaisesRegex(ValueError, 'full transport digest'):
                        transport.download_archive(selected, 'fixture', target, max_bytes=len(raw))
                    self.assertFalse(target.exists())
                else:
                    transport.download_archive(selected, 'fixture', target, max_bytes=len(raw))
                    self.assertEqual(raw, target.read_bytes())
                    with self.assertRaises(FileExistsError):
                        transport.download_archive(selected, 'fixture', target, max_bytes=len(raw))
                    self.assertEqual(raw, target.read_bytes())
                self.assertEqual(['bytes=0-7', 'bytes=8-15', 'bytes=16-23', 'bytes=16-23',
                                  'bytes=24-31'], ranges)

    def test_download_link_reuse_refresh_and_fail_closed(self):
        official = 'https://api.github.com/repos/codex-agent-labs/codex-agent/actions/artifacts/1/zip'
        blob = 'https://blob.example.invalid/signed-download'
        artifact = {'id': 1, 'size_in_bytes': 4, 'digest': 'sha256:' + 'a' * 64,
                    'archive_download_url': official}
        requests = []
        changed = None
        expired = False

        def open_range(request, timeout):
            nonlocal expired
            requests.append(request)
            if expired and request.full_url == blob:
                expired = False
                raise urllib.error.HTTPError(blob, 403, 'expired', {}, io.BytesIO())
            begin, end = map(int, request.get_header('Range')[6:].split('-'))
            response = io.BytesIO(b'abcd'[begin:end + 1])
            response.status = 206
            response.headers = {'ETag': changed or '"same"',
                                'Content-Range': f'bytes {begin}-{end}/4'}
            response.geturl = lambda: blob
            return response

        with mock.patch.object(transport, '_READ_AHEAD', 0), \
                mock.patch.object(transport.urllib.request, 'build_opener') as factory:
            factory.return_value.open.side_effect = open_range
            stream = transport._Archive(artifact, 'secret')
            self.assertEqual(b'a', stream.read(1))
            self.assertEqual(b'b', stream.read(1))
            self.assertEqual([official, blob], [r.full_url for r in requests])
            self.assertEqual('Bearer secret', requests[0].get_header('Authorization'))
            self.assertIsNone(requests[1].get_header('Authorization'))
            self.assertEqual('"same"', requests[1].get_header('If-match'))
            expired = True
            self.assertEqual(b'c', stream.read(1))
            self.assertEqual([blob, official], [r.full_url for r in requests[-2:]])
            changed = '"different"'
            with self.assertRaisesRegex(ValueError, 'identity changed'):
                stream.read(1)
            self.assertEqual(3, stream.position)
            for request in requests:
                if request.full_url == blob:
                    self.assertIsNone(request.get_header('Authorization'))

    def test_read_ahead_and_transient_retry_preserve_every_member_identity(self):
        from ci.tests.test_runtime_reference_transport import RangeOpener
        from products.inventory import sha256_bytes
        data = io.BytesIO()
        bodies = {f'member-{i:03d}': bytes([i]) * 1024 for i in range(100)}
        with zipfile.ZipFile(data, 'w', compression=zipfile.ZIP_STORED) as archive:
            for name, body in bodies.items():
                archive.writestr(name, body)
        raw = data.getvalue()
        artifact = dict(id=1, size_in_bytes=len(raw), digest=sha256_bytes(raw),
            archive_download_url='https://api.github.com/repos/codex-agent-labs/codex-agent/actions/artifacts/1/zip')
        for failure in (None, 503):
            opener = RangeOpener({1: raw})
            calls = []
            def open_range(request, timeout):
                calls.append(request.get_header('Range'))
                if failure and len(calls) == 2:
                    raise urllib.error.HTTPError(request.full_url, failure, 'temporary', {}, io.BytesIO())
                return opener.open(request, timeout)
            with tempfile.TemporaryDirectory() as temporary, \
                    mock.patch.object(transport.urllib.request, 'build_opener') as factory, \
                    mock.patch.object(transport.time, 'sleep') as sleep:
                factory.return_value.open.side_effect = open_range
                with transport.open_reference_archive(artifact, 'unused-fixture-token') as (archive, stream):
                    for name, body in bodies.items():
                        destination = Path(temporary) / name
                        transport.copy_reference_member(archive, name, destination,
                                                       dict(bytes=len(body), sha256=sha256_bytes(body)))
                        self.assertEqual(body, destination.read_bytes())
                self.assertLessEqual(len(calls), 3)
                self.assertLessEqual(stream.transferred, len(raw) + 65557)
                if failure:
                    self.assertEqual(calls[1], calls[2])
                    sleep.assert_called_once_with(1)
                else:
                    sleep.assert_not_called()

    def test_retries_are_bounded_and_invalid_responses_never_retry(self):
        artifact = dict(id=1, size_in_bytes=4, digest='sha256:' + 'a' * 64,
            archive_download_url='https://api.github.com/repos/codex-agent-labs/codex-agent/actions/artifacts/1/zip')
        with mock.patch.object(transport.urllib.request, 'build_opener') as factory, \
                mock.patch.object(transport.time, 'sleep') as sleep:
            factory.return_value.open.side_effect = lambda request, **kwargs: (_ for _ in ()).throw(
                urllib.error.HTTPError(request.full_url, 503, 'unavailable', {}, io.BytesIO()))
            stream = transport._Archive(artifact, 'unused-fixture-token')
            with self.assertRaises(urllib.error.HTTPError):
                stream.read(4)
            self.assertEqual(3, factory.return_value.open.call_count)
            self.assertEqual(0, stream.tell())
            self.assertEqual([mock.call(1), mock.call(2)], sleep.call_args_list)
            for content, content_range, attempts in ((b'ab', 'bytes 0-3/4', 3),
                    (b'abcde', 'bytes 0-3/4', 1), (b'abcd', 'bytes 0-2/4', 1)):
                def response_for_range(*args, **kwargs):
                    response = io.BytesIO(content)
                    response.status = 206
                    response.headers = {'ETag': '"same"', 'Content-Range': content_range}
                    return response
                factory.return_value.open.side_effect = response_for_range
                factory.return_value.open.reset_mock()
                with self.assertRaises(ValueError):
                    stream.read(4)
                self.assertEqual(attempts, factory.return_value.open.call_count)
                self.assertEqual(0, stream.tell())

    def test_fragmented_reads_and_incomplete_first_range_keep_pinned_identity(self):
        artifact = dict(id=1, size_in_bytes=4, digest='sha256:' + 'a' * 64,
            archive_download_url='https://api.github.com/repos/codex-agent-labs/codex-agent/actions/artifacts/1/zip')
        for changed in (False, True):
            requests = []
            class Fragmented(io.BytesIO):
                def read(self, size=-1):
                    return super().read(min(size, 1))
            def open_range(request, timeout):
                requests.append(request)
                response = Fragmented(b'ab' if len(requests) == 1 else b'abcd')
                response.status = 206
                response.headers = {'ETag': '"changed"' if changed and len(requests) > 1 else '"same"',
                    'Content-Range': 'bytes 0-3/4'}
                return response
            with mock.patch.object(transport.urllib.request, 'build_opener') as factory, \
                    mock.patch.object(transport.time, 'sleep') as sleep:
                factory.return_value.open.side_effect = open_range
                stream = transport._Archive(artifact, 'unused-fixture-token')
                if changed:
                    with self.assertRaisesRegex(ValueError, 'identity changed'):
                        stream.read(4)
                    self.assertEqual(0, stream.tell())
                    self.assertEqual(0, stream.transferred)
                else:
                    self.assertEqual(b'abcd', stream.read(4))
                    self.assertEqual(4, stream.tell())
                    self.assertEqual(4, stream.transferred)
                self.assertEqual(['bytes=0-3', 'bytes=0-3'], [r.get_header('Range') for r in requests])
                self.assertEqual('"same"', requests[1].get_header('If-match'))
                sleep.assert_called_once_with(1)


if __name__ == '__main__':
    unittest.main()
