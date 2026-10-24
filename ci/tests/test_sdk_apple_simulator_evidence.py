"""Synthetic simulator binding only; no native execution or hosted authority."""

from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

from ci.products import sdk_apple_simulator_evidence as simulator
from ci.products.inventory import regular_file_inventory


class AppleSimulatorEvidenceTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="apple-simulator-evidence-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.runtime = "com.apple.CoreSimulator.SimRuntime.iOS-26-5"
        self.device_type = "com.apple.CoreSimulator.SimDeviceType.iPhone-17"
        self.udid = "12345678-ABCD-1234-ABCD-123456789012"
        self.report = {"devices": {self.runtime: [{
            "udid": self.udid, "isAvailable": True, "state": "Booted",
            "deviceTypeIdentifier": self.device_type, "name": "iPhone 17",
            "dataPath": "/original/simulator/data", "lastBootedAt": "external observation",
        }]}, "futureOptionalField": "preserved"}
        self.execution = {
            "schemaVersion": 1, "exitCode": 0, "workingDirectory": "/original/CodexAgentPackage",
            "environment": {"LC_ALL": "C", "LANG": "C"},
            "command": ["xcodebuild", "-scheme", "CodexAgent-Package", "-destination",
                        "platform=iOS Simulator,id=" + self.udid, "-derivedDataPath", "/original/derived",
                        "-resultBundlePath", "/original/swift-authentication-tests.xcresult",
                        "CODE_SIGNING_ALLOWED=NO", "test"],
        }
        self.write("reports/simulator-devices.json", self.report)
        self.write("xctest-raw/successful-attempt.json", {"schemaVersion": 1, "attempt": 0})
        for attempt in (0,):
            for operation in ("xcodebuild", "summary", "tests"):
                self.write(f"xctest-raw/attempt-{attempt}/{operation}/execution.json", self.execution)
                directory = self.root / f"xctest-raw/attempt-{attempt}/{operation}"
                (directory / "stdout.bin").write_bytes(b"raw\x00output\n")
                (directory / "stderr.bin").write_bytes(b"")

    def write(self, relative, value):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2) + "\n")

    def verify(self, **changes):
        return simulator.verify_apple_simulator_evidence(self.root, **{
            "expected_runtime_identifier": self.runtime,
            "expected_device_type_identifier": self.device_type, **changes,
        })

    def test_successful_attempt_binding_preserves_optional_fields_and_empty_raw(self):
        for attempt in (0, 1):
            with self.subTest(attempt=attempt):
                if attempt == 1:
                    shutil.copytree(self.root / "xctest-raw/attempt-0", self.root / "xctest-raw/attempt-1")
                self.write("xctest-raw/successful-attempt.json", {"schemaVersion": 1, "attempt": attempt})
                before = regular_file_inventory(self.root, allow_empty=True)
                result = self.verify()
                self.assertEqual(set(result), {"simulatorReport", "xctestRaw"})
                self.assertEqual(result["xctestRaw"], regular_file_inventory(self.root / "xctest-raw", allow_empty=True))
                self.assertEqual(before, regular_file_inventory(self.root, allow_empty=True))

    def test_pin_mismatch_unavailable_unbooted_missing_and_duplicate_devices_reject(self):
        for change in ({"isAvailable": False}, {"isAvailable": 1}, {"state": "Shutdown"},
                       {"state": None}, {"deviceTypeIdentifier": "another-type"}, {"udid": "another-device"}):
            with self.subTest(change=change):
                report = deepcopy(self.report)
                report["devices"][self.runtime][0].update(change)
                self.write("reports/simulator-devices.json", report)
                with self.assertRaises(ValueError):
                    self.verify()
        for other_runtime in (self.runtime, "com.apple.CoreSimulator.SimRuntime.iOS-27-0"):
            report = deepcopy(self.report)
            report["devices"].setdefault(other_runtime, []).append(deepcopy(report["devices"][self.runtime][0]))
            self.write("reports/simulator-devices.json", report)
            with self.assertRaisesRegex(ValueError, "duplicate UDID"):
                self.verify()
        self.write("reports/simulator-devices.json", self.report)
        for changes in ({"expected_runtime_identifier": "com.apple.CoreSimulator.SimRuntime.iOS-27-0"},
                        {"expected_device_type_identifier": "com.apple.CoreSimulator.SimDeviceType.iPhone-18"},
                        {"expected_runtime_identifier": ""}, {"expected_device_type_identifier": None}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.verify(**changes)

    def test_marker_and_successful_destination_are_strict(self):
        for marker in ({"schemaVersion": True, "attempt": 0}, {"schemaVersion": 1, "attempt": True},
                       {"schemaVersion": 1, "attempt": 2}, {"schemaVersion": 1, "attempt": 0, "extra": 1}):
            self.write("xctest-raw/successful-attempt.json", marker)
            with self.assertRaises(ValueError):
                self.verify()
        self.write("xctest-raw/successful-attempt.json", {"schemaVersion": 1, "attempt": 0})
        command = self.execution["command"]
        for change in ({"exitCode": True}, {"exitCode": 1}, {"schemaVersion": True}, {"extra": 1},
                       {"command": command + ["-destination", command[4]]},
                       {"command": ["xcodebuild", "-destination"]},
                       {"command": ["xcodebuild", "-destination", command[4] + ",name=other"]},
                       {"command": ["not-xcodebuild", "-destination", command[4]]}):
            with self.subTest(change=change):
                self.write("xctest-raw/attempt-0/xcodebuild/execution.json", {**self.execution, **change})
                with self.assertRaises(ValueError):
                    self.verify()

    def test_report_schema_missing_and_symbolic_evidence_reject(self):
        for report in ({}, {"devices": []}, {"devices": {self.runtime: {}}},
                       {"devices": {self.runtime: []}}, {"devices": {self.runtime: [{"udid": None}]}}):
            self.write("reports/simulator-devices.json", report)
            with self.assertRaises(ValueError):
                self.verify()
        report = self.root / "reports/simulator-devices.json"
        report.unlink()
        report.symlink_to(self.root / "xctest-raw/successful-attempt.json")
        with self.assertRaises(ValueError):
            self.verify()

    def test_late_report_or_raw_mutation_rejects(self):
        original = simulator._read
        for relative in ("reports/simulator-devices.json", "xctest-raw/attempt-0/xcodebuild/stderr.bin"):
            with self.subTest(relative=relative):
                path = self.root / relative
                contents = path.read_bytes()

                def read(target):
                    value = original(target)
                    if target == self.root / "reports/simulator-devices.json":
                        path.write_bytes(contents + b" ")
                    return value

                try:
                    with mock.patch.object(simulator, "_read", side_effect=read):
                        with self.assertRaisesRegex(ValueError, "changed during verification"):
                            self.verify()
                finally:
                    path.write_bytes(contents)


if __name__ == "__main__":
    unittest.main()
