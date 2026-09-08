"""Pure native argument mapping; callback sentinels are not artifact admission."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import runtime_native_phase
from products.registry import NATIVE_TARGETS


REVISION = "1" * 40
FLAGS = "sha256:" + "2" * 64


class RuntimeNativePhaseTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="native-phase-properties-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()

    def plan(self, component, phase):
        return {"schemaVersion": 1, "product": "runtime", "component": component,
                "phase": phase, "target": component, "buildKey": "sha256:" + "3" * 64,
                "inputs": {"flagsDigest": FLAGS}}

    def predecessor(self, component, phase, target):
        return {"stage": self.root / component / phase / "stage",
                "receiptPath": self.root / component / phase / "original-receipt.json",
                "receipt": {"schemaVersion": 1, "result": "success", "product": "runtime",
                            "component": component, "phase": phase, "target": target, "productVersion": "0.2.4"}}

    def output(self, component, phase, target, kind):
        self.assertEqual(component, target)
        return self.root / component / phase / "declared-original" / kind

    def report(self, component, target):
        self.assertEqual(component, target)
        return self.root / component / "validation" / "original-raw-report.json"

    def invoke(self, plan, **changes):
        return runtime_native_phase.properties(plan, **{
            "plan_path": self.root / "elected-plan.json", "revision": REVISION,
            "predecessor": self.predecessor, "output": self.output, "report": self.report,
            **changes,
        })

    def test_all_five_native_components_use_exact_existing_phase_properties(self):
        for component in NATIVE_TARGETS:
            for phase in ("binary", "package", "validation", "metadata"):
                with self.subTest(component=component, phase=phase):
                    predecessor = mock.Mock(side_effect=self.predecessor)
                    output = mock.Mock(side_effect=self.output)
                    report = mock.Mock(side_effect=self.report)
                    actual = self.invoke(self.plan(component, phase), predecessor=predecessor, output=output, report=report)
                    if phase == "binary":
                        expected = {"codexAgent.runtimeBinaryPlan": str(self.root / "elected-plan.json"),
                                    "codexAgent.runtimeBinaryFlagsDigest": FLAGS,
                                    "codexAgent.repositoryRevision": REVISION}
                        predecessor.assert_not_called()
                    elif phase in {"package", "validation"}:
                        previous = "binary" if phase == "package" else "package"
                        prefix = "runtimeBinary" if phase == "package" else "runtimePackage"
                        expected = {f"codexAgent.{prefix}Stage": str(self.root / component / previous / "stage"),
                                    f"codexAgent.{prefix}Version": "0.2.4"}
                        predecessor.assert_called_once_with(component, previous, component)
                    else:
                        expected = {
                            "codexAgent.runtimeVariantIdentity": str(self.output(component, "binary", component, "runtime-identity")),
                            "codexAgent.runtimeVariantCAbiArchive": str(self.output(component, "package", component, "c-abi")),
                            "codexAgent.runtimeVariantAppServerArchive": str(self.output(component, "package", component, "app-server")),
                            "codexAgent.runtimeVariantValidationEvidence": str(self.report(component, component)),
                            **{f"codexAgent.runtimeVariant{previous.title()}Receipt":
                               str(self.root / component / previous / "original-receipt.json")
                               for previous in ("binary", "package", "validation")},
                        }
                        self.assertEqual([mock.call(component, previous, component)
                                          for previous in ("binary", "package", "validation")], predecessor.call_args_list)
                        self.assertEqual([mock.call(component, "binary", component, "runtime-identity"),
                                          mock.call(component, "package", component, "c-abi"),
                                          mock.call(component, "package", component, "app-server")], output.call_args_list)
                        report.assert_called_once_with(component, component)
                    self.assertEqual(expected, actual)
                    if phase != "metadata":
                        output.assert_not_called()
                        report.assert_not_called()

    def test_wrong_phase_identity_schema_or_required_binary_fields_reject(self):
        original = self.plan("macos-arm64", "binary")
        for changes in ({"product": "sdk"}, {"component": "jvm", "target": "jvm"},
                        {"target": "macos-x64"}, {"phase": "aggregate"}, {"schemaVersion": True},
                        {"schemaVersion": 2}, {"buildKey": "wrong"}, {"inputs": []},
                        {"inputs": {}}, {"inputs": {"flagsDigest": "wrong"}}, {"extra": True}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.invoke({**original, **changes})
        for revision in ("HEAD", "1" * 39, "A" * 40, " " + REVISION):
            with self.subTest(revision=revision), self.assertRaises(ValueError):
                self.invoke(original, revision=revision)
        with self.assertRaises(ValueError):
            self.invoke(original, plan_path=Path("relative.json"))

    def test_missing_or_crosspaired_originals_never_fall_back_to_source_producers(self):
        plan = self.plan("linux-x64", "package")
        with self.assertRaisesRegex(ValueError, "missing original"):
            self.invoke(plan, predecessor=mock.Mock(side_effect=ValueError("missing original")))
        baseline = self.predecessor("linux-x64", "binary", "linux-x64")
        for field, value in (("product", "contract"), ("component", "macos-arm64"),
                             ("target", "macos-arm64"), ("phase", "package"),
                             ("result", "failure"), ("schemaVersion", True),
                             ("productVersion", "latest"), ("productVersion", "0.2.4+run.1")):
            changed = copy.deepcopy(baseline)
            changed["receipt"][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.invoke(plan, predecessor=mock.Mock(return_value=changed))
        for field in ("stage", "receiptPath"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.invoke(plan, predecessor=mock.Mock(return_value={**baseline, field: Path("relative")}))

    def test_metadata_requires_original_declared_files_and_rejects_unsafe_path_values(self):
        plan = self.plan("windows-x64", "metadata")
        for bad in (None, "caller-string", Path("relative"), self.root / "child" / ".." / "original"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.invoke(plan, output=mock.Mock(return_value=bad))
            with self.subTest(report=bad), self.assertRaises(ValueError):
                self.invoke(plan, report=mock.Mock(return_value=bad))
        with self.assertRaisesRegex(ValueError, "missing original identity"):
            self.invoke(plan, output=mock.Mock(side_effect=ValueError("missing original identity")))
        self.assertNotIn("codexAgent.runtimePackageStage", self.invoke(plan))
        self.assertNotIn("codexAgent.desktopSupervisorDirectory", self.invoke(self.plan("linux-arm64", "binary")))
