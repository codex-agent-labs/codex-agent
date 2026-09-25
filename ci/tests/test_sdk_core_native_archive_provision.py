"""Core native archive provision admits only candidate-Git-pinned host bytes."""

import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.request import Request

from ci import sdk_core_native_archive_provision as provider


ROOT = Path(__file__).resolve().parents[2]
COMMIT = "a" * 40
VERSION = "2.3.10"
NAME = f"kotlin-native-prebuilt-{VERSION}-macos-aarch64.tar.gz"
URL = f"https://repo.maven.apache.org/maven2/org/jetbrains/kotlin/kotlin-native-prebuilt/{VERSION}/{NAME}"


class Response(io.BytesIO):
    status = 200

    def __init__(self, payload, url=URL):
        super().__init__(payload)
        self.url = url

    def geturl(self):
        return self.url


class CoreNativeArchiveProvisionTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="core-native-provider-", dir=ROOT / "build")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.repository = self.base / "repository"
        self.repository.mkdir()
        self.plan = self.base / "plan.json"
        self.plan.write_bytes(b"authenticated plan fixture")
        self.destination = self.base / NAME
        self.payload = b"pinned native archive fixture"

    def sources(self, *, payload=None, include_archive=True, target="macos-arm64"):
        payload = self.payload if payload is None else payload
        digest = hashlib.sha256(payload).hexdigest()
        extension = "zip" if target == "windows-x64" else "tar.gz"
        name = f"kotlin-native-prebuilt-{VERSION}-{provider._SUFFIXES[target]}.{extension}"
        artifact = (f'<artifact name="{name}"><sha256 value="{digest}"/></artifact>'
                    if include_archive else "")
        return {
            provider.VERSION_CATALOG: b'[versions]\nkotlin = "2.3.10"\n',
            provider.RUNTIME_VERIFICATION_METADATA: f"<verification-metadata>{artifact}</verification-metadata>".encode(),
        }

    def run_provider(self, *, target="macos-arm64", response=None, sources=None, plan=None):
        self.download_urls = []
        sources = self.sources() if sources is None else sources

        def git_blob(_root, _revision, name, *, max_bytes):
            self.assertEqual(4 * 1024 * 1024, max_bytes)
            return sources[name]

        def download(url):
            self.download_urls.append(url)
            return response(url) if callable(response) else Response(self.payload) if response is None else response

        with patch.object(provider.product_reuse, "_validate_plan", return_value={
                "validationCommit": COMMIT, "remoteBuildAuthorized": True}) as validate, \
                patch.object(provider, "git_regular_blob_bytes", side_effect=git_blob), \
                patch.object(provider, "_open_archive", side_effect=download):
            result = provider.provision(self.plan if plan is None else plan, target,
                                        self.destination, repository_root=self.repository)
        self.assertEqual(2, validate.call_count)
        return result

    def test_three_macos_arm64_routes_publish_exact_git_pinned_archive(self):
        for target in ("macos-arm64", "ios-arm64", "ios-simulator-arm64"):
            with self.subTest(target=target):
                result = self.run_provider(target=target)
                self.assertEqual([URL], self.download_urls)
                self.assertEqual(self.payload, result.read_bytes())
                result.unlink()

    def test_four_other_native_routes_require_their_host_git_pin_before_retrieval(self):
        for target in ("macos-x64", "linux-arm64", "linux-x64", "windows-x64"):
            with self.subTest(target=target):
                with self.assertRaisesRegex(ValueError, "exact checksum"):
                    self.run_provider(target=target)
                self.assertEqual([], self.download_urls)
                self.assertFalse(self.destination.exists())
                result = self.run_provider(target=target, sources=self.sources(target=target))
                extension = "zip" if target == "windows-x64" else "tar.gz"
                name = f"kotlin-native-prebuilt-{VERSION}-{provider._SUFFIXES[target]}.{extension}"
                self.assertEqual([f"{provider._MAVEN_ROOT}/{VERSION}/{name}"], self.download_urls)
                self.assertEqual(self.payload, result.read_bytes())
                result.unlink()

    def test_linux_arm64_target_uses_the_pinned_linux_x64_host_archive(self):
        result = self.run_provider(target="linux-arm64", sources=self.sources(target="linux-x64"))
        self.assertEqual([f"{provider._MAVEN_ROOT}/{VERSION}/"
                          f"kotlin-native-prebuilt-{VERSION}-linux-x86_64.tar.gz"], self.download_urls)
        self.assertEqual(self.payload, result.read_bytes())

    def test_missing_pin_wrong_bytes_and_redirect_fail_without_publishing(self):
        with self.assertRaisesRegex(ValueError, "exact checksum"):
            self.run_provider(sources=self.sources(include_archive=False))
        self.assertEqual([], self.download_urls)
        for response in (Response(b"wrong"), Response(self.payload, "https://example.com/archive")):
            with self.subTest(response=response.geturl()), self.assertRaises(ValueError):
                self.run_provider(response=response)
            self.assertFalse(self.destination.exists())

    def test_plan_mutation_oversize_and_existing_destination_fail_closed(self):
        def mutate(_url):
            self.plan.write_bytes(b"changed during download")
            return Response(self.payload)

        with self.assertRaisesRegex(ValueError, "plan or policy changed"):
            self.run_provider(response=mutate)
        self.assertFalse(self.destination.exists())
        self.plan.write_bytes(b"authenticated plan fixture")
        with patch.object(provider, "_MAX_ARCHIVE_BYTES", 3), self.assertRaisesRegex(ValueError, "size limit"):
            self.run_provider()
        self.assertFalse(self.destination.exists())
        self.destination.write_bytes(b"foreign")
        with self.assertRaisesRegex(ValueError, "fresh"):
            self.run_provider()
        self.assertEqual(b"foreign", self.destination.read_bytes())
        self.assertEqual([], self.download_urls)

    def test_authorization_location_and_policy_mutation_reject(self):
        with patch.object(provider.product_reuse, "_validate_plan", return_value={
                "validationCommit": COMMIT, "remoteBuildAuthorized": False}), \
                patch.object(provider, "_open_archive") as download, \
                self.assertRaisesRegex(ValueError, "authorized"):
            provider.provision(self.plan, "macos-arm64", self.destination,
                               repository_root=self.repository)
        download.assert_not_called()
        with patch.object(provider, "_open_archive") as download, self.assertRaisesRegex(ValueError, "external"):
            provider.provision(self.plan, "macos-arm64", self.repository / "inside",
                               repository_root=self.repository)
        download.assert_not_called()

        sources = self.sources()
        reads = []

        def changed(_root, _revision, name, *, max_bytes):
            reads.append(name)
            if len(reads) > 2 and name == provider.VERSION_CATALOG:
                return b'[versions]\nkotlin = "2.3.11"\n'
            return sources[name]

        with patch.object(provider.product_reuse, "_validate_plan", return_value={
                "validationCommit": COMMIT, "remoteBuildAuthorized": True}), \
                patch.object(provider, "git_regular_blob_bytes", side_effect=changed), \
                patch.object(provider, "_open_archive", return_value=Response(self.payload)), \
                self.assertRaisesRegex(ValueError, "plan or policy changed"):
            provider.provision(self.plan, "macos-arm64", self.destination,
                               repository_root=self.repository)
        self.assertFalse(self.destination.exists())

    def test_redirects_cannot_leave_maven_central_https(self):
        redirect = provider._MavenRedirect()
        for url in ("http://repo.maven.apache.org/archive", "https://example.com/archive",
                    "https://repo.maven.apache.org:8443/archive"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                redirect.redirect_request(Request(URL), None, 302, "moved", {}, url)


if __name__ == "__main__":
    unittest.main()
