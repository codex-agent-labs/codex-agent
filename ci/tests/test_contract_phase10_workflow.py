"""Original Contract upload and later protected signing have separate jobs."""

import json
from pathlib import Path
import os
import subprocess
import tempfile
import textwrap
import unittest

from ci.products.inventory import canonical_json_bytes, sha256_bytes


ROOT = Path(__file__).resolve().parents[2]
UPLOAD = ROOT / ".github/workflows/contract-phase10-output-record.yml"
LATER = ROOT / ".github/workflows/contract-phase10-later-record.yml"


class ContractPhase10WorkflowTests(unittest.TestCase):
    def test_original_job_uploads_only_exact_product_bytes(self):
        workflow = UPLOAD.read_text(encoding="utf-8")
        self.assertIn("remote_build_authorized == 'true'", workflow)
        self.assertIn("github.event_name != 'workflow_dispatch'", workflow)
        self.assertIn("name: codex-agent-contract-phase10-maven-", workflow)
        self.assertNotIn("CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY", workflow)
        self.assertNotIn("contract_phase10_record_signer.py", workflow)
        self.assertNotIn("  record:\n", workflow)

    def test_later_gate_rejects_unapproved_or_noncanonical_control(self):
        workflow = LATER.read_text(encoding="utf-8")
        step = workflow.split("      - name: Require independently approved completed-run control before checkout\n", 1)[1]
        script = textwrap.dedent(step.split("        run: |\n", 1)[1].split(
            "      - name: Check out protected reviewed verifier and signer\n", 1,
        )[0])
        source = "a" * 40
        pgp = "sha256:" + "b" * 64
        pins = b"{}\n"
        control = {
            "schemaVersion": 1, "originalRunId": 91, "originalRunAttempt": 2,
            "validationCommit": "c" * 40, "validationTree": "d" * 40,
            "planArtifactId": 101, "planArtifactSha256": "sha256:" + "e" * 64,
            "outputArtifactId": 102, "outputArtifactSha256": "sha256:" + "f" * 64,
            "originalWorkflowSha": "1" * 40,
            "originalJobName": "product-validation / contract-phase10-output-record / contract-phase10-output",
            "trustedSourceCommit": source, "phase11PinsSha256": sha256_bytes(pins),
            "pgpKeySha256": pgp,
        }
        raw = canonical_json_bytes(control)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            environment = {
                **os.environ, "RUNNER_TEMP": str(root),
                "GITHUB_OUTPUT": str(root / "outputs"),
                "CONTROL_JSON": raw.decode().rstrip("\n"),
                "CONTROL_SHA256": sha256_bytes(raw),
                "SOURCE_SHA": source,
                "PINS_JSON": pins.decode().rstrip("\n"),
                "PINS_SHA256": sha256_bytes(pins),
                "PGP_KEY_SHA256": pgp,
            }
            cases = ({}, {"CONTROL_SHA256": "sha256:" + "0" * 64},
                     {"PINS_SHA256": "sha256:" + "0" * 64},
                     {"CONTROL_JSON": json.dumps(control)},
                     {"SOURCE_SHA": "0" * 40})
            for changed in cases:
                result = subprocess.run(["bash", "-e", "-c", script],
                                        env={**environment, **changed},
                                        capture_output=True, text=True, timeout=10)
                self.assertEqual(0 if not changed else 1, result.returncode,
                                 (changed, result.stderr))
                output = root / "outputs"
                if output.exists():
                    output.unlink()

    def test_later_record_signs_only_after_exact_original_observation(self):
        workflow = LATER.read_text(encoding="utf-8")
        self.assertIn("environment: product-attestation", workflow)
        self.assertIn('--original-run-id "$ORIGINAL_RUN_ID" --original-run-attempt "$ORIGINAL_RUN_ATTEMPT"', workflow)
        self.assertIn('--expected-phase11-pins-sha256 "$PINS_SHA256"', workflow)
        self.assertLess(workflow.index("contract_phase10_output_record.py prepare"),
                        workflow.index("contract_phase10_record_signer.py"))
        self.assertLess(workflow.index("contract_phase10_record_signer.py"),
                        workflow.index("contract_phase10_output_record.py verify-publish"))
        before, signing = workflow.split("      - name: Sign only the independently prepared record\n", 1)
        sign, after = signing.split("      - name: Reobserve original", 1)
        self.assertNotIn("CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY", before)
        self.assertIn("CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY", sign)
        self.assertNotIn("CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY", after)
        self.assertNotIn("GITHUB_TOKEN:", sign)
        for command in ("./gradlew", "cargo build", "cmake --build", "xcodebuild", "npm run"):
            self.assertNotIn(command, workflow)


if __name__ == "__main__":
    unittest.main()
