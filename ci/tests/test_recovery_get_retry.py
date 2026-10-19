"""Recovery retries transport failures, never failed content authentication."""
import hashlib
from http.client import IncompleteRead
import io
import json
import socket
import ssl
from pathlib import Path
import tempfile
import unittest
import urllib.error
from unittest import mock

import ci.product_reuse as recovery
import reuse


class RecoveryGetRetryTest(unittest.TestCase):
    def test_primary_exhaustion_waits_once_for_reset_without_changing_request(self):
        headers = {'x-ratelimit-limit': '5000', 'x-ratelimit-remaining': '0',
                   'x-ratelimit-used': '5000', 'x-ratelimit-reset': '1120'}
        for repeated in (False, True):
            error = urllib.error.HTTPError('https://api.github.com/repos/a/b/actions/runs/1',
                                          403, 'denied', headers, io.BytesIO(b'private body'))
            self.addCleanup(error.close)
            operation = mock.Mock(side_effect=[error, error if repeated else {'id': 1}])
            with mock.patch.object(recovery.time, 'time', return_value=1000), \
                    mock.patch.object(recovery.time, 'sleep') as sleep, \
                    mock.patch.object(recovery.sys, 'stderr', new_callable=io.StringIO) as log:
                if repeated:
                    with self.assertRaises(urllib.error.HTTPError):
                        recovery._retry_github_get(operation)('exact-url', token='secret-token')
                else:
                    self.assertEqual({'id': 1}, recovery._retry_github_get(operation)(
                        'exact-url', token='secret-token'))
                self.assertEqual([mock.call('exact-url', token='secret-token')] * 2, operation.call_args_list)
                sleep.assert_called_once_with(122)
                self.assertNotIn('secret-token', log.getvalue())
                self.assertNotIn('private body', log.getvalue())
                self.assertNotIn(error.url, log.getvalue())
                diagnostics = [json.loads(line.removeprefix('github-api-error '))
                               for line in log.getvalue().splitlines()
                               if line.startswith('github-api-error ')]
                self.assertEqual([{'status': 403, 'messageKind': 'unclassified',
                    'rateLimit': {name: int(value) for name, value in headers.items()}}], diagnostics)

    def test_other_denials_and_unbounded_or_untrusted_resets_never_authorize_wait(self):
        headers = {'x-ratelimit-limit': '5000', 'x-ratelimit-remaining': '0',
                   'x-ratelimit-used': '5000', 'x-ratelimit-reset': '1120'}
        cases = [(401, 'https://api.github.com/x', headers),
                 (403, 'https://api.github.com.evil.invalid/x', headers),
                 (403, 'http://api.github.com/x', headers),
                 (403, 'https://secret@api.github.com/x', headers)]
        for field, value in [('x-ratelimit-limit', '0'), ('x-ratelimit-remaining', '1'),
                             ('x-ratelimit-used', '4999'), ('x-ratelimit-reset', '9999999'),
                             ('x-ratelimit-reset', '990'), ('x-ratelimit-reset', '-1'),
                             ('x-ratelimit-reset', '１２３'), ('retry-after', '7200'),
                             ('retry-after', 'malformed')]:
            cases.append((403, 'https://api.github.com/x', dict(headers, **{field: value})))
        for code, url, values in cases:
            with self.subTest(code=code, url=url, headers=values), \
                    mock.patch.object(recovery.time, 'time', return_value=1000), \
                    mock.patch.object(recovery.time, 'sleep') as sleep, \
                    mock.patch.object(recovery, 'report_api_error') as report:
                error = urllib.error.HTTPError(url, code, 'denied', values, None)
                self.addCleanup(error.close)
                operation = mock.Mock(side_effect=error)
                with self.assertRaises(urllib.error.HTTPError):
                    recovery._retry_github_get(operation)()
                operation.assert_called_once()
                sleep.assert_not_called()
                report.assert_not_called()
        error = urllib.error.HTTPError('https://api.github.com/x', 429, 'limited',
                                      dict(headers, **{'retry-after': '200'}), None)
        self.addCleanup(error.close)
        with mock.patch.object(recovery.time, 'time', return_value=1000):
            self.assertEqual(202, recovery._primary_rate_limit_delay(error))

    def test_failed_original_transfer_reports_identity_without_retry_or_admission(self):
        digest = "sha256:" + "a" * 64
        failure = ValueError("GitHub artifact transport digest or size mismatch")
        with mock.patch.object(recovery, "download_artifact_to_file", side_effect=failure) as download:
            with self.assertRaisesRegex(ValueError, "original artifact 71, expected 23 bytes / " + digest):
                recovery._download_contract_ci_upload_bytes(
                    {"id": 71}, "secret-token", Path("unused.zip"), 1024, digest, 23)
            download.assert_called_once()

    def test_timeout_retries_are_bounded_and_authentication_errors_do_not_retry(self):
        for error, calls in ((TimeoutError("read timed out"), 4),
                             (IncompleteRead(b"", 105405), 4),
                             (ConnectionResetError(104, "Connection reset by peer"), 4),
                             (urllib.error.URLError(ConnectionResetError(104, "Connection reset by peer")), 4),
                             (urllib.error.URLError(TimeoutError("read timed out")), 4),
                             (urllib.error.URLError(socket.gaierror(8, "nodename nor servname provided")), 4),
                             (urllib.error.URLError(ssl.SSLCertVerificationError("certificate rejected")), 1),
                             (urllib.error.URLError("unknown transport failure"), 1),
                             (urllib.error.HTTPError("https://example.invalid", 500, "internal server error", {}, None), 4),
                             (urllib.error.HTTPError("https://example.invalid", 503, "unavailable", {}, None), 4),
                             (ValueError("digest mismatch"), 1),
                             (urllib.error.HTTPError("https://example.invalid", 403, "denied", {}, None), 1)):
            with self.subTest(error=type(error).__name__), mock.patch.object(recovery.time, "sleep") as sleep:
                if isinstance(error, urllib.error.HTTPError):
                    self.addCleanup(error.close)
                operation = mock.Mock(side_effect=error)
                with self.assertRaises(type(error)):
                    recovery._retry_github_get(operation)()
                self.assertEqual(calls, operation.call_count)
                self.assertEqual([mock.call(1), mock.call(2), mock.call(4)] if calls == 4 else [],
                                 sleep.call_args_list)

    def test_stream_timeout_discards_partial_file_and_reverifies_complete_retry(self):
        contents = b"original immutable bytes"
        artifact = {"id": 71, "size_in_bytes": len(contents),
                    "digest": "sha256:" + hashlib.sha256(contents).hexdigest(),
                    "archive_download_url": "https://api.github.com/repos/codex-agent-labs/codex-agent/actions/artifacts/71/zip"}
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.read.side_effect = [contents[:2], IncompleteRead(b"", len(contents) - 2)]
        opener = mock.Mock()
        opener.open.side_effect = [response, io.BytesIO(contents)]
        with tempfile.TemporaryDirectory() as temporary, \
                mock.patch.object(reuse.urllib.request, "build_opener", return_value=opener), \
                mock.patch.object(recovery.time, "sleep") as sleep:
            destination = Path(temporary) / "original.zip"
            recovery.download_artifact_to_file(artifact, "test-token", destination, max_bytes=1024)
            self.assertEqual(contents, destination.read_bytes())
            self.assertEqual(2, opener.open.call_count)
            sleep.assert_called_once_with(1)


if __name__ == "__main__":
    unittest.main()
