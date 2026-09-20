"""Synthetic structural projection tests, not Apple compiler/host acceptance."""

from copy import deepcopy
import unittest

from ci.products.inventory import canonical_json_bytes
from ci.products.sdk_apple_validation_content import apple_validation_content


class AppleValidationContentTest(unittest.TestCase):
    def setUp(self):
        canonical = {"apiReportSha256": "a" * 64, "coverageReceiptSha256": "b" * 64}
        scenarios = sorted((
            "async-success", "async-failure", "cancellation", "state-current-value",
            "state-subsequent-value", "subscription-cancellation", "terminal-delivery",
            "structured-failure", "identity", "parent-child-ownership", "repeated-close-dispose",
            "nullability", "collection-immutability-ordering", "value-conversion",
        ))
        self.arguments = dict(
            target="ios-simulator-arm64", sdk_version="0.8.0",
            package_outputs_digest="sha256:" + "c" * 64, contract_digest="sha256:" + "d" * 64,
            expected_canonical=canonical, binding_receipts={},
        )
        for language in ("objective-c", "swift"):
            self.arguments["binding_receipts"][language] = {
                "schema": 4, "result": "passed", "phase": "M8", "language": language,
                "canonical": dict(canonical),
                "artifacts": [{"id": name, "sha256": "e" * 64} for name in (
                    "apple-binding-evidence", "apple-compiler-evidence", "apple-xctest-evidence",
                    "codex-agent-xcframework",
                )],
                "hostConsumerProofs": [], "testProgramSha256": "f" * 64,
                "testResultsSha256": "1" * 64, "publicSymbols": ["symbol-a", "symbol-b"],
                "tests": [{"id": "test-a", "status": "passed"}],
                "scenarios": [{"id": name, "testIds": ["test-a"]} for name in scenarios],
                "claims": [{"capabilityKey": "capability-a", "publicSymbols": ["symbol-a"],
                            "executedTests": ["test-a"], "sharedScenarios": ["identity"]}],
                "exclusions": [],
            }

    def test_exact_projection_and_independent_return_for_both_targets(self):
        for target in ("ios-arm64", "ios-simulator-arm64"):
            with self.subTest(target=target):
                arguments = deepcopy(self.arguments)
                arguments["target"] = target
                original = deepcopy(arguments)
                content = apple_validation_content(**arguments)
                self.assertEqual(set(content), {
                    "schemaVersion", "kind", "component", "target", "sdkVersion",
                    "packageOutputsDigest", "contractDigest", "canonical", "bindings",
                })
                self.assertEqual(content["schemaVersion"], 1)
                self.assertEqual(content["kind"], "sdk-apple-validation-content")
                self.assertEqual(content["component"], "sdk-ios")
                self.assertEqual(content["target"], target)
                self.assertEqual(content["sdkVersion"], "0.8.0")
                self.assertEqual(content["canonical"], arguments["expected_canonical"])
                for row in content["bindings"]:
                    self.assertEqual(set(row), {
                        "phase", "language", "publicSymbols", "tests", "scenarios", "claims", "exclusions",
                    })
                self.assertEqual([r["language"] for r in content["bindings"]], ["objective-c", "swift"])
                self.assertEqual(arguments, original)
                content["canonical"]["apiReportSha256"] = "9" * 64
                content["bindings"][0]["claims"].clear()
                self.assertEqual(arguments, original)

    def test_different_original_execution_hashes_have_identical_content(self):
        baseline = canonical_json_bytes(apple_validation_content(**self.arguments))
        for receipt in self.arguments["binding_receipts"].values():
            receipt["testResultsSha256"] = "3" * 64
            for artifact in receipt["artifacts"]:
                if artifact["id"] != "codex-agent-xcframework":
                    artifact["sha256"] = "4" * 64
        self.assertEqual(canonical_json_bytes(apple_validation_content(**self.arguments)), baseline)

    def test_contract_package_and_semantic_changes_change_content(self):
        baseline = canonical_json_bytes(apple_validation_content(**self.arguments))
        for field, value in (("contract_digest", "sha256:" + "5" * 64),
                             ("package_outputs_digest", "sha256:" + "6" * 64),
                             ("sdk_version", "0.8.1")):
            with self.subTest(field=field):
                arguments = deepcopy(self.arguments)
                arguments[field] = value
                self.assertNotEqual(canonical_json_bytes(apple_validation_content(**arguments)), baseline)
        arguments = deepcopy(self.arguments)
        arguments["binding_receipts"]["swift"]["claims"][0]["publicSymbols"] = ["symbol-b"]
        self.assertNotEqual(canonical_json_bytes(apple_validation_content(**arguments)), baseline)
        arguments = deepcopy(self.arguments)
        arguments["expected_canonical"]["apiReportSha256"] = "7" * 64
        for receipt in arguments["binding_receipts"].values():
            receipt["canonical"]["apiReportSha256"] = "7" * 64
        self.assertNotEqual(canonical_json_bytes(apple_validation_content(**arguments)), baseline)

    def test_both_receipts_must_match_independent_expected_canonical(self):
        for language in ("objective-c", "swift"):
            for field in ("apiReportSha256", "coverageReceiptSha256"):
                with self.subTest(language=language, field=field):
                    arguments = deepcopy(self.arguments)
                    arguments["binding_receipts"][language]["canonical"][field] = "8" * 64
                    with self.assertRaisesRegex(ValueError, "caller-owned canonical"):
                        apple_validation_content(**arguments)

    def test_unknown_missing_or_malformed_receipt_semantics_reject(self):
        mutations = (
            lambda r: r.update(schema=True), lambda r: r.update(schema=5),
            lambda r: r.update(result="failed"), lambda r: r.update(phase="M11"),
            lambda r: r.update(language="kotlin"), lambda r: r.update(extra="unknown"),
            lambda r: r.pop("claims"), lambda r: r.update(claims=[]),
            lambda r: r["canonical"].update(extra="unknown"),
            lambda r: r["artifacts"].pop(), lambda r: r["artifacts"][0].update(sha256="bad"),
            lambda r: r.update(testResultsSha256="sha256:" + "a" * 64),
            lambda r: r.update(hostConsumerProofs=[{}]), lambda r: r.update(exclusions=[{}]),
            lambda r: r["publicSymbols"].reverse(), lambda r: r["publicSymbols"].append("symbol-b"),
            lambda r: r["tests"][0].update(status="failed"),
            lambda r: r["tests"][0].update(extra="unknown"),
            lambda r: r["scenarios"].pop(), lambda r: r["scenarios"][0].update(testIds=["unknown"]),
            lambda r: r["claims"][0].update(executedTests=["unknown"]),
            lambda r: r["claims"][0].update(sharedScenarios=["unknown"]),
            lambda r: r["claims"][0].update(publicSymbols=["unknown"]),
            lambda r: r["claims"][0].update(capabilityKey="*"),
            lambda r: r["claims"][0].update(extra="unknown"),
        )
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                arguments = deepcopy(self.arguments)
                mutate(arguments["binding_receipts"]["swift"])
                with self.assertRaises(ValueError):
                    apple_validation_content(**arguments)

    def test_caller_schema_and_identity_fail_closed(self):
        for field, value in (
            ("target", "macos-arm64"), ("sdk_version", "latest"), ("contract_digest", "bad"),
            ("package_outputs_digest", "a" * 64), ("expected_canonical", {}),
            ("expected_canonical", {"apiReportSha256": "A" * 64, "coverageReceiptSha256": "b" * 64}),
            ("binding_receipts", {}),
        ):
            with self.subTest(field=field, value=value):
                arguments = deepcopy(self.arguments)
                arguments[field] = value
                with self.assertRaises(ValueError):
                    apple_validation_content(**arguments)


if __name__ == "__main__":
    unittest.main()
