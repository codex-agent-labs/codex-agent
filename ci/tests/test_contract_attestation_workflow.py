"""Source wiring checks only; no protected environment or hosted execution is asserted."""

from pathlib import Path
import os
import re
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
TRUSTED_SOURCE = "0953cb9ca87d30cf08b0f1227a204b701cafea75"


def workflow_job(source: str, name: str) -> str:
    match = re.search(rf"^  {re.escape(name)}:\n(?P<body>.*?)(?=^  [a-z][a-z0-9-]*:\n|\Z)",
                      source, re.MULTILINE | re.DOTALL)
    if match is None:
        raise AssertionError(f"Missing workflow job: {name}")
    return match.group("body")


class ContractAttestationWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = (ROOT / ".github/workflows/product-validation.yml").read_text(encoding="utf-8")
        cls.job = workflow_job(cls.workflow, "contract-attestation")
        cls.gate = workflow_job(cls.workflow, "merge-gate")

    def test_signer_is_authorized_before_allocating_a_runner(self):
        condition = re.search(r"^    if: (?P<value>.*?)(?=^    [a-z][a-z-]*:)",
                              self.job, re.MULTILINE | re.DOTALL)
        self.assertIsNotNone(condition)
        expression = condition.group("value")
        for guard in (
            "needs.plan.outputs.event_authorized == 'true'",
            "needs.plan.outputs.remote_build_authorized == 'true'",
            "needs.plan.outputs.validation_reused != 'true'",
            "needs.contract-continuation.result == 'success'",
            "needs.contract-continuation.outputs.contract_complete == 'true'",
            "github.event_name != 'workflow_dispatch'",
        ):
            self.assertIn(guard, expression)
        self.assertLess(condition.start(), self.job.index("    runs-on:"))
        self.assertIn("    environment: product-attestation", self.job)
        needs = re.search(r"^    needs: \[(.*?)\]$", self.job, re.MULTILINE)
        self.assertIsNotNone(needs)
        self.assertIn("plan", [name.strip() for name in needs.group(1).split(",")])
        self.assertIn("contract-continuation", [name.strip() for name in needs.group(1).split(",")])

    def test_only_reviewed_source_is_executable_and_no_product_tasks_run(self):
        self.assertEqual(1, self.job.count("uses: actions/checkout@"))
        checkout = re.search(r"uses: actions/checkout@.*?(?=^      -|\Z)",
                             self.job, re.MULTILINE | re.DOTALL)
        self.assertIsNotNone(checkout)
        for setting in (f"ref: {TRUSTED_SOURCE}", "path: trusted-source", "persist-credentials: false"):
            self.assertIn(setting, checkout.group())
        self.assertNotIn("ref: ${{ needs.plan.outputs.validation_commit }}", self.job)
        self.assertNotRegex(self.job, r"uses: (?:\./|actions/cache(?:/|@)|actions/setup-)")
        self.assertNotRegex(self.job, r"(?:\./gradlew|\bcargo\s+(?:build|test)|\bcmake\s|\bxcodebuild\b|\bnpm\s+(?:ci|install|run)|\bpip\s+install)")
        self.assertIn("ci/contract_release.py", self.job)
        self.assertIn("--trusted-source-sha", self.job)
        self.assertIn(TRUSTED_SOURCE, self.job)
        self.assertNotIn("ssh-keygen", self.job)

    def test_secret_is_scoped_to_the_single_existing_signer_invocation(self):
        steps = re.split(r"(?=^      - )", self.job, flags=re.MULTILINE)
        secret_steps = [step for step in steps if "secrets." in step]
        self.assertEqual(1, len(secret_steps))
        self.assertIn("CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY", secret_steps[0])
        self.assertIn("ci/contract_release.py", secret_steps[0])
        self.assertEqual(1, self.job.count("ci/contract_release.py"))
        self.assertNotIn("secrets.", self.job.split("    steps:", 1)[0])
        self.assertNotRegex(self.job, r"(?:cat|echo|printf).*CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY")

    def test_current_artifact_identity_is_forwarded_from_continuation_outputs(self):
        for value in (
            "needs.contract-continuation.outputs.attestation_inputs_id",
            "needs.contract-continuation.outputs.attestation_inputs_digest",
            "needs.plan.outputs.validation_tree", "--artifact-id", "--artifact-sha256",
            "--trusted-workflow-sha", "--validation-tree", "--contract-version",
        ):
            self.assertIn(value, self.job)
        self.assertNotIn("uses: actions/download-artifact", self.job)
        self.assertIn("needs.contract-continuation.outputs.contract_version", self.job)

    def test_workflow_pin_is_a_required_caller_literal_checked_by_the_existing_cli(self):
        declaration = re.search(r"^      trustedWorkflowSha:\n(?P<body>.*?)(?=^      \w|^permissions:)",
                                self.workflow, re.MULTILINE | re.DOTALL)
        self.assertIsNotNone(declaration)
        self.assertIn("required: true", declaration.group("body"))
        self.assertIn("type: string", declaration.group("body"))
        self.assertIn("TRUSTED_WORKFLOW_SHA: ${{ inputs.trustedWorkflowSha }}", self.job)
        self.assertIn('--trusted-workflow-sha "$TRUSTED_WORKFLOW_SHA"', self.job)
        caller = workflow_job((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"), "product-validation")
        selected = re.search(r"uses: codex-agent-labs/codex-agent/\.github/workflows/product-validation\.yml@([0-9a-f]{40})", caller)
        argument = re.search(r"trustedWorkflowSha: ([0-9a-f]{40})", caller)
        self.assertIsNotNone(selected)
        self.assertIsNotNone(argument)
        self.assertEqual(selected.group(1), argument.group(1))
        pinned = subprocess.run(
            ["git", "show", f"{selected.group(1)}:.github/workflows/product-validation.yml"],
            cwd=ROOT, check=True, capture_output=True, text=True,
        )
        self.assertEqual(self.workflow, pinned.stdout, "Caller must execute the reviewed current workflow bytes")

    def test_complete_external_capture_upload_is_immutable(self):
        uploads = re.findall(r"uses: actions/upload-artifact@.*?(?=^      -|\Z)",
                             self.job, re.MULTILINE | re.DOTALL)
        self.assertEqual(1, len(uploads))
        self.assertIn("overwrite: false", uploads[0])
        self.assertIn("if-no-files-found: error", uploads[0])
        self.assertNotIn("/contract-input/*", uploads[0])
        outputs = self.job.split("    steps:", 1)[0]
        self.assertIn(".outputs.artifact-id", outputs)
        self.assertIn("sha256:", outputs)
        self.assertIn(".outputs.artifact-digest", outputs)
        for name in ("artifact_name:", "artifact_id:", "artifact_digest:"):
            self.assertIn(name, outputs)
        self.assertIn("steps.upload_attestation.outputs.artifact-id", outputs)
        self.assertIn("steps.upload_attestation.outputs.artifact-digest", outputs)

    def test_merge_gate_waits_for_the_protected_job(self):
        needs = re.search(r"^    needs: \[(.*?)\]$", self.gate, re.MULTILINE)
        self.assertIsNotNone(needs)
        self.assertIn("contract-attestation", [name.strip() for name in needs.group(1).split(",")])
        self.assertIn("needs.contract-attestation.result", self.gate)
        self.assertIn("needs.contract-continuation.outputs.contract_complete", self.gate)
        self.assertIn("needs.plan.outputs.validation_reused", self.gate)

    def test_actual_merge_gate_shell_rejects_missing_failed_or_skipped_required_attestation(self):
        # Execute only the existing prerequisite shell, never checkout/download/product steps.
        first = re.split(r"(?=^      - )", self.gate, flags=re.MULTILINE)[1]
        match = re.search(r"^        run: \|\n(?P<body>(?:^          .*\n|^\n)+)", first, re.MULTILINE)
        self.assertIsNotNone(match)
        script = "\n".join(line[10:] if line.startswith(" " * 10) else line
                           for line in match.group("body").splitlines())
        for name in ("CONTRACT_COMPLETE", "CONTRACT_ATTESTATION_RESULT",
                     "CONTRACT_ATTESTATION_ARTIFACT_ID", "CONTRACT_ATTESTATION_ARTIFACT_DIGEST"):
            self.assertIn(name, first)
        base = {
            "EVENT_AUTHORIZED": "true", "MERGE_READY": "true", "REMOTE_BUILD_AUTHORIZED": "true",
            "REMOTE_BUILD_AUTHORIZATION_REASON": "pull-request-final", "RESULTS": "success success",
            "CONTRACT_COMPLETE": "true", "CONTRACT_ATTESTATION_RESULT": "success",
            "CONTRACT_ATTESTATION_ARTIFACT_ID": "700", "CONTRACT_ATTESTATION_ARTIFACT_DIGEST": "sha256:" + "a" * 64,
            "PRODUCT_RESUME_RESULT": "success", "PRODUCT_RESUME_ARTIFACT_ID": "701",
            "SDK_COMPLETION_RESULT": "success", "SDK_COMPLETE": "true",
            "PRODUCT_RESUME_ARTIFACT_DIGEST": "sha256:" + "b" * 64,
            "PRODUCT_FULL_REUSE": "true", "RUNTIME_WAVE_FAILED": "false false false false",
        }
        cases = [({}, True), ({"CONTRACT_COMPLETE": "false", "CONTRACT_ATTESTATION_RESULT": "skipped",
                               "CONTRACT_ATTESTATION_ARTIFACT_ID": "", "CONTRACT_ATTESTATION_ARTIFACT_DIGEST": ""}, True)]
        cases.extend(({"CONTRACT_ATTESTATION_RESULT": result}, False) for result in ("failure", "cancelled", "skipped", ""))
        cases.extend(({field: ""}, False) for field in ("CONTRACT_ATTESTATION_ARTIFACT_ID", "CONTRACT_ATTESTATION_ARTIFACT_DIGEST"))
        for changes, success in cases:
            with self.subTest(changes=changes):
                result = subprocess.run(["bash", "-e", "-o", "pipefail", "-c", script],
                                        env={"PATH": os.environ.get("PATH", ""), **base, **changes},
                                        capture_output=True, text=True)
                self.assertEqual(success, result.returncode == 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
