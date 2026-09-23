"""Selected Apple original-source orchestration; official APIs and full gate are mocked."""

from contextlib import contextmanager, ExitStack
from io import BytesIO
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sdk_apple_original_package_selection as selection
from products.inventory import canonical_json_bytes, snapshot_regular_tree, write_canonical_json
from products.receipt import write_output_manifest
from products.restore import finalize_phase_object
from tests.product_chain_support import write_receipt


class OriginalApplePackageSelectionTest(unittest.TestCase):
    def setUp(self):
        checkout = tempfile.TemporaryDirectory(prefix="apple-selection-checkout-")
        scratch = tempfile.TemporaryDirectory(prefix="apple-selection-scratch-")
        self.addCleanup(checkout.cleanup)
        self.addCleanup(scratch.cleanup)
        self.repo, self.scratch = Path(checkout.name).resolve(), Path(scratch.name).resolve()
        self.producer = {"repository": "codex-agent-labs/codex-agent",
            "workflowPath": ".github/workflows/product-validation.yml",
            "commit": "a" * 40, "tree": "b" * 40, "event": "pull_request",
            "runId": 71, "runAttempt": 2, "pullRequest": 31}
        stage = self.repo / "fixture-stage"
        (stage / "outputs/apple").mkdir(parents=True)
        (stage / "outputs/apple/package.zip").write_bytes(b"synthetic original package")
        manifest = write_output_manifest(stage, "sdk", "sdk-ios", "package", "ios", "0.8.0",
                                         {"apple": "outputs/apple"})
        receipt_path = self.repo / "fixture-receipt.json"
        receipt = write_receipt(receipt_path, product="sdk", component="sdk-ios", phase="package",
            target="ios", version="0.8.0", version_identity="0.8.0", outputs=manifest["outputs"],
            upstream=[], context={"producer": self.producer})
        phase = {name: receipt[name] for name in (
            "schemaVersion", "product", "component", "phase", "target", "buildKey", "inputs")}
        self.package_upload = self.repo / "fixture-package-upload"
        original = self.package_upload / "original"
        original.mkdir(parents=True)
        finalized = finalize_phase_object(stage_root=stage, phase_plan=phase,
            producer=self.producer, product_version="0.8.0", trust_domain="development",
            destination=original / "shard")
        self.raw = finalized["receiptBytes"]
        self.envelope = {"receipt": finalized["receipt"], "receiptBytes": self.raw,
            "receiptSha256": finalized["receiptSha256"], "objectSha256": finalized["objectSha256"]}
        write_canonical_json(original / "apple-package-execution.json", {
            "sdkInputsArtifact": {"artifactId": 811, "artifactSha256": "sha256:" + "8" * 64}})
        original_plan = b'{"synthetic":"original impact plan, not hosted evidence"}\n'
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
            archive.writestr("impact-plan.json", original_plan)
        self.plan_zip = buffer.getvalue()
        self.events = []
        self.validated_plan = {"remoteBuildAuthorized": True, "event": "pull_request"}

    def selector(self):
        return selection.OriginalApplePackageSelector(self.scratch,
            repository_root=self.repo, trusted_workflow_sha="c" * 40,
            keyring=self.repo / "keyring.json", keys_directory=self.repo / "keys",
            tooling_evidence=self.repo / "tooling", tooling_public_key=self.repo / "tooling.pub",
            java_executable=self.repo / "java", policy_revision="d" * 40,
            required_trust_domain="development", environ={}, token="synthetic")

    def capture_package(self, plan, destination, **kwargs):
        self.events.append("package-capture")
        self.assertEqual(self.raw, Path(kwargs["package_receipt_path"]).read_bytes())
        self.assertEqual(self.validated_plan, selection.product_reuse._validate_plan(plan, self.repo,
            expected_revision=self.producer["commit"]))
        snapshot_regular_tree(self.package_upload, destination, allow_empty=True)

    def capture_sdk(self, plan, destination, **kwargs):
        self.events.append("s858-capture")
        self.assertEqual(self.raw, Path(kwargs["original_package_receipt_path"]).read_bytes())
        self.assertEqual("current-runtime", kwargs["expected_source"])
        self.assertEqual(811, kwargs["artifact_id"])
        self.assertEqual("sha256:" + "8" * 64, kwargs["artifact_sha256"])
        destination.mkdir()
        (destination / "placeholder.txt").write_bytes(b"synthetic S858; no original gate claimed")

    @contextmanager
    def mocked_original_gate(self, _plan, _receipt, **_options):
        self.events.append("full-gate-enter")
        selected_stage = self.scratch / self.envelope["receiptSha256"].removeprefix("sha256:") / "selected-stage"
        try:
            yield {"stage": selected_stage, "receipt": self.envelope["receipt"],
                   "receiptBytes": self.raw, "original": self.package_upload / "original"}
        finally:
            self.events.append("full-gate-exit")

    def patch_sources(self):
        stack = ExitStack()
        stack.enter_context(patch.object(selection.product_reuse, "_observe_ci_producer_jobs",
            return_value=[{"run": {"head_sha": self.producer["commit"]}, "jobs": []}]))
        stack.enter_context(patch.object(selection.product_reuse, "paginated_items", return_value=[]))
        stack.enter_context(patch.object(selection, "_original_upload", return_value=({"id": 701}, self.plan_zip)))
        stack.enter_context(patch.object(selection.product_reuse, "_validate_plan", return_value=self.validated_plan))
        stack.enter_context(patch.object(selection.product_reuse, "_consumer",
            return_value={"producer": self.producer}))
        stack.enter_context(patch.object(selection, "locate_original_apple_upload",
            return_value={"artifact_id": 801, "artifact_sha256": "sha256:" + "7" * 64}))
        stack.enter_context(patch.object(selection.product_reuse, "capture_sdk_ios_package_upload",
            side_effect=self.capture_package))
        stack.enter_context(patch.object(selection, "git_product_versions",
            return_value={"sdk": "0.8.0", "runtime-release": "0.8.0"}))
        stack.enter_context(patch.object(selection, "sdk_runtime_source", return_value=None))
        stack.enter_context(patch.object(selection.product_reuse, "capture_sdk_inputs_upload",
            side_effect=self.capture_sdk))
        return stack

    def test_official_original_plan_package_and_s858_are_captured_before_full_gate(self):
        with self.patch_sources(), patch(
                "ci.sdk_ios_original_package.verified_retained_ios_package", self.mocked_original_gate):
            admission = self.selector()(self.envelope)
            self.assertIs(type(admission), selection.ApplePackageAdmission)
            self.assertEqual(["package-capture", "s858-capture"], self.events)
            admission.verify(self.envelope)
        self.assertEqual(["package-capture", "s858-capture", "full-gate-enter", "full-gate-exit"], self.events)

    def test_wrong_original_plan_producer_fails_before_package_capture(self):
        self.validated_plan = {"remoteBuildAuthorized": False, "event": "pull_request"}
        with self.patch_sources(), patch.object(selection.product_reuse,
                "capture_sdk_ios_package_upload") as package, self.assertRaisesRegex(ValueError, "original plan|Original Apple plan"):
            self.selector()(self.envelope)
        package.assert_not_called()

    def test_wrong_official_package_object_blocks_s858_selection(self):
        wrong = dict(self.envelope)
        wrong["objectSha256"] = "sha256:" + "f" * 64
        with self.patch_sources(), patch.object(selection.product_reuse,
                "capture_sdk_inputs_upload") as sdk, self.assertRaisesRegex(ValueError, "official|Official"):
            self.selector()(wrong)
        sdk.assert_not_called()

    def test_descriptor_locator_is_only_a_claim_and_must_be_exact(self):
        write_canonical_json(self.package_upload / "original/apple-package-execution.json",
                             {"sdkInputsArtifact": {"artifactId": 811}})
        with self.patch_sources(), patch.object(selection.product_reuse,
                "capture_sdk_inputs_upload") as sdk, self.assertRaises(ValueError):
            self.selector()(self.envelope)
        sdk.assert_not_called()

    def test_selected_receipt_sdk_version_must_match_original_git(self):
        with self.patch_sources(), patch.object(selection, "git_product_versions",
                return_value={"sdk": "0.8.1", "runtime-release": "0.8.0"}), \
                patch.object(selection.product_reuse, "capture_sdk_inputs_upload") as sdk, \
                self.assertRaisesRegex(ValueError, "Git SDK version"):
            self.selector()(self.envelope)
        sdk.assert_not_called()

    def test_original_s858_capture_failure_does_not_create_admission(self):
        with self.patch_sources(), patch.object(selection.product_reuse,
                "capture_sdk_inputs_upload", side_effect=ValueError("official S858 mismatch")), \
                patch.object(selection, "ApplePackageAdmission") as admission, \
                self.assertRaisesRegex(ValueError, "official S858 mismatch"):
            self.selector()(self.envelope)
        admission.assert_not_called()

    def test_non_package_envelope_rejected_before_observation(self):
        wrong = {**self.envelope, "receipt": {**self.envelope["receipt"], "phase": "binary"}}
        with patch.object(selection.product_reuse, "_observe_ci_producer_jobs") as observe, \
                self.assertRaises(ValueError):
            self.selector()(wrong)
        observe.assert_not_called()


if __name__ == "__main__":
    unittest.main()
