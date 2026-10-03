"""Synthetic raw observations only; no tools, source authentication or host proof."""

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci.products import sdk_apple_toolchain_evidence as toolchain
from ci.products.inventory import regular_file_inventory


class AppleToolchainEvidenceTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="apple-toolchain-evidence-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.expected = {"xcodeVersion": "26.6", "xcodeBuild": "17G12", "swiftVersion": "6.3"}
        self.cwd = "/original/checkout/codex-agent-runtime-ios"
        self.outputs = {
            "xcode": b"Xcode 26.6\nBuild version 17G12\n",
            "swift": b"Apple Swift version 6.3 (swiftlang-example clang-example)\nTarget: arm64-apple-macosx26.0\n",
            "clang": b"Apple clang version 17.0.0 (clang-example)\nTarget: arm64-apple-darwin\n",
        }
        self.report = {"toolchain": {**self.expected, "clangVersion": self.outputs["clang"].decode().splitlines()[0]}}
        self.write_json("reports/compiler-evidence.json", self.report)
        self.executions = {}
        for name, command in (
            ("xcode", ["/usr/bin/xcodebuild", "-version"]),
            ("swift", ["/usr/bin/xcrun", "swift", "--version"]),
            ("clang", ["/usr/bin/xcrun", "clang", "--version"]),
        ):
            execution = {"schemaVersion": 1, "command": command, "workingDirectory": self.cwd,
                         "environment": {"LC_ALL": "C", "LANG": "C"}, "exitCode": 0}
            self.executions[name] = execution
            self.write_json(f"compiler-raw/toolchain/{name}/execution.json", execution)
            self.write(f"compiler-raw/toolchain/{name}/stdout.bin", self.outputs[name])
            self.write(f"compiler-raw/toolchain/{name}/stderr.bin", b"")
        for name in ("xcode", "swift"):
            self.write(f"toolchain/{name}.txt", self.outputs[name])

    def write(self, relative, contents):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)

    def write_json(self, relative, value):
        self.write(relative, (json.dumps(value, indent=4) + "\n").encode())

    def verify(self, **overrides):
        arguments = dict(expected_toolchain=self.expected, original_working_directory=self.cwd)
        return toolchain.verify_apple_toolchain_evidence(self.root, **{**arguments, **overrides})

    def test_original_observations_match_pins_and_remain_unchanged(self):
        before = regular_file_inventory(self.root, allow_empty=True)
        result = self.verify()
        self.assertEqual(set(result), {"toolchain", "compiler-raw/toolchain", "compiler-report"})
        self.assertEqual(len(result["compiler-raw/toolchain"]), 9)
        self.assertEqual(result["toolchain"], regular_file_inventory(self.root / "toolchain"))
        self.assertEqual(before, regular_file_inventory(self.root, allow_empty=True))

    def test_self_declared_report_and_raw_versions_cannot_replace_pins(self):
        self.report["toolchain"]["xcodeVersion"] = "27.0"
        self.write_json("reports/compiler-evidence.json", self.report)
        self.write("toolchain/xcode.txt", b"Xcode 27.0\nBuild version 17G12\n")
        self.write("compiler-raw/toolchain/xcode/stdout.bin", b"Xcode 27.0\nBuild version 17G12\n")
        with self.assertRaisesRegex(ValueError, "caller pins"):
            self.verify()

    def test_each_retained_or_raw_version_and_clang_mismatch_rejects(self):
        mutations = {
            "toolchain/xcode.txt": b"Xcode 26.6\nBuild version 17G99\n",
            "toolchain/swift.txt": b"Apple Swift version 6.30\n",
            "compiler-raw/toolchain/xcode/stdout.bin": b"Xcode 26.6\nXcode 27.0\nBuild version 17G12\n",
            "compiler-raw/toolchain/swift/stdout.bin": b"Apple Swift version 6.3\nApple Swift version 6.3\n",
            "compiler-raw/toolchain/clang/stdout.bin": b"Apple clang version OTHER\n",
        }
        for relative, changed in mutations.items():
            with self.subTest(relative=relative):
                path = self.root / relative
                original = path.read_bytes()
                self.write(relative, changed)
                with self.assertRaises(ValueError):
                    self.verify()
                self.write(relative, original)

    def test_fixed_commands_cwd_environment_and_success_are_required(self):
        original = self.executions["xcode"]
        for changes in (
            {"schemaVersion": True}, {"schemaVersion": 2}, {"exitCode": None}, {"exitCode": True},
            {"exitCode": 1}, {"workingDirectory": None}, {"workingDirectory": "/different/producer"},
            {"command": ["xcodebuild", "-version"]}, {"command": original["command"] + ["extra"]},
            {"environment": {"LC_ALL": "C", "LANG": "C", "EXTRA": "value"}}, {"unknown": "field"},
        ):
            with self.subTest(changes=changes):
                self.write_json("compiler-raw/toolchain/xcode/execution.json", {**original, **changes})
                with self.assertRaises(ValueError):
                    self.verify()
        self.write_json("compiler-raw/toolchain/xcode/execution.json", original)

    def test_exact_inventory_and_safe_files(self):
        extra = self.root / "toolchain/extra.txt"
        extra.write_bytes(b"extra")
        with self.assertRaises(ValueError):
            self.verify()
        extra.unlink()
        path = self.root / "compiler-raw/toolchain/swift/stderr.bin"
        path.unlink()
        with self.assertRaises(ValueError):
            self.verify()
        path.symlink_to(self.root / "toolchain/swift.txt")
        with self.assertRaises(ValueError):
            self.verify()

    def test_malformed_expected_identity_report_and_utf8_reject(self):
        for expected in ({}, {**self.expected, "xcodeBuild": "bad"}, {**self.expected, "swiftVersion": "6.*"},
                         {**self.expected, "other": "unknown"}):
            with self.subTest(expected=expected):
                with self.assertRaises(ValueError):
                    self.verify(expected_toolchain=expected)
        with self.assertRaises(ValueError):
            self.verify(original_working_directory="relative/path")
        report = deepcopy(self.report)
        report["toolchain"]["unknown"] = "field"
        self.write_json("reports/compiler-evidence.json", report)
        with self.assertRaises(ValueError):
            self.verify()
        self.write_json("reports/compiler-evidence.json", self.report)
        self.write("toolchain/swift.txt", b"\xff")
        with self.assertRaisesRegex(ValueError, "UTF-8"):
            self.verify()

    def test_late_original_mutation_rejects(self):
        original = toolchain._versions
        def mutate(*arguments):
            original(*arguments)
            self.write("compiler-raw/toolchain/clang/stderr.bin", b"changed after initial inventory")
        with patch.object(toolchain, "_versions", side_effect=mutate):
            with self.assertRaisesRegex(ValueError, "changed during replay"):
                self.verify()


if __name__ == "__main__":
    unittest.main()
