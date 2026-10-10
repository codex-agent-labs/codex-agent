"""Saved Core package wave wiring; hosted package evidence remains pending."""

from pathlib import Path
import json
import os
import re
import tempfile
import textwrap
import unittest
from unittest.mock import patch

from ci.tests.test_sdk_native_continuation import locator, needs_for


WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/product-validation.yml"
CHILD = WORKFLOW.with_name("sdk-core-package-validation.yml")


class CorePackageWorkflowTest(unittest.TestCase):
    def test_package_wave_requires_independent_original_binary_and_contract(self):
        source = CHILD.read_text()

        def job(name):
            found = re.search(rf"(?ms)^  {re.escape(name)}:\n.*?(?=^  [a-z][a-z0-9-]*:|\Z)", source)
            self.assertIsNotNone(found, name)
            return found[0]

        parent = WORKFLOW.read_text()
        plan = parent.split("  sdk-core-package-plan:\n", 1)[1].split("\n  sdk-core-package-wave:\n", 1)[0]
        worker, collect, result = (job(name) for name in (
            "sdk-core-package", "sdk-collect-12", "sdk-core-package-result"))
        self.assertIn("needs.plan.outputs.remote_build_authorized == 'true'", plan)
        self.assertIn("needs.sdk-core-binary-wave.result == 'success'", plan)
        self.assertNotIn("sdk-inputs", plan.split("    needs:", 1)[1].split("\n", 1)[0])
        self.assertIn("uses: ./.github/workflows/sdk-core-package-validation.yml", parent)
        for block in (worker, collect, result):
            self.assertIn("fromJSON(inputs.planOutputs).remote_build_authorized == 'true'", block)
            self.assertIn("fromJSON(inputs.binaryWave).result == 'success'", block)
        self.assertIn("sdk-family: core-package", plan)
        self.assertIn("sdk-family: core-package", collect)
        self.assertIn("wave: '12'", collect)
        self.assertIn("sdk-worker-workflow-path: .github/workflows/sdk-core-package-validation.yml", collect)
        self.assertIn("sdk-worker-job-name: product-validation / sdk-core-package-wave / sdk-core-package-common", collect)
        self.assertIn("runs-on: ${{ matrix.runner }}", worker)
        self.assertIn("fromJSON(inputs.binaryWave).outputs.sdk_state_wave == '11'", worker)
        self.assertIn("fromJSON(inputs.binaryWave).outputs.binary_artifact_id != ''", worker)
        self.assertIn("ci.sdk_workflow capture-transport", worker)
        self.assertIn("--sdk-state-wave 11", worker)
        self.assertIn("build/sdk-core-package-policy-capture", worker)
        self.assertIn("ci.sdk_core_package_policy", worker)
        self.assertIn("--expected-build-key \"$BUILD_KEY\"", worker)
        self.assertIn("--binary-artifact-id \"$BINARY_ID\"", worker)
        self.assertIn("--binary-original-context \"$BINARY_CONTEXT\"", worker)
        self.assertIn("phase: package", worker)
        self.assertIn("sdk-inputs-id: ${{ fromJSON(inputs.sdkInputs).outputs.artifact_id }}", worker)
        self.assertIn("binary-artifact-id: ${{ fromJSON(inputs.binaryWave).outputs.binary_artifact_id }}", worker)
        self.assertIn("binary-contract-evidence: ${{ steps.policy.outputs.binary-contract-evidence }}", worker)
        self.assertIn("binary-original-context: ${{ steps.policy.outputs.binary-original-context }}", worker)
        self.assertLess(worker.index("ci.sdk_workflow capture-transport"), worker.index("ci.sdk_core_package_policy"))
        self.assertLess(worker.index("ci.sdk_core_package_policy"), worker.index("uses: ./.github/actions/sdk-core-maven-worker"))
        self.assertIn("needs['sdk-core-binary-wave'] = json.loads(os.environ['BINARY_RESULT'])", result)
        self.assertIn("needs['sdk-core-package-plan'] = json.loads(os.environ['PACKAGE_PLAN'])", result)
        self.assertIn("select_native_state(needs, stage='core-package')", result)
        self.assertIn("sdk-core-package-wave", parent.split("  sdk-completion:\n", 1)[1].split("\n", 1)[0])

    def test_child_result_rejoins_the_exact_binary_parent_before_selection(self):
        block = CHILD.read_text().split("  sdk-core-package-result:\n", 1)[1]
        script = textwrap.dedent(block.split("          python3 - <<'PY'\n", 1)[1].split("\n          PY", 1)[0])
        for required in (False, True):
            needs = needs_for("core-package", required=required, state=locator("11", "0"))
            binary = needs.pop("sdk-core-binary-wave")
            plan = needs.pop("sdk-core-package-plan")
            with self.subTest(required=required), tempfile.TemporaryDirectory() as temporary:
                output = Path(temporary) / "output"
                with patch.dict(os.environ, {"RESULTS": json.dumps(needs), "BINARY_RESULT": json.dumps(binary),
                                          "PACKAGE_PLAN": json.dumps(plan),
                                          "GITHUB_OUTPUT": str(output)}, clear=True):
                    exec(compile(script, "sdk-core-package-result", "exec"), {})
                values = dict(line.split("=", 1) for line in output.read_text().splitlines())
                self.assertEqual("12" if required else "11", values["sdk_state_wave"])
                binary["result"] = "failure"
                with patch.dict(os.environ, {"RESULTS": json.dumps(needs), "BINARY_RESULT": json.dumps(binary),
                                          "PACKAGE_PLAN": json.dumps(plan),
                                          "GITHUB_OUTPUT": str(output)}, clear=True), self.assertRaises(ValueError):
                    exec(compile(script, "sdk-core-package-result", "exec"), {})


if __name__ == "__main__":
    unittest.main()
