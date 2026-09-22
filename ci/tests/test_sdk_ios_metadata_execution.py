"""iOS metadata orchestration tests; mocked handoffs are not Apple admission proof."""

from contextlib import contextmanager, redirect_stderr
import io
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from ci import sdk_ios_metadata_workflow as workflow
from ci.products.receipt import write_output_manifest


class SdkIosMetadataExecutionTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sdk-ios-metadata-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.plan = self.root / "impact-plan.json"
        self.plan.write_bytes(b'{"synthetic":"current plan"}\n')
        self.discovery, self.state = self.root / "discovery", self.root / "state"
        self.discovery.mkdir()
        self.state.mkdir()
        self.destination = self.root / "result"
        self.ready = {"schemaVersion": 1, "product": "sdk", "component": "sdk-ios",
                      "phase": "metadata", "target": "ios", "buildKey": "sha256:" + "1" * 64,
                      "inputs": []}
        self.producer = {"repository": "codex-agent-labs/codex-agent",
            "workflowPath": ".github/workflows/ci.yml", "commit": "a" * 40, "tree": "b" * 40,
            "event": "pull_request", "runId": 19, "runAttempt": 2, "pullRequest": 7}
        self.version = "0.8.0"
        policy_root = self.root / "policy"
        for name in ("product-keys", "tooling", "tooling-keys"):
            (policy_root / name).mkdir(parents=True)
            (policy_root / name / "retained.bin").write_bytes(name.encode())
        for name in ("product-keyring.json", "tooling.pub", "java", "tooling-keyring.json"):
            (policy_root / name).write_bytes((name + "\n").encode())
        self.policy = {"plan": str(self.plan), "attestationPublicKey": None,
            "attestationTrustDomain": "release", "keyring": str(policy_root / "product-keyring.json"),
            "keysDirectory": str(policy_root / "product-keys"),
            "toolingEvidence": str(policy_root / "tooling"),
            "toolingPublicKey": str(policy_root / "tooling.pub"),
            "javaExecutable": str(policy_root / "java"), "toolingTrustDomain": "release",
            "toolingKeyring": str(policy_root / "tooling-keyring.json"),
            "toolingKeysDirectory": str(policy_root / "tooling-keys")}
        self.receipts = {}
        self.records = []
        for index, target in enumerate(workflow._TARGETS):
            receipt = {"product": "sdk", "component": "sdk-ios", "phase": "validation",
                "target": target, "productVersion": self.version,
                "outputs": [{"kind": "apple-validation-content",
                    "relativePath": "outputs/validation/apple-validation.json",
                    "sha256": "sha256:" + str(index + 2) * 64}], "producer": self.producer}
            raw = workflow.canonical_json_bytes(receipt)
            self.receipts[target] = (receipt, raw)
            self.records.append({"receiptSha256": workflow.sha256_bytes(raw), "target": target,
                "evidenceRoot": f"evidence/{target}/originals/{workflow.sha256_bytes(raw)[7:]}"})
        self.records.sort(key=lambda row: row["receiptSha256"])
        self.verified = SimpleNamespace(prior_ready_plans={workflow._INSTANCE: self.ready},
            expected_fixed={"versions": {"sdk": self.version}}, producer=self.producer,
            rebased_request={"repositoryRevision": self.producer["commit"],
                             "sdkAppleValidationEvidence": self.records})
        self.expected = {"schemaVersion": 1, "kind": "sdk-apple-metadata-content",
                         "component": "sdk-ios", "sdkVersion": self.version, "synthetic": "joined"}
        self.package = self.root / "private/package"
        self.package.mkdir(parents=True)
        (self.package / "package.bin").write_bytes(b"authenticated package")
        self.validation_contents = {}
        for target in workflow._TARGETS:
            path = self.root / "private" / target / "apple-validation.json"
            path.parent.mkdir(parents=True)
            path.write_bytes(workflow.canonical_json_bytes({"target": target}))
            self.validation_contents[target] = path
        self.stage = self.root / "generated-stage"
        self.events = []
        self.admissions = {}
        self.mutation = None

    def assert_admissions(self, options):
        actual = {name: options[name] for name in (
            "sdk_facade_metadata_admission", "sdk_android_metadata_admission") if name in options}
        self.assertEqual(set(self.admissions), set(actual))
        for name, value in self.admissions.items():
            self.assertIs(value, actual[name])

    def verified_state(self, *args, **options):
        self.assert_admissions(options)
        return self.verified

    def materialize(self, plan, discovery, state, instance, destination, **options):
        self.assertEqual(workflow._INSTANCE, instance)
        self.assertEqual(self.ready["buildKey"], options["expected_build_key"])
        self.assertEqual(self.policy, options["sdk_apple_validation_policy"])
        self.assert_admissions(options)
        destination.mkdir(parents=True)
        (destination / "producer.json").write_bytes(workflow.canonical_json_bytes(self.producer))
        for target in workflow._TARGETS:
            directory = destination / f"sdk-sdk-ios-validation-{target}"
            (directory / "stage").mkdir(parents=True)
            (directory / "stage/output-manifest.json").write_bytes(b"synthetic manifest")
            (directory / "phase-receipt.json").write_bytes(self.receipts[target][1])
        if self.mutation == "election-materialize":
            self.ready["target"] = "changed-after-election"
        return dict(self.ready)

    @contextmanager
    def originals(self, **arguments):
        self.events.append("full-enter")
        self.assertEqual(self.root, arguments["repository"])
        self.assertEqual(self.root, arguments["evidence_root"])
        self.assertEqual(self.records, arguments["evidence_records"])
        self.assertEqual(self.producer["commit"], arguments["policy_revision"])
        self.assertEqual(self.policy, arguments["policy"])
        for target, path in arguments["validation_receipts"].items():
            self.assertEqual(self.receipts[target][1], path.read_bytes())
        yield {"package_stage": self.package, "package_receipt": {"synthetic": "package"},
            "package_receipt_bytes": b"package", "validation_contents": self.validation_contents,
            "validation_receipts": {target: value[0] for target, value in self.receipts.items()},
            "validation_receipt_bytes": {target: value[1] for target, value in self.receipts.items()},
            "content": dict(self.expected)}
        self.events.append("full-exit")
        if self.mutation == "context-exit":
            raise ValueError("full Apple context changed")
        if self.mutation == "predecessor-exit":
            prepared = self.destination / "inputs/sdk-sdk-ios-validation-ios-arm64/phase-receipt.json"
            prepared.write_bytes(b"changed")
        if self.mutation == "diagnostics-exit":
            (self.destination / "worker/execution.json").write_bytes(b"changed")

    def worker(self, plan, **arguments):
        self.events.append("worker")
        self.assertEqual(["full-enter", "worker"], self.events)
        self.assertEqual(self.package, arguments["package_stage"])
        self.assertEqual(self.validation_contents, arguments["validation_contents"])
        self.stage.mkdir()
        content = self.stage / workflow.OUTPUT_PATH
        content.parent.mkdir(parents=True)
        value = {**self.expected, **({"changed": True} if self.mutation == "content" else {})}
        content.write_bytes(workflow.canonical_json_bytes(value))
        diagnostics = self.destination / "worker"
        diagnostics.mkdir(parents=True)
        (diagnostics / "execution.json").write_bytes(b"worker execution")
        (diagnostics / "gradle.log").write_bytes(b"worker log")
        return {"stage": self.stage, "content": content,
                "outputInventory": workflow.regular_file_inventory(self.stage),
                "diagnostics": diagnostics}

    def finalize(self, **arguments):
        self.assertEqual("full-exit", self.events[-1])
        self.events.append("finalize")
        destination = arguments["destination"]
        destination.mkdir()
        receipt = {**self.ready, "producer": self.producer, "productVersion": self.version,
                   "trustDomain": "development", "outputs": []}
        raw = workflow.canonical_json_bytes(receipt)
        (destination / workflow.PHASE_RECEIPT_NAME).write_bytes(raw)
        (destination / "object.zip").write_bytes(b"candidate object")
        return {"receipt": receipt, "receiptBytes": raw, "receiptSha256": workflow.sha256_bytes(raw),
                "objectPath": "object.zip", "objectSha256": workflow.sha256_bytes(b"candidate object"),
                "buildKey": self.ready["buildKey"]}

    def admit(self, **arguments):
        self.assertEqual("finalize", self.events[-1])
        self.events.append("admit")
        if self.mutation == "admission":
            raise ValueError("candidate metadata rejected")
        if self.mutation == "diagnostics-admission":
            (self.destination / "worker/gradle.log").write_bytes(b"changed")
        raw = arguments["metadata_receipt"].read_bytes()
        return workflow.load_canonical_json_bytes(raw), raw

    def verify_shard(self, path, instance):
        self.assertEqual(workflow._INSTANCE, instance)
        raw = (path / workflow.PHASE_RECEIPT_NAME).read_bytes()
        receipt = workflow.load_canonical_json_bytes(raw)
        return {"receipt": receipt, "receiptBytes": raw, "receiptSha256": workflow.sha256_bytes(raw),
                "objectPath": "object.zip", "objectSha256": workflow.sha256_bytes(
                    (path / "object.zip").read_bytes()), "buildKey": receipt["buildKey"]}

    def run_controller(self, **changes):
        self.admissions = {name: changes[name] for name in (
            "sdk_facade_metadata_admission", "sdk_android_metadata_admission") if name in changes}
        with patch.object(workflow.product_reuse, "_verified_product_state", side_effect=self.verified_state), \
                patch.object(workflow.product_reuse, "materialize_product_predecessors", side_effect=self.materialize), \
                patch.object(workflow.product_reuse, "_canonical_control", return_value=self.producer), \
                patch.object(workflow.product_reuse, "validate_phase_receipt", side_effect=lambda value: value), \
                patch.object(workflow, "verify_output_manifest_identity",
                    side_effect=lambda stage, *identity: {"outputs": self.receipts[identity[3]][0]["outputs"]}), \
                patch.object(workflow.product_reuse, "_retained_apple_handoffs", return_value=[]), \
                patch.object(workflow, "verified_sdk_apple_metadata_inputs", side_effect=self.originals), \
                patch.object(workflow, "_execute_metadata", side_effect=self.worker), \
                patch.object(workflow.product_reuse, "_runtime_worker_checkout"), \
                patch.object(workflow.product_reuse, "finalize_phase_object", side_effect=self.finalize), \
                patch.object(workflow, "verify_sdk_apple_metadata_admission", side_effect=self.admit), \
                patch.object(workflow, "verify_phase_shard", side_effect=self.verify_shard):
            return workflow.execute(self.plan, self.discovery, self.state, self.destination,
                expected_build_key=self.ready["buildKey"], repository_root=self.root,
                environ={}, sdk_apple_validation_policy=self.policy, **changes)

    def test_two_full_original_gates_exit_before_final_receipt_and_publication(self):
        result = self.run_controller()
        self.assertEqual(["full-enter", "worker", "full-exit", "finalize", "admit"], self.events)
        self.assertEqual(self.ready["buildKey"], result["buildKey"])
        self.assertTrue((self.destination / "shard/phase-receipt.json").is_file())
        self.assertEqual(self.records, self.verified.rebased_request["sdkAppleValidationEvidence"])

    def test_metadata_admissions_reach_state_and_materializer_without_serialization(self):
        admissions = {"sdk_facade_metadata_admission": object(),
                      "sdk_android_metadata_admission": object()}
        result = self.run_controller(**admissions)
        self.assertEqual(self.ready["buildKey"], result["buildKey"])
        for path in (self.destination / "worker/execution.json", self.stage / workflow.OUTPUT_PATH):
            raw = path.read_bytes()
            for name in admissions:
                self.assertNotIn(name.encode(), raw)

    def test_context_exit_predecessor_content_and_candidate_admission_fail_without_shard(self):
        for mutation, message in (("context-exit", "full Apple"), ("predecessor-exit", "predecessors changed"),
                                  ("content", "producer differs"), ("admission", "metadata rejected"),
                                  ("diagnostics-exit", "output changed"),
                                  ("diagnostics-admission", "candidate changed")):
            self.mutation = mutation
            with self.subTest(mutation=mutation), self.assertRaisesRegex(ValueError, message):
                self.run_controller()
            self.assertFalse((self.destination / "shard").exists())
            if self.destination.exists():
                import shutil
                shutil.rmtree(self.destination)
            if self.stage.exists():
                import shutil
                shutil.rmtree(self.stage)
            self.events.clear()

    def test_materializer_cannot_rebaseline_the_elected_plan(self):
        self.mutation = "election-materialize"
        try:
            with self.assertRaisesRegex(ValueError, "election changed"):
                self.run_controller()
        finally:
            self.ready["target"] = "ios"
        self.assertFalse((self.destination / "shard").exists())

    def test_missing_policy_readiness_and_exact_signed_target_record_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "caller-owned"):
            workflow.execute(self.plan, self.discovery, self.state, self.destination,
                expected_build_key=self.ready["buildKey"], repository_root=self.root, environ={})
        original = self.verified.prior_ready_plans
        self.verified.prior_ready_plans = {}
        with self.assertRaisesRegex(ValueError, "not ready"):
            self.run_controller()
        self.verified.prior_ready_plans = original
        self.verified.rebased_request["sdkAppleValidationEvidence"] = self.records[:-1]
        with self.assertRaisesRegex(ValueError, "exact signed validation carrier"):
            self.run_controller()
        self.assertFalse((self.destination / "shard").exists())

    def test_signing_secret_is_rejected_before_state_or_outputs(self):
        with patch.object(workflow.product_reuse, "_verified_product_state") as state, \
                self.assertRaisesRegex(ValueError, "signing-secret context"):
            workflow.execute(self.plan, self.discovery, self.state, self.destination,
                expected_build_key=self.ready["buildKey"], repository_root=self.root,
                environ={"CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY": ""},
                sdk_apple_validation_policy=self.policy)
        state.assert_not_called()
        self.assertFalse(self.destination.exists())


