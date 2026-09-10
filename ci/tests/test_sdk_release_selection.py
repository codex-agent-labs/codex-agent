"""Real synthetic Git policy checks, not Runtime authentication or host evidence."""

from pathlib import Path
import subprocess
import tempfile
import unittest

from ci.products.sdk_release_selection import read_sdk_release_selection, require_sdk_release_selection


class SdkReleaseSelectionTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sdk-release-selection-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.sdk = self.root / "gradle/release/versions/sdk.txt"
        self.default = self.root / "gradle/release/sdk-default-runtime.txt"
        self.sdk.parent.mkdir(parents=True)
        self.sdk.write_bytes(b"0.3.0-rc.1\n")
        self.default.write_bytes(b"0.2.0\n")
        self.git("init", "-q")
        self.git("config", "user.name", "Synthetic SDK Policy")
        self.git("config", "user.email", "sdk-policy@example.invalid")
        self.revision = self.commit()

    def git(self, *arguments):
        return subprocess.run(["git", *arguments], cwd=self.root, check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True).stdout.strip()

    def commit(self):
        self.git("add", "-A")
        self.git("commit", "-qm", "synthetic policy")
        return self.git("rev-parse", "HEAD")

    def test_exact_original_selection_ignores_checkout_and_unrelated_runtime_version(self):
        self.sdk.write_bytes(b"9.0.0\n")
        self.default.write_bytes(b"9.1.0\n")
        (self.sdk.parent / "runtime.txt").write_bytes(b"99.0.0\n")
        expected = {"sdkVersion": "0.3.0-rc.1", "defaultRuntimeVersion": "0.2.0"}
        self.assertEqual(expected, require_sdk_release_selection(self.root, self.revision,
                         sdk_version="0.3.0-rc.1", runtime_version="0.2.0"))
        self.assertEqual(b"9.0.0\n", self.sdk.read_bytes())
        self.assertEqual(b"9.1.0\n", self.default.read_bytes())
        later = self.commit()
        self.assertEqual(expected, read_sdk_release_selection(self.root, self.revision))
        self.assertEqual({"sdkVersion": "9.0.0", "defaultRuntimeVersion": "9.1.0"},
                         read_sdk_release_selection(self.root, later))

    def test_mismatched_sdk_or_authenticated_runtime_is_rejected(self):
        for sdk, runtime in (("0.3.0", "0.2.0"), ("0.3.0-rc.1", "0.2.1"),
                             (None, "0.2.0"), ("0.3.0-rc.1", "0.2.0+build")):
            with self.subTest(sdk=sdk, runtime=runtime), self.assertRaises(ValueError):
                require_sdk_release_selection(self.root, self.revision, sdk_version=sdk, runtime_version=runtime)

    def test_only_exact_revisions_are_accepted(self):
        for revision in (None, "HEAD", self.revision[:12], self.revision.upper(), self.revision + "^{tree}"):
            with self.subTest(revision=revision), self.assertRaises(ValueError):
                read_sdk_release_selection(self.root, revision)

    def test_each_authority_rejects_malformed_bytes(self):
        invalid = (b"", b"0.2.0", b"0.2.0\r\n", b"0.2.0\n\n", b" 0.2.0\n",
                   b"0.2.0 \n", b"0.2.0+build\n", b"00.2.0\n", b"\xff\n", b"0.2.0\x00\n", b"1" * 257 + b"\n")
        for path in (self.sdk, self.default):
            for raw in invalid:
                with self.subTest(path=path.name, raw=raw):
                    self.sdk.write_bytes(b"0.3.0-rc.1\n")
                    self.default.write_bytes(b"0.2.0\n")
                    path.write_bytes(raw)
                    revision = self.commit()
                    with self.assertRaises(ValueError):
                        read_sdk_release_selection(self.root, revision)

    def test_default_requires_stable_release_but_sdk_may_be_prerelease(self):
        self.default.write_bytes(b"0.2.0-rc.1\n")
        revision = self.commit()
        with self.assertRaisesRegex(ValueError, "stable release"):
            read_sdk_release_selection(self.root, revision)

    def test_missing_and_symbolic_git_authorities_are_rejected(self):
        for path in (self.sdk, self.default):
            relative = path.relative_to(self.root).as_posix()
            self.git("read-tree", self.revision)
            self.git("update-index", "--force-remove", relative)
            tree = self.git("write-tree")
            with self.subTest(path=relative, mode="missing"), self.assertRaisesRegex(ValueError, "absent"):
                read_sdk_release_selection(self.root, tree)
            self.git("read-tree", self.revision)
            blob = self.git("rev-parse", f"{self.revision}:{relative}")
            self.git("update-index", "--cacheinfo", "120000", blob, relative)
            tree = self.git("write-tree")
            with self.subTest(path=relative, mode="symbolic"), self.assertRaisesRegex(ValueError, "not a regular"):
                read_sdk_release_selection(self.root, tree)


if __name__ == "__main__":
    unittest.main()
