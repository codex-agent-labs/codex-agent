"""Saved caller mode selection; no product or historical acceptance is minted."""

from itertools import product
from pathlib import Path
import re
import unittest
from unittest.mock import patch

from ci.tests import test_runtime_recovery_acceptance as recovery_tests


ROOT = Path(__file__).resolve().parents[2]
recovery = recovery_tests.recovery


class SdkRecoveryCallerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.caller = (ROOT / ".github/workflows/ci.yml").read_text()
        cls.job = re.search(r"(?ms)^  product-validation:\n.*?(?=^  [a-z][a-z0-9-]*:|\Z)",
                            cls.caller)[0]

    def input(self, name):
        values = re.findall(rf"(?m)^      {name}: (.+)$", self.job)
        self.assertEqual(1, len(values), name)
        return values[0]

    def selected(self, name, event, labels):
        expression = self.input(name)
        if expression in ("true", "false"):
            return expression == "true"
        self.assertTrue(expression.startswith("${{") and expression.endswith("}}"))
        expression = expression[3:-2].replace("github.event_name", repr(event))
        expression = expression.replace("github.event.pull_request.labels.*.name", repr(labels))
        expression = expression.replace("&&", " and ").replace("||", " or ")
        expression = re.sub(r"!(?!=)", " not ", expression).strip()
        return eval(expression, {"__builtins__": {}}, {"contains": lambda rows, value: value in rows})

    def test_exactly_one_mode_and_sdk_checkpoints_follow_only_explicit_sdk_request(self):
        for event, sdk, tooling in product(("pull_request", "merge_group", "workflow_dispatch"),
                                          (False, True), (False, True)):
            labels = ["merge-ready", "ci:remote-final"]
            if sdk:
                labels.append("ci:sdk-recovery")
            if tooling:
                labels.append("ci:tooling-only")
            with self.subTest(event=event, labels=labels):
                actual = {name: self.selected(name, event, labels) for name in (
                    "toolingOnly", "sdkRecoveryOnly", "sdkCheckpoints", "fullReuseAcceptanceOnly",
                    "runtimeRecoveryOnly", "runtimeAggregateRequalification")}
                expected_tooling = event == "pull_request" and tooling
                expected_sdk = event == "pull_request" and sdk and not tooling
                self.assertEqual(expected_tooling, actual["toolingOnly"])
                self.assertEqual(expected_sdk, actual["sdkRecoveryOnly"])
                self.assertEqual(expected_sdk, actual["sdkCheckpoints"])
                self.assertEqual(not (expected_tooling or expected_sdk), actual["fullReuseAcceptanceOnly"])
                self.assertFalse(actual["runtimeRecoveryOnly"])
                self.assertFalse(actual["runtimeAggregateRequalification"])
                self.assertEqual(1, sum(actual[name] for name in
                                       ("toolingOnly", "sdkRecoveryOnly", "fullReuseAcceptanceOnly")))

    def test_actual_expression_delegates_to_unchanged_sdk_authority_checks(self):
        source = self.caller.encode()
        self.assertIn(recovery.SDK_RECOVERY_CALLER, source.splitlines())
        self.assertEqual(self.input("sdkRecoveryOnly"), self.input("sdkCheckpoints"))
        with patch.object(recovery, "_blob", return_value=source), \
                patch.object(recovery, "_sdk_reviewed_scope", return_value=object()) as sdk_scope, \
                patch.object(recovery, "_tree", side_effect=AssertionError("wrong scope")):
            result = recovery._reviewed_scope(Path("/trusted"), Path("/candidate"), "a" * 40)
        sdk_scope.assert_called_once_with(Path("/trusted"), Path("/candidate"), "a" * 40)
        self.assertIs(result, sdk_scope.return_value)

    def test_expression_classifier_does_not_evaluate_alternatives_or_accept_duplicate_scope(self):
        source = self.caller.encode()
        cases = [
            source.replace(b"ci:sdk-recovery", b"ci:other"),
            source.replace(b"github.event_name == 'pull_request' && ", b""),
            source.replace(b" && !contains(github.event.pull_request.labels.*.name, 'ci:tooling-only')", b""),
            source + b"      sdkRecoveryOnly: false\n",
            source + recovery.SDK_RECOVERY_CALLER + b"\n",
            source + b"      runtimeRecoveryOnly: true\n",
            source.replace(b"      runtimeRecoveryOnly: false", b"      runtimeRecoveryOnly: true"),
        ]
        for number, candidate in enumerate(cases):
            with self.subTest(case=number), patch.object(recovery, "_blob", return_value=candidate), \
                    patch.object(recovery, "_sdk_reviewed_scope") as sdk_scope, \
                    patch.object(recovery, "_tree", side_effect=ValueError("original legacy checks")), \
                    self.assertRaisesRegex(ValueError, "original legacy checks"):
                recovery._reviewed_scope(Path("/trusted"), Path("/candidate"), "a" * 40)
            sdk_scope.assert_not_called()

    def test_existing_literal_sdk_and_runtime_scopes_keep_their_distinct_authority(self):
        for sdk, runtime, options in (("true", "false", {}),
                                      ("false", "true", {"allow_posix_correction": True})):
            source = f"      sdkRecoveryOnly: {sdk}\n      runtimeRecoveryOnly: {runtime}\n".encode()
            with self.subTest(sdk=sdk), patch.object(recovery, "_blob", return_value=source), \
                    patch.object(recovery, "_sdk_reviewed_scope") as sdk_scope:
                recovery._reviewed_scope(Path("/trusted"), Path("/candidate"), "a" * 40)
            sdk_scope.assert_called_once_with(Path("/trusted"), Path("/candidate"), "a" * 40, **options)


if __name__ == "__main__":
    unittest.main()
