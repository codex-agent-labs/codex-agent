"""Workflow matrix selection for a missing authenticated tooling release."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest


WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/product-validation.yml"


class ToolingWorkflowSelectionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = WORKFLOW.read_text(encoding="utf-8")
        cls.selection = cls.source.split("      - id: product-selection\n", 1)[1].split(
            "      - id: upload_plan\n", 1,
        )[0]
        embedded = cls.selection.split("          python3 - <<'PY'\n", 1)[1].rsplit(
            "          PY", 1,
        )[0]
        cls.script = textwrap.dedent(embedded)

    def select(self, matrix, *, miss="false", authorized="true", reused="false"):
        with tempfile.TemporaryDirectory(prefix="tooling-workflow-selection-") as temporary:
            output = Path(temporary) / "github-output"
            result = subprocess.run(
                [sys.executable, "-B", "-c", self.script],
                env={
                    "ORIGINAL_PRODUCT_MATRIX": json.dumps(matrix),
                    "TOOLING_MISS": miss,
                    "AUTHORIZED": authorized,
                    "VALIDATION_REUSED": reused,
                    "GITHUB_OUTPUT": str(output),
                },
                text=True,
                capture_output=True,
            )
            value = None
            if output.exists():
                line = output.read_text(encoding="utf-8").strip()
                self.assertTrue(line.startswith("product_matrix="), line)
                value = json.loads(line.removeprefix("product_matrix="))
            return result, value

    def test_tooling_miss_adds_only_a_disabled_contracts_row(self):
        original = [{"lane": "android", "build": True, "test": False, "metadata": True}]
        result, selected = self.select(original, miss="true")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual([
            {"lane": "contracts", "build": False, "test": False, "metadata": False},
            *original,
        ], selected)

    def test_hit_and_empty_miss_preserve_the_original_matrix(self):
        original = [{"lane": "node-js", "build": False, "test": True, "metadata": False}]
        for miss in ("false", ""):
            with self.subTest(miss=miss):
                result, selected = self.select(original, miss=miss)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual(original, selected)

    def test_existing_contracts_row_is_not_replaced_or_duplicated(self):
        original = [
            {"lane": "contracts", "build": True, "test": True, "metadata": True},
            {"lane": "portable", "build": True, "test": False, "metadata": False},
        ]
        result, selected = self.select(original, miss="true")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(original, selected)

    def test_unauthorized_or_reused_validation_suppresses_product_work(self):
        original = [{"lane": "contracts", "build": True, "test": True, "metadata": True}]
        for authorized, reused in (("false", "false"), ("true", "true")):
            with self.subTest(authorized=authorized, reused=reused):
                result, selected = self.select(
                    original, miss="true", authorized=authorized, reused=reused,
                )
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual([], selected)

    def test_invalid_tooling_miss_is_rejected_without_output(self):
        for miss in ("TRUE", "0", " true"):
            with self.subTest(miss=miss):
                result, selected = self.select([], miss=miss)
                self.assertNotEqual(0, result.returncode)
                self.assertIsNone(selected)
                self.assertIn("Invalid tooling miss state", result.stderr)

    def test_workflow_uses_selected_matrix_and_forces_only_missing_tooling_contracts(self):
        self.assertIn("product_matrix: ${{ steps.product-selection.outputs.product_matrix }}", self.source)
        self.assertIn("ORIGINAL_PRODUCT_MATRIX: ${{ steps.impact.outputs.product_matrix }}", self.selection)
        product = self.source.split("\n  product:\n", 1)[1].split("\n  contract-continuation:\n", 1)[0]
        condition = "${{ matrix.lane == 'contracts' && needs.plan.outputs.tooling_miss == 'true' }}"
        self.assertEqual(2, product.count(condition))
        self.assertIn(f"force-build: {condition}", product)
        self.assertIn(f"reuse-disabled: {condition}", product)


if __name__ == "__main__":
    unittest.main()
