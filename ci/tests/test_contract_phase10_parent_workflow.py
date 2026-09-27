"""Parent Contract Phase-10 source wiring is gated before protected jobs."""

from pathlib import Path
import os
import re
import subprocess
import tempfile
import textwrap
import unittest

from ci.products.inventory import canonical_json_bytes, sha256_bytes
from ci.tests.test_contract_attestation_workflow import workflow_job


ROOT = Path(__file__).resolve().parents[2]
PARENT = ROOT / ".github/workflows/product-validation.yml"
MAVEN = ROOT / ".github/workflows/contract-phase10-maven.yml"
RECORD = ROOT / ".github/workflows/contract-phase10-output-record.yml"


class ContractPhase10ParentWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parent = PARENT.read_text(encoding="utf-8")

    def test_immutable_children_and_authorized_contract_only(self):
        jobs = {name: workflow_job(self.parent, name) for name in (
            "contract-phase10-pgp-authority", "contract-phase10-maven",
            "contract-phase10-pins", "contract-phase10-output-record",
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
        self.assertIn("environment: product-attestation", jobs["contract-phase10-pins"])
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
        self.assertIn("phase11PinsJson: ${{ needs.contract-phase10-pins.outputs.pins_json }}", record)
        self.assertIn("phase11PinsSha256: ${{ needs.contract-phase10-pins.outputs.pins_sha256 }}", record)
        child = RECORD.read_text(encoding="utf-8")
        self.assertIn("phase10OutputArtifactId:\n        value: ${{ jobs.upload.outputs.artifact_id }}", child)
        self.assertIn("phase10OutputArtifactSha256:\n        value: ${{ jobs.upload.outputs.artifact_sha256 }}", child)
        self.assertIn("recordArtifactId:\n        value: ${{ jobs.record.outputs.artifact_id }}", child)

    def test_protected_pins_are_canonical_and_not_derived_from_child_artifact(self):
        job = workflow_job(self.parent, "contract-phase10-pins")
        self.assertIn("PROTECTED_PINS_JSON: ${{ vars.CODEX_AGENT_CONTRACT_PHASE11_PINS_JSON }}", job)
        self.assertIn("PROTECTED_PINS_SHA256: ${{ vars.CODEX_AGENT_CONTRACT_PHASE11_PINS_SHA256 }}", job)
        self.assertNotIn("needs.contract-phase10-maven.outputs.phase10OutputArtifactSha256", job)
        script = textwrap.dedent(job.split("      - name: Verify protected exact pins and forward the selection\n", 1)[1]
                                 .split("        run: |\n", 1)[1])
        with tempfile.TemporaryDirectory(prefix="ct-parent-pins-") as temporary:
            root = Path(temporary)
            trusted = root / "trusted-source"
            trusted.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=trusted, check=True)
            (trusted / "fixture").write_text("fixture\n")
            subprocess.run(["git", "add", "fixture"], cwd=trusted, check=True)
            subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                            "commit", "-qm", "pin"], cwd=trusted, check=True)
            commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=trusted, text=True).strip()
            tree = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=trusted,
                                           text=True).strip()
            pins = {name: "sha256:" + "a" * 64 for name in (
                "expected_inventory_sha256", "expected_payload_sha256",
                "expected_metadata_build_key", "expected_caller_sha256",
                "expected_keyring_sha256", "expected_keys_inventory_sha256",
                "expected_pgp_key_sha256",
            )}
            pins.update(expected_contract_version="0.8.0", expected_source_commit=commit,
                        expected_source_tree=tree, expected_validation_tree="b" * 40,
                        expected_workflow_sha=commit)
            raw = canonical_json_bytes(pins)
            environment = {
                **os.environ, "PYTHONPATH": str(ROOT), "PROTECTED_PINS_JSON": raw.decode().rstrip("\n"),
                "PROTECTED_PINS_SHA256": sha256_bytes(raw), "PROTECTED_UPLOAD_JOB": "contract-output",
                "PROTECTED_SOURCE_SHA": commit, "EXPECTED_PGP_KEY_SHA256": pins["expected_pgp_key_sha256"],
                "VALIDATION_TREE": pins["expected_validation_tree"], "CONTRACT_VERSION": "0.8.0",
                "GITHUB_OUTPUT": str(root / "out"),
            }
            for changes in ({}, {"PROTECTED_PINS_SHA256": "sha256:" + "0" * 64},
                            {"VALIDATION_TREE": "0" * 40},
                            {"PROTECTED_PINS_JSON": raw.decode().rstrip("\n") + "\n"},
                            {"PROTECTED_UPLOAD_JOB": "forged\noutput=1"}):
                output = root / "out"
                result = subprocess.run(["bash", "-e", "-c", script], cwd=root,
                                        env={**environment, **changes}, capture_output=True,
                                        text=True, timeout=10)
                self.assertEqual(0 if not changes else 1, result.returncode,
                                 (changes, result.stderr))
                if output.exists():
                    output.unlink()

    def test_normal_merge_gate_requires_both_protected_outputs(self):
        gate = workflow_job(self.parent, "merge-gate")
        for name in ("contract-phase10-pgp-authority", "contract-phase10-maven",
                     "contract-phase10-pins", "contract-phase10-output-record"):
            self.assertIn(name, gate.split("    runs-on:", 1)[0])
        self.assertIn("CONTRACT_PHASE10_REQUIRED: ${{ github.event_name != 'workflow_dispatch' && needs.contract-validation.outputs.contract_complete == 'true' }}", gate)
        for value in ("CONTRACT_PHASE10_PGP_RESULT", "CONTRACT_PHASE10_MAVEN_RESULT",
                      "CONTRACT_PHASE10_PINS_RESULT", "CONTRACT_PHASE10_RECORD_RESULT",
                      "CONTRACT_PHASE10_MAVEN_ARTIFACT_SHA256", "CONTRACT_PHASE10_RECORD_ARTIFACT_SHA256",
                      "CONTRACT_PHASE10_REUPLOAD_ARTIFACT_ID", "CONTRACT_PHASE10_REUPLOAD_ARTIFACT_SHA256"):
            self.assertIn(value, gate)
        self.assertIn('[[ "$CONTRACT_PHASE10_REUPLOAD_ARTIFACT_ID" =~ ^[1-9][0-9]*$ ]] || exit 1', gate)
        self.assertIn('[[ "$CONTRACT_PHASE10_REUPLOAD_ARTIFACT_SHA256" =~ ^sha256:[0-9a-f]{64}$ ]] || exit 1', gate)
        self.assertIn("if [ \"$CONTRACT_PHASE10_REQUIRED\" = true ]; then", gate)


if __name__ == "__main__":
    unittest.main()
