"""Routing hints only: verified state, object and Git policy are mocked boundaries."""

import copy
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import product_reuse as controller
from products import sdk_release_selection as policy


CONTRACT = controller.PhaseInstanceId("contract", "contract", "metadata", "common")
KEY = "sha256:" + "a" * 64
RECEIPT = "sha256:" + "b" * 64
OBJECT = "sha256:" + "c" * 64
PAYLOAD = "sha256:" + "d" * 64


class SdkInputSelectionTest(unittest.TestCase):
    def setUp(self):
        self.root = Path("/synthetic/repository")
        self.revision = "e" * 40
        self.contract_object = self.root / "original-contract-object.zip"
        self.state = SimpleNamespace(
            prior={"phases": [self.phase("sdk", "python", "package", "desktop")]},
            sources={CONTRACT: self.contract_object},
            prior_carrier_phases={CONTRACT: {"buildKey": KEY, "receiptSha256": RECEIPT, "objectSha256": OBJECT}},
            producer={"commit": self.revision}, expected_fixed={"versions": {"contract": "0.8.0"}},
            rebased_request={})
        self.receipt = {"productVersion": "0.8.0", "outputs": [
            {"kind": "contract-bundle", "relativePath": "outputs/codex-agent-contract-0.8.0.zip",
             "bytes": 123, "sha256": PAYLOAD}]}
        self.selection = {"sdkVersion": "0.8.0", "defaultRuntimeVersion": "0.8.0"}
        self.ranges = {"compatibleReleaseRange": ">=0.8.0 <0.9.0",
                       "compatibleRuntimeCompatibilityRange": ">=0.8.0 <0.9.0"}
        self.read_policy = self.enterContext(patch.object(policy, "read_sdk_release_selection", return_value=self.selection))
        self.read_ranges = self.enterContext(patch.object(policy, "read_sdk_runtime_compatibility_policy", return_value=self.ranges))
        self.object_gate = self.enterContext(patch.object(controller, "verify_object", return_value={"receipt": self.receipt}))

    @staticmethod
    def phase(product, component, phase, target, state="build"):
        return {"product": product, "component": component, "phase": phase, "target": target, "state": state}

    def route(self):
        return controller._sdk_input_selection(self.state, self.root)

    def test_no_consumer_binary_and_completed_sdk_do_not_read_policy_or_objects(self):
        cases = ([], [self.phase("runtime", "jvm", "binary", "jvm")],
                 [self.phase("sdk", "sdk-core", "binary", "common")],
                 [self.phase("sdk", "python", "package", "desktop", "retained")],
                 [self.phase("sdk", "python", "package", "desktop", "reused")])
        for phases in cases:
            self.state.prior["phases"] = phases
            with self.subTest(phases=phases):
                self.assertIsNone(self.route())
        self.read_policy.assert_not_called()
        self.read_ranges.assert_not_called()
        self.object_gate.assert_not_called()

    def test_current_or_released_runtime_selection_binds_contract_content_not_receipt(self):
        for source in (None, "released-default"):
            self.state.rebased_request = {} if source is None else {"sdkRuntimeSource": source}
            before = copy.deepcopy(self.state.__dict__)
            with self.subTest(source=source):
                result = self.route()
                self.assertEqual({"source": source or "current-runtime", **self.selection, **self.ranges,
                    "contractVersion": "0.8.0", "contractPayloadSha256": PAYLOAD,
                    "consumers": [{"product": "sdk", "component": "python", "phase": "package", "target": "desktop"}]}, result)
                self.assertNotEqual(RECEIPT, result["contractPayloadSha256"])
                self.assertNotEqual(OBJECT, result["contractPayloadSha256"])
                self.assertEqual(before, self.state.__dict__)
                self.read_policy.assert_called_with(self.root, self.revision)
                self.read_ranges.assert_called_with(self.root, self.revision)
                self.object_gate.assert_called_with(self.contract_object, build_key=KEY,
                    receipt_sha256=RECEIPT, object_sha256=OBJECT)

    def test_missing_current_contract_does_not_read_policy_or_fall_back(self):
        self.state.sources = {}
        self.assertIsNone(self.route())
        self.read_policy.assert_not_called()
        self.read_ranges.assert_not_called()
        self.object_gate.assert_not_called()

    def test_wrong_version_kind_count_digest_and_rejected_policy_fail_closed(self):
        for mutation in ("version", "kind", "extra", "missing", "digest"):
            receipt = copy.deepcopy(self.receipt)
            if mutation == "version":
                receipt["productVersion"] = "0.7.0"
            elif mutation == "kind":
                receipt["outputs"][0]["kind"] = "unrelated"
            elif mutation == "extra":
                receipt["outputs"].append(copy.deepcopy(receipt["outputs"][0]))
            elif mutation == "missing":
                receipt["outputs"] = []
            else:
                receipt["outputs"][0]["sha256"] = "not-a-digest"
            self.object_gate.return_value = {"receipt": receipt}
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.route()
        self.read_policy.side_effect = ValueError("synthetic malformed Git policy")
        self.object_gate.reset_mock()
        with self.assertRaisesRegex(ValueError, "malformed Git policy"):
            self.route()
        self.object_gate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
