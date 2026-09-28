"""C# binary orchestration gates; hosted/original trust functions are mocked."""

from contextlib import contextmanager
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ci import sdk_csharp_binary_workflow as workflow
from ci.tests.product_chain_support import output, write_receipt
from products.inventory import canonical_json_bytes, snapshot_regular_tree, write_canonical_json
from products.receipt import write_output_manifest
from products.restore import PHASE_PLAN_KEYS


class CSharpBinaryWorkflowTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.plan = self.root / "plan.json"
        self.plan.write_bytes(b"{}\n")
        self.discovery = self.root / "discovery"
        self.state = self.root / "state"
        self.discovery.mkdir()
        self.state.mkdir()
        self.destination = self.root / "build/csharp-binary"
        self.producer = {"repository": "fixture/repository", "commit": "a" * 40,
            "tree": "b" * 40, "event": "pull_request",
            "workflowPath": ".github/workflows/product-validation.yml",
            "runId": 10, "runAttempt": 1, "pullRequest": 2}
        self.records = {}
        for phase in ("binary", "package", "validation", "metadata"):
            stage = self.root / "contract-original" / phase / "stage"
            path = stage / "outputs" / ("codex-agent-contract-0.8.0.zip" if phase == "metadata" else "artifact")
            path.parent.mkdir(parents=True)
            path.write_bytes(phase.encode())
            kind = "contract-bundle" if phase == "metadata" else "fixture"
            manifest = write_output_manifest(stage, "contract", "contract", phase,
                                             "common", "0.8.0", {kind: "outputs"})
            receipt_path = stage.parent / "phase-receipt.json"
            receipt = write_receipt(receipt_path, product="contract", component="contract",
                phase=phase, target="common", version="0.8.0", version_identity="0.8.0",
                outputs=manifest["outputs"], upstream=[], context={"producer": self.producer})
            self.records[phase] = {"stage": stage, "receiptPath": receipt_path, "receipt": receipt}
        elected = write_receipt(self.root / "elected.json", product="sdk", component="csharp",
            phase="binary", target="desktop", version="0.8.0", version_identity="0.8.0",
            outputs=self.records["metadata"]["receipt"]["outputs"], upstream=[],
            context={"producer": self.producer})
        self.ready = {name: elected[name] for name in PHASE_PLAN_KEYS}
        self.sdk = self.root / "sdk-inputs"
        self.sdk.mkdir()
        (self.sdk / "sdk-compatibility-request.json").write_bytes(b"caller-authenticated request")
        (self.sdk / "sdk-compatibility.json").write_bytes(b"caller-authenticated compatibility")
        key_dir = self.root / "gradle/release/keys"
        key_dir.mkdir(parents=True)
        (key_dir / "sdk-runtime-root.pub").write_bytes(b"caller-authenticated root key")
        self.keyring = self.root / "keyring.json"
        self.keyring.write_bytes(b"caller-authenticated keyring")
        self.keys = self.root / "keys"
        self.keys.mkdir()
        self.selection = {"consumers": [dict(workflow._PACKAGE)], "sdkVersion": "0.8.0",
            "contractPayloadSha256": self.records["metadata"]["receipt"]["outputs"][0]["sha256"]}
        self.calls = []

    @contextmanager
    def verified(self, *args, **kwargs):
        self.calls.append("verified-s858")
        try:
            yield {"selection": self.selection, "sdk": {"directory": self.sdk}}
        finally:
            self.calls.append("verified-s858-exit")

    def materialize(self, plan, discovery, state, instance, destination, **kwargs):
        self.assertEqual(workflow._INSTANCE, instance)
        self.assertEqual(self.ready["buildKey"], kwargs["expected_build_key"])
        destination.mkdir(parents=True)
        for phase, record in self.records.items():
            prefix = destination / f"contract-contract-{phase}-common"
            snapshot_regular_tree(record["stage"], prefix / "stage")
            (prefix / "phase-receipt.json").write_bytes(record["receiptPath"].read_bytes())
        write_canonical_json(destination / "phase-plan.json", self.ready)
        write_canonical_json(destination / "producer.json", self.producer)
        return dict(self.ready)

    def policy(self, root, commit, destination):
        self.assertEqual(self.producer["commit"], commit)
        destination.mkdir(parents=True)
        keyring = destination / "keyring.json"
        keyring.write_bytes(b"Git-authoritative policy fixture")
        keys = destination / "keys"
        keys.mkdir()
        return SimpleNamespace(keyring=keyring, keys=keys)

    def capture_contract(self, root, evidence, original, one_output, prepared, trust):
        record = original("contract", "contract", "metadata", "common")
        self.assertEqual(self.records["metadata"]["receipt"], record["receipt"])
        self.assertEqual(self.records["metadata"]["stage"].joinpath(
            "outputs/codex-agent-contract-0.8.0.zip").read_bytes(),
            one_output(record, "contract-bundle").read_bytes())
        handoff = prepared / "contract-input"
        handoff.mkdir()
        for name in ("codex-agent-contract-0.8.0.zip", "codex-agent-contract-0.8.0.attestation.json",
                     "codex-agent-contract-0.8.0.attestation.sig", "public-key.pub"):
            (handoff / name).write_bytes(name.encode())
        return record, "0.8.0", handoff, {}, workflow._inventory(handoff)

    def produce(self, plan, **kwargs):
        self.calls.append("gradle-binary")
        self.assertEqual(self.ready, plan)
        self.assertEqual(self.sdk / "sdk-compatibility-request.json", kwargs["compatibility_request"])
        stage = self.root / "codex-agent-sdk/build/product-stage/sdk/csharp/binary"
        for name in ("CodexAgent.dll", "CodexAgent.pdb", "CodexAgent.xml", "CodexAgent.deps.json",
                     "sdk-compatibility.json", "sdk-runtime-root.pub"):
            path = stage / "outputs/csharp" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((self.sdk / name).read_bytes() if name == "sdk-compatibility.json" else
                             (self.root / "gradle/release/keys" / name).read_bytes()
                             if name == "sdk-runtime-root.pub" else name.encode())
        write_output_manifest(stage, "sdk", "csharp", "binary", "desktop", "0.8.0",
                              {"csharp-binary": "outputs/csharp"})
        return {"stage": stage, "outputInventory": workflow._inventory(stage)}

    def invoke(self):
        with (patch.object(workflow.sdk_workflow, "verified_inputs", side_effect=self.verified),
              patch.object(workflow.product_reuse, "inspect_products",
                           return_value={"readyPlans": [dict(self.ready)]}),
              patch.object(workflow.product_reuse, "materialize_product_predecessors",
                           side_effect=self.materialize),
              patch.object(workflow.product_reuse, "_verified_product_state",
                           return_value=SimpleNamespace(prior_ready_plans={workflow._INSTANCE: dict(self.ready)},
                               producer=self.producer, rebased_request={
                               "contractEvidence": {"expectedTrustDomain": "release"}})),
              patch.object(workflow.product_reuse, "_release_trust", side_effect=self.policy),
              patch.object(workflow.product_reuse, "_capture_runtime_contract",
                           side_effect=self.capture_contract),
              patch.object(workflow, "verify_contract_component_projection"),
              patch.object(workflow, "execute_binary", side_effect=self.produce)):
            return workflow.execute(self.plan, self.discovery, self.state, self.destination,
                expected_build_key=self.ready["buildKey"], sdk_inputs_artifact_id=10,
                sdk_inputs_artifact_sha256="sha256:" + "c" * 64,
                trusted_workflow_sha="sha256:" + "d" * 64,
                keyring=self.keyring, keys_directory=self.keys,
                repository_root=self.root, environ={}, token="fixture-token")

    def test_binary_requires_selected_s858_and_publishes_after_exit(self):
        result = self.invoke()
        self.assertEqual(["verified-s858", "gradle-binary", "verified-s858-exit"], self.calls)
        self.assertEqual("csharp", result["receipt"]["component"])
        self.assertTrue((self.destination / "shard/phase-receipt.json").is_file())

    def test_unselected_csharp_package_rejected_before_binary(self):
        self.selection["consumers"] = []
        with self.assertRaisesRegex(ValueError, "selected C# package"):
            self.invoke()
        self.assertEqual(["verified-s858", "verified-s858-exit"], self.calls)

    def test_lookup_only_plan_current_and_released_default_have_same_real_key(self):
        dependencies = workflow.phase_instance_dependencies(workflow._INSTANCE)
        receipts = {instance: write_receipt(self.root / f"lookup-{index}.json",
            product=instance.product, component=instance.component, phase=instance.phase,
            target=instance.target, version="0.8.0", version_identity="0.8.0",
            outputs=[output("fixture", "outputs/value", str(index).encode())], upstream=[],
            context={"producer": self.producer}) for index, instance in enumerate(dependencies)}
        records = {instance: {"buildKey": "sha256:" + "1" * 64,
            "receiptSha256": "sha256:" + "2" * 64,
            "objectSha256": "sha256:" + "3" * 64} for instance in dependencies}
        projection = {"schemaVersion": 1, "receiptSha256": "sha256:" + "7" * 64,
            "bundlePath": "outputs/codex-agent-contract-0.8.0.zip",
            "bundleSha256": "sha256:" + "8" * 64,
            "manifestSha256": "sha256:" + "9" * 64,
            "contractVersion": "0.8.0", "contractDigest": "sha256:" + "a" * 64,
            "componentDigests": [{"component": "common", "sha256": "sha256:" + "b" * 64}]}
        keys = []
        for external in (False, True):
            versions = {name: "0.8.0" for name in
                ("contract", "runtime-release", "runtime-compatibility", "sdk")}
            if external:
                versions["runtime-release"] = "0.8.1"  # SDK still embeds the authenticated 0.8.0 default.
            sources = {instance: self.root / str(index) for index, instance in enumerate(dependencies)
                       if not external or instance.product == "contract"}
            verified = SimpleNamespace(closure=tuple(sources),
                plan={"validationCommit": "a" * 40},
                rebased_request={"contractEvidence": {"expectedTrustDomain": "release"},
                    **({"sdkRuntimeSource": "released-default"} if external else {})},
                sources=sources, prior_by_instance=records)
            by_path = {path: receipts[instance] for instance, path in sources.items()}

            def original_state(*_args, **kwargs):
                self.assertNotEqual(_args[1], _args[2])  # Advanced wave, not discovery-only replay.
                if external:
                    kwargs["sdk_runtime_consumer"]({"handoff": {"receiptBytes": {
                        identity: canonical_json_bytes(receipt) for identity, receipt in receipts.items()
                        if identity.product == "runtime"}}})
                return verified

            with (patch.object(workflow.product_reuse, "_verified_product_state", side_effect=original_state),
              patch.object(workflow.product_reuse, "_versions", return_value=versions),
              patch.object(workflow, "_contract_projection_from_request_components", return_value="signed-common"),
              patch("products.plan._contract_projection_value", return_value=projection),
              patch("products.reuse.verified_phase_toolchain_digest", side_effect=lambda _r, _v, _i, value: value),
              patch("products.reuse.verified_phase_flags_digest", side_effect=lambda _r, _v, _i, value: value),
              patch.object(workflow.product_reuse, "verify_object",
                           side_effect=lambda path, **_kwargs: {"receipt": by_path[path]}),
              patch.object(workflow.product_reuse, "_authorities", return_value=([{
                  "toolchainProfileDigest": "sha256:" + "4" * 64,
                  "flagsDigest": "sha256:" + "5" * 64,
                  "outputSchemaVersion": 1}], None)),
              patch.object(workflow, "phase_git_inventory", return_value=[{
                  "relativePath": "tracked/input", "bytes": 1, "sha256": "sha256:" + "6" * 64}])):
                result = workflow.lookup_only_plan(self.plan, self.discovery, self.state,
                    repository_root=self.root, environ={})
            keys.append(result["buildKey"])
        self.assertEqual(keys[0], keys[1])
        self.assertTrue(keys[0].startswith("sha256:"))

    def test_lookup_only_plan_refuses_missing_original(self):
        verified = SimpleNamespace(closure=(), sources={}, prior_by_instance={},
            rebased_request={"sdkRuntimeSource": "released-default"})
        with (patch.object(workflow.product_reuse, "_verified_product_state", return_value=verified),
              patch.object(workflow, "_plan") as planner):
            with self.assertRaisesRegex(ValueError, "authenticated original predecessor"):
                workflow.lookup_only_plan(self.plan, self.discovery, self.state,
                    repository_root=self.root, environ={})
        planner.assert_not_called()

    def test_lookup_only_same_pr_capture_verifies_stage_and_expires(self):
        stage = self.produce(self.ready,
            compatibility_request=self.sdk / "sdk-compatibility-request.json")["stage"]
        manifest = workflow.verify_output_manifest_identity(stage, "sdk", "csharp", "binary",
            "desktop", "0.8.0")
        original_producer = {**self.producer, "commit": "d" * 40, "tree": "e" * 40,
            "runId": 20, "runAttempt": 2}
        receipt = write_receipt(self.root / "original-csharp-receipt.json", product="sdk",
            component="csharp", phase="binary", target="desktop", version="0.8.0",
            version_identity="0.8.0", outputs=manifest["outputs"], upstream=[],
            context={"producer": original_producer})

        class Session:
            def capture(self, source, plan, destination):
                self_source.assertEqual("same-pr", source)
                self_source.assertEqual(receipt["buildKey"], plan["buildKey"])
                snapshot_regular_tree(stage, destination)
                return SimpleNamespace(envelope={"receipt": receipt,
                    "receiptBytes": canonical_json_bytes(receipt)},
                    transport_source={"kind": "same-pr"})

        self_source = self
        session = Session()
        mutate_controls = {"plan": False}

        def replay(*_args, authenticated_lookup_consumer, **_kwargs):
            authenticated_lookup_consumer(session)
            if mutate_controls["plan"]:
                self.plan.write_bytes(b"mutated\n")
            return SimpleNamespace(producer=self.producer,
                plan={"validationCommit": self.producer["commit"]})

        with (patch.object(workflow, "lookup_only_plan", return_value={"buildKey": receipt["buildKey"]}),
              patch.object(workflow.sdk_workflow, "verified_inputs", side_effect=self.verified),
              patch.object(workflow.product_reuse, "_verified_product_state", side_effect=replay),
              patch.object(workflow, "git_regular_blob_bytes",
                           return_value=(self.root / "gradle/release/keys/sdk-runtime-root.pub").read_bytes())):
            with workflow.verified_lookup_only_same_pr_original(self.plan, self.discovery, self.state,
                    sdk_inputs_artifact_id=10, sdk_inputs_artifact_sha256="sha256:" + "c" * 64,
                    trusted_workflow_sha="sha256:" + "d" * 64, keyring=self.keyring,
                    keys_directory=self.keys, repository_root=self.root,
                    environ={}, token="fixture-token") as original:
                captured_stage = original["stage"]
                self.assertTrue((captured_stage / "outputs/csharp/CodexAgent.dll").is_file())
                self.assertEqual("same-pr", original["transportSource"]["kind"])
            mutate_controls["plan"] = True
            with self.assertRaisesRegex(ValueError, "controls changed"):
                with workflow.verified_lookup_only_same_pr_original(self.plan, self.discovery, self.state,
                        sdk_inputs_artifact_id=10, sdk_inputs_artifact_sha256="sha256:" + "c" * 64,
                        trusted_workflow_sha="sha256:" + "d" * 64, keyring=self.keyring,
                        keys_directory=self.keys, repository_root=self.root,
                        environ={}, token="fixture-token"):
                    self.fail("Changed plan was accepted")
            self.plan.write_bytes(b"{}\n")
            mutate_controls["plan"] = False
            (stage / "outputs/csharp/sdk-compatibility.json").write_bytes(b"tampered")
            with self.assertRaises(ValueError):
                with workflow.verified_lookup_only_same_pr_original(self.plan, self.discovery, self.state,
                        sdk_inputs_artifact_id=10, sdk_inputs_artifact_sha256="sha256:" + "c" * 64,
                        trusted_workflow_sha="sha256:" + "d" * 64, keyring=self.keyring,
                        keys_directory=self.keys, repository_root=self.root,
                        environ={}, token="fixture-token"):
                    self.fail("Tampered C# stage was accepted")
        self.assertFalse(captured_stage.exists())

    def test_lookup_only_same_pr_rejects_missing_original(self):
        class Session:
            def capture(self, _source, _plan, _destination):
                return SimpleNamespace(envelope=None, transport_source=None)

        def replay(*_args, authenticated_lookup_consumer, **_kwargs):
            authenticated_lookup_consumer(Session())

        with (patch.object(workflow, "lookup_only_plan", return_value={"buildKey": "sha256:" + "a" * 64}),
              patch.object(workflow.sdk_workflow, "verified_inputs", side_effect=self.verified),
              patch.object(workflow.product_reuse, "_verified_product_state", side_effect=replay),
              self.assertRaisesRegex(ValueError, "same-PR C# binary original is unavailable")):
            with workflow.verified_lookup_only_same_pr_original(self.plan, self.discovery, self.state,
                    sdk_inputs_artifact_id=10, sdk_inputs_artifact_sha256="sha256:" + "c" * 64,
                    trusted_workflow_sha="sha256:" + "d" * 64, keyring=self.keyring,
                    keys_directory=self.keys, repository_root=self.root,
                    environ={}, token="fixture-token"):
                self.fail("Missing C# original was accepted")


if __name__ == "__main__":
    unittest.main()
