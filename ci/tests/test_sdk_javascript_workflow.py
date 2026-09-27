"""Controller ordering only: election, signed input capture and worker are seams.

Real files exercise original receipt pairing and before/after inventories. These
synthetic stages are not compiled products or hosted/signature acceptance.
"""

from contextlib import contextmanager
from copy import deepcopy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci import sdk_workflow as workflow
from ci.tests.product_chain_support import write_receipt
from ci.tests.test_product_plan import PRODUCER
import sdk_javascript_phase as worker
from products.inventory import regular_file_inventory, snapshot_regular_tree, write_canonical_json
from products.receipt import write_output_manifest
from products.registry import PhaseInstanceId
from products.sdk_inputs import REQUEST_NAME


CONTRACT = PhaseInstanceId("contract", "contract", "metadata", "common")
NODE_PACKAGE = PhaseInstanceId("runtime", "node-js", "package", "node-js")
NODE_VALIDATION = PhaseInstanceId("runtime", "node-js", "validation", "node-js-binding")
SDK_PACKAGE = PhaseInstanceId("sdk", "javascript", "package", "node")


class SdkJavascriptWorkflowTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sdk-javascript-controller-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.repository = self.root / "repository"
        self.repository.mkdir()
        self.plan = self.repository / "plan.json"
        self.plan.write_bytes(b'{"synthetic":"mocked elected plan boundary"}\n')
        self.discovery, self.state = self.repository / "discovery", self.repository / "state"
        self.discovery.mkdir()
        self.state.mkdir()
        self.destination = self.repository / "build/worker"
        self.producer = deepcopy(PRODUCER)
        self.originals = self.root / "originals"
        self.receipts, self.original_paths = {}, {}
        for identity in (CONTRACT, NODE_PACKAGE, NODE_VALIDATION, SDK_PACKAGE):
            directory = self.originals / self.name(identity)
            stage = directory / "stage"
            (stage / "outputs").mkdir(parents=True)
            (stage / "outputs/synthetic.bin").write_bytes(b"synthetic original bytes\x00\xff\n")
            kind = "contract-bundle" if identity == CONTRACT else "fixture"
            version = "0.2.0" if identity.product == "contract" else "0.2.7" if identity.product == "runtime" else "0.2.9"
            manifest = write_output_manifest(stage, identity.product, identity.component, identity.phase,
                identity.target, version, {kind: "outputs"})
            path = directory / "phase-receipt.json"
            receipt = write_receipt(path, product=identity.product, component=identity.component,
                phase=identity.phase, target=identity.target, version=version, version_identity=version,
                outputs=manifest["outputs"], upstream=[], context={"producer": self.producer})
            self.receipts[identity] = path.read_bytes()
            self.original_paths[identity] = {"stage": stage, "receiptPath": path, "receipt": receipt}
        self.before = regular_file_inventory(self.originals)
        self.selection = {"source": "released-default", "sdkVersion": "0.2.9",
            "contractPayloadSha256": self.original_paths[CONTRACT]["receipt"]["outputs"][0]["sha256"],
            "consumers": [{"product": "sdk", "component": "javascript", "phase": phase, "target": "node"}
                          for phase in ("package", "validation")]}
        self.sdk = self.root / "verified-sdk"
        self.sdk.mkdir()
        (self.sdk / REQUEST_NAME).write_bytes(b'{"synthetic":"verified request seam"}\n')
        self.inputs = {"selection": self.selection, "sdk": {"directory": self.sdk}, "runtime": {
            "originalPhases": self.original_paths,
            "receiptBytes": {identity: raw for identity, raw in self.receipts.items() if identity.product == "runtime"}}}
        self.arguments = {"expected_build_key": "sha256:" + "a" * 64, "artifact_id": 71,
            "artifact_sha256": "sha256:" + "b" * 64, "trusted_workflow_sha": "c" * 40,
            "keyring": self.root / "caller-keyring.json", "keys_directory": self.root / "caller-keys",
            "repository_root": self.repository, "environ": {"GITHUB_RUN_ID": "7"}, "token": "caller-token"}
        self.events, self.live = [], False
        self.failure = None
        self.result = None

    @staticmethod
    def name(identity):
        return "-".join((identity.product, identity.component, identity.phase, identity.target))

    def tearDown(self):
        self.assertEqual(self.before, regular_file_inventory(self.originals))

    @contextmanager
    def verified(self, *args, **kwargs):
        self.events.append("enter")
        self.live = True
        try:
            yield self.inputs
            self.events.append("exit-check")
            if self.failure == "late-context":
                raise ValueError("synthetic late original-input rejection")
            if self.failure == "late-output":
                (self.result["stage"] / "synthetic-output.bin").write_bytes(b"changed after worker\n")
            self.events.append("exited")
        finally:
            self.live = False

    def materialize(self, plan, discovery, state, identity, destination, **arguments):
        self.assertTrue(self.live)
        self.events.append("materialize")
        self.assertEqual((self.plan, self.discovery, self.state), (plan, discovery, state))
        self.assertEqual(self.destination / "inputs", destination)
        self.assertEqual({"expected_build_key": self.arguments["expected_build_key"],
            "repository_root": self.repository, "environ": self.arguments["environ"],
            "sdk_original_workflow_sha": self.arguments["trusted_workflow_sha"]}, arguments)
        # This is the explicit original-object materialization seam. No claim
        # is made that these representative stages satisfy the whole planner.
        snapshot_regular_tree(self.originals, destination)
        write_canonical_json(destination / "producer.json", self.producer)
        self.ready = {"schemaVersion": 1, "product": identity.product, "component": identity.component,
                      "phase": identity.phase, "target": identity.target,
                      "buildKey": self.arguments["expected_build_key"], "inputs": {}}
        write_canonical_json(destination / "phase-plan.json", self.ready)
        return self.ready

    def execute(self, ready, **arguments):
        self.assertTrue(self.live)
        self.events.append("worker")
        self.assertEqual(self.ready, ready)
        self.assertEqual(self.producer, arguments["producer"])
        self.assertEqual("0.2.9", arguments["sdk_version"])
        self.assertEqual("development" if self.producer["event"] == "pull_request" else "release",
                         arguments["trust_domain"])
        self.assertEqual(self.sdk / REQUEST_NAME if ready["phase"] == "package" else None,
                         arguments["compatibility_request"])
        runtime = NODE_PACKAGE if ready["phase"] == "package" else NODE_VALIDATION
        value = arguments["predecessor"](runtime.product, runtime.component, runtime.phase, runtime.target)
        self.assertEqual(self.receipts[runtime], value["receiptPath"].read_bytes())
        self.assertTrue(value["stage"].is_relative_to(self.destination / "inputs"))
        if self.failure == "worker":
            raise ValueError("synthetic worker failure")
        if self.failure == "changed-input":
            (value["stage"] / "outputs/synthetic.bin").write_bytes(b"changed worker input\n")
        stage = self.destination / "synthetic-stage"
        stage.mkdir()
        (stage / "synthetic-output.bin").write_bytes(b"synthetic worker output\n")
        self.result = {"stage": stage, "diagnostics": arguments["destination"],
                       "outputInventory": regular_file_inventory(stage)}
        return self.result

    def finalize(self, **arguments):
        self.assertFalse(self.live)
        self.assertEqual("exited", self.events[-1])
        self.events.append("finalize")
        self.assertEqual({"stage_root": self.result["stage"], "phase_plan": self.ready,
            "producer": self.producer, "product_version": "0.2.9",
            "trust_domain": "development" if self.producer["event"] == "pull_request" else "release",
            "destination": self.destination / "shard"}, arguments)
        return {"synthetic": "finalizer invoked after verified contexts"}

    def invoke(self, phase="package"):
        with patch.object(workflow, "verified_inputs", side_effect=self.verified) as verified, \
                patch.object(workflow.product_reuse, "materialize_product_predecessors", side_effect=self.materialize) as materializer, \
                patch.object(worker, "execute", side_effect=self.execute) as execution, \
                patch.object(workflow.product_reuse, "finalize_phase_object", side_effect=self.finalize) as finalizer:
            self.mocks = verified, materializer, execution, finalizer
            return workflow.execute_javascript(self.plan, self.discovery, self.state, self.destination,
                                                phase=phase, **self.arguments)

    def test_package_and_validation_finalize_only_after_verified_context_exit(self):
        for phase in ("package", "validation"):
            with self.subTest(phase=phase):
                self.destination = self.repository / f"build/{phase}"
                self.events.clear()
                if phase == "validation":
                    self.producer.update(event="merge_group", pullRequest=None)
                self.assertEqual({"synthetic": "finalizer invoked after verified contexts"}, self.invoke(phase))
                self.assertEqual(["enter", "materialize", "worker", "exit-check", "exited", "finalize"], self.events)
                self.mocks[0].assert_called_once_with(self.plan, self.discovery, self.state,
                    **{name: value for name, value in self.arguments.items() if name != "expected_build_key"})
                self.mocks[3].assert_called_once()

    def test_wrong_selected_identity_never_materializes_or_executes(self):
        self.selection["consumers"] = [{"product": "sdk", "component": "python", "phase": "package", "target": "desktop"}]
        with self.assertRaisesRegex(ValueError, "not selected"):
            self.invoke()
        for mocked in self.mocks[1:]:
            mocked.assert_not_called()
        self.assertFalse(self.destination.exists())

    def test_mismatched_runtime_original_receipt_never_finalizes(self):
        self.inputs["runtime"]["receiptBytes"][NODE_PACKAGE] = self.receipts[NODE_PACKAGE] + b"\n"
        with self.assertRaisesRegex(ValueError, "differs from the verified original"):
            self.invoke()
        self.mocks[3].assert_not_called()
        self.assertFalse((self.destination / "shard").exists())

    def test_current_contract_payload_mismatch_rejects_before_worker(self):
        self.selection["contractPayloadSha256"] = "sha256:" + "d" * 64
        with self.assertRaisesRegex(ValueError, "current Contract differs"):
            self.invoke()
        self.mocks[2].assert_not_called()
        self.mocks[3].assert_not_called()

    def test_worker_late_context_output_and_input_failures_never_finalize(self):
        for failure, message in (("worker", "worker failure"), ("late-context", "late original-input rejection"),
                                 ("late-output", "output changed before finalization"),
                                 ("changed-input", "inputs changed during execution")):
            self.failure = failure
            self.destination = self.repository / "build" / failure
            self.events.clear()
            with self.subTest(failure=failure), self.assertRaisesRegex(ValueError, message):
                self.invoke()
            self.mocks[3].assert_not_called()
            self.assertFalse((self.destination / "shard").exists())
            self.assertNotIn("finalize", self.events)

    def test_cli_forwards_fixed_worker_inputs_and_rejects_command_override(self):
        paths = {"plan": self.plan, "discovery-root": self.discovery, "state-root": self.state,
            "destination": self.destination, "repository-root": self.repository,
            "keyring": self.arguments["keyring"], "keys-directory": self.arguments["keys_directory"]}
        argv = ["javascript", "--phase", "package", *[
            item for name, value in paths.items() for item in (f"--{name}", str(value))]]
        for name in ("expected_build_key", "artifact_id", "artifact_sha256", "trusted_workflow_sha"):
            argv.extend(("--" + name.replace("_", "-"), str(self.arguments[name])))
        with patch.dict(os.environ, {"GITHUB_TOKEN": "cli-token"}, clear=True), \
                patch.object(workflow, "execute_javascript") as execute:
            self.assertEqual(0, workflow.main(argv))
            execute.assert_called_once_with(self.plan, self.discovery, self.state, self.destination,
                **{**self.arguments, "phase": "package", "environ": os.environ, "token": "cli-token"})
        with patch.object(workflow, "execute_javascript") as execute, self.assertRaises(SystemExit):
            workflow.main([*argv, "--command", "caller-selected-command"])
        execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
