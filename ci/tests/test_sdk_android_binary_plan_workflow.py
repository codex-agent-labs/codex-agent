"""The first Android continuation job only elects authenticated work."""

from pathlib import Path
import re
import unittest


WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/product-validation.yml"


class AndroidBinaryPlanWorkflowTest(unittest.TestCase):
    def test_wave_fifteen_plan_requires_authorized_core_state_without_worker(self):
        source = WORKFLOW.read_text()
        match = re.search(
            r"(?ms)^  sdk-android-binary-plan:\n.*?(?=^  [a-z][a-z0-9-]*:|\Z)",
            source,
        )
        self.assertIsNotNone(match)
        job = match[0]
        self.assertIn("needs: [plan, sdk-plan, sdk-core-metadata-result]", job)
        for condition in (
            "needs.plan.outputs.event_authorized == 'true'",
            "needs.plan.outputs.remote_build_authorized == 'true'",
            "needs.sdk-plan.result == 'success'",
            "needs.sdk-core-metadata-result.result == 'success'",
            "needs.sdk-core-metadata-result.outputs.artifact_id != ''",
        ):
            self.assertIn(condition, job)
        self.assertIn("sdk-family: android-binary", job)
        self.assertIn("artifact-id: ${{ needs.sdk-core-metadata-result.outputs.artifact_id }}", job)
        self.assertIn("artifact-sha256: ${{ needs.sdk-core-metadata-result.outputs.artifact_digest }}", job)
        self.assertIn("sdk-validation-tooling: ${{ steps.tooling.outputs.tooling-policy }}", job)
        self.assertIn("sdk-apple-validation-policy: ${{ steps.tooling.outputs.apple-policy }}", job)
        self.assertNotIn("    strategy:\n", job)
        self.assertNotIn("sdk-android-maven-worker", job)
        self.assertNotIn("sdk-android-binary-plan", re.search(
            r"(?ms)^  sdk-completion:\n.*?(?=^  [a-z][a-z0-9-]*:|\Z)", source,
        )[0])
        gate = re.search(r"(?ms)^  merge-gate:\n.*?(?=^  [a-z][a-z0-9-]*:|\Z)", source)[0]
        self.assertIn("sdk-android-binary-plan", gate.split("    needs:", 1)[1].split("\n", 1)[0])


if __name__ == "__main__":
    unittest.main()
