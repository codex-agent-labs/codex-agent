"""Original SDK upload transport is captured before, not as, metadata election."""

from pathlib import Path
import os
import json
import io
import zipfile
import re
import subprocess
import textwrap
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
                environ={}, token="synthetic", allow_earlier_attempt=True)
            self.assertEqual(destination / "original/runtime-state", paths["state_root"])
            self.assertEqual(destination / "original/product-resume-state", paths["discovery_root"])
            self.assertEqual(plan, paths["plan_path"])
            raw = output.read_text()
            self.assertIn("state_root=" + str(paths["state_root"]), raw)
            self.assertNotIn("sdk_matrix", raw)

    def test_compact_capture_keeps_complete_caller_plan_for_apple_intake(self):
        from receipt import INPUT_NAMES
        from sdk_apple_native import LANES
        with tempfile.TemporaryDirectory() as checkout, tempfile.TemporaryDirectory() as outputs:
            root = Path(checkout).resolve()
            plan, destination = root / "plan/impact-plan.json", root / "build/captured"
            plan.parent.mkdir()
            plan.write_bytes(b"exact current plan\n")
            for lane in LANES:
                for name in INPUT_NAMES.values():
                    member = plan.parent / "inventories" / lane / name
                    member.parent.mkdir(parents=True, exist_ok=True)
                    member.write_bytes((lane + "/" + name).encode())
            output = Path(outputs).resolve() / "github-output"
            output.touch()

            def capture(source, target, **kwargs):
                compact = target / "original/product-resume-inputs/plan/impact-plan.json"
                compact.parent.mkdir(parents=True)
                compact.write_bytes(source.read_bytes())

            with patch.object(product_reuse, "capture_runtime_resume_upload", side_effect=capture):
                paths = sdk_workflow.capture_transport(plan, destination, output, artifact_id=71,
                    artifact_sha256="sha256:" + "a" * 64, trusted_workflow_sha="b" * 40,
                    repository_root=root, environ={}, token="synthetic")
            for lane in LANES:
                for name in INPUT_NAMES.values():
                    self.assertEqual((lane + "/" + name).encode(),
                        (paths["plan_path"].parent / "inventories" / lane / name).read_bytes())
            compact = destination / "original/product-resume-inputs/plan"
            self.assertEqual(["impact-plan.json"], sorted(p.name for p in compact.iterdir()))

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

    def test_external_caller_plan_keeps_exact_capture_and_path_guards(self):
        from products.inventory import sha256_bytes
        with tempfile.TemporaryDirectory() as checkout, tempfile.TemporaryDirectory() as runner:
            root, external = Path(checkout).resolve(), Path(runner).resolve()
            plan = external / "plan/impact-plan.json"
            plan.parent.mkdir()
            output = external / "github-output"
            output.touch()
            producer = {"tree": "c" * 40, "runAttempt": 1}
            for case in ("valid", "wrong-upload-plan", "late-plan-change", "symlink-plan", "external-destination", "plan-output", "plan-output-alias"):
                with self.subTest(case=case):
                    plan.write_bytes(b"exact caller plan\n")
                    destination = (external if case == "external-destination" else root) / case
                    selected_plan = plan if case != "plan-output-alias" else plan.parent / ".." / "plan" / plan.name
                    if case == "symlink-plan":
                        selected_plan = external / "alias.json"
                        selected_plan.symlink_to(plan)
                    stream = io.BytesIO()
                    with zipfile.ZipFile(stream, "w") as archive:
                        for name, raw in {"product-resume-inputs/plan/impact-plan.json":
                                b"wrong plan\n" if case == "wrong-upload-plan" else plan.read_bytes(),
                                "product-resume-state/state.json": b"fixture discovery\n",
                                "runtime-state/state.json": b"fixture state, not an admission\n"}.items():
                            archive.writestr(name, raw)
                    raw = stream.getvalue()
                    artifact = {"digest": sha256_bytes(raw), "size_in_bytes": len(raw)}
                    def download(*args, **kwargs):
                        kwargs["destination"].write_bytes(raw)
                        if case == "late-plan-change":
                            plan.write_bytes(b"changed caller plan\n")
                        return artifact, None
                    with patch.object(product_reuse, "_validate_plan",
                            return_value={"remoteBuildAuthorized": True, "event": "pull_request"}), \
                            patch.object(product_reuse, "_consumer", return_value={"producer": producer}), \
                            patch.object(product_reuse, "_retry_upload_producer", return_value=producer), \
                            patch.object(product_reuse, "_observe_ci_producer_jobs", return_value=[{"run": {}}]), \
                            patch.object(product_reuse, "_download_contract_ci_upload", side_effect=download) as fetched, \
                            patch.object(product_reuse, "_require_artifact_job_window") as window, \
                            patch.object(sdk_workflow, "matrix", side_effect=AssertionError("premature election")):
                        def capture():
                            return sdk_workflow.capture_transport(selected_plan, destination,
                                plan if case in {"plan-output", "plan-output-alias"} else output, artifact_id=71,
                                artifact_sha256=artifact["digest"], trusted_workflow_sha="b" * 40,
                                sdk_state_wave=7, repository_root=root, environ={}, token="synthetic")
                        if case == "valid":
                            paths = capture()
                            self.assertEqual(plan, paths["plan_path"])
                            self.assertEqual(plan.read_bytes(),
                                (paths["input_root"] / "product-resume-inputs/plan/impact-plan.json").read_bytes())
                            fetched.assert_called_once()
                            window.assert_called_once()
                        else:
                            with self.assertRaises(ValueError):
                                capture()
                            self.assertFalse(destination.exists())
                            if case in {"symlink-plan", "external-destination", "plan-output", "plan-output-alias"}:
                                fetched.assert_not_called()
                    if case != "late-plan-change":
                        self.assertEqual(b"exact caller plan\n", plan.read_bytes())

    def test_collector_capture_uses_transport_but_preserves_worker_routes(self):
        root = Path(__file__).resolve().parents[2]
        action = (root / ".github/actions/capture-runtime-state/action.yml").read_text()
        step = action.split("    - id: capture\n", 1)[1]
        script = textwrap.dedent(step.split("        script: |\n", 1)[1])
        with tempfile.TemporaryDirectory() as temporary:
            scratch = Path(temporary).resolve()
            binary = scratch / "python3"
            binary.write_text(f"#!{sys.executable}\nimport json, os, sys\n"
                "with open(os.environ['COMMAND_LOG'], 'w') as stream:\n"
                "    json.dump(sys.argv[1:], stream)\n")
            binary.chmod(0o700)
            log = scratch / "command.json"
            env = dict(os.environ, PATH=str(scratch) + os.pathsep + os.environ["PATH"],
                COMMAND_LOG=str(log), GITHUB_WORKSPACE=str(scratch),
                GITHUB_OUTPUT=str(scratch / "output"), CODEX_AGENT_COMPLETED_REUSE_POLICY="signed-policy.json")
            env.update({name: "" for name in re.findall(r"^        (\w+):", step, re.M)})
            env.update(PLAN_DIRECTORY="plan directory", ARTIFACT_ID="71", ARTIFACT_SHA256="sha256:" + "a" * 64,
                TRUSTED_WORKFLOW_SHA="b" * 40, STATE_WAVE="0", PREPARATION_STATE_WAVE="0",
                SDK_VALIDATION_TOOLING="tooling.json", SDK_APPLE_VALIDATION_POLICY="apple.json")
            cases = (("sdk", "native-metadata", "8", "7"),
                     ("sdk", "ios-validation", "9", "8"),
                     ("sdk", "core-package", "12", "11"), ("sdk", "", "1", ""),
                     ("sdk", "native-metadata", "", "7"),
                     ("runtime", "", "2", ""), ("sdk-ios-binary", "", "3", "2"))
            for product, family, preflight, predecessor in cases:
                with self.subTest(product=product, family=family, preflight=preflight):
                    env.update(STATE_PRODUCT=product, SDK_FAMILY=family,
                        PREFLIGHT_WAVE=preflight, SDK_STATE_WAVE=predecessor)
                    result = subprocess.run(["bash", "-c", script], cwd=scratch, env=env,
                        capture_output=True, text=True)
                    self.assertEqual(0, result.returncode, result.stderr)
                    argv = json.loads(log.read_text())
                    selected = product == "sdk" and bool(preflight)
                    self.assertEqual("capture-transport" if selected else "capture", argv[3 if product != "runtime" else 2])
                    for flag, value in (("--plan", "plan directory/impact-plan.json"),
                            ("--artifact-id", "71"), ("--artifact-sha256", env["ARTIFACT_SHA256"]),
                            ("--trusted-workflow-sha", env["TRUSTED_WORKFLOW_SHA"]),
                            ("--github-output", env["GITHUB_OUTPUT"]),
                            ("--completed-frozen-policy", "signed-policy.json")):
                        self.assertEqual(value, argv[argv.index(flag) + 1])
                    if predecessor:
                        self.assertEqual(predecessor, argv[argv.index("--sdk-state-wave") + 1])
                    if selected:
                        self.assertEqual(str(scratch), argv[argv.index("--repository-root") + 1])
                        for flag in ("--family", "--scope-inputs", "--sdk-validation-tooling", "--sdk-apple-validation-policy"):
                            self.assertNotIn(flag, argv)
                    else:
                        self.assertIn("--sdk-validation-tooling", argv)
                        self.assertIn("--sdk-apple-validation-policy", argv)
                        if product == "sdk":
                            self.assertEqual(family, argv[argv.index("--family") + 1])
                            self.assertIn("--scope-inputs", argv)
                        elif product == "sdk-ios-binary":
                            self.assertIn("--ios-binary", argv)

            env.update(STATE_PRODUCT="sdk", SDK_FAMILY="native-metadata", PREFLIGHT_WAVE="8", SDK_STATE_WAVE="7")
            for key, value in (("COMPONENT", "python"), ("PHASE", "metadata"), ("TARGET", "desktop"),
                    ("BUILD_KEY", "sha256:" + "c" * 64), ("CONTINUATION", "selected"),
                    ("SDK_FAMILY", "unknown"), ("PREPARATION_PHASE", "validation")):
                with self.subTest(rejected=key):
                    log.unlink(missing_ok=True)
                    result = subprocess.run(["bash", "-c", script], cwd=scratch,
                        env={**env, key: value}, capture_output=True, text=True)
                    self.assertNotEqual(0, result.returncode)
                    self.assertFalse(log.exists(), "invalid input reached capture command")

    def test_collector_still_requires_full_replay_before_advancement(self):
        for family, wave in (("native-metadata", 8), ("ios-validation", 9), ("core-package", 12)):
            with self.subTest(family=family), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                original = root / "original"
                (original / "runtime-state").mkdir(parents=True)
                (original / "product-resume-state").mkdir()
                tooling, apple, frozen = {"caller": "tooling"}, {"caller": "apple"}, object()
                with patch.object(product_reuse, "_verified_product_state",
                        side_effect=ValueError("mandatory full replay rejected")) as verified, \
                        patch.object(product_reuse, "advance_products") as advance, \
                        self.assertRaisesRegex(ValueError, "mandatory full replay rejected"):
                    sdk_workflow.collect(original, root / "next", root / "output", wave=wave,
                        family=family, trusted_workflow_sha="b" * 40, repository_root=root,
                        environ={}, token="synthetic", sdk_validation_tooling=tooling,
                        sdk_apple_validation_policy=apple, completed_frozen=frozen)
                verified.assert_called_once()
                self.assertEqual(original / "product-resume-inputs/plan/impact-plan.json", verified.call_args.args[0])
                self.assertEqual(original / "runtime-state", verified.call_args.args[2])
                self.assertIs(tooling, verified.call_args.args[5])
                self.assertIs(apple, verified.call_args.kwargs["sdk_apple_validation_policy"])
                self.assertIs(frozen, verified.call_args.kwargs["completed_frozen"])
                self.assertEqual("b" * 40, verified.call_args.kwargs["sdk_original_workflow_sha"])
                self.assertEqual(tuple(sorted(product_reuse.SDK_FAMILY_INSTANCES[family])),
                                 verified.call_args.kwargs["requested_scope"])
                advance.assert_not_called()

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
