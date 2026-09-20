"""Caller ordering controls, not source, signature, compiler or hosted acceptance.

Election, joined authority, upload observation, full content gates and Gradle
are explicit seams. Receipt/manifest parsing, inventories, private finalization
and final phase shard verification run their real implementations.
"""

from contextlib import contextmanager
from pathlib import Path
import unittest
from unittest.mock import patch

from ci import sdk_javascript_metadata_workflow as workflow
from ci.tests import test_sdk_javascript_workflow as fixture
from ci.tests.test_sdk_native_package_execution import caller_apple_policy
from ci.tests.product_chain_support import write_receipt
from products.inventory import (
    load_canonical_json_bytes, regular_file_inventory,
    snapshot_regular_tree, write_canonical_json,
)
from products.receipt import write_output_manifest
from products.registry import PhaseInstanceId
from products.restore import PHASE_PLAN_KEYS
from products.sdk_inputs import REQUEST_NAME


CONTRACT_BINARY = PhaseInstanceId("contract", "contract", "binary", "common")
SDK_VALIDATION = PhaseInstanceId("sdk", "javascript", "validation", "node")


class SdkJavaScriptMetadataExecutionTest(unittest.TestCase):
    name = staticmethod(fixture.SdkJavascriptWorkflowTest.name)
    tearDown = fixture.SdkJavascriptWorkflowTest.tearDown

    def setUp(self):
        fixture.SdkJavascriptWorkflowTest.setUp(self)
        self.producer.update(event="pull_request", workflowPath=".github/workflows/ci.yml",
                             runId=71, runAttempt=2, pullRequest=31)
        for identity, version in ((CONTRACT_BINARY, "0.2.0"), (SDK_VALIDATION, "0.2.9")):
            directory = self.originals / self.name(identity)
            stage = directory / "stage"
            (stage / "outputs").mkdir(parents=True)
            (stage / "outputs/synthetic.bin").write_bytes(b"original simulated content\xff\n")
            manifest = write_output_manifest(stage, identity.product, identity.component, identity.phase,
                                             identity.target, version, {"fixture": "outputs"})
            receipt_path = directory / "phase-receipt.json"
            receipt = write_receipt(receipt_path, product=identity.product, component=identity.component,
                phase=identity.phase, target=identity.target, version=version, version_identity=version,
                outputs=manifest["outputs"], upstream=[], context={"producer": self.producer})
            self.original_paths[identity] = {"stage": stage, "receiptPath": receipt_path, "receipt": receipt}
            self.receipts[identity] = receipt_path.read_bytes()
        self.before = regular_file_inventory(self.originals)
        self.selection["consumers"] = [dict(product="sdk", component="javascript", phase="metadata", target="node")]
        elected = write_receipt(self.root / "elected.json", product="sdk", component="javascript", phase="metadata",
            target="node", version="0.2.9", version_identity="0.2.9", outputs=manifest["outputs"], upstream=[],
            context={"producer": self.producer})
        self.ready = {name: elected[name] for name in PHASE_PLAN_KEYS}
        old = self.arguments
        self.arguments = {**{name: old[name] for name in ("trusted_workflow_sha", "keyring", "keys_directory",
            "repository_root", "environ", "token")}, "expected_build_key": self.ready["buildKey"],
            "sdk_inputs_artifact_id": 71, "sdk_inputs_artifact_sha256": old["artifact_sha256"],
            "validation_artifact_id": 72, "validation_artifact_sha256": "sha256:" + "d" * 64,
            "tooling_evidence": self.root / "tooling", "tooling_public_key": self.root / "tooling.pub",
            "java_executable": self.root / "java", "policy_revision": "c" * 40,
            "required_trust_domain": "release", "tooling_keyring": self.root / "tooling-keyring.json",
            "tooling_keys_directory": self.root / "tooling-keys"}
        for name in ("keys_directory", "tooling_evidence", "tooling_keys_directory"):
            path = self.arguments[name]
            path.mkdir()
            (path / "original").write_bytes(b"caller authority boundary")
        for name in ("keyring", "tooling_public_key", "java_executable", "tooling_keyring"):
            self.arguments[name].write_bytes(b"caller authority boundary")
        self.consumer = Path("/observed/original/codex-agent-sdk/build/npm/consumer")
        self.tooling_policy = {"evidence": str(self.arguments["tooling_evidence"]),
            "publicKey": str(self.arguments["tooling_public_key"]),
            "javaExecutable": str(self.arguments["java_executable"]),
            "requiredTrustDomain": "release", "keyring": str(self.arguments["tooling_keyring"]),
            "keysDirectory": str(self.arguments["tooling_keys_directory"])}
        self.capture_path = self.candidate_path = None

    @contextmanager
    def verified(self, *args, **kwargs):
        self.assertEqual((self.plan, self.discovery, self.state), args)
        self.assertEqual({"artifact_id": 71, "artifact_sha256": self.arguments["sdk_inputs_artifact_sha256"],
            **{name: self.arguments[name] for name in ("trusted_workflow_sha", "keyring", "keys_directory",
                                                     "repository_root", "environ", "token")},
            "sdk_validation_tooling": self.tooling_policy}, kwargs)
        self.events.append("enter")
        self.live = True
        try:
            yield self.inputs
            self.events.append("exit-check")
            if self.failure == "late-context":
                raise ValueError("late authenticated inputs failure")
            paths = {"late-plan": self.plan, "late-policy": self.arguments["keyring"],
                "late-input": self.destination / "inputs/producer.json",
                "late-capture": self.capture_path / "transport.zip",
                "late-stage": self.result["stage"] / "outputs/binding-evidence/javascript-typescript-parity.json",
                "late-candidate": self.candidate_path / "phase-receipt.json"}
            if self.failure in paths:
                paths[self.failure].write_bytes(b"changed during context exit")
            self.events.append("exited")
        finally:
            self.live = False

    def materialize(self, plan, discovery, state, identity, destination, **kwargs):
        self.assertTrue(self.live)
        self.events.append("materialize")
        self.assertEqual(PhaseInstanceId("sdk", "javascript", "metadata", "node"), identity)
        self.assertEqual((self.plan, self.discovery, self.state), (plan, discovery, state))
        self.assertEqual(self.destination / "inputs", destination)
        self.assertEqual({"expected_build_key": self.ready["buildKey"], "repository_root": self.repository,
                          "environ": self.arguments["environ"],
                          "sdk_validation_tooling": self.tooling_policy}, kwargs)
        snapshot_regular_tree(self.originals, destination)
        write_canonical_json(destination / "producer.json", self.producer)
        write_canonical_json(destination / "phase-plan.json", self.ready)
        return self.ready

    def capture(self, plan, destination, **kwargs):
        self.assertTrue(self.live)
        self.events.append("capture")
        self.assertEqual(self.plan, plan)
        self.assertEqual(self.receipts[SDK_VALIDATION], kwargs["validation_receipt_path"].read_bytes())
        self.assertEqual(self.destination / "inputs" / self.name(SDK_VALIDATION) / "phase-receipt.json",
                         kwargs["validation_receipt_path"])
        self.assertEqual({"artifact_id": 72, "artifact_sha256": "sha256:" + "d" * 64,
            **{name: self.arguments[name] for name in ("trusted_workflow_sha", "repository_root", "environ", "token")}},
            {name: value for name, value in kwargs.items() if name != "validation_receipt_path"})
        self.assertFalse(destination.is_relative_to(self.repository))
        self.capture_path = destination
        (destination / "original/worker").mkdir(parents=True)
        (destination / "original/worker/gradle.log").write_bytes(b"")
        (destination / "transport.zip").write_bytes(b"opaque observed original upload\xff")
        if self.failure == "capture":
            raise ValueError("observation failed")
        return {"originalConsumerDirectory": str(self.consumer)}

    def package_gate(self, repository, stage, receipt, request, **kwargs):
        self.assertTrue(self.live)
        self.events.append("package")
        self.assertEqual(self.repository, repository)
        self.assertEqual(self.sdk / REQUEST_NAME, request)
        for identity, path in ((fixture.SDK_PACKAGE, receipt),
                               (fixture.NODE_PACKAGE, kwargs["runtime_package_receipt"])):
            self.assertEqual(self.receipts[identity], path.read_bytes())
        self.assertEqual(kwargs["runtime_package_receipt"].parent / "stage", kwargs["runtime_package_stage"])
        self.assertEqual(receipt.parent / "stage", stage)
        if self.failure == "package":
            raise ValueError("package full gate rejected")
        raw = receipt.read_bytes()
        return load_canonical_json_bytes(raw), raw + b"different" if self.failure == "package-pairing" else raw

    def worker(self, ready, **kwargs):
        self.assertTrue(self.live)
        self.events.append("worker")
        self.assertEqual(self.ready, ready)
        self.assertEqual({"producer": self.producer, "sdk_version": "0.2.9", "trust_domain": "development",
            "repository_root": self.repository, "destination": self.destination / "worker",
            "original_consumer_directory": self.consumer, "environ": self.arguments["environ"]},
            {name: value for name, value in kwargs.items() if name != "predecessor"})
        for identity in (CONTRACT_BINARY, fixture.SDK_PACKAGE, SDK_VALIDATION, fixture.NODE_VALIDATION):
            record = kwargs["predecessor"](identity.product, identity.component, identity.phase, identity.target)
            self.assertEqual(self.receipts[identity], record["receiptPath"].read_bytes())
        if self.failure == "worker":
            raise ValueError("fixed process failed")
        stage = self.destination / "synthetic-stage"
        output = stage / "outputs/binding-evidence/javascript-typescript-parity.json"
        output.parent.mkdir(parents=True)
        output.write_bytes(b"synthetic metadata, not parity evidence")
        write_output_manifest(stage, "sdk", "javascript", "metadata", "node", "0.2.9",
                              {"binding-evidence": "outputs/binding-evidence"})
        self.result = {"stage": stage, "diagnostics": kwargs["destination"], "outputInventory": regular_file_inventory(stage)}
        return self.result

    def admission(self, **kwargs):
        self.assertTrue(self.live)
        self.events.append("admission")
        self.assertFalse((self.destination / "shard").exists())
        self.assertFalse(kwargs["metadata_receipt"].is_relative_to(self.repository))
        self.candidate_path = kwargs["metadata_receipt"].parent
        self.assertEqual(self.consumer, kwargs["original_consumer_directory"])
        self.assertEqual(self.repository, kwargs["repository"])
        for name in ("tooling_evidence", "tooling_public_key", "java_executable", "policy_revision",
                     "required_trust_domain", "tooling_keyring", "tooling_keys_directory"):
            self.assertEqual(self.arguments[name], kwargs[name])
        for prefix, identity in (("contract", CONTRACT_BINARY), ("package", fixture.SDK_PACKAGE),
                                 ("validation", SDK_VALIDATION), ("runtime_validation", fixture.NODE_VALIDATION)):
            self.assertEqual(self.receipts[identity], kwargs[prefix + "_receipt"].read_bytes())
            self.assertEqual(kwargs[prefix + "_receipt"].parent / "stage", kwargs[prefix + "_stage"])
        if self.failure == "admission":
            raise ValueError("full metadata gate rejected")
        raw = kwargs["metadata_receipt"].read_bytes()
        return load_canonical_json_bytes(raw), raw + b"different" if self.failure == "admission-pairing" else raw

    def invoke(self):
        with patch.object(workflow.sdk_workflow, "verified_inputs", self.verified), \
                patch.object(workflow.product_reuse, "materialize_product_predecessors", side_effect=self.materialize), \
                patch.object(workflow.product_reuse, "capture_sdk_javascript_validation_upload", side_effect=self.capture), \
                patch.object(workflow, "verify_sdk_package_inputs", side_effect=self.package_gate), \
                patch.object(workflow, "execute_metadata", side_effect=self.worker), \
                patch.object(workflow, "verify_sdk_javascript_metadata_admission", side_effect=self.admission), \
                patch.object(workflow.product_reuse, "_runtime_worker_checkout") as checkout, \
                patch.object(workflow.product_reuse, "finalize_phase_object",
                             wraps=workflow.product_reuse.finalize_phase_object) as finalizer:
            self.finalizer = finalizer
            self.checkout = checkout
            if self.failure == "late-checkout":
                checkout.side_effect = ValueError("candidate checkout changed after admission")
            return workflow.execute(self.plan, self.discovery, self.state, self.destination, **self.arguments)

    def test_real_private_finalization_full_gate_and_context_exit_precede_public_shard(self):
        result = self.invoke()
        self.assertEqual(["enter", "materialize", "capture", "package", "worker", "admission", "exit-check", "exited"], self.events)
        self.finalizer.assert_called_once()
        self.checkout.assert_called_with(self.repository, self.producer)
        self.assertEqual(self.producer, result["receipt"]["producer"])
        self.assertEqual("development", result["receipt"]["trustDomain"])
        self.assertEqual("0.2.9", result["receipt"]["productVersion"])
        self.assertEqual(b"opaque observed original upload\xff", (self.destination / "validation-upload/transport.zip").read_bytes())
        self.assertEqual(b"", (self.destination / "validation-upload/original/worker/gradle.log").read_bytes())
        self.assertFalse(self.capture_path.exists())
        self.assertFalse(self.candidate_path.exists())

    def test_explicit_apple_policy_reaches_both_replays_without_replacing_existing_gates(self):
        policy = caller_apple_policy(self.root / "caller")
        before = dict(policy)
        self.arguments["sdk_apple_validation_policy"] = policy

        def forwarded(delegate):
            def invoke(*args, **kwargs):
                self.assertIs(policy, kwargs.pop("sdk_apple_validation_policy"))
                return delegate(*args, **kwargs)
            return invoke

        with patch.object(self, "verified", side_effect=forwarded(self.verified)) as verified, \
                patch.object(self, "materialize", side_effect=forwarded(self.materialize)) as materialize:
            result = self.invoke()
        for replay in (verified, materialize):
            replay.assert_called_once()
            self.assertIs(policy, replay.call_args.kwargs["sdk_apple_validation_policy"])
        self.assertEqual(before, policy)
        self.assertNotIn("sdkAppleValidationPolicy", result["receipt"])
        self.assertNotIn("sdk_apple_validation_policy", result["receipt"])
        self.assertEqual(["enter", "materialize", "capture", "package", "worker", "admission", "exit-check", "exited"], self.events)

    def test_missing_locator_uses_only_selected_original_then_runs_unchanged_capture(self):
        self.arguments.pop("validation_artifact_id")
        self.arguments.pop("validation_artifact_sha256")

        def locate(receipt, **kwargs):
            self.assertTrue(self.live)
            self.assertEqual(self.receipts[SDK_VALIDATION], receipt.read_bytes())
            self.assertEqual({"trusted_workflow_sha": self.arguments["trusted_workflow_sha"],
                              "token": self.arguments["token"]}, kwargs)
            self.assertNotIn("capture", self.events)
            return {"artifact_id": 72, "artifact_sha256": "sha256:" + "d" * 64}

        with patch("sdk_javascript_validation_locator.locate_javascript_validation_upload", side_effect=locate) as discover:
            self.invoke()
        discover.assert_called_once()
        self.assertIn("capture", self.events)

    def test_unpaired_explicit_locator_rejects_without_discovery(self):
        self.arguments.pop("validation_artifact_sha256")
        with self.assertRaisesRegex(ValueError, "supplied together"):
            self.invoke()
        self.assertEqual([], self.events)

    def test_wrong_selection_current_contract_or_each_retained_runtime_receipt_rejects(self):
        for kind in ("selection", "contract", "runtime-package", "runtime-validation"):
            self.setUp()
            if kind == "selection": self.selection["consumers"] = []
            elif kind == "contract": self.selection["contractPayloadSha256"] = "sha256:" + "e" * 64
            else:
                identity = fixture.NODE_PACKAGE if kind == "runtime-package" else fixture.NODE_VALIDATION
                self.inputs["runtime"]["receiptBytes"][identity] += b"\n"
            with self.subTest(kind=kind), self.assertRaises(ValueError): self.invoke()
            self.finalizer.assert_not_called()
            self.assertNotIn("worker", self.events)
            self.assertFalse((self.destination / "shard").exists())

    def test_gate_and_context_failures_never_publish_candidate_or_validation_capture(self):
        for failure in ("capture", "package", "package-pairing", "worker", "admission", "admission-pairing",
                        "late-context", "late-plan", "late-policy", "late-input", "late-capture", "late-stage", "late-candidate",
                        "late-checkout"):
            self.setUp()
            self.failure = failure
            with self.subTest(failure=failure), self.assertRaises(ValueError): self.invoke()
            self.assertFalse((self.destination / "shard").exists())
            self.assertFalse((self.destination / "validation-upload").exists())

    def test_destination_original_overlap_and_existing_output_are_preserved(self):
        self.destination.mkdir(parents=True)
        sentinel = self.destination / "sentinel"
        sentinel.write_bytes(b"keep original")
        with self.assertRaisesRegex(ValueError, "must not exist"): self.invoke()
        self.assertEqual(b"keep original", sentinel.read_bytes())
        self.destination = self.discovery / "nested"
        with self.assertRaisesRegex(ValueError, "overlaps"): self.invoke()
        self.assertFalse(self.destination.exists())


if __name__ == "__main__":
    unittest.main()
