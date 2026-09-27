"""The SDK authority upload is a separate, protected no-build custody step."""

import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import textwrap
import unittest

from ci.products.inventory import canonical_json_bytes, sha256_bytes


WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/sdk-phase10-later-authority.yml"


class SdkPhase10AuthorityWorkflowTest(unittest.TestCase):
    def test_dispatch_pins_authority_child_and_requires_exact_upload(self):
        caller = WORKFLOW.with_name("ci.yml").read_text(encoding="utf-8")
        child = caller.split("  sdk-phase10-authority:\n", 1)[1].split("\n  merge-gate:", 1)[0]
        self.assertIn("inputs.purpose == 'sdk-phase10-authority'", child)
        match = re.search(r"sdk-phase10-later-authority\.yml@([0-9a-f]{40})", child)
        self.assertIsNotNone(match)
        committed = subprocess.check_output(
            ["git", "show", f"{match.group(1)}:.github/workflows/sdk-phase10-later-authority.yml"],
            cwd=WORKFLOW.parents[2], text=True)
        self.assertEqual(WORKFLOW.read_text(encoding="utf-8"), committed)
        gate = caller.split("  merge-gate:\n", 1)[1]
        script = textwrap.dedent(gate.split("        run: |\n", 1)[1])
        environment = {**os.environ, "EVENT": "workflow_dispatch", "PURPOSE": "sdk-phase10-authority",
            "PRODUCT_VALIDATION_RESULT": "skipped", "SDK_CUSTODY_RESULT": "skipped",
            "RUNTIME_RECORD_RESULT": "skipped", "CONTRACT_RECORD_RESULT": "skipped",
            "SDK_AUTHORITY_RESULT": "success", "SDK_AUTHORITY_ARTIFACT_ID": "123",
            "SDK_AUTHORITY_ARTIFACT_SHA256": "sha256:" + "a" * 64}
        for changed in ({}, {"SDK_AUTHORITY_RESULT": "failure"},
                        {"SDK_AUTHORITY_ARTIFACT_ID": ""},
                        {"SDK_AUTHORITY_ARTIFACT_SHA256": "sha256:bad"},
                        {"PRODUCT_VALIDATION_RESULT": "success"}):
            result = subprocess.run(["bash", "-e", "-c", script],
                env={**environment, **changed}, capture_output=True, text=True, timeout=10)
            self.assertEqual(0 if not changed else 1, result.returncode,
                             (changed, result.stderr))

    def test_protected_authority_digest_is_checked_before_checkout(self):
        source = WORKFLOW.read_text(encoding="utf-8")
        before, after = source.split("      - name: Check out protected reviewed authority verifier\n", 1)
        self.assertIn("github.event.inputs.purpose == 'sdk-phase10-authority'", before)
        self.assertIn("environment: product-attestation", before)
        self.assertIn("CODEX_AGENT_SDK_AUTHORITY_APPROVED_SHA256", before)
        self.assertIn("CODEX_AGENT_SDK_ORIGINAL_PRODUCER_APPROVED_SHA256", before)
        self.assertIn("sdk_campaign_authority_producer.py", after)
        self.assertNotIn("CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY", source)
        self.assertNotIn("GITHUB_TOKEN:", source)
        for command in ("./gradlew", "cargo build", "cmake --build", "xcodebuild"):
            self.assertNotIn(command, source)
        script = textwrap.dedent(before.split("        run: |\n", 1)[1])
        authority = canonical_json_bytes({"schemaVersion": 1, "completedCatalogPin": {}})
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            environment = {**os.environ, "RUNNER_TEMP": str(root),
                "GITHUB_OUTPUT": str(root / "outputs"), "SOURCE_SHA": "a" * 40,
                "AUTHORITY_JSON": authority.decode().rstrip("\n"),
                "AUTHORITY_SHA256": sha256_bytes(authority),
                "ORIGINAL_PRODUCER_SHA256": "sha256:" + "b" * 64}
            for changed in ({}, {"AUTHORITY_SHA256": "sha256:" + "0" * 64},
                            {"AUTHORITY_JSON": json.dumps({"completedCatalogPin": {}, "schemaVersion": 1})},
                            {"SOURCE_SHA": "bad"}):
                result = subprocess.run(["bash", "-e", "-c", script],
                    env={**environment, **changed}, capture_output=True, text=True, timeout=10)
                self.assertEqual(0 if not changed else 1, result.returncode,
                                 (changed, result.stderr))
                output = root / "outputs"
                if output.exists():
                    output.unlink()


if __name__ == "__main__":
    unittest.main()
