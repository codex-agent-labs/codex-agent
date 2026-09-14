"""Static workflow isolation checks; no protected or hosted execution is claimed."""

from pathlib import Path
import re
import unittest

from ci.tests.test_contract_attestation_workflow import workflow_job


ROOT = Path(__file__).resolve().parents[2]


def job_needs(job: str) -> set[str]:
    match = re.search(r"^    needs: \[(?P<value>.*)\]$", job, re.MULTILINE)
    if match is None:
        raise AssertionError("Workflow job has no fixed needs list")
    return {value.strip() for value in match.group("value").split(",")}


def job_steps(job: str) -> list[str]:
    return re.split(r"(?=^      - )", job, flags=re.MULTILINE)[1:]


class RuntimeSigningWorkflowIsolationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / ".github/workflows/product-validation.yml").read_text(encoding="utf-8")
        cls.native_prepare = workflow_job(cls.source, "runtime-signing-prepare-native")
        cls.aggregate_prepare = workflow_job(cls.source, "runtime-signing-prepare-aggregate")
        cls.native_signer = workflow_job(cls.source, "runtime-native-attestation")
        cls.aggregate_signer = workflow_job(cls.source, "runtime-aggregate-attestation")
        cls.action = (ROOT / ".github/actions/prepare-runtime-signing/action.yml").read_text(encoding="utf-8")

    def test_preparation_jobs_are_non_secret_pinned_and_gated_before_execution(self):
        cases = (
            (self.native_prepare, "runtime-signing-prepare-${{ matrix.target }}",
             "needs.runtime-continuation.result == 'success'", "${{ matrix.target }}"),
            (self.aggregate_prepare, "runtime-signing-prepare-aggregate",
             "needs.runtime-aggregate-continuation.result == 'success'", "aggregate"),
        )
        for job, name, upstream, target in cases:
            with self.subTest(name=name):
                before_runner = job.split("    runs-on:", 1)[0]
                self.assertIn(f"name: {name}", job)
                self.assertTrue({"workflow-lint", "plan", "product-tooling"}.issubset(job_needs(job)))
                for guard in ("always()", "needs.plan.outputs.event_authorized == 'true'",
                              "needs.plan.outputs.remote_build_authorized == 'true'",
                              "github.event_name != 'workflow_dispatch'", upstream,
                              "!contains(needs.*.result, 'failure')",
                              "!contains(needs.*.result, 'cancelled')"):
                    self.assertIn(guard, before_runner)
                self.assertNotIn("    environment:", job)
                self.assertNotIn("secrets.", job)
                self.assertNotIn("CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY", job)
                self.assertEqual(2, job.count("uses: actions/checkout@"))
                self.assertIn("path: trusted-source", job)
                self.assertIn("path: candidate-source", job)
                self.assertIn("ref: ${{ needs.plan.outputs.validation_commit }}", job)
                self.assertIn("fetch-depth: 0", job)
                self.assertEqual(2, job.count("persist-credentials: false"))
                pin = re.search(r"repository: codex-agent-labs/codex-agent\n\s+ref: ([0-9a-f]{40})", job)
                self.assertIsNotNone(pin)
                self.assertIn(f"source-sha: {pin.group(1)}", job)
                self.assertEqual(1, job.count("uses: ./trusted-source/.github/actions/prepare-runtime-signing"))
                self.assertIn(f"target: {target}", job)
                self.assertIn(f"name: codex-agent-runtime-signing-preparation-{target}-"
                              "${{ needs.plan.outputs.validation_tree }}-attempt-${{ github.run_attempt }}", job)
                for setting in ("overwrite: false", "if-no-files-found: error", "include-hidden-files: true"):
                    self.assertIn(setting, job)

        matrix = "${{ fromJSON(needs.runtime-continuation.outputs.native_attestation_matrix) }}"
        self.assertIn(f"matrix: {matrix}", self.native_prepare)
        self.assertIn(f"matrix: {matrix}", self.native_signer)
        self.assertIn("needs.runtime-continuation.outputs.native_attestation_matrix != '{\"include\":[]}'",
                      self.native_prepare.split("    runs-on:", 1)[0])

    def test_preparation_action_can_only_run_the_non_secret_prepare_route(self):
        self.assertNotIn("secrets.", self.action)
        self.assertNotIn("CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY", self.action)
        self.assertIn("require_no_signing_secret(os.environ)", self.action)
        self.assertIn("str(trusted / 'ci/runtime_release.py'), '--prepare-only'", self.action)
        self.assertIn("str(trusted / 'ci/tooling_capture.py')", self.action)
        self.assertLess(self.action.index("str(trusted / 'ci/tooling_capture.py')"),
                        self.action.index("str(trusted / 'ci/runtime_release.py')"))

    def test_signers_resolve_preparation_before_the_only_secret_step(self):
        cases = (
            (self.native_signer, "runtime-signing-prepare-native", "--target \"$TARGET\""),
            (self.aggregate_signer, "runtime-signing-prepare-aggregate", "--target aggregate"),
        )
        for job, prerequisite, target in cases:
            with self.subTest(prerequisite=prerequisite):
                self.assertIn(prerequisite, job_needs(job))
                self.assertIn(f"needs.{prerequisite}.result == 'success'", job.split("    runs-on:", 1)[0])
                for forbidden in ("--prepare-only", "--sdk-validation-tooling", "--release-handoff",
                                  "javaExecutable", "JAVA_HOME"):
                    self.assertNotIn(forbidden, job)
                steps = job_steps(job)
                locator_index, locator = next((index, step) for index, step in enumerate(steps)
                                              if "runtime_preparation_locator.py" in step)
                secret_steps = [(index, step) for index, step in enumerate(steps) if "secrets." in step]
                self.assertEqual(1, len(secret_steps))
                secret_index, signer = secret_steps[0]
                self.assertLess(locator_index, secret_index)
                self.assertNotIn("secrets.", locator)
                self.assertIn("python3 -B trusted-source/ci/runtime_preparation_locator.py", locator)
                self.assertIn(target, locator)
                self.assertIn("PREPARATION_ID: ${{ steps.preparation.outputs.artifact_id }}", signer)
                self.assertIn("PREPARATION_SHA256: ${{ steps.preparation.outputs.artifact_sha256 }}", signer)
                self.assertIn('--preparation-artifact-id "$PREPARATION_ID"', signer)
                self.assertIn('--preparation-artifact-sha256 "$PREPARATION_SHA256"', signer)

    def test_merge_gate_directly_waits_for_both_non_secret_preparations(self):
        needs = job_needs(workflow_job(self.source, "merge-gate"))
        self.assertIn("runtime-signing-prepare-native", needs)
        self.assertIn("runtime-signing-prepare-aggregate", needs)


if __name__ == "__main__":
    unittest.main()
