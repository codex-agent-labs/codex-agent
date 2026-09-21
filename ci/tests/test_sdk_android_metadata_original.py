"""Original Android metadata replay tests; hosted and native boundaries are mocked."""

from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

from ci import sdk_android_metadata_original as original
from ci.tests import test_sdk_android_metadata_workflow as fixtures
from ci.products.inventory import (
    canonical_json_bytes, regular_file_inventory, sha256_bytes,
    snapshot_regular_tree, write_canonical_json,
)
from ci.products.receipt import write_output_manifest
from ci.products.restore import finalize_phase_object


class AndroidMetadataOriginalTest(unittest.TestCase):
    def setUp(self):
        # Reuse the real package/validation/Contract fixture without importing
        # its TestCase into this module's discovery namespace.
        self.f = fixtures.AndroidMetadataWorkflowTest(methodName="runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.root = self.f.root
        self.versions = {"sdk": self.f.version, "contract": "0.2.0",
                         "runtime-release": "0.8.1", "runtime-compatibility": "0.8.0"}
        source = self.root / "source-inventory"
        source.mkdir()
        (source / "metadata.py").write_bytes(b"original Android metadata source\n")
        self.inventory = regular_file_inventory(source)
        self.plan_value = original.plan_phase(
            original._INSTANCE, inventory=self.inventory, versions=self.versions,
            upstream_receipts=[self.f.validation],
            toolchain_profile_digest=original.NOT_APPLICABLE_TOOLCHAIN_DIGEST,
            flags_digest=original.NOT_APPLICABLE_FLAGS_DIGEST, output_schema_version=1)
        self.producer = deepcopy(self.f.current)
        self.context = {"repositoryRoot": "/original/checkout",
                        "metadataRequest": "/original/private/metadata-request.json"}
        self.recovery_plan = self.root / "current-recovery-impact-plan.json"
        self.recovery_plan.write_bytes(b"different current recovery plan")
        self.worker = self.root / "original-metadata-worker"
        self._build_worker()
        self.receipt_path = self.root / "selected-metadata.json"
        self.receipt_path.write_bytes((self.worker / "shard/phase-receipt.json").read_bytes())
        self.receipt = original._json(self.receipt_path)
        self.capture_mutation = None
        self.held_exit_failure = None
        self.active = False
        self.enterContext(patch.object(
            original, "capture_sdk_android_metadata_upload", side_effect=self.capture_upload))
        self.plan = self.enterContext(patch.object(
            original.product_reuse, "_validate_plan",
            return_value={"remoteBuildAuthorized": True, "event": "pull_request"}))
        self.enterContext(patch.object(
            original.product_reuse, "_consumer", return_value={"producer": self.producer}))
        self.enterContext(patch.object(
            original, "run_git", side_effect=lambda root, op, revision:
            self.producer["tree" if revision.endswith("{tree}") else "commit"] + "\n"))
        self.enterContext(patch.object(original, "git_product_versions", return_value=self.versions))
        self.git_inventory = self.enterContext(patch.object(
            original, "phase_git_inventory", return_value=self.inventory))
        self.held = self.enterContext(patch.object(
            original, "verified_retained_android_validation", side_effect=self.held_validation))

    def _build_worker(self):
        request = self.worker / "metadata-request.json"
        request.parent.mkdir(parents=True)
        write_canonical_json(request, {
            "sdkVersion": self.f.version,
            "packageStage": "/original/inputs/package/stage",
            "packageReceipt": "/original/inputs/package/phase-receipt.json",
            "validationStage": "/original/inputs/validation/stage",
            "validationReceipt": "/original/inputs/validation/phase-receipt.json",
            "releaseAarSha256": self.f.validation_content["releaseAarSha256"],
            "bundledRuntimeSha256": self.f.validation_content["bundledRuntimeSha256"],
        })
        stage = self.root / "metadata-stage"
        output = stage / original.OUTPUT_PATH
        output.parent.mkdir(parents=True)
        local_request = self.root / "local-metadata-request.json"
        write_canonical_json(local_request, {
            "sdkVersion": self.f.version,
            "packageStage": str(self.f.package_stage),
            "packageReceipt": str(self.f.package_receipt),
            "validationStage": str(self.f.validation_stage),
            "validationReceipt": str(self.f.validation_receipt),
            "releaseAarSha256": self.f.validation_content["releaseAarSha256"],
            "bundledRuntimeSha256": self.f.validation_content["bundledRuntimeSha256"],
        })
        original.write_android_metadata_content(local_request, output)
        write_output_manifest(
            stage, "sdk", "sdk-android", "metadata", "android", self.f.version,
            {original.OUTPUT_KIND: "outputs/evidence"},
            expected_output_paths=[original.OUTPUT_PATH])
        finalize_phase_object(
            stage_root=stage, phase_plan=self.plan_value, producer=self.producer,
            product_version=self.f.version, trust_domain="development",
            destination=self.worker / "shard")
        inputs = self.worker / "inputs"
        inputs.mkdir()
        write_canonical_json(inputs / "phase-plan.json", self.plan_value)
        write_canonical_json(inputs / "producer.json", self.producer)
        selection = self.worker / "selection"
        selection.mkdir()
        (selection / "impact-plan.json").write_bytes(self.f.plan.read_bytes())
        write_canonical_json(selection / "phase-plan.json", self.plan_value)
        write_canonical_json(selection / "producer.json", self.producer)
        for name, selected_stage, receipt in (
                ("sdk-sdk-android-package-android", self.f.package_stage, self.f.package_receipt),
                ("sdk-sdk-android-validation-android", self.f.validation_stage,
                 self.f.validation_receipt)):
            selected = inputs / name
            shutil.copytree(selected_stage, selected / "stage")
            (selected / "phase-receipt.json").write_bytes(receipt.read_bytes())
        shutil.copytree(self.f.original_capture, self.worker / "originals/validation")
        worker = self.worker / "worker"
        worker.mkdir()
        fields = {
            "codexAgent.product": "sdk", "codexAgent.component": "sdk-android",
            "codexAgent.phase": "metadata", "codexAgent.target": "android",
            "codexAgent.candidateCommit": self.producer["commit"],
            "codexAgent.candidateTree": self.producer["tree"],
            "codexAgent.sdkVersion": self.f.version,
            "codexAgent.sdkAndroidMetadataRequest": self.context["metadataRequest"],
        }
        write_canonical_json(worker / "execution.json", {
            "schemaVersion": 1, "producer": self.producer,
            "buildKey": self.plan_value["buildKey"],
            "command": original.product_reuse._runtime_worker_command(
                "/original/checkout/gradlew", fields, {}, build_directory=".",
                platform_name="posix"),
            "workingDirectory": self.context["repositoryRoot"], "returnCode": 0,
            "launchError": None, "elapsedNs": 17,
        })
        (worker / "gradle.log").write_bytes(b"")

    def capture_upload(self, plan, destination, **kwargs):
        self.assertEqual(self.receipt_path.read_bytes(),
                         kwargs["metadata_receipt_path"].read_bytes())
        self.assertEqual(73, kwargs["artifact_id"])
        self.assertEqual("caller-observation-token", kwargs["token"])
        snapshot_regular_tree(self.worker, destination / "original", allow_empty=True)
        (destination / "plan").mkdir()
        (destination / "plan/impact-plan.json").write_bytes(Path(plan).read_bytes())
        (destination / "transport.zip").write_bytes(b"mocked exact official upload")
        transport = {
            "artifact": {"id": 73}, "captureProducer": deepcopy(self.producer),
            "observed": [],
            "metadataReceiptSha256": sha256_bytes(self.receipt_path.read_bytes()),
        }
        write_canonical_json(destination / "capture-transport.json", transport)
        if self.capture_mutation is not None:
            self.capture_mutation(destination / "original")
        return transport

    @contextmanager
    def held_validation(self, plan, receipt, **kwargs):
        self.assertEqual(self.recovery_plan, plan)
        self.assertEqual(self.f.original_capture, kwargs["validation_capture"])
        self.assertEqual(self.f.package_stage, kwargs["package_stage"])
        self.assertEqual(self.f.contract_evidence, kwargs["binary_contract_evidence"])
        self.active = True
        try:
            yield {
                "stage": self.f.validation_stage,
                "receiptPath": self.f.validation_receipt,
                "receiptBytes": self.f.validation_receipt.read_bytes(),
                "receipt": deepcopy(self.f.validation),
                "capture": self.f.original_capture,
                "packageStage": self.f.package_stage,
                "packageReceipt": deepcopy(self.f.package),
            }
        finally:
            self.active = False
            if self.held_exit_failure is not None:
                raise self.held_exit_failure

    def call(self, **changes):
        values = dict(
            plan=self.recovery_plan, metadata_receipt_path=self.receipt_path,
            artifact_id=73, artifact_sha256="sha256:" + "7" * 64,
            validation_capture=self.f.original_capture,
            package_stage=self.f.package_stage, package_receipt=self.f.package_receipt,
            binary_stage=self.f.binary_stage, binary_receipt=self.f.binary_receipt,
            compatibility_request=self.f.compatibility,
            binary_contract_evidence=self.f.contract_evidence,
            trusted_source_commit="e" * 40, trusted_source_tree="f" * 40,
            original_context=self.context, trusted_workflow_sha="8" * 40,
            tooling_evidence=self.f.tooling, tooling_public_key=self.f.tooling_key,
            java_executable=self.f.java, apkanalyzer_executable=self.f.analyzer,
            policy_revision="1" * 40, required_trust_domain="development",
            repository_root=self.root, environ={}, token="caller-observation-token")
        values.update(changes)
        return original.verified_original_sdk_android_metadata(**values)

    def test_full_held_validation_real_join_and_key_replay(self):
        with self.call() as value:
            self.assertTrue(self.active)
            self.assertEqual(self.receipt, value["receipt"])
            self.assertEqual(self.receipt_path.read_bytes(), value["receiptBytes"])
            self.assertEqual((self.worker / "shard/phase-receipt.json").read_bytes(),
                             value["receiptBytes"])
            self.assertEqual((self.root / "metadata-stage" / original.OUTPUT_PATH).read_bytes(),
                             (value["stage"] / original.OUTPUT_PATH).read_bytes())
            private_stage = value["stage"]
            historical = self.plan.call_args.args[0]
            self.assertEqual(self.f.plan.read_bytes(), historical.read_bytes())
            self.assertNotEqual(self.recovery_plan.read_bytes(), historical.read_bytes())
        self.assertFalse(self.active)
        self.assertFalse(private_stage.exists())
        self.held.assert_called_once()
        self.plan.assert_called_once()
        self.assertEqual((self.root,), self.plan.call_args.args[1:])
        self.assertEqual(self.producer["commit"],
                         self.plan.call_args.kwargs["expected_revision"])

    def test_exact_original_context_and_worker_command_are_required(self):
        with self.assertRaisesRegex(ValueError, "path is invalid"):
            with self.call(original_context={**self.context, "metadataRequest": "/bad/../path"}):
                pass
        def change_command(root):
            path = root / "worker/execution.json"
            value = original._json(path)
            value["command"].remove("--offline")
            write_canonical_json(path, value)
        self.capture_mutation = change_command
        with self.assertRaisesRegex(ValueError, "fixed offline command"), self.call():
            pass

    def test_retained_validation_and_selected_inputs_are_exact(self):
        def change_request(root):
            path = root / "metadata-request.json"
            value = original._json(path)
            value["releaseAarSha256"] = "sha256:" + "6" * 64
            write_canonical_json(path, value)
        mutations = {
            "validation-capture": lambda root: (root / "originals/validation/original/stage/extra").write_bytes(b"x"),
            "validation-stage": lambda root: (root / "inputs/sdk-sdk-android-validation-android/stage/extra").write_bytes(b"x"),
            "package-receipt": lambda root: (root / "inputs/sdk-sdk-android-package-android/phase-receipt.json").write_bytes(b"{}\n"),
            "metadata-request": change_request,
            "selection": lambda root: (root / "selection/phase-plan.json").write_bytes(b"{}\n"),
            "missing-selection": lambda root: shutil.rmtree(root / "selection"),
            "layout": lambda root: (root / "unexpected").write_bytes(b"x"),
        }
        for name, mutation in mutations.items():
            self.capture_mutation = mutation
            with self.subTest(name=name), self.assertRaisesRegex(
                    ValueError, "retained validation|retained selection|differs from verified originals|unexpected retained layout|request differs"):
                with self.call():
                    pass

    def test_original_source_key_and_content_cannot_be_substituted(self):
        self.git_inventory.return_value = [
            {**self.inventory[0], "sha256": "sha256:" + "4" * 64}]
        with self.assertRaisesRegex(ValueError, "source/version/phase key"), self.call():
            pass
        self.git_inventory.return_value = self.inventory
        def corrupt_object(root):
            descriptor = root / "shard/phase-object.json"
            value = original._json(descriptor)
            value["objectSha256"] = "sha256:" + "9" * 64
            write_canonical_json(descriptor, value)
        self.capture_mutation = corrupt_object
        with self.assertRaises(ValueError), self.call():
            pass

    def test_lifetime_mutation_and_held_exit_failure_reject(self):
        with self.assertRaisesRegex(ValueError, "changed"), self.call() as value:
            value["receipt"]["producer"]["runId"] += 1
        with self.assertRaisesRegex(ValueError, "changed"), self.call() as value:
            value["transport"]["observed"].append({"late": True})
        self.held_exit_failure = ValueError("full validation exit rejected")
        with self.assertRaisesRegex(ValueError, "full validation exit rejected"), self.call():
            pass

    def test_caller_policy_and_history_remain_independent(self):
        before = deepcopy(self.context)
        with self.assertRaisesRegex(ValueError, "changed"), self.call():
            self.context["metadataRequest"] = "/late/request.json"
        self.context = before
        self.plan.return_value["remoteBuildAuthorized"] = False
        with self.assertRaisesRegex(ValueError, "not authorized"), self.call():
            pass


if __name__ == "__main__":
    unittest.main()
