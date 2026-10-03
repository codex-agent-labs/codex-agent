"""The protected Runtime sidecar child keeps observation and signing separate."""

from pathlib import Path
import re
import subprocess
import unittest


WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/runtime-phase10-maven.yml"
PARENT = WORKFLOW.with_name("product-validation.yml")


class RuntimePhase10MavenWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = WORKFLOW.read_text(encoding="utf-8")

    def test_protected_source_and_public_pgp_key_precede_checkout(self):
        source = self.source
        self.assertIn("environment: product-attestation", source)
        self.assertIn("github.event_name != 'workflow_dispatch'", source)
        self.assertLess(source.index("Require protected source and public PGP authority"),
                        source.index("Check out reviewed Runtime verifier and signer"))
        self.assertIn("test \"$CALLER_SOURCE_SHA\" = \"$PROTECTED_SOURCE_SHA\"", source)
        self.assertIn("test \"$CALLER_PGP_KEY_SHA256\" = \"$PROTECTED_PGP_KEY_SHA256\"", source)
        self.assertIn("--expected-pgp-key-sha256 \"$EXPECTED_PGP_KEY_SHA256\"", source)

    def test_official_capture_is_pinned_before_token_free_pgp_signing(self):
        source = self.source
        capture = source.split("      - name: Capture the official aggregate upload without signing keys\n", 1)[1]
        capture = capture.split("      - name: Sign only the captured original Maven primaries externally\n", 1)[0]
        signing = source.split("      - name: Sign only the captured original Maven primaries externally\n", 1)[1]
        signing = signing.split("      - name: Preserve exact external Runtime Maven sidecars\n", 1)[0]
        self.assertIn("GITHUB_TOKEN: ${{ github.token }}", capture)
        self.assertNotIn("SIGNING_IN_MEMORY_KEY", capture)
        self.assertIn("--destination \"$RUNNER_TEMP/runtime-phase10-capture\"", capture)
        self.assertIn("test \"$(sed -n 's/^artifact_id=//p' \"$GITHUB_OUTPUT\")\" = \"$EXPECTED_ARTIFACT_ID\"", capture)
        self.assertIn("test \"$(sed -n 's/^artifact_sha256=//p' \"$GITHUB_OUTPUT\")\" = \"$EXPECTED_ARTIFACT_SHA256\"", capture)
        self.assertIn("SIGNING_IN_MEMORY_KEY: ${{ secrets.SIGNING_IN_MEMORY_KEY }}", signing)
        self.assertNotIn("GITHUB_TOKEN:", signing)
        self.assertIn("--protected-output \"$RUNNER_TEMP/runtime-phase10-capture/original\"", signing)
        self.assertIn("--keyring trusted-source/gradle/release/product-signing-keys.json", signing)
        self.assertIn("sidecarArtifactSha256:\n        value: ${{ jobs.sidecars.outputs.artifact_sha256 }}", source)

    def test_parent_pins_reviewed_child_and_gates_its_exact_upload(self):
        parent = PARENT.read_text(encoding="utf-8")
        job = parent.split("  runtime-phase10-maven:\n", 1)[1].split("\n  sdk-inputs:", 1)[0]
        match = re.search(r"uses: codex-agent-labs/codex-agent/\.github/workflows/"
                          r"runtime-phase10-maven\.yml@([0-9a-f]{40})", job)
        self.assertIsNotNone(match)
        pinned = subprocess.check_output(["git", "show",
            f"{match.group(1)}:.github/workflows/runtime-phase10-maven.yml"],
            cwd=WORKFLOW.parents[2], text=True)
        self.assertEqual(self.source, pinned)
        self.assertIn("aggregateArtifactId: ${{ needs.runtime-aggregate-attestation.outputs.artifact_id }}", job)
        self.assertIn("aggregateArtifactSha256: ${{ needs.runtime-aggregate-attestation.outputs.artifact_digest }}", job)
        self.assertIn("expectedPgpKeySha256: ${{ needs.contract-phase10-pgp-authority.outputs.pgp_key_sha256 }}", job)
        gate = parent.split("  merge-gate:\n", 1)[1]
        self.assertIn("runtime-phase10-maven, sdk-inputs", gate.split("    runs-on:", 1)[0])
        self.assertIn('test "$RUNTIME_PHASE10_MAVEN_RESULT" = success || exit 1', gate)
        self.assertIn('[[ "$RUNTIME_PHASE10_MAVEN_ARTIFACT_ID" =~ ^[1-9][0-9]*$ ]] || exit 1', gate)
        self.assertIn('[[ "$RUNTIME_PHASE10_MAVEN_ARTIFACT_SHA256" =~ ^sha256:[0-9a-f]{64}$ ]] || exit 1', gate)


if __name__ == "__main__":
    unittest.main()
