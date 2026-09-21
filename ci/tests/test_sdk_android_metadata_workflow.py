"""Android metadata orchestration tests; native and hosted boundaries are mocked."""

from copy import deepcopy
from contextlib import contextmanager, redirect_stderr
import io
from pathlib import Path
import shutil
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from ci import sdk_android_metadata_workflow as workflow
from ci import sdk_android_firebase_original as firebase_reader
from ci import sdk_android_original_validation as original_reader
from ci.products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, regular_file_inventory,
    sha256_file, write_canonical_json,
)
from ci.products.plan import _upstream_record
from ci.products.receipt import output_inventory_digest, write_output_manifest
from ci.products.sdk_android_validation_content import android_validation_content
from ci.tests.product_chain_support import write_receipt


class AndroidMetadataWorkflowTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="android-metadata-workflow-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.discovery, self.state = self.root / "discovery", self.root / "state"
        self.discovery.mkdir(); self.state.mkdir()
        (self.discovery / "catalog").write_bytes(b"discovery")
        (self.state / "state").write_bytes(b"state")
        self.plan = self.root / "impact-plan.json"
        self.plan.write_bytes(b"plan")
        self.destination = self.root / "worker"
        self.version = "0.8.7"
        self.current = self.producer(3)
        self.validation_producer = self.producer(2)
        self.binary_producer = self.producer(1)
        self.metadata_plan = {"schemaVersion": 1, "product": "sdk", "component": "sdk-android",
            "phase": "metadata", "target": "android", "buildKey": "sha256:" + "d" * 64,
            "inputs": {}}
        self.package_stage = self.root / "caller/package"
        self.binary_stage = self.root / "caller/binary"
        for stage, phase, raw in ((self.package_stage, "package", b"package"),
                                  (self.binary_stage, "binary", b"binary")):
            payload = stage / "outputs/payload.bin"
            payload.parent.mkdir(parents=True)
            payload.write_bytes(raw)
            write_output_manifest(stage, "sdk", "sdk-android", phase, "android", self.version,
                                  {"maven": "outputs"})
        self.package_receipt = self.root / "caller/package.json"
        self.binary_receipt = self.root / "caller/binary.json"
        self.package = self.receipt(self.package_stage, self.package_receipt, "package", self.binary_producer)
        self.binary = self.receipt(self.binary_stage, self.binary_receipt, "binary", self.binary_producer)
        self.validation_content = android_validation_content(
            sdk_version=self.version, package_outputs_digest=output_inventory_digest(
                self.package["outputs"]), release_aar_sha256="sha256:" + "a" * 64,
            bundled_runtime_sha256="sha256:" + "b" * 64)
        self.validation_stage = self.root / "validation-stage"
        content = self.validation_stage / workflow.validation_phase.OUTPUT_PATH
        content.parent.mkdir(parents=True)
        content.write_bytes(canonical_json_bytes(self.validation_content))
        manifest = write_output_manifest(
            self.validation_stage, "sdk", "sdk-android", "validation", "android", self.version,
            {workflow.validation_phase.OUTPUT_KIND: "outputs/validation"},
            expected_output_paths=[workflow.validation_phase.OUTPUT_PATH])
        self.validation_receipt = self.root / "validation.json"
        self.validation = write_receipt(
            self.validation_receipt, product="sdk", component="sdk-android", phase="validation",
            target="android", version=self.version, version_identity=self.version,
            outputs=manifest["outputs"], upstream=[_upstream_record(self.package)],
            context={"producer": self.validation_producer})
        self.original = self.root / "original-validation"
        for name in ("inputs", "originals/final", "originals/protected",
                     "originals/validation-inputs", "shard"):
            (self.original / name).mkdir(parents=True)
        shutil.copytree(self.validation_stage, self.original / "stage")
        (self.original / "shard/phase-receipt.json").write_bytes(self.validation_receipt.read_bytes())
        write_canonical_json(self.original / "inputs/phase-plan.json",
            {name: self.validation[name] for name in workflow.PHASE_PLAN_KEYS})
        write_canonical_json(self.original / "inputs/producer.json", self.validation_producer)
        for phase, stage, receipt in (("package", self.package_stage, self.package_receipt),
                                      ("binary", self.binary_stage, self.binary_receipt)):
            selected = self.original / f"inputs/sdk-sdk-android-{phase}-android"
            shutil.copytree(stage, selected / "stage")
            (selected / "phase-receipt.json").write_bytes(receipt.read_bytes())
        (self.original / "originals/final/evidence").write_bytes(b"final")
        (self.original / "originals/protected/evidence").write_bytes(b"protected")
        self.compatibility = self.root / "caller/compatibility.json"
        self.compatibility.write_bytes(b"compatibility")
        (self.original / "originals/validation-inputs/original-compatibility-request.json").write_bytes(
            b"historical request with original absolute paths")
        self.contract_stage = self.root / "caller/contract-stage"
        self.contract_stage.mkdir(parents=True)
        (self.contract_stage / "contract").write_bytes(b"contract")
        self.contract = self.root / "caller/contract"
        self.contract.mkdir()
        for name in ("receipt.json", "attestation.json", "signature", "public.pub"):
            (self.contract / name).write_bytes(name.encode())
        closure = self.contract / workflow.validation_phase.CONTRACT_EXECUTION_CLOSURE_DIRECTORY
        closure.mkdir(); (closure / "closure").write_bytes(b"closure")
        self.contract_evidence = {"stageRoot": str(self.contract_stage),
            "phaseReceipt": str(self.contract / "receipt.json"),
            "attestation": str(self.contract / "attestation.json"),
            "attestationSignature": str(self.contract / "signature"),
            "publicKey": str(self.contract / "public.pub"), "expectedTrustDomain": "development",
            "keyring": None, "keysDirectory": None}
        retained = self.original / "originals/validation-inputs"
        sdk_inputs = retained / "sdk-inputs"
        sdk_inputs.mkdir()
        for name, raw in (("sdk-compatibility-request.json", b"compatibility"),
                          ("sdk-compatibility.json", b"derived"),
                          ("sdk-inputs-inventory.json", b"inventory")):
            (sdk_inputs / name).write_bytes(raw)
        captured_contract = retained / "contract"
        shutil.copytree(self.contract_stage, captured_contract / "stage")
        (captured_contract / "phase-receipt.json").write_bytes((self.contract / "receipt.json").read_bytes())
        for field, source in (("attestation", self.contract / "attestation.json"),
                              ("signature", self.contract / "signature"),
                              ("public-key", self.contract / "public.pub")):
            target = captured_contract / "auth" / field / source.name
            target.parent.mkdir(parents=True)
            target.write_bytes(source.read_bytes())
        shutil.copytree(closure, captured_contract / "auth/attestation" /
                        workflow.validation_phase.CONTRACT_EXECUTION_CLOSURE_DIRECTORY)
        write_canonical_json(retained / "binary-contract-invocation.json", {
            **self.contract_evidence, "stageRoot": "/historical/contract/stage",
            "phaseReceipt": "/historical/contract/phase-receipt.json",
            "attestation": "/historical/contract/auth/attestation/attestation.json",
            "attestationSignature": "/historical/contract/auth/signature/signature",
            "publicKey": "/historical/contract/auth/public-key/public.pub",
        })
        self.original_capture = self.root / "original-validation-capture"
        shutil.copytree(self.original, self.original_capture / "original")
        (self.original_capture / "plan").mkdir()
        (self.original_capture / "plan/impact-plan.json").write_bytes(self.plan.read_bytes())
        (self.original_capture / "transport.zip").write_bytes(b"authenticated transport fixture")
        write_canonical_json(self.original_capture / "capture-transport.json", {
            "artifact": {"id": 1}, "captureProducer": self.validation_producer,
            "observed": [], "validationReceiptSha256": sha256_file(self.validation_receipt),
        })
        self.tooling = self.root / "caller/tooling"; self.tooling.mkdir()
        (self.tooling / "evidence").write_bytes(b"tooling")
        self.tooling_key = self.root / "caller/tooling.pub"; self.tooling_key.write_bytes(b"key")
        self.java = self.root / "caller/java"; self.java.write_bytes(b"java")
        self.analyzer = self.root / "caller/apkanalyzer"; self.analyzer.write_bytes(b"analyzer")
        self.events = []
        self.reader_arguments = None
        self.reader_enter_failure = self.reader_exit_failure = None
        self.reader_stage = None
        self.arguments = dict(expected_build_key=self.metadata_plan["buildKey"],
            original_validation_capture=self.original_capture, package_stage=self.package_stage,
            package_receipt=self.package_receipt, binary_stage=self.binary_stage,
            binary_receipt=self.binary_receipt, compatibility_request=self.compatibility,
            binary_contract_evidence=self.contract_evidence, trusted_source_commit="e" * 40,
            trusted_source_tree="f" * 40, tooling_evidence=self.tooling,
            tooling_public_key=self.tooling_key, java_executable=self.java,
            apkanalyzer_executable=self.analyzer, policy_revision="1" * 40,
            required_trust_domain="development", repository_root=self.root,
            environ={"GITHUB_RUN_ID": "9", "GITHUB_RUN_ATTEMPT": "3"})

    def stage_inputs(self, request, destination, **kwargs):
        destination.mkdir(parents=True)
        for name, raw in (("sdk-compatibility-request.json", b"compatibility"),
                          ("sdk-compatibility.json", b"derived"),
                          ("sdk-inputs-inventory.json", b"inventory")):
            (destination / name).write_bytes(raw)

    def producer(self, attempt):
        return {"repository": "codex-agent-labs/codex-agent",
            "workflowPath": ".github/workflows/ci.yml", "commit": "a" * 40,
            "tree": "b" * 40, "event": "pull_request", "runId": 9,
            "runAttempt": attempt, "pullRequest": 4}

    def receipt(self, stage, path, phase, producer):
        manifest = workflow.verify_output_manifest_identity(
            stage, "sdk", "sdk-android", phase, "android", self.version)
        return write_receipt(path, product="sdk", component="sdk-android", phase=phase,
            target="android", version=self.version, version_identity=self.version,
            outputs=manifest["outputs"], upstream=[], context={"producer": producer})

    def verified_state(self, *args, **kwargs):
        self.events.append("state")
        return SimpleNamespace(prior_ready_plans={workflow._INSTANCE: deepcopy(self.metadata_plan)},
            producer=deepcopy(self.current), expected_fixed={"versions": {"sdk": self.version}})

    def materialize(self, plan, discovery, state, instance, destination, **kwargs):
        self.events.append("materialize")
        destination.mkdir(parents=True)
        selected = destination / "sdk-sdk-android-validation-android"
        shutil.copytree(self.validation_stage, selected / "stage")
        (selected / "phase-receipt.json").write_bytes(self.validation_receipt.read_bytes())
        write_canonical_json(destination / "phase-plan.json", self.metadata_plan)
        write_canonical_json(destination / "producer.json", self.current)
        return deepcopy(self.metadata_plan)

    @contextmanager
    def verified_reader(self, plan, receipt, **kwargs):
        self.events.append("reader-enter")
        self.reader_arguments = kwargs
        self.assertEqual(self.plan, plan)
        self.assertEqual(self.validation_receipt.read_bytes(), Path(receipt).read_bytes())
        if "validation_capture" in kwargs:
            self.assertEqual(self.original_capture, kwargs["validation_capture"])
        else:
            self.assertEqual(17, kwargs["validation_artifact_id"])
            self.assertEqual("sha256:" + "7" * 64,
                             kwargs["validation_artifact_sha256"])
            self.assertEqual("8" * 40, kwargs["trusted_workflow_sha"])
            self.assertEqual("9" * 40, kwargs["trusted_android_workflow_sha"])
            self.assertEqual(self.validation_producer["runId"],
                             kwargs["expected_original_run_id"])
            self.assertEqual(self.validation_producer["runAttempt"],
                             kwargs["expected_original_run_attempt"])
            self.assertEqual("observation-token", kwargs["token"])
        if self.reader_enter_failure is not None:
            raise self.reader_enter_failure
        selected = Path(receipt).parent
        try:
            yield {"stage": self.reader_stage or selected / "stage",
                "receiptPath": Path(receipt), "receiptBytes": Path(receipt).read_bytes(),
                "receipt": deepcopy(self.validation), "capture": self.original_capture}
        finally:
            self.events.append("reader-exit")
            if self.reader_exit_failure is not None:
                raise self.reader_exit_failure

    def execute_metadata(self, plan, **kwargs):
        self.events.append("execute")
        stage = self.root / "build/product-stage/sdk/sdk-android/metadata/android"
        output = stage / workflow.OUTPUT_PATH
        output.parent.mkdir(parents=True)
        result = workflow.write_android_metadata_content(kwargs["request"], output)
        write_output_manifest(stage, "sdk", "sdk-android", "metadata", "android", self.version,
            {workflow.OUTPUT_KIND: "outputs/evidence"}, expected_output_paths=[workflow.OUTPUT_PATH])
        diagnostics = kwargs["destination"]; diagnostics.mkdir(parents=True)
        (diagnostics / "execution.json").write_bytes(b"diagnostics")
        return {"stage": stage, "content": output,
            "outputInventory": regular_file_inventory(stage), "diagnostics": diagnostics}

    def finalize(self, **kwargs):
        self.events.append("finalize")
        kwargs["destination"].mkdir()
        (kwargs["destination"] / "phase-receipt.json").write_bytes(b"final")
        return {"receipt": {"buildKey": self.metadata_plan["buildKey"]}}

    def call(self, **changes):
        shard = {"receiptBytes": self.validation_receipt.read_bytes(),
            "objectPath": "objects/object.zip", "buildKey": self.validation["buildKey"],
            "receiptSha256": sha256_file(self.validation_receipt), "objectSha256": "sha256:" + "0" * 64}
        finalized = {"receipt": {"buildKey": self.metadata_plan["buildKey"]}}
        def verify_shard(root, instance):
            return shard if instance == workflow._VALIDATION else deepcopy(finalized)
        with patch.object(workflow, "_request_inventory",
                          side_effect=lambda path: {Path(path): sha256_file(Path(path))}), \
                patch.object(workflow.product_reuse, "_verified_product_state", side_effect=self.verified_state), \
                patch.object(workflow.product_reuse, "materialize_product_predecessors", side_effect=self.materialize), \
                patch.object(workflow, "verify_phase_shard", side_effect=verify_shard), \
                patch.object(original_reader, "verified_retained_android_validation",
                             side_effect=self.verified_reader), \
                patch.object(firebase_reader, "verified_original_android_firebase_validation",
                             side_effect=self.verified_reader), \
                patch.object(workflow, "_execute_metadata", side_effect=self.execute_metadata), \
                patch.object(workflow.product_reuse, "_runtime_worker_checkout"), \
                patch.object(workflow.product_reuse, "finalize_phase_object", side_effect=self.finalize):
            return workflow.execute(self.plan, self.discovery, self.state,
                changes.pop("destination", self.destination), **{**self.arguments, **changes})

    def test_verified_original_reader_exits_before_metadata_final_receipt(self):
        result = self.call()
        self.assertEqual(["state", "materialize", "reader-enter", "execute", "reader-exit",
                          "finalize"], self.events)
        self.assertEqual(self.package_stage, self.reader_arguments["package_stage"])
        self.assertEqual(self.contract_evidence, self.reader_arguments["binary_contract_evidence"])
        self.assertEqual(regular_file_inventory(self.original_capture),
                         regular_file_inventory(result["originals"] / "validation"))
        request = load_canonical_json_bytes((self.destination / "metadata-request.json").read_bytes())
        self.assertEqual((self.validation_content["releaseAarSha256"],
                          self.validation_content["bundledRuntimeSha256"]),
                         (request["releaseAarSha256"], request["bundledRuntimeSha256"]))

    def test_observed_original_reader_uses_explicit_caller_pins_and_run(self):
        result = self.call(
            original_validation_capture=None,
            validation_artifact_id=17,
            validation_artifact_sha256="sha256:" + "7" * 64,
            trusted_workflow_sha="8" * 40,
            trusted_android_workflow_sha="9" * 40,
            expected_original_run_id=self.validation_producer["runId"],
            expected_original_run_attempt=self.validation_producer["runAttempt"],
            token="observation-token")
        self.assertEqual(["state", "materialize", "reader-enter", "execute", "reader-exit",
                          "finalize"], self.events)
        self.assertEqual(self.package_stage, self.reader_arguments["package_stage"])
        self.assertEqual(regular_file_inventory(self.original_capture),
                         regular_file_inventory(result["originals"] / "validation"))

    def test_original_reader_modes_are_complete_and_mutually_exclusive(self):
        cases = (
            {"original_validation_capture": None},
            {"validation_artifact_id": 17},
            {"original_validation_capture": None, "validation_artifact_id": 17},
            {"validation_artifact_id": 17,
             "validation_artifact_sha256": "sha256:" + "7" * 64,
             "trusted_workflow_sha": "8" * 40,
             "trusted_android_workflow_sha": "9" * 40,
             "expected_original_run_id": 9,
             "expected_original_run_attempt": 2},
        )
        for index, changes in enumerate(cases):
            self.events.clear()
            with self.subTest(index=index), self.assertRaisesRegex(
                    ValueError, "exactly one complete original validation mode"):
                self.call(destination=self.root / f"invalid-mode-{index}", **changes)
            self.assertNotIn("state", self.events)
        observed = dict(
            original_validation_capture=None, validation_artifact_id=17,
            validation_artifact_sha256="sha256:" + "7" * 64,
            trusted_workflow_sha="8" * 40, trusted_android_workflow_sha="9" * 40,
            expected_original_run_id=9, expected_original_run_attempt=2, token="")
        with self.assertRaisesRegex(ValueError, "observation token"):
            self.call(destination=self.root / "missing-token", **observed)
        self.assertNotIn("state", self.events)

    def test_observed_reader_failure_or_exit_never_publishes(self):
        observed = dict(
            original_validation_capture=None, validation_artifact_id=17,
            validation_artifact_sha256="sha256:" + "7" * 64,
            trusted_workflow_sha="8" * 40, trusted_android_workflow_sha="9" * 40,
            expected_original_run_id=9, expected_original_run_attempt=2,
            token="observation-token")
        self.reader_enter_failure = ValueError("official observation rejected")
        destination = self.root / "observed-enter-failure"
        with self.assertRaisesRegex(ValueError, "official observation rejected"):
            self.call(destination=destination, **observed)
        self.assertNotIn("finalize", self.events)
        self.assertFalse((destination / "shard").exists())
        self.events.clear()
        self.reader_enter_failure = None
        self.reader_exit_failure = ValueError("official observation changed")
        destination = self.root / "observed-exit-failure"
        with self.assertRaisesRegex(ValueError, "official observation changed"):
            self.call(destination=destination, **observed)
        self.assertNotIn("finalize", self.events)
        self.assertFalse((destination / "shard").exists())

    def test_gate_failure_or_late_original_mutation_never_finalizes(self):
        self.reader_enter_failure = ValueError("full replay failed")
        with self.assertRaisesRegex(ValueError, "full replay failed"):
            self.call(destination=self.root / "failure")
        self.assertNotIn("finalize", self.events)
        self.events.clear()
        self.reader_enter_failure = None
        original_execute = self.execute_metadata
        def mutate(*args, **kwargs):
            result = original_execute(*args, **kwargs)
            (self.original_capture / "original/originals/final/evidence").write_bytes(b"changed")
            return result
        with patch.object(self, "execute_metadata", side_effect=mutate), \
                self.assertRaisesRegex(ValueError, "changed"):
            self.call(destination=self.root / "mutation")
        self.assertNotIn("finalize", self.events)

        self.events.clear()
        def fail_after_mutation(*args, **kwargs):
            (self.original_capture / "original/originals/final/evidence").write_bytes(b"failed mutation")
            raise ValueError("worker failed")
        with patch.object(self, "execute_metadata", side_effect=fail_after_mutation), \
                self.assertRaisesRegex(ValueError, "changed"):
            self.call(destination=self.root / "failed-mutation")
        self.assertNotIn("finalize", self.events)
        self.assertFalse((self.root / "failed-mutation/shard").exists())

    def test_reader_exit_must_succeed_before_finalization(self):
        self.reader_exit_failure = ValueError("reader exit rejected")
        destination = self.root / "reader-exit-failure"
        with self.assertRaisesRegex(ValueError, "reader exit rejected"):
            self.call(destination=destination)
        self.assertNotIn("finalize", self.events)
        self.assertFalse((destination / "shard").exists())

    def test_reader_stage_must_equal_selected_predecessor(self):
        self.reader_stage = self.root / "different-validation-stage"
        shutil.copytree(self.validation_stage, self.reader_stage)
        (self.reader_stage / workflow.validation_phase.OUTPUT_PATH).write_bytes(b"different")
        with self.assertRaisesRegex(ValueError, "differs from selected predecessor"):
            self.call()
        self.assertNotIn("execute", self.events)

    def test_finalizer_mutation_does_not_publish_candidate(self):
        finalize = self.finalize
        def mutate(**kwargs):
            result = finalize(**kwargs)
            (kwargs["stage_root"] / workflow.OUTPUT_PATH).write_bytes(b"changed")
            return result
        destination = self.root / "finalizer-mutation"
        with patch.object(self, "finalize", side_effect=mutate), \
                self.assertRaisesRegex(ValueError, "candidate or output changed"):
            self.call(destination=destination)
        self.assertFalse((destination / "shard").exists())

    def test_late_elected_plan_mutation_rejects_before_finalization(self):
        original_execute = self.execute_metadata
        def mutate(plan, **kwargs):
            result = original_execute(plan, **kwargs)
            plan["buildKey"] = "sha256:" + "9" * 64
            return result
        with patch.object(self, "execute_metadata", side_effect=mutate), \
                self.assertRaisesRegex(ValueError, "changed"):
            self.call()
        self.assertNotIn("finalize", self.events)

    def test_product_stage_must_be_disjoint_from_every_original_source(self):
        overlapping = self.root / "build/product-stage/sdk/sdk-android/metadata/android/source"
        shutil.copytree(self.package_stage, overlapping)
        with self.assertRaisesRegex(ValueError, "overlap"):
            self.call(package_stage=overlapping)
        self.assertNotIn("state", self.events)

    def test_fixed_gradle_metadata_mapping_and_raw_failure(self):
        request = self.root / "metadata-request.json"
        write_canonical_json(request, {"sdkVersion": self.version,
            "packageStage": str(self.package_stage), "packageReceipt": str(self.package_receipt),
            "validationStage": str(self.validation_stage), "validationReceipt": str(self.validation_receipt),
            "releaseAarSha256": self.validation_content["releaseAarSha256"],
            "bundledRuntimeSha256": self.validation_content["bundledRuntimeSha256"]})
        captured = {}
        def command(wrapper, fields, environment, **kwargs):
            captured.update(fields)
            return ["./gradlew", "ciProductPhase"]
        def process(*args, **kwargs):
            stage = self.root / "build/product-stage/sdk/sdk-android/metadata/android"
            output = stage / workflow.OUTPUT_PATH
            output.parent.mkdir(parents=True)
            workflow.write_android_metadata_content(request, output)
            write_output_manifest(stage, "sdk", "sdk-android", "metadata", "android", self.version,
                {workflow.OUTPUT_KIND: "outputs/evidence"}, expected_output_paths=[workflow.OUTPUT_PATH])
            return SimpleNamespace(returncode=0)
        with patch.object(workflow.product_reuse, "_runtime_worker_environment",
                          return_value=({}, self.root / "gradlew")), \
                patch.object(workflow.product_reuse, "_runtime_worker_command", side_effect=command), \
                patch.object(workflow.product_reuse, "_runtime_worker_checkout"), \
                patch.object(workflow.subprocess, "run", side_effect=process):
            result = workflow._execute_metadata(self.metadata_plan, producer=self.current,
                sdk_version=self.version, request=request, repository_root=self.root,
                destination=self.root / "diagnostics", environ={})
        self.assertEqual(str(request), captured["codexAgent.sdkAndroidMetadataRequest"])
        self.assertEqual(workflow.OUTPUT_PATH, result["content"].relative_to(result["stage"]).as_posix())

    def test_cli_forwards_strict_paths_and_canonical_contract(self):
        contract = self.root / "contract.json"; write_canonical_json(contract, self.contract_evidence)
        argv = []
        paths = {"plan": self.plan, "discovery-root": self.discovery, "state-root": self.state,
            "destination": self.destination, "original-validation-capture": self.original_capture,
            "package-stage": self.package_stage, "package-receipt": self.package_receipt,
            "binary-stage": self.binary_stage, "binary-receipt": self.binary_receipt,
            "compatibility-request": self.compatibility, "binary-contract-evidence": contract,
            "tooling-evidence": self.tooling, "tooling-public-key": self.tooling_key,
            "java-executable": self.java, "apkanalyzer-executable": self.analyzer,
            "repository-root": self.root}
        values = {"expected-build-key": self.metadata_plan["buildKey"],
            "trusted-source-commit": "e" * 40, "trusted-source-tree": "f" * 40,
            "policy-revision": "1" * 40, "required-trust-domain": "development"}
        for name, value in {**paths, **values}.items():
            argv.extend(("--" + name, str(value)))
        with patch.object(workflow, "execute") as execute:
            self.assertEqual(0, workflow.main(argv))
        self.assertEqual(self.discovery, execute.call_args.kwargs["discovery"])
        self.assertEqual(self.state, execute.call_args.kwargs["state"])
        self.assertEqual(self.original_capture,
                         execute.call_args.kwargs["original_validation_capture"])
        self.assertEqual(self.contract_evidence, execute.call_args.kwargs["binary_contract_evidence"])
        observed_argv = [value for pair in zip(argv[::2], argv[1::2])
                         if pair[0] != "--original-validation-capture" for value in pair]
        for name, value in {
            "validation-artifact-id": 17,
            "validation-artifact-sha256": "sha256:" + "7" * 64,
            "trusted-workflow-sha": "8" * 40,
            "trusted-android-workflow-sha": "9" * 40,
            "expected-original-run-id": 9,
            "expected-original-run-attempt": 2,
        }.items():
            observed_argv.extend(("--" + name, str(value)))
        with patch.dict(workflow.os.environ, {"GITHUB_TOKEN": "observation-token"}), \
                patch.object(workflow, "execute") as observed_execute:
            self.assertEqual(0, workflow.main(observed_argv))
        self.assertIsNone(observed_execute.call_args.kwargs["original_validation_capture"])
        self.assertEqual(17, observed_execute.call_args.kwargs["validation_artifact_id"])
        self.assertEqual("observation-token", observed_execute.call_args.kwargs["token"])
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            workflow.main([*argv, "--unknown"])
        self.assertEqual(2, error.exception.code)


if __name__ == "__main__":
    unittest.main()
