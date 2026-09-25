"""Saved Core validation wave wiring; real eleven-host evidence remains pending."""

from pathlib import Path
import re
import unittest


WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/product-validation.yml"


class CoreValidationWorkflowTest(unittest.TestCase):
    def test_wave_thirteen_uses_original_inputs_and_fails_after_collection(self):
        source = WORKFLOW.read_text()

        def job(name):
            found = re.search(rf"(?ms)^  {re.escape(name)}:\n.*?(?=^  [a-z][a-z0-9-]*:|\Z)", source)
            self.assertIsNotNone(found, name)
            return found[0]

        plan, worker, collect, result = (job(name) for name in (
            "sdk-core-validation-plan", "sdk-core-validation", "sdk-collect-13",
            "sdk-core-validation-result"))
        for block in (plan, worker, collect, result):
            self.assertIn("needs.plan.outputs.remote_build_authorized == 'true'", block)
            self.assertIn("needs.sdk-core-package-result.result == 'success'", block)
        self.assertIn("sdk-family: core-validation", plan)
        self.assertIn("sdk-family: core-validation", collect)
        self.assertIn("wave: '13'", collect)
        self.assertIn("runs-on: ${{ matrix.runner }}", worker)
        self.assertIn("fail-fast: false", worker)
        self.assertIn("needs.sdk-inputs.result == 'success'", worker)
        self.assertIn("uses: ./.github/actions/capture-sdk-tooling", worker)
        self.assertIn("ci.sdk_core_native_archive_provision", worker)
        self.assertIn("name: Provision only Git-pinned native compiler archives\n        shell: bash", worker)
        self.assertIn("name: Select installed caller Java\n        shell: bash", worker)
        self.assertIn("uses: ./.github/actions/sdk-core-validation-worker", worker)
        self.assertLess(worker.index("ci.sdk_core_native_archive_provision"),
                        worker.index("uses: ./.github/actions/sdk-core-validation-worker"))
        for field in ("sdk-inputs-id", "sdk-inputs-sha256", "sdk-validation-tooling",
                      "sdk-apple-validation-policy", "native-compiler-archive", "build-key", "tree"):
            self.assertIn(field + ":", worker)
        self.assertIn("select_native_state(json.loads(os.environ['RESULTS']), stage='core-validation')", result)
        self.assertIn("sdk-core-validation-result", job("sdk-completion").split("    needs:", 1)[1].split("\n", 1)[0])


if __name__ == "__main__":
    unittest.main()
