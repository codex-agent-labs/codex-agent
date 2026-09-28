"""C# binary orchestration gates; hosted/original trust functions are mocked."""

from contextlib import contextmanager
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ci import sdk_csharp_binary_workflow as workflow
from ci.tests.product_chain_support import write_receipt
from products.inventory import snapshot_regular_tree, write_canonical_json
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


if __name__ == "__main__":
    unittest.main()
