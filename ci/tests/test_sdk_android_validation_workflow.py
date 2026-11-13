"""Android validation controller orchestration; transport and full gates are mocked."""

from copy import deepcopy
from contextlib import contextmanager, redirect_stderr
import base64
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
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
        self.capture_producer = self.current
        self.original = self.producer(1)
        self.apk_producer = self.producer(1)
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
        self.admissions = {}
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
        self.assertEqual(workflow.maven_consumed_predecessors(instance), kwargs["materialized_scope"])
        self.assertEqual(6, len(kwargs["materialized_scope"]))
        self.assertEqual(self.ready["buildKey"], kwargs["expected_build_key"])
        self.assertEqual(self.arguments["trusted_workflow_sha"], kwargs["sdk_original_workflow_sha"])
        self.assertIs(self.apple_policy, kwargs["sdk_apple_validation_policy"])
        actual = {name: kwargs[name] for name in (
            "sdk_facade_metadata_admission", "sdk_android_metadata_admission") if name in kwargs}
        self.assertEqual(set(self.admissions), set(actual))
        for name, value in self.admissions.items():
            self.assertIs(value, actual[name])
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
        return {"captureProducer": deepcopy(self.capture_producer)}

    def capture_protected(self, plan, root, final, destination, **kwargs):
        self.events.append("protected-capture")
        self.assertTrue((final / "final.bin").is_file())
        self.assertNotIn(self.root, destination.parents)
        destination.mkdir()
        (destination / "protected.bin").write_bytes(b"exact protected capture")
        lane = destination / "original/lane-receipt.json"
        lane.parent.mkdir()
        receipt = deepcopy(self.apk_producer)
        receipt["validationCommit"] = receipt.pop("commit")
        receipt["validationTree"] = receipt.pop("tree")
        write_canonical_json(lane, receipt)
        return {"captureProducer": deepcopy(self.capture_producer)}

    def produce(self, **kwargs):
        self.events.append("produce")
        self.phase_arguments = kwargs
        self.assertEqual(self.apk_producer, kwargs["expected_original_producer"])
        self.assertEqual(self.binary["producer"], kwargs["expected_binary_producer"])
        self.assertEqual(self.capture_producer, kwargs["expected_capture_producer"])
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

    def test_retained_device_capture_preserves_old_producer_and_finalizes_current_phase(self):
        self.capture_producer = {**self.original, "runId": 16, "commit": "9" * 40}
        self.apk_producer = {**self.capture_producer, "runAttempt": 1}
        origin = {"producer": self.capture_producer, "workflowSha": "8" * 40,
            "authority": {"trustedSourceCommit": "e" * 40, "trustedSourceTree": "1" * 40,
                          "trustedAndroidWorkflowSha": "d" * 40},
            "final": {"artifact_id": 701}, "protected": {"artifact_id": 702}}
        historical = self.root / "historical-plan.json"
        historical.write_bytes(b"original plan")
        final, protected = self.capture_final, self.capture_protected
        def capture(kind, callback, *args, **kwargs):
            self.assertEqual(historical, args[0])
            self.assertEqual("16", kwargs["environ"]["GITHUB_RUN_ID"])
            self.assertEqual("9" * 40, kwargs["expected_revision"])
            self.assertEqual("8" * 40, kwargs["trusted_workflow_sha"])
            return {**callback(*args, **kwargs), "locator": origin[kind]}
        self.capture_final = lambda *a, **k: capture("final", final, *a, **k)
        self.capture_protected = lambda *a, **k: capture("protected", protected, *a, **k)
        with patch.object(workflow, "retained_android_evidence_origin", return_value=origin), \
                patch.object(workflow, "capture_retained_android_plan", return_value=historical) as plan:
            _, finalize = self.call()
        plan.assert_called_once()
        self.assertEqual(self.current, finalize.call_args.kwargs["producer"])
        self.assertEqual("17", self.environment["GITHUB_RUN_ID"])
        self.assertEqual(self.capture_producer, self.phase_arguments["expected_capture_producer"])
        self.assertEqual(self.apk_producer, self.phase_arguments["expected_original_producer"])

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
        self.assertEqual(self.apk_producer, self.phase_arguments["expected_original_producer"])
        self.assertEqual(self.original, self.phase_arguments["expected_binary_producer"])
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

    def test_metadata_admissions_are_forwarded_by_identity_only_when_supplied(self):
        self.admissions = {
            "sdk_facade_metadata_admission": object(),
            "sdk_android_metadata_admission": object(),
        }
        result, _ = self.call(**self.admissions)
        self.assertEqual(self.ready["buildKey"], result["shard"]["receipt"]["buildKey"])
        for name in self.admissions:
            self.assertNotIn(name, self.phase_arguments)

    def test_missing_original_apk_receipt_never_falls_back_to_current_producer(self):
        capture = self.capture_protected
        def missing(*args, **kwargs):
            result = capture(*args, **kwargs)
            (args[3] / "original/lane-receipt.json").unlink()
            return result
        self.capture_protected = missing
        with self.assertRaisesRegex(ValueError, "missing or unsafe"):
            self.call()
        self.assertNotIn("produce", self.events)
        self.assertNotIn("finalize", self.events)

    def test_older_selected_binary_is_preserved_but_substituted_bytes_reject(self):
        changed = self.producer(1, commit="9" * 40)
        self.binary = self.receipt(self.binary_stage, self.binary_receipt, "binary", changed)
        self.selected_binary_bytes = self.binary_receipt.read_bytes()
        raw = self.binary_receipt.read_bytes()
        self.call()
        self.assertEqual(changed, self.phase_arguments["expected_binary_producer"])
        self.assertEqual(self.apk_producer, self.phase_arguments["expected_original_producer"])
        self.assertEqual(raw, self.binary_receipt.read_bytes())

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

    def test_cli_metadata_policy_context_wraps_execute_and_fails_closed(self):
        for mode in ("absent", "present", "error"):
            policy = self.root / (mode + ".json") if mode != "absent" else None
            parsed = SimpleNamespace(plan=self.plan, repository_root=self.root,
                binary_contract_evidence=self.root / "contract-policy.json",
                tooling_keyring=None, tooling_keys_directory=None,
                sdk_apple_validation_policy=None,
                sdk_facade_metadata_policy=policy, sdk_android_metadata_policy=policy)
            admissions = ({"sdk_facade_metadata_admission": object(),
                           "sdk_android_metadata_admission": object()}
                          if mode == "present" else {})
            events = []

            @contextmanager
            def options(arguments):
                self.assertIs(self.plan, arguments["plan"])
                self.assertIs(self.root, arguments["repository_root"])
                arguments.pop("sdk_facade_metadata_policy")
                arguments.pop("sdk_android_metadata_policy")
                if mode == "error":
                    raise ValueError("metadata policy rejected")
                events.append("enter")
                try:
                    yield admissions
                finally:
                    events.append("exit")

            def run(**arguments):
                self.assertEqual(["enter"], events)
                for name in ("sdk_facade_metadata_admission", "sdk_android_metadata_admission"):
                    if name in admissions:
                        self.assertIs(admissions[name], arguments[name])
                    else:
                        self.assertNotIn(name, arguments)
                self.assertNotIn("sdk_facade_metadata_policy", arguments)
                self.assertNotIn("sdk_android_metadata_policy", arguments)
                events.append("execute")

            with self.subTest(mode=mode), \
                    patch.object(workflow.argparse.ArgumentParser, "parse_args", return_value=parsed), \
                    patch.object(workflow, "add_metadata_admission_arguments") as add, \
                    patch.object(workflow, "metadata_admission_options", side_effect=options), \
                    patch.object(workflow.product_reuse, "_canonical_control",
                                 return_value=self.contract_evidence), \
                    patch.object(workflow, "execute", side_effect=run) as execute:
                if mode == "error":
                    with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                        workflow.main([])
                    execute.assert_not_called()
                else:
                    self.assertEqual(0, workflow.main([]))
                    self.assertEqual(["enter", "execute", "exit"], events)
                add.assert_called_once()


