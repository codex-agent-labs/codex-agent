from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path
import sys
import tempfile
import unittest
import urllib.error
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from reuse import download_artifact_to_file  # noqa: E402
import product_reuse  # noqa: E402


class StreamedArtifactTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.destination = Path(self.temporary.name) / "transport.zip"
        self.payload = b"exact transport bytes"
        self.artifact = {
            "archive_download_url": "https://api.github.com/artifact/zip",
            "digest": "sha256:" + hashlib.sha256(self.payload).hexdigest(),
            "size_in_bytes": len(self.payload),
        }

    def download(self, payload=None, artifact=None):
        response = BytesIO(self.payload if payload is None else payload)
        with mock.patch("reuse.urllib.request.build_opener") as builder:
            builder.return_value.open.return_value = response
            download_artifact_to_file(
                self.artifact if artifact is None else artifact,
                "token", self.destination, max_bytes=1024,
            )
            return builder

    def test_exact_bytes_are_streamed_into_new_file(self):
        builder = self.download()
        self.assertEqual(self.payload, self.destination.read_bytes())
        self.assertEqual("Bearer token", builder.return_value.open.call_args.args[0].get_header("Authorization"))

    def test_oversized_claim_is_rejected_before_network_or_file_creation(self):
        with mock.patch("reuse.urllib.request.build_opener") as builder:
            with self.assertRaisesRegex(ValueError, "fixed bound"):
                download_artifact_to_file({**self.artifact, "size_in_bytes": 1025},
                    "token", self.destination, max_bytes=1024)
            builder.assert_not_called()
        self.assertFalse(self.destination.exists())

    def test_digest_size_and_overflow_fail_without_retained_file(self):
        for payload, artifact in (
            (b"same length, not same!", self.artifact),
            (self.payload[:-1], self.artifact),
            (self.payload + b"!", self.artifact),
        ):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                self.download(payload, artifact)
            self.assertFalse(self.destination.exists())

    def test_existing_file_is_not_overwritten(self):
        self.destination.write_bytes(b"original")
        with self.assertRaises(FileExistsError):
            self.download()
        self.assertEqual(b"original", self.destination.read_bytes())

    def test_transient_get_retries_preserve_transport_checks_and_auth(self):
        for streamed in (False, True):
            with self.subTest(streamed=streamed), mock.patch("product_reuse.time.sleep") as sleep, \
                    mock.patch("reuse.urllib.request.build_opener") as builder:
                opener = builder.return_value
                opener.open.side_effect = [urllib.error.HTTPError(
                    self.artifact["archive_download_url"], 502, "transient", {}, None), BytesIO(self.payload)]
                if streamed:
                    product_reuse.download_artifact_to_file(self.artifact, "token", self.destination, max_bytes=1024)
                    self.assertEqual(self.payload, self.destination.read_bytes())
                else:
                    self.assertEqual(self.payload, product_reuse.download_artifact(self.artifact, "token"))
                self.assertEqual(2, opener.open.call_count)
                sleep.assert_called_once_with(1)
                self.assertEqual("Bearer token", opener.open.call_args.args[0].get_header("Authorization"))

    def test_permanent_or_exhausted_get_failure_is_not_admitted(self):
        for code, attempts in ((403, 1), (502, 4)):
            with self.subTest(code=code), mock.patch("product_reuse.time.sleep"), \
                    mock.patch("reuse.urllib.request.build_opener") as builder:
                builder.return_value.open.side_effect = urllib.error.HTTPError(
                    self.artifact["archive_download_url"], code, "failed", {}, None)
                with self.assertRaises(urllib.error.HTTPError):
                    product_reuse.download_artifact_to_file(self.artifact, "token", self.destination, max_bytes=1024)
                self.assertEqual(attempts, builder.return_value.open.call_count)
                self.assertFalse(self.destination.exists())


if __name__ == "__main__":
    unittest.main()
