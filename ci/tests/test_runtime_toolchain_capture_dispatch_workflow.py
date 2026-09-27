"""The registered CI dispatcher isolates protected toolchain capture."""

import os
from pathlib import Path
import subprocess
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[2]
CI = ROOT / ".github/workflows/ci.yml"
CAPTURE = CI.with_name("runtime-toolchain-capture.yml")


class RuntimeToolchainCaptureDispatchTest(unittest.TestCase):
    def test_exact_source_capture_is_the_only_selected_job(self):
        caller = CI.read_text(encoding="utf-8")
        selected = caller.split("  runtime-toolchain-capture:\n", 1)[1].split(
            "\n  runtime-phase10-record:", 1,
        )[0]
        self.assertIn("inputs.purpose == 'runtime-toolchain-capture'", selected)
        self.assertIn("uses: ./.github/workflows/runtime-toolchain-capture.yml", selected)
        self.assertIn("validationCommit: ${{ inputs.validationCommit }}", selected)
        self.assertIn("validationTree: ${{ inputs.validationTree }}", selected)
        self.assertIn("environment: product-attestation", CAPTURE.read_text(encoding="utf-8"))
        self.assertIn('test "$GITHUB_SHA" = "$VALIDATION_COMMIT"', CAPTURE.read_text(encoding="utf-8"))
        self.assertIn('test "$(git rev-parse \'HEAD^{tree}\')" = "$VALIDATION_TREE"',
                      CAPTURE.read_text(encoding="utf-8"))
        self.assertIn("  workflow_call:\n", CAPTURE.read_text(encoding="utf-8"))

        gate = caller.split("  merge-gate:\n", 1)[1]
        script = textwrap.dedent(gate.split("        run: |\n", 1)[1])
        common = {
            **os.environ,
            "EVENT": "workflow_dispatch",
            "PURPOSE": "runtime-toolchain-capture",
            "PRODUCT_VALIDATION_RESULT": "skipped",
            "SDK_CUSTODY_RESULT": "skipped",
            "RUNTIME_RECORD_RESULT": "skipped",
            "CONTRACT_RECORD_RESULT": "skipped",
            "SDK_AUTHORITY_RESULT": "skipped",
            "SDK_RECORD_RESULT": "skipped",
        }
        for capture, product, expected in (
            ("success", "skipped", 0),
            ("failure", "skipped", 1),
            ("skipped", "skipped", 1),
            ("success", "success", 1),
        ):
            result = subprocess.run(
                ["bash", "-e", "-c", script],
                env={**common, "TOOLCHAIN_CAPTURE_RESULT": capture,
                     "PRODUCT_VALIDATION_RESULT": product},
                capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(expected, result.returncode, (capture, product, result.stderr))


if __name__ == "__main__":
    unittest.main()
