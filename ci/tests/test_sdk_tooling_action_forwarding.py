"""Exercise exact SDK tooling-policy forwarding in the composite actions.

The recording Python stand-in proves shell routing only.  Product admission and
the tooling policy itself remain owned by the existing Python controllers.
"""

import unittest

from ci.tests import test_sdk_family_actions as action_harness


class SdkToolingActionForwardingTest(unittest.TestCase):
    def setUp(self):
        self.harness = action_harness.SdkFamilyActionsTest(methodName="runTest")
        self.harness.setUp()
        self.tooling = "/caller supplied/tooling policy.json"

    def test_capture_forwards_exact_tooling_path_for_sdk_projections(self):
        cases = (
            ({"STATE_PRODUCT": "sdk", "SDK_FAMILY": "native-validation", "SDK_STATE_WAVE": "6"},
             ["--sdk-state-wave", "6", "--family", "native-validation"]),
            ({"STATE_PRODUCT": "sdk", "SDK_FAMILY": "native-metadata", "SDK_STATE_WAVE": "7"},
             ["--sdk-state-wave", "7", "--family", "native-metadata"]),
            ({"STATE_PRODUCT": "sdk-ios-binary", "SDK_STATE_WAVE": "2"},
             ["--sdk-state-wave", "2", "--ios-binary"]),
        )
        for environment, selected in cases:
            with self.subTest(environment=environment):
                result, args, token, output = self.harness.run_action(
                    "capture", SDK_VALIDATION_TOOLING=self.tooling, **environment)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual(self.harness.capture_arguments(output, [
                    *selected, "--sdk-validation-tooling", self.tooling], sdk=True), args)
                self.assertEqual("synthetic environment-only token", token)

    def test_collect_forwards_exact_tooling_path_for_waves_seven_and_eight(self):
        for family, wave in (("native-validation", "7"), ("native-metadata", "8")):
            with self.subTest(family=family):
                result, args, token, output = self.harness.run_action(
                    "collect", PRODUCT="sdk", SDK_FAMILY=family, WAVE=wave,
                    SDK_VALIDATION_TOOLING=self.tooling)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual(self.harness.collect_arguments(output, [
                    "--family", family, "--sdk-validation-tooling", self.tooling],
                    sdk=True, wave=wave), args)
                self.assertEqual("synthetic environment-only token", token)

        before_collect = self.harness.collect.split("    - id: collect", 1)[0]
        self.assertIn("sdk-validation-tooling: ${{ inputs.sdk-validation-tooling }}", before_collect)

    def test_runtime_policy_forwarding_and_invalid_sdk_scope_rejection(self):
        cases = (
            ("capture", {"STATE_PRODUCT": "runtime", "SDK_VALIDATION_TOOLING": self.tooling}),
            ("capture", {"STATE_PRODUCT": "sdk", "SDK_FAMILY": "unknown",
                         "SDK_VALIDATION_TOOLING": self.tooling}),
            ("capture", {"STATE_PRODUCT": "sdk-ios-binary", "SDK_FAMILY": "native-validation",
                         "SDK_VALIDATION_TOOLING": self.tooling}),
            ("collect", {"PRODUCT": "runtime", "SDK_VALIDATION_TOOLING": self.tooling}),
            ("collect", {"PRODUCT": "sdk", "SDK_FAMILY": "unknown",
                         "SDK_VALIDATION_TOOLING": self.tooling}),
            ("collect", {"PRODUCT": "sdk-ios-binary", "SDK_FAMILY": "native-metadata",
                         "SDK_VALIDATION_TOOLING": self.tooling}),
        )
        for action, environment in cases:
            with self.subTest(action=action, environment=environment):
                result, args, token, output = self.harness.run_action(action, **environment)
                if environment.get("STATE_PRODUCT", environment.get("PRODUCT")) == "runtime":
                    # Runtime replay also authenticates retained SDK evidence.
                    selected = ["--sdk-validation-tooling", self.tooling]
                    expected = (self.harness.capture_arguments(output, selected) if action == "capture" else
                                self.harness.collect_arguments(output, ["--state-wave", "0", *selected]))
                    self.assertEqual(0, result.returncode, result.stderr)
                    self.assertEqual(expected, args)
                    self.assertEqual("synthetic environment-only token", token)
                else:
                    self.assertNotEqual(0, result.returncode)
                    self.assertIsNone(args)
                    self.assertIsNone(token)

    def test_absent_tooling_preserves_existing_default_arguments(self):
        for action in ("capture", "collect"):
            with self.subTest(action=action):
                result, args, _, output = self.harness.run_action(action)
                self.assertEqual(0, result.returncode, result.stderr)
                expected = (self.harness.capture_arguments(output) if action == "capture" else
                            self.harness.collect_arguments(output, ["--state-wave", "0"]))
                self.assertEqual(expected, args)
                self.assertNotIn("--sdk-validation-tooling", args)


if __name__ == "__main__":
    unittest.main()
