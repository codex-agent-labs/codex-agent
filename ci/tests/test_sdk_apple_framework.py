"""Byte-inventory tests only; native Apple inspection remains in Gradle."""

from pathlib import Path
import plistlib
import tempfile
import unittest
from unittest.mock import patch

from ci.products import sdk_apple_framework as framework


class SdkAppleFrameworkInventoryTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sdk-apple-framework-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.inputs = {
            "ios-arm64": self._framework("device", "iPhoneOS"),
            "ios-simulator-arm64": self._framework("simulator", "iPhoneSimulator"),
        }

    def _framework(self, name: str, platform: str) -> Path:
        root = self.root / name / "CodexAgent.framework"
        members = {
            "CodexAgent": b"static archive bytes\x00\xff",
            "Headers/CodexAgent.h": b"void codex_agent(void);\n",
            "Modules/module.modulemap": b"framework module CodexAgent {}\n",
            "Modules/CodexAgent.swiftmodule/arm64.swiftinterface": b"// swift interface\n",
            "Info.plist": plistlib.dumps({"CFBundleSupportedPlatforms": [platform]}),
        }
        for relative, contents in members.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(contents)
        return root

    def test_exact_pair_has_deterministic_complete_byte_inventory_only(self):
        first = framework.inspect_apple_frameworks(self.inputs)
        self.assertEqual(first, framework.inspect_apple_frameworks(dict(reversed(self.inputs.items()))))
        self.assertEqual(1, first["schemaVersion"])
        self.assertEqual("sdk-apple-framework-inventory", first["kind"])
        self.assertEqual(
            ["ios-arm64", "ios-simulator-arm64"],
            [value["target"] for value in first["targets"]],
        )
        self.assertEqual(
            sorted(path.relative_to(self.inputs["ios-arm64"]).as_posix()
                   for path in self.inputs["ios-arm64"].rglob("*") if path.is_file()),
            [record["relativePath"] for record in first["targets"][0]["files"]],
        )
        for forbidden in ("producer", "compatibility", "signature", "receipt", "execution", "result"):
            self.assertNotIn(forbidden, first)

    def test_exact_pair_normalized_paths_and_nonoverlap_are_required(self):
        for value in (
            {"ios-arm64": self.inputs["ios-arm64"]},
            {**self.inputs, "macos-arm64": self.inputs["ios-arm64"]},
        ):
            with self.subTest(keys=set(value)), self.assertRaisesRegex(ValueError, "exact two targets"):
                framework.inspect_apple_frameworks(value)

        relative = Path("device/CodexAgent.framework")
        with self.assertRaisesRegex(ValueError, "path is invalid"):
            framework.inspect_apple_frameworks({**self.inputs, "ios-arm64": relative})
        with self.assertRaisesRegex(ValueError, "must not overlap"):
            framework.inspect_apple_frameworks({key: self.inputs["ios-arm64"] for key in self.inputs})
        alias = self.root / "alias/CodexAgent.framework"
        alias.parent.mkdir()
        alias.symlink_to(self.inputs["ios-arm64"], target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "normalized and non-symbolic"):
            framework.inspect_apple_frameworks({**self.inputs, "ios-arm64": alias})

    def test_required_members_platform_and_all_regular_files_are_strict(self):
        header = self.inputs["ios-arm64"] / "Headers/CodexAgent.h"
        header.unlink()
        with self.assertRaisesRegex(ValueError, "required member"):
            framework.inspect_apple_frameworks(self.inputs)
        header.write_bytes(b"void codex_agent(void);\n")

        plist = self.inputs["ios-simulator-arm64"] / "Info.plist"
        plist.write_bytes(plistlib.dumps({"CFBundleSupportedPlatforms": ["iPhoneOS"]}))
        with self.assertRaisesRegex(ValueError, "platform is invalid"):
            framework.inspect_apple_frameworks(self.inputs)
        plist.write_bytes(plistlib.dumps({"CFBundleSupportedPlatforms": ["iPhoneSimulator"]}))

        linked = self.inputs["ios-arm64"] / "linked"
        linked.symlink_to(header)
        with self.assertRaisesRegex(ValueError, "unsafe"):
            framework.inspect_apple_frameworks(self.inputs)
        linked.unlink()
        (self.inputs["ios-arm64"] / "empty").write_bytes(b"")
        with self.assertRaisesRegex(ValueError, "empty file"):
            framework.inspect_apple_frameworks(self.inputs)

    def test_late_input_mutation_is_rejected(self):
        original = plistlib.loads

        def mutate(contents):
            (self.inputs["ios-arm64"] / "Headers/CodexAgent.h").write_bytes(b"changed\n")
            return original(contents)

        with patch.object(framework.plistlib, "loads", side_effect=mutate), \
                self.assertRaisesRegex(ValueError, "changed during inventory"):
            framework.inspect_apple_frameworks(self.inputs)


if __name__ == "__main__":
    unittest.main()
