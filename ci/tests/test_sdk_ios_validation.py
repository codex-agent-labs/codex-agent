"""Property translation only: synthetic paths are not authenticated Apple inputs."""

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sdk_ios_validation import validation_properties


class SdkIosValidationTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sdk-ios-validation-mapper-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.package = self.root / "original-package"
        self.contract = self.root / "original-contract"
        self.application = self.root / "original-test-application"
        for stage in (self.package, self.contract, self.application):
            stage.mkdir()
            (stage / "original.bin").write_bytes(b"unchanged original fixture\n")
        self.compatibility = self.root / "sdk-compatibility.json"
        self.compatibility.write_bytes(b"opaque caller-authenticated compatibility fixture\n")
        self.arguments = dict(target="ios-arm64", sdk_version="0.8.1", contract_version="0.8.0",
            candidate_tree="a" * 40, package_stage=self.package, contract_binary_stage=self.contract,
            sdk_compatibility=self.compatibility, test_application=self.application)

    def translate(self, **changes):
        return validation_properties(**{**self.arguments, **changes})

    def test_both_exact_targets_forward_only_original_validation_properties(self):
        before = {path.relative_to(self.root): path.read_bytes()
                  for path in self.root.rglob("*") if path.is_file()}
        for target in ("ios-arm64", "ios-simulator-arm64"):
            with self.subTest(target=target):
                self.assertEqual({
                    "codexAgent.product": "sdk", "codexAgent.component": "sdk-ios",
                    "codexAgent.phase": "validation", "codexAgent.target": target,
                    "codexAgent.iosValidationPackageStage": str(self.package),
                    "codexAgent.contractBinaryStage": str(self.contract),
                    "codexAgent.sdkCompatibilityFile": str(self.compatibility),
                    "codexAgent.iosValidationTestApplicationDirectory": str(self.application),
                    "codexAgent.sdkVersion": "0.8.1", "codexAgent.contractVersion": "0.8.0",
                    "codexAgent.candidateTree": "a" * 40,
                }, self.translate(target=target))
        self.assertEqual(before, {path.relative_to(self.root): path.read_bytes()
                                 for path in self.root.rglob("*") if path.is_file()})

    def test_invalid_target_versions_and_tree_are_not_coerced(self):
        cases = [("target", value) for value in (None, [], "ios", "iosArm64", "macos-arm64")]
        cases += [(field, value) for field in ("sdk_version", "contract_version")
                  for value in (None, 8, "", "0.8", " 0.8.0", "latest")]
        cases += [("candidate_tree", value) for value in
                  (None, 40, "", "A" * 40, "a" * 39, "a" * 64, "../original-package")]
        for field, value in cases:
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.translate(**{field: value})

    def test_directory_inputs_reject_missing_wrong_type_relative_alias_and_escape(self):
        alias = self.root / "package-alias"
        alias.symlink_to(self.package, target_is_directory=True)
        parent_alias = self.root / "parent-alias"
        parent_alias.symlink_to(self.root, target_is_directory=True)
        for field in ("package_stage", "contract_binary_stage", "test_application"):
            for value in (None, str(self.package), Path("relative"), self.root / "missing",
                          self.compatibility, alias, parent_alias / "original-package",
                          self.package / ".." / "original-contract"):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    self.translate(**{field: value})

    def test_both_targets_require_the_caller_test_application(self):
        for target in ("ios-arm64", "ios-simulator-arm64"):
            arguments = {**self.arguments, "target": target}
            del arguments["test_application"]
            with self.subTest(target=target), self.assertRaises(TypeError):
                validation_properties(**arguments)
            with self.subTest(target=target, application=None), self.assertRaises(ValueError):
                self.translate(target=target, test_application=None)

    def test_compatibility_requires_nonempty_regular_original_file(self):
        empty = self.root / "empty.json"
        empty.write_bytes(b"")
        alias = self.root / "compatibility-alias"
        alias.symlink_to(self.compatibility)
        parent_alias = self.root / "parent-alias"
        parent_alias.symlink_to(self.root, target_is_directory=True)
        for value in (None, str(self.compatibility), Path("relative.json"), self.root / "missing",
                      self.package, empty, alias, parent_alias / self.compatibility.name,
                      self.package / ".." / self.compatibility.name):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.translate(sdk_compatibility=value)


if __name__ == "__main__":
    unittest.main()
