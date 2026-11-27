"""Binary-only iOS package mapping, not original evidence or Apple acceptance."""

from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sdk_ios_phase as mapper  # noqa: E402


CONTRACT = ("contract", "contract", "binary", "common")
SDK = ("sdk", "sdk-ios", "binary", "ios")


class SdkIosBinaryPackageTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sdk-ios-binary-package-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.plan = dict(product="sdk", component="sdk-ios", phase="package", target="ios")
        self.request = self.root / "sdk-compatibility-request.json"
        self.request.write_bytes(b"caller-authenticated S858 fixture\n")
        self.records = {}
        for identity, version in ((CONTRACT, "0.2.0"), (SDK, "0.8.0")):
            stage = self.root / "-".join(identity)
            stage.mkdir()
            self.records[identity] = {"stage": stage,
                "receipt": dict(zip(("product", "component", "phase", "target"), identity), productVersion=version)}
        self.calls = []

    def predecessor(self, *identity):
        self.calls.append(identity)
        self.assertIn(identity, self.records, "No native, old distribution or package predecessor may be inferred")
        return self.records[identity]

    def translate(self, **changes):
        return mapper.binary_package_properties(changes.get("plan", self.plan),
            sdk_version=changes.get("sdk_version", "0.8.0"), predecessor=self.predecessor,
            compatibility_request=changes.get("compatibility_request", self.request))

    def test_exact_binary_only_properties_and_independent_original_versions(self):
        before = deepcopy(self.records)
        original = self.request.read_bytes()
        self.assertEqual({
            "codexAgent.product": "sdk", "codexAgent.component": "sdk-ios",
            "codexAgent.phase": "package", "codexAgent.target": "ios",
            "codexAgent.sdkIosBinaryStageRoot": str(self.records[SDK]["stage"]),
            "codexAgent.contractBinaryStage": str(self.records[CONTRACT]["stage"]),
            "codexAgent.contractVersion": "0.2.0",
            "codexAgent.sdkCompatibilityRequest": str(self.request),
            "codexAgent.iosPackageFromBinary": "true",
        }, self.translate())
        self.assertCountEqual([SDK, CONTRACT], self.calls)
        self.assertEqual(2, len(self.calls))
        self.assertEqual(before, self.records)
        self.assertEqual(original, self.request.read_bytes())
        # No old distribution, native tests, expected proof or caller framework
        # directories exist: Gradle owns the imported binary snapshot paths.
        self.assertEqual(3, len(list(self.root.iterdir())))

    def test_bad_package_identity_and_elected_version_reject_before_callback(self):
        for changes in ({"product": "runtime"}, {"component": "sdk-core"},
                        {"phase": "binary"}, {"phase": "metadata"}, {"target": "desktop"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.translate(plan={**self.plan, **changes})
            self.assertEqual([], self.calls)
        for version in ("invalid", "0.8", "", None):
            with self.subTest(version=version), self.assertRaises(ValueError):
                self.translate(sdk_version=version)
            self.assertEqual([], self.calls)

    def test_crosspaired_original_identity_or_sdk_version_is_rejected(self):
        for identity in (CONTRACT, SDK):
            original = self.records[identity]["receipt"]
            for field, value in (("product", "runtime"), ("component", "other"), ("phase", "package"),
                                 ("target", "other"), ("productVersion", "invalid"), ("productVersion", None)):
                self.records[identity]["receipt"] = {**original, field: value}
                with self.subTest(identity=identity, field=field, value=value), self.assertRaises(ValueError):
                    self.translate()
            self.records[identity]["receipt"] = original
        self.records[SDK]["receipt"] = {**self.records[SDK]["receipt"], "productVersion": "0.8.1"}
        with self.assertRaisesRegex(ValueError, "version"):
            self.translate()

    def test_noncanonical_missing_symbolic_and_wrong_type_binary_stage_paths_reject(self):
        (self.root / "unused").mkdir()
        for identity in (CONTRACT, SDK):
            original = self.records[identity]["stage"]
            link = self.root / (identity[0] + "-link")
            link.symlink_to(original, target_is_directory=True)
            for invalid in (Path("relative"), self.root / "missing", self.root / "unused/../" / original.name,
                            link, str(original), self.request):
                self.records[identity]["stage"] = invalid
                with self.subTest(identity=identity, path=invalid), self.assertRaises(ValueError):
                    self.translate()
            self.records[identity]["stage"] = original

    def test_request_must_be_nonempty_regular_absolute_and_normalized(self):
        (self.root / "unused").mkdir()
        empty = self.root / "empty"
        empty.write_bytes(b"")
        link = self.root / "request-link"
        link.symlink_to(self.request)
        parent = self.root / "parent-link"
        parent.symlink_to(self.root, target_is_directory=True)
        for invalid in (Path("relative"), self.root / "missing", self.root / "unused/../" / self.request.name,
                        empty, link, parent / self.request.name, str(self.request), self.root):
            with self.subTest(path=invalid), self.assertRaises(ValueError):
                self.translate(compatibility_request=invalid)


if __name__ == "__main__":
    unittest.main()
