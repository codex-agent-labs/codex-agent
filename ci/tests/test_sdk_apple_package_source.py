from pathlib import Path
import os
import shutil
import stat
import subprocess
import tempfile
import unittest

from ci.products.inventory import git_file_inventory, regular_file_inventory
from ci.products.sdk_apple_package_source import capture_apple_package_sources


class SdkApplePackageSourceTest(unittest.TestCase):
    def test_captures_exact_immutable_tree_and_ignores_dirty_checkout(self):
        with RepositoryFixture() as fixture:
            revision = fixture.commit()
            expected_paths = fixture.source_paths(revision)
            fixture.write("codex-agent-runtime-ios/apple/Sources/CodexAgent/Api.swift", "dirty\n")
            fixture.write("codex-agent-runtime-ios/apple/Sources/untracked.swift", "untracked\n")
            fixture.write(fixture.pin_path, fixture.pins("99.0", "bad", "99.0"))

            result = capture_apple_package_sources(fixture.repository, revision, fixture.output)

            self.assertEqual({
                "xcodeVersion": "26.6",
                "xcodeBuild": "17F113",
                "swiftVersion": "6.3.3",
            }, result)
            self.assertEqual(
                git_file_inventory(fixture.repository, revision, expected_paths),
                regular_file_inventory(fixture.output),
            )
            self.assertEqual(
                b"api\n",
                (fixture.output / "codex-agent-runtime-ios/apple/Sources/CodexAgent/Api.swift").read_bytes(),
            )
            self.assertFalse((fixture.output / "codex-agent-runtime-ios/apple/Sources/untracked.swift").exists())
            self.assertFalse((fixture.output / fixture.pin_path).exists())
            self.assertTrue(os.stat(
                fixture.output / "codex-agent-runtime-ios/apple/TestApp/App.swift",
            ).st_mode & stat.S_IXUSR)

    def test_accepts_an_exact_tree_and_captures_new_members_of_each_fixed_tree(self):
        with RepositoryFixture() as fixture:
            fixture.write("codex-agent-runtime-ios/apple/Tests/Nested/NewTest.swift", "new\n")
            revision = fixture.commit()
            tree = fixture.git("rev-parse", f"{revision}^{{tree}}")

            capture_apple_package_sources(fixture.repository, tree, fixture.output)

            self.assertEqual(b"new\n", (
                fixture.output / "codex-agent-runtime-ios/apple/Tests/Nested/NewTest.swift"
            ).read_bytes())

    def test_rejects_missing_empty_symbolic_and_unsafe_source_entries(self):
        mutations = {
            "missing singleton": lambda fixture: fixture.remove("LICENSE"),
            "missing tree": lambda fixture: fixture.remove("codex-agent-runtime-ios/apple/TestApp"),
            "empty blob": lambda fixture: fixture.write(
                "codex-agent-runtime-ios/apple/Tests/ApiTests.swift", "",
            ),
            "symbolic blob": lambda fixture: fixture.symlink(
                "codex-agent-runtime-ios/apple/Sources/CodexAgent/Api.swift",
            ),
            "unsafe path": lambda fixture: fixture.write(
                "codex-agent-runtime-ios/apple/Sources/bad\nname.swift", "unsafe\n",
            ),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label), RepositoryFixture() as fixture:
                mutate(fixture)
                revision = fixture.commit()
                with self.assertRaises(ValueError):
                    capture_apple_package_sources(fixture.repository, revision, fixture.output)
                self.assertFalse(fixture.output.exists())

    def test_rejects_invalid_or_unavailable_revisions_and_toolchain_declarations(self):
        with RepositoryFixture() as fixture:
            revision = fixture.commit()
            for invalid in ("HEAD", revision[:12], revision.upper(), "f" * 40):
                with self.subTest(revision=invalid), self.assertRaises(ValueError):
                    capture_apple_package_sources(fixture.repository, invalid, fixture.next_output())

        invalid_pins = (
            "private val pinnedXcodeVersion = \"26.x\"\n"
            "private val pinnedXcodeBuild = \"17F113\"\n"
            "private val pinnedSwiftVersion = \"6.3.3\"\n",
            RepositoryFixture.pins("26.6", "17F-113", "6.3.3"),
            RepositoryFixture.pins("26.6", "build", "6.3.3"),
            RepositoryFixture.pins("26.6", "17F113", "6.3.3") +
            "private val pinnedSwiftVersion = \"6.3.3\"\n",
        )
        for index, contents in enumerate(invalid_pins):
            with self.subTest(index=index), RepositoryFixture() as fixture:
                fixture.write(fixture.pin_path, contents)
                revision = fixture.commit()
                with self.assertRaises(ValueError):
                    capture_apple_package_sources(fixture.repository, revision, fixture.output)

    def test_rejects_existing_overlapping_and_non_normalized_outputs(self):
        with RepositoryFixture() as fixture:
            revision = fixture.commit()
            fixture.output.mkdir()
            with self.assertRaisesRegex(ValueError, "already exists"):
                capture_apple_package_sources(fixture.repository, revision, fixture.output)
        with RepositoryFixture() as fixture:
            revision = fixture.commit()
            with self.assertRaisesRegex(ValueError, "overlaps"):
                capture_apple_package_sources(
                    fixture.repository,
                    revision,
                    fixture.repository / "captured",
                )
        with RepositoryFixture() as fixture:
            revision = fixture.commit()
            non_normalized = fixture.output.parent / "missing" / ".." / fixture.output.name
            with self.assertRaisesRegex(ValueError, "normalized"):
                capture_apple_package_sources(fixture.repository, revision, non_normalized)


