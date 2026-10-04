"""SDK workflow composition only; mocked authenticated gates are not host evidence."""

from contextlib import ExitStack, nullcontext, contextmanager
from copy import deepcopy
import os
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile, ZIP_STORED
from unittest.mock import patch
from types import SimpleNamespace

from ci import sdk_workflow as workflow


class SdkWorkflowTest(unittest.TestCase):
    def test_java_import_uses_checked_zip_contents_and_rejects_changed_input_after_use(self):
        identities = (workflow.PhaseInstanceId("contract", "contract", "binary", "common"),
            workflow.PhaseInstanceId("runtime", "jvm", "binary", "jvm"),
            workflow.PhaseInstanceId("sdk", "sdk-android", "package", "android"))
        phases = [{**dict(zip(workflow.product_reuse._IDENTITY_KEYS,
            (identity.product, identity.component, identity.phase, identity.target))), "state": "retained"}
            for identity in identities]
        verified = SimpleNamespace(prior={"phases": phases}, sources={identity: object() for identity in identities})
        classes = self.root / "canonical-classes"
        classes.mkdir()
        (classes / "Core.class").write_bytes(b"synthetic original compiler output")

        def restore(verified, identities, destination):
            contract, runtime, android = [destination / "-".join(getattr(identity, field)
                for field in workflow.product_reuse._IDENTITY_KEYS) / "stage/outputs" for identity in identities]
            group = "maven/io/github/codex-agent-labs"
            core = contract / f"{group}/codex-agent-core-jvm/0.8.0/codex-agent-core-jvm-0.8.0.jar"
            core.parent.mkdir(parents=True)
            with ZipFile(core, "w", compression=ZIP_STORED) as archive:
                archive.writestr("Core.class", (classes / "Core.class").read_bytes())
                archive.writestr("META-INF/", b"")
                archive.writestr("META-INF/MANIFEST.MF", b"synthetic manifest")
            for path in (contract / f"{group}/codex-agent-core-android/0.8.0/codex-agent-core-android-0.8.0.aar",
                    runtime / "adapter/codex-agent-runtime-desktop-jvm-0.8.0.jar",
                    android / f"{group}/codex-agent-runtime-android/0.8.0/codex-agent-runtime-android-0.8.0.aar"):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"synthetic authenticated product input")
            evidence = contract / "evidence"
            evidence.mkdir()
            (evidence / "canonical-api.json").write_bytes(workflow.canonical_json_bytes({"targets": [
                {"kind": "jvm-classes", "sha256": workflow._execution_tree_digest(classes)}]}))
            (evidence / "canonical-coverage.json").write_bytes(b"synthetic canonical coverage")
            execution = contract / "execution/contract-execution.zip"
            execution.parent.mkdir()
            with ZipFile(execution, "w", compression=ZIP_STORED) as archive:
                archive.writestr("compiled-tests/Fixture.class", b"synthetic original fixture")
            return {identity: {"receipt": {"productVersion": "0.8.0"}} for identity in identities}

        plan_bytes = self.plan.read_bytes()
        with patch.object(workflow.product_reuse, "_restore_product_objects", side_effect=restore):
            with workflow._java_parity_inputs(verified, self.plan, plan_bytes) as inputs:
                self.assertEqual((classes / "Core.class").read_bytes(), (inputs / "kotlin-classes/Core.class").read_bytes())
                self.assertEqual(b"synthetic original fixture", (inputs / "fixture-classes/Fixture.class").read_bytes())
            with self.assertRaisesRegex(ValueError, "Original Java parity inputs changed"):
                with workflow._java_parity_inputs(verified, self.plan, plan_bytes) as inputs:
                    (inputs / "core-jvm.jar").write_bytes(b"different output")

    def test_full_parity_rejects_authentication_failure_or_incomplete_sdk_before_import(self):
        for failure in (ValueError("original authentication failed"), None):
            with self.subTest(failure=failure), \
                    patch.object(workflow.product_reuse, "_verified_product_state",
                        side_effect=failure, return_value=SimpleNamespace(prior={"phases": []}, sources={})) as authenticate, \
                    patch.object(workflow.product_reuse, "_restore_product_objects") as restore, \
                    patch.object(workflow, "decode_sdk_validation_records") as decode:
                with self.assertRaisesRegex(ValueError, "authentication failed|every selected SDK phase"):
                    with workflow.verified_parity_inputs(self.plan, self.discovery, self.state,
                            repository_root=self.repository, environ={}):
                        self.fail("Incomplete or unauthenticated products cannot reach consumers")
                authenticate.assert_called_once()
                restore.assert_not_called()
                decode.assert_not_called()

    def test_full_parity_composes_existing_checks_and_publishes_only_after_original_exit_checks(self):
        self.plan.write_bytes(workflow.canonical_json_bytes({"validationCommit": self.revision}))
        self.discovery.mkdir()
        self.state.mkdir()
        original = self.root / "preserved"
        original.mkdir()
        files = {}
        for name in ("canonical-api.json", "canonical-coverage.json", "kotlin-parity.json",
                "javascript-typescript-parity.json", "swift-parity.json", "objective-c-parity.json"):
            files[name] = original / name
            files[name].write_bytes(b"synthetic immutable evidence\n")
        stage, receipt = original / "stage", original / "phase.json"
        stage.mkdir()
        (stage / "evidence").write_bytes(b"synthetic original stage\n")
        receipt.write_bytes(b"synthetic original receipt\n")
        record = {name: stage for name in ("packageStage", "runtimeStages", "stagedSdks", "validationStage")}
        record.update({name: receipt for name in ("packageReceipt", "validationReceipt", "compatibilityRequest")})
        inputs = {"java": original, "files": files, "phases": {}, "native": {
            language: {target: record for target in workflow.NATIVE_TARGETS} for language in workflow.NATIVE_BINDINGS}}
        tooling = {"evidence": original, "publicKey": receipt, "requiredTrustDomain": "development",
            "keyring": None, "keysDirectory": None, "javaExecutable": "java"}
        before = workflow.regular_file_inventory(original)
        commands = []

        def consumer(command, **kwargs):
            commands.append(command)
            kwargs["stdout"].write(b"synthetic consumer log\n")
            if "--init-script" in command:
                if ":codex-agent-core:verifyJavaBindingParity" in command:
                    path = next(value.split("=", 1)[1] for value in command
                        if value.startswith("-DcodexAgent.importedJavaParityOutput="))
                    Path(path).parent.mkdir()
                    Path(path).write_bytes(b"synthetic consumer parity\n")
                else:
                    config_path = next(value.split("=", 1)[1] for value in command
                        if value.startswith("-DcodexAgent.importedNativeParityInputs="))
                    config = workflow.product_reuse.load_json_bytes(Path(config_path).read_bytes())
                    if ":verifyImportedSdkBindingParity" in command:
                        Path(config["finalOutput"]).write_bytes(b'{"result":"passed"}\n')
                    else:
                        for values in config["native"].values():
                            Path(values["output"]).write_bytes(b"synthetic consumer parity\n")
                        cabi = Path(config["cabiOutput"])
                        cabi.mkdir()
                        (cabi / "c-abi-parity.json").write_bytes(b"synthetic consumer parity\n")
            elif "-jar" in command:
                output = Path(command[command.index("--output") + 1])
                output.write_bytes(b"synthetic derived audit or receipt\n")

        for exit_failure in (False, True):
            @contextmanager
            def authenticated(*args, **kwargs):
                yield inputs
                if exit_failure:
                    raise ValueError("Original parity inputs changed during use")
            destination = self.repository / ("success" if not exit_failure else "failure")
            commands.clear()
            with patch.object(workflow, "verified_parity_inputs", side_effect=authenticated) as authenticate, \
                    patch.object(workflow, "verified_tooling_capture", return_value=nullcontext(receipt)) as tool_auth, \
                    patch.object(workflow.subprocess, "run", side_effect=consumer):
                if exit_failure:
                    with self.assertRaisesRegex(ValueError, "Original parity inputs changed"):
                        workflow.execute_parity(self.plan, self.discovery, self.state, destination,
                            repository_root=self.repository, environ={}, sdk_validation_tooling=tooling)
                    self.assertFalse(destination.exists())
                else:
                    workflow.execute_parity(self.plan, self.discovery, self.state, destination,
                        repository_root=self.repository, environ={}, sdk_validation_tooling=tooling)
                    self.assertEqual(14, len(list((destination / "m11").iterdir())))
                    self.assertTrue((destination / "sdk-parity.json").is_file())
                authenticate.assert_called_once()
                self.assertEqual(self.revision, tool_auth.call_args.kwargs["policy_revision"])
            self.assertEqual(before, workflow.regular_file_inventory(original))
            audits = [command[command.index("--phase") + 1] for command in commands
                if "audit-cross-language-bindings" in command]
            self.assertEqual(["M8", "M9_PYTHON", "M9_CSHARP", "M9_RUST", "M9_CPP", "M9_DART", "M11"], audits)
            self.assertEqual(5, sum("verify-native" in command for command in commands))

    def test_java_parity_publishes_nothing_when_original_input_exit_check_fails(self):
        @contextmanager
        def changed_originals(*args, **kwargs):
            yield self.root / "synthetic-verified-input-lifetime"
            raise ValueError("Original Java parity inputs changed")

        def consumer(command, **kwargs):
            output = next(value.split("=", 1)[1] for value in command
                if value.startswith("-DcodexAgent.importedJavaParityOutput="))
            Path(output).write_text('{"synthetic":"consumer result is not authority"}\n')

        destination = self.repository / "new-java-parity"
        self.discovery.mkdir(parents=True, exist_ok=True)
        self.state.mkdir(parents=True, exist_ok=True)
        with patch.object(workflow, "verified_java_parity_inputs", side_effect=changed_originals), \
                patch.object(workflow.subprocess, "run", side_effect=consumer), \
                patch.object(workflow, "publish_regular_tree") as publish:
            with self.assertRaisesRegex(ValueError, "inputs changed"):
                workflow.execute_java_parity(self.plan, self.discovery, self.state, destination,
                    repository_root=self.repository, environ={})
            publish.assert_not_called()
            self.assertFalse(destination.exists())

    def test_java_parity_authenticates_before_import_and_rejects_missing_or_unfinished_products(self):
        identities = (
            workflow.PhaseInstanceId("contract", "contract", "binary", "common"),
            workflow.PhaseInstanceId("runtime", "jvm", "binary", "jvm"),
            workflow.PhaseInstanceId("sdk", "sdk-android", "package", "android"),
        )
        for missing_source, pending in ((True, False), (False, True)):
            with self.subTest(missing_source=missing_source, pending=pending):
                rows = [{**dict(zip(workflow.product_reuse._IDENTITY_KEYS,
                    (identity.product, identity.component, identity.phase, identity.target))),
                    "state": "build" if pending and identity == identities[-1] else "retained"}
                    for identity in identities]
                verified = SimpleNamespace(prior={"phases": rows},
                    sources={identity: object() for identity in identities if not (missing_source and identity == identities[-1])})
                with patch.object(workflow.product_reuse, "_verified_product_state", return_value=verified) as authenticate, \
                        patch.object(workflow.product_reuse, "_restore_product_objects") as restore:
                    with self.assertRaisesRegex(ValueError, "completed authenticated"):
                        with workflow.verified_java_parity_inputs(self.plan, self.discovery, self.state,
                                repository_root=self.repository, environ={},
                                sdk_original_workflow_sha=self.revision):
                            self.fail("Incomplete products must never reach a consumer")
                    authenticate.assert_called_once()
                    self.assertEqual(self.revision, authenticate.call_args.kwargs["sdk_original_workflow_sha"])
                    restore.assert_not_called()

    def test_java_parity_cannot_bypass_failed_original_authentication(self):
        with patch.object(workflow.product_reuse, "_verified_product_state", side_effect=ValueError("original authentication failed")), \
                patch.object(workflow.product_reuse, "_restore_product_objects") as restore:
            with self.assertRaisesRegex(ValueError, "original authentication failed"):
                with workflow.verified_java_parity_inputs(self.plan, self.discovery, self.state,
                        repository_root=self.repository, environ={}):
                    self.fail("Failed authentication must never reach a consumer")
            restore.assert_not_called()

    def test_platform_controller_dispatch_preserves_exact_cli_tail_and_result(self):
        for command, module in (("core-metadata", "sdk_facade_metadata_workflow"),
                                ("maven-binary", "sdk_maven_binary_workflow"),
                                ("android-metadata", "sdk_android_metadata_workflow"),
                                ("android-validation", "sdk_android_validation_workflow"),
                                ("maven-package", "sdk_maven_package_workflow")):
            with self.subTest(command=command), patch(module + ".main", return_value=7) as execute:
                self.assertEqual(7, workflow.main([command, "--plan", "original plan"]))
                execute.assert_called_once_with(["--plan", "original plan"])

    def test_core_validation_dispatch_preserves_exact_cli_tail_and_result(self):
        with patch("sdk_facade_workflow.main", return_value=7) as execute:
            self.assertEqual(7, workflow.main(["core-validation", "--plan", "original plan"]))
        execute.assert_called_once_with(["--plan", "original plan"])

    def test_ios_metadata_dispatch_preserves_exact_cli_tail_and_result(self):
        with patch("sdk_ios_metadata_workflow.main", return_value=7) as execute:
            self.assertEqual(7, workflow.main(["ios-metadata", "--plan", "original plan"]))
            execute.assert_called_once_with(["--plan", "original plan"])

    def test_native_validation_dispatch_preserves_exact_cli_tail_and_result(self):
        with patch("sdk_native_validation_workflow.main", return_value=7) as execute:
            self.assertEqual(7, workflow.main(["native-validation", "--plan", "original plan"]))
            execute.assert_called_once_with(["--plan", "original plan"])

    def test_native_metadata_dispatch_preserves_exact_cli_tail_and_result(self):
        with patch("sdk_native_metadata_workflow.main", return_value=7) as execute:
            self.assertEqual(7, workflow.main(["native-metadata", "--plan", "original plan"]))
            execute.assert_called_once_with(["--plan", "original plan"])

    def test_verified_inputs_forwards_identical_caller_tooling_to_selection_not_imported_policy(self):
        caller_policy = {"evidence": self.root / "caller-tooling", "policyRevision": self.revision}
        imported_policy = {"evidence": self.root / "untrusted-transported-tooling", "policyRevision": "f" * 40}
        for policy in (caller_policy, None):
            self.inspect.reset_mock()
            captured = {}

            def capture(plan, destination, **kwargs):
                destination.mkdir()
                contract = destination / "contract.json"
                runtime = destination / "runtime.json"
                attestation = destination / "runtime.attestation.json"
                contract.write_bytes(b'{"synthetic":"original Contract receipt boundary"}\n')
                runtime.write_bytes(b'{"buildKey":"sha256:' + b"a" * 64 + b'"}\n')
                attestation.write_bytes(b"synthetic exact original attestation pairing\n")
                captured["sdk"] = {"arguments": {"contract_metadata_receipt": contract,
                    "runtime_metadata_receipt": runtime, "runtime_attestation": attestation,
                    "runtime_keyring": self.root / "captured-runtime-keyring",
                    "runtime_keys_directory": self.root / "captured-runtime-keys"},
                    "sdk_validation_tooling": imported_policy}
                captured["runtime"] = {"indexInputs": {"attestation": attestation}, "receiptBytes": {
                    workflow.PhaseInstanceId("contract", "contract", "metadata", "common"): contract.read_bytes(),
                    workflow.PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate"): runtime.read_bytes()}}

            # The joined context stands for existing signed-content authority;
            # its exact original receipt pairing has separate full-fixture tests.
            with self.subTest(policy=policy), \
                    patch.object(workflow, "_selection", wraps=workflow._selection) as selected, \
                    patch.object(workflow.product_reuse, "capture_sdk_inputs_upload", side_effect=capture), \
                    patch.object(workflow, "verified_apple_original_inputs",
                                 side_effect=lambda *a, **k: nullcontext(captured)) as verified:
                optional = {"sdk_validation_tooling": policy} if policy is not None else {}
                with workflow.verified_inputs(self.plan, self.discovery, self.state, **self.arguments,
                        **self.upload_for_capture(), **optional) as inputs:
                    captured_path = inputs["capture"]
                    self.assertTrue(captured_path.exists())
                    self.assertIs(imported_policy, inputs["sdk"]["sdk_validation_tooling"])
                    self.assertIs(policy, selected.call_args.kwargs["sdk_validation_tooling"])
                    self.assertEqual(self.revision, verified.call_args.kwargs["selection_revision"])
                    self.assertEqual(self.arguments["keyring"], verified.call_args.kwargs["keyring"])
                    self.assertEqual(self.arguments["keys_directory"], verified.call_args.kwargs["keys_directory"])
                    expected = {"repository_root": self.repository, "environ": self.arguments["environ"],
                                "include_sdk_selection": True,
                                "sdk_original_workflow_sha": self.upload["trusted_workflow_sha"], **optional}
                    self.inspect.assert_called_once_with(self.plan, self.discovery, self.state, **expected)
                    if policy is not None:
                        self.assertIs(caller_policy, self.inspect.call_args.kwargs["sdk_validation_tooling"])
                self.assertFalse(captured_path.exists())

    def test_native_package_dispatch_preserves_exact_cli_tail_and_result(self):
        with patch("sdk_native_package_workflow.main", return_value=7) as execute:
            self.assertEqual(7, workflow.main(["native-package", "--plan", "original plan"]))
            execute.assert_called_once_with(["--plan", "original plan"])

    def test_matrix_uses_only_replayed_javascript_package_and_validation(self):
        identities = (("sdk", "javascript", "package", "node"), ("sdk", "javascript", "validation", "node"),
                      ("sdk", "javascript", "metadata", "node"), ("runtime", "jvm", "binary", "jvm"))
        plans = [dict(zip(("product", "component", "phase", "target"), identity), buildKey="sha256:" + "a" * 64)
                 for identity in identities]
        self.inspect.return_value = {"readyPlans": plans}
        output = self.repository / "matrix-output"
        result = workflow.matrix(self.plan, self.discovery, self.state, output,
                                 repository_root=self.repository, environ={})
        self.assertEqual(["package", "validation"], [row["phase"] for row in result["include"]])
        self.assertTrue(all(row["runner"] == "ubuntu-24.04" for row in result["include"]))
        self.assertIn("sdk_workers_required=true", output.read_text())
        self.inspect.return_value = {"readyPlans": []}
        self.assertEqual({"include": []}, workflow.matrix(self.plan, self.discovery, self.state,
            self.repository / "empty-matrix", repository_root=self.repository, environ={}))

    def test_sdk_state_capture_replays_before_exposing_paths(self):
        destination = self.repository / "capture"
        with patch.object(workflow.product_reuse, "capture_runtime_resume_upload") as captured, \
                patch.object(workflow, "matrix", return_value={"include": []}) as matrix:
            result = workflow.capture(self.plan, destination, self.repository / "capture-output",
                **self.upload_for_capture(), sdk_state_wave=1, repository_root=self.repository, environ={}, token="fixture")
        self.assertEqual(1, captured.call_args.kwargs["sdk_state_wave"])
        self.assertEqual(destination / "original/runtime-state", result["state_root"])
        self.assertEqual(destination / "original/product-resume-state", result["discovery_root"])
        self.assertEqual(result["state_root"], matrix.call_args.args[2])
        self.assertEqual(self.upload["trusted_workflow_sha"], matrix.call_args.kwargs["trusted_workflow_sha"])
        with patch.object(workflow.product_reuse, "capture_runtime_resume_upload"), \
                patch.object(workflow, "matrix", side_effect=ValueError("invalid original state")):
            failed_output = self.repository / "failed-capture-output"
            with self.assertRaisesRegex(ValueError, "invalid original state"):
                workflow.capture(self.plan, destination, failed_output, **self.upload_for_capture(), token="fixture")
            self.assertFalse(failed_output.exists())

    def upload_for_capture(self):
        return {key: self.upload[key] for key in ("artifact_id", "artifact_sha256", "trusted_workflow_sha")}

    def test_matrix_forwards_exact_caller_workflow_pin_only_when_supplied(self):
        pin = "c" * 40
        self.inspect.return_value = {"readyPlans": []}
        workflow.matrix(self.plan, self.discovery, self.state, self.repository / "pinned-matrix-output",
            repository_root=self.repository, environ={}, trusted_workflow_sha=pin)
        self.assertEqual(pin, self.inspect.call_args.kwargs["sdk_original_workflow_sha"])
        workflow.matrix(self.plan, self.discovery, self.state, self.repository / "legacy-matrix-output",
            repository_root=self.repository, environ={})
        self.assertNotIn("sdk_original_workflow_sha", self.inspect.call_args.kwargs)

    def test_matrix_cli_accepts_caller_workflow_pin(self):
        pin = "c" * 40
        with patch.object(workflow, "matrix", return_value={"include": []}) as matrix:
            self.assertEqual(0, workflow.main(["matrix", "--plan", str(self.plan),
                "--discovery-root", str(self.discovery), "--state-root", str(self.state),
                "--github-output", str(self.repository / "cli-matrix-output"),
                "--trusted-workflow-sha", pin]))
        self.assertEqual(pin, matrix.call_args.kwargs["trusted_workflow_sha"])

    def test_collect_cli_forwards_paired_original_child_route(self):
        path = ".github/workflows/sdk-core-binary-validation.yml"
        job = "product-validation / sdk-core-binary-wave / sdk-core-binary-common"
        with patch.object(workflow, "collect") as collect:
            self.assertEqual(0, workflow.main(["collect", "--family", "core-binary",
                "--input-root", str(self.repository), "--destination", str(self.repository / "collected"),
                "--wave", "11", "--trusted-workflow-sha", "c" * 40,
                "--github-output", str(self.repository / "output"),
                "--sdk-worker-workflow-path", path, "--sdk-worker-job-name", job]))
        self.assertEqual(path, collect.call_args.kwargs["sdk_worker_workflow_path"])
        self.assertEqual(job, collect.call_args.kwargs["sdk_worker_job_name"])

    def test_collection_preserves_original_roots_and_uses_exact_sdk_partition(self):
        original = self.repository / "original"
        for name in ("product-resume-inputs", "product-resume-state", "runtime-state"):
            (original / name).mkdir(parents=True)
            (original / name / "original.bin").write_bytes(name.encode())
        identity = {"product": "sdk", "component": "javascript", "phase": "package", "target": "node"}
        for failure in (False, True):
            destination = self.repository / f"collected-{failure}"
            row = {**identity, "result": "failure" if failure else "success", "shardDirectory": "rows/js/original/shard"}

            def advance(*args, **kwargs):
                self.assertTrue(kwargs["sdk_javascript_only"])
                self.assertEqual((workflow.PhaseInstanceId(**identity),) if failure else (), kwargs["failed_instances"])
                self.assertEqual([] if failure else [destination / "collection/rows/js/original/shard"], args[3])
                args[4].mkdir(parents=True)
                return {"synthetic": "advanced"}

            with patch.object(workflow.product_reuse, "collect_runtime_workers", return_value={"rows": [row]}) as collect, \
                    patch.object(workflow.product_reuse, "advance_products", side_effect=advance) as advanced, \
                    patch.object(workflow, "matrix", return_value={"include": []}) as matrix:
                result = workflow.collect(original, destination, self.repository / f"collect-output-{failure}",
                    wave=1, trusted_workflow_sha="c" * 40, repository_root=self.repository, environ={}, token="fixture")
            self.assertTrue(collect.call_args.kwargs["sdk_javascript_only"])
            self.assertIsNone(collect.call_args.kwargs["sdk_worker_workflow_path"])
            self.assertIsNone(collect.call_args.kwargs["sdk_worker_job_name"])
            self.assertEqual("c" * 40, advanced.call_args.kwargs[
                "sdk_original_workflow_sha"])
            if not failure:
                self.assertEqual("c" * 40, matrix.call_args.kwargs["trusted_workflow_sha"])
            self.assertEqual({"synthetic": "advanced"}, result)
            self.assertEqual(not failure, matrix.called)
            for name in ("product-resume-inputs", "product-resume-state"):
                self.assertEqual(name.encode(), (destination / "handoff" / name / "original.bin").read_bytes())

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sdk-workflow-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.repository = self.root / "repository"
        self.repository.mkdir()
        self.plan = self.repository / "impact-plan.json"
        self.plan.write_bytes(b'{"synthetic":"original plan bytes"}\n')
        self.discovery, self.state = self.repository / "discovery", self.repository / "state"
        self.destination = self.root / "fresh-output"
        self.revision = "b" * 40
        self.selection = {"source": "current-runtime", "sdkVersion": "0.8.0", "defaultRuntimeVersion": "0.8.1",
            "compatibleReleaseRange": ">=0.8.0 <0.9.0", "compatibleRuntimeCompatibilityRange": ">=0.8.0 <0.9.0",
            "contractVersion": "0.8.0", "contractPayloadSha256": "sha256:" + "c" * 64, "consumers": [
                {"product": "sdk", "component": "python", "phase": "package", "target": "desktop"}]}
        self.arguments = {"keyring": self.root / "keyring.json", "keys_directory": self.root / "keys",
            "repository_root": self.repository, "environ": {"GITHUB_RUN_ID": "7"}, "token": "caller-token"}
        self.upload = {"trusted_workflow_sha": "d" * 40, "artifact_id": 42, "artifact_sha256": "sha256:" + "e" * 64,
            "expected_build_key": "sha256:" + "f" * 64, "expected_metadata_receipt_sha256": "sha256:" + "a" * 64}
        stack = self.enterContext(ExitStack())
        self.validate = stack.enter_context(patch.object(workflow.product_reuse, "_validate_plan",
                                                       return_value={"validationCommit": self.revision}))
        self.inspect = stack.enter_context(patch.object(workflow.product_reuse, "inspect_products",
                                                      return_value={"sdkInputSelection": self.selection}))
        self.released = stack.enter_context(patch.object(workflow.product_reuse, "materialize_sdk_default_inputs",
                                                       return_value={"synthetic": "released result"}))
        self.fresh = stack.enter_context(patch.object(workflow.sdk_handoff, "capture_sdk_handoff",
                                                    return_value={"synthetic": "fresh result"}))

    def stage(self, **changes):
        return workflow.stage(self.plan, self.discovery, self.state, self.destination, **{**self.arguments, **changes})

    def test_current_runtime_forwards_replayed_policy_contract_digest_and_exact_upload(self):
        before = deepcopy(self.selection)
        self.assertEqual({"synthetic": "fresh result"}, self.stage(**self.upload))
        self.validate.assert_called_once_with(self.plan, self.repository)
        self.inspect.assert_called_once_with(self.plan, self.discovery, self.state,
            repository_root=self.repository, environ=self.arguments["environ"], include_sdk_selection=True,
            sdk_original_workflow_sha=self.upload["trusted_workflow_sha"])
        self.fresh.assert_called_once_with(self.plan, self.destination, **self.upload,
            sdk_version=self.selection["sdkVersion"], compatible_release_range=self.selection["compatibleReleaseRange"],
            compatible_runtime_compatibility_range=self.selection["compatibleRuntimeCompatibilityRange"],
            expected_contract_payload_sha256=self.selection["contractPayloadSha256"],
            keyring=self.arguments["keyring"], keys_directory=self.arguments["keys_directory"],
            selection_repository_root=self.repository, selection_revision=self.revision,
            repository_root=self.repository, environ=self.arguments["environ"], token=self.arguments["token"])
        self.released.assert_not_called()
        self.assertEqual(before, self.selection)

    def test_retained_runtime_identity_does_not_replace_current_sdk_replay_authority(self):
        original = {"runId": 3, "runAttempt": 1}
        original_pin = "d" * 40
        self.stage(**self.upload, runtime_original_producer=original,
                   runtime_original_workflow_sha=original_pin)
        self.assertEqual(self.upload["trusted_workflow_sha"],
                         self.inspect.call_args.kwargs["sdk_original_workflow_sha"])
        self.assertEqual(original_pin, self.fresh.call_args.kwargs["trusted_workflow_sha"])
        self.assertEqual(original, self.fresh.call_args.kwargs["original_producer"])
        self.assertEqual(self.upload["expected_build_key"], self.fresh.call_args.kwargs["expected_build_key"])
        self.assertEqual(self.upload["expected_metadata_receipt_sha256"],
                         self.fresh.call_args.kwargs["expected_metadata_receipt_sha256"])
        self.released.assert_not_called()

    def test_retained_runtime_requires_paired_identity_and_current_runtime_selection(self):
        for options in ({"runtime_original_producer": {"runId": 3}},
                        {"runtime_original_workflow_sha": "d" * 40}):
            with self.subTest(options=options), self.assertRaisesRegex(ValueError, "must be paired"):
                self.stage(**self.upload, **options)
            self.inspect.assert_not_called()
        self.selection["source"] = "released-default"
        with self.assertRaisesRegex(ValueError, "cannot override a released default"):
            self.stage(**self.upload, runtime_original_producer={"runId": 3},
                       runtime_original_workflow_sha="d" * 40)
        self.fresh.assert_not_called()
        self.released.assert_not_called()

    def test_released_default_uses_current_replay_materializer_without_upload_identity(self):
        self.selection["source"] = "released-default"
        self.destination = self.repository / "build/sdk-inputs"
        self.assertEqual({"synthetic": "released result"}, self.stage())
        self.released.assert_called_once_with(self.plan, self.discovery, self.state, self.destination,
            keyring=self.arguments["keyring"], keys_directory=self.arguments["keys_directory"],
            repository_root=self.repository, environ=self.arguments["environ"])
        self.fresh.assert_not_called()

    def test_missing_or_unknown_replayed_selection_never_dispatches(self):
        for selection in (None, "released-default", {}, {**self.selection, "source": "caller-choice"}):
            self.inspect.return_value = {"sdkInputSelection": selection}
            with self.subTest(selection=selection), self.assertRaises(ValueError):
                self.stage(**self.upload)
            self.fresh.assert_not_called()
            self.released.assert_not_called()
            self.assertFalse(self.destination.exists())

    def test_current_runtime_requires_every_upload_identity_before_dispatch(self):
        for field in self.upload:
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "complete authenticated upload identity"):
                self.stage(**{name: value for name, value in self.upload.items() if name != field})
            self.fresh.assert_not_called()
            self.released.assert_not_called()
            self.assertFalse(self.destination.exists())

    def test_changed_plan_and_delegated_failure_never_report_success(self):
        original = self.plan.read_bytes()
        def changed(*args, **kwargs):
            self.plan.write_bytes(original + b"changed\n")
            return {"sdkInputSelection": self.selection}
        self.inspect.side_effect = changed
        with self.assertRaisesRegex(ValueError, "changed during inspection"):
            self.stage(**self.upload)
        self.fresh.assert_not_called()
        self.released.assert_not_called()
        self.plan.write_bytes(original)
        self.inspect.side_effect = None
        for source, delegated in (("current-runtime", self.fresh), ("released-default", self.released)):
            self.selection["source"] = source
            delegated.side_effect = ValueError("original gate rejected")
            with self.subTest(source=source), self.assertRaisesRegex(ValueError, "original gate rejected"):
                self.stage(**self.upload)
            self.assertFalse(self.destination.exists())

    def test_cli_capture_and_stage_share_private_verification_and_reject_incomplete_locator(self):
        import products.restore as restore
        capture_root = self.repository / "capture"
        discovery = capture_root / "original/product-resume-state"
        state = capture_root / "original/runtime-state"
        paths = {"plan": self.plan, "discovery-root": discovery, "state-root": state,
                 "destination": self.destination, "keyring": self.arguments["keyring"],
                 "keys-directory": self.arguments["keys_directory"], "repository-root": self.repository}
        argv = [value for name, path in paths.items() for value in (f"--{name}", str(path))]
        argv += ["--trusted-workflow-sha", self.upload["trusted_workflow_sha"],
                 "--state-artifact-id", "7", "--state-artifact-sha256", self.upload["artifact_sha256"],
                 "--state-capture-root", str(capture_root), "--state-wave", "4"]
        contexts = []
        def capture(*args, **kwargs):
            contexts.append(restore._VERIFICATION_SESSION.get())
            self.assertEqual(4, kwargs["state_wave"])
            self.assertEqual(7, kwargs["artifact_id"])
        def stage(*args, **kwargs):
            contexts.append(restore._VERIFICATION_SESSION.get())
        with patch.object(workflow.product_reuse, "capture_runtime_resume_upload", side_effect=capture) as captured, \
                patch.object(workflow, "stage", side_effect=stage):
            self.assertEqual(0, workflow.main(argv))
            captured.assert_called_once()
            self.assertIsNotNone(contexts[0])
            self.assertIs(contexts[0], contexts[1])
            captured.reset_mock()
            for invalid in (argv[:-4], [*argv, "--state-root", str(self.state)]):
                with self.assertRaises(SystemExit):
                    workflow.main(invalid)
                captured.assert_not_called()

    def test_cli_retained_runtime_locator_is_canonical_and_paired_before_capture(self):
        from products.inventory import canonical_json_bytes
        paths = {"plan": self.plan, "discovery-root": self.discovery, "state-root": self.state,
                 "destination": self.destination, "keyring": self.arguments["keyring"],
                 "keys-directory": self.arguments["keys_directory"], "repository-root": self.repository}
        argv = [value for name, path in paths.items() for value in (f"--{name}", str(path))]
        original = {"runId": 3, "runAttempt": 1}
        locator = self.repository / "original-producer.json"
        locator.write_bytes(canonical_json_bytes(original))
        options = ["--runtime-original-producer", str(locator), "--runtime-original-workflow-sha", "d" * 40]
        with patch.object(workflow, "stage") as staged:
            self.assertEqual(0, workflow.main([*argv, *options]))
            self.assertEqual(original, staged.call_args.kwargs["runtime_original_producer"])
            self.assertEqual("d" * 40, staged.call_args.kwargs["runtime_original_workflow_sha"])
            staged.reset_mock()
            for invalid in (options[:2], options[2:]):
                with self.subTest(invalid=invalid), self.assertRaises(SystemExit):
                    workflow.main([*argv, *invalid])
                staged.assert_not_called()
            locator.write_bytes(b'{ "runId":3,"runAttempt":1 }')
            with self.assertRaises(SystemExit):
                workflow.main([*argv, *options])
            staged.assert_not_called()

    def test_cli_forwards_paths_upload_identity_and_environment_without_source_override(self):
        paths = {"plan": self.plan, "discovery-root": self.discovery, "state-root": self.state,
                 "destination": self.destination, "keyring": self.arguments["keyring"],
                 "keys-directory": self.arguments["keys_directory"], "repository-root": self.repository}
        argv = [value for name, path in paths.items() for value in (f"--{name}", str(path))]
        for name, value in self.upload.items():
            argv.extend(("--" + name.replace("_", "-"), str(value)))
        with patch.dict(os.environ, {"GITHUB_TOKEN": "workflow-token"}, clear=True), patch.object(workflow, "stage") as stage:
            self.assertEqual(0, workflow.main(argv))
            stage.assert_called_once_with(self.plan, self.discovery, self.state, self.destination,
                keyring=self.arguments["keyring"], keys_directory=self.arguments["keys_directory"],
                repository_root=self.repository, **self.upload, environ=os.environ, token="workflow-token")
        with patch.object(workflow, "stage") as stage, self.assertRaises(SystemExit):
            workflow.main([*argv, "--source", "released-default"])
        stage.assert_not_called()
        with patch.object(workflow, "stage", side_effect=ValueError("replay mismatch")), self.assertRaises(SystemExit) as failed:
            workflow.main(argv)
        self.assertEqual(2, failed.exception.code)


if __name__ == "__main__":
    unittest.main()
