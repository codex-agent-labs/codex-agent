"""C# controller lifetime only; authentication, election and product gates are seams.

Reuse the existing Python controller fixture without changing it. Small canonical
binary receipts/stages, finalization, inventories and publication remain real.
"""

from contextlib import contextmanager
from pathlib import Path
import unittest
from unittest.mock import patch

from ci.tests import test_sdk_native_package_execution as fixture
from ci.tests.product_chain_support import reference, write_receipt
from products.inventory import regular_file_inventory, snapshot_regular_tree
from products.receipt import compute_build_key, write_output_manifest
from products.registry import PhaseInstanceId
import tooling_inspector


class CSharpInspectorControllerTest(unittest.TestCase):
    def setUp(self):
        self.case = case = fixture.SdkNativePackageExecutionTest(methodName="runTest")
        case.setUp()
        self.addCleanup(case.doCleanups)
        self.addCleanup(case.tearDown)
        self.binary_identity = PhaseInstanceId("sdk", "csharp", "binary", "desktop")
        self.binary = case.root / "csharp-original/stage"
        output = self.binary / "outputs/csharp"
        output.mkdir(parents=True)
        for name in ("CodexAgent.dll", "CodexAgent.pdb", "CodexAgent.xml", "CodexAgent.deps.json",
                     "sdk-compatibility.json", "sdk-runtime-root.pub"):
            (output / name).write_bytes(("synthetic binary fixture: " + name).encode())
        manifest = write_output_manifest(self.binary, "sdk", "csharp", "binary", "desktop", "0.3.0",
                                         {"csharp-binary": "outputs/csharp"})
        self.binary_receipt = self.binary.parent / "phase-receipt.json"
        binary = write_receipt(self.binary_receipt, product="sdk", component="csharp", phase="binary",
            target="desktop", version="0.3.0", version_identity="0.3.0", outputs=manifest["outputs"],
            upstream=[], context={"producer": case.producer})
        self.binary_before = regular_file_inventory(self.binary.parent)
        case.ready["component"] = "csharp"
        case.ready["inputs"]["upstreamArtifacts"] = [reference(binary)]
        case.ready["buildKey"] = compute_build_key(**{name: case.ready[name] for name in
            ("product", "component", "phase", "target", "inputs")})
        case.arguments.update(component="csharp", expected_build_key=case.ready["buildKey"])
        self.policy = {"explicit": "mocked external authentication boundary"}
        self.capability, self.capability_live = object(), False
        self.late_failure = False

    def without_tooling(self, arguments):
        self.assertIs(self.policy, arguments.pop("sdk_validation_tooling"))
        return arguments

    @contextmanager
    def verified(self, *args, **kwargs):
        with self.case.verified(*args, **self.without_tooling(kwargs)) as value:
            yield value

    def inspect(self, *args, **kwargs):
        return self.case.inspect(*args, **self.without_tooling(kwargs))

    def materialize(self, plan, discovery, state, identity, destination, **kwargs):
        case = self.case
        self.without_tooling(kwargs)
        self.assertEqual(PhaseInstanceId("sdk", "csharp", "package", "desktop"), identity)
        base_scope = (fixture.fixture.CONTRACT, *case.original_paths)
        self.assertEqual((*base_scope, self.binary_identity), kwargs["materialized_scope"])
        # Reuse the fixture's existing Runtime/Contract copy and strict checks;
        # only its Python-specific identity assertion needs this local adapter.
        kwargs["materialized_scope"] = base_scope
        ready = case.materialize(plan, discovery, state,
            PhaseInstanceId("sdk", "python", "package", "desktop"), destination, **kwargs)
        binary = destination / case.name(self.binary_identity)
        snapshot_regular_tree(self.binary, binary / "stage")
        (binary / "phase-receipt.json").write_bytes(self.binary_receipt.read_bytes())
        return ready

    @contextmanager
    def authenticated(self, policy, repository, revision):
        case = self.case
        self.assertIs(self.policy, policy)
        self.assertEqual((case.root, case.producer["commit"]), (repository, revision))
        self.assertTrue(case.live)
        case.events.append("inspector-enter")
        self.capability_live = True
        try:
            yield self.capability
        finally:
            case.events.append("inspector-exit")
            self.capability_live = False
            if self.late_failure:
                raise ValueError("late inspector authentication failure")

    def worker(self, ready, **kwargs):
        case = self.case
        self.assertTrue(self.capability_live)
        self.assertIs(self.capability, kwargs.pop("csharp_inspector"))
        self.assertEqual(case.destination / "inputs/sdk-csharp-binary-desktop/stage",
                         kwargs.pop("csharp_binary_stage"))
        result = case.worker(ready, **kwargs)
        write_output_manifest(result["stage"], "sdk", "csharp", "package", "desktop", "0.3.0",
                              {"package": "outputs"})
        result["outputInventory"] = regular_file_inventory(result["stage"])
        return result

    def gate(self, *args, **kwargs):
        self.assertTrue(self.capability_live)
        self.assertIs(self.capability, kwargs.pop("csharp_inspector"))
        binary = self.case.destination / "inputs/sdk-csharp-binary-desktop"
        self.assertEqual(binary / "stage", kwargs.pop("binary_stage_root"))
        self.assertEqual(binary / "phase-receipt.json", kwargs.pop("binary_receipt_path"))
        return self.case.gate(*args, **kwargs)

    def invoke(self):
        case, workflow = self.case, fixture.workflow
        publish = workflow.publish_regular_tree

        def publish_after_exit(source, destination, **kwargs):
            self.assertFalse(self.capability_live)
            self.assertFalse(case.live)
            self.assertIn("inspector-exit", case.events)
            self.assertIn("exited", case.events)
            case.events.append("publish:" + Path(destination).name)
            return publish(source, destination, **kwargs)

        with patch.object(workflow.sdk_workflow, "verified_inputs", self.verified), \
                patch.object(workflow.product_reuse, "inspect_products", side_effect=self.inspect), \
                patch.object(workflow.product_reuse, "capture_sdk_native_prepared_upload", side_effect=case.capture), \
                patch.object(workflow.product_reuse, "materialize_product_predecessors", side_effect=self.materialize), \
                patch.object(workflow, "execute_package", side_effect=self.worker) as worker, \
                patch.object(workflow, "verify_sdk_package_inputs", side_effect=self.gate) as gate, \
                patch.object(tooling_inspector, "authenticated_inspector", side_effect=self.authenticated) as capture, \
                patch.object(workflow, "publish_regular_tree", side_effect=publish_after_exit) as published:
            self.worker_mock, self.gate_mock, self.capture_mock, self.publish_mock = worker, gate, capture, published
            return workflow.execute(case.plan_path, case.discovery, case.state, case.destination,
                                    **case.arguments, sdk_validation_tooling=self.policy)

    def test_same_live_inspector_wraps_worker_and_full_gate_then_closes_before_publication(self):
        result = self.invoke()
        self.assertEqual("csharp", result["receipt"]["component"])
        self.assertEqual(self.case.gate_receipt, (self.case.destination / "shard/phase-receipt.json").read_bytes())
        self.assertEqual(["enter", "inspect", "capture", "materialize", "inspector-enter", "worker", "gate",
                          "inspector-exit", "exit-check", "exited", "publish:prepared-upload", "publish:shard"],
                         self.case.events)
        self.capture_mock.assert_called_once()
        self.worker_mock.assert_called_once()
        self.gate_mock.assert_called_once()
        self.assertEqual(2, self.publish_mock.call_count)
        self.assertEqual(self.binary_before, regular_file_inventory(self.binary.parent))

    def test_late_inspector_exit_failure_publishes_neither_shard_nor_preparation_capture(self):
        self.late_failure = True
        with self.assertRaisesRegex(ValueError, "late inspector authentication failure"):
            self.invoke()
        self.capture_mock.assert_called_once()
        self.worker_mock.assert_called_once()
        self.gate_mock.assert_called_once()
        self.publish_mock.assert_not_called()
        self.assertFalse(self.capability_live)
        self.assertFalse(self.case.live)
        self.assertFalse((self.case.destination / "shard").exists())
        self.assertFalse((self.case.destination / "prepared-upload").exists())
        self.assertEqual(self.binary_before, regular_file_inventory(self.binary.parent))
