"""Local immutable Git fixtures only; no Apple compiler or hosted-source admission."""

from pathlib import Path
import os
import shutil
import stat
import unittest
from unittest import mock

from ci.products import sdk_apple_package_source as shared
from ci.products import sdk_apple_validation_source as validation
from ci.products.inventory import git_file_inventory, regular_file_inventory
from ci.products.sdk_apple_validation_source import (
    capture_apple_validation_sources,
    read_apple_validation_simulator_policy,
    verify_apple_validation_sources,
)
from ci.tests.test_sdk_apple_package_source import RepositoryFixture


_APPLE = "codex-agent-runtime-ios/apple/"
_SWIFT = _APPLE + "CompilerEvidence/CodexFailureSwiftConsumer.swift"
_OBJECTIVE_C = _APPLE + "CompilerEvidence/CodexFailureObjectiveCConsumer.m"
_SIMULATOR_POLICY = "gradle/build-logic/src/main/kotlin/IosAppleDistributionTasks.kt"


def simulator_policy(runtime="iOS 26.5", device="com.apple.CoreSimulator.SimDeviceType.iPhone-17"):
    return (
        "fun register() {\n"
        f'    runtimeName.set("{runtime}")\n'
        f'    deviceTypeIdentifier.set("{device}")\n'
        "}\n"
    )


def validation_fixture():
    fixture = RepositoryFixture()
    fixture.write(_SWIFT, "original Swift consumer\n")
    fixture.write(_OBJECTIVE_C, "original Objective-C consumer\n")
    fixture.write(_APPLE + "CompilerEvidence/unrelated.m", "not selected\n")
    fixture.write(_APPLE + "TestApp/Nested/config.json", "original test application config\n")
    fixture.write(_SIMULATOR_POLICY, simulator_policy())
    return fixture


def retained_sources(fixture, revision):
    capture_apple_validation_sources(fixture.repository, revision, fixture.output)
    evidence = fixture.root / "evidence"
    shutil.copytree(fixture.output / (_APPLE + "CompilerEvidence"), evidence / "consumer")
    shutil.copytree(fixture.output / (_APPLE + "TestApp"), evidence / "device-test-application")
    (evidence / "device-raw").mkdir()
    (evidence / "device-raw/stderr.bin").write_bytes(b"")
    return evidence


