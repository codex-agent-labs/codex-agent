"""Per-open transport reuse retains immutable range and member authentication."""
import io
from pathlib import Path
import sys
import unittest
import urllib.error
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import runtime_reference_archive as transport


class ReferenceDownloadTest(unittest.TestCase):
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

        with mock.patch.object(transport.urllib.request, 'build_opener') as factory:
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


if __name__ == '__main__':
    unittest.main()
