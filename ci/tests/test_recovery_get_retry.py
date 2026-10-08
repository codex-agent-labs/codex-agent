"""Recovery retries transport failures, never failed content authentication."""
import hashlib
import io
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
    def test_timeout_retries_are_bounded_and_authentication_errors_do_not_retry(self):
        for error, calls in ((TimeoutError("read timed out"), 4),
                             (urllib.error.URLError(socket.gaierror(8, "nodename nor servname provided")), 4),
                             (urllib.error.URLError(ssl.SSLCertVerificationError("certificate rejected")), 1),
                             (urllib.error.URLError("unknown transport failure"), 1),
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
        response.read.side_effect = [contents[:2], TimeoutError("read timed out")]
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