class SdkIosMetadataCliTest(unittest.TestCase):
    def test_cli_forwards_exact_paths_policy_and_environment(self):
        root = Path("/absolute/repository")
        policy = Path("/absolute/policy.json")
        value = {"caller": "policy"}
        arguments = ["--plan", "/absolute/plan.json", "--discovery-root", "/absolute/discovery",
            "--state-root", "/absolute/state", "--destination", "/absolute/output",
            "--expected-build-key", "sha256:" + "1" * 64, "--repository-root", str(root),
            "--sdk-apple-validation-policy", str(policy)]
        with patch.object(workflow.product_reuse, "_canonical_control", return_value=value) as load, \
                patch.object(workflow, "execute") as execute:
            self.assertEqual(0, workflow.main(arguments))
        load.assert_called_once_with(policy, "Caller Apple validation policy")
        execute.assert_called_once_with(plan=Path("/absolute/plan.json"),
            discovery=Path("/absolute/discovery"), state=Path("/absolute/state"),
            destination=Path("/absolute/output"), expected_build_key="sha256:" + "1" * 64,
            repository_root=root, sdk_apple_validation_policy=value, environ=os.environ)

    def test_cli_is_strict_and_reports_controller_errors_as_usage(self):
        base = ["--plan", "/p", "--discovery-root", "/d", "--state-root", "/s",
                "--destination", "/o", "--expected-build-key", "key", "--repository-root", "/r"]
        for extra in (["--legacy-validation-artifact-id", "1"], ["--unknown", "value"]):
            with self.subTest(extra=extra), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as stopped:
                workflow.main([*base, *extra])
            self.assertEqual(2, stopped.exception.code)
        with patch.object(workflow, "execute", side_effect=ValueError("metadata rejected")), \
                redirect_stderr(io.StringIO()) as errors, self.assertRaises(SystemExit) as stopped:
            workflow.main(base)
        self.assertEqual(2, stopped.exception.code)
        self.assertIn("metadata rejected", errors.getvalue())

    def test_metadata_policy_context_wraps_execute_and_fails_closed(self):
        plan, root = Path("/absolute/plan.json"), Path("/absolute/repository")
        for mode in ("absent", "present", "error"):
            policy = Path("/absolute/" + mode + ".json") if mode != "absent" else None
            parsed = SimpleNamespace(plan=plan, repository_root=root,
                sdk_apple_validation_policy=None,
                sdk_facade_metadata_policy=policy, sdk_android_metadata_policy=policy)
            admissions = ({"sdk_facade_metadata_admission": object(),
                           "sdk_android_metadata_admission": object()}
                          if mode == "present" else {})
            events = []

            @contextmanager
            def options(arguments):
                self.assertIs(plan, arguments["plan"])
                self.assertIs(root, arguments["repository_root"])
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
                    patch.object(workflow, "execute", side_effect=run) as execute:
                if mode == "error":
                    with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                        workflow.main([])
                    execute.assert_not_called()
                else:
                    self.assertEqual(0, workflow.main([]))
                    self.assertEqual(["enter", "execute", "exit"], events)
                add.assert_called_once()


