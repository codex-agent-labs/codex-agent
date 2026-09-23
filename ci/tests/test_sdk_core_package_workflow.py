"""Saved Core package wave wiring; hosted package evidence remains pending."""

from pathlib import Path
import re
import unittest


WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/product-validation.yml"


class CorePackageWorkflowTest(unittest.TestCase):
    def test_package_wave_requires_independent_original_binary_and_contract(self):
        source = WORKFLOW.read_text()

        def job(name):
            found = re.search(rf"(?ms)^  {re.escape(name)}:\n.*?(?=^  [a-z][a-z0-9-]*:|\Z)", source)
            self.assertIsNotNone(found, name)
            return found[0]

        plan, worker, collect, result = (job(name) for name in (
            "sdk-core-package-plan", "sdk-core-package", "sdk-collect-12", "sdk-core-package-result"))
        for block in (plan, worker, collect, result):
            self.assertIn("needs.plan.outputs.remote_build_authorized == 'true'", block)
            self.assertIn("needs.sdk-core-binary-result.result == 'success'", block)
        self.assertIn("sdk-family: core-package", plan)
        self.assertIn("sdk-family: core-package", collect)
        self.assertIn("wave: '12'", collect)
        self.assertIn("runs-on: ${{ matrix.runner }}", worker)
        self.assertIn("needs.sdk-core-binary-result.outputs.sdk_state_wave == '11'", worker)
        self.assertIn("needs.sdk-core-binary-result.outputs.binary_artifact_id != ''", worker)
        self.assertIn("ci.sdk_workflow capture-transport", worker)
        self.assertIn("--sdk-state-wave 11", worker)
        self.assertIn("build/sdk-core-package-policy-capture", worker)
        self.assertIn("ci.sdk_core_package_policy", worker)
        self.assertIn("--expected-build-key \"$BUILD_KEY\"", worker)
        self.assertIn("--binary-artifact-id \"$BINARY_ID\"", worker)
        self.assertIn("--binary-original-context \"$BINARY_CONTEXT\"", worker)
        self.assertIn("phase: package", worker)
        self.assertIn("sdk-inputs-id: ${{ needs.sdk-inputs.outputs.artifact_id }}", worker)
        self.assertIn("binary-artifact-id: ${{ needs.sdk-core-binary-result.outputs.binary_artifact_id }}", worker)
        self.assertIn("binary-contract-evidence: ${{ steps.policy.outputs.binary-contract-evidence }}", worker)
        self.assertIn("binary-original-context: ${{ steps.policy.outputs.binary-original-context }}", worker)
        self.assertLess(worker.index("ci.sdk_workflow capture-transport"), worker.index("ci.sdk_core_package_policy"))
        self.assertLess(worker.index("ci.sdk_core_package_policy"), worker.index("uses: ./.github/actions/sdk-core-maven-worker"))
        self.assertIn("select_native_state(json.loads(os.environ['RESULTS']), stage='core-package')", result)
        self.assertIn("sdk-core-package-result", job("sdk-completion").split("    needs:", 1)[1].split("\n", 1)[0])


if __name__ == "__main__":
    unittest.main()
