"""The Runtime record carrier authenticates a completed run without rebuilding it."""

from pathlib import Path
import unittest


WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/runtime-phase10-output-record.yml"


class RuntimePhase10OutputRecordWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = WORKFLOW.read_text(encoding="utf-8")

    def section(self, name, next_name):
        return self.source.split(f"      - name: {name}\n", 1)[1].split(
            f"      - name: {next_name}\n", 1,
        )[0]

    def test_approved_completed_run_control_precedes_any_checkout(self):
        authority = self.section(
            "Require independently approved completed-run control before checkout",
            "Check out protected reviewed verifier and signer",
        )
        self.assertIn("environment: product-attestation", self.source)
        self.assertIn("github.event_name == 'workflow_dispatch'", self.source)
        self.assertIn("github.event.inputs.purpose == 'runtime-phase10-record'", self.source)
        self.assertIn("CODEX_AGENT_RUNTIME_PHASE10_CONTROL_APPROVED_SHA256", authority)
        self.assertIn('= "$CONTROL_SHA256"', authority)
        self.assertIn('= "$PINS_SHA256"', authority)
        self.assertIn('test "$(jq -er \'.trustedSourceCommit\' ', authority)
        self.assertIn('test "$(jq -er \'.pgpKeySha256\' ', authority)
        self.assertNotIn("GITHUB_TOKEN:", authority)
        self.assertNotIn("CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY", authority)

    def test_original_capture_uses_approved_run_not_attestation_run(self):
        source = self.source
        self.assertIn("run-id: ${{ steps.authority.outputs.originalRunId }}", source)
        self.assertIn("artifact-ids: ${{ steps.authority.outputs.planArtifactId }}", source)
        for name, next_name in (
            ("Capture official original aggregate without signing keys",
             "Capture official original sidecars without signing keys"),
            ("Capture official original sidecars without signing keys",
             "Prepare unsigned record from approved exact bytes"),
        ):
            capture = self.section(name, next_name)
            self.assertIn('GITHUB_TOKEN: ${{ github.token }}', capture)
            self.assertIn('--original-run-id "$ORIGINAL_RUN_ID"', capture)
            self.assertIn('--original-run-attempt "$ORIGINAL_RUN_ATTEMPT"', capture)
            self.assertNotIn("CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY", capture)
        self.assertIn('--plan-artifact-sha256 "$PLAN_SHA256"', source)
        self.assertIn('--trusted-workflow-sha "$SIDECAR_WORKFLOW_SHA"', source)
        self.assertIn('--trusted-workflow-sha "$AGGREGATE_WORKFLOW_SHA"', source)

    def test_signing_is_token_free_and_record_has_external_transport(self):
        prepare = self.section(
            "Prepare unsigned record from approved exact bytes",
            "Sign only the prepared record without observation token",
        )
        signing = self.section(
            "Sign only the prepared record without observation token",
            "Reobserve original and publish only the verified signed pair",
        )
        verification = self.section(
            "Reobserve original and publish only the verified signed pair",
            "Preserve exact original sidecar transport externally",
        )
        self.assertIn('--phase11-pins "$RUNNER_TEMP/runtime-phase11-pins.json"', prepare)
        self.assertIn('--maven-sidecars "$RUNNER_TEMP/runtime-sidecar-capture/original"', prepare)
        self.assertNotIn("CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY", prepare)
        self.assertIn("CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY: ${{ secrets.CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY }}", signing)
        self.assertNotIn("GITHUB_TOKEN:", signing)
        self.assertIn("GITHUB_TOKEN: ${{ github.token }}", verification)
        self.assertNotIn("CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY", verification)
        self.assertIn("path: ${{ runner.temp }}/runtime-sidecar-capture", self.source)
        self.assertIn("path: ${{ runner.temp }}/runtime-verified-record", self.source)


if __name__ == "__main__":
    unittest.main()