class RetainedAndroidConsumerTest(unittest.TestCase):
    """Synthetic live-state boundary; no native authentication or Gradle runs."""

    def setUp(self):
        from reuse_qualification import CompletedFrozenReuse
        self.native_type = CompletedFrozenReuse
        temporary = tempfile.TemporaryDirectory(prefix="retained-android-consumer-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.plan_path = self.root / "plan.json"
        self.plan = {"repository": "codex-agent-labs/codex-agent", "event": "pull_request",
                     "pullRequest": 31, "validationCommit": "a" * 40, "validationTree": "b" * 40,
                     "lanes": {"consumer-android": {"build": True, "test": True, "metadata": False}}}
        write_canonical_json(self.plan_path, self.plan)
        self.environment = {"GITHUB_RUN_ID": "20", "GITHUB_RUN_ATTEMPT": "1",
                            "CI_VALIDATION_COMMIT": "a" * 40, "CI_VALIDATION_TREE": "b" * 40,
                            "GITHUB_TOKEN": "synthetic-read-token", "ANDROID_HOME": "/installed/android"}
        consumer = workflow.product_reuse._consumer(self.plan, self.environment)
        self.records = {instance: {
            **{key: getattr(instance, key) for key in ("product", "component", "phase", "target")},
            "state": "retained", "buildKey": "sha256:" + str(index) * 64,
            "receiptSha256": "sha256:" + str(index + 3) * 64, "objectSha256": "sha256:" + "9" * 64,
        } for index, instance in enumerate(workflow._CONSUMER_INPUTS, 1)}
        self.state = workflow.product_reuse._VerifiedProductState(
            plan=self.plan, producer=consumer["producer"], consumer=consumer,
            requested=workflow._CONSUMER_INPUTS, closure=workflow._CONSUMER_INPUTS,
            expected_fixed={"versions": {"sdk": "0.8.7", "contract": "0.8.0"}},
            rebased_request={}, prior={}, prior_by_instance=self.records, sources={},
            prior_carrier_phases=deepcopy(self.records), prior_ready_plans={},
            completed_frozen=object.__new__(CompletedFrozenReuse))
        self.restored = {}
        self.private_roots = []
        self.collision = False
        self.native_live = True
        self.check = self.enterContext(patch.object(CompletedFrozenReuse, "check_consumer", side_effect=self.check_live))
        self.envelope = self.enterContext(patch.object(CompletedFrozenReuse, "envelope", side_effect=self.original))
        self.checkout = self.enterContext(patch.object(workflow.product_reuse, "_runtime_worker_checkout"))
        self.restore = self.enterContext(patch.object(workflow.product_reuse, "_restore_product_objects",
                                                     side_effect=self.restore_inputs))
        self.run = self.enterContext(patch.object(workflow.subprocess, "run"))
        self.count = self.enterContext(patch.object(workflow.product_reuse, "count"))
        self.projection = self.root / "build/protected-candidate" / ("a" * 40) / "consumer-maven/android"

    def check_live(self, consumer):
        self.assertEqual(self.state.consumer, consumer)
        if not self.native_live:
            raise ValueError("Native owner expired")

    def original(self, record, raw):
        instance = workflow.product_reuse._identity(record)
        self.assertEqual(self.restored[instance]["receiptBytes"], raw)
        return {"receipt": self.restored[instance]["receipt"]}

    def restore_inputs(self, state, instances, destination):
        from ci.products.contract import _write_contract_zip
        self.assertIs(state, self.state)
        self.assertEqual(workflow._CONSUMER_INPUTS, instances)
        self.private_roots.append(destination.parent)
        for index, instance in enumerate(instances):
            stage = destination / "-".join((instance.product, instance.component, instance.phase, instance.target)) / "stage"
            stage.mkdir(parents=True)
            version = "0.8.0" if index == 0 else "0.8.7"
            receipt = {"productVersion": version, "producer": {"commit": "c" * 40}}
            if index == 0:
                content = self.root / "contract-content"
                file = content / "maven/io/github/codex-agent-labs/codex-agent-core/0.8.0/codex-agent-core-0.8.0.pom"
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_bytes(b"original contract Maven bytes")
                archive = stage / "outputs/contract.zip"
                archive.parent.mkdir()
                _write_contract_zip(content, archive)
                receipt["outputs"] = [{"relativePath": "outputs/contract.zip", "kind": "contract-bundle",
                                       "bytes": archive.stat().st_size, "sha256": sha256_file(archive)}]
            else:
                artifact = "codex-agent" if index == 1 or self.collision else "codex-agent-runtime-android"
                output = stage / f"outputs/maven/io/github/codex-agent-labs/{artifact}/{version}/{artifact}-{version}.pom"
                output.parent.mkdir(parents=True)
                output.write_bytes(f"original {instance.component}".encode())
            self.restored[instance] = {"receipt": receipt, "receiptBytes": canonical_json_bytes(receipt)}
        return self.restored

    def consume(self, state=None):
        return workflow.run_retained_android_consumer(self.state if state is None else state,
            plan_path=self.plan_path, repository_root=self.root, environ=self.environment)

    def test_exact_three_originals_fixed_command_and_private_lifetime(self):
        def execute(command, **kwargs):
            self.assertEqual([str(self.root / "gradlew"), "verifyStagedKmpConsumerAndroid",
                              "--build-cache", "--parallel", "--stacktrace",
                              "-PcodexAgent.candidateCommit=" + "a" * 40,
                              "-PcodexAgent.candidateTree=" + "b" * 40], command[:-1])
            maven = Path(command[-1].removeprefix("-PcodexAgent.mavenRepositoryDirectory="))
            self.assertEqual(3, len(regular_file_inventory(maven)))
            self.assertTrue(self.private_roots[0].is_dir())
            self.assertEqual(self.root, kwargs["cwd"])
            self.assertIs(kwargs["check"], True)
            self.assertEqual(workflow.subprocess.DEVNULL, kwargs["stdin"])
            self.assertNotIn("GITHUB_TOKEN", kwargs["env"])
            self.assertEqual("/installed/android", kwargs["env"]["ANDROID_HOME"])
        self.run.side_effect = execute
        self.assertIsNone(self.consume())
        self.run.assert_called_once()
        self.restore.assert_called_once()
        self.assertEqual(3, self.envelope.call_count)
        projected = regular_file_inventory(self.projection)
        self.assertEqual(3, len(projected))
        self.count.assert_any_call("androidInstalledMavenProjectionTrees")
        self.count.assert_any_call("androidInstalledMavenProjectionBytes", sum(row["bytes"] for row in projected))
        self.assertTrue(all(not path.exists() for path in self.private_roots))
        self.assertEqual("c" * 40, self.restored[workflow._CONSUMER_INPUTS[2]]["receipt"]["producer"]["commit"])

    def test_rejects_caller_dict_missing_native_and_changed_current_selection(self):
        from dataclasses import replace
        for state in ({"complete": True}, replace(self.state, completed_frozen=None)):
            with self.subTest(state=type(state).__name__), self.assertRaisesRegex(ValueError, "live native"):
                self.consume(state)
        self.records[workflow._CONSUMER_INPUTS[2]]["objectSha256"] = "sha256:" + "e" * 64
        with self.assertRaisesRegex(ValueError, "exact completed predecessor"):
            self.consume()
        self.restore.assert_not_called()
        self.run.assert_not_called()

    def test_rejects_unauthorized_lane_and_original_receipt_mismatch(self):
        self.environment["CI_VALIDATION_TREE"] = "e" * 40
        with self.assertRaisesRegex(ValueError, "authorized lane"):
            self.consume()
        self.environment["CI_VALIDATION_TREE"] = "b" * 40
        self.envelope.return_value = None
        self.envelope.side_effect = None
        with self.assertRaisesRegex(ValueError, "native original receipt"):
            self.consume()
        self.run.assert_not_called()
        self.assertTrue(all(not path.exists() for path in self.private_roots))

    def test_overlapping_maven_inputs_fail_before_consumer(self):
        self.collision = True
        with self.assertRaisesRegex(ValueError, "inputs overlap"):
            self.consume()
        self.run.assert_not_called()
        self.assertTrue(all(not path.exists() for path in self.private_roots))

    def test_late_input_change_or_native_exit_cannot_return_success(self):
        def mutate(command, **kwargs):
            maven = Path(command[-1].split("=", 1)[1])
            next(maven.rglob("*.pom")).write_bytes(b"changed after child launch")
        self.run.side_effect = mutate
        with self.assertRaisesRegex(ValueError, "inputs changed"):
            self.consume()
        self.assertTrue(all(not path.exists() for path in self.private_roots))
        self.assertFalse(self.projection.exists())
        self.run.side_effect = lambda *args, **kwargs: setattr(self, "native_live", False)
        with self.assertRaisesRegex(ValueError, "Native owner expired"):
            self.consume()
        self.assertTrue(all(not path.exists() for path in self.private_roots))
        self.assertFalse(self.projection.exists())

    def test_child_failure_propagates_after_lifetime_recheck_and_cleanup(self):
        self.run.side_effect = workflow.subprocess.CalledProcessError(7, ["fixed-consumer"])
        with self.assertRaises(workflow.subprocess.CalledProcessError) as caught:
            self.consume()
        self.assertEqual(7, caught.exception.returncode)
        self.assertEqual(3, self.check.call_count)
        self.assertTrue(all(not path.exists() for path in self.private_roots))
        self.assertFalse(self.projection.exists())

    def test_projection_is_fresh_and_never_overwrites_existing_output(self):
        self.projection.mkdir(parents=True)
        sentinel = self.projection / "existing"
        sentinel.write_bytes(b"preserve this original")
        with self.assertRaisesRegex(ValueError, "must not exist"):
            self.consume()
        self.assertEqual(b"preserve this original", sentinel.read_bytes())
        self.assertTrue(all(not path.exists() for path in self.private_roots))


class RetainedInstalledConsumerTest(unittest.TestCase):
    """Fixed lane mapping with tiny synthetic state; no Gradle or admission calls."""
    check_live = RetainedAndroidConsumerTest.check_live
    original = RetainedAndroidConsumerTest.original

    def setUp(self):
        RetainedAndroidConsumerTest.setUp(self)
        self.expected_inputs = workflow._CONSUMER_INPUTS
        self.bad_runtime_version = False
        self.run.side_effect = self.emit_controls
        self.state.expected_fixed["versions"].update({"runtime-release": "0.8.2", "runtime-compatibility": "0.8.0"})
        repository = Path(__file__).resolve().parents[2]
        # Candidate test files run under their source overlay; use the exact new
        # declarations and unchanged repository template as small fixture data.
        candidate = repository
        main = Path.cwd()
        template = self.root / "gradle/release/kmp-consumer-template"
        shutil.copytree(main / "gradle/release/kmp-consumer-template", template,
                        ignore=shutil.ignore_patterns(".gradle", "build"))
        control = self.root / workflow._CONSUMER_TEMPLATE
        control.parent.mkdir(parents=True)
        shutil.copytree(candidate / workflow._CONSUMER_TEMPLATE, control)

    def select(self, lane):
        from dataclasses import replace
        target, _, extras = workflow._INSTALLED_CONSUMERS[lane]
        self.lane = lane
        self.expected_inputs = (*workflow._CONSUMER_INPUTS[:2], *extras)
        self.plan["lanes"] = {lane: {"build": True, "test": False, "metadata": False}}
        write_canonical_json(self.plan_path, self.plan)
        self.records = {instance: {
            **{key: getattr(instance, key) for key in ("product", "component", "phase", "target")},
            "state": "retained", "buildKey": "sha256:" + str(i) * 64,
            "receiptSha256": "sha256:" + str(i + 3) * 64, "objectSha256": "sha256:" + "9" * 64,
        } for i, instance in enumerate(self.expected_inputs, 1)}
        self.state = replace(self.state, requested=self.expected_inputs, closure=self.expected_inputs,
                             prior_by_instance=self.records, prior_carrier_phases=deepcopy(self.records))
        self.projection = self.root / "build/protected-candidate" / ("a" * 40) / (
            "payload/maven" if target == "common" else "consumer-maven/" + target)

    def restore_inputs(self, state, instances, destination):
        self.assertEqual(tuple(i for i in self.expected_inputs if i != workflow._IOS_PACKAGE), instances)
        base = workflow._CONSUMER_INPUTS if workflow._CONSUMER_INPUTS[2] in instances else workflow._CONSUMER_INPUTS[:2]
        with patch.object(workflow, "_CONSUMER_INPUTS", base):
            RetainedAndroidConsumerTest.restore_inputs(self, state, base, destination)
        if workflow._RUNTIME_MAVEN in instances:
            instance = workflow._RUNTIME_MAVEN
            stage = destination / "runtime-runtime-aggregate-metadata-aggregate/stage"
            for component in ("jvm", "macos-arm64", "macos-x64", "linux-arm64", "linux-x64", "windows-x64", "node-js", "node-wasm"):
                artifact = "runtime-" + component
                path = stage / f"outputs/maven/{component}/io/github/codex-agent-labs/{artifact}/0.8.2/{artifact}-0.8.2.pom"
                path.parent.mkdir(parents=True)
                path.write_bytes(component.encode())
            receipt = {"productVersion": "0.8.7" if self.bad_runtime_version else "0.8.2",
                       "producer": {"commit": "d" * 40}}
            self.restored[instance] = {"receipt": receipt, "receiptBytes": canonical_json_bytes(receipt)}
        return self.restored

    def emit_controls(self, command, **kwargs):
        target = workflow._INSTALLED_CONSUMERS[self.lane][0]
        maven = Path(command[-1].split("=", 1)[1])
        self.consumed_maven = maven
        versions = self.state.expected_fixed["versions"]
        report = {"schemaVersion": 6, "result": "passed", "sdkVersion": versions["sdk"],
            "runtimeVersion": versions["runtime-release"], "repository": "CENTRAL_STAGING-only",
            "mavenGroup": "io.github.codex-agent-labs", "target": target, "tasks": list(workflow._INSTALLED[self.lane][3])}
        inventory = {"schemaVersion": 1, "groupId": "io.github.codex-agent-labs",
            "contractVersion": versions["contract"], "runtimeVersion": versions["runtime-release"],
            "sdkVersion": versions["sdk"], "target": target,
            "files": [{"fileName": row["relativePath"], "bytes": row["bytes"],
                       "sha256": row["sha256"].removeprefix("sha256:")} for row in regular_file_inventory(maven)]}
        self.report_root = self.root / "build/protected-candidate" / ("a" * 40) / "reports"
        self.report_root.mkdir(parents=True, exist_ok=True)
        # Preserve deliberately noncanonical raw formatting, as the real Kotlin task does.
        (self.report_root / f"kmp-consumer-{target}.json").write_text(json.dumps(report, indent=2) + "\n")
        (self.report_root / f"maven-inventory-{target}.json").write_text(json.dumps(inventory, indent=2) + "\n")

    def consume(self):
        return workflow.run_retained_installed_consumer(self.state, lane=self.lane,
            plan_path=self.plan_path, repository_root=self.root, environ=self.environment)

    def test_common_returns_only_exact_detached_controls_and_no_maven_projection(self):
        self.select("consumer-common")
        result = self.consume()
        self.assertEqual("verifyStagedKmpConsumerCommon", self.run.call_args.args[0][1])
        self.assertEqual(2, len(result["record"]["mavenFiles"]))
        self.assertIn("--init-script", self.run.call_args.args[0])
        self.assertFalse(self.projection.exists())
        self.assertFalse(self.consumed_maven.exists())
        self.assertEqual((self.report_root / "kmp-consumer-common.json").read_bytes(), result["consumerReport"])
        self.assertEqual((self.report_root / "maven-inventory-common.json").read_bytes(), result["mavenInventory"])
        self.assertEqual(self.state.consumer["producer"], result["record"]["producer"])
        self.assertEqual(sha256_file(self.plan_path), result["record"]["planSha256"])
        result["record"]["originalInputs"][0]["buildKey"] = "changed detached control"
        self.assertNotEqual(result["record"]["originalInputs"][0]["buildKey"], self.state.prior_by_instance[self.expected_inputs[0]]["buildKey"])

    def test_runtime_lanes_select_exact_components_and_distinct_version_guards(self):
        for lane in ("consumer-desktop", "consumer-node-js", "consumer-node-wasm"):
            with self.subTest(lane=lane):
                self.select(lane)
                target, task, _ = workflow._INSTALLED_CONSUMERS[lane]
                def execute(command, **kwargs):
                    self.assertEqual(task, command[1])
                    script = Path(command[command.index("--init-script") + 1]).read_text()
                    for version in ("0.8.0", "0.8.2", "0.8.7"):
                        self.assertIn('"' + version + '"', script)
                    self.assertIn("inventory.inputs.properties.runtimeVersion != expectedRuntime", script)
                    self.assertIn("consumer.runtimeVersion.get() != expectedRuntime", script)
                    self.assertIn('new File("', script)
                    maven = Path(command[-1].split("=", 1)[1])
                    rows = regular_file_inventory(maven)
                    self.assertEqual(2 + len(workflow._RUNTIME_COMPONENTS[target]), len(rows))
                    actual = {Path(row["relativePath"]).name for row in rows if "/runtime-" in row["relativePath"]}
                    self.assertEqual({"runtime-" + c + "-0.8.2.pom" for c in workflow._RUNTIME_COMPONENTS[target]}, actual)
                    self.assertNotIn("GITHUB_TOKEN", kwargs["env"])
                    self.emit_controls(command, **kwargs)
                self.run.side_effect = execute
                self.consume()
                self.assertFalse(self.projection.exists())

    def test_runtime_version_mismatch_and_template_mutation_fail_without_projection(self):
        self.select("consumer-node-js")
        self.bad_runtime_version = True
        with self.assertRaisesRegex(ValueError, "native original receipt"):
            self.consume()
        self.run.assert_not_called()
        self.bad_runtime_version = False
        def mutate(command, **_):
            source = self.root / workflow._CONSUMER_TEMPLATE / "build.gradle.kts"
            source.write_text(source.read_text() + "// late replacement\n")
        self.run.side_effect = mutate
        with self.assertRaisesRegex(ValueError, "template inputs changed"):
            self.consume()
        self.assertFalse(self.projection.exists())

    def test_ios_borrows_scoped_reader_without_full_object_restore_and_detaches_after_exits(self):
        self.select("consumer-ios-device")
        events = []
        def scoped(state, record, destination, target, stack, *, token):
            self.assertIs(state, self.state)
            self.assertIs(record, self.records[workflow._IOS_PACKAGE])
            self.assertEqual("ios-device", target)
            self.assertEqual("synthetic-read-token", token)
            file = destination / "ios-input.klib"
            file.write_bytes(b"tiny selected scoped input")
            stack.callback(lambda: events.append("archives-closed"))
        def execute(*args, **kwargs):
            self.assertEqual([], events)
            self.emit_controls(*args, **kwargs)
        self.run.side_effect = execute
        with patch.object(workflow, "_copy_retained_ios_maven", side_effect=scoped), \
                patch.object(workflow, "publish_regular_tree", side_effect=AssertionError("No generic Maven publication")):
            result = self.consume()
        self.assertEqual(["archives-closed"], events)
        self.assertEqual("consumer-ios-device", result["record"]["lane"])
        self.assertFalse(self.projection.exists())
        shutil.rmtree(self.report_root)
        def fail_late(*args, **kwargs):
            scoped(*args, **kwargs)
            def fail():
                raise ValueError("synthetic late archive owner failure")
            args[4].callback(fail)
        events.clear()
        with patch.object(workflow, "_copy_retained_ios_maven", side_effect=fail_late), \
                self.assertRaisesRegex(ValueError, "late archive owner"):
            self.consume()
        self.assertFalse(self.projection.exists())

    def test_unknown_lane_cannot_supply_a_command_or_template(self):
        with self.assertRaisesRegex(ValueError, "Unsupported installed consumer lane"):
            workflow.run_retained_installed_consumer(self.state, lane="consumer-desktop;compile-product",
                plan_path=self.plan_path, repository_root=self.root, environ=self.environment)
        self.run.assert_not_called()
        self.restore.assert_not_called()

    def test_dedicated_template_changes_only_exact_target_declarations(self):
        original = (Path.cwd() / "gradle/release/kmp-consumer-template/build.gradle.kts").read_text()
        new = (self.root / workflow._CONSUMER_TEMPLATE / "build.gradle.kts").read_text()
        self.assertEqual(original[original.index('if (consumerTarget == "desktop") {'):],
                         new[new.index('if (consumerTarget == "desktop") {'):])
        self.assertEqual(original[:original.index('                listOf(macosMain')],
                         new[:new.index('                mapOf(')])
        for suffix in ("jvm", "js", "wasm-js"):
            self.assertIn('codex-agent-runtime-desktop-' + suffix + ':$codexAgentRuntimeVersion', new)
        for suffix in ("macosarm64", "macosx64", "linuxarm64", "linuxx64", "mingwx64"):
            self.assertIn('to "' + suffix + '"', new)
        self.assertIn('codex-agent:$codexAgentSdkVersion', new)
        self.assertNotIn('codex-agent-runtime-desktop:$codexAgentRuntimeVersion', new)


    def test_fresh_control_guard_rejects_existing_report_before_consumer(self):
        self.select("consumer-common")
        report = self.root / "build/protected-candidate" / ("a" * 40) / "reports/kmp-consumer-common.json"
        report.parent.mkdir(parents=True)
        report.write_bytes(b"stale success")
        with self.assertRaisesRegex(ValueError, "controls must be fresh"):
            self.consume()
        self.run.assert_not_called()
        self.assertEqual(b"stale success", report.read_bytes())

    def test_task_version_and_maven_row_substitution_never_returns_controls(self):
        self.select("consumer-common")
        for kind in ("task", "runtime-version", "contract-version", "maven-sha", "maven-size-bool", "extra-field"):
            with self.subTest(kind=kind):
                def bad(command, **kwargs):
                    self.emit_controls(command, **kwargs)
                    filename = "kmp-consumer-common.json" if kind in ("task", "runtime-version", "extra-field") else "maven-inventory-common.json"
                    path = self.report_root / filename
                    value = json.loads(path.read_bytes())
                    if kind == "task": value["tasks"] = ["unrelatedTask"]
                    elif kind == "runtime-version": value["runtimeVersion"] = "0.8.7"
                    elif kind == "contract-version": value["contractVersion"] = "0.8.2"
                    elif kind == "maven-sha": value["files"][0]["sha256"] = "f" * 64
                    elif kind == "maven-size-bool": value["files"][0]["bytes"] = True
                    else: value["unapproved"] = True
                    path.write_text(json.dumps(value))
                self.run.side_effect = bad
                with self.assertRaises(ValueError): self.consume()
                self.assertFalse(self.projection.exists())
                shutil.rmtree(self.report_root)

    def test_generic_android_keeps_control_only_mode_distinct_from_legacy_wrapper(self):
        self.select("consumer-android")
        with patch.object(workflow, "publish_regular_tree", side_effect=AssertionError("Generic lane must not project Maven")):
            result = self.consume()
        self.assertEqual(3, len(result["record"]["originalInputs"]))
        self.assertEqual("verifyStagedKmpConsumerAndroid", result["record"]["task"])
        self.assertFalse(self.projection.exists())

    def test_live_session_reuses_maven_scan_but_rejects_late_equal_size_mutation(self):
        from products import restore
        self.select("consumer-common")
        real_scan = restore._uncached_file_inventory
        scanned = []
        def scan(path, **kwargs):
            if Path(path).name == "maven": scanned.append(Path(path))
            return real_scan(path, **kwargs)
        with restore.verification_session(), patch.object(restore, "_uncached_file_inventory", side_effect=scan):
            self.consume()
        self.assertEqual(1, len(scanned))
        shutil.rmtree(self.report_root)
        def mutate(command, **kwargs):
            self.emit_controls(command, **kwargs)
            file = next(path for path in self.consumed_maven.rglob("*") if path.is_file())
            before = file.stat()
            file.write_bytes(b"x" * before.st_size)
            os.utime(file, ns=(before.st_atime_ns, before.st_mtime_ns))
        self.run.side_effect = mutate
        with restore.verification_session(), self.assertRaisesRegex(ValueError, "inputs changed"):
            self.consume()
        self.assertFalse(self.projection.exists())

class RetainedAndroidConsumerRoutingTest(unittest.TestCase):
    def test_only_same_job_canonical_full_consumer_skips_second_execution(self):
        root = Path(__file__).resolve().parents[2]
        action = (root / ".github/actions/run-ci-lane/action.yml").read_text()
        execution = action.split("    - id: execution\n", 1)[1].split("      continue-on-error:", 1)[0]
        condition = " ".join(execution.split("if: >-", 1)[1].split())
        values = {"inputs.contract-tooling-only": "false", "inputs.reuse-only": "false",
                  "steps.reuse.outputs.reused": "false", "steps.portable-runtime-products.outcome": "skipped",
                  "inputs.force-build": "false", "steps.selection.outputs.test": "true",
                  "steps.selection.outputs.metadata": "false", "steps.selection.outputs.build": "true",
                  "steps.production.outputs.reused": "false"}
        for lane, mode, production, expected in (
                ("consumer-android", "true", "success", False),
                ("consumer-android", "true", "skipped", True),
                ("consumer-android", "true", "failure", False),
                ("consumer-android", "false", "success", True),
                ("consumer-desktop", "true", "success", True),
                ("consumer-node-js", "false", "success", True)):
            with self.subTest(lane=lane, mode=mode, production=production):
                selected = {**values, "inputs.lane": lane, "inputs.android-installed-consumer": mode,
                            "steps.production-execution.outcome": production}
                expression = condition
                for key, value in sorted(selected.items(), key=lambda item: -len(item[0])):
                    expression = expression.replace(key, repr(value))
                expression = expression.replace("&&", " and ").replace("||", " or ").replace("!(", "not (")
                self.assertEqual(expected, eval(expression, {"__builtins__": {}}))
        # No serialized capability or production reuse result skips this check.
        self.assertIn("inputs.android-installed-consumer == 'true' && steps.production-execution.outcome == 'success'", condition)
        self.assertEqual(2, action.count("CODEX_AGENT_ANDROID_INSTALLED_CONSUMER: ${{ inputs.android-installed-consumer }}"))
        workflow_text = (root / ".github/workflows/sdk-consumer-validation.yml").read_text()
        self.assertIn("android-installed-consumer: ${{ matrix.lane == 'consumer-android' && inputs.retainedAndroidConsumer && 'true' || 'false' }}", workflow_text)
        legacy = workflow_text.split("      - if: matrix.lane == 'consumer-android' && !inputs.retainedAndroidConsumer\n", 1)[1]
        self.assertIn("name: codex-agent-ci-android-${{ inputs.validationTree }}", legacy.split("      - if:", 1)[0])

    def test_fixed_branch_invokes_one_capture_and_requires_native_policy(self):
        import subprocess
        root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory(prefix="android-consumer-routing-") as temporary:
            work = Path(temporary).resolve()
            executable = work / "python3"
            executable.write_text('#!/bin/sh\nprintf "%s\\n" "$@" >> "$RECORDED_ARGUMENTS"\n')
            executable.chmod(0o755)
            recorded = work / "arguments"
            environment = {"PATH": str(work), "CI_VALIDATION_COMMIT": "a" * 40,
                "CI_VALIDATION_TREE": "b" * 40, "CODEX_AGENT_ANDROID_INSTALLED_CONSUMER": "true",
                "CODEX_AGENT_COMPLETED_REUSE_POLICY": str(work / "native-policy.json"),
                "SDK_STATE_ARTIFACT_ID": "17", "SDK_STATE_ARTIFACT_SHA256": "sha256:" + "c" * 64,
                "SDK_STATE_WAVE": "0", "SDK_STATE_SDK_WAVE": "10", "TRUSTED_WORKFLOW_SHA": "d" * 40,
                "GITHUB_OUTPUT": str(work / "github-output"), "RECORDED_ARGUMENTS": str(recorded)}
            command = ["/bin/bash", str(root / "ci/run-lane.sh"), "consumer-android"]
            subprocess.run(command, cwd=work, env=environment, check=True, capture_output=True)
            arguments = recorded.read_text().splitlines()
            self.assertEqual(["-B", "-m", "ci.sdk_completion", "capture"], arguments[:4])
            self.assertEqual(1, arguments.count("--android-installed-consumer"))
            self.assertEqual("10", arguments[arguments.index("--sdk-state-wave") + 1])
            self.assertNotIn("verifyStagedKmpConsumerAndroid", arguments)
            recorded.unlink()
            del environment["CODEX_AGENT_COMPLETED_REUSE_POLICY"]
            result = subprocess.run(command, cwd=work, env=environment, capture_output=True)
            self.assertNotEqual(0, result.returncode)
            self.assertFalse(recorded.exists())


if __name__ == "__main__":
    unittest.main()
