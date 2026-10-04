"""Original SDK upload transport is captured before, not as, metadata election."""

from pathlib import Path
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import product_reuse
import sdk_workflow


class SdkTransportCaptureTest(unittest.TestCase):
    def test_exact_official_capture_emits_paths_without_replaying_state_or_matrix(self):
        with tempfile.TemporaryDirectory() as checkout, tempfile.TemporaryDirectory() as outputs:
            root = Path(checkout).resolve()
            plan, destination = root / "plan.json", root / "build/captured"
            output = Path(outputs).resolve() / "github-output"
            plan.write_text("original plan")
            output.touch()
            with patch.object(product_reuse, "capture_runtime_resume_upload") as capture, \
                    patch.object(sdk_workflow, "matrix", side_effect=AssertionError("premature election")):
                paths = sdk_workflow.capture_transport(plan, destination, output, artifact_id=71,
                    artifact_sha256="sha256:" + "a" * 64, trusted_workflow_sha="b" * 40,
                    sdk_state_wave=17, repository_root=root, environ={}, token="synthetic")
            capture.assert_called_once_with(plan, destination, artifact_id=71,
                artifact_sha256="sha256:" + "a" * 64, trusted_workflow_sha="b" * 40,
                sdk_state_wave=17, state_wave=0, repository_root=root,
                environ={}, token="synthetic")
            self.assertEqual(destination / "original/runtime-state", paths["state_root"])
            self.assertEqual(destination / "original/product-resume-state", paths["discovery_root"])
            self.assertEqual(destination / "original/product-resume-inputs/plan/impact-plan.json", paths["plan_path"])
            raw = output.read_text()
            self.assertIn("state_root=" + str(paths["state_root"]), raw)
            self.assertNotIn("sdk_matrix", raw)

    def test_forwarded_runtime_or_initial_state_uses_its_exact_transport_root(self):
        for wave, expected_root in ((0, "product-resume-state"), (5, "runtime-state")):
            with self.subTest(wave=wave), tempfile.TemporaryDirectory() as checkout, \
                    tempfile.TemporaryDirectory() as outputs:
                root = Path(checkout).resolve()
                plan, destination = root / "plan.json", root / "build/captured"
                output = Path(outputs).resolve() / "github-output"
                plan.write_text("original plan")
                output.touch()
                with patch.object(product_reuse, "capture_runtime_resume_upload") as capture, \
                        patch.object(sdk_workflow, "matrix", side_effect=AssertionError("premature election")):
                    paths = sdk_workflow.capture_transport(plan, destination, output, artifact_id=71,
                        artifact_sha256="sha256:" + "a" * 64, trusted_workflow_sha="b" * 40,
                        state_wave=wave, repository_root=root, environ={}, token="synthetic")
                self.assertEqual(wave, capture.call_args.kwargs["state_wave"])
                self.assertIsNone(capture.call_args.kwargs["sdk_state_wave"])
                self.assertEqual(destination / "original" / expected_root, paths["state_root"])

    def test_mixed_runtime_and_sdk_waves_reject_before_capture(self):
        with tempfile.TemporaryDirectory() as checkout, tempfile.TemporaryDirectory() as outputs:
            root = Path(checkout).resolve()
            output = Path(outputs).resolve() / "github-output"
            output.touch()
            with patch.object(product_reuse, "capture_runtime_resume_upload") as capture, \
                    self.assertRaisesRegex(ValueError, "one exact current state wave"):
                sdk_workflow.capture_transport(root / "plan", root / "build/captured", output,
                    artifact_id=71, artifact_sha256="sha256:" + "a" * 64,
                    trusted_workflow_sha="b" * 40, state_wave=5, sdk_state_wave=12,
                    repository_root=root, environ={}, token="synthetic")
            capture.assert_not_called()

    def test_output_cannot_mutate_captured_state_or_source(self):
        with tempfile.TemporaryDirectory() as checkout, tempfile.TemporaryDirectory() as outputs:
            root = Path(checkout).resolve()
            plan, destination = root / "plan.json", root / "build/captured"
            plan.write_text("original plan")
            alias = Path(outputs).resolve() / "plan-alias"
            alias.symlink_to(plan)
            hardlink = Path(outputs).resolve() / "plan-hardlink"
            hardlink.hardlink_to(plan)
            for output in (plan, destination / "original/state.json", root / "other-output", alias, hardlink):
                with self.subTest(output=output), patch.object(product_reuse, "capture_runtime_resume_upload") as capture, \
                        self.assertRaisesRegex(ValueError, "outside source|singly linked"):
                    sdk_workflow.capture_transport(plan, destination, output, artifact_id=71,
                        artifact_sha256="sha256:" + "a" * 64, trusted_workflow_sha="b" * 40,
                        sdk_state_wave=17, repository_root=root, environ={}, token="synthetic")
                capture.assert_not_called()
            self.assertEqual("original plan", plan.read_text())

    def test_cli_rejects_unauthorized_policy_flags_and_out_of_range_wave(self):
        arguments = ["capture-transport", "--plan", "plan", "--destination", "captured",
            "--github-output", "output", "--repository-root", "repo",
            "--artifact-id", "71", "--artifact-sha256", "sha256:" + "a" * 64,
            "--trusted-workflow-sha", "b" * 40, "--sdk-state-wave", "17"]
        for extra in (("--sdk-android-metadata-policy", "untrusted.json"),
                      ("--sdk-state-wave", "20"), ("--state-wave", "6")):
            with self.subTest(extra=extra), patch.object(sdk_workflow, "capture_transport") as capture, \
                    self.assertRaises(SystemExit):
                sdk_workflow.main([*arguments, *extra])
            capture.assert_not_called()

    def test_cli_requires_runner_owned_output_path(self):
        arguments = ["capture-transport", "--plan", "plan", "--destination", "captured",
            "--github-output", "output", "--repository-root", "repo",
            "--artifact-id", "71", "--artifact-sha256", "sha256:" + "a" * 64,
            "--trusted-workflow-sha", "b" * 40, "--sdk-state-wave", "17"]
        with patch.dict(os.environ, {"GITHUB_OUTPUT": "different-output"}), \
                patch.object(sdk_workflow, "capture_transport") as capture, self.assertRaises(SystemExit):
            sdk_workflow.main(arguments)
        capture.assert_not_called()
        with patch.dict(os.environ, {"GITHUB_OUTPUT": "output"}), \
                patch.object(sdk_workflow, "capture_transport") as capture:
            self.assertEqual(0, sdk_workflow.main(arguments))
        capture.assert_called_once()

    def test_composite_runs_only_official_transport_capture(self):
        source = (Path(__file__).resolve().parents[2] /
                  ".github/actions/capture-sdk-transport/action.yml").read_text()
        self.assertIn("python3 -B -m ci.sdk_workflow capture-transport", source)
        self.assertIn("--sdk-state-wave \"$SDK_STATE_WAVE\"", source)
        self.assertIn('wave=(--state-wave "$STATE_WAVE")', source)
        self.assertIn('if [ -n "$SDK_STATE_WAVE" ]; then', source)
        self.assertNotIn("sdk-matrix", source)
        self.assertNotIn("setup-", source)
        self.assertNotIn("--sdk-android-metadata-policy", source)
        self.assertNotIn("--sdk-facade-metadata-policy", source)


if __name__ == "__main__":
    unittest.main()
