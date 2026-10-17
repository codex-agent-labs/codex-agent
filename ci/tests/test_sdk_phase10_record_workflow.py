"""The later SDK record signs only independently approved, replayed bytes."""

from pathlib import Path
import json
import os
import re
import subprocess
import tempfile
import textwrap
import unittest

from ci.products.inventory import sha256_bytes


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/sdk-phase10-later-record.yml"


class SdkPhase10RecordWorkflowTest(unittest.TestCase):
    def test_precheckout_rejects_untrusted_ref_and_output_injection(self):
        source = WORKFLOW.read_text(encoding="utf-8")
        approval = source.split("      - name: Require independently approved SDK control and index before checkout\n", 1)[1].split(
            "      - name: Check out reviewed verifier and signer\n", 1)[0]
        script = textwrap.dedent(approval.split("        run: |\n", 1)[1])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for commit, accepted in (("b" * 40, True),
                                     ("refs/heads/main", False),
                                     ("b" * 40 + "\nforged=yes", False)):
                control = {"trustedSourceCommit": "a" * 40,
                           "originalProducer": {"commit": commit, "tree": "c" * 40,
                                                "runId": 123}, "planArtifactId": 456}
                raw = (json.dumps(control, sort_keys=True, separators=(",", ":")) + "\n").encode()
                output = root / "output"
                result = subprocess.run(["bash", "-e", "-c", script],
                    env={**os.environ, "RUNNER_TEMP": str(root), "GITHUB_OUTPUT": str(output),
                         "SOURCE_SHA": "a" * 40, "CONTROL_JSON": raw.decode().rstrip("\n"),
                         "CONTROL_SHA256": sha256_bytes(raw),
                         "INDEX_SHA256": "sha256:" + "d" * 64},
                    capture_output=True, text=True, timeout=10)
                self.assertEqual(0 if accepted else 1, result.returncode,
                                 (commit, result.stderr))
                if output.exists():
                    self.assertNotIn("forged=yes", output.read_text())
                    output.unlink()

    def test_dispatch_pins_child_and_isolates_merge_gate(self):
        caller = WORKFLOW.with_name("ci.yml").read_text(encoding="utf-8")
        child = caller.split("  sdk-phase10-record:\n", 1)[1].split("\n  merge-gate:", 1)[0]
        self.assertIn("inputs.purpose == 'sdk-phase10-record'", child)
        match = re.search(r"sdk-phase10-later-record\.yml@([0-9a-f]{40})", child)
        self.assertIsNotNone(match)
        committed = subprocess.check_output(["git", "show", f"{match.group(1)}:.github/workflows/sdk-phase10-later-record.yml"], cwd=ROOT, text=True)
        self.assertEqual(WORKFLOW.read_text(encoding="utf-8"), committed)
        gate = caller.split("  merge-gate:\n", 1)[1]
        script = textwrap.dedent(gate.split("        run: |\n", 1)[1])
        environment = {**os.environ, "EVENT": "workflow_dispatch", "PURPOSE": "sdk-phase10-record",
            "DIAGNOSTICS_RESULT": "skipped",
            "PRODUCT_VALIDATION_RESULT": "skipped", "SDK_CUSTODY_RESULT": "skipped",
            "TOOLCHAIN_CAPTURE_RESULT": "skipped", "RUNTIME_RECORD_RESULT": "skipped", "CONTRACT_RECORD_RESULT": "skipped",
            "SDK_AUTHORITY_RESULT": "skipped", "SDK_RECORD_RESULT": "success",
            "SDK_MAVEN_RESULT": "skipped",
            "SDK_RECORD_ARTIFACT_ID": "123", "SDK_RECORD_ARTIFACT_SHA256": "sha256:" + "a" * 64}
        for changed in ({}, {"SDK_RECORD_RESULT": "failure"},
                        {"SDK_RECORD_ARTIFACT_ID": ""},
                        {"SDK_RECORD_ARTIFACT_SHA256": "sha256:bad"},
                        {"PRODUCT_VALIDATION_RESULT": "success"}):
            result = subprocess.run(["bash", "-e", "-c", script],
                env={**environment, **changed}, capture_output=True, text=True, timeout=10)
            self.assertEqual(0 if not changed else 1, result.returncode,
                             (changed, result.stderr))

    def test_protected_replay_precedes_token_free_signing(self):
        source = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("environment: product-attestation", source)
        self.assertIn("CODEX_AGENT_SDK_PHASE10_CONTROL_APPROVED_SHA256", source)
        self.assertIn("CODEX_AGENT_SDK_INDEX_APPROVED_SHA256", source)
        self.assertIn("sdk_phase10_protected_inputs.py stage", source)
        self.assertIn("sdk_phase10_original_plan.py", source)
        self.assertIn("sdk_campaign_release_issuer.py prepare", source)
        self.assertIn("sdk_campaign_release_issuer.py sign", source)
        self.assertIn("--repository-root \"$PWD/original-source\"", source)
        self.assertLess(source.index("sdk_phase10_protected_inputs.py stage"),
                        source.index("sdk_phase10_original_plan.py"))
        self.assertLess(source.index("sdk_phase10_original_plan.py"),
                        source.index("sdk_campaign_release_issuer.py prepare"))
        self.assertLess(source.index("sdk_campaign_release_issuer.py prepare"),
                        source.index("sdk_campaign_release_issuer.py sign"))
        signer = source.split("      - name: Sign only the preapproved index", 1)[1].split(
            "      - name: Upload exact signed pair", 1)[0]
        self.assertNotIn("GITHUB_TOKEN:", signer)
        self.assertNotIn("GH_TOKEN:", signer)
        self.assertIn("CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY", signer)
        self.assertNotIn("CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY", source.split(
            "      - name: Sign only the preapproved index", 1)[0])

    def test_upload_is_signed_pair_only(self):
        source = WORKFLOW.read_text(encoding="utf-8")
        upload = source.split("      - name: Upload exact signed pair", 1)[1]
        self.assertIn("path: ${{ runner.temp }}/sdk-signed-index", upload)
        self.assertIn("overwrite: false", upload)
        admission = (ROOT / "ci/sdk_phase10_release_index_admission.py").read_text(encoding="utf-8")
        self.assertIn('_WORKFLOW = ".github/workflows/sdk-phase10-later-record.yml"', admission)
        self.assertIn('_JOB = "sdk-phase10-record / sdk-phase10-record"', admission)
        self.assertIn("name: sdk-phase10-record", source)
        self.assertIn("name: codex-agent-sdk-phase10-release-index-${{ steps.approval.outputs.original_tree }}-attestation-${{ github.run_id }}-attempt-${{ github.run_attempt }}", upload)
        self.assertIn('f"codex-agent-sdk-phase10-release-index-{original[\'tree\']}"', admission)
        self.assertNotIn("gradlew", source)
        self.assertNotIn("cargo build", source)


if __name__ == "__main__":
    unittest.main()
