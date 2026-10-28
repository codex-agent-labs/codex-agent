"""Android caller-policy construction; hosted/full gates are explicit mocks."""

from contextlib import contextmanager, redirect_stderr, redirect_stdout
from copy import deepcopy
import io
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from ci import sdk_android_metadata_policy as policy
from ci.products.inventory import canonical_json_bytes, regular_file_inventory
from ci.tests import test_sdk_android_metadata_workflow as fixtures


class AndroidMetadataPolicyTest(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.AndroidMetadataWorkflowTest(methodName="runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        temporary = tempfile.TemporaryDirectory(prefix="android-metadata-policy-output-")
        self.addCleanup(temporary.cleanup)
        self.external = Path(temporary.name).resolve()
        self.destination = self.external / "policy"
        self.evidence = self.f.root / "metadata-evidence"
        self.evidence.mkdir()
        (self.evidence / "opaque-original").write_bytes(b"transport only\x00\xff")
        self.records = [{"component": "sdk-android", "phase": "metadata",
            "target": "android", "receiptSha256": "sha256:" + "7" * 64,
            "receipt": "originals/receipt.json", "capture": "originals/capture"}]
        self.context = {"repositoryRoot": "/original/checkout",
                        "metadataRequest": "/original/private/metadata-request.json"}
        self.revision = "1" * 40
        self.events = []
        self.exit_failure = None
        self.exit_mutation = None
        self.arguments = dict(
            plan=self.f.plan, evidence_root=self.evidence,
            validation_receipt_path=self.f.validation_receipt,
            validation_capture=self.f.original_capture,
            destination=self.destination, validation_artifact_id=73,
            validation_artifact_sha256="sha256:" + "8" * 64,
            trusted_workflow_sha="2" * 40,
            trusted_android_workflow_sha="3" * 40,
            expected_original_run_id=self.f.validation_producer["runId"],
            expected_original_run_attempt=self.f.validation_producer["runAttempt"],
            package_stage=self.f.package_stage, package_receipt=self.f.package_receipt,
            binary_stage=self.f.binary_stage, binary_receipt=self.f.binary_receipt,
            compatibility_request=self.f.compatibility,
            binary_contract_evidence=deepcopy(self.f.contract_evidence),
            trusted_source_commit="e" * 40, trusted_source_tree="f" * 40,
            original_context=deepcopy(self.context), tooling_evidence=self.f.tooling,
            tooling_public_key=self.f.tooling_key, java_executable=self.f.java,
            apkanalyzer_executable=self.f.analyzer,
            required_trust_domain="development", repository_root=self.f.root,
            environ={}, token="caller observation token")
        self.plan = self.enterContext(patch.object(
            policy.product_reuse, "_validate_plan",
            return_value={"validationCommit": self.revision,
                          "validationTree": "4" * 40}))
        self.loader = self.enterContext(patch.object(
            policy, "load_sdk_metadata_evidence", return_value=self.records))
        self.enterContext(patch.object(policy, "_request_inventory", return_value={}))
        self.reader = self.enterContext(patch.object(
            policy, "verified_original_android_firebase_validation",
            side_effect=self.verified_validation))
        self.admission = self.enterContext(patch.object(
            policy, "AndroidMetadataAdmission", side_effect=self.validate_descriptor))

    @contextmanager
    def verified_validation(self, plan, receipt, **kwargs):
        self.events.append("validation-enter")
        self.assertNotEqual(self.f.plan, Path(plan))
        self.assertEqual(self.f.plan.read_bytes(), Path(plan).read_bytes())
        self.assertEqual(self.f.validation_receipt, Path(receipt))
        self.assertEqual(self.revision, kwargs["policy_revision"])
        self.assertEqual(self.f.contract_evidence, kwargs["binary_contract_evidence"])
        try:
            yield {"receiptBytes": self.f.validation_receipt.read_bytes(),
                   "capture": self.f.original_capture}
        finally:
            self.assertTrue(self.destination.exists())
            self.events.append("validation-exit")
            if self.exit_mutation is not None:
                self.exit_mutation()
            if self.exit_failure is not None:
                raise ValueError(self.exit_failure)

    def validate_descriptor(self, root, records, *, repository, policy_revision, policy):
        self.events.append("adapter-schema")
        self.assertEqual(self.evidence, Path(root))
        self.assertEqual(self.f.root, Path(repository))
        self.assertEqual(self.revision, policy_revision)
        self.assertEqual([{"receiptSha256": self.records[0]["receiptSha256"],
                           "captureRoot": self.records[0]["capture"]}], records)
        self.assertEqual(self.context, policy["originalContext"])
        return object()

    def call(self, **changes):
        arguments = {**self.arguments, **changes}
        published = policy.publish_regular_tree

        def publish(source, destination, **kwargs):
            self.assertEqual(["validation-enter", "adapter-schema"], self.events)
            self.events.append("publish")
            return published(source, destination, **kwargs)

        with patch.object(policy, "publish_regular_tree", side_effect=publish):
            return policy.create_sdk_android_metadata_policy(**arguments)

    def test_exact_descriptor_uses_current_policy_revision_and_no_carrier_authority(self):
        before = {"evidence": regular_file_inventory(self.evidence, allow_empty=True),
                  "validation": regular_file_inventory(self.f.original_capture, allow_empty=True)}
        descriptor = self.call()
        self.assertEqual(["validation-enter", "adapter-schema", "publish", "validation-exit"], self.events)
        self.assertEqual(descriptor, policy.load_canonical_json_bytes(
            (self.destination / policy.POLICY_NAME).read_bytes()))
        self.assertEqual({"evidenceRoot", "records", "policy"}, set(descriptor))
        self.assertEqual(str(self.evidence), descriptor["evidenceRoot"])
        self.assertEqual(self.f.contract_evidence,
                         descriptor["policy"]["binaryContractEvidence"])
        self.assertEqual(self.context, descriptor["policy"]["originalContext"])
        for forbidden in ("policyRevision", "validationArtifactId", "trustedWorkflowSha",
                          "expectedOriginalRunId", "accepted", "hosted"):
            self.assertNotIn(forbidden, descriptor["policy"])
        self.assertEqual(before["evidence"], regular_file_inventory(self.evidence, allow_empty=True))
        self.assertEqual(before["validation"], regular_file_inventory(
            self.f.original_capture, allow_empty=True))
        self.plan.assert_called_once()
        self.loader.assert_called_once_with(self.evidence)

    def test_official_gate_failure_retains_unaccepted_policy_for_caller_cleanup(self):
        self.exit_failure = "official Firebase recheck failed"
        with self.assertRaisesRegex(ValueError, "official Firebase"):
            self.call()
        self.assertTrue((self.destination / policy.POLICY_NAME).is_file())

    def test_late_input_mutation_retains_unaccepted_policy_for_caller_cleanup(self):
        original = self.f.plan.read_bytes()
        self.exit_mutation = lambda: self.f.plan.write_bytes(b"late changed plan")
        with self.assertRaisesRegex(ValueError, "inputs changed"):
            self.call()
        self.assertTrue((self.destination / policy.POLICY_NAME).is_file())
        self.f.plan.write_bytes(original)

    def test_byte_identical_replacement_is_not_deleted_on_reader_exit_failure(self):
        replacement = self.external / "replacement-source"

        def replace():
            self.destination.rename(self.external / "owned-publication")
            shutil.copytree(self.external / "owned-publication", replacement)
            replacement.rename(self.destination)
            self.replacement_identity = self.destination.stat().st_ino

        self.exit_mutation = replace
        self.exit_failure = "official Firebase exit rejected"
        with self.assertRaisesRegex(ValueError, "official Firebase exit"):
            self.call()
        self.assertTrue(self.destination.is_dir())
        self.assertEqual(self.replacement_identity, self.destination.stat().st_ino)
        self.assertEqual(
            (self.external / "owned-publication" / policy.POLICY_NAME).read_bytes(),
            (self.destination / policy.POLICY_NAME).read_bytes())

    def test_reader_exit_replacement_cannot_return_success(self):
        def replace():
            self.destination.rename(self.external / "owned-publication")
            shutil.copytree(self.external / "owned-publication", self.external / "replacement")
            (self.external / "replacement").rename(self.destination)
            self.replacement_identity = self.destination.stat().st_ino

        self.exit_mutation = replace
        with self.assertRaisesRegex(ValueError, "changed after validation"):
            self.call()
        self.assertEqual(self.replacement_identity, self.destination.stat().st_ino)
        self.assertEqual(
            (self.external / "owned-publication" / policy.POLICY_NAME).read_bytes(),
            (self.destination / policy.POLICY_NAME).read_bytes())

    def test_missing_android_record_overlap_stale_output_and_secret_fail_closed(self):
        self.loader.return_value = [{**self.records[0], "component": "sdk-core", "target": "common"}]
        with self.assertRaisesRegex(ValueError, "requires retained Android"):
            self.call()
        self.loader.return_value = self.records
        for destination in (self.evidence / "nested", self.f.tooling / "nested"):
            with self.subTest(destination=destination), self.assertRaises(ValueError):
                self.call(destination=destination)
            self.assertFalse(destination.exists())
        self.destination.mkdir()
        (self.destination / "marker").write_bytes(b"keep")
        with self.assertRaisesRegex(ValueError, "fresh"):
            self.call()
        self.assertEqual(b"keep", (self.destination / "marker").read_bytes())
        with patch.dict(os.environ, {"CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY": ""}), \
                self.assertRaisesRegex(ValueError, "signing-secret"):
            self.call(destination=self.external / "secret")
        self.reader.assert_not_called()

    def test_cli_loads_only_explicit_caller_json_and_prints_descriptor_path(self):
        contract = self.external / "contract.json"
        context = self.external / "context.json"
        contract.write_bytes(canonical_json_bytes(self.f.contract_evidence))
        context.write_bytes(canonical_json_bytes(self.context))
        paths = {
            "plan": self.f.plan, "evidence-root": self.evidence,
            "validation-receipt": self.f.validation_receipt,
            "validation-capture": self.f.original_capture,
            "destination": self.destination, "package-stage": self.f.package_stage,
            "package-receipt": self.f.package_receipt, "binary-stage": self.f.binary_stage,
            "binary-receipt": self.f.binary_receipt,
            "compatibility-request": self.f.compatibility,
            "binary-contract-evidence": contract, "original-context": context,
            "tooling-evidence": self.f.tooling, "tooling-public-key": self.f.tooling_key,
            "java-executable": self.f.java, "apkanalyzer-executable": self.f.analyzer,
            "repository-root": self.f.root,
        }
        argv = [part for name, value in paths.items() for part in ("--" + name, str(value))]
        argv += ["--validation-artifact-id", "73",
                 "--validation-artifact-sha256", "sha256:" + "8" * 64,
                 "--trusted-workflow-sha", "2" * 40,
                 "--trusted-android-workflow-sha", "3" * 40,
                 "--expected-original-run-id", str(self.f.validation_producer["runId"]),
                 "--expected-original-run-attempt", str(self.f.validation_producer["runAttempt"]),
                 "--trusted-source-commit", "e" * 40,
                 "--trusted-source-tree", "f" * 40,
                 "--required-trust-domain", "development"]
        with patch.object(policy, "create_sdk_android_metadata_policy",
                          return_value={"evidenceRoot": str(self.evidence),
                                        "records": [], "policy": {}}) as create, \
                patch.dict(os.environ, {"GITHUB_TOKEN": "token"}, clear=True), \
                redirect_stdout(io.StringIO()) as output:
            self.assertEqual(0, policy.main(argv))
        self.assertEqual({"policy_path": str(self.destination / policy.POLICY_NAME)},
                         policy.load_canonical_json_bytes(output.getvalue().encode()))
        self.assertEqual(self.f.contract_evidence,
                         create.call_args.kwargs["binary_contract_evidence"])
        self.assertEqual(self.context, create.call_args.kwargs["original_context"])
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            policy.main([*argv, "--unknown", "value"])


if __name__ == "__main__":
    unittest.main()
