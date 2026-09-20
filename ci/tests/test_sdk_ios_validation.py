"""Property translation only: synthetic paths are not authenticated Apple inputs."""

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import product_reuse
import sdk_ios_validation
from products.inventory import load_canonical_json_bytes, regular_file_inventory, sha256_bytes
from products.receipt import write_output_manifest
from ci.tests.product_chain_support import write_receipt

validation_properties = sdk_ios_validation.validation_properties


class SdkIosValidationTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sdk-ios-validation-mapper-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.package = self.root / "original-package"
        self.contract = self.root / "original-contract"
        self.application = self.root / "original-test-application"
        self.consumers = self.root / "original-compiler-consumers"
        self.consumers.mkdir()
        for name in ("CodexFailureSwiftConsumer.swift", "CodexFailureObjectiveCConsumer.m"):
            (self.consumers / name).write_bytes(b"original compiler consumer fixture\n")
        for stage in (self.package, self.contract, self.application):
            stage.mkdir()
            (stage / "original.bin").write_bytes(b"unchanged original fixture\n")
        self.compatibility = self.root / "sdk-compatibility.json"
        self.compatibility.write_bytes(b"opaque caller-authenticated compatibility fixture\n")
        self.arguments = dict(target="ios-arm64", sdk_version="0.8.1", contract_version="0.8.0",
            candidate_tree="a" * 40, package_stage=self.package, contract_binary_stage=self.contract,
            sdk_compatibility=self.compatibility, test_application=self.application,
            compiler_consumers=self.consumers)

    def translate(self, **changes):
        return validation_properties(**{**self.arguments, **changes})

    def test_both_exact_targets_forward_only_original_validation_properties(self):
        before = {path.relative_to(self.root): path.read_bytes()
                  for path in self.root.rglob("*") if path.is_file()}
        for target in ("ios-arm64", "ios-simulator-arm64"):
            with self.subTest(target=target):
                self.assertEqual({
                    "codexAgent.product": "sdk", "codexAgent.component": "sdk-ios",
                    "codexAgent.phase": "validation", "codexAgent.target": target,
                    "codexAgent.iosValidationPackageStage": str(self.package),
                    "codexAgent.contractBinaryStage": str(self.contract),
                    "codexAgent.sdkCompatibilityFile": str(self.compatibility),
                    "codexAgent.iosValidationTestApplicationDirectory": str(self.application),
                    "codexAgent.iosValidationCompilerConsumersDirectory": str(self.consumers),
                    "codexAgent.sdkVersion": "0.8.1", "codexAgent.contractVersion": "0.8.0",
                    "codexAgent.candidateTree": "a" * 40,
                }, self.translate(target=target))
        self.assertEqual(before, {path.relative_to(self.root): path.read_bytes()
                                 for path in self.root.rglob("*") if path.is_file()})

    def test_invalid_target_versions_and_tree_are_not_coerced(self):
        cases = [("target", value) for value in (None, [], "ios", "iosArm64", "macos-arm64")]
        cases += [(field, value) for field in ("sdk_version", "contract_version")
                  for value in (None, 8, "", "0.8", " 0.8.0", "latest")]
        cases += [("candidate_tree", value) for value in
                  (None, 40, "", "A" * 40, "a" * 39, "a" * 64, "../original-package")]
        for field, value in cases:
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.translate(**{field: value})

    def test_directory_inputs_reject_missing_wrong_type_relative_alias_and_escape(self):
        alias = self.root / "package-alias"
        alias.symlink_to(self.package, target_is_directory=True)
        parent_alias = self.root / "parent-alias"
        parent_alias.symlink_to(self.root, target_is_directory=True)
        for field in ("package_stage", "contract_binary_stage", "test_application", "compiler_consumers"):
            for value in (None, str(self.package), Path("relative"), self.root / "missing",
                          self.compatibility, alias, parent_alias / "original-package",
                          self.package / ".." / "original-contract"):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    self.translate(**{field: value})

    def test_both_targets_require_the_caller_test_application(self):
        for target in ("ios-arm64", "ios-simulator-arm64"):
            arguments = {**self.arguments, "target": target}
            del arguments["test_application"]
            with self.subTest(target=target), self.assertRaises(TypeError):
                validation_properties(**arguments)
            with self.subTest(target=target, application=None), self.assertRaises(ValueError):
                self.translate(target=target, test_application=None)

    def test_compatibility_requires_nonempty_regular_original_file(self):
        empty = self.root / "empty.json"
        empty.write_bytes(b"")
        alias = self.root / "compatibility-alias"
        alias.symlink_to(self.compatibility)
        parent_alias = self.root / "parent-alias"
        parent_alias.symlink_to(self.root, target_is_directory=True)
        for value in (None, str(self.compatibility), Path("relative.json"), self.root / "missing",
                      self.package, empty, alias, parent_alias / self.compatibility.name,
                      self.package / ".." / self.compatibility.name):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.translate(sdk_compatibility=value)

    def test_both_targets_require_the_compiler_consumers_directory(self):
        for target in ("ios-arm64", "ios-simulator-arm64"):
            arguments = {**self.arguments, "target": target}
            del arguments["compiler_consumers"]
            with self.subTest(target=target), self.assertRaises(TypeError):
                validation_properties(**arguments)

    def test_both_named_compiler_consumers_must_be_nonempty_regular_original_files(self):
        for name in ("CodexFailureSwiftConsumer.swift", "CodexFailureObjectiveCConsumer.m"):
            for mutation in ("missing", "empty", "linked", "directory"):
                with self.subTest(name=name, mutation=mutation):
                    member = self.consumers / name
                    original = member.read_bytes()
                    member.unlink()
                    try:
                        if mutation == "empty":
                            member.write_bytes(b"")
                        elif mutation == "linked":
                            member.symlink_to(self.compatibility)
                        elif mutation == "directory":
                            member.mkdir()
                        with self.assertRaises(ValueError):
                            self.translate()
                    finally:
                        if member.is_symlink() or member.is_file():
                            member.unlink()
                        elif member.is_dir():
                            member.rmdir()
                        member.write_bytes(original)


class SdkIosValidationExecutionTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sdk-ios-validation-worker-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.producer = {
            "repository": "owner/repository",
            "workflowPath": ".github/workflows/product-validation.yml",
            "commit": "a" * 40,
            "tree": "b" * 40,
            "event": "pull_request",
            "runId": 7,
            "runAttempt": 2,
            "pullRequest": 3,
        }
        self.plan = {
            "schemaVersion": 1,
            "product": "sdk",
            "component": "sdk-ios",
            "phase": "validation",
            "target": "ios-arm64",
            "buildKey": "sha256:" + "c" * 64,
            "inputs": {},
        }
        self.package = self.root / "original-package"
        (self.package / "outputs/apple").mkdir(parents=True)
        (self.package / "outputs/apple/package.zip").write_bytes(b"authenticated package\x00\xff")
        self.compatibility = self.package / "outputs/evidence/sdk-compatibility.json"
        self.compatibility.parent.mkdir()
        self.compatibility.write_bytes(b"authenticated SDK compatibility\n")
        package_manifest = write_output_manifest(
            self.package, "sdk", "sdk-ios", "package", "ios", "0.8.0",
            {"apple": "outputs/apple", "evidence": "outputs/evidence"},
        )
        self.package_receipt = self.root / "package-receipt.json"
        self.package_value = write_receipt(
            self.package_receipt, product="sdk", component="sdk-ios", phase="package", target="ios",
            version="0.8.0", version_identity="0.8.0", outputs=package_manifest["outputs"],
            upstream=[], context={"producer": self.producer},
        )
        self.contract = self.root / "original-contract"
        (self.contract / "outputs/evidence").mkdir(parents=True)
        (self.contract / "outputs/evidence/canonical-api.json").write_bytes(b"authenticated API\n")
        (self.contract / "outputs/evidence/canonical-coverage.json").write_bytes(b"authenticated coverage\n")
        contract_manifest = write_output_manifest(
            self.contract, "contract", "contract", "binary", "common", "0.2.0",
            {"contract-evidence": "outputs/evidence"},
        )
        self.contract_receipt = self.root / "contract-receipt.json"
        self.contract_value = write_receipt(
            self.contract_receipt, product="contract", component="contract", phase="binary", target="common",
            version="0.2.0", version_identity="0.2.0", outputs=contract_manifest["outputs"],
            upstream=[], context={"producer": self.producer},
        )
        self.package_record = {
            "stage": self.package, "receiptPath": self.package_receipt, "receipt": self.package_value,
        }
        self.contract_record = {
            "stage": self.contract, "receiptPath": self.contract_receipt, "receipt": self.contract_value,
        }
        self.application = self.root / "validation-source/TestApp"
        self.application.mkdir(parents=True)
        (self.application / "CodexAgentTestApp.xcodeproj").mkdir()
        (self.application / "CodexAgentTestApp.xcodeproj/project.pbxproj").write_bytes(b"project\n")
        self.consumers = self.root / "validation-source/CompilerEvidence"
        self.consumers.mkdir()
        for name in ("CodexFailureSwiftConsumer.swift", "CodexFailureObjectiveCConsumer.m"):
            (self.consumers / name).write_bytes(f"authenticated {name}\n".encode())
        self.destination = self.root / "build/validation-worker"
        self.ios_build = self.root / "codex-agent-runtime-ios/build"
        self.validation_root = self.ios_build / (
            f"imported-sdk-validation/{self.producer['tree']}/{self.plan['target']}"
        )
        self.archive = self.validation_root / "execution-envelope/apple-validation-evidence.zip"
        self.return_code = 0
        self.launch_error = False
        self.archive_mode = "valid"
        self.after_process = lambda _fields: None
        self.process_calls = []

    def process(self, command, **arguments):
        self.process_calls.append(command)
        self.assertEqual(self.root, arguments["cwd"])
        self.assertEqual({"SAFE": "fixed environment"}, arguments["env"])
        self.assertEqual(subprocess.STDOUT, arguments["stderr"])
        self.assertFalse(arguments["check"])
        self.assertEqual(".", command[command.index("-p") + 1])
        self.assertIn(sdk_ios_validation.TASK, command)
        self.assertNotIn("ciProductPhase", command)
        fields = dict(value[2:].split("=", 1) for value in command if value.startswith("-P"))
        self.assertEqual({
            "product": "sdk", "component": "sdk-ios", "phase": "validation",
            "target": self.plan["target"],
        }, {name: fields[f"codexAgent.{name}"] for name in ("product", "component", "phase", "target")})
        self.assertEqual(self.producer["commit"], fields["codexAgent.candidateCommit"])
        self.assertEqual(self.producer["tree"], fields["codexAgent.candidateTree"])
        self.assertEqual(str(self.package), fields["codexAgent.iosValidationPackageStage"])
        self.assertEqual(str(self.contract), fields["codexAgent.contractBinaryStage"])
        self.assertEqual(str(self.compatibility), fields["codexAgent.sdkCompatibilityFile"])
        self.assertEqual(str(self.application), fields["codexAgent.iosValidationTestApplicationDirectory"])
        self.assertEqual(str(self.consumers), fields["codexAgent.iosValidationCompilerConsumersDirectory"])
        arguments["stdout"].write(b"raw validation diagnostics\x00\xff\n")
        if self.launch_error:
            raise OSError("synthetic validation launch failure")
        if self.return_code == 0 and self.archive_mode != "missing":
            self.archive.parent.mkdir(parents=True)
            if self.archive_mode == "symlink":
                self.archive.symlink_to(self.compatibility)
            else:
                self.archive.write_bytes(
                    b"" if self.archive_mode == "empty"
                    else b"PK\x03\x04raw validation evidence\x00\xff"
                )
            if self.archive_mode == "extra":
                (self.archive.parent / "unexpected.bin").write_bytes(b"unexpected evidence\n")
        self.after_process(fields)
        return subprocess.CompletedProcess(command, self.return_code)

    def execute(self, **changes):
        arguments = {
            "producer": self.producer,
            "sdk_version": "0.8.0",
            "package_stage": self.package_record,
            "contract_binary_stage": self.contract_record,
            "sdk_compatibility": self.compatibility,
            "test_application": self.application,
            "compiler_consumers": self.consumers,
            "repository_root": self.root,
            "destination": self.destination,
            "environ": {},
        }
        arguments.update(changes)
        with patch("native_wrappers.host_classifier", return_value="macos-arm64"), \
                patch.object(product_reuse, "_runtime_worker_environment",
                             return_value=({"SAFE": "fixed environment"}, self.root / "gradlew")), \
                patch.object(product_reuse, "_runtime_worker_checkout") as checkout, \
                patch.object(sdk_ios_validation.subprocess, "run", side_effect=self.process):
            result = sdk_ios_validation.execute(self.plan, **arguments)
        self.checkout = checkout
        return result

    def cleanup_outputs(self):
        shutil.rmtree(self.root / "codex-agent-runtime-ios", ignore_errors=True)
        shutil.rmtree(self.destination, ignore_errors=True)

    def test_fixed_imported_archive_task_preserves_raw_evidence_and_emits_no_admission(self):
        originals = {
            "package": regular_file_inventory(self.package),
            "contract": regular_file_inventory(self.contract),
            "application": regular_file_inventory(self.application),
            "consumers": regular_file_inventory(self.consumers),
        }
        result = self.execute()
        self.assertEqual({"evidenceArchive", "diagnostics", "evidenceSha256"}, set(result))
        self.assertEqual(self.archive, result["evidenceArchive"])
        self.assertEqual(self.destination, result["diagnostics"])
        self.assertEqual(sha256_bytes(self.archive.read_bytes()), result["evidenceSha256"])
        self.assertFalse({"receipt", "receiptPath", "stage", "admission"} & set(result))
        self.assertEqual(b"raw validation diagnostics\x00\xff\n", (self.destination / "gradle.log").read_bytes())
        execution = load_canonical_json_bytes((self.destination / "execution.json").read_bytes())
        self.assertEqual(sdk_ios_validation.TASK, execution["command"][execution["command"].index(sdk_ios_validation.TASK)])
        self.assertEqual(0, execution["returnCode"])
        self.assertIsNone(execution["launchError"])
        self.assertEqual(originals["package"], regular_file_inventory(self.package))
        self.assertEqual(originals["contract"], regular_file_inventory(self.contract))
        self.assertEqual(originals["application"], regular_file_inventory(self.application))
        self.assertEqual(originals["consumers"], regular_file_inventory(self.consumers))
        self.assertGreaterEqual(self.checkout.call_count, 3)

    def test_nonzero_and_launch_failure_preserve_raw_process_diagnostics_only(self):
        for launch in (False, True):
            self.cleanup_outputs()
            self.destination = self.root / f"build/failure-{launch}"
            self.return_code, self.launch_error = 7, launch
            with self.subTest(launch=launch), self.assertRaisesRegex(
                OSError if launch else ValueError,
                "launch failure" if launch else "exit code 7",
            ):
                self.execute()
            self.assertEqual(b"raw validation diagnostics\x00\xff\n", (self.destination / "gradle.log").read_bytes())
            execution = load_canonical_json_bytes((self.destination / "execution.json").read_bytes())
            self.assertEqual(None if launch else 7, execution["returnCode"])
            self.assertEqual("synthetic validation launch failure" if launch else None,
                             execution["launchError"])
            self.assertFalse(self.archive.exists())

    def test_missing_empty_extra_and_symlink_archive_outputs_are_rejected(self):
        for mode in ("missing", "empty", "extra", "symlink"):
            self.cleanup_outputs()
            self.destination = self.root / f"build/archive-{mode}"
            self.archive_mode = mode
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                self.execute()
            self.assertEqual(1, len(self.process_calls))
            self.process_calls.clear()

    def test_originals_election_and_private_bytecode_are_rechecked_after_execution(self):
        cases = {
            "package": self.package / "outputs/apple/package.zip",
            "contract": self.contract / "outputs/evidence/canonical-api.json",
            "compatibility": self.compatibility,
            "application": self.application / "CodexAgentTestApp.xcodeproj/project.pbxproj",
            "consumer": self.consumers / "CodexFailureSwiftConsumer.swift",
            "bytecode": None,
        }
        for name, path in cases.items():
            self.cleanup_outputs()
            self.destination = self.root / f"build/mutation-{name}"
            if name == "bytecode":
                path = self.destination / "python-bytecode/injected.pyc"
            original = path.read_bytes() if path.exists() else None
            def mutate(_fields, target=path):
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b"changed during validation execution\n")
            self.after_process = mutate
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "changed|bytecode"):
                self.execute()
            if original is None:
                shutil.rmtree(path.parent, ignore_errors=True)
            else:
                path.write_bytes(original)

        for name, value in (("plan", self.plan), ("producer", self.producer)):
            self.cleanup_outputs()
            self.destination = self.root / f"build/mutation-{name}"
            original = dict(value)
            self.after_process = lambda _fields, target=value: target.update(buildKey="sha256:" + "d" * 64)
            if name == "producer":
                self.after_process = lambda _fields, target=value: target.update(tree="d" * 40)
            try:
                with self.subTest(name=name), self.assertRaisesRegex(ValueError, "input changed"):
                    self.execute()
            finally:
                value.clear(); value.update(original)

    def test_mapper_cannot_mutate_an_original_before_execution(self):
        original = (self.consumers / "CodexFailureSwiftConsumer.swift").read_bytes()
        mapper = sdk_ios_validation.validation_properties

        def mutate(**arguments):
            result = mapper(**arguments)
            (self.consumers / "CodexFailureSwiftConsumer.swift").write_bytes(b"changed by mapper\n")
            return result

        try:
            with patch.object(sdk_ios_validation, "validation_properties", side_effect=mutate), \
                    self.assertRaisesRegex(ValueError, "input changed"):
                self.execute()
        finally:
            (self.consumers / "CodexFailureSwiftConsumer.swift").write_bytes(original)
        self.assertEqual([], self.process_calls)
        self.assertFalse(self.destination.exists())

    def test_wrong_identity_version_host_and_stale_outputs_never_execute(self):
        for changed in (
            {"component": "sdk-core"}, {"phase": "package"}, {"target": "ios"},
        ):
            plan = self.plan
            self.plan = {**plan, **changed}
            try:
                with self.subTest(changed=changed), self.assertRaisesRegex(ValueError, "identity"):
                    self.execute()
            finally:
                self.plan = plan
        with self.assertRaisesRegex(ValueError, "package version"):
            self.execute(sdk_version="0.9.0")
        with self.assertRaisesRegex(ValueError, "outputs overlap"):
            self.execute(destination=self.validation_root)
        with patch("native_wrappers.host_classifier", return_value="macos-x64"), \
                patch.object(sdk_ios_validation.subprocess, "run") as process, \
                self.assertRaisesRegex(ValueError, "macOS ARM64"):
            sdk_ios_validation.execute(
                self.plan, producer=self.producer, sdk_version="0.8.0",
                package_stage=self.package_record, contract_binary_stage=self.contract_record,
                sdk_compatibility=self.compatibility, test_application=self.application,
                compiler_consumers=self.consumers, repository_root=self.root,
                destination=self.destination, environ={},
            )
        process.assert_not_called()
        stale = self.validation_root
        stale.mkdir(parents=True)
        (stale / "sentinel").write_bytes(b"preserve\n")
        with self.assertRaisesRegex(ValueError, "fresh"):
            self.execute()
        self.assertEqual(b"preserve\n", (stale / "sentinel").read_bytes())


if __name__ == "__main__":
    unittest.main()
