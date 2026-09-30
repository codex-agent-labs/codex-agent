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

    def select(self, matrix, *, miss="false", authorized="true", reused="false",
               full_reuse="false", target_jobs="true"):
        with tempfile.TemporaryDirectory(prefix="tooling-workflow-selection-") as temporary:
            output = Path(temporary) / "github-output"
            result = subprocess.run(
                [sys.executable, "-B", "-c", self.script],
                env={
                    "ORIGINAL_PRODUCT_MATRIX": json.dumps(matrix),
                    "TOOLING_MISS": miss,
                    "PRODUCT_FULL_REUSE": full_reuse,
                    "PRODUCT_TARGET_JOBS_REQUIRED": target_jobs,
                    "AUTHORIZED": authorized,
                    "VALIDATION_REUSED": reused,
                    "GITHUB_OUTPUT": str(output),
                },
                text=True,
                capture_output=True,
            )
            values = None
            if output.exists():
                lines = [line.split("=", 1) for line in output.read_text(encoding="utf-8").splitlines()]
                self.assertEqual({"product_matrix", "contract_matrix"}, {key for key, _ in lines})
                values = {key: json.loads(value) for key, value in lines}
            return result, values

    def test_tooling_miss_adds_only_a_disabled_contracts_row(self):
        original = [{"lane": "android", "build": True, "test": False, "metadata": True}]
        result, selected = self.select(original, miss="true")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(original, selected["product_matrix"])
        self.assertEqual({"include": [{"lane": "contracts", "build": False,
                                       "test": False, "metadata": False}]}, selected["contract_matrix"])

    def test_hit_and_empty_miss_preserve_the_original_matrix(self):
        original = [{"lane": "node-js", "build": False, "test": True, "metadata": False}]
        for miss in ("false", ""):
            with self.subTest(miss=miss):
                result, selected = self.select(original, miss=miss)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual(original, selected["product_matrix"])
                self.assertEqual({"include": []}, selected["contract_matrix"])

    def test_existing_contracts_row_is_not_replaced_or_duplicated(self):
        original = [
            {"lane": "contracts", "build": True, "test": True, "metadata": True},
            {"lane": "portable", "build": True, "test": False, "metadata": False},
        ]
        result, selected = self.select(original, miss="true")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(original[1:], selected["product_matrix"])
        self.assertEqual({"include": original[:1]}, selected["contract_matrix"])

    def test_unauthorized_or_reused_validation_suppresses_product_work(self):
        original = [{"lane": "contracts", "build": True, "test": True, "metadata": True}]
        for authorized, reused in (("false", "false"), ("true", "true")):
            with self.subTest(authorized=authorized, reused=reused):
                result, selected = self.select(
                    original, miss="true", authorized=authorized, reused=reused,
                )
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual([], selected["product_matrix"])
                self.assertEqual({"include": []}, selected["contract_matrix"])

    def test_verified_full_reuse_suppresses_both_product_matrices(self):
        original = [
            {"lane": "contracts", "build": True, "test": True, "metadata": True},
            {"lane": "portable", "build": True, "test": False, "metadata": False},
        ]
        result, selected = self.select(original, full_reuse="true", target_jobs="false")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual([], selected["product_matrix"])
        self.assertEqual({"include": []}, selected["contract_matrix"])

    def test_inconsistent_reuse_state_fails_closed(self):
        for full_reuse, target_jobs, miss in (
            ("true", "true", "false"),
            ("false", "false", "false"),
            ("", "", "false"),
            ("true", "false", "true"),
        ):
            with self.subTest(full_reuse=full_reuse, target_jobs=target_jobs, miss=miss):
                result, selected = self.select(
                    [{"lane": "portable", "build": True, "test": False, "metadata": False}],
                    full_reuse=full_reuse, target_jobs=target_jobs, miss=miss,
                )
                self.assertNotEqual(0, result.returncode)
                self.assertIsNone(selected)

    def test_invalid_tooling_miss_is_rejected_without_output(self):
        for miss in ("TRUE", "0", " true"):
            with self.subTest(miss=miss):
                result, selected = self.select([], miss=miss)
                self.assertNotEqual(0, result.returncode)
                self.assertIsNone(selected)
                self.assertIn("Invalid tooling miss state", result.stderr)

    def test_duplicate_contract_rows_fail_before_work_is_selected(self):
        row = {"lane": "contracts", "build": True, "test": True, "metadata": True}
        result, selected = self.select([row, row])
        self.assertNotEqual(0, result.returncode)
        self.assertIsNone(selected)
        self.assertIn("Contract product lane is duplicated", result.stderr)

    def test_workflow_uses_selected_matrix_and_forces_only_missing_tooling_contracts(self):
        self.assertIn("product_matrix: ${{ steps.product-selection.outputs.product_matrix }}", self.source)
        self.assertIn("contract_matrix: ${{ steps.product-selection.outputs.contract_matrix }}", self.source)
        self.assertIn("ORIGINAL_PRODUCT_MATRIX: ${{ steps.impact.outputs.product_matrix }}", self.selection)
        product = self.source.split("\n  product:\n", 1)[1].split("\n  contract-validation:\n", 1)[0]
        child = (WORKFLOW.parent / "contract-validation.yml").read_text(encoding="utf-8")
        contract = child.split("\n  contract-binary:\n", 1)[1].split("\n  tooling-attestation:\n", 1)[0]
        self.assertNotIn("matrix.lane == 'contracts'", product)
        self.assertIn("name: product-contracts", contract)
        self.assertIn("force-build: ${{ fromJSON(inputs.planOutputs).tooling_miss == 'true' }}", contract)
        self.assertIn("reuse-disabled: ${{ fromJSON(inputs.planOutputs).tooling_miss == 'true' }}", contract)
        self.assertIn("needs: [contract-binary]", child)
        self.assertIn("uses: ./.github/workflows/contract-validation.yml", self.source)

    def test_retained_contract_only_builds_tooling_and_never_claims_test_actions(self):
        child = (WORKFLOW.parent / "contract-validation.yml").read_text()
        job = child.split("\n  contract-binary:\n", 1)[1].split("\n  tooling-attestation:\n", 1)[0]
        self.assertIn("contract_next_phase == 'binary' ||", job)
        self.assertIn("contract-tooling-only: ${{ fromJSON(inputs.planOutputs).tooling_miss == 'true' && fromJSON(inputs.planOutputs).contract_next_phase != 'binary' }}", job)
        action = (WORKFLOW.parents[1] / "actions/run-ci-lane/action.yml").read_text()
        production = action.split("    - id: production-execution\n", 1)[1].split("    - id: portable-runtime-products\n", 1)[0]
        script = production.split("      run: |\n", 1)[1]
        script = textwrap.dedent(script).replace("${{ inputs.contract-tooling-only }}", "true")
        with tempfile.TemporaryDirectory() as temporary:
            log = Path(temporary) / "calls"
            gradle = Path(temporary) / "gradlew"
            gradle.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "' + str(log) + '"\n')
            gradle.chmod(0o755)
            subprocess.run(["bash", "-e", "-c", script], cwd=temporary, check=True)
            self.assertEqual(":build-logic:releaseToolingJar --stacktrace\n", log.read_text())
        for step, end in (("contract-product", "contract-product-shard"), ("execution", "runtime-validation-handoff")):
            self.assertIn("inputs.contract-tooling-only != 'true'", action.split("    - id: " + step + "\n", 1)[1].split("    - id: " + end + "\n", 1)[0])
        self.assertIn('forced=(--production-only)', action)


if __name__ == "__main__":
    unittest.main()
