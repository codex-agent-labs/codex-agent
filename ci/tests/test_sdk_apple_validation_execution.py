"""Gate composition tests with mocked leaves, not genuine Apple evidence."""

from contextlib import ExitStack, contextmanager
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci.products import sdk_apple_validation_execution as gate
from ci.products.inventory import canonical_json_bytes, regular_file_inventory, sha256_file
from ci.products.receipt import write_output_manifest
from ci.tests.product_chain_support import write_receipt
import ci.tests.test_sdk_apple_validation_content as content_fixture
import ci.tests.test_sdk_apple_validation_evidence as archive_fixture


class AppleValidationExecutionTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.evidence = self.root / "evidence"
        self.product = self.root / "product"
        for directory in (self.evidence / "device-package", self.evidence / "consumer", self.product):
            directory.mkdir(parents=True)
            (directory / "file").write_bytes(b"unchanged")
        self.files = {}
        for name in ("sdk_compatibility", "canonical_api", "canonical_coverage"):
            self.files[name] = self.root / name
            self.files[name].write_bytes(b"original expected input")
        self.sources = {"testApplicationInventory": [{"source": "immutable"}],
                        "toolchain": {"pin": "immutable"}}
        self.arguments = dict(evidence_root=self.evidence, product_directory=self.product,
            sdk_version="0.8.0", **self.files, repository=self.root, source_revision="a" * 40,
            original_working_directory="/original/project", original_device_work_directory="/original/device",
            original_test_application_directory="/original/consumer/CodexAgentTestApp",
            developer_directory="/original/Xcode", tooling_evidence=self.root / "tooling",
            tooling_public_key=self.root / "key", java_executable=self.root / "java",
            policy_revision="b" * 40, required_trust_domain="release")
        self.calls = []

    def run_gate(self, failure=None, mutation=None):
        leaves = (
            "verify_apple_validation_sources", "read_apple_validation_simulator_policy",
            "verify_sdk_apple_validation_binding_content", "verify_sdk_apple_simulator_execution",
            "verify_apple_device_evidence", "verify_apple_toolchain_evidence",
        )
        def call(name, args, kwargs):
            self.calls.append(name)
            if name == failure:
                raise ValueError("leaf rejected")
            if name == leaves[0]:
                self.assertEqual((self.root, "a" * 40, self.evidence), args)
                return self.sources
            if name == leaves[1]:
                return {"runtimeName": "independent runtime", "deviceTypeIdentifier": "independent device"}
            if name == leaves[3]:
                self.assertEqual(self.evidence, kwargs["evidence_directory"])
                self.assertEqual("independent runtime", kwargs["expected_runtime_name"])
                self.assertEqual("independent device", kwargs["expected_device_type_identifier"])
            if name == leaves[2]:
                consumers = kwargs["consumer_source_directory"]
                self.assertNotIn(self.evidence, consumers.parents)
                self.assertEqual(gate.regular_file_inventory(self.evidence / "consumer"),
                                 gate.regular_file_inventory(consumers))
            if name == leaves[4]:
                self.assertEqual(self.sources["testApplicationInventory"], kwargs["expected_test_application_inventory"])
                self.assertEqual(gate.regular_file_inventory(self.evidence / "device-package"),
                                 kwargs["expected_package_inventory"])
            if name == leaves[5]:
                self.assertEqual(self.sources["toolchain"], kwargs["expected_toolchain"])
                if mutation:
                    mutation.write_bytes(b"changed")
        with ExitStack() as stack:
            for name in leaves:
                stack.enter_context(patch.object(gate, name,
                    side_effect=lambda *args, _name=name, **kwargs: call(_name, args, kwargs)))
            return gate.verify_apple_validation_execution(**self.arguments)

    def test_all_full_gates_run_in_order_without_minting_authority(self):
        self.assertIsNone(self.run_gate())
        self.assertEqual(6, len(self.calls))
        self.assertLess(self.calls.index("verify_sdk_apple_validation_binding_content"),
                        self.calls.index("verify_apple_device_evidence"))

    def test_each_failure_prevents_later_gates(self):
        self.run_gate()
        expected = self.calls[:]
        for index, name in enumerate(expected):
            self.calls.clear()
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "leaf rejected"):
                self.run_gate(failure=name)
            self.assertEqual(expected[:index + 1], self.calls)

    def test_evidence_product_and_expectation_mutations_reject(self):
        for path in (self.evidence / "device-package/file", self.product / "file", *self.files.values()):
            original = path.read_bytes()
            try:
                with self.subTest(path=path), self.assertRaisesRegex(ValueError, "inputs changed"):
                    self.run_gate(mutation=path)
            finally:
                path.write_bytes(original)


