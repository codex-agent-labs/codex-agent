"""Local source-wiring checks, not hosted signing acceptance."""

from pathlib import Path
import re
import unittest

from ci.tests.test_contract_attestation_workflow import workflow_job


ROOT = Path(__file__).resolve().parents[2]


class RuntimeNativeAttestationWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / ".github/workflows/product-validation.yml").read_text()
        cls.job = workflow_job(cls.source, "runtime-native-attestation")

    def test_authorization_and_independent_matrix_precede_execution(self):
        guards = self.job.split("    runs-on:", 1)[0]
        for guard in ("needs.plan.outputs.event_authorized == 'true'",
                      "needs.plan.outputs.remote_build_authorized == 'true'",
                      "github.event_name != 'workflow_dispatch'",
                      "needs.runtime-continuation.result == 'success'",
                      "needs.runtime-continuation.outputs.aggregate_state != 'not-selected'",
                      "needs.runtime-continuation.outputs.native_attestation_matrix != '{\"include\":[]}'"):
            self.assertIn(guard, guards)
        self.assertIn("environment: product-attestation", self.job)
        self.assertIn("fail-fast: false", self.job)
        self.assertIn("fromJSON(needs.runtime-continuation.outputs.native_attestation_matrix)", self.job)
        self.assertIn("runtime-native-attestation", workflow_job(self.source, "merge-gate"))

    def test_executable_pin_and_candidate_data_are_separate(self):
        self.assertEqual(2, self.job.count("uses: actions/checkout@"))
        self.assertIn("ref: ${{ needs.plan.outputs.source_sha }}", self.job)
        self.assertIn("TRUSTED_SOURCE_SHA: ${{ needs.plan.outputs.source_sha }}", self.job)
        self.assertIn("TRUSTED_WORKFLOW_SHA: ${{ needs.plan.outputs.publisher_sha }}", self.job)
        for setting in ("path: trusted-source", "path: candidate-source", "fetch-depth: 0",
                        '--repository-root "$GITHUB_WORKSPACE/trusted-source"',
                        '--candidate-root "$GITHUB_WORKSPACE/candidate-source"'):
            self.assertIn(setting, self.job)
        self.assertEqual(2, self.job.count("persist-credentials: false"))
        self.assertNotRegex(self.job, r"uses: (?:\./|actions/setup-|actions/cache)")
        self.assertNotRegex(self.job, r"(?:\./gradlew|\bcargo\s|\bcmake\s|\bxcodebuild\b|\bpip\s|\bnpm\s)")
        pinned = (ROOT / "ci/runtime_release.py").read_text()
        self.assertIn("def attest_runtime_state_ci(", pinned)
        self.assertIn('selection["releaseHandoffs"]', pinned)

    def test_secret_only_reaches_reviewed_caller_with_exact_original_selection(self):
        steps = re.split(r"(?=^      - )", self.job, flags=re.MULTILINE)
        secret_steps = [step for step in steps if "secrets." in step]
        self.assertEqual(1, len(secret_steps))
        self.assertEqual(1, self.job.count("python3 -B trusted-source/ci/runtime_release.py"))
        self.assertIn("python3 -B trusted-source/ci/runtime_release.py", secret_steps[0])
        for name in ("artifact_id", "artifact_digest", "state_wave"):
            self.assertIn(f"needs.runtime-continuation.outputs.{name}", secret_steps[0])
        for argument in ("target", "expected-build-key", "artifact-id", "artifact-sha256",
                         "state-wave", "trusted-source-sha", "trusted-workflow-sha", "validation-tree"):
            self.assertIn(f"--{argument} ", secret_steps[0])
        self.assertIn("${{ matrix.buildKey }}", secret_steps[0])
        self.assertIn("artifact-ids: ${{ needs.plan.outputs.plan_id }}", self.job)
        self.assertIn('"$RUNNER_TEMP/runtime-attestation-plan/impact-plan.json"', secret_steps[0])
        self.assertIn('"$RUNNER_TEMP/runtime-release-evidence"', secret_steps[0])
        self.assertIn("path: ${{ runner.temp }}/runtime-release-evidence", self.job)
        for setting in ("overwrite: false", "if-no-files-found: error", "include-hidden-files: true"):
            self.assertIn(setting, self.job)


if __name__ == "__main__":
    unittest.main()
