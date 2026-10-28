"""Caller-policy routing with mocked replay gates, not product admission proof."""

from copy import deepcopy
import unittest
from unittest.mock import patch

from ci.tests import test_runtime_workflow as fixture


workflow = fixture.workflow


class RuntimeCollectToolingPolicyTest(unittest.TestCase):
    def setUp(self):
        self.case = fixture.RuntimeWorkflowTest()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.policy = {"evidence": str(self.case.root / "evidence"),
            "publicKey": str(self.case.root / "public.pub"), "javaExecutable": str(self.case.root / "java"),
            "requiredTrustDomain": "release", "keyring": str(self.case.root / "keyring.json"),
            "keysDirectory": str(self.case.root / "keys")}

    def test_all_waves_forward_same_policy_through_collection_advance_and_final_replay(self):
        before = deepcopy(self.policy)
        for wave in range(1, 6):
            for supplied in (False, True):
                optional = {"sdk_validation_tooling": self.policy} if supplied else {}
                destination = self.case.root / f"wave-{wave}-{supplied}"
                with self.subTest(wave=wave, supplied=supplied), \
                        patch.object(workflow.products, "collect_runtime_workers", side_effect=(
                            self.case.aggregate_collection if wave == 5 else self.case.collection)) as collector, \
                        patch.object(workflow.products, "advance_products", side_effect=self.case.advanced) as advance, \
                        patch.object(workflow.products, "runtime_worker_matrix", return_value={"include": []}) as matrix, \
                        patch.object(workflow.products, "inspect_products", return_value=self.case.final_fixture("retained")) as inspect:
                    self.case.collect(destination, wave, **optional)
                for gate in (collector, advance, inspect if wave == 5 else matrix):
                    gate.assert_called_once()
                    if supplied:
                        self.assertIs(self.policy, gate.call_args.kwargs["sdk_validation_tooling"])
                    elif gate is inspect:
                        # Existing continuation forwards its default None to inspection.
                        self.assertIsNone(gate.call_args.kwargs["sdk_validation_tooling"])
                    else:
                        self.assertNotIn("sdk_validation_tooling", gate.call_args.kwargs)
                (matrix if wave == 5 else inspect).assert_not_called()
                self.assertEqual(wave == 5, collector.call_args.kwargs.get("runtime_aggregate_only", False))
                self.assertEqual(wave == 5, advance.call_args.kwargs.get("runtime_aggregate_only", False))
                self.assertEqual(wave != 5, advance.call_args.kwargs.get("runtime_workers_only", False))
                for name, raw in self.case.base.items():
                    self.assertEqual(raw, (destination / "handoff" / name).read_bytes())
                    self.assertEqual(raw, (self.case.input / name).read_bytes())
                self.assertEqual(before, self.policy)

    def test_failure_siblings_keep_policy_and_original_successes_without_next_election(self):
        def mixed(*args, **kwargs):
            result = self.case.collection(*args, **kwargs)
            result["rows"].append(fixture.row(fixture.NODE, result="failure", shardDirectory=None))
            return result
        destination = self.case.root / "mixed"
        with patch.object(workflow.products, "collect_runtime_workers", side_effect=mixed) as collector, \
                patch.object(workflow.products, "advance_products", side_effect=self.case.advanced) as advance, \
                patch.object(workflow.products, "runtime_worker_matrix") as matrix, \
                patch.object(workflow, "continuation") as continuation:
            self.case.collect(destination, sdk_validation_tooling=self.policy)
        self.assertIs(self.policy, collector.call_args.kwargs["sdk_validation_tooling"])
        self.assertIs(self.policy, advance.call_args.kwargs["sdk_validation_tooling"])
        self.assertEqual((fixture.NODE,), advance.call_args.kwargs["failed_instances"])
        self.assertEqual([destination / "collection/good/shard"], advance.call_args.args[3])
        self.assertEqual(b"", (destination / "collection/raw.log").read_bytes())
        self.assertEqual(b"original worker receipt\n", (destination / "collection/good/shard/phase-receipt.json").read_bytes())
        matrix.assert_not_called()
        continuation.assert_not_called()
        self.assertEqual("false", self.case.outputs()["runtime_workers_required"])

    def test_collection_replay_rejection_never_advances_or_emits_election(self):
        with patch.object(workflow.products, "collect_runtime_workers", side_effect=ValueError("policy rejected")), \
                patch.object(workflow.products, "advance_products") as advance, \
                patch.object(workflow, "matrix") as matrix:
            with self.assertRaisesRegex(ValueError, "policy rejected"):
                self.case.collect(self.case.root / "rejected", sdk_validation_tooling=self.policy)
        advance.assert_not_called()
        matrix.assert_not_called()
        self.assertFalse(self.case.output.exists())

    def test_cli_preserves_omission_and_loads_only_canonical_caller_policy(self):
        policy_path = self.case.root / "policy.json"
        policy_path.write_bytes(workflow.canonical_json_bytes(self.policy))
        destination = self.case.root / "cli-output"
        argv = ["collect", "--input-root", str(self.case.input), "--destination", str(destination),
            "--github-output", str(self.case.output), "--wave", "5", "--state-wave", "0",
            "--trusted-workflow-sha", fixture.PIN]
        for supplied in (False, True):
            with self.subTest(supplied=supplied), patch.object(workflow, "collect") as collect, \
                    patch.dict(workflow.os.environ, {"GITHUB_TOKEN": "synthetic-token"}):
                self.assertEqual(0, workflow.main(argv + (
                    ["--sdk-validation-tooling", str(policy_path)] if supplied else [])))
                collect.assert_called_once_with(self.case.input, destination, self.case.output,
                    wave=5, state_wave=0, trusted_workflow_sha=fixture.PIN, token="synthetic-token",
                    **({"sdk_validation_tooling": self.policy} if supplied else {}))
        for raw in (b"{", b"[]\n", b'{ "evidence": "value" }\n', b'{"a":1,"a":2}\n'):
            with self.subTest(raw=raw), patch.object(workflow, "collect") as collect:
                policy_path.write_bytes(raw)
                with self.assertRaises(SystemExit) as failure:
                    workflow.main(argv + ["--sdk-validation-tooling", str(policy_path)])
                self.assertEqual(2, failure.exception.code)
                collect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
