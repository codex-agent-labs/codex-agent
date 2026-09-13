"""Protected tooling-attestation workflow boundary checks."""

from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/product-validation.yml"
PIN = "d3eb9635e71a2347a07a13a3874417df45c21403"


class ToolingAttestationWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = WORKFLOW.read_text(encoding="utf-8")
        cls.job = cls.source.split("\n  tooling-attestation:\n", 1)[1].split(
            "\n  contract-continuation:\n", 1,
        )[0]
        cls.merge_gate = cls.source.split("\n  merge-gate:\n", 1)[1]

    def test_job_has_the_exact_protected_missing_tooling_guard(self):
        guard = self.job.split("    if: >-\n", 1)[1].split("    needs:", 1)[0]
        for condition in (
            "always() && !cancelled()",
            "needs.plan.result == 'success'",
            "needs.workflow-lint.result == 'success'",
            "needs.plan.outputs.event_authorized == 'true'",
            "needs.plan.outputs.remote_build_authorized == 'true'",
            "needs.plan.outputs.validation_reused != 'true'",
            "github.event_name != 'workflow_dispatch'",
            "needs.plan.outputs.tooling_required == 'true'",
            "needs.plan.outputs.tooling_miss == 'true'",
        ):
            self.assertIn(condition, guard)
        self.assertNotIn("needs.product.result", guard)
        self.assertIn("needs: [workflow-lint, plan, product]", self.job)
        self.assertIn("name: tooling-attestation", self.job)
        self.assertIn("environment: product-attestation", self.job)
        self.assertIn("permissions:\n      actions: read\n      contents: read", self.job)

    def test_only_the_pinned_signer_step_receives_the_secret(self):
        checkout, after_checkout = self.job.split(
            "      - name: Import exact producer Git objects without checking out producer code\n", 1,
        )
        imported, remainder = after_checkout.split(
            "      - name: Download original plan and source inventories\n", 1,
        )
        download, signer_and_after = remainder.split(
            "      - name: Authenticate original tooling and establish detached release trust\n", 1,
        )
        signer = signer_and_after.split("      - id: identity\n", 1)[0]
        self.assertEqual(3, self.job.count(PIN))
        self.assertIn("ref: " + PIN, checkout)
        self.assertIn("path: trusted-source", checkout)
        self.assertIn("fetch-depth: 0", checkout)
        self.assertIn("persist-credentials: false", checkout)
        self.assertIn('[[ "$VALIDATION_COMMIT" =~ ^[0-9a-f]{40}$ ]]', imported)
        self.assertIn('[[ "$VALIDATION_TREE" =~ ^[0-9a-f]{40}$ ]]', imported)
        self.assertIn('git -C trusted-source fetch --no-tags origin "$VALIDATION_COMMIT"', imported)
        self.assertIn(
            'test "$(git -C trusted-source rev-parse "$VALIDATION_COMMIT^{tree}")" = "$VALIDATION_TREE"',
            imported,
        )
        self.assertIn(f'test "$(git -C trusted-source rev-parse HEAD)" = {PIN}', imported)
        for operation in ("checkout", "switch", "reset"):
            self.assertNotIn(f"git -C trusted-source {operation}", imported)
        self.assertIn("artifact-ids: ${{ needs.plan.outputs.plan_id }}", download)
        self.assertIn("path: ${{ runner.temp }}/tooling-original-plan", download)
        secret = "${{ secrets.CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY }}"
        self.assertEqual(1, self.job.count(secret))
        self.assertIn(secret, signer)
        self.assertNotIn("secrets.", checkout + imported + download)
        for argument in (
            "python3 -B trusted-source/ci/tooling_release.py",
            '--repository-root "$GITHUB_WORKSPACE/trusted-source"',
            '--plan "$RUNNER_TEMP/tooling-original-plan/impact-plan.json"',
            '--destination "$RUNNER_TEMP/tooling-release-evidence"',
            '--trusted-source-sha "$TRUSTED_SOURCE_SHA"',
            '--trusted-workflow-sha "$TRUSTED_WORKFLOW_SHA"',
            '--validation-tree "$VALIDATION_TREE"',
        ):
            self.assertIn(argument, signer)
        self.assertNotIn("./gradlew", self.job)
        self.assertNotIn(" -jar ", self.job)

    def test_upload_and_outputs_preserve_the_exact_signed_folder_and_locator(self):
        self.assertIn("artifact_id: ${{ steps.upload_tooling.outputs.artifact-id }}", self.job)
        self.assertIn("artifact_sha256: sha256:${{ steps.upload_tooling.outputs.artifact-digest }}", self.job)
        self.assertIn("transport_producer: ${{ steps.identity.outputs.transport_producer }}", self.job)
        upload = self.job.split("      - id: upload_tooling\n", 1)[1]
        self.assertIn("overwrite: false", upload)
        self.assertIn("include-hidden-files: true", upload)
        self.assertIn(
            "name: codex-agent-release-tooling-${{ needs.plan.outputs.validation_tree }}-attempt-${{ github.run_attempt }}",
            upload,
        )
        self.assertIn("path: ${{ runner.temp }}/tooling-release-evidence", upload)

    def test_merge_gate_requires_the_selected_tooling_upload_on_a_miss(self):
        self.assertIn("tooling-attestation", self.merge_gate.split("    runs-on:", 1)[0])
        for binding in (
            "TOOLING_MISS: ${{ needs.plan.outputs.tooling_miss }}",
            "TOOLING_ATTESTATION_RESULT: ${{ needs.tooling-attestation.result }}",
            "TOOLING_ARTIFACT_ID: ${{ needs.tooling-attestation.outputs.artifact_id }}",
            "TOOLING_ARTIFACT_SHA256: ${{ needs.tooling-attestation.outputs.artifact_sha256 }}",
        ):
            self.assertIn(binding, self.merge_gate)
        requirement = self.merge_gate.split('          if [ "$TOOLING_MISS" = true ]; then\n', 1)[1].split(
            "          fi\n", 1,
        )[0]
        self.assertIn('test "$TOOLING_ATTESTATION_RESULT" = success || exit 1', requirement)
        self.assertIn('[[ "$TOOLING_ARTIFACT_ID" =~ ^[1-9][0-9]*$ ]] || exit 1', requirement)
        self.assertIn(
            '[[ "$TOOLING_ARTIFACT_SHA256" =~ ^sha256:[0-9a-f]{64}$ ]] || exit 1',
            requirement,
        )

    def test_reviewed_pin_contains_the_protected_signer(self):
        result = subprocess.run(
            ["git", "show", f"{PIN}:ci/tooling_release.py"],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        for source in (
            "def attest_tooling_ci(",
            "verify_product_release_context(",
            "_verify_original(original, repository_root)",
            'environment.get("CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY")',
            "sign_manifest(fresh / ATTESTATION, private_key, signing)",
        ):
            self.assertIn(source, result.stdout)
        self.assertLess(
            result.stdout.index("_verify_original(original, repository_root)"),
            result.stdout.index('environment.get("CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY")'),
        )


if __name__ == "__main__":
    unittest.main()
