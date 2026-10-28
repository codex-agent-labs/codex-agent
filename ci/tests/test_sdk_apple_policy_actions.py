"""Exercise caller-owned Apple policy routing in the shared composites.

The actual Bash blocks run with a recording Python stand-in.  These tests prove
argument routing only; policy parsing and Apple admission remain in Python.
"""

import unittest

from ci.tests import test_sdk_family_actions as action_harness


class SdkApplePolicyActionsTest(unittest.TestCase):
    def setUp(self):
        self.harness = action_harness.SdkFamilyActionsTest(methodName="runTest")
        self.harness.setUp()
        self.policy = "/caller supplied/Apple validation policy.json"

    def test_capture_forwards_optional_policy_for_each_supported_product_scope(self):
        cases = (
            ({}, False, []),
            ({"STATE_PRODUCT": "sdk", "SDK_FAMILY": "ios-validation", "SDK_STATE_WAVE": "8"}, True,
             ["--sdk-state-wave", "8", "--family", "ios-validation"]),
            ({"STATE_PRODUCT": "sdk", "SDK_FAMILY": "ios-metadata", "SDK_STATE_WAVE": "10"}, True,
             ["--sdk-state-wave", "10", "--family", "ios-metadata"]),
            ({"STATE_PRODUCT": "sdk-ios-binary", "SDK_STATE_WAVE": "2"}, True,
             ["--sdk-state-wave", "2", "--ios-binary"]),
        )
        for environment, sdk, selected in cases:
            for supplied in (False, True):
                policy = self.policy if supplied else ""
                with self.subTest(environment=environment, supplied=supplied):
                    result, args, token, output = self.harness.run_action(
                        "capture", SDK_APPLE_VALIDATION_POLICY=policy, **environment)
                self.assertEqual(0, result.returncode, result.stderr)
                expected = [*selected, *(["--sdk-apple-validation-policy", policy] if supplied else [])]
                self.assertEqual(self.harness.capture_arguments(output, expected, sdk=sdk), args)
                self.assertEqual("synthetic environment-only token", token)

    def test_collect_forwards_optional_policy_for_each_supported_product_scope(self):
        cases = (
            ({}, False, ["--state-wave", "0"], "1"),
            ({"PRODUCT": "sdk", "SDK_FAMILY": "ios-validation", "WAVE": "9"}, True,
             ["--family", "ios-validation"], "9"),
            ({"PRODUCT": "sdk", "SDK_FAMILY": "ios-metadata", "WAVE": "10"}, True,
             ["--family", "ios-metadata"], "10"),
            ({"PRODUCT": "sdk-ios-binary", "WAVE": "3"}, True, ["--ios-binary"], "3"),
        )
        for environment, sdk, selected, wave in cases:
            for supplied in (False, True):
                policy = self.policy if supplied else ""
                with self.subTest(environment=environment, supplied=supplied):
                    result, args, token, output = self.harness.run_action(
                        "collect", SDK_APPLE_VALIDATION_POLICY=policy, **environment)
                self.assertEqual(0, result.returncode, result.stderr)
                expected = [*selected, *(["--sdk-apple-validation-policy", policy] if supplied else [])]
                self.assertEqual(self.harness.collect_arguments(output, expected, sdk=sdk, wave=wave), args)
                self.assertEqual("synthetic environment-only token", token)

    def test_collect_forwards_policy_to_capture_without_exposing_it_as_output(self):
        capture = self.harness.collect.split("    - id: captured\n", 1)[1].split("    - id: collect\n", 1)[0]
        self.assertIn("sdk-apple-validation-policy: ${{ inputs.sdk-apple-validation-policy }}", capture)
        self.assertIn("  sdk-apple-validation-policy:\n    default: ''", self.harness.capture)
        self.assertIn("  sdk-apple-validation-policy:\n    default: ''", self.harness.collect)
        for source in (self.harness.capture, self.harness.collect):
            outputs = source.split("outputs:\n", 1)[1].split("runs:\n", 1)[0]
            self.assertNotIn("apple-validation-policy", outputs)


if __name__ == "__main__":
    unittest.main()
