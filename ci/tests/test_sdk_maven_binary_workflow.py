"""Orchestration fixtures: real manifests/receipts/shards, mocked authority gates."""

from contextlib import redirect_stderr
from copy import deepcopy
import io
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ci import sdk_maven_binary_workflow as workflow
from ci.tests.product_chain_support import write_receipt
from ci.tests.test_sdk_facade_workflow import assert_metadata_cli_context
from products.inventory import load_canonical_json_bytes, sha256_file, snapshot_regular_tree, write_canonical_json
from products.receipt import write_output_manifest
from products.restore import PHASE_PLAN_KEYS


class MavenBinaryWorkflowTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.plan = self.root / "plan.json"
        self.plan.write_bytes(b"{}\n")
        self.discovery = self.root / "discovery"
        self.discovery.mkdir()
        self.destination = self.root / "build/upload"
        self.producer = {"repository": "fixture/repository", "commit": "a" * 40, "tree": "b" * 40,
            "event": "pull_request", "workflowPath": ".github/workflows/product-validation.yml",
            "runId": 10, "runAttempt": 1, "pullRequest": 2}
        self.evidence_root = self.root / "contract-original"
        self.evidence_root.mkdir()
        self.evidence = {"expectedTrustDomain": "release"}
        for key in ("attestation", "attestationSignature", "publicKey"):
            path = self.evidence_root / key
            path.write_bytes(b"mocked original signature authority: " + key.encode())
            self.evidence[key] = str(path)
        closure = self.evidence_root / "execution-closure"
        closure.mkdir()
        (closure / "original.json").write_bytes(b"exact original closure")
        self.contracts = {phase: self.record("contract", "contract", phase, "common")
                          for phase in ("binary", "package", "validation", "metadata")}
        self.archive = self.root / "android-runtime.tar.gz"
        self.archive.write_bytes(b"preprovisioned pinned archive; executor gate mocked")
        self.configure("sdk-core")
        self.state = self.enterContext(patch.object(workflow.product_reuse, "_verified_product_state",
                                                    side_effect=lambda *a, **k: self.verified))
        self.trust = self.enterContext(patch.object(workflow.product_reuse, "_release_trust", side_effect=self.policy))
        self.materialized = self.enterContext(patch.object(workflow.product_reuse, "_materialize_product_predecessors",
                                                         side_effect=self.materialize))
        self.capture = self.enterContext(patch.object(workflow.product_reuse, "_capture_runtime_contract",
                                                    side_effect=self.capture_contract))
        self.projection = self.enterContext(patch.object(workflow, "verify_contract_component_projection"))
        self.worker = self.enterContext(patch.object(workflow, "execute_binary", side_effect=self.produce))
        self.gate = self.enterContext(patch.object(workflow, "verify_sdk_maven_binary_content"))
        self.checkout = self.enterContext(patch.object(workflow.product_reuse, "_runtime_worker_checkout"))
        self.finalize = self.enterContext(patch.object(workflow.product_reuse, "finalize_phase_object",
                                                      wraps=workflow.product_reuse.finalize_phase_object))

    def record(self, product, component, phase, target):
        stage = self.root / (component + "-" + phase) / "stage"
        output = stage / "outputs/artifact.bin"
        output.parent.mkdir(parents=True)
        output.write_bytes((component + phase).encode())
        manifest = write_output_manifest(stage, product, component, phase, target, "0.8.7", {"fixture": "outputs"})
        receipt = stage.parent / "phase-receipt.json"
        value = write_receipt(receipt, product=product, component=component, phase=phase, target=target,
            version="0.8.7", version_identity="0.8.7", outputs=manifest["outputs"], upstream=[],
            context={"producer": self.producer})
        return {"stage": stage, "receiptPath": receipt, "receipt": value}

    def configure(self, component):
        self.component = component
        self.target = "common" if component == "sdk-core" else "android"
        self.binary = self.record("sdk", component, "binary", self.target)
        self.ready = {name: self.binary["receipt"][name] for name in PHASE_PLAN_KEYS}
        self.instance = workflow.PhaseInstanceId("sdk", component, "binary", self.target)
        self.verified = SimpleNamespace(prior_ready_plans={self.instance: deepcopy(self.ready)},
            plan={"validationCommit": "a" * 40}, producer=self.producer,
            expected_fixed={"versions": {"sdk": "0.8.7"}}, rebased_request={"contractEvidence": self.evidence})

    def policy(self, root, revision, destination):
        self.assertEqual("a" * 40, revision)
        destination.mkdir()
        ring, keys = destination / "keyring.json", destination / "keys"
        ring.write_bytes(b"mocked Git policy")
        keys.mkdir()
        (keys / "release.pub").write_bytes(b"mocked public key")
        return SimpleNamespace(keyring=ring, keys=keys)

    def materialize(self, state, instance, destination, key, root):
        self.assertEqual(self.instance, instance)
        self.assertEqual(self.ready["buildKey"], key)
        destination.mkdir()
        for phase, record in self.contracts.items():
            directory = destination / ("contract-contract-" + phase + "-common")
            snapshot_regular_tree(record["stage"], directory / "stage")
            (directory / "phase-receipt.json").write_bytes(record["receiptPath"].read_bytes())
        write_canonical_json(destination / "phase-plan.json", self.ready)
        write_canonical_json(destination / "producer.json", self.producer)
        return deepcopy(self.ready)

    def capture_contract(self, root, evidence, original, one_output, prepared, trust):
        records = {phase: original("contract", "contract", phase, "common") for phase in self.contracts}
        handoff = prepared / "contract-input"
        snapshot_regular_tree(self.evidence_root, handoff)
        return records["metadata"], "0.8.7", handoff, {"mocked": "full signed Contract gate"}, workflow._inventory(handoff)

    def produce(self, plan, **arguments):
        self.assertEqual(self.ready, plan)
        self.assertEqual(self.producer, arguments["producer"])
        self.assertEqual("0.8.7", arguments["sdk_version"])
        self.assertNotIn("sdk_binary", arguments)
        self.assertNotIn("compatibility_request", arguments)
        self.assertFalse((self.destination / "shard").exists())
        if self.component == "sdk-android":
            self.assertEqual(self.archive.read_bytes(), arguments["android_runtime_archive"].read_bytes())
            self.assertNotEqual(self.archive, arguments["android_runtime_archive"])
        else:
            self.assertNotIn("android_runtime_archive", arguments)
        arguments["destination"].mkdir()
        (arguments["destination"] / "gradle.log").write_bytes(b"")
        (arguments["destination"] / "execution.json").write_bytes(b"{}\n")
        return {"stage": self.binary["stage"], "diagnostics": arguments["destination"],
                "outputInventory": workflow._inventory(self.binary["stage"])}

    def invoke(self, **changes):
        arguments = dict(component=self.component, expected_build_key=self.ready["buildKey"],
                         repository_root=self.root, environ={}, trusted_workflow_sha="e" * 40)
        if self.component == "sdk-android":
            arguments["android_runtime_archive"] = self.archive
        return workflow.execute(self.plan, self.discovery, self.discovery, self.destination,
                                **{**arguments, **changes})

    def test_core_retains_exact_originals_and_finalizes_after_full_gates(self):
        def checked(stage, manifest):
            self.finalize.assert_not_called()
            self.assertEqual("sdk-core", manifest["component"])
        self.gate.side_effect = checked
        result = self.invoke()
        self.assertEqual(self.ready["buildKey"], result["receipt"]["buildKey"])
        self.assertEqual(self.binary["receipt"]["outputs"], result["receipt"]["outputs"])
        self.assertEqual(self.plan.read_bytes(), (self.destination / "selection/impact-plan.json").read_bytes())
        context = load_canonical_json_bytes((self.destination / "selection/original-context.json").read_bytes())
        self.assertEqual({"repositoryRoot": self.root.as_posix(),
                          "workerRoot": self.destination.as_posix()}, context)
        locator = load_canonical_json_bytes((self.destination / "selection/original-contract-locator.json").read_bytes())
        self.assertEqual(self.evidence, locator["sourceEvidence"])
        self.assertEqual("0.8.7", locator["contractVersion"])
        self.assertEqual(workflow._inventory(self.destination / locator["handoffRelativePath"]),
                         locator["handoffInventory"])
        self.assertEqual(workflow._inventory(self.destination / locator["metadataStageRelativePath"]),
                         locator["metadataStageInventory"])
        self.assertEqual(sha256_file(self.destination / locator["metadataReceiptRelativePath"]),
                         locator["metadataReceiptSha256"])
        self.assertFalse((self.destination / "shard" / "original-context.json").exists())
        self.assertEqual(b"exact original closure", (self.destination /
            "inputs/contract-input/execution-closure/original.json").read_bytes())
        self.assertEqual(workflow.required_contract_components(self.instance),
                         self.projection.call_args.kwargs["required_components"])
        self.assertEqual({"sdk_original_workflow_sha": "e" * 40}, self.state.call_args.kwargs)
        self.assertIsNone(self.state.call_args.args[-1])
        self.finalize.assert_called_once()

    def test_android_uses_separate_exact_archive_and_android_projection(self):
        self.configure("sdk-android")
        result = self.invoke()
        self.assertEqual("sdk-android", result["receipt"]["component"])
        self.assertEqual(("android",), self.projection.call_args.kwargs["required_components"])
        self.assertEqual(self.archive.read_bytes(), (self.destination / "android-original" / self.archive.name).read_bytes())

    def test_explicit_policies_forward_without_serialization(self):
        tooling, apple = {"test": "tooling"}, {"test": "apple"}
        self.invoke(sdk_validation_tooling=tooling, sdk_apple_validation_policy=apple)
        self.assertIs(tooling, self.state.call_args.args[-1])
        self.assertEqual({"sdk_apple_validation_policy": apple,
                          "sdk_original_workflow_sha": "e" * 40}, self.state.call_args.kwargs)
        self.assertEqual({"impact-plan.json", "phase-plan.json", "producer.json",
                          "original-context.json", "original-contract-locator.json"},
                         {path.name for path in (self.destination / "selection").iterdir()})

    def test_original_invocation_evidence_is_pinned_through_worker_exit(self):
        def mutate(*args, **kwargs):
            result = self.produce(*args, **kwargs)
            (self.destination / "selection/original-context.json").write_bytes(b"changed")
            return result
        self.worker.side_effect = mutate
        with self.assertRaisesRegex(ValueError, "retained evidence changed"):
            self.invoke()
        self.finalize.assert_not_called()

    def test_contract_capture_inventory_cannot_be_self_baselined(self):
        self.capture.side_effect = lambda *args: (*self.capture_contract(*args)[:4], [])
        with self.assertRaisesRegex(ValueError, "retained evidence changed"):
            self.invoke()
        self.worker.assert_not_called()
        self.finalize.assert_not_called()

    def test_metadata_admission_objects_forward_only_to_state_replay(self):
        admissions = {"sdk_facade_metadata_admission": object(), "sdk_android_metadata_admission": object()}
        self.invoke(**admissions)
        self.assertEqual({**admissions, "sdk_original_workflow_sha": "e" * 40}, self.state.call_args.kwargs)
        for name, value in admissions.items():
            self.assertIs(value, self.state.call_args.kwargs[name])
            self.assertNotIn(name, self.worker.call_args.kwargs)
            for path in self.destination.rglob("*"):
                if path.is_file():
                    self.assertNotIn(name.encode(), path.read_bytes(), str(path))

    def test_not_ready_wrong_archive_and_missing_release_authority_fail_before_worker(self):
        for changes in ({"expected_build_key": "sha256:" + "0" * 64},
                        {"android_runtime_archive": self.archive}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.invoke(**changes)
        self.evidence["expectedTrustDomain"] = "development"
        with self.assertRaisesRegex(ValueError, "release Contract"):
            self.invoke()
        self.worker.assert_not_called()
        self.finalize.assert_not_called()

    def test_failed_binary_gate_retains_diagnostics_without_shard(self):
        self.gate.side_effect = ValueError("malformed Maven repository")
        with self.assertRaisesRegex(ValueError, "malformed Maven"):
            self.invoke()
        self.assertTrue((self.destination / "worker/execution.json").is_file())
        self.assertFalse((self.destination / "shard").exists())
        self.finalize.assert_not_called()

    def test_late_original_mutation_prevents_finalization(self):
        self.gate.side_effect = lambda *args: self.plan.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "changed"):
            self.invoke()
        self.finalize.assert_not_called()
        self.assertFalse((self.destination / "shard").exists())

    def test_final_checkout_failure_never_publishes(self):
        self.checkout.side_effect = ValueError("dirty checkout")
        with self.assertRaisesRegex(ValueError, "dirty checkout"):
            self.invoke()
        self.finalize.assert_not_called()
        self.assertFalse((self.destination / "shard").exists())

    def test_cli_canonical_forwarding_omission_and_malformed_policy(self):
        arguments = ["--plan", str(self.plan), "--discovery-root", str(self.discovery),
            "--state-root", str(self.discovery), "--destination", str(self.destination),
            "--repository-root", str(self.root), "--component", "sdk-core", "--expected-build-key", self.ready["buildKey"],
            "--trusted-workflow-sha", "e" * 40]
        policy = self.root / "caller.json"
        write_canonical_json(policy, {"caller": "policy"})
        assert_metadata_cli_context(self, workflow, arguments)
        with patch.object(workflow, "execute") as execute:
            self.assertEqual(0, workflow.main(arguments))
            self.assertEqual("e" * 40, execute.call_args.kwargs["trusted_workflow_sha"])
            self.assertNotIn("sdk_validation_tooling", execute.call_args.kwargs)
            self.assertNotIn("sdk_apple_validation_policy", execute.call_args.kwargs)
            for name in ("sdk_facade_metadata_admission", "sdk_android_metadata_admission"):
                self.assertNotIn(name, execute.call_args.kwargs)
            for name in ("sdk_facade_metadata_admission", "sdk_android_metadata_admission"):
                execute.reset_mock()
                with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    workflow.main(arguments + ["--" + name.replace("_", "-"), "transport.json"])
                execute.assert_not_called()
            self.assertEqual(0, workflow.main(arguments + ["--sdk-validation-tooling", str(policy),
                                                           "--sdk-apple-validation-policy", str(policy)]))
            self.assertEqual({"caller": "policy"}, execute.call_args.kwargs["sdk_validation_tooling"])
            self.assertEqual({"caller": "policy"}, execute.call_args.kwargs["sdk_apple_validation_policy"])
            execute.reset_mock()
            policy.write_bytes(b'{"caller":"policy"}')
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                workflow.main(arguments + ["--sdk-validation-tooling", str(policy)])
            execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