class AppleValidationStageTest(unittest.TestCase):
    """Real manifests/archive/projection; full execution gate is explicitly mocked."""

    def setUp(self):
        content_fixture.AppleValidationContentFileTest.setUp(self)
        self.package = self.stage
        self.producer = {
            "repository": "codex-agent-labs/codex-agent", "workflowPath": ".github/workflows/ci.yml",
            "commit": "a" * 40, "tree": "b" * 40, "event": "pull_request",
            "runId": 7, "runAttempt": 1, "pullRequest": 8,
        }
        self.receipt = write_receipt(self.root / "package-receipt.json", product="sdk", component="sdk-ios",
            phase="package", target="ios", version="0.8.0", version_identity="0.8.0",
            outputs=self.manifest["outputs"], upstream=[], context={"producer": self.producer})
        self.archive = self.root / "evidence.zip"
        members = {f"{name}/original.bin": b"original raw evidence" for name in gate.APPLE_VALIDATION_EVIDENCE_ROOTS}
        members["compiler-raw/empty-stderr.bin"] = b""
        members.update({f"reports/{language}-parity.json": canonical_json_bytes(receipt)
                        for language, receipt in self.receipts.items()})
        archive_fixture.SdkAppleValidationEvidenceTest.write(self, sorted(members.items()))
        work = "/original/repository/codex-agent-runtime-ios"
        execution = work + "/build/imported-sdk-validation/" + self.producer["tree"] + "/ios-arm64"
        self.context = {
            "schemaVersion": 1, "producer": dict(self.producer), "target": "ios-arm64",
            "packageArtifact": {"artifactId": 1, "artifactSha256": "sha256:" + "1" * 64},
            "binaryArtifact": {"artifactId": 2, "artifactSha256": "sha256:" + "2" * 64},
            "rustHost": "aarch64-apple-darwin", "developerDirectory": "/original/Xcode.app/Contents/Developer",
            "originalWorkingDirectory": work, "originalDeviceWorkDirectory": execution + "/device-execution",
            "originalTestApplicationDirectory": execution + "/device-consumer/CodexAgentTestApp",
            "evidenceSha256": sha256_file(self.archive),
        }
        self.validation = self.root / "validation"
        self.content_path = self.validation / "outputs/validation/apple-validation.json"
        self.content_path.parent.mkdir(parents=True)
        self.content = gate.apple_validation_content(target="ios-arm64", sdk_version="0.8.0",
            package_outputs_digest=gate.output_inventory_digest(self.manifest["outputs"]),
            contract_digest=self.compatibility["contract"]["digest"], expected_canonical=self.canonical,
            binding_receipts=self.receipts)
        self.stage_content(self.content)
        self.arguments = dict(validation_stage=self.validation, target="ios-arm64", sdk_version="0.8.0",
            package_stage=self.package, package_receipt=self.receipt,
            sdk_compatibility=self.paths["sdk_compatibility"], contract_digest=self.compatibility["contract"]["digest"],
            canonical_api=self.paths["canonical_api"], canonical_coverage=self.paths["canonical_coverage"],
            evidence_archive=self.archive, context=self.context, repository=self.root, source_revision="a" * 40,
            tooling_evidence=self.root / "tooling", tooling_public_key=self.root / "key",
            java_executable=self.root / "java", policy_revision="b" * 40, required_trust_domain="release",
            tooling_keyring=self.root / "tooling-policy.json", tooling_keys_directory=self.root / "tooling-keys")

    def stage_content(self, content, target="ios-arm64", kind="apple-validation-content"):
        self.content_path.write_bytes(canonical_json_bytes(content))
        write_output_manifest(self.validation, "sdk", "sdk-ios", "validation", target, "0.8.0",
                              {kind: "outputs/validation"})

    def test_full_gate_precedes_projection_and_preserves_all_originals(self):
        before = regular_file_inventory(self.root)
        order, extracted = [], []
        projection = gate.apple_validation_content

        def execute(**arguments):
            order.append("full gate")
            extracted.append(arguments["evidence_root"])
            self.assertTrue(extracted[-1].is_dir())
            self.assertEqual(self.package / "outputs/apple", arguments["product_directory"])
            for name in ("repository", "source_revision", "tooling_evidence", "tooling_public_key",
                         "java_executable", "policy_revision", "required_trust_domain", "tooling_keyring",
                         "tooling_keys_directory", "sdk_version", "sdk_compatibility", "canonical_api", "canonical_coverage"):
                self.assertEqual(self.arguments[name], arguments[name])
            for argument, field in (("original_working_directory", "originalWorkingDirectory"),
                    ("original_device_work_directory", "originalDeviceWorkDirectory"),
                    ("original_test_application_directory", "originalTestApplicationDirectory"),
                    ("developer_directory", "developerDirectory")):
                self.assertEqual(self.context[field], arguments[argument])

        def project(**arguments):
            self.assertEqual(["full gate"], order)
            order.append("projection")
            return projection(**arguments)

        with patch.object(gate, "verify_apple_validation_execution", side_effect=execute), \
                patch.object(gate, "apple_validation_content", side_effect=project):
            self.assertEqual(self.content, gate.verify_apple_validation_stage(**self.arguments))
        self.assertEqual(["full gate", "projection"], order)
        self.assertFalse(extracted[0].exists())
        self.assertEqual(before, regular_file_inventory(self.root))

    def test_second_target_and_exact_stage_content_comparison(self):
        target = "ios-simulator-arm64"
        content = {**self.content, "target": target}
        self.stage_content(content, target)
        context = {**self.context, "target": target,
                   "originalDeviceWorkDirectory": self.context["originalDeviceWorkDirectory"].replace("ios-arm64/", target + "/"),
                   "originalTestApplicationDirectory": self.context["originalTestApplicationDirectory"].replace("ios-arm64/", target + "/")}
        with patch.object(gate, "verify_apple_validation_execution"):
            self.assertEqual(content, gate.verify_apple_validation_stage(**{**self.arguments, "target": target, "context": context}))
        self.stage_content({**self.content, "contractDigest": "sha256:" + "f" * 64})
        with patch.object(gate, "verify_apple_validation_execution"), self.assertRaisesRegex(ValueError, "staged content differs"):
            gate.verify_apple_validation_stage(**self.arguments)

    def test_structural_pairing_fails_before_full_gate(self):
        changed_receipt = deepcopy(self.receipt)
        changed_receipt["outputs"][0]["sha256"] = "sha256:" + "c" * 64
        for change in ({"target": "desktop"}, {"context": {**self.context, "target": "ios-simulator-arm64"}},
                       {"sdk_version": "0.8.1"}, {"package_receipt": changed_receipt}):
            with self.subTest(change=change), patch.object(gate, "verify_apple_validation_execution") as execute, \
                    self.assertRaises(ValueError):
                gate.verify_apple_validation_stage(**{**self.arguments, **change})
            execute.assert_not_called()
        for kind in ("evidence", "validation"):
            self.stage_content(self.content, kind=kind)
            with patch.object(gate, "verify_apple_validation_execution") as execute, self.assertRaises(ValueError):
                gate.verify_apple_validation_stage(**self.arguments)
            execute.assert_not_called()

    def test_full_gate_failure_never_projects(self):
        with patch.object(gate, "verify_apple_validation_execution", side_effect=ValueError("full gate rejected")), \
                patch.object(gate, "apple_validation_content") as project, \
                self.assertRaisesRegex(ValueError, "full gate rejected"):
            gate.verify_apple_validation_stage(**self.arguments)
        project.assert_not_called()

    def test_original_file_and_mutable_expectation_changes_reject(self):
        paths = [self.content_path, self.package / "outputs/apple/package.zip", self.archive,
                 self.paths["canonical_api"], self.paths["canonical_coverage"], self.paths["sdk_compatibility"]]
        for path in paths:
            original = path.read_bytes()
            try:
                with self.subTest(path=path), patch.object(gate, "verify_apple_validation_execution",
                        side_effect=lambda **_arguments: path.write_bytes(b"changed")), self.assertRaises(ValueError):
                    gate.verify_apple_validation_stage(**self.arguments)
            finally:
                path.write_bytes(original)
        for value in (self.context, self.receipt):
            original = deepcopy(value)
            try:
                with self.subTest(value=value), patch.object(gate, "verify_apple_validation_execution",
                        side_effect=lambda **_arguments: value.update(unexpected="mutation")), self.assertRaises(ValueError):
                    gate.verify_apple_validation_stage(**self.arguments)
            finally:
                value.clear()
                value.update(original)

    def test_archive_exit_mutation_is_rejected_after_projection(self):
        original_archive_context = gate.verified_apple_validation_archive

        @contextmanager
        def late_mutation(*arguments, **keywords):
            with original_archive_context(*arguments, **keywords) as extracted:
                yield extracted
            self.context["rustHost"] = "changed after replay"

        with patch.object(gate, "verified_apple_validation_archive", side_effect=late_mutation), \
                patch.object(gate, "verify_apple_validation_execution"), self.assertRaisesRegex(ValueError, "originals changed"):
            gate.verify_apple_validation_stage(**self.arguments)


if __name__ == "__main__":
    unittest.main()