class RepositoryFixture:
    pin_path = "gradle/build-logic/src/main/kotlin/codexagent.ios-runtime.gradle.kts"

    def __init__(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="sdk-apple-package-source-")
        self.root = Path(self.temporary.name).resolve()
        self.repository = self.root / "repository"
        self.output = self.root / "captured"
        self.repository.mkdir()
        self.git("init", "-q")
        self.git("config", "user.name", "Apple package source fixture")
        self.git("config", "user.email", "apple-package-source@example.invalid")
        files = {
            "LICENSE": "license\n",
            "THIRD_PARTY_NOTICES.md": "third party\n",
            "legal/openai-codex/openai-codex-LICENSE.txt": "openai license\n",
            "legal/openai-codex/openai-codex-NOTICE.txt": "openai notice\n",
            "codex-agent-runtime-ios/apple/Package.swift": "// package\n",
            "codex-agent-runtime-ios/apple/Sources/CodexAgent/Api.swift": "api\n",
            "codex-agent-runtime-ios/apple/Tests/ApiTests.swift": "tests\n",
            "codex-agent-runtime-ios/apple/TestApp/App.swift": "app\n",
            self.pin_path: self.pins("26.6", "17F113", "6.3.3"),
        }
        for path, contents in files.items():
            self.write(path, contents)
        os.chmod(self.repository / "codex-agent-runtime-ios/apple/TestApp/App.swift", 0o755)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.temporary.cleanup()

    def git(self, *arguments):
        return subprocess.run(
            ["git", *arguments],
            cwd=self.repository,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ).stdout.strip()

    def write(self, relative, contents):
        path = self.repository / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")

    def remove(self, relative):
        path = self.repository / relative
        shutil.rmtree(path) if path.is_dir() else path.unlink()

    def symlink(self, relative):
        path = self.repository / relative
        path.unlink()
        path.symlink_to("Api.swift.target")

    def commit(self):
        self.git("add", "-A")
        self.git("commit", "-qm", "fixture")
        return self.git("rev-parse", "HEAD")

    def source_paths(self, revision):
        lines = self.git("ls-tree", "-r", "--name-only", revision).splitlines()
        return [path for path in lines if path in {
            "LICENSE",
            "THIRD_PARTY_NOTICES.md",
            "legal/openai-codex/openai-codex-LICENSE.txt",
            "legal/openai-codex/openai-codex-NOTICE.txt",
            "codex-agent-runtime-ios/apple/Package.swift",
        } or path.startswith((
            "codex-agent-runtime-ios/apple/Sources/",
            "codex-agent-runtime-ios/apple/Tests/",
            "codex-agent-runtime-ios/apple/TestApp/",
        ))]

    def next_output(self):
        return self.root / f"captured-{len(list(self.root.glob('captured-*')))}"

    @staticmethod
    def pins(xcode, build, swift):
        return (
            f'private val pinnedXcodeVersion = "{xcode}"\n'
            f'private val pinnedXcodeBuild = "{build}"\n'
            f'private val pinnedSwiftVersion = "{swift}"\n'
        )


if __name__ == "__main__":
    unittest.main()
