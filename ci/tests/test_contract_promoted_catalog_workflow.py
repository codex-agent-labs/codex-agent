"""Source-only guards for the protected Contract catalog workflow."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest


WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/contract-promoted-catalog.yml"
PARENT = WORKFLOW.with_name("promote.yml")


class ContractPromotedCatalogWorkflowTest(unittest.TestCase):
    def test_parent_calls_catalog_only_after_non_authoritative_arm_switch(self):
        parent = PARENT.read_text()
        job = parent.split("  contract-promoted-catalog:\n", 1)[1]
        self.assertIn("github.ref == 'refs/heads/main' && github.ref_protected", job)
        self.assertIn("vars.CI_MERGE_QUEUE_ENABLED == 'true'", job)
        self.assertIn("vars.CODEX_AGENT_CONTRACT_PROMOTION_ENABLED == 'true'", job)
        self.assertNotIn("CODEX_AGENT_CONTRACT_PROMOTION_PHASE_SELECTION_SHA256", job)
        self.assertIn("needs.discover.result == 'success'", job)
        self.assertIn("uses: ./.github/workflows/contract-promoted-catalog.yml", job)

    def test_authority_rejects_missing_or_mismatched_protected_values_before_checkout(self):
        source = WORKFLOW.read_text()
        precheckout = source.split("      - name: Require independently approved S1048 Contract selection before checkout\n", 1)[1]
        script = textwrap.dedent(precheckout.split("        run: |\n", 1)[1].split(
            "      - name: Check out reviewed Contract promotion verifier only\n", 1)[0])
        selection = "{}\n"
        digest = "sha256:" + hashlib.sha256(selection.encode()).hexdigest()
        authority = {
            "SOURCE_SHA": "a" * 40, "VALIDATED_TREE": "b" * 40,
            "VALIDATION_WORKFLOW_SHA": "c" * 40, "PROMOTION_WORKFLOW_SHA": "d" * 40,
            "HANDOFF_ID": "41", "HANDOFF_SHA256": "sha256:" + "e" * 64,
            "PHASE_SELECTION_JSON": selection.rstrip("\n"),
            "PHASE_SELECTION_SHA256": digest,
            "CAPTURE_INVENTORY_SHA256": "",
        }
        with tempfile.TemporaryDirectory() as temporary:
            for change in ({}, {"SOURCE_SHA": ""}, {"HANDOFF_ID": "0"},
                           {"PHASE_SELECTION_SHA256": "sha256:" + "f" * 64},
                           {"CAPTURE_INVENTORY_SHA256": "not-a-digest"}):
                with self.subTest(change=change):
                    output = Path(temporary) / "output"
                    result = subprocess.run(["bash", "-c", script],
                        env={**os.environ, **authority, **change,
                             "RUNNER_TEMP": temporary, "GITHUB_OUTPUT": str(output)},
                        capture_output=True, text=True, timeout=10)
                    self.assertEqual(0 if not change else 1, result.returncode,
                                     (change, result.stderr))
                    if output.exists():
                        output.unlink()

    def test_capture_precedes_secret_and_source_only_workflow_has_no_build(self):
        source = WORKFLOW.read_text()
        self.assertIn("  workflow_call:\n", source)
        self.assertNotIn("  workflow_dispatch:\n", source)
        self.assertIn("environment: product-attestation", source)
        self.assertIn("CODEX_AGENT_CONTRACT_PROMOTION_PHASE_SELECTION_JSON", source)
        self.assertIn("CODEX_AGENT_CONTRACT_PROMOTION_CAPTURE_INVENTORY_SHA256", source)
        self.assertIn("CODEX_AGENT_CONTRACT_PROMOTION_HANDOFF_ARTIFACT_SHA256", source)
        capture, signing = source.split(
            "      - name: Sign only the approved external Contract catalog without an observation token\n", 1)
        self.assertIn("capture_promotable_contract_originals", capture)
        self.assertIn("contract_equal_tree_original.py", capture)
        self.assertIn("GITHUB_TOKEN: ${{ github.token }}", capture)
        self.assertNotIn("secrets.CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY", capture)
        self.assertIn("sign_promoted_contract_catalog", signing)
        self.assertIn("CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY: ${{ secrets.CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY }}", signing)
        self.assertNotIn("GITHUB_TOKEN:", signing)
        self.assertNotIn("github.token", signing)
        self.assertLess(source.index("Retain the exact original handoff and four phase uploads"),
                        source.index("Require independent approval of the retained four-upload capture"))
        self.assertLess(source.index("Require independent approval of the retained four-upload capture"),
                        source.index("Sign only the approved external Contract catalog"))
        for command in ("./gradlew", "cargo build", "cmake --build", "xcodebuild", "npm run"):
            self.assertNotIn(command, source)


if __name__ == "__main__":
    unittest.main()