class SdkAppleValidationSourceTest(unittest.TestCase):
    def test_simulator_policy_comes_only_from_the_exact_immutable_commit_or_tree(self):
        with validation_fixture() as fixture:
            revision = fixture.commit()
            tree = fixture.git("rev-parse", f"{revision}^{{tree}}")
            fixture.write(_SIMULATOR_POLICY, simulator_policy("iOS 99.1", "com.apple.CoreSimulator.SimDeviceType.iPad-99"))

            expected = {
                "runtimeName": "iOS 26.5",
                "deviceTypeIdentifier": "com.apple.CoreSimulator.SimDeviceType.iPhone-17",
            }
            self.assertEqual(expected, read_apple_validation_simulator_policy(fixture.repository, revision))
            self.assertEqual(expected, read_apple_validation_simulator_policy(fixture.repository, tree))

    def test_simulator_policy_rejects_missing_duplicate_malformed_and_nonregular_declarations(self):
        invalid = (
            "",
            'runtimeName.set("iOS 26.5")\n',
            simulator_policy() + 'runtimeName.set("iOS 26.5")\n',
            simulator_policy() +
            'deviceTypeIdentifier.set("com.apple.CoreSimulator.SimDeviceType.iPhone-17")\n',
            simulator_policy() + 'runtimeName.set(providers.gradleProperty("runtime"))\n',
            simulator_policy() +
            'deviceTypeIdentifier . set (providers.gradleProperty("device"))\n',
            simulator_policy("26.5"),
            simulator_policy("iOS 026.5"),
            simulator_policy(device="iPhone-17"),
            simulator_policy(device="com.apple.CoreSimulator.SimDeviceType.iPhone 17"),
        )
        for index, contents in enumerate(invalid):
            with self.subTest(index=index), validation_fixture() as fixture:
                fixture.write(_SIMULATOR_POLICY, contents)
                revision = fixture.commit()
                with self.assertRaises(ValueError):
                    read_apple_validation_simulator_policy(fixture.repository, revision)

        with validation_fixture() as fixture:
            fixture.remove(_SIMULATOR_POLICY)
            revision = fixture.commit()
            with self.assertRaises(ValueError):
                read_apple_validation_simulator_policy(fixture.repository, revision)
        with validation_fixture() as fixture:
            fixture.symlink(_SIMULATOR_POLICY)
            revision = fixture.commit()
            with self.assertRaises(ValueError):
                read_apple_validation_simulator_policy(fixture.repository, revision)

    def test_simulator_policy_rejects_invalid_revision_and_non_utf8_source(self):
        with validation_fixture() as fixture:
            revision = fixture.commit()
            for invalid in ("HEAD", revision[:12], revision.upper(), "f" * 40, None):
                with self.subTest(revision=invalid), self.assertRaises(ValueError):
                    read_apple_validation_simulator_policy(fixture.repository, invalid)
        with validation_fixture() as fixture:
            (fixture.repository / _SIMULATOR_POLICY).write_bytes(b"\xff\xfe")
            revision = fixture.commit()
            with self.assertRaisesRegex(ValueError, "not UTF-8"):
                read_apple_validation_simulator_policy(fixture.repository, revision)

    def test_retained_sources_match_selected_git_not_dirty_checkout_and_preserve_raw(self):
        with validation_fixture() as fixture:
            revision = fixture.commit()
            evidence = retained_sources(fixture, revision)
            before = regular_file_inventory(evidence, allow_empty=True)
            fixture.write(_SWIFT, "dirty unrelated checkout\n")
            fixture.write(_APPLE + "TestApp/App.swift", "dirty application\n")
            fixture.write(fixture.pin_path, "dirty invalid toolchain declarations\n")

            result = verify_apple_validation_sources(fixture.repository, revision, evidence)

            self.assertEqual({
                "consumerInventory": regular_file_inventory(evidence / "consumer"),
                "testApplicationInventory": regular_file_inventory(evidence / "device-test-application"),
                "toolchain": {"xcodeVersion": "26.6", "xcodeBuild": "17F113", "swiftVersion": "6.3.3"},
            }, result)
            self.assertEqual(before, regular_file_inventory(evidence, allow_empty=True))
            self.assertEqual(b"dirty unrelated checkout\n", (fixture.repository / _SWIFT).read_bytes())

    def test_retained_missing_extra_modified_empty_or_linked_sources_reject(self):
        for relative in ("consumer/CodexFailureSwiftConsumer.swift", "device-test-application/App.swift"):
            for mutation in ("missing", "extra", "modified", "empty", "linked"):
                with self.subTest(path=relative, mutation=mutation), validation_fixture() as fixture:
                    revision = fixture.commit()
                    evidence = retained_sources(fixture, revision)
                    source = evidence / relative
                    if mutation == "missing":
                        source.unlink()
                    elif mutation == "extra":
                        source.with_name("extra.swift").write_bytes(b"extra\n")
                    elif mutation == "linked":
                        source.unlink()
                        source.symlink_to(fixture.repository / _SWIFT)
                    else:
                        source.write_bytes(b"" if mutation == "empty" else b"unrelated\n")
                    with self.assertRaises(ValueError):
                        verify_apple_validation_sources(fixture.repository, revision, evidence)
                    self.assertEqual(b"", (evidence / "device-raw/stderr.bin").read_bytes())

    def test_self_consistent_retained_checkout_is_not_selected_git_authority(self):
        with validation_fixture() as fixture:
            revision = fixture.commit()
            evidence = retained_sources(fixture, revision)
            changed = b"different source\n"
            fixture.write(_SWIFT, changed.decode())
            (evidence / "consumer/CodexFailureSwiftConsumer.swift").write_bytes(changed)
            before = regular_file_inventory(evidence, allow_empty=True)
            with self.assertRaisesRegex(ValueError, "selected immutable Git"):
                verify_apple_validation_sources(fixture.repository, revision, evidence)
            self.assertEqual(before, regular_file_inventory(evidence, allow_empty=True))
            for invalid in ("HEAD", None):
                with self.subTest(revision=invalid), self.assertRaises(ValueError):
                    verify_apple_validation_sources(fixture.repository, invalid, evidence)

    def test_retained_source_mutation_during_capture_and_root_alias_reject(self):
        with validation_fixture() as fixture:
            revision = fixture.commit()
            evidence = retained_sources(fixture, revision)
            original_capture = validation.capture_apple_validation_sources

            def capture(*args):
                result = original_capture(*args)
                (evidence / "consumer/CodexFailureSwiftConsumer.swift").write_bytes(b"late mutation\n")
                return result

            with mock.patch.object(validation, "capture_apple_validation_sources", side_effect=capture):
                with self.assertRaisesRegex(ValueError, "changed during verification"):
                    verify_apple_validation_sources(fixture.repository, revision, evidence)
            alias = fixture.root / "evidence-alias"
            alias.symlink_to(evidence, target_is_directory=True)
            for root in (alias, Path("relative"), evidence / "device-raw" / ".."):
                with self.subTest(root=root), self.assertRaises(ValueError):
                    verify_apple_validation_sources(fixture.repository, revision, root)

    def test_exact_commit_and_tree_capture_only_consumer_allowlist_and_original_modes(self):
        for tree_revision in (False, True):
            with self.subTest(tree=tree_revision), validation_fixture() as fixture:
                revision = fixture.commit()
                selected = [_SWIFT, _OBJECTIVE_C, _APPLE + "TestApp/App.swift",
                            _APPLE + "TestApp/Nested/config.json"]
                expected = git_file_inventory(fixture.repository, revision, selected)
                if tree_revision:
                    revision = fixture.git("rev-parse", f"{revision}^{{tree}}")
                fixture.write(_SWIFT, "dirty current consumer\n")
                fixture.write(_APPLE + "TestApp/untracked.swift", "untracked\n")
                fixture.write(fixture.pin_path, "dirty invalid pins\n")

                result = capture_apple_validation_sources(fixture.repository, revision, fixture.output)

                self.assertEqual({"xcodeVersion": "26.6", "xcodeBuild": "17F113", "swiftVersion": "6.3.3"}, result)
                self.assertEqual(expected, regular_file_inventory(fixture.output))
                self.assertEqual(b"original Swift consumer\n", (fixture.output / _SWIFT).read_bytes())
                self.assertEqual(b"dirty current consumer\n", (fixture.repository / _SWIFT).read_bytes())
                self.assertEqual(b"dirty invalid pins\n", (fixture.repository / fixture.pin_path).read_bytes())
                self.assertEqual(0o755, stat.S_IMODE(os.stat(fixture.output / (_APPLE + "TestApp/App.swift")).st_mode))
                self.assertEqual(0o644, stat.S_IMODE(os.stat(fixture.output / _OBJECTIVE_C).st_mode))
                self.assertFalse((fixture.output / fixture.pin_path).exists())

    def test_missing_empty_symbolic_and_unsafe_selected_sources_reject_without_publication(self):
        mutations = {
            "missing Swift": lambda f: f.remove(_SWIFT),
            "missing Objective-C": lambda f: f.remove(_OBJECTIVE_C),
            "missing application": lambda f: f.remove(_APPLE + "TestApp"),
            "empty consumer": lambda f: f.write(_SWIFT, ""),
            "empty application member": lambda f: f.write(_APPLE + "TestApp/App.swift", ""),
            "symbolic consumer": lambda f: f.symlink(_OBJECTIVE_C),
            "symbolic application member": lambda f: f.symlink(_APPLE + "TestApp/App.swift"),
            "unsafe application path": lambda f: f.write(_APPLE + "TestApp/bad\nname.swift", "bad\n"),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label), validation_fixture() as fixture:
                mutate(fixture)
                revision = fixture.commit()
                with self.assertRaises(ValueError):
                    capture_apple_validation_sources(fixture.repository, revision, fixture.output)
                self.assertFalse(fixture.output.exists())

    def test_invalid_revision_and_toolchain_pins_reject_without_publication(self):
        with validation_fixture() as fixture:
            revision = fixture.commit()
            for invalid in ("HEAD", revision[:12], revision.upper(), "f" * 40, None):
                with self.subTest(revision=invalid), self.assertRaises(ValueError):
                    capture_apple_validation_sources(fixture.repository, invalid, fixture.output)
                self.assertFalse(fixture.output.exists())
        for pins in ("", "missing declarations\n", RepositoryFixture.pins("26.6", "bad", "6.3.3"),
                     RepositoryFixture.pins("26.6", "17F113", "6.3.3") +
                     'private val pinnedSwiftVersion = "6.3.3"\n'):
            with self.subTest(pins=pins), validation_fixture() as fixture:
                fixture.write(fixture.pin_path, pins)
                revision = fixture.commit()
                with self.assertRaises(ValueError):
                    capture_apple_validation_sources(fixture.repository, revision, fixture.output)
                self.assertFalse(fixture.output.exists())

    def test_output_must_be_fresh_external_normalized_and_non_symbolic(self):
        with validation_fixture() as fixture:
            revision = fixture.commit()
            existing = fixture.root / "existing"
            existing.mkdir()
            marker = existing / "marker"
            marker.write_bytes(b"preserve\n")
            alias = fixture.root / "alias"
            alias.symlink_to(existing, target_is_directory=True)
            for output in (Path("relative"), existing, fixture.repository / "capture", fixture.root,
                           alias / "capture", fixture.root / "missing" / ".." / "capture"):
                with self.subTest(output=output), self.assertRaises(ValueError):
                    capture_apple_validation_sources(fixture.repository, revision, output)
            self.assertEqual(b"preserve\n", marker.read_bytes())
            self.assertFalse((existing / "capture").exists())
            self.assertFalse((fixture.repository / "capture").exists())

    def test_changed_captured_blob_or_original_inventory_is_rejected_before_publish(self):
        for mutation in ("blob", "inventory"):
            with self.subTest(mutation=mutation), validation_fixture() as fixture:
                revision = fixture.commit()
                original_blob = shared.git_regular_blob_bytes
                original_inventory = shared.git_file_inventory
                calls = 0

                def blob(repository, tree, path, **kwargs):
                    raw = original_blob(repository, tree, path, **kwargs)
                    return b"tampered capture\n" if mutation == "blob" and path == _SWIFT else raw

                def inventory(*args, **kwargs):
                    nonlocal calls
                    calls += 1
                    value = original_inventory(*args, **kwargs)
                    return value[:-1] if mutation == "inventory" and calls > 1 else value

                with mock.patch.object(shared, "git_regular_blob_bytes", side_effect=blob), \
                        mock.patch.object(shared, "git_file_inventory", side_effect=inventory), \
                        mock.patch.object(shared, "publish_regular_tree") as publish:
                    with self.assertRaisesRegex(ValueError, "changed during capture"):
                        capture_apple_validation_sources(fixture.repository, revision, fixture.output)
                    publish.assert_not_called()
                self.assertFalse(fixture.output.exists())
                self.assertEqual(b"original Swift consumer\n", (fixture.repository / _SWIFT).read_bytes())


if __name__ == "__main__":
    unittest.main()
