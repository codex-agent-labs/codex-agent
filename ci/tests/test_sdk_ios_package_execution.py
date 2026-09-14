"""Controller-order tests; authority, Apple tooling and host execution are mocked."""

from contextlib import contextmanager, ExitStack
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci import sdk_ios_package_workflow as workflow
from ci.tests.product_chain_support import write_receipt
from products.inventory import (
    canonical_json_bytes, regular_file_inventory, write_canonical_json,
)
from products.receipt import write_output_manifest


class SdkIosPackageExecutionTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sdk-ios-package-controller-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.discovery, self.state = self.root / "discovery", self.root / "state"
        self.discovery.mkdir(); self.state.mkdir()
        self.plan = self.root / "plan.json"
        self.plan.write_bytes(b'{"synthetic":"verified plan boundary"}\n')
        self.destination = self.root / "build/package"
        self.producer = {
            "repository": "owner/repository",
            "workflowPath": ".github/workflows/product-validation.yml",
            "commit": "a" * 40, "tree": "b" * 40, "event": "pull_request",
            "runId": 7, "runAttempt": 2, "pullRequest": 3,
        }
        self.ready = {"schemaVersion": 1, "product": "sdk", "component": "sdk-ios",
                      "phase": "package", "target": "ios",
                      "buildKey": "sha256:" + "c" * 64, "inputs": {}}
        self.expected_key = self.ready["buildKey"]
        self.sdk_directory = self.root / "verified-sdk"
        self.sdk_directory.mkdir()
        (self.sdk_directory / "sdk-compatibility-request.json").write_bytes(b"request\n")
        (self.sdk_directory / "sdk-compatibility.json").write_bytes(b"compatibility\n")
        self.arguments = {}
        for name in ("contract_payload", "contract_metadata_receipt", "contract_attestation",
                     "contract_attestation_signature", "contract_public_key"):
            path = self.root / f"verified-sdk/{name}"
            path.write_bytes(f"synthetic {name}\n".encode())
            self.arguments[name] = path
        self.arguments.update({
            "required_trust_domain": "release", "contract_keyring": self.root / "keyring.json",
            "contract_keys_directory": self.root / "keys",
        })
        self.arguments["contract_keyring"].write_bytes(b"policy\n")
        self.arguments["contract_keys_directory"].mkdir()
        self.sdk_inputs = {
            "selection": {"consumers": [{"product": "sdk", "component": "sdk-ios",
                                           "phase": "package", "target": "ios"}],
                          "sdkVersion": "0.8.0"},
            "sdk": {"directory": self.sdk_directory, "arguments": self.arguments},
        }
        self.expected_proof = self.root / "expected-proof.json"
        self.expected_proof.write_bytes(b"expected proof\n")
        self.native = self.root / "native"
        self.native.mkdir(); (self.native / "proof.json").write_bytes(b"native\n")
        self.tooling = self.root / "tooling"
        self.tooling.mkdir(); (self.tooling / "receipt.json").write_bytes(b"tooling\n")
        self.tooling_key = self.root / "tooling.pub"; self.tooling_key.write_bytes(b"public\n")
        self.java = self.root / "java"; self.java.write_bytes(b"java\n")
        self.events = []
        self.context_failure = None
        self.gate_failure = False
        self.native_producer = self.producer
        self.finalized = None

    @contextmanager
    def verified_inputs(self, *args, **kwargs):
        self.assertEqual(self.tooling_policy, kwargs["sdk_validation_tooling"])
        self.events.append("sdk-enter")
        try:
            yield self.sdk_inputs
            self.events.append("sdk-exit")
            if self.context_failure == "sdk":
                (self.result["stage"] / "changed-after-gate").write_bytes(b"changed\n")
            elif self.context_failure == "sdk-prepared":
                (self.destination / "inputs/changed-after-gate").write_bytes(b"changed\n")
            elif self.context_failure == "sdk-apple":
                (self.destination / "apple-source/changed-after-gate").write_bytes(b"changed\n")
        finally:
            self.events.append("sdk-closed")

    def materialize(self, *args, **kwargs):
        self.assertEqual(self.tooling_policy, kwargs["sdk_validation_tooling"])
        self.events.append("materialize")
        prepared = args[4]
        prepared.mkdir(parents=True)
        write_canonical_json(prepared / "producer.json", self.producer)
        records = (
            ("contract", "contract", "binary", "common", "0.2.0"),
            ("contract", "contract", "metadata", "common", "0.2.0"),
            ("sdk", "sdk-ios", "binary", "ios", "0.8.0"),
        )
        for product, component, phase, target, version in records:
            directory = prepared / "-".join((product, component, phase, target))
            output = directory / "stage/outputs/artifact.bin"
            output.parent.mkdir(parents=True)
            output.write_bytes(f"{product}/{component}/{phase}/{target}\n".encode())
            manifest = write_output_manifest(
                directory / "stage", product, component, phase, target, version,
                {"contract-bundle" if phase == "metadata" else "fixture": "outputs"},
            )
            receipt = directory / "phase-receipt.json"
            write_receipt(
                receipt, product=product, component=component, phase=phase, target=target,
                version=version, version_identity=version, outputs=manifest["outputs"],
                upstream=[], context={"producer": self.producer},
            )
            if phase == "metadata":
                self.arguments["contract_metadata_receipt"].write_bytes(receipt.read_bytes())
        return self.ready

    def capture_apple(self, plan, destination, **arguments):
        self.events.append("apple-source")
        self.assertEqual("development", arguments["required_trust_domain"])
        self.assertEqual(self.expected_proof, arguments["expected_distribution_proof"])
        self.assertEqual(
            self.sdk_directory / "sdk-compatibility.json",
            arguments["expected_sdk_compatibility"],
        )
        distribution = destination / workflow._DISTRIBUTION
        distribution.mkdir(parents=True)
        (distribution / "verified-distribution-proof.json").write_bytes(b"captured original proof\n")
        # A retained source producer may differ; the caller must not relabel it.
        return {"originalProducer": {**self.producer, "commit": "d" * 40, "tree": "e" * 40}}

    @contextmanager
    def native_inputs(self, *args, **kwargs):
        self.events.append("native-enter")
        try:
            yield {"producer": self.native_producer, "directory": self.native}
            self.events.append("native-exit")
            if self.context_failure == "native":
                raise ValueError("synthetic native context rejection")
        finally:
            self.events.append("native-closed")

    def worker(self, ready, **arguments):
        self.events.append("worker")
        self.assertEqual(self.ready, ready)
        self.assertEqual(self.producer, arguments["producer"])
        self.assertEqual(self.destination / "apple-source" / workflow._DISTRIBUTION,
                         arguments["verified_distribution"])
        stage = self.destination / "synthetic-stage"
        validation = self.destination / "synthetic-validation"
        stage.mkdir(); validation.mkdir()
        (stage / "output").write_bytes(b"synthetic package output\n")
        (validation / "proof").write_bytes(b"synthetic validation evidence\n")
        self.result = {"stage": stage, "validationEvidence": validation,
                       "outputInventory": regular_file_inventory(stage),
                       "validationEvidenceInventory": regular_file_inventory(validation)}
        return self.result

    def finalize(self, **arguments):
        self.events.append("finalize")
        candidate = arguments["destination"]
        candidate.mkdir()
        receipt = {"synthetic": "candidate receipt"}
        (candidate / "phase-receipt.json").write_bytes(canonical_json_bytes(receipt))
        (candidate / "phase-object.json").write_bytes(b"synthetic object\n")
        self.finalized = {"receipt": receipt, "synthetic": "verified shard"}
        return self.finalized

    def gate(self, repository, stage, receipt, request, **arguments):
        self.events.append("gate")
        if self.gate_failure:
            raise ValueError("synthetic full package rejection")
        self.assertIn("native-enter", self.events)
        self.assertNotIn("native-exit", self.events)
        apple = arguments["apple_verification"]
        self.assertEqual(self.result["validationEvidence"], apple["validation_evidence_directory"])
        self.assertEqual("development", apple["required_trust_domain"])
        self.assertEqual(self.sdk_directory / "sdk-compatibility.json",
                         apple["expected_sdk_compatibility"])
        raw = receipt.read_bytes()
        return self.finalized["receipt"], raw

    def invoke(self):
        self.tooling_policy = {"evidence": str(self.tooling), "publicKey": str(self.tooling_key),
            "javaExecutable": str(self.java), "requiredTrustDomain": "development",
            "keyring": None, "keysDirectory": None}
        arguments = dict(
            expected_build_key=self.expected_key,
            sdk_inputs_artifact_id=11, sdk_inputs_artifact_sha256="sha256:" + "1" * 64,
            apple_artifact_id=12, apple_artifact_sha256="sha256:" + "2" * 64,
            native_uploads={"synthetic": "caller uploads"}, trusted_workflow_sha="f" * 40,
            keyring=self.arguments["contract_keyring"], keys_directory=self.arguments["contract_keys_directory"],
            expected_distribution_proof=self.expected_proof,
            tooling_evidence=self.tooling, tooling_public_key=self.tooling_key,
            java_executable=self.java, policy_revision="9" * 40, required_trust_domain="development",
            repository_root=self.root, environ={"SAFE": "environment"}, token="token",
        )
        with ExitStack() as stack:
            stack.enter_context(patch.object(workflow.product_reuse, "_product_materialization_paths",
                                             return_value=(self.discovery, self.state, self.destination)))
            stack.enter_context(patch.object(workflow.sdk_workflow, "verified_inputs",
                                             side_effect=self.verified_inputs))
            stack.enter_context(patch.object(workflow.product_reuse, "materialize_product_predecessors",
                                             side_effect=self.materialize))
            stack.enter_context(patch.object(workflow, "verify_contract_component_projection",
                                             return_value=object()))
            stack.enter_context(patch.object(workflow, "capture_sdk_apple_original_ci",
                                             side_effect=self.capture_apple))
            stack.enter_context(patch.object(workflow, "verified_sdk_apple_native_inputs",
                                             side_effect=self.native_inputs))
            stack.enter_context(patch.object(workflow, "execute_package", side_effect=self.worker))
            stack.enter_context(patch.object(workflow.product_reuse, "finalize_phase_object",
                                             side_effect=self.finalize))
            stack.enter_context(patch.object(workflow, "verify_sdk_package_inputs", side_effect=self.gate))
            stack.enter_context(patch.object(workflow, "verify_phase_shard",
                                             side_effect=lambda *_: self.finalized))
            return workflow.execute(self.plan, self.discovery, self.state, self.destination, **arguments)

    def test_full_gate_precedes_context_exit_and_publication(self):
        result = self.invoke()
        self.assertEqual(self.finalized, result)
        self.assertEqual(
            ["sdk-enter", "materialize", "apple-source", "native-enter", "worker", "finalize",
             "gate", "native-exit", "native-closed", "sdk-exit", "sdk-closed"],
            self.events,
        )
        self.assertTrue((self.destination / "shard").is_dir())

    def test_native_original_must_match_elected_producer(self):
        self.native_producer = {**self.producer, "runAttempt": 3}
        with self.assertRaisesRegex(ValueError, "native evidence differs"):
            self.invoke()
        self.assertNotIn("worker", self.events)
        self.assertFalse((self.destination / "shard").exists())

    def test_gate_or_context_exit_failure_never_publishes(self):
        self.gate_failure = True
        with self.assertRaisesRegex(ValueError, "full package rejection"):
            self.invoke()
        self.assertFalse((self.destination / "shard").exists())

        self.destination = self.root / "build/context-rejection"
        self.events.clear(); self.gate_failure = False; self.context_failure = "native"
        with self.assertRaisesRegex(ValueError, "native context rejection"):
            self.invoke()
        self.assertFalse((self.destination / "shard").exists())

    def test_output_mutation_after_outer_exit_rejects_before_publication(self):
        self.context_failure = "sdk"
        with self.assertRaisesRegex(ValueError, "candidate changed after admission"):
            self.invoke()
        self.assertFalse((self.destination / "shard").exists())

    def test_authenticated_input_mutation_on_outer_exit_rejects_before_publication(self):
        for mutation in ("sdk-prepared", "sdk-apple"):
            self.destination = self.root / "build" / mutation
            self.events.clear(); self.context_failure = mutation
            with self.subTest(mutation=mutation), self.assertRaisesRegex(
                    ValueError, "changed after SDK verification"):
                self.invoke()
            self.assertFalse((self.destination / "shard").exists())


if __name__ == "__main__":
    unittest.main()
