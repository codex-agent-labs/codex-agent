"""Build-free Runtime candidate entry point; no hosted acceptance claim."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest


WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/runtime-candidate.yml"


class RuntimeCandidateWorkflowTest(unittest.TestCase):
    def test_protected_authority_binds_tag_source_controls_and_public_key(self):
        source = WORKFLOW.read_text()
        step = source.split("        run: |\n", 1)[1]
        script = textwrap.dedent(step.split("      - name: Check out the exact landed tag\n", 1)[0])
        digest = lambda raw: "sha256:" + hashlib.sha256(raw.encode()).hexdigest()
        selection = json.dumps({"schemaVersion": 2, "phase10": {
            "originalProducer": {"commit": "b" * 40}}})
        key = "public-key\n"
        pins = json.dumps({"phase11Pins": {"expected_runtime_version": "0.8.0",
            "expected_source_commit": "a" * 40, "expected_pgp_key_sha256": digest(key)}})
        with tempfile.TemporaryDirectory() as temporary:
            base = {**os.environ, "GITHUB_REF_TYPE": "tag", "GITHUB_REF_PROTECTED": "true",
                "GITHUB_REF_NAME": "candidate/runtime/v0.8.0-rc.1", "SELECTION_JSON": selection,
                "SELECTION_SHA256": digest(selection), "PINS_JSON": pins, "PINS_SHA256": digest(pins),
                "PGP_PUBLIC_KEY": key, "RUNNER_TEMP": temporary,
                "GITHUB_OUTPUT": str(Path(temporary) / "output")}
            for change in ({}, {"GITHUB_REF_PROTECTED": "false"}, {"GITHUB_REF_TYPE": "branch"},
                {"GITHUB_REF_NAME": "candidate/sdk/v0.8.0-rc.1"},
                {"GITHUB_REF_NAME": "candidate/runtime/v0.8.1-rc.1"},
                {"SELECTION_SHA256": "sha256:" + "c" * 64},
                {"PINS_SHA256": "sha256:" + "c" * 64}, {"PGP_PUBLIC_KEY": "different key\n"},
                {"SELECTION_JSON": selection.replace('"schemaVersion": 2', '"schemaVersion": 1'),
                 "SELECTION_SHA256": digest(selection.replace('"schemaVersion": 2', '"schemaVersion": 1'))}):
                with self.subTest(change=change):
                    result = subprocess.run(["bash", "-c", script], env={**base, **change},
                                            capture_output=True, text=True, timeout=10)
                    self.assertEqual(0 if not change else 1, result.returncode, result.stderr)

    def test_capture_token_is_absent_from_offline_join_and_no_build_or_signing(self):
        source = WORKFLOW.read_text()
        self.assertIn("environment: release-candidate", source)
        self.assertIn("vars.CODEX_AGENT_PRODUCT_PGP_PUBLIC_KEY", source)
        self.assertIn("git -C landed-source merge-base --is-ancestor", source)
        self.assertIn("--expected-pins-sha256", source)
        self.assertIn("--landed-repository landed-source", source)
        self.assertEqual(1, source.count("GITHUB_TOKEN: ${{ github.token }}"))
        offline = source.split("      - name: Verify offline", 1)[1]
        self.assertNotIn("TOKEN", offline)
        for forbidden in ("secrets.", "./gradlew", "cargo build", "cmake --build", "xcodebuild",
                          "gpg --sign", "ssh-keygen -Y sign", "runtime_phase10_upload_locator.py",
                          "runtime_phase10_sidecar_upload.py", "actions/download-artifact"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
