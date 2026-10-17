"""Fail-closed, build-free Contract candidate workflow guards."""

from pathlib import Path
import hashlib
import os
import subprocess
import tempfile
import textwrap
import unittest


WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/contract-candidate.yml"


class ContractCandidateWorkflowTest(unittest.TestCase):
    def test_authority_requires_protected_tag_and_independent_selection_digest(self):
        source = WORKFLOW.read_text()
        step = source.split("      - name: Require protected tag and independently approved S1048 selection\n", 1)[1]
        script = textwrap.dedent(step.split("        run: |\n", 1)[1].split(
            "      - name: Check out the exact landed tag\n", 1)[0])
        selection = '{"phase10":{"phase11Pins":{"expected_contract_version":"0.8.0"},"trustedSourceCommit":"' + "a" * 40 + '","originalProducer":{"commit":"' + "b" * 40 + '"}}}'
        digest = "sha256:" + hashlib.sha256(selection.encode()).hexdigest()
        with tempfile.TemporaryDirectory() as temporary:
            base = {**os.environ, "GITHUB_REF_TYPE": "tag",
                    "GITHUB_REF_PROTECTED": "true",
                    "GITHUB_REF_NAME": "candidate/contract/v0.8.0-rc.1",
                    "SELECTION_JSON": selection, "SELECTION_SHA256": digest,
                    "RUNNER_TEMP": temporary, "GITHUB_OUTPUT": str(Path(temporary) / "output")}
            for change in ({}, {"GITHUB_REF_PROTECTED": "false"},
                           {"GITHUB_REF_NAME": "candidate/runtime/v0.8.0-rc.1"},
                           {"SELECTION_SHA256": "sha256:" + "c" * 64},
                           {"SELECTION_JSON": selection.replace("0.8.0", "0.8.1")}):
                with self.subTest(change=change):
                    result = subprocess.run(["bash", "-c", script], env={**base, **change},
                                            capture_output=True, text=True, timeout=10)
                    self.assertEqual(0 if not change else 1, result.returncode, result.stderr)

    def test_workflow_only_authenticates_and_forwards(self):
        source = WORKFLOW.read_text()
        self.assertIn("environment: release-candidate", source)
        self.assertIn("candidate/contract/v*-rc.*", source)
        self.assertIn("--expected-selection-sha256", source)
        self.assertIn("--landed-repository landed-source", source)
        self.assertIn("git -C landed-source merge-base --is-ancestor", source)
        self.assertEqual(1, source.count("GITHUB_TOKEN: ${{ github.token }}"))
        for forbidden in ("secrets.", "./gradlew", "cargo build", "cmake --build",
                          "xcodebuild", "gpg --sign", "ssh-keygen -Y sign"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
