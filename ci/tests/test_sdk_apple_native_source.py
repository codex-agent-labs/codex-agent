"""Immutable local Git capture fixtures; no native execution or host admission."""

import os
import stat
import unittest

from ci.products.inventory import git_file_inventory, regular_file_inventory
from ci.products.sdk_apple_native_source import capture_apple_native_sources
from ci.tests import test_sdk_apple_package_source as fixtures


_ROOT = "codex-agent-runtime-ios/native/"
_FILES = {
    "patches/0001-uninitialized-in-process-host.patch": "adapter patch\n",
    "patches/0002-locked-ios-bridge.patch": "lock patch\n",
    "patches/0003-pinned-ios-sqlite.patch": "workspace patch\n",
    "sqlite/0001-ios-filesystem-probes.patch": "sqlite patch\n",
    "include/codex_agent_ios.h": "original header\n",
    "provenance.json": '{"fixture":"original provenance bytes, not semantic admission"}\n',
    "bridge/Cargo.toml": "[package]\nname = \"synthetic-bridge\"\n",
    "bridge/src/lib.rs": "original bridge\n",
    "bridge/tests/nested/check.rs": "original nested test\n",
    "bridge/resources/schema.json": '{"fixture":"full bridge tree"}\n',
    "bridge/build.rs": "original build script\n",
}


def native_fixture():
    fixture = fixtures.RepositoryFixture()
    for relative, contents in _FILES.items():
        fixture.write(_ROOT + relative, contents)
    fixture.write(_ROOT + "patches/unrelated.patch", "unselected extra patch\n")
    fixture.write(_ROOT + "include/unrelated.h", "unselected extra header\n")
    fixture.write("codex-agent-runtime-ios/build/native-output.a", "unselected build output\n")
    os.chmod(fixture.repository / (_ROOT + "bridge/build.rs"), 0o755)
    return fixture


class SdkAppleNativeSourceTest(unittest.TestCase):
    def test_exact_old_commit_or_tree_preserves_full_allowlist_and_ignores_dirty_checkout(self):
        for tree_revision in (False, True):
            with self.subTest(tree=tree_revision), native_fixture() as fixture:
                original = fixture.commit()
                selected = fixture.git("rev-parse", f"{original}^{{tree}}") if tree_revision else original
                expected = git_file_inventory(fixture.repository, original, [_ROOT + name for name in _FILES])
                fixture.write(_ROOT + "bridge/src/lib.rs", "new committed bridge\n")
                fixture.write(fixture.pin_path, fixture.pins("99.1", "99A1", "99.1"))
                self.assertNotEqual(original, fixture.commit())
                fixture.write(_ROOT + "include/codex_agent_ios.h", "dirty header\n")
                fixture.write(_ROOT + "bridge/untracked.rs", "untracked source\n")
                fixture.write(fixture.pin_path, "dirty invalid pins\n")

                pins = capture_apple_native_sources(fixture.repository, selected, fixture.output)

                self.assertEqual({"xcodeVersion": "26.6", "xcodeBuild": "17F113", "swiftVersion": "6.3.3"}, pins)
                self.assertEqual(expected, regular_file_inventory(fixture.output))
                for relative, contents in _FILES.items():
                    self.assertEqual(contents.encode(), (fixture.output / (_ROOT + relative)).read_bytes())
                self.assertEqual(0o755, stat.S_IMODE((fixture.output / (_ROOT + "bridge/build.rs")).stat().st_mode))
                self.assertEqual(0o644, stat.S_IMODE((fixture.output / (_ROOT + "bridge/Cargo.toml")).stat().st_mode))
                self.assertFalse((fixture.output / fixture.pin_path).exists())
                self.assertFalse((fixture.output / "LICENSE").exists())
                self.assertFalse((fixture.output / "codex-agent-runtime-ios/apple").exists())
                self.assertFalse((fixture.output / "codex-agent-runtime-ios/build").exists())
                self.assertEqual(b"dirty header\n", (fixture.repository / (_ROOT + "include/codex_agent_ios.h")).read_bytes())
                self.assertEqual(b"dirty invalid pins\n", (fixture.repository / fixture.pin_path).read_bytes())

    def test_every_fixed_native_file_and_nonempty_bridge_tree_are_required(self):
        selected = [name for name in _FILES if not name.startswith("bridge/")] + ["bridge"]
        for relative in selected:
            with self.subTest(missing=relative), native_fixture() as fixture:
                fixture.remove(_ROOT + relative)
                revision = fixture.commit()
                with self.assertRaises(ValueError):
                    capture_apple_native_sources(fixture.repository, revision, fixture.output)
                self.assertFalse(fixture.output.exists())

    def test_symbolic_empty_and_unsafe_native_members_fail_before_publication(self):
        mutations = {
            "symbolic header": lambda f: f.symlink(_ROOT + "include/codex_agent_ios.h"),
            "symbolic bridge member": lambda f: f.symlink(_ROOT + "bridge/resources/schema.json"),
            "empty provenance": lambda f: f.write(_ROOT + "provenance.json", ""),
            "empty bridge member": lambda f: f.write(_ROOT + "bridge/Cargo.toml", ""),
            "unsafe bridge path": lambda f: f.write(_ROOT + "bridge/bad\npath.rs", "unsafe\n"),
        }
        for label, mutation in mutations.items():
            with self.subTest(mutation=label), native_fixture() as fixture:
                mutation(fixture)
                revision = fixture.commit()
                with self.assertRaises(ValueError):
                    capture_apple_native_sources(fixture.repository, revision, fixture.output)
                self.assertFalse(fixture.output.exists())

    def test_existing_shared_revision_pin_and_destination_guards_remain_required(self):
        with native_fixture() as fixture:
            revision = fixture.commit()
            for invalid in ("HEAD", revision[:12], None):
                with self.subTest(revision=invalid), self.assertRaises(ValueError):
                    capture_apple_native_sources(fixture.repository, invalid, fixture.output)
                self.assertFalse(fixture.output.exists())
            with self.assertRaisesRegex(ValueError, "overlaps"):
                capture_apple_native_sources(fixture.repository, revision, fixture.repository / "capture")
            fixture.output.mkdir()
            (fixture.output / "sentinel").write_bytes(b"preserved\n")
            with self.assertRaisesRegex(ValueError, "already exists"):
                capture_apple_native_sources(fixture.repository, revision, fixture.output)
            self.assertEqual(b"preserved\n", (fixture.output / "sentinel").read_bytes())
        with native_fixture() as fixture:
            fixture.write(fixture.pin_path, "missing existing pinned declarations\n")
            revision = fixture.commit()
            with self.assertRaises(ValueError):
                capture_apple_native_sources(fixture.repository, revision, fixture.output)
            self.assertFalse(fixture.output.exists())


if __name__ == "__main__":
    unittest.main()
