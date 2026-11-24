"""The protected Runtime sidecar child keeps observation and signing separate."""

from pathlib import Path
import subprocess
import unittest
from ci.tests.test_reviewed_workflow_publication import publication


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
        self.assertIn(f"    uses: {publication.PROJECT}.github/workflows/"
                      f"{WORKFLOW.name}@{publication.PROTECTED_REF}\n", job)
        root = WORKFLOW.parents[2]
        revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        reviewed = publication.reviewed_workflow_closure(root, revision)
        self.assertEqual(self.source.encode("utf-8"), reviewed[f".github/workflows/{WORKFLOW.name}"])
        self.assertEqual(PARENT.read_bytes(), reviewed[publication.ENTRYPOINT])
        self.assertIn("trustedWorkflowSha: ${{ needs.plan.outputs.publisher_sha }}", job)
        self.assertIn("trustedSourceSha: ${{ needs.plan.outputs.source_sha }}", job)
        self.assertIn("aggregateArtifactId: ${{ needs.runtime-aggregate-attestation.outputs.artifact_id }}", job)
        self.assertIn("aggregateArtifactSha256: ${{ needs.runtime-aggregate-attestation.outputs.artifact_digest }}", job)
        self.assertIn("expectedPgpKeySha256: ${{ needs.contract-phase10-pgp-authority.outputs.pgp_key_sha256 }}", job)
        gate = parent.split("  merge-gate:\n", 1)[1]
        self.assertIn("runtime-phase10-maven, sdk-inputs", gate.split("    runs-on:", 1)[0])
        self.assertIn('test "$RUNTIME_PHASE10_MAVEN_RESULT" = success || exit 1', gate)
        self.assertIn('[[ "$RUNTIME_PHASE10_MAVEN_ARTIFACT_ID" =~ ^[1-9][0-9]*$ ]] || exit 1', gate)
        self.assertIn('[[ "$RUNTIME_PHASE10_MAVEN_ARTIFACT_SHA256" =~ ^sha256:[0-9a-f]{64}$ ]] || exit 1', gate)

    def test_merge_gate_requires_maven_only_when_its_job_can_be_scheduled(self):
        """Native-Contract-complete runs skip contract-phase10-pgp-authority, so
        runtime-phase10-maven cannot run; the gate must not require it then."""
        from test_workflow_job_status_gates import _Evaluator
        parent = PARENT.read_text(encoding="utf-8")
        gate = parent.split("  merge-gate:\n", 1)[1]
        needs = gate.split("    runs-on:", 1)[0]
        self.assertIn("contract-phase10-pgp-authority", needs)
        self.assertIn("runtime-aggregate-attestation", needs)
        [line] = [row for row in gate.splitlines() if row.strip().startswith("RUNTIME_PHASE10_MAVEN_REQUIRED:")]
        expression = line.split("${{", 1)[1].rsplit("}}", 1)[0]
        job = parent.split("  runtime-phase10-maven:\n", 1)[1].split("\n  sdk-inputs:", 1)[0]
        condition = job.split("    if: >-\n", 1)[1].split("    uses:", 1)[0]
        condition = " ".join(row.strip() for row in condition.splitlines())
        # A live, uncancelled run: the evaluator otherwise leaves cancelled() unknown.
        self.assertEqual(1, condition.count("!cancelled()"))
        condition = condition.replace("!cancelled()", "true")
        scheduled = {"inputs.fullReuseAcceptanceOnly": False, "inputs.runtimeRecoveryOnly": False,
                     "inputs.sdkRecoveryOnly": False, "github.event_name": "pull_request",
                     "needs.plan.outputs.event_authorized": "true",
                     "needs.plan.outputs.remote_build_authorized": "true"}
        for aggregate in ("success", "skipped", "failure"):
            for pgp in ("success", "skipped", "failure"):
                context = {"needs.runtime-aggregate-attestation.result": aggregate,
                           "needs.contract-phase10-pgp-authority.result": pgp}
                with self.subTest(aggregate=aggregate, pgp=pgp):
                    required = _Evaluator(expression, context).evaluate()
                    self.assertIs(aggregate == pgp == "success", required)
                    # The gate requires the job exactly when its own condition can schedule it.
                    self.assertEqual(required, _Evaluator(condition, {**scheduled, **context}).evaluate())


if __name__ == "__main__":
    unittest.main()
