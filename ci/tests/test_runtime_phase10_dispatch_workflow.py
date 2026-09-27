"""Runtime record dispatch cannot silently run product validation or SDK custody."""

from pathlib import Path
import re
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
CI = ROOT / ".github/workflows/ci.yml"
CHILD = CI.with_name("runtime-phase10-output-record.yml")
PRODUCT = CI.with_name("product-validation.yml")


class RuntimePhase10DispatchWorkflowTest(unittest.TestCase):
    def test_dispatch_pins_reviewed_child_and_skips_product_build(self):
        source = CI.read_text(encoding="utf-8")
        child = source.split("  runtime-phase10-record:\n", 1)[1].split("\n  merge-gate:", 1)[0]
        self.assertIn("options: [validation, sdk-catalog-custody, runtime-toolchain-capture, runtime-phase10-record, contract-phase10-record, sdk-phase10-authority, sdk-phase10-record]", source)
        self.assertIn("github.event_name == 'workflow_dispatch' && inputs.purpose == 'runtime-phase10-record'", child)
        match = re.search(r"uses: codex-agent-labs/codex-agent/\.github/workflows/"
                          r"runtime-phase10-output-record\.yml@([0-9a-f]{40})", child)
        self.assertIsNotNone(match)
        committed = subprocess.check_output(
            ["git", "show", f"{match.group(1)}:.github/workflows/runtime-phase10-output-record.yml"],
            cwd=ROOT, text=True,
        )
        self.assertEqual(CHILD.read_text(encoding="utf-8"), committed)
        self.assertIn("attestationJson: ${{ inputs.producerJson }}", child)
        product = source.split("  product-validation:\n", 1)[1].split(
            "\n  sdk-failed-catalog-custody:", 1,
        )[0]
        self.assertIn("inputs.purpose == 'validation'", product)
        match = re.search(r"product-validation\.yml@([0-9a-f]{40})", product)
        self.assertIsNotNone(match)
        self.assertEqual(PRODUCT.read_text(encoding="utf-8"), subprocess.check_output(
            ["git", "show", f"{match.group(1)}:.github/workflows/product-validation.yml"],
            cwd=ROOT, text=True,
        ))

    def test_merge_gate_requires_both_record_and_transport_uploads(self):
        gate = CI.read_text(encoding="utf-8").split("  merge-gate:\n", 1)[1]
        self.assertIn("needs: [product-validation, sdk-failed-catalog-custody, runtime-toolchain-capture, runtime-phase10-record, contract-phase10-record, sdk-phase10-authority, sdk-phase10-record]", gate)
        self.assertIn('test "$PRODUCT_VALIDATION_RESULT" = skipped', gate)
        self.assertIn('test "$SDK_CUSTODY_RESULT" = skipped', gate)
        self.assertIn('test "$RUNTIME_RECORD_RESULT" = success', gate)
        for field in ("RUNTIME_RECORD_ARTIFACT_ID", "RUNTIME_TRANSPORT_ARTIFACT_ID"):
            self.assertIn(f'[[ "${field}" =~ ^[1-9][0-9]*$ ]] || exit 1', gate)
        for field in ("RUNTIME_RECORD_ARTIFACT_SHA256", "RUNTIME_TRANSPORT_ARTIFACT_SHA256"):
            self.assertIn(f'[[ "${field}" =~ ^sha256:[0-9a-f]{{64}}$ ]] || exit 1', gate)


if __name__ == "__main__":
    unittest.main()
