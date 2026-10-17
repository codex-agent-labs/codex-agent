"""Parent Contract Phase-10 source wiring is gated before protected jobs."""

from pathlib import Path
import re
import subprocess
import unittest
from ci.tests.test_contract_attestation_workflow import workflow_job


ROOT = Path(__file__).resolve().parents[2]
PARENT = ROOT / ".github/workflows/product-validation.yml"
MAVEN = ROOT / ".github/workflows/contract-phase10-maven.yml"
RECORD = ROOT / ".github/workflows/contract-phase10-output-record.yml"
LATER = ROOT / ".github/workflows/contract-phase10-later-record.yml"
CI = ROOT / ".github/workflows/ci.yml"


class ContractPhase10ParentWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parent = PARENT.read_text(encoding="utf-8")

    def test_immutable_children_and_authorized_contract_only(self):
        jobs = {name: workflow_job(self.parent, name) for name in (
            "contract-phase10-pgp-authority", "contract-phase10-maven",
            "contract-phase10-output-record",
        )}
        for name, job in jobs.items():
            self.assertIn("github.event_name != 'workflow_dispatch'", job, name)
            self.assertIn("needs.plan.outputs.event_authorized == 'true'", job, name)
            self.assertIn("needs.plan.outputs.remote_build_authorized == 'true'", job, name)
            self.assertIn("always() && !cancelled()", job, name)
        self.assertIn("needs.contract-validation.outputs.contract_complete == 'true'",
                      jobs["contract-phase10-pgp-authority"])
        self.assertIn("needs.contract-validation.outputs.contract_attestation_result == 'success'",
                      jobs["contract-phase10-pgp-authority"])
        self.assertIn("environment: product-attestation", jobs["contract-phase10-pgp-authority"])
        for name, child in (("contract-phase10-maven", MAVEN),
                            ("contract-phase10-output-record", RECORD)):
            match = re.search(r"uses: codex-agent-labs/codex-agent/\.github/workflows/"
                              + re.escape(child.name) + r"@([0-9a-f]{40})", jobs[name])
            self.assertIsNotNone(match, name)
            reviewed = subprocess.run(["git", "show", f"{match.group(1)}:.github/workflows/{child.name}"],
                                      cwd=ROOT, capture_output=True, text=True, check=True)
            self.assertEqual(child.read_text(encoding="utf-8"), reviewed.stdout)
        maven = jobs["contract-phase10-maven"]
        self.assertIn("contractInputsArtifactId: ${{ needs.contract-validation.outputs.contract_attestation_inputs_artifact_id }}", maven)
        self.assertIn("contractInputsArtifactSha256: ${{ needs.contract-validation.outputs.contract_attestation_inputs_artifact_sha256 }}", maven)
        self.assertIn("contractVersion: ${{ needs.contract-validation.outputs.contract_version }}", maven)
        self.assertIn("expectedPgpKeySha256: ${{ needs.contract-phase10-pgp-authority.outputs.pgp_key_sha256 }}", maven)
        record = jobs["contract-phase10-output-record"]
        self.assertIn("phase10OutputArtifactId: ${{ needs.contract-phase10-maven.outputs.phase10OutputArtifactId }}", record)
        child = RECORD.read_text(encoding="utf-8")
        self.assertIn("phase10OutputArtifactId:\n        value: ${{ jobs.upload.outputs.artifact_id }}", child)
        self.assertIn("phase10OutputArtifactSha256:\n        value: ${{ jobs.upload.outputs.artifact_sha256 }}", child)

    def test_later_record_has_independent_precheckout_control_and_token_free_signer(self):
        child = LATER.read_text(encoding="utf-8")
        self.assertIn("if: github.event_name == 'workflow_dispatch' && github.event.inputs.purpose == 'contract-phase10-record'", child)
        self.assertIn("environment: product-attestation", child)
        authority = child.index("Require independently approved completed-run control before checkout")
        checkout = child.index("Check out protected reviewed verifier and signer")
        self.assertLess(authority, checkout)
        for binding in ("CODEX_AGENT_CONTRACT_PHASE10_CONTROL_APPROVED_SHA256",
                        "CODEX_AGENT_CONTRACT_PHASE11_PINS_SHA256",
                        "CODEX_AGENT_PRODUCT_PGP_PUBLIC_KEY_SHA256"):
            self.assertIn(binding, child[:checkout])
        self.assertIn('raise ValueError("Contract control is not canonical JSON")', child[:checkout])
        self.assertIn("--original-run-id \"$ORIGINAL_RUN_ID\" --original-run-attempt \"$ORIGINAL_RUN_ATTEMPT\"", child)
        self.assertIn("--trusted-workflow-path .github/workflows/contract-phase10-output-record.yml", child)
        signer = child.split("- name: Sign only the independently prepared record", 1)[1].split(
            "- name: Reobserve original", 1)[0]
        self.assertNotIn("GITHUB_TOKEN:", signer)
        self.assertIn("CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY:", signer)
        self.assertIn("codex-agent-contract-phase10-output-record-${{ steps.authority.outputs.validationTree }}-attestation-${{ github.run_id }}-attempt-${{ github.run_attempt }}", child)

    def test_normal_merge_gate_requires_exact_original_upload_only(self):
        gate = workflow_job(self.parent, "merge-gate")
        for name in ("contract-phase10-pgp-authority", "contract-phase10-maven",
                     "contract-phase10-output-record"):
            self.assertIn(name, gate.split("    runs-on:", 1)[0])
        self.assertIn("CONTRACT_PHASE10_REQUIRED: ${{ github.event_name != 'workflow_dispatch' && needs.contract-validation.outputs.contract_complete == 'true' }}", gate)
        for value in ("CONTRACT_PHASE10_PGP_RESULT", "CONTRACT_PHASE10_MAVEN_RESULT",
                      "CONTRACT_PHASE10_RECORD_RESULT", "CONTRACT_PHASE10_MAVEN_ARTIFACT_SHA256",
                      "CONTRACT_PHASE10_REUPLOAD_ARTIFACT_ID", "CONTRACT_PHASE10_REUPLOAD_ARTIFACT_SHA256"):
            self.assertIn(value, gate)
        self.assertNotIn("CONTRACT_PHASE10_PINS_RESULT", gate)
        self.assertNotIn("CONTRACT_PHASE10_RECORD_ARTIFACT_SHA256", gate)
        self.assertIn('[[ "$CONTRACT_PHASE10_REUPLOAD_ARTIFACT_ID" =~ ^[1-9][0-9]*$ ]] || exit 1', gate)
        self.assertIn('[[ "$CONTRACT_PHASE10_REUPLOAD_ARTIFACT_SHA256" =~ ^sha256:[0-9a-f]{64}$ ]] || exit 1', gate)
        self.assertIn("if [ \"$CONTRACT_PHASE10_REQUIRED\" = true ]; then", gate)

    def test_later_dispatch_uses_pinned_child_and_requires_signed_record_upload(self):
        source = CI.read_text(encoding="utf-8")
        job = workflow_job(source, "contract-phase10-record")
        self.assertIn("github.event_name == 'workflow_dispatch' && inputs.purpose == 'contract-phase10-record'", job)
        match = re.search(r"uses: codex-agent-labs/codex-agent/\.github/workflows/"
                          r"contract-phase10-later-record\.yml@([0-9a-f]{40})", job)
        self.assertIsNotNone(match)
        reviewed = subprocess.run(["git", "show", f"{match.group(1)}:.github/workflows/{LATER.name}"],
                                  cwd=ROOT, capture_output=True, text=True, check=True)
        self.assertEqual(LATER.read_text(encoding="utf-8"), reviewed.stdout)
        gate = workflow_job(source, "merge-gate")
        self.assertIn("test \"$CONTRACT_RECORD_RESULT\" = success", gate)
        self.assertIn('[[ "$CONTRACT_RECORD_ARTIFACT_ID" =~ ^[1-9][0-9]*$ ]] || exit 1', gate)
        self.assertIn('[[ "$CONTRACT_RECORD_ARTIFACT_SHA256" =~ ^sha256:[0-9a-f]{64}$ ]] || exit 1', gate)


if __name__ == "__main__":
    unittest.main()
