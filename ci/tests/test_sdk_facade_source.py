"""Real local Git fixtures; no generator execution, compiler or host acceptance."""

import os
import stat
import unittest
from unittest.mock import patch

from ci.products import sdk_facade_source as source
from ci.products.inventory import (
    git_file_inventory, publish_regular_tree as actual_publish_regular_tree,
    regular_file_inventory,
)
from ci.tests import test_sdk_apple_package_source as fixtures


_TEMPLATE = "gradle/release/sdk-facade-consumer-template"
_FILES = {
    "gradlew": "#!/bin/sh\n# exact original wrapper\n",
    "gradlew.bat": "@rem exact original Windows wrapper\n",
    "gradle/wrapper/gradle-wrapper.jar": "synthetic wrapper archive bytes; never execute\n",
    "gradle/wrapper/gradle-wrapper.properties": "distributionUrl=https://fixture.invalid/gradle.zip\n",
    "gradle/build-logic/src/main/kotlin/KmpConsumerVerificationTask.kt": "original base/init generator\n",
    "gradle/build-logic/src/main/kotlin/ReleaseToolingGradleTasks.kt": "original appended capture generator\n",
    "gradle/build-logic/src/main/kotlin/SdkFacadeValidationTasks.kt": "original target mapping and registration\n",
    "gradle/build-logic/src/main/kotlin/SdkFacadeCompilerCapture.kt": "original selected compiler capture generator\n",
    "gradle/build-logic/build.gradle.kts": "original generator dependency declaration\n",
    "gradle/build-logic/settings.gradle.kts": "original version catalog binding\n",
    "gradle/libs.versions.toml": 'kotlinx-serialization = "original"\n',
    f"{_TEMPLATE}/build.gradle.kts": "original target build\n",
    f"{_TEMPLATE}/settings.gradle.kts": "original artifact-only repositories\n",
    f"{_TEMPLATE}/src/commonMain/kotlin/Consumer.kt": "original facade consumer\n",
    f"{_TEMPLATE}/src/commonMain/resources/nested/input.txt": "all template members are copied\n",
}


def repository_fixture():
    fixture = fixtures.RepositoryFixture()
    for path, contents in _FILES.items():
        fixture.write(path, contents)
    fixture.write("codex-agent-sdk/src/unrelated.kt", "must not capture product source\n")
    fixture.write("build/consumer/.codex-consumer-task-outcomes.init.gradle.kts", "untrusted generated current script\n")
    os.chmod(fixture.repository / "gradlew", 0o755)
    return fixture


