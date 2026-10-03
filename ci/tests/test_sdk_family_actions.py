"""Execute actual composite routing shell with a recording Python stand-in.

No controller, product command, setup step or network operation is executed.
These checks prove shell argument routing only; Python retains plan admission.
"""

from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[2]
FAMILY_WAVES = {
    "native-package": 4,
    "ios-package": 5,
    "javascript-metadata": 6,
    "native-validation": 7,
    "native-metadata": 8,
    "ios-validation": 9,
}


class SdkFamilyActionsTest(unittest.TestCase):
    def setUp(self):
        self.capture = (ROOT / ".github/actions/capture-runtime-state/action.yml").read_text()
        self.collect = (ROOT / ".github/actions/collect-runtime-wave/action.yml").read_text()
        self.shell = shutil.which("bash")
        self.assertIsNotNone(self.shell, "Composite routing tests require the repository's Bash shell")

    def run_action(self, name, **changes):
        source = self.capture if name == "capture" else self.collect
        block = re.search(rf"(?ms)^    - id: {name}\n(.*?)(?=^    - |\Z)", source)
        self.assertIsNotNone(block)
        script = textwrap.dedent(block[1].split("      run: |\n", 1)[1])
        with tempfile.TemporaryDirectory(prefix="sdk-family-shell-") as temporary:
            root = Path(temporary)
            binary = root / "bin"
            binary.mkdir()
            python = binary / "python3"
            python.write_text("#!/bin/sh\nprintf '%s\\0' \"$@\" >> \"$RECORDED_ARGS\"\n"
                              "printf '%s' \"$GITHUB_TOKEN\" > \"$RECORDED_TOKEN\"\n"
                              "exit \"${PYTHON_EXIT:-0}\"\n")
            python.chmod(0o700)
            record, token = root / "arguments", root / "token"
            output = root / "output with spaces"
            environment = {
                "PATH": str(binary), "RECORDED_ARGS": str(record), "RECORDED_TOKEN": str(token),
                "GITHUB_OUTPUT": str(output), "GITHUB_TOKEN": "synthetic environment-only token",
                "ARTIFACT_ID": "71", "ARTIFACT_SHA256": "sha256:" + "a" * 64,
                "TRUSTED_WORKFLOW_SHA": "b" * 40, "STATE_WAVE": "0", "STATE_PRODUCT": "runtime",
                "SDK_STATE_WAVE": "", "SDK_FAMILY": "", "COMPONENT": "", "PHASE": "", "TARGET": "",
                "BUILD_KEY": "", "PRODUCT": "runtime", "INPUT_ROOT": "/original input/with spaces",
                "WAVE": "1", "SDK_APPLE_VALIDATION_POLICY": "", **changes,
            }
            result = subprocess.run([self.shell, "--noprofile", "--norc", "-c", script], cwd=root,
                                    env=environment, capture_output=True, text=True, check=False)
            args = record.read_bytes().decode().split("\0")[:-1] if record.exists() else None
            observed_token = token.read_text() if token.exists() else None
            return result, args, observed_token, str(output)

    @staticmethod
    def capture_arguments(output, selected=(), *, sdk=False, state_wave="0"):
        return (["-B", "-m", "ci.sdk_workflow", "capture"] if sdk else
                ["-B", "ci/runtime_workflow.py", "capture"]) + [
            "--plan", "build/runtime-plan/impact-plan.json", "--destination", "build/runtime-input",
            "--artifact-id", "71", "--artifact-sha256", "sha256:" + "a" * 64,
            "--trusted-workflow-sha", "b" * 40, "--state-wave", state_wave,
            "--github-output", output, *selected]

    @staticmethod
    def collect_arguments(output, selected=(), *, sdk=False, wave="1"):
        return (["-B", "-m", "ci.sdk_workflow", "collect"] if sdk else
                ["-B", "ci/runtime_workflow.py", "collect"]) + [
            "--input-root", "/original input/with spaces", "--destination", "build/runtime-next",
            "--wave", wave, *selected, "--trusted-workflow-sha", "b" * 40, "--github-output", output]

    def test_capture_routes_each_family_with_exact_original_sdk_state_arguments(self):
        for family, wave in FAMILY_WAVES.items():
            predecessor = str(wave - 1)
            with self.subTest(family=family, predecessor=predecessor):
                result, args, token, output = self.run_action("capture", STATE_PRODUCT="sdk",
                    SDK_FAMILY=family, SDK_STATE_WAVE=predecessor)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual(self.capture_arguments(output,
                    ["--sdk-state-wave", predecessor, "--family", family], sdk=True), args)
                self.assertEqual("synthetic environment-only token", token)
                self.assertNotIn("--token", args)

    def test_csharp_binary_uses_wave_nineteen_after_wave_three(self):
        result, args, _, output = self.run_action("capture", STATE_PRODUCT="sdk",
            SDK_FAMILY="csharp-binary", SDK_STATE_WAVE="3")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(self.capture_arguments(output,
            ["--sdk-state-wave", "3", "--family", "csharp-binary"], sdk=True), args)
        result, args, _, output = self.run_action("collect", PRODUCT="sdk",
            SDK_FAMILY="csharp-binary", WAVE="19")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(self.collect_arguments(output,
            ["--family", "csharp-binary"], sdk=True, wave="19"), args)

    def test_capture_preserves_default_javascript_ios_binary_and_runtime_selection(self):
        cases = (
            ({}, False, []),
            ({"STATE_PRODUCT": "sdk"}, True, []),
            ({"STATE_PRODUCT": "sdk-ios-binary", "SDK_STATE_WAVE": "2"}, True,
             ["--sdk-state-wave", "2", "--ios-binary"]),
            ({"COMPONENT": "linux-arm64", "PHASE": "binary", "TARGET": "linux-arm64", "BUILD_KEY": "sha256:" + "c" * 64}, False,
             ["--component", "linux-arm64", "--phase", "binary", "--target", "linux-arm64", "--expected-build-key", "sha256:" + "c" * 64]),
        )
        for environment, sdk, selected in cases:
            with self.subTest(environment=environment):
                result, args, _, output = self.run_action("capture", **environment)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual(self.capture_arguments(output, selected, sdk=sdk), args)

    def test_capture_forwards_only_explicit_sdk_metadata_caller_policies(self):
        before = self.capture.split("    - id: capture\n", 1)[1]
        for name in ("facade", "android"):
            self.assertIn(f"SDK_{name.upper()}_METADATA_POLICY: ${{{{ inputs.sdk-{name}-metadata-policy }}}}", before)
        for product in ("sdk", "sdk-ios-binary"):
            with self.subTest(product=product):
                result, args, _, output = self.run_action("capture", STATE_PRODUCT=product,
                    SDK_FACADE_METADATA_POLICY="/caller policy/core.json",
                    SDK_ANDROID_METADATA_POLICY="/caller policy/android.json")
                self.assertEqual(0, result.returncode, result.stderr)
                expected = ["--ios-binary"] if product == "sdk-ios-binary" else []
                expected += ["--sdk-facade-metadata-policy", "/caller policy/core.json",
                             "--sdk-android-metadata-policy", "/caller policy/android.json"]
                self.assertEqual(self.capture_arguments(output, expected, sdk=True), args)
        result, args, _, _ = self.run_action("capture", SDK_FACADE_METADATA_POLICY="/caller/core.json")
        self.assertNotEqual(0, result.returncode)
        self.assertIsNone(args)

    def test_capture_invalid_or_mixed_scopes_reject_before_python(self):
        cases = [{"STATE_PRODUCT": "unknown"}, {"SDK_STATE_WAVE": "2"}, {"SDK_FAMILY": "native-package"},
                 {"STATE_PRODUCT": "sdk", "SDK_FAMILY": "unknown"},
                 {"STATE_PRODUCT": "sdk", "SDK_FAMILY": "native-package ios-package"},
                 {"STATE_PRODUCT": "sdk-ios-binary", "SDK_FAMILY": "ios-package"}]
        cases += [{"STATE_PRODUCT": product, field: "not-empty"}
                  for product in ("sdk", "sdk-ios-binary") for field in ("COMPONENT", "PHASE", "TARGET", "BUILD_KEY")]
        for environment in cases:
            with self.subTest(environment=environment):
                result, args, token, _ = self.run_action("capture", **environment)
                self.assertNotEqual(0, result.returncode)
                self.assertIsNone(args)
                self.assertIsNone(token)

    def test_collect_routes_exact_family_and_preserves_legacy_scopes(self):
        cases = [({"PRODUCT": "sdk", "SDK_FAMILY": family, "WAVE": str(wave)}, True,
                  ["--family", family], str(wave)) for family, wave in FAMILY_WAVES.items()]
        cases += [({}, False, ["--state-wave", "0"], "1"),
                  ({"STATE_WAVE": "3", "WAVE": "4"}, False, ["--state-wave", "3"], "4"),
                  ({"PRODUCT": "sdk"}, True, [], "1"),
                  ({"PRODUCT": "sdk-ios-binary", "WAVE": "3"}, True, ["--ios-binary"], "3")]
        for environment, sdk, selected, wave in cases:
            with self.subTest(environment=environment):
                result, args, token, output = self.run_action("collect", **environment)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual(self.collect_arguments(output, selected, sdk=sdk, wave=wave), args)
                self.assertEqual("synthetic environment-only token", token)

    def test_collect_rejects_unknown_and_cross_family_scopes_before_python(self):
        for environment in ({"PRODUCT": "unknown"}, {"SDK_FAMILY": "native-package"},
                {"PRODUCT": "sdk-ios-binary", "SDK_FAMILY": "ios-package"},
                {"PRODUCT": "sdk", "SDK_FAMILY": "unknown"},
                {"PRODUCT": "sdk", "SDK_FAMILY": "native-package javascript-metadata"}):
            with self.subTest(environment=environment):
                result, args, token, _ = self.run_action("collect", **environment)
                self.assertNotEqual(0, result.returncode)
                self.assertIsNone(args)
                self.assertIsNone(token)

    def test_python_failure_propagates_and_collection_forwards_capture_family(self):
        for name in ("capture", "collect"):
            with self.subTest(action=name):
                result, args, _, _ = self.run_action(name, PYTHON_EXIT="17")
                self.assertEqual(17, result.returncode)
                self.assertIsNotNone(args)
        before_collect = self.collect.split("    - id: collect", 1)[0]
        for name in ("product", "sdk-state-wave", "sdk-family", "state-wave"):
            self.assertIn(f"{name}: ${{{{ inputs.{name} }}}}", before_collect)


if __name__ == "__main__":
    unittest.main()
