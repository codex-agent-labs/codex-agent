"""SDK workflow composition only; mocked authenticated gates are not host evidence."""

from contextlib import ExitStack, nullcontext, contextmanager, redirect_stderr
from copy import deepcopy
import io
import os
import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile, ZIP_STORED
from unittest.mock import patch
from types import SimpleNamespace

from ci import sdk_workflow as workflow


_SDK_INPUT_RECOVERY_FIXTURE = json.loads(
    (Path(__file__).parent / "data/sdk-input-recovery.json").read_bytes())


def _sdk_input_recovery_arguments(source, runtime):
    return dict(retained_sdk_inputs_source=source, reference_sdk_inputs=True,
        artifact_id=runtime["artifactId"], artifact_sha256=runtime["artifactSha256"],
        expected_build_key=runtime["buildKey"],
        expected_metadata_receipt_sha256=runtime["metadataReceiptSha256"],
        runtime_original_producer=runtime["producer"],
        runtime_original_workflow_sha=runtime["workflowSha"])


class SdkWorkflowTest(unittest.TestCase):
    def test_compact_apple_pins_select_retained_completion_not_legacy_recovery_hint(self):
        import sdk_apple_upload_locator as locator
        spec = json.loads((Path(__file__).parent / "data/requalified-sdk-completed-resume.json").read_bytes())
        # Schema4 lists current additions; these exact Apple pins belong to the
        # preserved completion it references, not its new completedPhases rows.
        self.assertEqual((12564750112, "dbb333097878fa669b2dbb56f7a1cff701fc708d"),
            (spec["reuseCompletion"]["artifactId"], spec["reuseCompletion"]["sourceCommit"]))
        self.assertEqual(
            {"buildKey": "sha256:468e22eaa2f42ee56fd101e6bc88a9f49eb20d721eac402c7e35c89b3d4a4bd9",
             "receiptSha256": "sha256:a9aa3a319595b754bc06ad843ff0142a4c7527824768a91cb131a3610c51adab",
             "artifactId": 12036959536,
             "artifactSha256": "sha256:835b2c7641fb225ff2a35f8f8f326746b6bf456cdffc45a2ff07c12ede280202",
             "jobId": 116893614838},
            locator.RETAINED_PARITY_SOURCE)

    def test_compact_apple_parity_requires_qualified_original_and_exact_raw_reports(self):
        from reuse_qualification import CompletedFrozenReuse
        import sdk_apple_upload_locator as locator
        import runtime_reference_archive as transport
        import io
        cap = object.__new__(CompletedFrozenReuse)
        identity = workflow.PhaseInstanceId("sdk", "sdk-ios", "validation", "ios-arm64")
        consumer = dict(repository="codex-agent-labs/codex-agent", workflowPath=".github/workflows/ci.yml",
                        event="pull_request", pullRequest=31, runId=40000000000, runAttempt=1)
        origin = locator.RETAINED_PARITY_SOURCE
        row = {field: origin[field] for field in ("buildKey", "receiptSha256")}
        envelope = dict(receipt={"producer": consumer})
        verified = SimpleNamespace(completed_frozen=cap, consumer={"kind": "ci", "producer": consumer},
            producer=consumer, rebased_request={}, prior_by_instance={identity: row})
        inner = io.BytesIO()
        reports = []
        with ZipFile(inner, "w") as archive:
            for name in ("swift-parity.json", "objective-c-parity.json"):
                raw = b"synthetic raw report, never hosted acceptance"
                archive.writestr("reports/" + name, raw)
                reports.append(dict(relativePath="reports/" + name, bytes=len(raw), sha256=workflow.sha256_bytes(raw)))
        outer = io.BytesIO()
        with ZipFile(outer, "w") as archive:
            archive.writestr("execution/apple-validation-evidence.zip", inner.getvalue())
        artifact = dict(id=origin["artifactId"], digest=origin["artifactSha256"])
        observed = [{"jobs": [{"id": origin["jobId"]}]}]
        for defect in (None, "authority", "receipt", "upload", "job", "report"):
            destination = self.root / ("apple-parity-" + str(defect))
            selected = None if defect == "authority" else envelope
            verified.prior_by_instance[identity] = {**row, "receiptSha256": "wrong"} if defect == "receipt" else row
            with self.subTest(defect=defect), ExitStack() as stack:
                for name in ("check_request", "check_consumer"):
                    stack.enter_context(patch.object(CompletedFrozenReuse, name))
                stack.enter_context(patch.object(CompletedFrozenReuse, "envelope", return_value=selected))
                stack.enter_context(patch.object(CompletedFrozenReuse, "observe_extended_sdk", return_value=(None,
                    {**artifact, "id": 1} if defect == "upload" else artifact,
                    [{"jobs": [{"id": 1}]}] if defect == "job" else observed)))
                stack.enter_context(patch.object(locator, "RETAINED_PARITY_ARCHIVE_BYTES", len(inner.getvalue())))
                stack.enter_context(patch.object(locator, "RETAINED_PARITY_REPORTS",
                    [{**r, "sha256": workflow.sha256_bytes(b"wrong")} for r in reports] if defect == "report" else reports))
                archive = stack.enter_context(ZipFile(io.BytesIO(outer.getvalue())))
                opened = stack.enter_context(patch.object(transport, "open_reference_archive",
                    return_value=nullcontext((archive, None))))
                if defect:
                    with self.assertRaises(ValueError):
                        workflow._completed_apple_parity_files(verified, destination, token="fixture")
                    if defect != "report":
                        opened.assert_not_called()
                else:
                    files = workflow._completed_apple_parity_files(verified, destination, token="fixture")
                    self.assertEqual({"swift-parity.json", "objective-c-parity.json"}, set(files))
                    self.assertTrue(all(path.read_bytes() == raw for path in files.values()))

    def test_compact_parity_borrows_qualified_categories_for_entire_consumer_lifetime(self):
        from products.restore import _VERIFICATION_SESSION
        fields = workflow.product_reuse._IDENTITY_KEYS
        rows = []
        native = {}
        directory = self.root / "categories"
        directory.mkdir()
        for identity in workflow.PHASE_INSTANCE_IDS:
            identity_fields = {name: getattr(identity, name) for name in fields}
            raw = workflow.canonical_json_bytes(identity_fields)
            row = {**identity_fields, "state": "retained",
                   "receiptSha256": workflow.sha256_bytes(raw)}
            rows.append(row)
            if identity.product == "sdk" and identity.component in workflow.NATIVE_BINDINGS and identity.phase == "validation":
                receipt = directory / (identity.component + "-" + identity.target + ".json")
                receipt.write_bytes(raw)
                native[row["receiptSha256"]] = dict(component=identity.component, target=identity.target,
                    receiptSha256=row["receiptSha256"], validationReceipt=receipt,
                    **{name: directory for name in ("packageStage", "runtimeStages", "stagedSdks",
                                                   "validationStage", "runtimeAuthorization", "binaryStage")},
                    **{name: receipt for name in ("packageReceipt", "compatibilityRequest", "binaryReceipt")})
        cap = SimpleNamespace(envelope=lambda row: row)
        verified = SimpleNamespace(prior={"phases": rows},
            sources={workflow.product_reuse._identity(row): object() for row in rows},
            rebased_request={}, completed_frozen=cap)
        borrowed = []
        def records(instance, envelopes, package):
            self.assertIsNotNone(_VERIFICATION_SESSION.get())
            self.assertEqual(sorted(workflow.NATIVE_TARGETS), [row["target"] for row in envelopes])
            self.assertEqual("package", package["phase"])
            borrowed.append(instance.component)
            return [], {row["receiptSha256"]: native[row["receiptSha256"]] for row in envelopes}
        def unchanged():
            self.assertIsNotNone(_VERIFICATION_SESSION.get())
        for mutate in (False, True):
            borrowed.clear()
            with patch.object(workflow.product_reuse, "_verified_product_state", return_value=verified), \
                    patch.object(workflow.product_reuse, "_retained_sdk_handoffs", return_value=[]), \
                    patch.object(workflow.product_reuse, "_retained_apple_handoffs", return_value=[]), \
                    patch.object(workflow.product_reuse, "_restore_product_objects") as restore, \
                    patch.object(workflow, "_completed_apple_parity_files", return_value={}) as apple, \
                    patch.object(workflow, "_java_parity_inputs", return_value=nullcontext(directory)), \
                    patch("sdk_native_metadata_workflow.completed_validation_recovery",
                          return_value=dict(records=records, check=unchanged)) as recover:
                def consume():
                    with workflow.verified_parity_inputs(self.plan, self.discovery, self.state,
                            repository_root=self.repository, environ={}, sdk_original_workflow_sha=self.revision,
                            sdk_validation_tooling={}, completed_frozen=cap) as inputs:
                        self.assertIsNotNone(_VERIFICATION_SESSION.get())
                        self.assertEqual(25, sum(len(hosts) for hosts in inputs["native"].values()))
                        if mutate:
                            next(iter(native.values()))["validationReceipt"].write_bytes(b"changed during use")
                if mutate:
                    with self.assertRaisesRegex(ValueError, "Original parity inputs changed"):
                        consume()
                else:
                    consume()
                self.assertEqual(list(workflow.NATIVE_BINDINGS), borrowed)
                recover.assert_called_once()
                apple.assert_called_once()
                restore.assert_called_once()  # Native categories are not restored/copied again here.
            self.assertIsNone(_VERIFICATION_SESSION.get())

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
        record = {name: stage for name in ("packageStage", "runtimeStages", "stagedSdks",
                                         "validationStage", "runtimeAuthorization", "binaryStage")}
        record.update({name: receipt for name in
                       ("packageReceipt", "validationReceipt", "compatibilityRequest", "binaryReceipt")})
        inputs = {"java": original, "files": files, "phases": {}, "native": {
            language: {target: record for target in workflow.NATIVE_TARGETS} for language in workflow.NATIVE_BINDINGS}}
        tooling = {"evidence": original, "publicKey": receipt, "requiredTrustDomain": "development",
            "keyring": None, "keysDirectory": None, "javaExecutable": "java"}
        before = workflow.regular_file_inventory(original)
        commands = []

        def consumer(command, **kwargs):
            commands.append(command)
            kwargs["stdout"].write(b"synthetic consumer log\n")
            if failure == "child":
                raise workflow.subprocess.CalledProcessError(1, command)
            if "verify-native" in command:
                package = Path(command[command.index("--receipt") + 1])
                self.assertEqual(receipt.read_bytes(), package.read_bytes())
                self.assertEqual(workflow.regular_file_inventory(stage),
                    workflow.regular_file_inventory(package.parent / "runtime-authorization/linux-x64"))
                if command[command.index("--component") + 1] == "csharp":
                    self.assertEqual(receipt.read_bytes(), (package.parent / "csharp-binary/phase-receipt.json").read_bytes())
                    self.assertEqual(workflow.regular_file_inventory(stage),
                        workflow.regular_file_inventory(package.parent / "csharp-binary/stage"))
            if "--init-script" in command:
                self.assertIn(str(self.repository / ".github/actions/run-ci-lane/release_tooling.init.gradle"), command)
                if ":codex-agent-core:verifyJavaBindingParity" in command:
                    path = next(value.split("=", 1)[1] for value in command
                        if value.startswith("-DcodexAgent.importedJavaParityOutput="))
                    Path(path).parent.mkdir()
                    Path(path).write_bytes(b"synthetic consumer parity\n")
                else:
                    config_path = next(value.split("=", 1)[1] for value in command
                        if value.startswith("-DcodexAgent.importedNativeParityInputs="))
                    native_init = Path(config_path).with_name("native.init.gradle").read_text()
                    self.assertIn("java.nio.file.Files.delete(output)", native_init)
                    self.assertIn("java.nio.file.LinkOption.NOFOLLOW_LINKS", native_init)
                    self.assertIn("C ABI parity output must be fresh", native_init)
                    self.assertIn("C ABI parity output overlaps an original input", native_init)
                    self.assertNotIn("deleteRecursively", native_init)
                    self.assertNotIn("VerifyImportedCAbiBindingParityTask", native_init)
                    self.assertIn("file(original.bootstrap)", native_init)
                    self.assertIn("spec.classifier.substring('c-abi-'.length())", native_init)
                    config = workflow.product_reuse.load_json_bytes(Path(config_path).read_bytes())
                    if ":verifyImportedSdkBindingParity" in command:
                        self.assertTrue(Path(config["nonNative"]["java"]).is_file())
                        self.assertIn("deriveCrossLanguageNativeWrapperBindingReceipt(input)", native_init)
                        self.assertIn("verifyCrossLanguageBindingParity(input)", native_init)
                        self.assertIn("schema:6", native_init)
                        self.assertIn("phase.set('M11')", native_init)
                        self.assertIn("output.list().toList().toSet()", native_init)
                        self.assertNotIn("evidenceDirectory.set(file(config.finalEvidence))", native_init)
                        self.assertIn("'candidateCommit', 'candidateTree'", native_init)
                        self.assertIn("canonical_json_bytes", native_init)
                        final = Path(config["finalEvidence"])
                        final.mkdir()
                        for name in (
                                "canonical-api.json", "canonical-coverage.json", "binding-obligations-m11.json",
                                *(language + "-parity.json" for language in (
                                    "kotlin", "java", "javascript-typescript", "swift", "objective-c", "c-abi",
                                    "python", "csharp", "rust", "cpp", "dart"))):
                            (final / name).write_bytes(b"synthetic aggregate evidence, not acceptance\n")
                        Path(config["finalOutput"]).write_bytes(b'{"result":"passed"}\n')
                        if failure == "context":
                            Path(config["native"]["cpp"]["packageReceipt"]).write_bytes(b"changed")
                    else:
                        for values in config["native"].values():
                            Path(values["output"]).write_bytes(b"synthetic consumer parity\n")
                        cabi = Path(config["cabiOutput"])
                        cabi.mkdir()
                        (cabi / "c-abi-parity.json").write_bytes(b"synthetic consumer parity\n")
            elif "-jar" in command:
                output = Path(command[command.index("--output") + 1])
                output.write_bytes(b"synthetic derived audit or receipt\n")

        for failure in (None, "original", "context", "child"):
            @contextmanager
            def authenticated(*args, **kwargs):
                yield inputs
                if failure == "original":
                    raise ValueError("Original parity inputs changed during use")
            destination = self.repository / ("result-" + str(failure))
            commands.clear()
            diagnostic = io.StringIO()
            with patch.object(workflow, "verified_parity_inputs", side_effect=authenticated) as authenticate, \
                    patch.object(workflow, "verified_tooling_capture", return_value=nullcontext(receipt)) as tool_auth, \
                    patch.object(workflow.subprocess, "run", side_effect=consumer), \
                    patch.object(workflow, "snapshot_regular_tree", wraps=workflow.snapshot_regular_tree) as capture, \
                    redirect_stderr(diagnostic):
                if failure:
                    error = workflow.subprocess.CalledProcessError if failure == "child" else ValueError
                    message = {"original": "Original parity inputs changed",
                               "context": "Parity package context changed", "child": "exit status 1"}[failure]
                    with self.assertRaisesRegex(error, message):
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
                authorizations = [call for call in capture.call_args_list if
                                  "runtime-authorization" in Path(call.args[1]).parts]
                self.assertEqual(5, len(authorizations))  # Shared once, not 25 copies.
            self.assertEqual(before, workflow.regular_file_inventory(original))
            if failure == "child":
                self.assertIn("synthetic consumer log", diagnostic.getvalue())
                self.assertEqual(1, len(commands))
                continue
            audits = [command[command.index("--phase") + 1] for command in commands
                if "audit-cross-language-bindings" in command]
            self.assertEqual([], audits)  # One in-memory M11 evaluation, no repeated JVM receipt advancement.
            self.assertEqual(2, sum("--init-script" in command for command in commands))
            self.assertFalse(any("-jar" in command for command in commands))
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

    def test_changed_aggregate_requires_full_input_admission_until_requalified(self):
        aggregate = workflow.PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate")
        for complete in (False, True):
            cap = SimpleNamespace(completed_phases=lambda: (aggregate,) if complete else ())
            def capture(plan, destination, **kwargs):
                destination.mkdir()
                self.assertEqual(cap if complete else None, kwargs.get("completed_frozen"))
            with self.subTest(complete=complete), \
                    patch.object(workflow, "_selection", return_value=(
                        {"validationCommit": self.revision},
                        {"source": "current-runtime", "contractPayloadSha256": "sha256:" + "a" * 64},
                        self.plan.read_bytes())), \
                    patch.object(workflow.product_reuse, "capture_sdk_inputs_upload", side_effect=capture), \
                    patch.object(workflow, "verified_apple_original_inputs", side_effect=lambda *a, **k: nullcontext({})) as full, \
                    patch.object(workflow, "_completed_sdk_inputs", side_effect=lambda *a, **k: nullcontext({})) as native:
                with workflow.verified_inputs(self.plan, self.discovery, self.state, **self.arguments,
                        **self.upload_for_capture(), completed_frozen=cap):
                    pass
                self.assertEqual(int(complete), native.call_count)
                self.assertEqual(int(not complete), full.call_count)

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

    def test_paired_capture_execution_shares_authority_and_exposes_outputs_only_after_exit_checks(self):
        import reuse_qualification
        from products.restore import _VERIFICATION_SESSION
        output = self.root / "paired-output"
        argv = ["capture", "--family", "native-validation", "--scope-inputs", "--plan", str(self.plan),
            "--destination", str(self.root / "current"), "--artifact-id", "42", "--artifact-sha256", "a" * 64,
            "--trusted-workflow-sha", "b" * 40, "--github-output", str(output),
            "--preparation-destination", str(self.root / "previous"), "--preparation-artifact-id", "41",
            "--preparation-artifact-sha256", "c" * 64, "--preparation-phase", "package",
            "--preparation-sdk-state-wave", "4"]
        for failure in (None, "second", "execute", "exit"):
            events, capability = [], object()
            sessions = []
            @contextmanager
            def authority(arguments):
                arguments.pop("completed_frozen_policy")
                events.append("authenticate")
                sessions.append(_VERIFICATION_SESSION.get())
                try:
                    yield {"completed_frozen": capability}
                finally:
                    self.assertFalse(output.exists())
                    events.append("exit-check")
                    if failure == "exit":
                        raise ValueError("policy changed during use")
            def capture(**arguments):
                sessions.append(_VERIFICATION_SESSION.get())
                self.assertIs(capability, arguments["completed_frozen"])
                self.assertTrue(arguments["scope_inputs"])
                self.assertIsNone(arguments["github_output_path"])
                self.assertFalse(output.exists())
                events.append(arguments["family"])
                if arguments["family"] == "native-package":
                    self.assertEqual(41, arguments["artifact_id"])
                    self.assertEqual("c" * 64, arguments["artifact_sha256"])
                    self.assertEqual(0, arguments["state_wave"])
                    self.assertEqual(4, arguments["sdk_state_wave"])
                    self.assertEqual(self.root / "current/plan.json", arguments["plan"])
                    if failure == "second":
                        raise ValueError("preparation authentication failed")
                root = arguments["destination"]
                return {"plan_path": root / "plan.json", "state_root": root / "state",
                    "matrix": {"include": [{"family": arguments["family"]}]}}
            def continuation(current, previous, semantic):
                sessions.append(_VERIFICATION_SESSION.get())
                self.assertIs(capability, semantic['completed_frozen'])
                self.assertEqual(self.root / 'current/plan.json', current['plan_path'])
                self.assertEqual(self.root / 'previous/state', previous['state_root'])
                self.assertEqual(['authenticate', 'native-validation', 'native-package'], events)
                self.assertFalse(output.exists())
                events.append('execute')
                if failure == 'execute':
                    raise ValueError('consumer failed')
            with self.subTest(failure=failure), \
                    patch.object(reuse_qualification, "completed_frozen_options", side_effect=authority) as auth, \
                    patch.object(workflow, "capture", side_effect=capture) as captured:
                if failure:
                    with self.assertRaises(SystemExit):
                        workflow._workflow_main(argv, _continuation=continuation)
                    self.assertFalse(output.exists())
                else:
                    workflow._workflow_main(argv, _continuation=continuation)
                    fields = dict(line.split("=", 1) for line in output.read_text().splitlines())
                    self.assertEqual(str(self.root / "previous/state"), fields["preparation_state_root"])
                    self.assertEqual({"include": [{"family": "native-package"}]}, json.loads(fields["preparation_sdk_matrix"]))
                    self.assertEqual({"include": [{"family": "native-validation"}]}, json.loads(fields["sdk_matrix"]))
                    output.unlink()
                auth.assert_called_once()
                self.assertIsNotNone(sessions[0])
                self.assertTrue(all(value is sessions[0] for value in sessions))
                self.assertIsNone(_VERIFICATION_SESSION.get())
                self.assertEqual(2, captured.call_count)
                self.assertEqual(["authenticate", "native-validation", "native-package"] +
                    ([] if failure == "second" else ["execute"]) + ["exit-check"], events)
        for flag, value in (("--family", "native-package"), ("--preparation-destination", str(self.root / "current/child"))):
            invalid = list(argv)
            invalid[invalid.index(flag) + 1] = value
            with patch.object(workflow, "capture") as captured, self.assertRaises(SystemExit):
                workflow.main(invalid)
            captured.assert_not_called()
        for flag in ("--scope-inputs", "--preparation-artifact-sha256"):
            invalid = list(argv)
            at = invalid.index(flag)
            del invalid[at:at + (1 if flag == "--scope-inputs" else 2)]
            with patch.object(workflow, "capture") as captured, self.assertRaises(SystemExit):
                workflow.main(invalid)
            captured.assert_not_called()

    def test_maven_capture_scopes_workers_but_preserves_full_collector_state(self):
        for family, component, target in (("core-binary", "sdk-core", "common"),
                                           ("android-binary", "sdk-android", "android")):
            for scoped in (False, True):
                with self.subTest(family=family, scoped=scoped), \
                        patch.object(workflow.product_reuse, "capture_runtime_resume_upload") as captured, \
                        patch.object(workflow, "matrix", return_value={"include": []}):
                    workflow.capture(self.plan, self.repository / "capture", self.repository / "capture-output",
                        **self.upload_for_capture(), token="fixture", family=family, scope_inputs=scoped)
                    if scoped:
                        self.assertEqual((workflow.PhaseInstanceId("sdk", component, "binary", target),),
                                         captured.call_args.kwargs["requested_scope"])
                    else:
                        self.assertNotIn("requested_scope", captured.call_args.kwargs)

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

    def test_android_metadata_collection_constructs_concrete_admission_before_advancing(self):
        from reuse_qualification import CompletedFrozenReuse
        from products.sdk_android_metadata_admission import AndroidMetadataAdmission
        original = self.repository / "android-metadata-input"
        for name in ("product-resume-inputs", "product-resume-state", "runtime-state"):
            (original / name).mkdir(parents=True)
        row = {"result": "success", "shardDirectory": "rows/android/original/shard", "artifact": {"id": 123}}
        destination = self.repository / "android-metadata-collected"
        cap = object.__new__(CompletedFrozenReuse)
        def advance(*args, **kwargs):
            admission = kwargs["sdk_android_metadata_admission"]
            self.assertIs(type(admission), AndroidMetadataAdmission)
            self.assertIs(cap, admission._completed["completed_frozen"])
            self.assertEqual(row["artifact"], admission._completed["artifact"])
            args[4].mkdir(parents=True)
            return {"matrices": {"sdk": []}}
        with patch.object(workflow.product_reuse, "collect_runtime_workers", return_value={"rows": [row]}), \
                patch.object(workflow.product_reuse, "advance_products", side_effect=advance):
            workflow.collect(original, destination, self.repository / "android-metadata-output", wave=18,
                family="android-metadata", trusted_workflow_sha="c" * 40, repository_root=self.repository,
                environ={}, token="fixture", completed_frozen=cap)

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
                return {"synthetic": "advanced", "matrices": {"sdk": []}}

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
            self.assertEqual({"synthetic": "advanced", "matrices": {"sdk": []}}, result)
            matrix.assert_not_called()
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

    def test_retained_sdk_route_keeps_current_selection_and_independent_runtime_pins(self):
        source = {"artifactId": 701, "artifactSha256": "sha256:" + "0" * 64,
                  "producer": {"runId": 3}, "workflowSha": "1" * 40}
        with patch.object(workflow.sdk_handoff, "capture_reused_sdk_handoff", return_value={"retained": True}) as reuse:
            self.assertEqual({"retained": True}, self.stage(**self.upload, retained_sdk_inputs_source=source))
        self.fresh.assert_not_called()
        self.assertEqual(source, reuse.call_args.kwargs["sdk_inputs_source"])
        self.assertEqual(self.revision, reuse.call_args.kwargs["selection_revision"])
        self.assertEqual(self.upload["artifact_id"], reuse.call_args.kwargs["artifact_id"])
        self.assertEqual(self.selection["contractPayloadSha256"],
                         reuse.call_args.kwargs["expected_contract_payload_sha256"])

    def test_control_only_route_keeps_both_independent_sources(self):
        source, runtime = {'artifactId': 701}, {'runId': 3}
        with patch.object(workflow.sdk_handoff, 'stage_sdk_input_binding', return_value={'routing': True}) as route:
            result = self.stage(**self.upload, retained_sdk_inputs_source=source,
                runtime_original_producer=runtime, runtime_original_workflow_sha='1'*40, reference_sdk_inputs=True)
        self.assertEqual({'routing': True}, result)
        self.fresh.assert_not_called()
        self.assertEqual(source, route.call_args.kwargs['sdk_inputs_source'])
        self.assertEqual(dict(artifactId=self.upload['artifact_id'], artifactSha256=self.upload['artifact_sha256'],
            producer=runtime, workflowSha='1'*40, buildKey=self.upload['expected_build_key'],
            metadataReceiptSha256=self.upload['expected_metadata_receipt_sha256']), route.call_args.kwargs['runtime_source'])
        with self.assertRaisesRegex(ValueError, 'independently selected'):
            self.stage(**self.upload, reference_sdk_inputs=True)

    def test_retained_current_sdk_bundle_cannot_override_released_default_selection(self):
        self.selection["source"] = "released-default"
        with patch.object(workflow.sdk_handoff, "capture_reused_sdk_handoff") as reuse:
            with self.assertRaisesRegex(ValueError, "cannot replace a released-default"):
                self.stage(**self.upload, retained_sdk_inputs_source={})
        reuse.assert_not_called()
        self.fresh.assert_not_called()
        self.released.assert_not_called()

    def test_current_job_routing_skips_replay_but_keeps_signed_bridge_and_context_checks(self):
        from ci.tests.test_product_routing import ProductRoutingTest
        from ci import sdk_native_continuation as routing
        fixture = ProductRoutingTest()
        fixture.setUp()
        fixture.decisions['runtime'] = dict(sdk_handoff_required='true', sdk_input_selection=json.dumps(self.selection))
        value = routing.bind(fixture.decisions, fixture.locator, fixture.expected)
        self.validate.return_value = dict(repository=fixture.producer['repository'], event='pull_request',
            pullRequest=31, validationCommit=fixture.producer['commit'], validationTree=fixture.producer['tree'])
        self.arguments['environ'] = dict(GITHUB_RUN_ID='7', GITHUB_RUN_ATTEMPT='1')
        upload = {**self.upload, 'trusted_workflow_sha': fixture.expected['workflowSha']}
        route = (value, fixture.locator, fixture.expected['planId'])
        self.assertEqual({'synthetic': 'fresh result'}, self.stage(**upload, routing_state=route))
        self.inspect.assert_not_called()
        self.fresh.assert_called_once()
        self.assertEqual(self.selection['contractPayloadSha256'],
                         self.fresh.call_args.kwargs['expected_contract_payload_sha256'])
        self.assertEqual(upload['expected_build_key'], self.fresh.call_args.kwargs['expected_build_key'])
        for field in ('artifact_id', 'artifact_digest', 'state_wave', 'sdk_state_wave'):
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.stage(**upload, routing_state=(value, {**fixture.locator, field: 'changed'}, '41'))
        self.fresh.assert_called_once()

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
            expected_contract_payload_sha256=self.selection["contractPayloadSha256"], reference_runtime=True,
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

    def test_cli_completed_policy_is_explicit_and_rejection_prevents_worker(self):
        import reuse_qualification
        paths = {"plan": self.plan, "discovery-root": self.discovery, "state-root": self.state,
                 "destination": self.destination, "keyring": self.arguments["keyring"],
                 "keys-directory": self.arguments["keys_directory"], "repository-root": self.repository}
        argv = ["javascript", "--phase", "validation"]
        argv += [value for name, path in paths.items() for value in ("--" + name, str(path))]
        argv += [value for name, item in self.upload.items() if name != "expected_metadata_receipt_sha256"
                 for value in ("--" + name.replace("_", "-"), str(item))]
        policy = self.root / "completed-policy.json"
        policy.write_bytes(b"{}\n")
        argv += ["--completed-frozen-policy", str(policy)]
        marker = object()
        @contextmanager
        def selected(arguments):
            self.assertEqual(policy, arguments.pop("completed_frozen_policy"))
            self.assertEqual(self.plan, arguments["plan"])
            yield {"completed_frozen": marker}
        with patch.object(reuse_qualification, "completed_frozen_options", side_effect=selected), \
                patch.object(workflow, "execute_javascript") as worker:
            self.assertEqual(0, workflow.main(argv))
            self.assertIs(marker, worker.call_args.kwargs["completed_frozen"])
        with patch.object(workflow, "execute_javascript") as worker, self.assertRaises(SystemExit):
            workflow.main(argv)  # Real malformed caller-policy gate.
        worker.assert_not_called()

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


    def test_exact_pair_routes_binding_without_capture_and_preserves_current_policy(self):
        pins = _SDK_INPUT_RECOVERY_FIXTURE
        source, runtime = deepcopy(pins["historicalSource"]), deepcopy(pins["runtimeSource"])
        before = deepcopy((source, runtime, self.selection))
        marker = object()
        with patch.object(workflow.sdk_handoff, "capture_reused_sdk_handoff") as capture, \
                patch.object(workflow.sdk_handoff, "stage_sdk_input_binding", return_value=marker) as binding:
            self.assertIs(marker, self.stage(trusted_workflow_sha=self.upload["trusted_workflow_sha"],
                **_sdk_input_recovery_arguments(source, runtime)))
            binding.assert_called_once_with(self.plan, self.destination,
                sdk_inputs_source=pins["compatibleSource"], runtime_source=runtime,
                repository_root=self.repository, environ=self.arguments["environ"])
            capture.assert_not_called()
            self.assertEqual(self.upload["trusted_workflow_sha"],
                             self.inspect.call_args.kwargs["sdk_original_workflow_sha"])
            failure = ValueError("routing plan changed")
            binding.side_effect = failure
            with self.assertRaises(ValueError) as raised:
                self.stage(trusted_workflow_sha=self.upload["trusted_workflow_sha"],
                           **_sdk_input_recovery_arguments(source, runtime))
            self.assertIs(raised.exception, failure)
            capture.assert_not_called()
        self.assertEqual(before, (source, runtime, self.selection))
        self.assertEqual({name: pins[name] for name in
            ("historicalSource", "runtimeSource", "compatibleSource")}, workflow._RETAINED_SDK_INPUT_RECOVERY)
        self.fresh.assert_not_called()
        self.released.assert_not_called()

    def test_every_selector_pin_mutation_keeps_original_reference_route(self):
        pins = _SDK_INPUT_RECOVERY_FIXTURE

        def leaves(value, prefix=()):
            for name, member in value.items():
                if isinstance(member, dict):
                    yield from leaves(member, (*prefix, name))
                else:
                    yield (*prefix, name)

        cases = []
        for which in ("historicalSource", "runtimeSource"):
            for path in leaves(pins[which]):
                pair = deepcopy(pins)
                parent = pair[which]
                for part in path[:-1]:
                    parent = parent[part]
                old = parent[path[-1]]
                parent[path[-1]] = old + 1 if type(old) is int else old + "-changed"
                cases.append((which + "." + ".".join(path), pair))
            pair = deepcopy(pins)
            pair[which]["extra"] = "must not override"
            cases.append((which + ".extra", pair))
        # The genuine historical pair must remain the historical reference route.
        pair = deepcopy(pins)
        pair["runtimeSource"] = deepcopy(pins["historicalRuntime"])
        cases.append(("matching historical Runtime", pair))
        self.assertEqual(27, len(cases))
        for label, pair in cases:
            source, runtime = pair["historicalSource"], pair["runtimeSource"]
            with self.subTest(pin=label), \
                    patch.object(workflow.sdk_handoff, "capture_reused_sdk_handoff") as capture, \
                    patch.object(workflow.sdk_handoff, "stage_sdk_input_binding", return_value=label) as binding:
                options = _sdk_input_recovery_arguments(source, runtime)
                # API shape has exactly six Runtime fields: an extra field cannot
                # be expressed there, so exercise its real producer object instead.
                if label == "runtimeSource.extra":
                    options["runtime_original_producer"] = {**runtime["producer"], "extra": "changed"}
                    runtime = {**runtime, "producer": options["runtime_original_producer"]}
                    runtime.pop("extra")
                self.assertEqual(label, self.stage(trusted_workflow_sha=self.upload["trusted_workflow_sha"],
                                                  **options))
                binding.assert_called_once_with(self.plan, self.destination,
                    sdk_inputs_source=source, runtime_source=runtime,
                    repository_root=self.repository, environ=self.arguments["environ"])
                capture.assert_not_called()
        self.fresh.assert_not_called()
        self.released.assert_not_called()

    def test_private_capture_inventory_reuses_only_unchanged_guarded_bytes(self):
        from products import restore
        from contextlib import nullcontext
        import os
        for session_enabled, defect in ((True, None), (False, None),
                                        (True, "bytes-restored-mtime"), (True, "symlink"),
                                        (True, "during-scan")):
            cache_enabled = session_enabled and not restore._is_windows()
            captured = {}
            def capture(plan, destination, **kwargs):
                destination.mkdir()
                body = destination / "body.bin"
                body.write_bytes(b"fixture private authenticated content")
                captured.update(root=destination, body=body)
            original_scanner = restore._uncached_file_inventory
            def scan(path, **kwargs):
                records = original_scanner(path, **kwargs)
                if defect == "during-scan":
                    captured["body"].write_bytes(b"changed during first captured scan")
                return records
            with self.subTest(session=session_enabled, defect=defect), \
                    patch.object(workflow, "_selection", return_value=(
                        {"validationCommit": self.revision},
                        {"source": "current-runtime", "contractPayloadSha256": "sha256:" + "a" * 64},
                        self.plan.read_bytes())), \
                    patch.object(workflow.product_reuse, "capture_sdk_inputs_upload", side_effect=capture), \
                    patch.object(workflow, "verified_apple_original_inputs", side_effect=lambda *a, **k: nullcontext({})), \
                    patch.object(restore, "_uncached_file_inventory", side_effect=scan) as scanner, \
                    patch.object(workflow, "regular_file_inventory", side_effect=lambda path, **kw: restore._uncached_file_inventory(path, **kw)), \
                    (restore.verification_session() if session_enabled else nullcontext()):
                def consume():
                    with workflow.verified_inputs(self.plan, self.discovery, self.state,
                            **self.arguments, **self.upload_for_capture()) as inputs:
                        self.assertEqual(captured["root"], inputs["capture"])
                        self.assertTrue(inputs["capture"].exists())
                        body = captured["body"]
                        if defect == "bytes-restored-mtime":
                            before = body.stat()
                            body.write_bytes(b"x" * before.st_size)
                            os.utime(body, ns=(before.st_atime_ns, before.st_mtime_ns))
                        elif defect == "symlink":
                            target = self.root / "outside-capture.bin"
                            target.write_bytes(body.read_bytes())
                            body.unlink()
                            body.symlink_to(target)
                if defect is None:
                    consume()
                    self.assertEqual(1 if cache_enabled else 3, scanner.call_count)
                else:
                    with self.assertRaises(ValueError):
                        consume()
                    self.assertGreaterEqual(scanner.call_count, 1)
                    if defect == "bytes-restored-mtime":
                        self.assertEqual(2 if cache_enabled else 3, scanner.call_count)
                self.assertFalse(captured["root"].exists())
            self.assertIsNone(restore._VERIFICATION_SESSION.get())

if __name__ == "__main__":
    unittest.main()
