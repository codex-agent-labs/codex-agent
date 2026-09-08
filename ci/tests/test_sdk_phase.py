"""SDK input translation fixtures, not authenticated products or execution."""

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sdk_phase import properties, route


class SdkPhaseTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sdk-phase-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.request = self.root / "compatibility-request.json"
        self.request.write_bytes(b"caller authenticated request fixture\n")
        self.calls = []
        self.records = {}
        for identity, version in (
            (("contract", "contract", "binary", "common"), "0.2.0"),
            (("runtime", "node-js", "package", "node-js"), "0.2.1"),
            (("runtime", "node-js", "validation", "node-js-binding"), "0.2.3"),
            (("sdk", "javascript", "package", "node"), "0.3.0"),
        ):
            stage = self.root / "-".join(identity)
            stage.mkdir()
            self.records[identity] = {"stage": stage, "receiptPath": stage / "original-receipt.json",
                                      "receipt": dict(zip(("product", "component", "phase", "target"), identity),
                                                      productVersion=version)}

    def plan(self, phase):
        return {"product": "sdk", "component": "javascript", "phase": phase, "target": "node",
                "productVersion": "0.3.0", "runtimeVersion": "0.2.9"}

    def predecessor(self, *identity):
        self.calls.append(identity)
        return self.records[identity]

    def test_package_consumes_exact_contract_runtime_package_and_authenticated_request(self):
        result = properties(self.plan("package"), predecessor=self.predecessor, compatibility_request=self.request)
        self.assertEqual({
            "codexAgent.contractBinaryStage": str(self.records[("contract", "contract", "binary", "common")]["stage"]),
            "codexAgent.runtimePackageStage": str(self.records[("runtime", "node-js", "package", "node-js")]["stage"]),
            "codexAgent.runtimePackageVersion": "0.2.1",
            "codexAgent.sdkCompatibilityRequest": str(self.request),
        }, result)
        self.assertEqual([("contract", "contract", "binary", "common"),
                          ("runtime", "node-js", "package", "node-js")], self.calls)

    def test_validation_uses_original_binding_version_and_sdk_without_package_reconstruction_inputs(self):
        result = properties(self.plan("validation"), predecessor=self.predecessor)
        self.assertEqual({
            "codexAgent.contractBinaryStage": str(self.records[("contract", "contract", "binary", "common")]["stage"]),
            "codexAgent.runtimeBindingValidationStage": str(self.records[("runtime", "node-js", "validation", "node-js-binding")]["stage"]),
            "codexAgent.runtimeBindingValidationVersion": "0.2.3",
            "codexAgent.sdkPackageStageRoot": str(self.records[("sdk", "javascript", "package", "node")]["stage"]),
        }, result)
        self.assertEqual([("contract", "contract", "binary", "common"),
                          ("runtime", "node-js", "validation", "node-js-binding"),
                          ("sdk", "javascript", "package", "node")], self.calls)

    def test_only_two_implemented_routes_exist_and_neither_creates_a_toolchain_profile(self):
        expected = {"runner": "ubuntu-24.04", "runnerOs": "Linux", "runnerArch": "X64",
                    "toolchainProfile": None, "producerRole": None, "supervisor": None}
        for phase in ("package", "validation"):
            self.assertEqual(expected, route({**self.plan(phase), "runner": "injected"}))
        for changes in ({"phase": "binary"}, {"phase": "metadata"}, {"component": "sdk-javascript"},
                        {"component": "sdk-core"}, {"component": "python"}, {"target": "node-js"},
                        {"target": "linux-x64"}, {"product": "runtime"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                route({**self.plan("package"), **changes})

    def test_missing_unsafe_or_unused_compatibility_request_is_rejected(self):
        link = self.root / "request-link"
        link.symlink_to(self.request)
        empty = self.root / "empty"
        empty.write_bytes(b"")
        for path in (None, Path("relative.json"), self.root / "absent", self.root, link, empty):
            with self.subTest(path=path), self.assertRaises(ValueError):
                properties(self.plan("package"), predecessor=self.predecessor, compatibility_request=path)
        self.assertEqual([], self.calls)
        with self.assertRaisesRegex(ValueError, "does not consume"):
            properties(self.plan("validation"), predecessor=self.predecessor, compatibility_request=self.request)

    def test_crosspaired_receipt_invalid_version_and_unsafe_stage_fail_closed(self):
        identity = ("contract", "contract", "binary", "common")
        original = self.records[identity]
        for field, value in (("product", "runtime"), ("component", "node-js"),
                             ("phase", "metadata"), ("target", "node"), ("productVersion", "not-semver")):
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.records[identity] = {**original, "receipt": {**original["receipt"], field: value}}
                properties(self.plan("validation"), predecessor=self.predecessor)
        self.records[identity] = original
        link = self.root / "stage-link"
        link.symlink_to(original["stage"], target_is_directory=True)
        for path in (Path("relative"), self.root / "absent", self.request, link):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.records[identity] = {**original, "stage": path}
                properties(self.plan("validation"), predecessor=self.predecessor)
        self.records[identity] = original


if __name__ == "__main__":
    unittest.main()
