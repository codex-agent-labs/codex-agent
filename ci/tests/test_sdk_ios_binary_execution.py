"""iOS binary controller lifetime only; input authority/worker/finalizer are mocks.

Synthetic files exercise inventory rechecks, not compiler, signature, hosted
execution or product receipt acceptance.
"""

from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci import sdk_workflow as workflow
from ci.tests.test_product_plan import PRODUCER
from products.inventory import regular_file_inventory
import sdk_ios_binary as worker


class SdkIosBinaryExecutionTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sdk-ios-binary-controller-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.repository = self.root / "repository"
        self.repository.mkdir()
        self.plan = self.repository / "plan.json"
        self.plan.write_bytes(b'{"synthetic":"input authority seam"}\n')
        self.discovery, self.state = self.repository / "discovery", self.repository / "state"
        self.discovery.mkdir()
        self.state.mkdir()
        self.destination = self.repository / "build/ios-binary"
        self.producer = deepcopy(PRODUCER)
        self.key = "sha256:" + "a" * 64
        self.ready = {"schemaVersion": 1, "product": "sdk", "component": "sdk-ios", "phase": "binary",
                      "target": "ios", "buildKey": self.key, "inputs": {}}
        self.options = {"expected_build_key": self.key, "native_uploads": {"synthetic": "exact caller uploads"},
            "trusted_workflow_sha": "c" * 40, "repository_root": self.repository,
            "environ": {"GITHUB_RUN_ID": "7"}, "token": "caller-token"}
        self.events, self.live = [], False
        self.failure = None
        self.result = None

    @contextmanager
    def inputs(self, plan, discovery, state, destination, **arguments):
        self.assertEqual((self.plan, self.discovery, self.state, self.destination / "inputs"),
                         (plan, discovery, state, destination))
        self.assertEqual(self.options, arguments)
        self.events.append("enter")
        self.live = True
        for name in ("metadata-stage", "contract-handoff", "native"):
            (destination / name).mkdir(parents=True)
            (destination / name / "synthetic-input").write_bytes(b"original controller input\n")
        receipt = destination / "metadata-receipt.json"
        receipt.write_bytes(b'{"synthetic":"already verified receipt boundary"}\n')
        self.value = {"ready": self.ready, "producer": self.producer, "sdkVersion": "0.2.9",
            "contract": {"stage": destination / "metadata-stage", "receiptPath": receipt,
                         "receipt": {"synthetic": "already verified record"}},
            "contractHandoff": destination / "contract-handoff", "native": destination / "native",
            "inputs": destination}
        before = regular_file_inventory(destination)
        try:
            yield self.value
            self.events.append("exit-check")
            if self.failure == "context":
                raise ValueError("synthetic original context exit rejected")
            if regular_file_inventory(destination) != before:
                raise ValueError("synthetic original context input mutation")
            if self.failure == "output":
                (self.result["stage"] / "synthetic-output").write_bytes(b"changed before finalization\n")
            self.events.append("exited")
        finally:
            self.live = False

    def execute(self, ready, **arguments):
        self.assertTrue(self.live)
        self.assertEqual(self.ready, ready)
        self.assertEqual({"producer": self.producer, "sdk_version": "0.2.9",
            "contract_metadata": self.value["contract"], "verified_contract_handoff": self.value["contractHandoff"],
            "native_evidence": self.value["native"], "repository_root": self.repository,
            "destination": self.destination / "worker", "environ": self.options["environ"]}, arguments)
        self.events.append("worker")
        if self.failure == "worker":
            raise ValueError("synthetic leaf failure")
        if self.failure == "input":
            self.value["contract"]["receiptPath"].write_bytes(b"changed during worker\n")
        stage = self.destination / "synthetic-stage"
        stage.mkdir()
        (stage / "synthetic-output").write_bytes(b"not a compiled iOS product\n")
        self.result = {"stage": stage, "diagnostics": self.destination / "worker",
                       "outputInventory": regular_file_inventory(stage)}
        return self.result

    def finalize(self, **arguments):
        self.assertFalse(self.live)
        self.assertEqual("exited", self.events[-1])
        self.assertEqual({"stage_root": self.result["stage"], "phase_plan": self.ready,
            "producer": self.producer, "product_version": "0.2.9",
            "trust_domain": "development" if self.producer["event"] == "pull_request" else "release",
            "destination": self.destination / "shard"}, arguments)
        self.events.append("finalize")
        return {"synthetic": "finalizer result"}

    def invoke(self):
        with patch.object(workflow, "verified_ios_binary_inputs", side_effect=self.inputs) as inputs, \
                patch.object(worker, "execute", side_effect=self.execute) as execute, \
                patch.object(workflow.product_reuse, "finalize_phase_object", side_effect=self.finalize) as finalize:
            self.mocks = inputs, execute, finalize
            return workflow.execute_ios_binary(self.plan, self.discovery, self.state, self.destination, **self.options)

    def test_exact_binary_inputs_forwarded_and_finalize_follows_successful_context_exit(self):
        for event in ("pull_request", "merge_group"):
            self.destination = self.repository / "build" / event
            self.producer.update(event=event, pullRequest=2 if event == "pull_request" else None)
            self.events.clear()
            with self.subTest(event=event):
                self.assertEqual({"synthetic": "finalizer result"}, self.invoke())
                self.assertEqual(["enter", "worker", "exit-check", "exited", "finalize"], self.events)
                for mocked in self.mocks:
                    mocked.assert_called_once()

    def test_leaf_failure_never_finalizes(self):
        self.failure = "worker"
        with self.assertRaisesRegex(ValueError, "leaf failure"):
            self.invoke()
        self.mocks[2].assert_not_called()
        self.assertFalse((self.destination / "shard").exists())
        self.assertFalse(self.live)

    def test_context_exit_error_input_mutation_and_output_mutation_never_finalize(self):
        for failure, message in (("context", "context exit rejected"), ("input", "context input mutation"),
                                 ("output", "output changed before finalization")):
            self.failure = failure
            self.destination = self.repository / "build" / failure
            self.events.clear()
            with self.subTest(failure=failure), self.assertRaisesRegex(ValueError, message):
                self.invoke()
            self.mocks[2].assert_not_called()
            self.assertFalse((self.destination / "shard").exists())
            self.assertNotIn("finalize", self.events)
            self.assertFalse(self.live)

    def test_existing_destination_preserved_before_input_context_or_worker(self):
        self.destination.mkdir(parents=True)
        (self.destination / "sentinel").write_bytes(b"preserve original output\n")
        before = regular_file_inventory(self.destination)
        with self.assertRaisesRegex(ValueError, "fresh destination"):
            self.invoke()
        for mocked in self.mocks:
            mocked.assert_not_called()
        self.assertEqual(before, regular_file_inventory(self.destination))


if __name__ == "__main__":
    unittest.main()
