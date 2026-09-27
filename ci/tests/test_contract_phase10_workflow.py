"""The protected Contract record carrier never signs or rebuilds payload bytes."""

from pathlib import Path
import os
import subprocess
import tempfile
import textwrap
import unittest


WORKFLOW = (Path(__file__).resolve().parents[2] /
            ".github/workflows/contract-phase10-output-record.yml")


class ContractPhase10WorkflowTests(unittest.TestCase):
    def test_protected_pin_gate_rejects_missing_or_substituted_authority(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        step = workflow.split("      - name: Require protected reviewed source before checkout\n", 1)[1]
        script = textwrap.dedent(step.split("        run: |\n", 1)[1].split(
            "      - name: Check out reviewed verifier and signer\n", 1,
        )[0])
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "gate-output"
            authority = {
                "PROTECTED_SOURCE_SHA": "a" * 40,
                "PROTECTED_PINS_SHA256": "sha256:" + "b" * 64,
                "PROTECTED_PGP_KEY_SHA256": "sha256:" + "c" * 64,
                "PROTECTED_UPLOAD_JOB": "product-validation / contract-phase10-output",
            }
            callers = {
                "CALLER_SOURCE_SHA": authority["PROTECTED_SOURCE_SHA"],
                "CALLER_PINS_SHA256": authority["PROTECTED_PINS_SHA256"],
                "CALLER_PGP_KEY_SHA256": authority["PROTECTED_PGP_KEY_SHA256"],
                "CALLER_UPLOAD_JOB": authority["PROTECTED_UPLOAD_JOB"],
            }
            for changed in (None, *authority, *callers):
                environment = {**os.environ, **authority, **callers,
                               "GITHUB_OUTPUT": str(output)}
                if changed:
                    environment[changed] = ""
                result = subprocess.run(["bash", "-c", script], env=environment,
                                        capture_output=True, text=True, timeout=10)
                self.assertEqual(0 if changed is None else 1, result.returncode,
                                 (changed, result.stderr))
                if changed:
                    self.assertFalse(output.exists())
                else:
                    self.assertEqual(4, len(output.read_text().splitlines()))
                    output.unlink()

    def test_official_upload_precedes_protected_record(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("  workflow_call:\n", workflow)
        self.assertNotIn("  workflow_dispatch:\n", workflow)
        self.assertIn("remote_build_authorized == 'true'", workflow)
        self.assertIn("    needs: [upload]\n", workflow)
        self.assertIn("    environment: product-attestation\n", workflow)
        self.assertIn("PROTECTED_SOURCE_SHA: ${{ vars.CODEX_AGENT_PRODUCT_TRUSTED_SOURCE_SHA }}", workflow)
        self.assertIn("PROTECTED_PINS_SHA256: ${{ vars.CODEX_AGENT_CONTRACT_PHASE11_PINS_SHA256 }}", workflow)
        self.assertIn("PROTECTED_PGP_KEY_SHA256: ${{ vars.CODEX_AGENT_PRODUCT_PGP_PUBLIC_KEY_SHA256 }}", workflow)
        self.assertIn("PROTECTED_UPLOAD_JOB: ${{ vars.CODEX_AGENT_CONTRACT_PHASE10_UPLOAD_JOB }}", workflow)
        self.assertIn('test "$CALLER_SOURCE_SHA" = "$PROTECTED_SOURCE_SHA"', workflow)
        self.assertIn('test "$CALLER_PINS_SHA256" = "$PROTECTED_PINS_SHA256"', workflow)
        self.assertIn('test "$CALLER_PGP_KEY_SHA256" = "$PROTECTED_PGP_KEY_SHA256"', workflow)
        self.assertIn('test "$CALLER_UPLOAD_JOB" = "$PROTECTED_UPLOAD_JOB"', workflow)
        self.assertIn("ref: ${{ steps.authority.outputs.source_sha }}", workflow)
        self.assertEqual(workflow.count("TRUSTED_SOURCE_SHA: ${{ steps.authority.outputs.source_sha }}"), 3)
        self.assertEqual(workflow.count("TRUSTED_UPLOAD_JOB: ${{ steps.authority.outputs.upload_job }}"), 2)
        self.assertNotIn("TRUSTED_SOURCE_SHA: ${{ inputs.trustedWorkflowSha }}", workflow)
        self.assertNotIn("TRUSTED_UPLOAD_JOB: ${{ inputs.trustedUploadJobName }}", workflow)
        self.assertIn("PHASE11_PINS_SHA256: ${{ steps.authority.outputs.pins_sha256 }}", workflow)
        self.assertEqual(workflow.count("EXPECTED_PGP_KEY_SHA256: ${{ steps.authority.outputs.pgp_key_sha256 }}"), 2)
        self.assertNotIn("EXPECTED_PGP_KEY_SHA256: ${{ inputs.expectedPgpKeySha256 }}", workflow)
        self.assertLess(workflow.index("name: Require protected reviewed source before checkout"),
                        workflow.index("name: Check out reviewed verifier and signer"))
        self.assertIn("--trusted-job-name \"$TRUSTED_UPLOAD_JOB\"", workflow)
        self.assertIn("--expected-phase11-pins-sha256 \"$PHASE11_PINS_SHA256\"", workflow)
        self.assertIn("--expected-pgp-key-sha256 \"$EXPECTED_PGP_KEY_SHA256\"", workflow)
        self.assertIn("--artifact-sha256 \"$OUTPUT_ARTIFACT_SHA256\"", workflow)
        self.assertEqual(workflow.count("uses: actions/download-artifact@"), 3)
        self.assertEqual(workflow.count("          merge-multiple: true\n"), 3)
        for source, destination in (
            ("inputs.phase10OutputArtifactId", "phase10-output"),
            ("fromJSON(inputs.planOutputs).plan_id", "plan"),
            ("needs.upload.outputs.artifact_id", "phase10-output"),
        ):
            self.assertIn(
                f"artifact-ids: ${{{{ {source} }}}}\n"
                f"          merge-multiple: true\n"
                f"          path: {destination}\n", workflow,
            )
        self.assertLess(workflow.index("name: contract-phase10-output"),
                        workflow.index("name: contract-phase10-record"))
        self.assertLess(workflow.index("contract_phase10_output_record.py prepare"),
                        workflow.index("contract_phase10_record_signer.py"))
        self.assertLess(workflow.index("contract_phase10_record_signer.py"),
                        workflow.index("contract_phase10_output_record.py verify-publish"))
        self.assertLess(workflow.index("contract_phase10_output_record.py verify-publish"),
                        workflow.index("name: Preserve the exact verified record and signature"))

    def test_private_key_is_step_scoped_and_no_product_build_runs(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        prepare, rest = workflow.split("      - name: Sign only the independently prepared record\n")
        sign, after_sign = rest.split("      - name: Re-observe official upload", 1)
        self.assertNotIn("CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY", prepare)
        self.assertIn("CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY", sign)
        self.assertNotIn("CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY", after_sign)
        for command in ("./gradlew", "cargo build", "cmake --build", "xcodebuild", "npm run"):
            self.assertNotIn(command, workflow)


if __name__ == "__main__":
    unittest.main()
