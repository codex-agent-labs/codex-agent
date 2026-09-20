"""Composite Apple attestation routing; no hosted signing or native work runs."""

import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
CI_ROOT = ROOT / "ci"
if str(CI_ROOT) not in sys.path:
    sys.path.insert(0, str(CI_ROOT))
SECRET = "CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY"


class SdkAppleAttestationActionTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sdk-apple-attestation-action-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.trusted = self.root / "trusted source"
        self.action_path = self.trusted / ".github/actions/attest-sdk-apple-validation"
        self.action_path.mkdir(parents=True)
        self.candidate = self.root / "candidate source"
        self.candidate.mkdir()
        self.scratch = self.root / "runner scratch"
        self.scratch.mkdir()
        self.plan = self.root / "original plan.json"
        self.plan.write_bytes(b"original caller plan\n")
        self.output = self.root / "github output"
        self.environment = {
            "GITHUB_ACTION_PATH": str(self.action_path),
            "GITHUB_OUTPUT": str(self.output),
            "GITHUB_TOKEN": "caller-observation-token",
            "RUNNER_TEMP": str(self.scratch),
            "PLAN_PATH": str(self.plan),
            "CANDIDATE_ROOT": str(self.candidate),
            "TARGET": "ios-arm64",
            "BUILD_KEY": "sha256:" + "a" * 64,
            "VALIDATION_TREE": "b" * 40,
            "TRUSTED_WORKFLOW_SHA": "c" * 40,
            "TRUSTED_SOURCE_SHA": "d" * 40,
        }
        self.source = (ROOT / ".github/actions/attest-sdk-apple-validation/action.yml").read_text()

    def execute_capture(self):
        code = self.source.split("        python3 -B - <<'PY'\n", 1)[1].split("\n        PY", 1)[0]
        with patch.dict(os.environ, self.environment, clear=True), patch("sys.path", list(sys.path)):
            exec(compile(textwrap.dedent(code), "<sdk-apple-attestation-capture>", "exec"), {})

    def worker(self, command, **arguments):
        self.assertEqual([sys.executable, "-B"], command[:2])
        self.assertEqual(self.trusted / "ci/sdk_apple_worker_capture.py", Path(command[2]))
        fields = dict(zip(command[3::2], command[4::2]))
        capture = Path(fields.pop("--destination"))
        self.assertEqual({
            "--plan": str(self.plan),
            "--candidate-root": str(self.candidate),
            "--target": "ios-arm64",
            "--expected-build-key": self.environment["BUILD_KEY"],
            "--trusted-workflow-sha": self.environment["TRUSTED_WORKFLOW_SHA"],
            "--github-output": str(self.output),
        }, fields)
        self.assertTrue(capture.is_relative_to(self.scratch))
        self.assertFalse(capture.is_relative_to(self.trusted))
        self.assertFalse(capture.is_relative_to(self.candidate))
        self.assertEqual(self.trusted, arguments["cwd"])
        self.assertIs(os.environ, arguments["env"])
        self.assertNotIn(SECRET, arguments["env"])
        self.assertTrue(arguments["check"])
        receipt = capture / "original/shard/phase-receipt.json"
        receipt.parent.mkdir(parents=True)
        receipt.write_bytes(b"mocked exact worker receipt\n")
        with self.output.open("a") as output:
            output.write("artifact_id=17\n")
            output.write("artifact_sha256=sha256:" + "e" * 64 + "\n")
            output.write("receipt_path=" + str(receipt) + "\n")
            output.write("receipt_sha256=sha256:" + "f" * 64 + "\n")
        self.capture = capture
        return subprocess.CompletedProcess(command, 0)

    def test_non_secret_capture_uses_reviewed_source_and_external_fresh_result(self):
        def git(_root, *arguments):
            return self.environment["TRUSTED_SOURCE_SHA"] if arguments == ("rev-parse", "HEAD") else ""

        with patch("products.inventory.run_git", side_effect=git), \
                patch("subprocess.run", side_effect=self.worker) as worker:
            self.execute_capture()
        worker.assert_called_once()
        outputs = dict(line.split("=", 1) for line in self.output.read_text().splitlines())
        self.assertEqual("17", outputs["artifact_id"])
        self.assertEqual("sha256:" + "f" * 64, outputs["receipt_sha256"])
        self.assertEqual(str(self.capture), outputs["capture_path"])
        result = Path(outputs["result_path"])
        self.assertEqual(self.capture.parent / "signed-result", result)
        self.assertFalse(result.exists())

    def test_secret_pin_overlap_and_child_failure_never_emit_local_outputs(self):
        baseline = dict(self.environment)
        cases = (
            ({SECRET: ""}, ValueError),
            ({"CANDIDATE_ROOT": str(self.trusted)}, ValueError),
            ({"RUNNER_TEMP": str(self.candidate)}, ValueError),
            ({"TRUSTED_SOURCE_SHA": "0" * 40}, ValueError),
        )
        for changes, error in cases:
            self.environment = {**baseline, **changes}
            with self.subTest(changes=changes), patch(
                "products.inventory.run_git",
                side_effect=lambda _root, *args: "d" * 40 if args == ("rev-parse", "HEAD") else "",
            ), patch("tempfile.mkdtemp") as allocate, patch("subprocess.run") as worker, \
                    self.assertRaises(error):
                self.execute_capture()
            allocate.assert_not_called()
            worker.assert_not_called()
            self.assertFalse(self.output.exists())

        self.environment = baseline
        with patch("products.inventory.run_git", side_effect=lambda _root, *args:
                "d" * 40 if args == ("rev-parse", "HEAD") else ""), \
                patch("subprocess.run", side_effect=subprocess.CalledProcessError(9, ["fixed-worker"])), \
                self.assertRaises(subprocess.CalledProcessError):
            self.execute_capture()
        self.assertFalse(self.output.exists())

    def test_exact_three_step_authority_order_and_single_secret_scope(self):
        capture = self.source.index("ci/sdk_apple_worker_capture.py")
        preparation = self.source.index("ci/sdk_apple_upload_locator.py preparation")
        signing = self.source.index("ci/sdk_apple_release_cli.py sign")
        upload = self.source.index("uses: actions/upload-artifact@")
        self.assertLess(capture, preparation)
        self.assertLess(preparation, signing)
        self.assertLess(signing, upload)
        self.assertEqual(1, self.source.count("${{ inputs.private-key }}"))
        self.assertEqual(1, self.source.count(SECRET))
        before_sign = self.source[:self.source.index("    - id: sign")]
        self.assertNotIn(SECRET, before_sign)
        self.assertNotIn("${{ inputs.private-key }}", before_sign)
        for value in (
            "--validation-receipt \"$VALIDATION_RECEIPT\"",
            "--expected-receipt-sha256 \"$RECEIPT_SHA256\"",
            "--artifact-id \"$VALIDATION_ARTIFACT_ID\"",
            "--artifact-sha256 \"$VALIDATION_ARTIFACT_SHA256\"",
            "--preparation-artifact-id \"$PREPARATION_ARTIFACT_ID\"",
            "--preparation-artifact-sha256 \"$PREPARATION_ARTIFACT_SHA256\"",
            "--trusted-source-sha \"$TRUSTED_SOURCE_SHA\"",
            "--trusted-workflow-sha \"$TRUSTED_WORKFLOW_SHA\"",
            "--validation-tree \"$VALIDATION_TREE\"",
        ):
            self.assertIn(value, self.source)
        for forbidden in ("setup-kmp", "setup-java", "gradlew", "java -jar", "GITHUB_WORKSPACE"):
            self.assertNotIn(forbidden, self.source)

    def test_upload_is_the_entire_five_root_signer_result_with_canonical_name(self):
        upload = self.source.split("    - id: upload\n", 1)[1]
        self.assertIn("path: ${{ steps.capture.outputs.result_path }}", upload)
        self.assertNotIn("sdk-apple-validation-evidence/", upload)
        self.assertIn(
            "name: codex-agent-sdk-apple-validation-evidence-${{ inputs.target }}-"
            "${{ steps.sign.outputs.receipt_hex }}-${{ inputs.tree }}-attempt-${{ github.run_attempt }}",
            upload,
        )
        for setting in ("if-no-files-found: error", "overwrite: false", "include-hidden-files: true",
                        "compression-level: 0", "retention-days: 90"):
            self.assertIn(setting, upload)
        inputs = self.source.split("inputs:\n", 1)[1].split("outputs:\n", 1)[0]
        self.assertEqual({"plan-path", "candidate-root", "target", "build-key", "tree",
                          "trusted-workflow-sha", "trusted-source-sha", "private-key"},
                         set(re.findall(r"^  ([a-z0-9-]+):$", inputs, re.MULTILINE)))
        outputs = self.source.split("outputs:\n", 1)[1].split("runs:\n", 1)[0]
        self.assertEqual({"artifact-id", "artifact-sha256", "receipt-sha256"},
                         set(re.findall(r"^  ([a-z0-9-]+):$", outputs, re.MULTILINE)))


if __name__ == "__main__":
    unittest.main()