class SdkIosMetadataWorkerTest(unittest.TestCase):
    def test_fixed_product_phase_receives_only_authenticated_artifact_paths(self):
        temporary = tempfile.TemporaryDirectory(prefix="sdk-ios-metadata-worker-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name).resolve()
        package = root / "original-package"
        package.mkdir()
        (package / "package.bin").write_bytes(b"package")
        contents = {}
        for target in workflow._TARGETS:
            path = root / f"{target}.json"
            path.write_bytes(target.encode())
            contents[target] = path
        plan = {"schemaVersion": 1, "product": "sdk", "component": "sdk-ios",
                "phase": "metadata", "target": "ios", "buildKey": "sha256:" + "1" * 64,
                "inputs": []}
        producer = {"repository": "codex-agent-labs/codex-agent",
            "workflowPath": ".github/workflows/ci.yml", "commit": "a" * 40, "tree": "b" * 40,
            "event": "pull_request", "runId": 19, "runAttempt": 2, "pullRequest": 7}
        stage = root / "build/product-stage/sdk/sdk-ios/metadata"
        captured = {}

        def command(wrapper, fields, environment, **options):
            captured.update(fields)
            self.assertEqual(".", options["build_directory"])
            return [str(wrapper), "ciProductPhase"]

        def run(arguments, **options):
            self.assertEqual([str(root / "gradlew"), "ciProductPhase"], arguments)
            content = stage / workflow.OUTPUT_PATH
            content.parent.mkdir(parents=True)
            content.write_bytes(b'{"canonical":"metadata"}\n')
            write_output_manifest(stage, "sdk", "sdk-ios", "metadata", "ios", "0.8.0",
                                  {workflow.OUTPUT_KIND: "outputs/evidence"})
            return SimpleNamespace(returncode=0)

        with patch.object(workflow.product_reuse, "_runtime_worker_environment",
                          return_value=({}, root / "gradlew")), \
                patch.object(workflow.product_reuse, "_runtime_worker_command", side_effect=command), \
                patch.object(workflow.product_reuse, "_runtime_worker_checkout"), \
                patch.object(workflow.subprocess, "run", side_effect=run):
            result = workflow._execute_metadata(plan, producer=producer, sdk_version="0.8.0",
                package_stage=package, validation_contents=contents, repository_root=root,
                destination=root / "diagnostics", environ={})
        self.assertEqual("sdk-ios", captured["codexAgent.component"])
        self.assertEqual("metadata", captured["codexAgent.phase"])
        self.assertEqual(str(package), captured["codexAgent.iosMetadataPackageStage"])
        self.assertEqual(str(contents["ios-arm64"]),
                         captured["codexAgent.iosMetadataDeviceValidationContent"])
        self.assertEqual(str(contents["ios-simulator-arm64"]),
                         captured["codexAgent.iosMetadataSimulatorValidationContent"])
        self.assertEqual(stage, result["stage"])
        self.assertEqual({"execution.json", "gradle.log"},
                         {path.name for path in result["diagnostics"].iterdir()})

    def test_worker_failure_and_input_mutation_are_causal_and_preserve_originals(self):
        for mutation in ("failure", "input", "bytecode"):
            with self.subTest(mutation=mutation):
                temporary = tempfile.TemporaryDirectory(prefix=f"sdk-ios-metadata-{mutation}-")
                self.addCleanup(temporary.cleanup)
                root = Path(temporary.name).resolve()
                package = root / "package"
                package.mkdir()
                (package / "value.bin").write_bytes(b"original package")
                contents = {}
                for target in workflow._TARGETS:
                    path = root / f"{target}.json"
                    path.write_bytes(target.encode())
                    contents[target] = path
                plan = {"schemaVersion": 1, "product": "sdk", "component": "sdk-ios",
                        "phase": "metadata", "target": "ios", "buildKey": "sha256:" + "1" * 64,
                        "inputs": []}
                producer = {"repository": "codex-agent-labs/codex-agent",
                    "workflowPath": ".github/workflows/ci.yml", "commit": "a" * 40, "tree": "b" * 40,
                    "event": "pull_request", "runId": 19, "runAttempt": 2, "pullRequest": 7}

                def run(*args, **kwargs):
                    if mutation == "input":
                        contents["ios-arm64"].write_bytes(b"changed")
                    if mutation == "bytecode":
                        (root / "diagnostics/python-bytecode").mkdir()
                    return SimpleNamespace(returncode=7 if mutation == "failure" else 0)

                message = {"failure": "exit code 7", "input": "inputs changed",
                           "bytecode": "bytecode namespace"}[mutation]
                with patch.object(workflow.product_reuse, "_runtime_worker_environment",
                                  return_value=({}, root / "gradlew")), \
                        patch.object(workflow.product_reuse, "_runtime_worker_command",
                                     return_value=[str(root / "gradlew"), "ciProductPhase"]), \
                        patch.object(workflow.product_reuse, "_runtime_worker_checkout"), \
                        patch.object(workflow.subprocess, "run", side_effect=run), \
                        self.assertRaisesRegex(ValueError, message):
                    workflow._execute_metadata(plan, producer=producer, sdk_version="0.8.0",
                        package_stage=package, validation_contents=contents, repository_root=root,
                        destination=root / "diagnostics", environ={})
                self.assertEqual(b"original package", (package / "value.bin").read_bytes())


if __name__ == "__main__":
    unittest.main()
