"""Synthetic retained device traces; no native command, source or host admission."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from ci.products import sdk_apple_device_evidence as device
from ci.products.inventory import regular_file_inventory


class SdkAppleDeviceEvidenceTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="apple-device-evidence-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.work = "/original/device-execution"
        self.application = "/original/device-consumer/CodexAgentTestApp"
        self.developer = "/Applications/Xcode_26.6.app/Contents/Developer"
        self.write("device-test-application/CodexAgentTestApp.xcodeproj/project.pbxproj", b"original project\n")
        self.write("device-test-application/App.swift", b"original app\n")
        self.write("device-package/Package.swift", b"original manifest\n")
        self.write("device-package/Sources/Api.swift", b"original package source\n")
        self.write("device-archive/Products/Applications/CodexAgentTestApp.app/CodexAgentTestApp", b"synthetic archive\n")
        self.write("device-raw/xcodebuild/stdout.bin", b"\x00\xfforiginal output\n")
        self.write("device-raw/xcodebuild/stderr.bin", b"")
        self.execution = {
            "schemaVersion": 1,
            "command": ["/usr/bin/xcodebuild", "-project", "CodexAgentTestApp.xcodeproj",
                "-scheme", "CodexAgentTestApp", "-configuration", "Release",
                "-destination", "generic/platform=iOS", "-derivedDataPath", self.work + "/derived-data",
                "-archivePath", self.work + "/CodexAgentTestApp.xcarchive", "ARCHS=arm64",
                "CODE_SIGNING_ALLOWED=NO", "SKIP_INSTALL=NO", "clean", "archive"],
            "workingDirectory": self.application,
            "environment": {"DEVELOPER_DIR": self.developer, "LANG": "C", "LC_ALL": "C"},
            "exitCode": 0,
        }
        self.save_execution()
        self.expected_application = regular_file_inventory(self.root / "device-test-application")
        self.expected_package = regular_file_inventory(self.root / "device-package")

    def write(self, relative, raw):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)

    def save_execution(self):
        # Kotlin emits pretty JSON, not the canonical product JSON encoding.
        self.write("device-raw/xcodebuild/execution.json", (json.dumps(self.execution, indent=4) + "\n").encode())

    def verify(self, **changes):
        arguments = dict(original_work_directory=self.work,
            original_test_application_directory=self.application, developer_directory=self.developer,
            expected_test_application_inventory=self.expected_application,
            expected_package_inventory=self.expected_package)
        return device.verify_apple_device_evidence(self.root, **{**arguments, **changes})

    def test_exact_success_preserves_all_original_bytes_and_empty_streams(self):
        before = regular_file_inventory(self.root, allow_empty=True)
        result = self.verify()
        self.assertEqual({name: regular_file_inventory(self.root / name, allow_empty=name == "device-raw")
            for name in ("device-raw", "device-archive", "device-test-application", "device-package")}, result)
        self.assertEqual(before, regular_file_inventory(self.root, allow_empty=True))
        self.assertEqual(self.expected_package, result["device-package"])

    def test_command_environment_directory_schema_and_failure_must_match_exactly(self):
        original = json.loads(json.dumps(self.execution))
        mutations = [
            {"schemaVersion": True}, {"schemaVersion": 2}, {"exitCode": True}, {"exitCode": None},
            {"exitCode": 1}, {"workingDirectory": "/unrelated/CodexAgentTestApp"},
            {"environment": {**original["environment"], "EXTRA": "override"}},
            {"environment": {**original["environment"], "DEVELOPER_DIR": "/wrong/Xcode"}},
            {"environment": {**original["environment"], "LC_ALL": "en_US"}},
            {"command": original["command"] + ["OTHER=YES"]},
            {"command": ["xcodebuild", *original["command"][1:]]},
            {"command": [part.replace("generic/platform=iOS", "generic/platform=iOS Simulator")
                         for part in original["command"]]},
            {"command": [part.replace(self.work, "/unrelated/work") for part in original["command"]]},
            {"unexpected": "field"},
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.execution = {**original, **mutation}
                self.save_execution()
                with self.assertRaises(ValueError):
                    self.verify()

    def test_original_path_expectations_are_not_inferred_from_retained_trace(self):
        for field in ("original_work_directory", "original_test_application_directory", "developer_directory"):
            for value in (None, "relative", "/original/../elsewhere", "//original/path", "/bad\npath"):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    self.verify(**{field: value})
        with self.assertRaises(ValueError):
            self.verify(original_work_directory="/original/device-consumer")
        with self.assertRaises(ValueError):
            self.verify(original_test_application_directory="/original/device-consumer/OtherApp")

    def test_independent_input_inventories_are_mandatory_and_exact(self):
        for field, original in (("expected_test_application_inventory", self.expected_application),
                                ("expected_package_inventory", self.expected_package)):
            for value in (None, [], list(reversed(original)), original[:-1],
                          [{**original[0], "sha256": "sha256:" + "0" * 64}, *original[1:]]):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    self.verify(**{field: value})
        self.write("device-package/Sources/Api.swift", b"self-consistent unrelated package\n")
        with self.assertRaisesRegex(ValueError, "independently authenticated"):
            self.verify()

    def test_extra_missing_and_symbolic_raw_members_and_empty_archive_reject(self):
        raw = self.root / "device-raw/xcodebuild/stderr.bin"
        raw.unlink()
        with self.assertRaises(ValueError):
            self.verify()
        raw.symlink_to(self.root / "device-package/Package.swift")
        with self.assertRaises(ValueError):
            self.verify()
        raw.unlink()
        raw.write_bytes(b"")
        extra = self.root / "device-raw/extra"
        extra.write_bytes(b"extra")
        with self.assertRaises(ValueError):
            self.verify()
        extra.unlink()
        archive = self.root / "device-archive/Products/Applications/CodexAgentTestApp.app/CodexAgentTestApp"
        archive.unlink()
        with self.assertRaises(ValueError):
            self.verify()

    def test_raw_or_retained_input_mutation_during_replay_rejects(self):
        original_load = device.load_json_bytes
        for relative in ("device-raw/xcodebuild/stdout.bin", "device-package/Sources/Api.swift",
                         "device-test-application/App.swift",
                         "device-archive/Products/Applications/CodexAgentTestApp.app/CodexAgentTestApp"):
            with self.subTest(relative=relative):
                path = self.root / relative
                before = path.read_bytes()

                def mutate(raw):
                    parsed = original_load(raw)
                    path.write_bytes(b"late mutation\n")
                    return parsed

                try:
                    with mock.patch.object(device, "load_json_bytes", side_effect=mutate):
                        with self.assertRaisesRegex(ValueError, "changed during replay"):
                            self.verify()
                finally:
                    path.write_bytes(before)


if __name__ == "__main__":
    unittest.main()