class FacadeSourceTest(unittest.TestCase):
    def test_old_commit_and_tree_capture_exact_template_wrapper_and_both_generators(self):
        for use_tree in (False, True):
            with self.subTest(tree=use_tree), repository_fixture() as fixture:
                original = fixture.commit()
                tree = fixture.git("rev-parse", f"{original}^{{tree}}")
                expected = git_file_inventory(fixture.repository, original, _FILES)
                fixture.write(f"{_TEMPLATE}/src/commonMain/kotlin/Consumer.kt", "new committed consumer\n")
                self.assertNotEqual(original, fixture.commit())
                fixture.write("gradle/build-logic/src/main/kotlin/ReleaseToolingGradleTasks.kt", "dirty wrong init generator\n")
                fixture.write(f"{_TEMPLATE}/untracked.txt", "do not import checkout authority\n")
                result = source.capture_facade_validation_sources(fixture.repository, tree if use_tree else original, fixture.output)
                self.assertEqual({"tree": tree, "files": expected}, result)
                self.assertEqual(expected, regular_file_inventory(fixture.output))
                for relative, contents in _FILES.items():
                    self.assertEqual(contents.encode(), (fixture.output / relative).read_bytes())
                self.assertEqual(0o755, stat.S_IMODE((fixture.output / "gradlew").stat().st_mode))
                self.assertEqual(0o644, stat.S_IMODE((fixture.output / "gradlew.bat").stat().st_mode))
                self.assertFalse((fixture.output / "build").exists())
                self.assertFalse((fixture.output / "codex-agent-sdk").exists())
                self.assertFalse((fixture.output / f"{_TEMPLATE}/untracked.txt").exists())
                self.assertEqual(b"dirty wrong init generator\n", (fixture.repository /
                    "gradle/build-logic/src/main/kotlin/ReleaseToolingGradleTasks.kt").read_bytes())

    def test_every_generator_wrapper_and_required_template_input_is_mandatory(self):
        required = [name for name in _FILES if not name.endswith("nested/input.txt")]
        for missing in required:
            with self.subTest(missing=missing), repository_fixture() as fixture:
                fixture.remove(missing)
                revision = fixture.commit()
                with self.assertRaises(ValueError):
                    source.capture_facade_validation_sources(fixture.repository, revision, fixture.output)
                self.assertFalse(fixture.output.exists())

    def test_symbolic_empty_and_unsafe_tracked_sources_reject(self):
        mutations = {
            "symbolic wrapper": lambda f: f.symlink("gradlew"),
            "symbolic template": lambda f: f.symlink(f"{_TEMPLATE}/src/commonMain/kotlin/Consumer.kt"),
            "empty capture generator": lambda f: f.write("gradle/build-logic/src/main/kotlin/ReleaseToolingGradleTasks.kt", ""),
            "unsafe full template member": lambda f: f.write(f"{_TEMPLATE}/bad\npath", "bad\n"),
        }
        for label, mutate in mutations.items():
            with self.subTest(case=label), repository_fixture() as fixture:
                mutate(fixture)
                revision = fixture.commit()
                with self.assertRaises(ValueError):
                    source.capture_facade_validation_sources(fixture.repository, revision, fixture.output)
                self.assertFalse(fixture.output.exists())

    def test_revision_destination_and_original_blob_identity_guards(self):
        with repository_fixture() as fixture:
            revision = fixture.commit()
            for invalid in ("HEAD", revision[:12], "f" * 40, None):
                with self.subTest(revision=invalid), self.assertRaises(ValueError):
                    source.capture_facade_validation_sources(fixture.repository, invalid, fixture.output)
            with self.assertRaisesRegex(ValueError, "overlaps"):
                source.capture_facade_validation_sources(fixture.repository, revision, fixture.repository / "capture")
            with self.assertRaisesRegex(ValueError, "normalized"):
                source.capture_facade_validation_sources(fixture.repository, revision, fixture.root / "absent/../capture")
            alias = fixture.root / "alias"
            alias.symlink_to(fixture.repository, target_is_directory=True)
            with self.assertRaises(ValueError):
                source.capture_facade_validation_sources(fixture.repository, revision, alias / "capture")
            original_read = source.git_regular_blob_bytes

            def altered(*args, **kwargs):
                result = original_read(*args, **kwargs)
                return result + b"changed" if args[2] == "gradlew" else result

            with patch.object(source, "git_regular_blob_bytes", side_effect=altered), self.assertRaisesRegex(ValueError, "changed"):
                source.capture_facade_validation_sources(fixture.repository, revision, fixture.output)
            self.assertFalse(fixture.output.exists())
            fixture.output.mkdir()
            sentinel = fixture.output / "sentinel"
            sentinel.write_bytes(b"preserve caller output\n")
            with self.assertRaisesRegex(ValueError, "already exists"):
                source.capture_facade_validation_sources(fixture.repository, revision, fixture.output)
            self.assertEqual(b"preserve caller output\n", sentinel.read_bytes())

    def test_late_captured_blob_mutation_cannot_be_published(self):
        with repository_fixture() as fixture:
            revision = fixture.commit()

            def mutate_before_copy(captured, output, **kwargs):
                wrapper = captured / "gradlew"
                wrapper.write_bytes(wrapper.read_bytes() + b"late mutation\n")
                actual_publish_regular_tree(captured, output, **kwargs)

            with patch.object(source, "publish_regular_tree", side_effect=mutate_before_copy), \
                    self.assertRaisesRegex(ValueError, "pinned inventory"):
                source.capture_facade_validation_sources(fixture.repository, revision, fixture.output)
            self.assertFalse(fixture.output.exists())

    def test_late_executable_mode_mutation_cannot_be_published(self):
        with repository_fixture() as fixture:
            revision = fixture.commit()

            def mutate_before_copy(captured, output, **kwargs):
                os.chmod(captured / "gradlew", 0o644)
                actual_publish_regular_tree(captured, output, **kwargs)

            with patch.object(source, "publish_regular_tree", side_effect=mutate_before_copy), \
                    self.assertRaisesRegex(ValueError, "pinned inventory"):
                source.capture_facade_validation_sources(fixture.repository, revision, fixture.output)
            self.assertFalse(fixture.output.exists())


if __name__ == "__main__":
    unittest.main()
