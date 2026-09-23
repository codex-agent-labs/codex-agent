"""Real receipts/shards, mocked election, signed-input context and full gate.

These tests establish orchestration only, not compiler or hosted authority.
"""

from contextlib import contextmanager, redirect_stderr
from copy import deepcopy
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci import sdk_maven_package_workflow as workflow
from ci.tests.product_chain_support import write_receipt
from ci.tests.test_sdk_facade_workflow import assert_metadata_cli_context
from products.inventory import canonical_json_bytes, load_canonical_json_bytes, snapshot_regular_tree, write_canonical_json
from products.receipt import write_output_manifest
from products.restore import PHASE_PLAN_KEYS


class MavenPackageWorkflowTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.plan = self.root / "plan.json"
        self.plan.write_bytes(b"{}\n")
        self.discovery = self.root / "discovery"
        self.discovery.mkdir()
        self.destination = self.root / "build/worker-upload"
        self.keyring = self.root / "keyring.json"
        self.keyring.write_bytes(b"caller policy (mocked)")
        self.keys = self.root / "keys"
        self.keys.mkdir()
        (self.keys / "key.pub").write_bytes(b"public caller key")
        self.producer = {"repository": "fixture/repository", "commit": "a" * 40, "tree": "b" * 40,
            "event": "pull_request", "workflowPath": ".github/workflows/product-validation.yml",
            "runId": 10, "runAttempt": 1, "pullRequest": 2}
        self.component, self.target = "sdk-core", "common"
        self.events, self.exit_mutation, self.binary_exit_mutation = [], None, None
        self.binary_held = False
        self.binary_context = {"repositoryRoot": "/original/checkout", "workerRoot": "/original/checkout/build/binary"}
        self.binary_capture = self.root / "binary-capture"
        (self.binary_capture / "original").mkdir(parents=True)
        (self.binary_capture / "original/raw.bin").write_bytes(b"")
        (self.binary_capture / "transport.zip").write_bytes(b"exact original binary upload")
        self.android_archive = self.root / "android-runtime.tar.gz"
        self.android_archive.write_bytes(b"caller original Android archive")
        self.original_contract = self.record("original-contract", "contract", "contract", "metadata", "common")
        self.current_contract = self.record("current-contract", "contract", "contract", "metadata", "common")
        evidence = self.root / "original-contract-evidence"
        evidence.mkdir()
        for name in ("attestation.json", "attestation.sig", "public.pub"):
            (evidence / name).write_bytes(b"original binary Contract " + name.encode())
        closure = evidence / workflow.CONTRACT_EXECUTION_CLOSURE_DIRECTORY
        closure.mkdir()
        (closure / "retained.json").write_bytes(b"original full closure (mocked)")
        self.evidence = {"stageRoot": str(self.original_contract["stage"]),
            "phaseReceipt": str(self.original_contract["receiptPath"]),
            "attestation": str(evidence / "attestation.json"), "attestationSignature": str(evidence / "attestation.sig"),
            "publicKey": str(evidence / "public.pub"), "expectedTrustDomain": "development",
            "keyring": None, "keysDirectory": None}
        self.capture = self.root / "authenticated-upload"
        (self.capture / "original").mkdir(parents=True)
        (self.capture / "original/raw.bin").write_bytes(b"")
        (self.capture / "original-upload.zip").write_bytes(b"exact opaque observed ZIP")
        self.sdk = self.root / "verified-sdk"
        self.sdk.mkdir()
        (self.sdk / workflow.REQUEST_NAME).write_bytes(b"authenticated S858 request")
        self.configure("sdk-core")
        self.verified = self.enterContext(patch.object(workflow.sdk_workflow, "verified_inputs", side_effect=self.inputs))
        self.materialized = self.enterContext(patch.object(workflow.product_reuse, "materialize_product_predecessors",
                                                          side_effect=self.materialize))
        self.worker = self.enterContext(patch.object(workflow, "execute_package", side_effect=self.execute_worker))
        self.gate = self.enterContext(patch.object(workflow, "verify_sdk_package_inputs", side_effect=self.full_gate))
        self.binary_reader = self.enterContext(patch.object(workflow, "verified_original_maven_phase", side_effect=self.binary_inputs))
        self.retained_reader = self.enterContext(patch.object(workflow, "verified_retained_maven_phase", side_effect=self.binary_inputs))
        self.checkout = self.enterContext(patch.object(workflow.product_reuse, "_runtime_worker_checkout"))
        self.publish = self.enterContext(patch.object(workflow, "publish_regular_tree", wraps=workflow.publish_regular_tree))

    def record(self, label, product, component, phase, target):
        stage = self.root / label / "stage"
        output = stage / "outputs/artifact.bin"
        output.parent.mkdir(parents=True)
        output.write_bytes(label.encode())
        manifest = write_output_manifest(stage, product, component, phase, target, "0.8.7", {"fixture": "outputs"})
        receipt = stage.parent / "phase-receipt.json"
        value = write_receipt(receipt, product=product, component=component, phase=phase, target=target,
            version="0.8.7", version_identity="0.8.7", outputs=manifest["outputs"], upstream=[],
            context={"producer": self.producer})
        return {"stage": stage, "receiptPath": receipt, "receipt": value}

    def configure(self, component):
        self.component = component
        self.target = "common" if component == "sdk-core" else "android"
        self.binary = self.record(component + "-binary", "sdk", component, "binary", self.target)
        self.package = self.record(component + "-candidate", "sdk", component, "package", self.target)
        self.ready = {name: self.package["receipt"][name] for name in PHASE_PLAN_KEYS}
        self.selection = {"sdkVersion": "0.8.7", "consumers": [dict(product="sdk", component=component,
                            phase="package", target=self.target)]}

    @contextmanager
    def inputs(self, *args, **kwargs):
        self.events.append("enter")
        yield {"selection": self.selection, "capture": self.capture, "sdk": {"directory": self.sdk,
            "arguments": {"contract_metadata_receipt": self.current_contract["receiptPath"]}}}
        self.events.append("exit")
        self.assertFalse((self.destination / "shard").exists())
        if self.exit_mutation:
            self.exit_mutation()
        self.events.append("closed")

    @contextmanager
    def binary_inputs(self, plan, receipt, **kwargs):
        self.events.append("binary-enter")
        self.assertEqual(self.plan, plan)
        self.assertEqual(self.binary["receiptPath"].read_bytes(), receipt.read_bytes())
        self.assertIs(self.evidence, kwargs["binary_contract_evidence"])
        self.assertIs(self.binary_context, kwargs["original_context"])
        self.assertNotIn("keyring", kwargs)
        self.assertNotIn("keys_directory", kwargs)
        if self.component == "sdk-android":
            self.assertEqual(self.android_archive, kwargs["android_runtime_archive"])
        else:
            self.assertNotIn("android_runtime_archive", kwargs)
        if "capture_root" in kwargs:
            self.assertEqual(self.binary_capture, kwargs["capture_root"])
            self.assertNotIn("token", kwargs)
        else:
            self.assertEqual((7, "sha256:" + "b" * 64, "e" * 40, "fixture-token"),
                tuple(kwargs[key] for key in ("artifact_id", "artifact_sha256", "trusted_workflow_sha", "token")))
        self.binary_held = True
        try:
            yield {**self.binary, "receiptBytes": self.binary["receiptPath"].read_bytes(), "capture": self.binary_capture}
        finally:
            self.events.append("binary-exit")
            self.assertFalse((self.destination / "shard").exists())
            self.binary_held = False
            if self.binary_exit_mutation:
                self.binary_exit_mutation()
            self.events.append("binary-closed")

    def materialize(self, plan, discovery, state, instance, destination, **kwargs):
        self.assertEqual(self.component, instance.component)
        self.assertEqual(self.ready["buildKey"], kwargs["expected_build_key"])
        destination.mkdir()
        for record in (self.binary, self.current_contract):
            receipt = record["receipt"]
            name = "-".join(receipt[field] for field in ("product", "component", "phase", "target"))
            snapshot_regular_tree(record["stage"], destination / name / "stage")
            (destination / name / "phase-receipt.json").write_bytes(record["receiptPath"].read_bytes())
        write_canonical_json(destination / "phase-plan.json", self.ready)
        write_canonical_json(destination / "producer.json", self.producer)
        return deepcopy(self.ready)

    def execute_worker(self, ready, **kwargs):
        self.events.append("worker")
        self.assertTrue(self.binary_held)
        self.assertEqual(self.ready, ready)
        self.assertEqual("0.8.7", kwargs["sdk_version"])
        self.assertEqual(self.sdk / workflow.REQUEST_NAME, kwargs["compatibility_request"])
        self.assertNotIn("contract_metadata", kwargs)
        self.assertNotIn("android_runtime_archive", kwargs)
        kwargs["destination"].mkdir()
        (kwargs["destination"] / "gradle.log").write_bytes(b"")
        (kwargs["destination"] / "execution.json").write_bytes(b"{}\n")
        return {"stage": self.package["stage"], "diagnostics": kwargs["destination"],
                "outputInventory": workflow._inventory(self.package["stage"])}

    def full_gate(self, root, stage, receipt, request, **kwargs):
        self.events.append("gate")
        self.assertTrue(self.binary_held)
        self.assertNotIn("exit", self.events)
        self.assertFalse((self.destination / "shard").exists())
        self.candidate = receipt.parent
        evidence = kwargs["binary_contract_evidence"]
        self.assertNotEqual(self.evidence["phaseReceipt"], evidence["phaseReceipt"])
        self.assertEqual(self.original_contract["receiptPath"].read_bytes(), Path(evidence["phaseReceipt"]).read_bytes())
        self.assertNotEqual(self.current_contract["receiptPath"].read_bytes(), Path(evidence["phaseReceipt"]).read_bytes())
        self.assertTrue((Path(evidence["attestation"]).parent / workflow.CONTRACT_EXECUTION_CLOSURE_DIRECTORY /
                         "retained.json").is_file())
        self.assertEqual(self.binary["receiptPath"].read_bytes(), kwargs["binary_receipt_path"].read_bytes())
        self.assertEqual({"binary_stage_root", "binary_receipt_path", "binary_contract_evidence"}, set(kwargs))
        raw = receipt.read_bytes()
        return load_canonical_json_bytes(raw), raw

    def invoke(self, **changes):
        return workflow.execute(self.plan, self.discovery, self.discovery, self.destination,
            **{**dict(component=self.component, expected_build_key=self.ready["buildKey"],
                sdk_inputs_artifact_id=3, sdk_inputs_artifact_sha256="sha256:" + "d" * 64,
                trusted_workflow_sha="e" * 40, keyring=self.keyring, keys_directory=self.keys,
                binary_contract_evidence=self.evidence, binary_original_context=self.binary_context,
                binary_artifact_id=7, binary_artifact_sha256="sha256:" + "b" * 64,
                android_runtime_archive=self.android_archive if self.component == "sdk-android" else None,
                repository_root=self.root, environ={}, token="fixture-token"),
               **changes})

    def test_original_workflow_pin_reaches_state_replay(self):
        self.invoke()
        self.assertEqual("e" * 40, self.materialized.call_args.kwargs["sdk_original_workflow_sha"])

    def test_both_families_publish_only_after_context_and_keep_originals_external(self):
        for component in ("sdk-core", "sdk-android"):
            with self.subTest(component=component):
                fixture = MavenPackageWorkflowTest(methodName="runTest")
                fixture.setUp()
                try:
                    if component == "sdk-android": fixture.configure(component)
                    result = fixture.invoke()
                    self.assertEqual(component, result["receipt"]["component"])
                    self.assertEqual(["enter", "binary-enter", "worker", "gate", "binary-exit", "binary-closed", "exit", "closed"], fixture.events)
                    self.assertEqual(fixture.capture.joinpath("original-upload.zip").read_bytes(),
                        (fixture.destination / "sdk-inputs-original/original-upload.zip").read_bytes())
                    self.assertEqual({"artifact.bin"}, {path.name for path in (fixture.package["stage"] / "outputs").iterdir()})
                    self.assertEqual(fixture.binary_capture.joinpath("transport.zip").read_bytes(),
                        (fixture.destination / "binary-original/capture/transport.zip").read_bytes())
                    self.assertEqual(canonical_json_bytes(fixture.binary_context),
                        (fixture.destination / "binary-original/context.json").read_bytes())
                    fixture.publish.assert_called_once()
                    self.assertNotIn("sdk_validation_tooling", fixture.verified.call_args.kwargs)
                    self.assertNotIn("sdk_apple_validation_policy", fixture.materialized.call_args.kwargs)
                    for call in (fixture.verified.call_args, fixture.materialized.call_args):
                        for name in ("sdk_facade_metadata_admission", "sdk_android_metadata_admission"):
                            self.assertNotIn(name, call.kwargs)
                finally:
                    fixture.doCleanups()

    def test_explicit_policy_objects_forward_only_to_replay(self):
        tooling, apple = {"fixturePolicy": "tooling"}, {"fixturePolicy": "apple"}
        self.invoke(sdk_validation_tooling=tooling, sdk_apple_validation_policy=apple)
        for call in (self.verified.call_args, self.materialized.call_args):
            self.assertIs(tooling, call.kwargs["sdk_validation_tooling"])
            self.assertIs(apple, call.kwargs["sdk_apple_validation_policy"])
        self.assertNotIn("sdk_validation_tooling", self.worker.call_args.kwargs)

    def test_metadata_admission_objects_forward_to_both_state_replays_only(self):
        admissions = {"sdk_facade_metadata_admission": object(), "sdk_android_metadata_admission": object()}
        self.invoke(**admissions)
        for name, value in admissions.items():
            for call in (self.verified.call_args, self.materialized.call_args):
                self.assertIs(value, call.kwargs[name])
            for call in (self.worker.call_args, self.binary_reader.call_args, self.gate.call_args):
                self.assertNotIn(name, call.kwargs)
            for path in self.destination.rglob("*"):
                if path.is_file():
                    self.assertNotIn(name.encode(), path.read_bytes(), str(path))

    def test_gate_rejection_and_context_exit_failures_never_publish(self):
        self.gate.side_effect = ValueError("full original lineage rejected")
        with self.assertRaisesRegex(ValueError, "lineage rejected"):
            self.invoke()
        self.assertFalse((self.destination / "shard").exists())
        self.assertTrue((self.destination / "worker/gradle.log").exists())
        self.publish.assert_not_called()

    def test_late_stage_copy_policy_and_candidate_mutation_reject(self):
        for name in ("stage", "copy", "policy", "candidate", "exception"):
            with self.subTest(name=name):
                fixture = MavenPackageWorkflowTest(methodName="runTest")
                fixture.setUp()
                try:
                    def mutate():
                        if name == "exception": raise ValueError("original context failed")
                        path = {"stage": fixture.package["stage"] / "outputs/artifact.bin",
                            "copy": fixture.destination / "sdk-inputs-original/original-upload.zip",
                            "policy": fixture.keyring,
                            "candidate": fixture.candidate / "phase-receipt.json"}[name]
                        path.write_bytes(b"changed")
                    fixture.exit_mutation = mutate
                    with self.assertRaises(ValueError): fixture.invoke()
                    self.assertFalse((fixture.destination / "shard").exists())
                    fixture.publish.assert_not_called()
                finally:
                    fixture.doCleanups()

    def test_missing_original_evidence_unselected_and_overlap_fail_before_worker(self):
        with self.assertRaises(ValueError): self.invoke(binary_contract_evidence={})
        with self.assertRaises(ValueError): self.invoke(component="sdk-ios")
        original_destination = self.destination
        self.destination = self.original_contract["stage"] / "worker"
        with self.assertRaisesRegex(ValueError, "overlaps"): self.invoke()
        self.destination = original_destination
        self.selection["consumers"] = []
        with self.assertRaisesRegex(ValueError, "not selected"): self.invoke()
        self.worker.assert_not_called()
        self.publish.assert_not_called()

    def test_final_checkout_failure_prevents_publication(self):
        self.checkout.side_effect = ValueError("tracked checkout changed")
        with self.assertRaisesRegex(ValueError, "checkout changed"): self.invoke()
        self.assertIn("closed", self.events)
        self.publish.assert_not_called()
        self.assertFalse((self.destination / "shard").exists())

    def test_retained_binary_mode_preserves_same_gates_without_observation(self):
        self.invoke(binary_artifact_id=None, binary_artifact_sha256=None, binary_capture_root=self.binary_capture)
        self.binary_reader.assert_not_called()
        self.retained_reader.assert_called_once()
        self.assertIn("binary-closed", self.events)

    def test_missing_mixed_or_partial_original_proof_fails_before_state_replay(self):
        for changes in ({"binary_artifact_id": None, "binary_artifact_sha256": None},
                        {"binary_capture_root": self.binary_capture},
                        {"binary_artifact_sha256": None}, {"binary_artifact_id": True},
                        {"binary_original_context": {}}, {"android_runtime_archive": self.android_archive}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.invoke(**changes)
        self.verified.assert_not_called()
        self.worker.assert_not_called()

    def test_original_binary_mismatch_rejects_before_package_consumption(self):
        @contextmanager
        def mismatch(*args, **kwargs):
            yield {**self.binary, "receiptBytes": b"different selected receipt", "capture": self.binary_capture}
        self.binary_reader.side_effect = mismatch
        with self.assertRaisesRegex(ValueError, "elected predecessor"):
            self.invoke()
        self.worker.assert_not_called()
        self.publish.assert_not_called()

    def test_binary_exit_failure_or_retained_mutation_never_publishes(self):
        for case in ("failure", "capture", "context"):
            with self.subTest(case=case):
                fixture = MavenPackageWorkflowTest(methodName="runTest")
                fixture.setUp()
                try:
                    def mutate():
                        if case == "failure":
                            raise ValueError("binary original reader exit failed")
                        path = fixture.destination / "binary-original" / (
                            "capture/transport.zip" if case == "capture" else "context.json")
                        path.write_bytes(b"changed")
                    fixture.binary_exit_mutation = mutate
                    with self.assertRaises(ValueError):
                        fixture.invoke()
                    self.assertFalse((fixture.destination / "shard").exists())
                    self.assertTrue((fixture.destination / "worker/gradle.log").exists())
                    fixture.publish.assert_not_called()
                finally:
                    fixture.doCleanups()

    def test_cli_canonical_evidence_policies_and_environment_token(self):
        evidence = self.root / "caller-evidence.json"
        write_canonical_json(evidence, self.evidence)
        context = self.root / "binary-context.json"
        write_canonical_json(context, self.binary_context)
        argv = []
        for name, value in {"plan": self.plan, "destination": self.destination, "keyring": self.keyring,
            "keys-directory": self.keys, "repository-root": self.root, "binary-contract-evidence": evidence,
            "discovery-root": self.discovery, "state-root": self.discovery, "component": "sdk-core",
            "expected-build-key": self.ready["buildKey"], "sdk-inputs-artifact-id": 3,
            "sdk-inputs-artifact-sha256": "sha256:" + "d" * 64, "trusted-workflow-sha": "e" * 40,
            "binary-original-context": context, "binary-artifact-id": 7,
            "binary-artifact-sha256": "sha256:" + "b" * 64}.items():
            argv.extend(["--" + name, str(value)])
        assert_metadata_cli_context(self, workflow, argv)
        with patch.object(workflow, "execute") as execute, patch.dict(workflow.os.environ, {"GITHUB_TOKEN": "env-token"}):
            self.assertEqual(0, workflow.main(argv))
            self.assertEqual(self.evidence, execute.call_args.kwargs["binary_contract_evidence"])
            self.assertEqual(self.binary_context, execute.call_args.kwargs["binary_original_context"])
            self.assertEqual(7, execute.call_args.kwargs["binary_artifact_id"])
            self.assertEqual("env-token", execute.call_args.kwargs["token"])
            self.assertNotIn("sdk_validation_tooling", execute.call_args.kwargs)
            for name in ("sdk_facade_metadata_admission", "sdk_android_metadata_admission"):
                self.assertNotIn(name, execute.call_args.kwargs)
            retained_argv = [item for name, value in zip(argv[::2], argv[1::2])
                             if name not in {"--binary-artifact-id", "--binary-artifact-sha256"}
                             for item in (name, value)]
            self.assertEqual(0, workflow.main([*retained_argv, "--binary-capture-root", str(self.binary_capture)]))
            self.assertEqual(self.binary_capture, execute.call_args.kwargs["binary_capture_root"])
            self.assertIsNone(execute.call_args.kwargs["binary_artifact_id"])
            policy = self.root / "caller-policy.json"
            write_canonical_json(policy, {"fixture": "caller-only"})
            self.assertEqual(0, workflow.main([*argv, "--sdk-validation-tooling", str(policy),
                                               "--sdk-apple-validation-policy", str(policy)]))
            self.assertEqual({"fixture": "caller-only"}, execute.call_args.kwargs["sdk_validation_tooling"])
            self.assertEqual({"fixture": "caller-only"}, execute.call_args.kwargs["sdk_apple_validation_policy"])
            for bad in ([*argv, "--token", "injected"], [*argv, "--component", "sdk-ios"],
                        ["--pl" if arg == "--plan" else arg for arg in argv],
                        [*argv, "--binary-capture-root", str(self.binary_capture)],
                        [*argv, "--sdk-facade-metadata-admission", "transport.json"],
                        [*argv, "--sdk-android-metadata-admission", "transport.json"],
                        argv[:-4], argv[:-2]):
                execute.reset_mock()
                with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit): workflow.main(bad)
                execute.assert_not_called()
            context.write_bytes(context.read_bytes() + b" ")
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit): workflow.main(argv)
            write_canonical_json(context, self.binary_context)
            evidence.write_bytes(evidence.read_bytes() + b" ")
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit): workflow.main(argv)


if __name__ == "__main__":
    unittest.main()
