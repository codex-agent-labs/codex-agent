"""The Contract Maven producer is a protected, uninvoked exact-byte handoff."""

from pathlib import Path
import hashlib
import os
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/contract-phase10-maven.yml"
RECORD = ROOT / ".github/workflows/contract-phase10-output-record.yml"
CHILD = ROOT / ".github/workflows/contract-validation.yml"


class ContractPhase10MavenWorkflowTest(unittest.TestCase):
    def test_unsigned_original_inputs_are_exported_from_contract_child(self):
        child = CHILD.read_text(encoding="utf-8")
        self.assertIn("contract_attestation_inputs_artifact_id:\n"
                      "        value: ${{ jobs.contract-continuation.outputs.attestation_inputs_id }}", child)
        self.assertIn("contract_attestation_inputs_artifact_sha256:\n"
                      "        value: ${{ jobs.contract-continuation.outputs.attestation_inputs_digest }}", child)
        self.assertIn("contract_version:\n"
                      "        value: ${{ jobs.contract-continuation.outputs.contract_version }}", child)

    def test_missing_or_substituted_protected_authority_stops_before_checkout(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        step = workflow.split("      - name: Require protected Contract signer authority before checkout\n", 1)[1]
        script = textwrap.dedent(step.split("        run: |\n", 1)[1].split(
            "      - name: Check out reviewed Contract verifier and signer\n", 1,
        )[0])
        with tempfile.TemporaryDirectory() as temporary:
            tools = Path(temporary) / "tools"
            tools.mkdir()
            fake_gpg = tools / "gpg"
            fake_gpg.write_text("#!/bin/sh\nprintf 'pub:::::::::\\nfpr:::::::::AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA:\\n'\n")
            fake_gpg.chmod(0o700)
            public = "fixture public key bytes\n"
            public_sha = "sha256:" + hashlib.sha256(public.encode()).hexdigest()
            authority = {
                "PROTECTED_SOURCE_SHA": "a" * 40,
                "PROTECTED_PGP_KEY_SHA256": public_sha,
                "PROTECTED_PGP_KEY": public,
                "CALLER_SOURCE_SHA": "a" * 40,
                "CALLER_PGP_KEY_SHA256": public_sha,
                "CONTRACT_INPUTS_ID": "123",
                "CONTRACT_INPUTS_SHA256": "sha256:" + "c" * 64,
                "CONTRACT_VERSION": "0.8.0",
            }
            for change in ({}, {"PROTECTED_SOURCE_SHA": ""},
                           {"PROTECTED_SOURCE_SHA": "", "CALLER_SOURCE_SHA": ""},
                           {"CALLER_SOURCE_SHA": "d" * 40},
                           {"PROTECTED_PGP_KEY": ""},
                           {"PROTECTED_PGP_KEY_SHA256": "sha256:" + "d" * 64},
                           {"PROTECTED_PGP_KEY_SHA256": "", "CALLER_PGP_KEY_SHA256": ""},
                           {"CALLER_PGP_KEY_SHA256": "sha256:" + "d" * 64},
                           {"CONTRACT_INPUTS_ID": ""}, {"CONTRACT_INPUTS_SHA256": ""},
                           {"CONTRACT_VERSION": "0.8"}):
                with self.subTest(change=change):
                    output = Path(temporary) / "output"
                    result = subprocess.run(
                        ["bash", "-c", script],
                        env={**os.environ, **authority, **change,
                             "PATH": str(tools) + os.pathsep + os.environ["PATH"],
                             "RUNNER_TEMP": temporary, "GITHUB_OUTPUT": str(output)},
                        capture_output=True, text=True, timeout=10,
                    )
                    self.assertEqual(0 if not change else 1, result.returncode,
                                     (change, result.stderr))
                    if change:
                        self.assertFalse(output.exists())
                    else:
                        self.assertEqual(3, len(output.read_text().splitlines()))
                        output.unlink()

    def test_external_sidecar_tree_is_uploaded_for_the_record_carrier(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("  workflow_call:\n", workflow)
        self.assertNotIn("  workflow_dispatch:\n", workflow)
        self.assertIn("    environment: product-attestation\n", workflow)
        self.assertIn("PROTECTED_SOURCE_SHA: ${{ vars.CODEX_AGENT_PRODUCT_TRUSTED_SOURCE_SHA }}", workflow)
        self.assertIn("PROTECTED_PGP_KEY: ${{ vars.CODEX_AGENT_PRODUCT_PGP_PUBLIC_KEY }}", workflow)
        self.assertIn("PROTECTED_PGP_KEY_SHA256: ${{ vars.CODEX_AGENT_PRODUCT_PGP_PUBLIC_KEY_SHA256 }}", workflow)
        self.assertIn('test "$CALLER_SOURCE_SHA" = "$PROTECTED_SOURCE_SHA"', workflow)
        self.assertIn('test "$CALLER_PGP_KEY_SHA256" = "$PROTECTED_PGP_KEY_SHA256"', workflow)
        self.assertIn("ref: ${{ steps.authority.outputs.source_sha }}", workflow)
        self.assertIn("--artifact-id \"$CONTRACT_INPUTS_ID\"", workflow)
        self.assertIn("--artifact-sha256 \"$CONTRACT_INPUTS_SHA256\"", workflow)
        self.assertIn("--expected-pgp-key-sha256 \"$EXPECTED_PGP_KEY_SHA256\"", workflow)
        self.assertIn("--destination \"$RUNNER_TEMP/contract-phase10-maven\"", workflow)
        self.assertIn("path: ${{ runner.temp }}/contract-phase10-maven", workflow)
        producer_name = ("codex-agent-contract-phase10-maven-original-"
                         "${{ fromJSON(inputs.planOutputs).validation_tree }}-attempt-"
                         "${{ github.run_attempt }}")
        record_name = ("codex-agent-contract-phase10-maven-"
                       "${{ fromJSON(inputs.planOutputs).validation_tree }}-attempt-"
                       "${{ github.run_attempt }}")
        self.assertIn("name: " + producer_name, workflow)
        record = RECORD.read_text(encoding="utf-8")
        self.assertIn("name: " + record_name, record)
        self.assertNotIn("name: " + producer_name, record)
        self.assertNotIn("name: " + record_name, workflow)
        self.assertIn("phase10OutputArtifactId:\n        value: ${{ jobs.sidecars.outputs.artifact_id }}", workflow)
        self.assertIn("phase10OutputArtifactSha256:\n"
                      "        value: ${{ jobs.sidecars.outputs.artifact_sha256 }}", workflow)
        preflight, sign = workflow.split("      - name: Authenticate original Contract bytes", 1)
        self.assertNotIn("secrets.", preflight)
        self.assertIn("SIGNING_IN_MEMORY_KEY: ${{ secrets.SIGNING_IN_MEMORY_KEY }}", sign)
        self.assertIn("CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY:", sign)
        for command in ("./gradlew", "cargo build", "cmake --build", "xcodebuild", "npm run"):
            self.assertNotIn(command, workflow)


if __name__ == "__main__":
    unittest.main()
