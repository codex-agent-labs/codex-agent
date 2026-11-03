"""Ready-plan anchor controls; process/content gates mocked, no host evidence."""

from copy import deepcopy
import unittest

from ci.tests import test_sdk_native_prepare as fixture
from products.inventory import canonical_json_bytes, load_canonical_json_bytes, regular_file_inventory
from products.receipt import compute_build_key
from products.registry import NATIVE_BINDINGS, NATIVE_TARGETS, PhaseInstanceId


worker = fixture.worker


class SdkNativePrepareAnchorTest(unittest.TestCase):
    def setUp(self):
        self.case = fixture.SdkNativePrepareTest(methodName="runTest")
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)

    def anchor(self, phase, target):
        self.case.plan.update(phase=phase, target=target)
        self.case.plan["buildKey"] = compute_build_key(**{name: self.case.plan[name]
            for name in ("product", "component", "phase", "target", "inputs")})

    def test_all_thirty_five_original_anchor_identities_run_same_linux_stage_once_task(self):
        for component in NATIVE_BINDINGS:
            for phase, target in (("package", "desktop"), *(("validation", value) for value in NATIVE_TARGETS),
                                  ("metadata", "desktop")):
                with self.subTest(component=component, phase=phase, target=target):
                    self.case.fixture(component)
                    self.anchor(phase, target)
                    before = canonical_json_bytes(self.case.plan)
                    originals = regular_file_inventory(self.case.root / "originals")
                    self.assertEqual(PhaseInstanceId("sdk", component, phase, target), worker.validate_anchor(self.case.plan))
                    result = self.case.invoke()
                    self.assertEqual(before, canonical_json_bytes(self.case.plan))
                    self.assertEqual(originals, regular_file_inventory(self.case.root / "originals"))
                    self.assertEqual(1, len(self.case.calls))
                    command = self.case.calls[0]
                    self.assertEqual(1, command.count(worker.TASK))
                    self.assertFalse(any(value.startswith(("-PcodexAgent.product=", "-PcodexAgent.phase=")) for value in command))
                    execution = load_canonical_json_bytes((result["diagnostics"] / "execution.json").read_bytes())
                    self.assertEqual(self.case.plan["buildKey"], execution["buildKey"])
                    self.assertEqual(self.case.producer, execution["producer"])
                    self.assertFalse((self.case.root / "codex-agent-sdk/build/product-stage").exists())
                    self.assertFalse((result["diagnostics"] / "shard").exists())

    def test_invalid_identity_shape_and_relabelled_key_never_run_process(self):
        mutations = ({"product": "runtime"}, {"component": "javascript"}, {"component": "sdk-ios"},
            {"phase": "binary"}, {"phase": "validation", "target": "desktop"},
            {"phase": "metadata", "target": "linux-x64"}, {"target": "linux-arm64"},
            {"phase": "metadata"}, {"phase": []}, {"schemaVersion": True},
            {"buildKey": "sha256:" + "f" * 64}, {"unexpected": "not a plan field"})
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.case.fixture()
                self.case.plan.update(deepcopy(mutation))
                with self.assertRaises(ValueError):
                    self.case.invoke()
                self.assertEqual([], self.case.calls)
                self.assertFalse(self.case.destination.exists())

    def test_non_linux_preparation_and_changed_original_anchor_still_fail_closed(self):
        for host in NATIVE_TARGETS:
            if host == "linux-x64":
                continue
            with self.subTest(host=host):
                self.case.fixture()
                self.anchor("validation", host)
                self.case.host = host
                with self.assertRaisesRegex(ValueError, "Linux X64"):
                    self.case.invoke()
                self.assertEqual([], self.case.calls)
        self.case.fixture()
        self.anchor("metadata", "desktop")
        self.case.after_process = lambda: self.case.plan.update(phase="package")
        with self.assertRaisesRegex(ValueError, "plan or producer changed"):
            self.case.invoke()
        self.assertEqual(1, len(self.case.calls))
        self.assertFalse((self.case.destination / "shard").exists())


if __name__ == "__main__":
    unittest.main()
