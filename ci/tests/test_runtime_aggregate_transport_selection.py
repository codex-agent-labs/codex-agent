"""Selected-state transport composition; signed-carrier trust is tested separately."""

from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ci.tests import test_product_reuse_adapter as fixture

reuse = fixture.product_reuse


class AggregateTransportSelectionTest(unittest.TestCase):
    def test_selected_receipt_only_is_captured_with_caller_policy_and_no_fallback(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            instance = reuse.PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate")
            digest, key = "sha256:" + "a" * 64, "sha256:" + "b" * 64
            record = {"receiptSha256": digest, "handoffRoot": "original"}
            state = SimpleNamespace(prior_by_instance={instance: {"receiptSha256": digest, "buildKey": key}},
                sources={instance: root / "object"}, prior_carrier_phases={instance: {}},
                rebased_request={"runtimeAggregateReleaseEvidence": [record]})
            kwargs = dict(expected_build_key=key, keyring=root / "keyring", keys_directory=root / "keys",
                          repository_root=root, environ={})
            args = (root / "plan", root / "discovery", root / "state", root / "output")
            (root / "discovery").mkdir()
            (root / "state").mkdir()
            with patch.object(reuse, "_verified_product_state", return_value=state), \
                    patch.object(reuse, "stage_runtime_aggregate_release_evidence", return_value=[record]) as stage:
                self.assertEqual(root / "output/original", reuse.materialize_runtime_aggregate_release_evidence(*args, **kwargs))
                stage.assert_called_once_with([record], root, root / "output",
                                               keyring=root / "keyring", keys_directory=root / "keys")
                stage.reset_mock()
                state.rebased_request["runtimeAggregateReleaseEvidence"] = [dict(record, receiptSha256="sha256:" + "c" * 64)]
                self.assertIsNone(reuse.materialize_runtime_aggregate_release_evidence(*args, **kwargs))
                stage.assert_not_called()
                state.rebased_request["runtimeAggregateReleaseEvidence"] = [record]
                stage.side_effect = ValueError("invalid original signature")
                with self.assertRaisesRegex(ValueError, "invalid original signature"):
                    reuse.materialize_runtime_aggregate_release_evidence(*args, **kwargs)
                state.sources.clear()
                with self.assertRaisesRegex(ValueError, "selected original"):
                    reuse.materialize_runtime_aggregate_release_evidence(*args, **kwargs)

    def test_discovery_inventory_and_rebase_preserve_receipt_but_reject_unbacked_record(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            carrier = root / "runtime-aggregate-release-evidence/0"
            (carrier / "handoffs/original").mkdir(parents=True)
            (carrier / "handoffs/original/empty.log").write_bytes(b"")
            records = [{"receiptSha256": "sha256:" + "a" * 64, "handoffRoot": "handoffs/original"}]
            (carrier / "runtime-aggregate-release-evidence.json").write_bytes(fixture.canonical_json_bytes(records))
            retained = reuse._retained_aggregate_handoffs(root, root)
            request = {"runtimeAggregateReleaseEvidence": retained}
            reuse._verify_discovery_sdk_records(request, root)
            relocated = reuse._rebase_native_request(request, root, root.parent)
            self.assertEqual(records[0]["receiptSha256"], relocated["runtimeAggregateReleaseEvidence"][0]["receiptSha256"])
            self.assertEqual(root.name + "/" + retained[0]["handoffRoot"],
                             relocated["runtimeAggregateReleaseEvidence"][0]["handoffRoot"])
            with self.assertRaisesRegex(ValueError, "complete retained"):
                reuse._verify_discovery_sdk_records({}, root)
            request["runtimeAggregateReleaseEvidence"][0]["handoffRoot"] = "../escape"
            with self.assertRaises(ValueError):
                reuse._rebase_native_request(request, root, root.parent)


if __name__ == "__main__":
    unittest.main()
