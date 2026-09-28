"""Offline Dart content-chain proof; pub publish validation remains required."""

from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from ci.tests.product_chain_sdk import _materialize_sources, _stage_sdks
from ci.tests.test_product_native_chain import build_chain

from ci import native_wrappers as wrappers


@unittest.skipUnless(shutil.which("ssh-keygen"), "OpenSSH signing tool unavailable")
class DartPackageContentChainTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="s808-dart-content-chain-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name).resolve()
        cls.chains = [build_chain(cls.root / name, run) for name, run in (("first", 11), ("second", 22))]

    def package(self, chain, name):
        work = self.root / name
        work.mkdir()
        sdks, version = _stage_sdks(work, chain["variants"], chain["compatibility"], chain["context"])
        sources = _materialize_sources(work, sdks, ("dart",))
        wrappers.set_source_sdk_version(sources, version, ("dart",))
        output = work / "packages"
        staged = work / "dart-release"
        with patch.object(wrappers, "run", side_effect=AssertionError(
                "Dart package-only phase must not run a build or pub command")):
            wrappers.package_once(sources, sdks, output, version, ("dart",))
        archive = output / "dart" / f"codex-agent-dart-{version}.tar.gz"
        wrappers.stage_dart_release(sources / "dart", staged)
        return sdks, staged, archive, version

    def test_two_original_producers_yield_equal_verified_dart_archive(self):
        first = self.package(self.chains[0], "dart-first")
        second = self.package(self.chains[1], "dart-second")
        self.assertEqual(first[3], second[3])
        self.assertEqual(first[2].read_bytes(), second[2].read_bytes())
        self.assertNotEqual(
            self.chains[0]["context"]["producer"], self.chains[1]["context"]["producer"])
        self.assertNotEqual(
            self.chains[0]["variants"]["variant_phase_receipts"]["macos-arm64"]["package"].read_bytes(),
            self.chains[1]["variants"]["variant_phase_receipts"]["macos-arm64"]["package"].read_bytes())
        native = first[1] / "lib/src/native"
        self.assertEqual({"README.md", "sdk-compatibility.json", "sdk-runtime-root.pub", *wrappers.HOSTS},
                         {path.name for path in native.iterdir()})
        with tempfile.TemporaryDirectory(prefix="s808-dart-content-extract-") as temporary:
            extracted = Path(temporary).resolve()
            wrappers.safe_extract_tar(first[2], extracted)
            packaged = extracted / f"codex_agent-{first[3]}"
            self.assertEqual(wrappers.package_inventory(first[1]), wrappers.package_inventory(packaged))
            self.assertFalse((packaged / "pubspec.lock").exists())
            self.assertFalse((packaged / ".dart_tool").exists())
            self.assertFalse((packaged / "consumer").exists())

    def test_native_byte_mutation_rejected_by_existing_package_verifier(self):
        sdks, _, archive, version = self.package(self.chains[0], "dart-tamper")
        library = sdks / "linux-x64/lib/libcodex_agent.so"
        original = library.read_bytes()
        try:
            library.write_bytes(original + b"tampered")
            with self.assertRaises(ValueError):
                wrappers.verify_native_wrapper_sdk_packages(archive.parent.parent, sdks, version, "dart")
        finally:
            library.write_bytes(original)


if __name__ == "__main__":
    unittest.main()
