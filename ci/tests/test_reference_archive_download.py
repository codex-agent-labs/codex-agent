"""Per-open transport reuse retains immutable range and member authentication."""
import io
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
