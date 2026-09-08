"""Workflow source/control checks, not genuine product or hosted acceptance."""

import os
from pathlib import Path
import re
import subprocess
import unittest

from ci.tests.test_contract_attestation_workflow import workflow_job


ROOT = Path(__file__).resolve().parents[2]


class ProductResumeWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = (ROOT / ".github/workflows/product-validation.yml").read_text(encoding="utf-8")
        cls.job = workflow_job(cls.workflow, "product-resume")
        cls.gate = workflow_job(cls.workflow, "merge-gate")

    def test_authorization_and_complete_upstreams_are_required_before_runner(self):
        condition = re.search(r"^    if: (?P<body>.*?)(?=^    [a-z][a-z-]*:)",
                              self.job, re.MULTILINE | re.DOTALL)
        self.assertIsNotNone(condition)
        for guard in (
            "needs.plan.outputs.event_authorized == 'true'",
            "needs.plan.outputs.remote_build_authorized == 'true'",
            "needs.plan.outputs.validation_reused != 'true'",
            "github.event_name != 'workflow_dispatch'",
            "needs.contract-continuation.outputs.contract_complete == 'true'",
            "needs.contract-continuation.result == 'success'",
            "needs.contract-attestation.result == 'success'",
        ):
            self.assertIn(guard, condition.group("body"))
        self.assertLess(condition.start(), self.job.index("    runs-on:"))
        needs = re.search(r"^    needs: \[(.*?)\]$", self.job, re.MULTILINE)
        self.assertIsNotNone(needs)
        self.assertEqual({"workflow-lint", "plan", "contract-continuation", "contract-attestation"},
                         {value.strip() for value in needs.group(1).split(",")})

    def test_exact_original_uploads_are_authenticated_before_resuming(self):
        downloads = re.findall(r"uses: actions/download-artifact@.*?(?=^      -|\Z)",
                               self.job, re.MULTILINE | re.DOTALL)
        self.assertEqual(1, len(downloads))
        self.assertIn("artifact-ids: ${{ needs.plan.outputs.plan_id }}", downloads[0])
        self.assertIn("path: build/product-resume-plan", downloads[0])
        self.assertNotRegex(downloads[0], re.compile(r"^          (?:name|pattern):", re.MULTILINE))
        for reference in (
            "needs.plan.outputs.plan_id", "needs.plan.outputs.plan_digest",
            "needs.contract-continuation.outputs.state_id", "needs.contract-continuation.outputs.state_digest",
            "needs.contract-attestation.outputs.artifact_id", "needs.contract-attestation.outputs.artifact_digest",
            "inputs.trustedWorkflowSha",
        ):
            self.assertIn(reference, self.job)
        for flag in ("--plan-artifact-id", "--plan-artifact-sha256", "--state-artifact-id", "--state-artifact-sha256",
                     "--release-artifact-id", "--release-artifact-sha256", "--trusted-workflow-sha"):
            self.assertIn(flag, self.job)
        self.assertEqual(1, self.job.count("ci/product_reuse.py capture-product-resume-inputs"))
        self.assertEqual(1, self.job.count("ci/product_reuse.py resume-products"))
        self.assertLess(self.job.index("capture-product-resume-inputs"), self.job.index("resume-products"))
        for flag, path in (
            ("--plan", "build/product-resume-inputs/plan/impact-plan.json"),
            ("--discovery-root", "build/product-resume-inputs/plan/product-reuse"),
            ("--state-root", "build/product-resume-inputs/state"),
            ("--contract-handoff", "build/product-resume-inputs/release/contract-input"),
            ("--destination", "build/product-resume-state"),
        ):
            self.assertRegex(self.job, re.escape(flag) + r"\s+[\"']?" + re.escape(path) + r"(?:[\"']|\s|$)")

    def test_resume_has_no_new_discovery_signing_or_product_execution(self):
        self.assertNotIn("secrets.", self.job)
        self.assertNotIn("CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY", self.job)
        self.assertNotIn("ci/contract_release.py", self.job)
        self.assertNotIn("ssh-keygen", self.job)
        self.assertNotRegex(self.job, r"ci/product_reuse\.py\s+(?:discover|advance-products|advance-contract)\b")
        self.assertNotRegex(self.job, r"uses: (?:\./|actions/cache(?:/|@)|actions/setup-)")
        self.assertNotRegex(self.job, r"(?:\./gradlew|\bcargo\s+(?:build|test)|\bcmake\s|\bxcodebuild\b|\bnpm\s+(?:ci|install|run)|\bpip\s+install)")

    def test_entire_inputs_and_resumed_state_are_uploaded_immutably(self):
        uploads = re.findall(r"uses: actions/upload-artifact@.*?(?=^      -|\Z)",
                             self.job, re.MULTILINE | re.DOTALL)
        self.assertEqual(1, len(uploads))
        for value in ("overwrite: false", "if-no-files-found: error", "include-hidden-files: true",
                      "build/product-resume-inputs", "build/product-resume-state"):
            self.assertIn(value, uploads[0])
        self.assertNotIn("release/contract-input", uploads[0])
        header = self.job.split("    steps:", 1)[0]
        for name in ("artifact_id:", "artifact_digest:", "full_reuse:", "target_jobs_required:"):
            self.assertIn(name, header)
        self.assertIn(".outputs.artifact-id", header)
        self.assertIn(".outputs.artifact-digest", header)
        self.assertIn("sha256:", header)
        self.assertIn(".outputs.full_reuse", header)
        self.assertIn(".outputs.target_jobs_required", header)
        for job_name, output_name, step_name in (("plan", "plan", "upload_plan"),
                                                  ("contract-continuation", "state", "upload_final_state")):
            job = workflow_job(self.workflow, job_name)
            self.assertIn(f"{output_name}_id: ${{{{ steps.{step_name}.outputs.artifact-id }}}}", job)
            self.assertIn(f"{output_name}_digest: sha256:${{{{ steps.{step_name}.outputs.artifact-digest }}}}", job)

    def test_actual_merge_guard_rejects_missing_required_resume_output(self):
        needs = re.search(r"^    needs: \[(.*?)\]$", self.gate, re.MULTILINE)
        self.assertIsNotNone(needs)
        self.assertIn("product-resume", {value.strip() for value in needs.group(1).split(",")})
        first = re.split(r"(?=^      - )", self.gate, flags=re.MULTILINE)[1]
        for value in ("needs.product-resume.result", "needs.product-resume.outputs.artifact_id",
                      "needs.product-resume.outputs.artifact_digest"):
            self.assertIn(value, first)
        script_match = re.search(r"^        run: \|\n(?P<body>(?:^          .*\n|^\n)+)", first, re.MULTILINE)
        self.assertIsNotNone(script_match)
        script = "\n".join(line[10:] if line.startswith(" " * 10) else line
                           for line in script_match.group("body").splitlines())
        base = {
            "EVENT_AUTHORIZED": "true", "MERGE_READY": "true", "REMOTE_BUILD_AUTHORIZED": "true",
            "REMOTE_BUILD_AUTHORIZATION_REASON": "pull-request-final", "RESULTS": "success success",
            "CONTRACT_COMPLETE": "true", "CONTRACT_ATTESTATION_RESULT": "success",
            "CONTRACT_ATTESTATION_ARTIFACT_ID": "700", "CONTRACT_ATTESTATION_ARTIFACT_DIGEST": "sha256:" + "a" * 64,
            "PRODUCT_RESUME_RESULT": "success", "PRODUCT_RESUME_ARTIFACT_ID": "701",
            "PRODUCT_RESUME_ARTIFACT_DIGEST": "sha256:" + "b" * 64,
            "PRODUCT_FULL_REUSE": "true", "RUNTIME_WAVE_FAILED": "false false false false",
        }
        cases = [({}, True), ({"CONTRACT_COMPLETE": "false", "PRODUCT_RESUME_RESULT": "skipped",
                               "PRODUCT_RESUME_ARTIFACT_ID": "", "PRODUCT_RESUME_ARTIFACT_DIGEST": ""}, True)]
        cases.extend(({"PRODUCT_RESUME_RESULT": value}, False) for value in ("failure", "cancelled", "skipped", ""))
        cases.extend(({field: ""}, False) for field in ("PRODUCT_RESUME_ARTIFACT_ID", "PRODUCT_RESUME_ARTIFACT_DIGEST"))
        cases.append(({"PRODUCT_RESUME_ARTIFACT_DIGEST": "not-a-digest"}, False))
        cases.extend(({"PRODUCT_FULL_REUSE": value}, False) for value in ("false", ""))
        cases.append(({"RUNTIME_WAVE_FAILED": "false true false false"}, False))
        for change, expected in cases:
            with self.subTest(change=change):
                result = subprocess.run(["bash", "-e", "-o", "pipefail", "-c", script],
                                        env={"PATH": os.environ.get("PATH", ""), **base, **change},
                                        capture_output=True, text=True)
                self.assertEqual(expected, result.returncode == 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
