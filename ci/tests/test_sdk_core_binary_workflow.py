"""Saved Core binary wave wiring; hosted compiler evidence remains separate."""

from pathlib import Path
import re
import unittest


WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/product-validation.yml"


class SdkCoreBinaryWorkflowTest(unittest.TestCase):
    def test_wave_eleven_is_elected_collected_and_selected_before_completion(self):
        source = WORKFLOW.read_text()

        def job(name):
            match = re.search(rf"(?ms)^  {re.escape(name)}:\n.*?(?=^  [a-z][a-z0-9-]*:|\Z)", source)
            self.assertIsNotNone(match, name)
            return match[0]

        plan = job("sdk-core-binary-plan")
        worker = job("sdk-core-binary")
        collect = job("sdk-collect-11")
        result = job("sdk-core-binary-result")
        for name, block in (("plan", plan), ("worker", worker), ("collect", collect)):
            with self.subTest(name=name):
                self.assertIn("needs.plan.outputs.remote_build_authorized == 'true'", block)
                self.assertIn("needs.sdk-ios-metadata-result.result == 'success'", block)
                self.assertIn("needs.sdk-ios-metadata-result.outputs.artifact_id", block)
        self.assertIn("sdk-family: core-binary", plan)
        self.assertIn("sdk-family: core-binary", collect)
        self.assertIn("runs-on: ${{ matrix.runner }}", worker)
        self.assertIn("uses: ./.github/actions/sdk-core-maven-worker", worker)
        self.assertIn("phase: binary", worker)
        self.assertIn("build-key: ${{ matrix.buildKey }}", worker)
        self.assertIn("wave: '11'", collect)
        self.assertIn("select_native_state(json.loads(os.environ['RESULTS']), stage='core-binary')", result)
        self.assertIn("sdk-core-binary-result", job("sdk-completion").split("    needs:", 1)[1].split("\n", 1)[0])


if __name__ == "__main__":
    unittest.main()
