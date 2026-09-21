"""Android validation controller orchestration; transport and full gates are mocked."""

from copy import deepcopy
from contextlib import redirect_stderr
import base64
import io
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from ci import sdk_android_validation_workflow as workflow
from ci.products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, public_key_fingerprint,
    regular_file_inventory, sha256_file, write_canonical_json,
)
from ci.products.receipt import write_output_manifest
from ci.tests.product_chain_support import write_receipt


class AndroidValidationWorkflowTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="android-validation-workflow-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.discovery = self.root / "discovery"
        self.state = self.root / "state"
        self.discovery.mkdir()
        self.state.mkdir()
        (self.discovery / "catalog.json").write_bytes(b"discovery")
        (self.state / "state.json").write_bytes(b"state")
        self.destination = self.root / "build/worker"
        self.plan = self.root / "impact-plan.json"
        self.plan.write_bytes(b"synthetic elected plan\n")
        self.current = self.producer(2)
        self.original = self.producer(1)
        self.ready = {"schemaVersion": 1, "product": "sdk", "component": "sdk-android",
                      "phase": "validation", "target": "android",
                      "buildKey": "sha256:" + "f" * 64, "inputs": {}}
        self.version = "0.8.7"
        self.package_stage = self.root / "caller/package"
        self.binary_stage = self.root / "caller/binary"
        for stage, phase, raw in ((self.package_stage, "package", b"package"),
                                  (self.binary_stage, "binary", b"binary aar")):
            payload = stage / "outputs/payload.bin"
            payload.parent.mkdir(parents=True)
            payload.write_bytes(raw)
            write_output_manifest(stage, "sdk", "sdk-android", phase, "android", self.version,
                                  {"maven": "outputs"})
        self.package_receipt = self.root / "caller/package.json"
        self.binary_receipt = self.root / "caller/binary.json"
        self.package = self.receipt(self.package_stage, self.package_receipt, "package", self.original)
        self.binary = self.receipt(self.binary_stage, self.binary_receipt, "binary", self.original)
        self.selected_package = self.root / "selected/package"
        self.selected_binary = self.root / "selected/binary"
        shutil.copytree(self.package_stage, self.selected_package)
        shutil.copytree(self.binary_stage, self.selected_binary)
        self.selected_package_bytes = self.package_receipt.read_bytes()
        self.selected_binary_bytes = self.binary_receipt.read_bytes()
        self.compatibility = self.root / "caller/sdk-compatibility.json"
        self.compatibility.write_bytes(b"synthetic compatibility\n")
        self.contract_stage = self.root / "caller/contract-stage"
        self.contract_stage.mkdir(parents=True)
        (self.contract_stage / "contract.bin").write_bytes(b"contract")
        self.contract = self.root / "caller/contract"
        self.contract.mkdir()
        paths = {}
        for name in ("receipt.json", "attestation.json", "signature.sig", "public.pub"):
            paths[name] = self.contract / name
            paths[name].write_bytes(name.encode())
        same_name_signature = self.contract / "signature/attestation.json"
        same_name_signature.parent.mkdir()
        same_name_signature.write_bytes(paths["signature.sig"].read_bytes())
        paths["signature.sig"] = same_name_signature
        closure = self.contract / workflow.validation_phase.CONTRACT_EXECUTION_CLOSURE_DIRECTORY
        closure.mkdir()
        (closure / "closure.json").write_bytes(b"closure")
        self.contract_evidence = {
            "stageRoot": str(self.contract_stage), "phaseReceipt": str(paths["receipt.json"]),
            "attestation": str(paths["attestation.json"]),
            "attestationSignature": str(paths["signature.sig"]),
            "publicKey": str(paths["public.pub"]), "expectedTrustDomain": "development",
            "keyring": None, "keysDirectory": None,
        }
        self.tooling = self.root / "caller/tooling"
        self.tooling.mkdir()
        (self.tooling / "attestation.json").write_bytes(b"tooling")
        self.public_key = self.root / "caller/tooling.pub"
        self.java = self.root / "caller/java"
        self.analyzer = self.root / "caller/apkanalyzer"
        for path, raw in ((self.public_key, b"key"), (self.java, b"java"),
                          (self.analyzer, b"analyzer")):
            path.write_bytes(raw)
        self.apple_keys = self.root / "caller/apple-keys"
        self.apple_keys.mkdir()
        self.apple_keyring = self.root / "caller/apple-keyring.json"
        self.apple_keyring.write_bytes(b"caller apple keyring")
        self.apple_policy = {
            "plan": str(self.plan), "attestationPublicKey": str(paths["public.pub"]),
            "attestationTrustDomain": "development", "keyring": str(self.apple_keyring),
            "keysDirectory": str(self.apple_keys), "toolingEvidence": str(self.tooling),
            "toolingPublicKey": str(self.public_key), "javaExecutable": str(self.java),
            "toolingTrustDomain": "development", "toolingKeyring": None,
            "toolingKeysDirectory": None,
        }
        self.environment = {"GITHUB_RUN_ID": "17", "GITHUB_RUN_ATTEMPT": "2"}
        self.events = []
        self.phase_arguments = None
        self.arguments = dict(
            expected_build_key=self.ready["buildKey"], package_stage=self.package_stage,
            package_receipt=self.package_receipt, binary_stage=self.binary_stage,
            binary_receipt=self.binary_receipt, compatibility_request=self.compatibility,
            binary_contract_evidence=self.contract_evidence,
            trusted_workflow_sha="c" * 40, trusted_android_workflow_sha="d" * 40,
            trusted_source_commit="e" * 40, trusted_source_tree="1" * 40,
            tooling_evidence=self.tooling, tooling_public_key=self.public_key,
            java_executable=self.java, apkanalyzer_executable=self.analyzer,
            policy_revision="2" * 40, required_trust_domain="development",
            repository_root=self.root, environ=self.environment, token="synthetic-token",
            sdk_apple_validation_policy=self.apple_policy,
        )

    def producer(self, attempt, *, commit="a" * 40):
        return {"repository": "codex-agent-labs/codex-agent",
                "workflowPath": ".github/workflows/ci.yml", "commit": commit,
                "tree": "b" * 40, "event": "pull_request", "runId": 17,
                "runAttempt": attempt, "pullRequest": 3}

    def receipt(self, stage, path, phase, producer):
        manifest = workflow.product_reuse.verify_output_manifest_identity(
            stage, "sdk", "sdk-android", phase, "android", self.version)
        return write_receipt(path, product="sdk", component="sdk-android", phase=phase,
            target="android", version=self.version, version_identity=self.version,
            outputs=manifest["outputs"], upstream=[], context={"producer": producer})

    def materialize(self, plan, discovery, state, instance, destination, **kwargs):
        self.events.append("materialize")
        self.assertEqual(workflow._INSTANCE, instance)
        self.assertEqual(self.ready["buildKey"], kwargs["expected_build_key"])
        self.assertIs(self.apple_policy, kwargs["sdk_apple_validation_policy"])
        destination.mkdir(parents=True)
        for phase, source, raw in (("package", self.selected_package, self.selected_package_bytes),
                                   ("binary", self.selected_binary, self.selected_binary_bytes)):
            selected = destination / f"sdk-sdk-android-{phase}-android"
            shutil.copytree(source, selected / "stage")
            (selected / "phase-receipt.json").write_bytes(raw)
        write_canonical_json(destination / "phase-plan.json", self.ready)
        write_canonical_json(destination / "producer.json", self.current)
        return deepcopy(self.ready)

    def stage_inputs(self, request, destination, **kwargs):
        self.events.append("retain-sdk-inputs")
        self.assertEqual(self.compatibility.parent, kwargs["request_directory"])
        destination.mkdir(parents=True)
        (destination / "sdk-compatibility-request.json").write_bytes(Path(request).read_bytes())
        (destination / "sdk-compatibility.json").write_bytes(b"retained compatibility")
        (destination / "sdk-inputs-inventory.json").write_bytes(b"retained inventory")
        return {"inventorySha256": "sha256:" + "0" * 64, "inventory": {}}

    def capture_final(self, plan, root, destination, **kwargs):
        self.events.append("final-capture")
        self.assertNotIn(self.root, destination.parents)
        destination.mkdir()
        (destination / "final.bin").write_bytes(b"exact final capture")
        return {"captureProducer": deepcopy(self.current)}

    def capture_protected(self, plan, root, final, destination, **kwargs):
        self.events.append("protected-capture")
        self.assertTrue((final / "final.bin").is_file())
        self.assertNotIn(self.root, destination.parents)
        destination.mkdir()
        (destination / "protected.bin").write_bytes(b"exact protected capture")
        return {"captureProducer": deepcopy(self.current)}

    def produce(self, **kwargs):
        self.events.append("produce")
        self.phase_arguments = kwargs
        self.assertEqual(self.original, kwargs["expected_original_producer"])
        self.assertEqual(self.current, kwargs["expected_capture_producer"])
        self.assertEqual(b"exact final capture", (kwargs["final_capture"] / "final.bin").read_bytes())
        self.assertEqual(b"exact protected capture", (kwargs["protected_capture"] / "protected.bin").read_bytes())
        stage = kwargs["destination"]
        output = stage / workflow.validation_phase.OUTPUT_PATH
        output.parent.mkdir(parents=True)
        output.write_bytes(b"canonical content fixture")
        return write_output_manifest(stage, "sdk", "sdk-android", "validation", "android", self.version,
            {workflow.validation_phase.OUTPUT_KIND: "outputs/validation"},
            expected_output_paths=[workflow.validation_phase.OUTPUT_PATH])

    def finalize(self, **kwargs):
        self.events.append("finalize")
        destination = kwargs["destination"]
        destination.mkdir()
        (destination / "shard.json").write_bytes(b"finalized")
        return {"receipt": {"buildKey": self.ready["buildKey"]}}

    def call(self, *, final_capture=None, phase=None, **changes):
        with patch.object(workflow, "_request_inventory",
                          side_effect=lambda path: {Path(path): sha256_file(Path(path))}), \
                patch.object(workflow.product_reuse, "materialize_product_predecessors",
                             side_effect=self.materialize), \
                patch.object(workflow, "capture_android_evidence",
                             side_effect=self.capture_final if final_capture is None else final_capture), \
                patch.object(workflow, "capture_android_firebase_evidence", side_effect=self.capture_protected), \
                patch.object(workflow, "stage_sdk_inputs", side_effect=self.stage_inputs), \
                patch.object(workflow.validation_phase, "produce_sdk_android_validation_phase",
                             side_effect=self.produce if phase is None else phase), \
                patch.object(workflow.product_reuse, "_runtime_worker_checkout"), \
                patch.object(workflow.product_reuse, "verify_phase_shard",
                             side_effect=lambda *args: {"receipt": {"buildKey": self.ready["buildKey"]}}), \
                patch.object(workflow.product_reuse, "finalize_phase_object",
                             side_effect=self.finalize) as finalize:
            result = workflow.execute(self.plan, self.discovery, self.state,
                changes.pop("destination", self.destination), **{**self.arguments, **changes})
        return result, finalize

    def test_exact_election_private_capture_retention_full_gate_then_finalization(self):
        result, finalize = self.call()
        self.assertEqual(["materialize", "final-capture", "protected-capture", "retain-sdk-inputs",
                          "produce", "finalize"], self.events)
        finalize.assert_called_once()
        self.assertEqual(self.destination / "stage", result["stage"])
        self.assertEqual(b"exact final capture",
                         (result["originals"] / "final/final.bin").read_bytes())
        self.assertEqual(b"exact protected capture",
                         (result["originals"] / "protected/protected.bin").read_bytes())
        self.assertEqual(self.current, self.phase_arguments["expected_capture_producer"])
        self.assertEqual(self.original, self.phase_arguments["expected_original_producer"])
        self.assertNotEqual(self.current["runAttempt"], self.original["runAttempt"])
        retained = result["originals"] / "validation-inputs"
        self.assertEqual(b"synthetic compatibility\n",
                         (retained / "original-compatibility-request.json").read_bytes())
        self.assertTrue((retained / "sdk-inputs/sdk-compatibility-request.json").is_file())
        invocation = load_canonical_json_bytes(
            (retained / "binary-contract-invocation.json").read_bytes())
        trees, files = workflow.validation_phase._contract_sources(invocation)
        self.assertEqual(regular_file_inventory(self.contract_stage),
                         regular_file_inventory(trees["contract/stage"]))
        self.assertEqual(regular_file_inventory(
            self.contract / workflow.validation_phase.CONTRACT_EXECUTION_CLOSURE_DIRECTORY),
            regular_file_inventory(trees["contract/closure"]))
        self.assertTrue(all(path.exists() for path in files.values()))
        _, original_files = workflow.validation_phase._contract_sources(self.contract_evidence)
        self.assertTrue(all(files[name].read_bytes() == original_files[name].read_bytes()
                            for name in files))

    def test_candidate_identity_mismatch_or_selected_original_mismatch_rejects_before_capture(self):
        changed = self.producer(1, commit="9" * 40)
        self.binary = self.receipt(self.binary_stage, self.binary_receipt, "binary", changed)
        self.selected_binary_bytes = self.binary_receipt.read_bytes()
        with self.assertRaisesRegex(ValueError, "different candidate identities"):
            self.call()
        self.assertNotIn("final-capture", self.events)

        # A caller cannot substitute different bytes for the elected binary stage.
        self.events.clear()
        self.binary = self.receipt(self.binary_stage, self.binary_receipt, "binary", self.original)
        self.selected_binary_bytes = self.binary_receipt.read_bytes()
        self.binary_stage.joinpath("outputs/payload.bin").write_bytes(b"substituted")
        with self.assertRaisesRegex(ValueError, "differs from its elected"):
            self.call(destination=self.root / "build/second")
        self.assertNotIn("final-capture", self.events)

    def test_capture_or_full_gate_failure_never_finalizes(self):
        for name, changes in (("capture", {"final_capture": ValueError("capture failed")}),
                              ("producer", {"phase": ValueError("producer failed")})):
            self.events.clear()
            destination = self.root / f"build/{name}"
            with self.assertRaisesRegex(ValueError, name + " failed"):
                self.call(destination=destination, **changes)
            self.assertNotIn("finalize", self.events)
            self.assertFalse((destination / "shard").exists())

    def test_output_must_be_disjoint_from_explicit_contract_sources(self):
        with self.assertRaisesRegex(ValueError, "overlap"):
            self.call(destination=self.contract_stage / "output")
        self.assertNotIn("materialize", self.events)

    def test_retention_copies_only_keyring_declared_public_keys(self):
        algorithm = b"ssh-ed25519"
        blob = len(algorithm).to_bytes(4, "big") + algorithm + (32).to_bytes(4, "big") + bytes(32)
        public = b"ssh-ed25519 " + base64.b64encode(blob) + b"\n"
        keys = self.root / "caller/contract-keys"
        keys.mkdir()
        (keys / "current.pub").write_bytes(public)
        (keys / "private-marker").write_bytes(b"must not be retained")
        keyring = self.root / "caller/contract-keyring.json"
        write_canonical_json(keyring, {"schemaVersion": 1, "namespace": "codex-agent-product-v1",
            "algorithm": "ssh-ed25519", "trustDomain": "release",
            "activeKey": {"keyId": "current", "fingerprint": public_key_fingerprint(public)},
            "retiredKeys": []})
        evidence = {**self.contract_evidence, "keyring": str(keyring), "keysDirectory": str(keys)}
        destination = self.root / "retained-public-only"
        with patch.object(workflow, "stage_sdk_inputs", side_effect=self.stage_inputs):
            workflow._retain_original_inputs(self.compatibility, evidence, destination)
        retained = destination / "contract/trust/keys"
        self.assertEqual(["current.pub"], [row["relativePath"] for row in regular_file_inventory(retained)])

    def test_late_plan_capture_or_retained_mutation_rejects_before_finalization(self):
        original_plan = self.plan.read_bytes()
        original_state = (self.state / "state.json").read_bytes()
        original_policy = self.apple_keyring.read_bytes()
        original_request = self.compatibility.read_bytes()
        mutations = {
            "plan": (lambda kwargs: self.plan.write_bytes(b"changed plan"),
                     lambda: self.plan.write_bytes(original_plan)),
            "discovery": (lambda kwargs: (self.discovery / "late").write_bytes(b"late"),
                          lambda: (self.discovery / "late").unlink()),
            "state": (lambda kwargs: (self.state / "state.json").write_bytes(b"changed"),
                      lambda: (self.state / "state.json").write_bytes(original_state)),
            "apple-policy": (lambda kwargs: self.apple_keyring.write_bytes(b"changed"),
                             lambda: self.apple_keyring.write_bytes(original_policy)),
            "compatibility-request": (lambda kwargs: self.compatibility.write_bytes(b"changed"),
                                      lambda: self.compatibility.write_bytes(original_request)),
            "private": (lambda kwargs: (kwargs["final_capture"] / "final.bin").write_bytes(b"changed"),
                        lambda: None),
            "retained": (lambda kwargs: (kwargs["destination"].parent / "originals/final/final.bin").write_bytes(b"changed"),
                         lambda: None),
            "retained-input": (lambda kwargs: (kwargs["destination"].parent /
                               "originals/validation-inputs/original-compatibility-request.json").write_bytes(b"changed"),
                               lambda: None),
        }
        for name, (mutate, restore) in mutations.items():
            self.events.clear()
            destination = self.root / f"build/mutated-{name}"
            def producer(**kwargs):
                result = self.produce(**kwargs)
                mutate(kwargs)
                return result
            with patch.object(workflow, "_request_inventory",
                              side_effect=lambda path: {Path(path): sha256_file(Path(path))}), \
                    patch.object(workflow.product_reuse, "materialize_product_predecessors",
                                 side_effect=self.materialize), \
                    patch.object(workflow, "capture_android_evidence", side_effect=self.capture_final), \
                    patch.object(workflow, "capture_android_firebase_evidence", side_effect=self.capture_protected), \
                    patch.object(workflow, "stage_sdk_inputs", side_effect=self.stage_inputs), \
                    patch.object(workflow.validation_phase, "produce_sdk_android_validation_phase",
                                 side_effect=producer), \
                    patch.object(workflow.product_reuse, "finalize_phase_object") as finalize, \
                    self.assertRaisesRegex(ValueError, "changed"):
                workflow.execute(self.plan, self.discovery, self.state, destination, **self.arguments)
            finalize.assert_not_called()
            restore()

    def test_finalizer_mutation_or_failure_never_publishes_a_shard(self):
        original_finalize = self.finalize
        for failure in (False, True):
            destination = self.root / f"finalizer-{failure}"
            before = self.compatibility.read_bytes()
            def finalize(**kwargs):
                result = original_finalize(**kwargs)
                self.compatibility.write_bytes(b"changed by finalizer")
                if failure:
                    raise ValueError("finalizer failed")
                return result
            try:
                with patch.object(self, "finalize", side_effect=finalize), \
                        self.assertRaisesRegex(ValueError, "changed"):
                    self.call(destination=destination)
                self.assertFalse((destination / "shard").exists())
            finally:
                self.compatibility.write_bytes(before)

    def test_cli_forwards_canonical_contract_policy_and_rejects_partial_keyring(self):
        evidence = self.root / "contract-evidence.json"
        write_canonical_json(evidence, self.contract_evidence)
        apple_policy = self.root / "apple-policy.json"
        write_canonical_json(apple_policy, self.apple_policy)
        argv = []
        paths = {
            "plan": self.plan, "discovery-root": self.discovery, "state-root": self.state,
            "destination": self.destination, "package-stage": self.package_stage,
            "package-receipt": self.package_receipt, "binary-stage": self.binary_stage,
            "binary-receipt": self.binary_receipt, "compatibility-request": self.compatibility,
            "binary-contract-evidence": evidence, "tooling-evidence": self.tooling,
            "tooling-public-key": self.public_key, "java-executable": self.java,
            "apkanalyzer-executable": self.analyzer, "repository-root": self.root,
            "sdk-apple-validation-policy": apple_policy,
        }
        values = {
            "expected-build-key": self.ready["buildKey"], "trusted-workflow-sha": "c" * 40,
            "trusted-android-workflow-sha": "d" * 40, "trusted-source-commit": "e" * 40,
            "trusted-source-tree": "1" * 40, "policy-revision": "2" * 40,
            "required-trust-domain": "development",
        }
        for name, value in {**paths, **values}.items():
            argv.extend(("--" + name, str(value)))
        with patch.object(workflow, "execute") as execute, \
                patch.dict(os.environ, {"GITHUB_TOKEN": "token"}, clear=True):
            self.assertEqual(0, workflow.main(argv))
        self.assertEqual(self.contract_evidence, execute.call_args.kwargs["binary_contract_evidence"])
        self.assertEqual(self.apple_policy, execute.call_args.kwargs["sdk_apple_validation_policy"])
        self.assertEqual(self.discovery, execute.call_args.kwargs["discovery"])
        self.assertEqual(self.state, execute.call_args.kwargs["state"])
        self.assertEqual("token", execute.call_args.kwargs["token"])
        self.assertIs(os.environ, execute.call_args.kwargs["environ"])
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            workflow.main([*argv, "--tooling-keyring", str(self.root / "keyring.json")])
        self.assertEqual(2, error.exception.code)


if __name__ == "__main__":
    unittest.main()
