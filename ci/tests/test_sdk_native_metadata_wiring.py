"""Metadata preparation-anchor wiring; full admission remains in existing suites."""

from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from ci import sdk_native_metadata_workflow as workflow
from ci.tests import test_sdk_native_metadata_worker_action as action_fixture
from ci.tests import test_sdk_native_metadata_workflow as controller_fixture
from products.inventory import canonical_json_bytes, sha256_bytes
from products.receipt import compute_build_key


class SdkNativeMetadataPreparationAnchorTest(unittest.TestCase):
    def setUp(self):
        self.case = controller_fixture.SdkNativeMetadataWorkflowTest(methodName="runTest")
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.addCleanup(self.case.tearDown)

    def validation_anchor(self, target="macos-x64"):
        self.case.preparation.update(phase="validation", target=target)
        self.case.preparation["buildKey"] = compute_build_key(**{
            name: self.case.preparation[name]
            for name in ("product", "component", "phase", "target", "inputs")
        })
        self.case.arguments["preparation_build_key"] = self.case.preparation["buildKey"]

    def test_replayed_validation_anchor_supplies_existing_metadata_controller(self):
        self.validation_anchor()
        result = self.case.invoke(preparation_phase="validation", preparation_target="macos-x64")
        self.assertEqual(result, workflow.verify_phase_shard(self.case.destination / "shard", self.case.instance))
        self.assertEqual(self.case.preparation,
                         self.case.capture_mock.call_args.kwargs["expected_phase_plan"])
        self.assertEqual((self.case.plan_path, self.case.discovery, self.case.preparation_state),
                         self.case.inspect_mock.call_args.args)

    def test_invalid_anchor_phase_target_pairs_reject_before_sdk_context(self):
        invalid = (("package", "linux-x64"), ("metadata", "macos-arm64"),
                   ("validation", "desktop"), ("binary", "desktop"))
        for phase, target in invalid:
            with self.subTest(phase=phase, target=target), \
                    patch.object(workflow.sdk_workflow, "verified_inputs") as verified, \
                    self.assertRaises(ValueError):
                self.case.invoke_without_context(preparation_phase=phase, preparation_target=target)
            verified.assert_not_called()


class SdkNativeMetadataAnchorActionTest(unittest.TestCase):
    def setUp(self):
        self.case = action_fixture.SdkNativeMetadataWorkerActionTest(methodName="runTest")
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)

    def test_validation_anchor_uses_its_elected_host_while_metadata_stays_linux(self):
        action = self.case.action
        for value in ("preparation-phase:\n    default: package",
                      "preparation-target:\n    default: desktop",
                      "validation:macos-arm64|validation:macos-x64",
                      '--family "$family"',
                      "--preparation-phase", "--preparation-target"):
            self.assertIn(value, action)

        plan = self.case.root / "plan.json"
        output = self.case.root / "identity-output"
        policy = self.case.root / "policy.json"
        plan.write_text(json.dumps({"validationTree": "a" * 40}))
        policy_raw = canonical_json_bytes({"synthetic": "caller policy"})
        policy.write_bytes(policy_raw)
        current = {"product": "sdk", "component": "python", "phase": "metadata", "target": "desktop",
                   "buildKey": "sha256:" + "b" * 64, "runnerOs": "Linux", "runnerArch": "X64"}
        preparation = {"product": "sdk", "component": "rust", "phase": "validation", "target": "macos-x64",
                       "buildKey": "sha256:" + "c" * 64, "runnerOs": "macOS", "runnerArch": "X64"}
        environment = {"MATRIX": json.dumps({"include": [current]}),
            "PREPARATION_MATRIX": json.dumps({"include": [preparation]}), "COMPONENT": "python",
            "PREPARATION_COMPONENT": "rust", "PREPARATION_PHASE": "validation",
            "PREPARATION_TARGET": "macos-x64", "BUILD_KEY": current["buildKey"],
            "PREPARATION_BUILD_KEY": preparation["buildKey"], "TREE": "a" * 40,
            "PLAN": str(plan), "GITHUB_OUTPUT": str(output), "SDK_VALIDATION_TOOLING": str(policy),
            "POLICY_SHA256": sha256_bytes(policy_raw)}
        self.case.python("identity", environment)
        self.assertEqual("key_hex=" + "b" * 64 + "\n", output.read_text())

        wrong = deepcopy(environment)
        preparation["runnerOs"], preparation["runnerArch"] = "Linux", "X64"
        wrong["PREPARATION_MATRIX"] = json.dumps({"include": [preparation]})
        with self.assertRaisesRegex(ValueError, "original replay election"):
            self.case.python("identity", wrong)


if __name__ == "__main__":
    unittest.main()
