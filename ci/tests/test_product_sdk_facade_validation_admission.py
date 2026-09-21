"""Actual planner/process/inventory replay; signature and Git boundaries mocked.

No fixture claims an observed worker, authentic signed inputs or compilation.
"""

from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

from ci.products import contract_projection, sdk_facade_validation_admission as admission
from ci.products import sdk_facade_inputs, sdk_facade_validation
from ci.products.inventory import canonical_json_bytes, load_canonical_json_bytes, sha256_bytes, sha256_file
from ci.products.receipt import write_output_manifest
from ci.products.registry import PhaseInstanceId
from ci.tests import test_sdk_facade_inputs as fixtures
from ci.tests.product_chain_support import write_receipt


class FacadeOriginalContentTest(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.FacadeInputsTest(methodName="runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.root = self.f.root
        self.contract_path = Path(self.f.evidence["phaseReceipt"])
        manifest = load_canonical_json_bytes((self.f.f.contract / "output-manifest.json").read_bytes())
        self.contract = write_receipt(self.contract_path, product="contract", component="contract", phase="metadata",
            target="common", version="0.8.2", version_identity="0.8.2", outputs=manifest["outputs"], upstream=[],
            context={"producer": self.f.producer})
        self.f.projection["receiptSha256"] = sha256_file(self.contract_path)
        self.inputs = self.root / "original-inputs"
        self.info = sdk_facade_inputs.prepare_facade_validation_inputs(self.f.request, self.inputs)
        self.projection = contract_projection.VerifiedContractProjection(
            deepcopy(self.info["contractProjection"]), contract_projection._VERIFIED)
        self.versions = {"contract": "0.8.2", "sdk": "0.8.7", "runtime-release": "0.8.9",
                         "runtime-compatibility": "0.8.0"}
        self.inventory = [{"relativePath": "fixture/original.txt", "bytes": 8, "sha256": sha256_bytes(b"original")}]
        self.instance = PhaseInstanceId("sdk", "sdk-core", "validation", "jvm")
        self.plan = admission.plan_phase(self.instance, inventory=self.inventory, versions=self.versions,
            upstream_receipts=[self.f.package_value, self.contract], contract_projection=self.projection,
            toolchain_profile_digest=admission.NOT_APPLICABLE_TOOLCHAIN_DIGEST,
            flags_digest=admission.NOT_APPLICABLE_FLAGS_DIGEST, output_schema_version=1)
        self.context = {"repositoryRoot": "/original checkout", "androidSdkDirectory": "/original Android SDK"}
        self.process_context, self.original_execution, _, _ = admission._context(
            self.context, {"producer": self.f.producer, "target": "jvm"})
        self.f.f.context = deepcopy(self.process_context)
        self.f.f.capture("jvm")
        arguments = self.content_arguments()
        self.content = sdk_facade_validation.verify_facade_consumer_evidence(**arguments)
        self.stage = self.root / "validation-stage"
        output = self.stage / admission.OUTPUT_PATH
        output.parent.mkdir(parents=True)
        output.write_bytes(canonical_json_bytes(self.content))
        manifest = write_output_manifest(self.stage, "sdk", "sdk-core", "validation", "jvm", "0.8.7",
                                         {admission.OUTPUT_KIND: "outputs/validation"})
        self.receipt_path = self.root / "validation.json"
        self.receipt = write_receipt(self.receipt_path, product="sdk", component="sdk-core", phase="validation",
            target="jvm", version="0.8.7", version_identity="0.8.7", outputs=manifest["outputs"], upstream=[],
            context={"producer": self.f.producer, "plan_factory": lambda *args: self.plan})
        self.consumer = self.root / "consumer-inputs"
        self.consumer.mkdir()
        (self.consumer / "retained.kt").write_bytes(b"mocked only at signed source/init gate\n")
        self.compiler_inputs = self.root / "compiler-inputs.json"
        self.compiler_inputs.write_bytes(b"mocked only at signed compiler-input gate\n")
        self.arguments = dict(repository=self.root, validation_stage=self.stage, validation_receipt=self.receipt_path,
            facade_request=self.f.request, prepared_inputs=self.inputs, execution_directory=self.f.f.evidence,
            consumer_inputs=self.consumer, compiler_inputs=self.compiler_inputs, original_context=self.context,
            tooling_evidence=self.root / "tooling", tooling_public_key=self.root / "tooling.pub",
            java_executable=self.root / "java", policy_revision="e" * 40, required_trust_domain="development")
        self.enterContext(patch.object(admission, "run_git", side_effect=lambda root, cmd, rev:
            self.f.producer["tree" if rev.endswith("{tree}") else "commit"]))
        self.enterContext(patch.object(admission, "git_product_versions", return_value=self.versions))
        self.enterContext(patch.object(admission, "git_regular_blob_bytes", return_value=b"0.8.9\n"))
        self.enterContext(patch.object(admission, "phase_git_inventory", return_value=self.inventory))
        self.projection_gate = self.enterContext(patch.object(admission, "_contract_projection_from_request",
                                                            return_value=self.projection))
        self.enterContext(patch.object(admission, "_request_inventory", side_effect=lambda path: {path: sha256_file(path)}))
        self.capture = self.enterContext(patch.object(admission, "capture_facade_validation_sources", side_effect=self.capture_source))
        self.tooling = self.enterContext(patch.object(admission, "_verify_sdk_apple_with_tooling", side_effect=self.verify_tooling))
        self.compiler_policy = self.enterContext(patch.object(admission, "verify_facade_kotlin_compiler_artifacts"))

    def content_arguments(self):
        return dict(evidence_directory=self.f.f.evidence, target="jvm", sdk_version="0.8.7", runtime_version="0.8.9",
            contract_version="0.8.2", package_stage=self.inputs / "package-stage", contract_stage=self.inputs / "contract-stage",
            imported_repository=self.inputs / "maven-repository", expected_package_inventory=self.info["inventories"]["package"],
            expected_contract_inventory=self.info["inventories"]["contract"],
            expected_repository_inventory=self.info["inventories"]["repository"],
            expected_contract_projection=self.info["contractProjection"], original_context=self.process_context)

    def capture_source(self, repository, revision, destination):
        self.assertEqual((self.root, self.f.producer["commit"]), (repository, revision))
        path = destination / "gradle/libs.versions.toml"
        path.parent.mkdir(parents=True)
        path.write_bytes(b'[versions]\nkotlin = "2.2.0"\n')
        return {"tree": self.f.producer["tree"], "files": admission._inventory(destination)}

    def verify_tooling(self, **kwargs):
        self.assertEqual("verify-original-sdk-facade-consumer-inputs", kwargs["command_name"])
        self.assertEqual(self.arguments["policy_revision"], kwargs["policy_revision"])
        self.assertEqual("development", kwargs["required_trust_domain"])
        snapshots = {key: pair[0] for key, pair in kwargs["sources"].items()}
        values = kwargs["argument_builder"](snapshots, kwargs["expected_paths"], self.root / "mocked-tooling-work")
        self.assertEqual(self.compiler_inputs, values["compiler-inputs"])
        self.assertEqual(self.original_execution, values["original-execution-directory"])
        self.assertEqual(self.context["androidSdkDirectory"], values["android-sdk-directory"])
        self.assertEqual("2.2.0", values["kotlin-version"])
        self.assertEqual("/original checkout", values["forbidden-path"])
        self.assertEqual("jvm", values["target"])
        self.assertNotEqual(self.f.f.package, values["package-stage"])

    def verify(self, **changes):
        return admission.verify_sdk_facade_validation_original_content(**{**self.arguments, **changes})

    def test_full_composition_real_key_and_process_gate_preserve_exact_original_receipt(self):
        before = admission._inventory(self.root, allow_empty=True)
        verified, raw = self.verify()
        self.assertEqual(self.receipt_path.read_bytes(), raw)
        self.assertEqual(self.receipt, verified)
        self.tooling.assert_called_once()
        self.compiler_policy.assert_called_once_with(repository=self.root,
            policy_revision=self.arguments["policy_revision"], compiler_inputs=self.compiler_inputs)
        self.projection_gate.assert_called_once()
        self.assertEqual(before, admission._inventory(self.root, allow_empty=True))
        self.assertIs(type(verified), dict)

    def test_unpinned_compiler_rejects_before_semantic_tool_execution(self):
        self.compiler_policy.side_effect = ValueError("compiler pin differs")
        with self.assertRaisesRegex(ValueError, "compiler pin differs"):
            self.verify()
        self.tooling.assert_not_called()

    def test_immutable_source_versions_plan_or_predecessor_mismatch_reject(self):
        for name, replacement in (("run_git", "f" * 40),
            ("git_regular_blob_bytes", b"0.8.8\n"),
            ("phase_git_inventory", [{**self.inventory[0], "sha256": "sha256:" + "f" * 64}])):
            with self.subTest(name=name), patch.object(admission, name, return_value=replacement), self.assertRaises(ValueError):
                self.verify()
        with patch.object(admission, "git_product_versions", return_value={**self.versions, "sdk": "0.8.8"}), \
                self.assertRaisesRegex(ValueError, "versions"):
            self.verify()
        forged = deepcopy(self.f.projection)
        forged["receiptSha256"] = "sha256:" + "f" * 64
        self.projection_gate.return_value = contract_projection.VerifiedContractProjection(forged, contract_projection._VERIFIED)
        with self.assertRaisesRegex(ValueError, "Contract projection"):
            self.verify()

    def test_input_union_source_gate_and_raw_process_are_all_mandatory(self):
        original_gate = self.f.package_gate.side_effect
        self.f.package_gate.side_effect = ValueError("full original package gate failed")
        with self.assertRaisesRegex(ValueError, "full original package gate"):
            self.verify()
        self.f.package_gate.side_effect = original_gate
        marker = self.inputs / "maven-repository/extra.jar"
        marker.write_bytes(b"unrelated injected artifact")
        with self.assertRaisesRegex(ValueError, "prepared inputs"):
            self.verify()
        marker.unlink()
        with patch.object(admission, "_verify_sdk_apple_with_tooling", side_effect=ValueError("signed gate failed")), \
                self.assertRaisesRegex(ValueError, "signed gate failed"):
            self.verify()
        record = self.f.f.execution
        record["exitCode"] = 9
        self.f.f.write("process/execution.json", record)
        with self.assertRaises(ValueError):
            self.verify()

    def test_context_is_strict_and_windows_paths_remain_lexical_not_replay_paths(self):
        for value in ({}, {**self.context, "command": []}, {**self.context, "repositoryRoot": "relative"},
                      {**self.context, "androidSdkDirectory": "bad\npath"}):
            with self.subTest(context=value), self.assertRaises(ValueError):
                self.verify(original_context=value)
        context, execution, original, android = admission._context(
            {"repositoryRoot": r"C:\original checkout", "androidSdkDirectory": r"C:\Android SDK",
             "javaExecutable": r"C:\original Java\bin\java.exe"}, self.receipt)
        self.assertEqual(r"C:\original checkout\gradlew.bat", context["gradleWrapper"])
        self.assertEqual(r"C:\original Java\bin\java.exe", context["javaExecutable"])
        self.assertTrue(execution.endswith("\\jvm\\execution"))
        self.assertEqual(r"C:\original checkout", original)
        self.assertEqual(r"C:\Android SDK", android)

    def test_original_windows_requires_explicit_exact_launcher_and_posix_remains_unchanged(self):
        windows = {"repositoryRoot": r"C:\original checkout", "androidSdkDirectory": r"C:\Android SDK"}
        for value in (windows, {**windows, "javaExecutable": None},
                      {**windows, "javaExecutable": r"java.exe"},
                      {**windows, "javaExecutable": "/current/host/java.exe"},
                      {**windows, "javaExecutable": r"C:\Java\bin\java"},
                      {**windows, "javaExecutable": r"C:\Java\..\bin\java.exe"},
                      {**self.context, "javaExecutable": r"C:\Java\bin\java.exe"}):
            with self.subTest(context=value), self.assertRaises(ValueError):
                admission._context(value, self.receipt)
        context, _, _, _ = admission._context(self.context, self.receipt)
        self.assertEqual("/original checkout/gradlew", context["gradleWrapper"])
        self.assertNotIn("javaExecutable", context)

    def test_original_windows_process_is_exact_java_wrapper_command_not_legacy_bare_wrapper(self):
        original = {"repositoryRoot": r"C:\original checkout", "androidSdkDirectory": "",
                    "javaExecutable": r"C:\original Java\bin\java.exe"}
        context, _, _, _ = admission._context(original, self.receipt)
        self.f.f.context = context
        self.f.f.capture("jvm")
        record = self.f.f.execution
        wrapper_jar = str(admission.PureWindowsPath(original["repositoryRoot"]) / "gradle/wrapper/gradle-wrapper.jar")
        bare = deepcopy(record)
        record["command"] = [original["javaExecutable"], "-Xmx64m", "-Xms64m",
                             "-Dorg.gradle.appname=gradlew", "-jar", wrapper_jar, *record["command"][1:]]
        self.f.f.write("process/execution.json", record)
        arguments = {**self.content_arguments(), "original_context": context}
        self.assertEqual(self.content, sdk_facade_validation.verify_facade_consumer_evidence(**arguments))
        for bad in (bare, {**record, "command": ["cmd.exe", "/c", *bare["command"]]},
                    {**record, "command": [r"C:\other\java.exe", *record["command"][1:]]}):
            self.f.f.write("process/execution.json", bad)
            with self.subTest(command=bad["command"]), self.assertRaises(ValueError):
                sdk_facade_validation.verify_facade_consumer_evidence(**arguments)

    def test_late_original_private_or_caller_mutation_rejects_without_returning_receipt(self):
        original_context = deepcopy(self.context)
        original_receipt = self.receipt_path.read_bytes()
        for mutate in (
            lambda kw: self.context.update(androidSdkDirectory="/changed"),
            lambda kw: self.receipt_path.write_bytes(b"changed\n"),
            lambda kw: (kw["sources"]["consumer"][0] / "retained.kt").write_bytes(b"changed\n"),
        ):
            def gate(**kwargs):
                self.verify_tooling(**kwargs)
                mutate(kwargs)
            self.tooling.side_effect = gate
            with self.subTest(mutation=mutate), self.assertRaises(ValueError):
                self.verify()
            self.context.clear()
            self.context.update(original_context)
            self.receipt_path.write_bytes(original_receipt)

    def test_stage_and_receipt_outputs_must_equal_recomputed_content(self):
        path = self.stage / admission.OUTPUT_PATH
        altered = {**self.content, "packageOutputsDigest": "sha256:" + "f" * 64}
        path.write_bytes(canonical_json_bytes(altered))
        write_output_manifest(self.stage, "sdk", "sdk-core", "validation", "jvm", "0.8.7",
                              {admission.OUTPUT_KIND: "outputs/validation"})
        with self.assertRaisesRegex(ValueError, "canonical stage/receipt"):
            self.verify()
