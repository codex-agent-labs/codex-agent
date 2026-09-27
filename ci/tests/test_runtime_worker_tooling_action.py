"""Runtime worker caller-policy routing, not tooling or product admission."""

from itertools import product
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[2]


class RuntimeWorkerToolingActionTest(unittest.TestCase):
    def setUp(self):
        self.action = (ROOT / ".github/actions/run-runtime-product-phase/action.yml").read_text()
        self.shell = shutil.which("bash")
        self.assertIsNotNone(self.shell, "Composite routing tests require Bash")

    def test_policy_is_optional_local_and_capture_precedes_all_setup(self):
        inputs = self.action.split("inputs:\n", 1)[1].split("runs:\n", 1)[0]
        self.assertIn("  sdk-validation-tooling:\n    default: ''", inputs)
        self.assertIn("  sdk-apple-validation-policy:\n    default: ''", inputs)
        capture = self.action.split("    - id: captured\n", 1)[1].split("    - if:", 1)[0]
        for name in ("component", "phase", "target", "build-key", "sdk-validation-tooling", "sdk-apple-validation-policy"):
            self.assertIn(f"{name}: ${{{{ inputs.{name} }}}}", capture)
        capture_index = self.action.index("    - id: captured")
        for setup in ("./.github/actions/setup-msvc", "./.github/actions/setup-kmp",
                      "./.github/actions/setup-runtime-archive"):
            self.assertLess(capture_index, self.action.index(setup))
        for forbidden in ("ci.tooling_discovery", "ci.tooling_capture", "capture-sdk-tooling"):
            self.assertNotIn(forbidden, self.action)

    def test_execution_forwards_exact_optional_policy_without_word_splitting(self):
        block = self.action.split("    - name: Execute the exact elected phase\n", 1)[1]
        script = textwrap.dedent(block.split("      run: |\n", 1)[1])
        self.assertIn("SDK_VALIDATION_TOOLING: ${{ inputs.sdk-validation-tooling }}", block)
        self.assertIn("SDK_APPLE_VALIDATION_POLICY: ${{ inputs.sdk-apple-validation-policy }}", block)
        self.assertIn('${extra[@]+"${extra[@]}"}', script)
        with tempfile.TemporaryDirectory(prefix="runtime-worker-tooling-") as temporary:
            root = Path(temporary)
            binary = root / "bin"
            binary.mkdir()
            python = binary / "python3"
            python.write_text("#!/bin/sh\nprintf '%s\\0' \"$@\" > \"$RECORDED_ARGS\"\n"
                              "exit \"${PYTHON_EXIT:-0}\"\n")
            python.chmod(0o700)
            recorded = root / "arguments"
            base = {
                "PATH": str(binary), "RECORDED_ARGS": str(recorded),
                "PLAN": "/original plan/impact.json", "DISCOVERY": "/original discovery",
                "STATE": "/original state", "COMPONENT": "jvm", "PHASE": "binary",
                "TARGET": "jvm", "BUILD_KEY": "sha256:" + "a" * 64, "ARCHIVE": "",
                "SUPERVISOR_ID": "", "SUPERVISOR_SHA256": "",
                "TRUSTED_WORKFLOW_SHA": "b" * 40,
            }
            for (policy, status), apple in product((("", 0), ("/caller policy/with spaces.json", 0),
                                                    ("/caller/policy.json", 17)),
                                                   (None, "", "/caller policy/apple with spaces.json")):
                with self.subTest(policy=policy, status=status, apple=apple):
                    environment = dict(base, SDK_VALIDATION_TOOLING=policy, PYTHON_EXIT=str(status))
                    if apple is not None:
                        environment["SDK_APPLE_VALIDATION_POLICY"] = apple
                    result = subprocess.run(
                        [self.shell, "--noprofile", "--norc", "-c", script], cwd=root,
                        env=environment,
                        capture_output=True, text=True, check=False)
                    self.assertEqual(status, result.returncode, result.stderr)
                    expected = [
                        "-B", "ci/product_reuse.py", "execute-runtime-phase",
                        "--plan", base["PLAN"], "--discovery-root", base["DISCOVERY"],
                        "--state-root", base["STATE"], "--product", "runtime",
                        "--component", base["COMPONENT"], "--phase", base["PHASE"],
                        "--target", base["TARGET"],
                        "--sdk-original-workflow-sha", base["TRUSTED_WORKFLOW_SHA"],
                        "--expected-build-key", base["BUILD_KEY"],
                        "--destination", "build/runtime-worker",
                    ]
                    if policy:
                        expected += ["--sdk-validation-tooling", policy]
                    if apple:
                        expected += ["--sdk-apple-validation-policy", apple]
                    self.assertEqual(expected, recorded.read_bytes().decode().split("\0")[:-1])


if __name__ == "__main__":
    unittest.main()
