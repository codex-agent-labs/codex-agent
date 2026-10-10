"""The Android archive provider publishes only candidate-Git-pinned bytes."""

import hashlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.request import Request

from ci import sdk_android_archive_provision as provider


ROOT = Path(__file__).resolve().parents[2]
COMMIT = "a" * 40
ASSET = "codex-app-server-aarch64-unknown-linux-musl"
URL = f"https://github.com/openai/codex/releases/download/rust-v0.149.0/{ASSET}.tar.gz"


class Response(io.BytesIO):
    status = 200

    def __init__(self, payload, url=URL):
        super().__init__(payload)
        self.url = url

    def geturl(self):
        return self.url


class AndroidArchiveProvisionTest(unittest.TestCase):
    def setUp(self):
        (ROOT / "build").mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="android-archive-provider-", dir=ROOT / "build")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.repository = self.base / "repository"
        self.repository.mkdir()
        self.plan = self.base / "plan.json"
        self.plan.write_bytes(b"authenticated plan fixture")
        self.destination = self.base / (ASSET + ".tar.gz")
        self.payload = b"original archive fixture"

    def pins(self, *, archive=None, version="0.149.0", binary="b" * 64):
        archive = self.payload if archive is None else archive
        return (f"codexAgent.codexVersion={version}\n"
                f"codexAgent.codexArchiveSha256={hashlib.sha256(archive).hexdigest()}\n"
                f"codexAgent.codexBinarySha256={binary}\n").encode()

    def run_provider(self, *, response=None, pins=None, plan=None):
        received = []
        self.download_urls = received
        def download(url):
            received.append(url)
            return response(url) if callable(response) else Response(self.payload) if response is None else response
        with patch.object(provider.product_reuse, "_validate_plan", return_value={
                "validationCommit": COMMIT, "remoteBuildAuthorized": True}) as validate, \
                patch.object(provider, "git_regular_blob_bytes", return_value=self.pins() if pins is None else pins) as git, \
                patch.object(provider, "_open_archive", side_effect=download):
            result = provider.provision(self.plan if plan is None else plan, self.destination,
                                        repository_root=self.repository)
        self.assertEqual(2, validate.call_count)
        validate.assert_any_call(self.plan if plan is None else plan, self.repository)
        git.assert_called_once_with(self.repository, COMMIT, "gradle.properties", max_bytes=1024 * 1024)
        return result, received

    def test_fixed_url_and_authenticated_git_hash_publish_exact_archive(self):
        result, urls = self.run_provider()
        self.assertEqual([URL], urls)
        self.assertEqual(self.destination, result)
        self.assertEqual(self.payload, result.read_bytes())

    def test_wrong_digest_and_redirect_publish_nothing(self):
        for response in (Response(b"wrong bytes"), Response(self.payload, "http://github.com/not-tls")):
            with self.subTest(response=response.geturl(), payload=response.getvalue()):
                with self.assertRaises(ValueError):
                    self.run_provider(response=response)
                self.assertFalse(self.destination.exists())

    def test_plan_mutation_oversize_and_existing_destination_fail_closed(self):
        def mutate(_url):
            self.plan.write_bytes(b"changed during download")
            return Response(self.payload)
        with self.assertRaisesRegex(ValueError, "plan changed during download"):
            self.run_provider(response=mutate)
        self.assertFalse(self.destination.exists())
        self.plan.write_bytes(b"authenticated plan fixture")
        with patch.object(provider, "_MAX_ARCHIVE_BYTES", 4), self.assertRaisesRegex(ValueError, "size limit"):
            self.run_provider()
        self.assertFalse(self.destination.exists())
        self.destination.write_bytes(b"foreign archive")
        with self.assertRaisesRegex(ValueError, "fresh"):
            self.run_provider()
        self.assertEqual(b"foreign archive", self.destination.read_bytes())
        self.assertEqual([], self.download_urls)

    def test_all_digest_and_secret_checks_finish_before_publication(self):
        actual_hash = provider.sha256_file
        actual_secret_check = provider.require_no_signing_secret
        checks = []

        def checked_hash(*args, **kwargs):
            self.assertFalse(self.destination.exists())
            checks.append("digest")
            return actual_hash(*args, **kwargs)

        def checked_secret(*args, **kwargs):
            self.assertFalse(self.destination.exists())
            checks.append("secret")
            return actual_secret_check(*args, **kwargs)

        with patch.object(provider, "sha256_file", side_effect=checked_hash), \
                patch.object(provider, "require_no_signing_secret", side_effect=checked_secret):
            self.run_provider()
        self.assertEqual(1, checks.count("digest"))
        self.assertEqual(2, checks.count("secret"))
        self.assertEqual(self.payload, self.destination.read_bytes())

    def test_publication_failure_after_link_removes_only_our_inode(self):
        real_link = os.link

        def linked_then_failed(*args, **kwargs):
            real_link(*args, **kwargs)
            raise OSError("synthetic post-link failure")

        with patch.object(provider.os, "link", side_effect=linked_then_failed), \
                self.assertRaisesRegex(OSError, "post-link failure"):
            self.run_provider()
        self.assertFalse(self.destination.exists())

        def replaced_then_failed(*args, **kwargs):
            real_link(*args, **kwargs)
            self.destination.unlink()
            self.destination.write_bytes(b"foreign replacement")
            raise OSError("synthetic replacement failure")

        with patch.object(provider.os, "link", side_effect=replaced_then_failed), \
                self.assertRaisesRegex(OSError, "replacement failure"):
            self.run_provider()
        self.assertEqual(b"foreign replacement", self.destination.read_bytes())

    def test_post_link_location_check_failure_rolls_back_our_inode(self):
        real_stat = os.stat
        failed = []

        def failed_location_check(path, *args, **kwargs):
            if path == self.destination.name and kwargs.get("dir_fd") is not None and not failed:
                try:
                    real_stat(self.destination, follow_symlinks=False)
                except FileNotFoundError:
                    pass
                else:
                    failed.append(True)
                    raise ValueError("synthetic post-link location failure")
            return real_stat(path, *args, **kwargs)

        with patch.object(provider.os, "stat", side_effect=failed_location_check), \
                self.assertRaisesRegex(ValueError, "location failure"):
            self.run_provider()
        self.assertEqual([True], failed)
        self.assertFalse(self.destination.exists())

    def test_unauthorized_plan_unsafe_location_and_malformed_git_pin_do_not_download(self):
        with patch.object(provider.product_reuse, "_validate_plan", return_value={
                "validationCommit": COMMIT, "remoteBuildAuthorized": False}), \
                patch.object(provider, "_open_archive") as download, \
                self.assertRaisesRegex(ValueError, "authorized"):
            provider.provision(self.plan, self.destination, repository_root=self.repository)
        download.assert_not_called()
        with patch.object(provider, "_open_archive") as download, self.assertRaisesRegex(ValueError, "external"):
            provider.provision(self.plan, self.repository / "inside", repository_root=self.repository)
        download.assert_not_called()
        with self.assertRaises(ValueError):
            self.run_provider(pins=self.pins(version="bad/version"))
        self.assertEqual([], self.download_urls)

    def test_redirects_cannot_leave_github_https(self):
        redirect = provider._GithubRedirect()
        for url in ("http://github.com/archive", "https://example.com/archive",
                    "https://github.com:8443/archive"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                redirect.redirect_request(Request(URL), None, 302, "moved", {}, url)


if __name__ == "__main__":
    unittest.main()
