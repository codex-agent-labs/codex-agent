"""Saved wave-9 routing only; no hosted execution or content admission claim."""

import importlib
import json
import os
from pathlib import Path
import re
import tempfile
import textwrap
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
MATRICES = ("sdk-ios-validation", "sdk-apple-signing-prepare", "sdk-apple-validation-attestation")
JOBS = ("sdk-native-result", "sdk-ios-validation-native", *MATRICES, "sdk-collect-9", "sdk-ios-validation-result")


class SdkAppleValidationWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.source = (ROOT / ".github/workflows/product-validation.yml").read_text()

    def job(self, name):
        matches = re.findall(rf"(?ms)^  {re.escape(name)}:\n.*?(?=^  [a-z][a-z0-9-]*:|\Z)", self.source)
        self.assertEqual(1, len(matches), name)
        return matches[0]

    def needs(self, job):
        match = re.search(r"(?m)^    needs: \[([^\]]+)\]$", job)
        self.assertIsNotNone(match)
        values = [value.strip() for value in match[1].split(",")]
        self.assertEqual(len(values), len(set(values)))
        return set(values)

    def condition(self, job):
        match = re.search(r"(?ms)^    if: >-\n(.*?)(?=^    \S)", job)
        self.assertIsNotNone(match)
        return match[1]

    def test_all_jobs_authorized_before_matrix_expansion(self):
        for name in JOBS:
            with self.subTest(job=name):
                job = self.job(name)
                condition = self.condition(job)
                for expected in ("always()", "needs.plan.outputs.event_authorized == 'true'",
                                 "needs.plan.outputs.remote_build_authorized == 'true'"):
                    self.assertIn(expected, condition)
                if name in MATRICES:
                    self.assertLess(job.index("    if:"), job.index("    strategy:"))
                    self.assertIn("fail-fast: false", job)
                    matrix = "needs.sdk-native-result.outputs.sdk_matrix"
                    if name != "sdk-ios-validation":
                        matrix = "needs.sdk-ios-validation-outcome.outputs.signing_matrix || " + matrix
                    self.assertIn("matrix: ${{ fromJSON(" + matrix + " || '{\"include\":[]}') }}", job)
                    self.assertIn("needs.sdk-native-result.result == 'success'", condition)
                    self.assertIn("needs.sdk-native-result.outputs.sdk_workers_required == 'true'", condition)

    def test_failed_sibling_does_not_suppress_preparation_signing_or_collection(self):
        for name in ("sdk-apple-signing-prepare", "sdk-apple-validation-attestation", "sdk-collect-9"):
            with self.subTest(job=name):
                job = self.job(name)
                condition = self.condition(job)
                self.assertIn("always()", condition)
                self.assertIn("needs.sdk-native-result.outputs.sdk_workers_required == 'true'", condition)
                self.assertIn("(needs.sdk-ios-validation.result == 'success' || needs.sdk-ios-validation-native.result == 'success' || "
                              "needs.sdk-ios-validation-outcome.result == 'success')", condition)
                self.assertIn("needs.sdk-ios-validation-outcome.outputs.all_failed != 'true'", condition)
                for matrix in MATRICES[1:]:
                    self.assertNotIn("needs." + matrix + ".result", condition)
        self.assertIn("sdk-ios-validation", self.needs(self.job("sdk-apple-signing-prepare")))
        self.assertIn("sdk-apple-signing-prepare", self.needs(self.job("sdk-apple-validation-attestation")))
        self.assertTrue(set(MATRICES) <= self.needs(self.job("sdk-collect-9")))

    def test_prefix_gate_and_election_share_one_job_without_product_authentication(self):
        job = self.job("sdk-native-result")
        self.assertNotIn("  sdk-ios-validation-plan:", self.source)
        self.assertEqual(1, job.count("uses: actions/checkout@"))
        self.assertIn("fetch-depth: 1", job)
        self.assertNotIn("tooling_required", job)
        for action in ("capture-sdk-tooling", "prepare-sdk-apple-policy", "download-artifact"):
            self.assertNotIn(action, job)
        capture = job.split("      - id: capture\n", 1)[1]
        self.assertIn("if: steps.result.outputs.artifact_id != ''", capture)
        self.assertIn("uses: ./.github/actions/capture-runtime-state/route", capture)
        self.assertIn("family: ios-validation", capture)
        self.assertIn("artifact-id: ${{ steps.result.outputs.artifact_id }}", capture)
        self.assertIn("needs['sdk-plan']['result'] != 'success'", job)
        self.assertLess(job.index("select_ios_ready_prefix(needs)"), job.index("id: capture"))
        self.assertIn("sdk_workers_required: ${{ steps.capture.outputs.sdk-workers-required }}", job)

    def test_election_worker_and_collector_preserve_parent_and_caller_policy(self):
        for name, action in (("sdk-ios-validation", "sdk-ios-validation-worker"),
                             ("sdk-collect-9", "collect-runtime-wave")):
            with self.subTest(job=name):
                job = self.job(name)
                block = job.split("uses: ./.github/actions/" + action, 1)[1].split("\n      - ", 1)[0]
                for flag, output in (("artifact-id", "artifact_id"), ("artifact-sha256", "artifact_digest"),
                                     ("state-wave", "state_wave"), ("sdk-state-wave", "sdk_state_wave")):
                    if name == "sdk-ios-validation":
                        env = {"artifact_id": "SDK_STATE_ARTIFACT_ID", "artifact_digest": "SDK_STATE_ARTIFACT_DIGEST",
                               "state_wave": "SDK_STATE_WAVE", "sdk_state_wave": "SDK_STATE_SDK_WAVE"}[output]
                        self.assertIn(flag + ": ${{ env." + env + " }}", block)
                        self.assertIn(env + ": ${{ needs.sdk-native-result.outputs." + output + " }}", job)
                    else:
                        self.assertIn(flag + ": ${{ needs.sdk-native-result.outputs." + output + " }}", block)
                self.assertIn("sdk-validation-tooling: ${{ steps.tooling.outputs.tooling-policy }}", block)
                self.assertIn("sdk-apple-validation-policy: ${{ steps.apple-policy.outputs.apple-policy }}", block)
                self.assertIn("trusted-workflow-sha: ${{ needs.plan.outputs.publisher_sha }}", block)
                self.assertLess(job.index("uses: ./.github/actions/prepare-sdk-apple-policy"),
                                job.index("uses: ./.github/actions/" + action))
                if name != "sdk-ios-validation":
                    self.assertIn("product: sdk", block)
                    self.assertIn("sdk-family: ios-validation", block)
        self.assertIn("wave: '9'", self.job("sdk-collect-9"))
        worker = self.job("sdk-ios-validation")
        self.assertIn("format('sdk-sdk-ios-validation-{0}', matrix.target)", worker)
        self.assertIn("target: ${{ matrix.target }}", worker)
        self.assertIn("build-key: ${{ matrix.buildKey }}", worker)

    def test_signer_uses_approved_source_distinct_from_publisher_and_candidate(self):
        job = self.job("sdk-apple-validation-attestation")
        self.assertIn("environment: product-attestation", job)
        self.assertIn("needs.workflow-lint.result == 'success'", self.condition(job))
        self.assertIn("trusted-source-sha: ${{ needs.plan.outputs.source_sha }}", job)
        self.assertIn("ref: ${{ needs.plan.outputs.source_sha }}\n          path: trusted-source", job)
        self.assertIn("trusted-workflow-sha: ${{ needs.plan.outputs.publisher_sha }}", job)
        self.assertIn("repository: codex-agent-labs/codex-agent", job)
        self.assertIn("uses: ./trusted-source/.github/actions/attest-sdk-apple-validation", job)
        self.assertIn("ref: ${{ needs.plan.outputs.validation_commit }}\n          path: candidate-source", job)
        self.assertIn("candidate-root: ${{ github.workspace }}/candidate-source", job)
        self.assertIn("name: sdk-apple-validation-attestation-${{ matrix.target }}", job)
        self.assertIn("plan-path: ${{ runner.temp }}/sdk-apple-plan/impact-plan.json", job)
        for key in ("target", "build-key"):
            value = "target" if key == "target" else "buildKey"
            self.assertIn(key + ": ${{ matrix." + value + " }}", job)
        for name in ("sdk-native-result", "sdk-ios-validation", "sdk-apple-signing-prepare",
                     "sdk-collect-9", "sdk-ios-validation-result"):
            self.assertNotIn("CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY", self.job(name))
        for forbidden in ("capture-sdk-tooling", "prepare-sdk-apple-policy", "setup-kmp", "setup-java", "gradlew"):
            self.assertNotIn(forbidden, job)

    def test_native_worker_starts_after_exact_checks_and_shares_unchanged_worker_steps(self):
        native, ordinary, plan = (self.job(name) for name in ("sdk-ios-validation-native", "sdk-ios-validation", "plan"))
        self.assertEqual({"plan", "workflow-lint"}, self.needs(native))
        for guard in ("!cancelled()", "needs.plan.result == 'success'", "needs.workflow-lint.result == 'success'",
                      "needs.plan.outputs.native_ios_worker_ready == 'true'",
                      "needs.plan.outputs.validation_reused != 'true'", "github.event_name != 'workflow_dispatch'"):
            self.assertIn(guard, self.condition(native))
        self.assertIn("needs.plan.outputs.native_ios_worker_ready != 'true'", self.condition(ordinary))
        self.assertIn("steps: &sdk_ios_validation_steps", ordinary)
        self.assertIn("steps: *sdk_ios_validation_steps", native)
        self.assertEqual(1, self.source.count("uses: ./.github/actions/sdk-ios-validation-worker"))
        self.assertNotIn("needs.sdk-plan.", native)
        self.assertNotIn("needs.sdk-native-result.", native)
        self.assertIn("sdk-ios-validation-ordinary-inactive", ordinary)
        self.assertIn("sdk-ios-validation-native-inactive", native)
        for job in (native, ordinary):
            self.assertIn("format('sdk-sdk-ios-validation-{0}', matrix.target)", job)
        self.assertIn("matrix: ${{ fromJSON(needs.plan.outputs.native_ios_matrix || '{\"include\":[]}') }}", native)
        self.assertIn("SDK_STATE_ARTIFACT_ID: ${{ needs.plan.outputs.native_resume_artifact_id }}", native)
        self.assertIn("SDK_STATE_ARTIFACT_DIGEST: ${{ needs.plan.outputs.native_resume_artifact_digest }}", native)
        self.assertIn("SDK_STATE_WAVE: '0'", native)
        self.assertIn("SDK_STATE_SDK_WAVE: ''", native)
        for field in ("ARTIFACT_ID", "ARTIFACT_SHA256", "TRANSPORT_PRODUCER"):
            self.assertIn("SDK_TOOLING_" + field + ": ${{ needs.plan.outputs.tooling_" + field.lower() + " }}", native)
        readiness = next(line for line in plan.splitlines() if "native_ios_worker_ready:" in line)
        for gate in ("steps.native-route.outputs.native_sdk_direct == 'true'",
                     "steps.product-reuse.outputs.native_contract_complete == 'true'",
                     "steps.product-reuse.outputs.tooling_miss == 'false'",
                     "steps.product-reuse.outputs.tooling_artifact_id != ''",
                     "steps.product-reuse.outputs.tooling_transport_producer != ''"):
            self.assertIn(gate, readiness)
        for name in ("sdk-ios-validation-outcome", "sdk-apple-signing-prepare",
                     "sdk-apple-validation-attestation", "sdk-collect-9", "sdk-ios-validation-result"):
            self.assertTrue({"sdk-ios-validation", "sdk-ios-validation-native"} <= self.needs(self.job(name)))
        outcome = self.condition(self.job("sdk-ios-validation-outcome"))
        self.assertIn("needs.sdk-native-result.outputs.sdk_workers_required == 'true'", outcome)
        self.assertNotIn("needs.sdk-ios-validation.result != 'success'", outcome)
        for name in ("sdk-apple-signing-prepare", "sdk-apple-validation-attestation"):
            self.assertIn("needs.sdk-ios-validation-outcome.outputs.signing_required == 'true'",
                          self.condition(self.job(name)))
        for name in ("sdk-apple-signing-prepare", "sdk-apple-validation-attestation", "sdk-collect-9"):
            self.assertIn("needs.sdk-ios-validation-outcome.result == 'success' &&",
                          self.condition(self.job(name)))

    def test_terminal_executes_selector_after_all_matrices_and_never_fabricates_output(self):
        job = self.job("sdk-ios-validation-result")
        expected_jobs = {"plan", "sdk-native-result", "sdk-ios-validation-native", "sdk-ios-validation-outcome", *MATRICES, "sdk-collect-9"}
        self.assertEqual(expected_jobs, self.needs(job))
        self.assertNotIn("sdk_workers_required", self.condition(job))
        for name in ("artifact_id", "artifact_digest", "state_wave", "sdk_state_wave"):
            self.assertIn(name + ": ${{ steps.result.outputs." + name + " }}", job)
        match = re.search(r"(?ms)^          python3 - <<'PY'\n(.*?)^          PY$", job)
        self.assertIsNotNone(match)
        script = textwrap.dedent(match[1])
        module = importlib.import_module("ci.sdk_native_continuation")
        needs = {name: {"result": "skipped", "outputs": {}} for name in expected_jobs}
        locator = {"artifact_id": "99", "artifact_digest": "sha256:" + "a" * 64,
                   "state_wave": "0", "sdk_state_wave": "9"}
        for fails in (False, True):
            with self.subTest(fails=fails), tempfile.TemporaryDirectory(prefix="apple-terminal-") as temporary:
                output = Path(temporary) / "output"
                with patch.dict(os.environ, {"RESULTS": json.dumps(needs), "GITHUB_OUTPUT": str(output)}, clear=True), \
                        patch.object(module, "select_native_state", return_value=locator,
                                     side_effect=ValueError("failed sibling") if fails else None) as select:
                    if fails:
                        with self.assertRaisesRegex(ValueError, "failed sibling"):
                            exec(compile(script, "saved-apple-terminal", "exec"), {})
                        self.assertFalse(output.exists())
                    else:
                        exec(compile(script, "saved-apple-terminal", "exec"), {})
                        self.assertEqual(locator, dict(line.split("=", 1) for line in output.read_text().splitlines()))
                select.assert_called_once_with(needs, stage="ios-validation")


if __name__ == "__main__":
    unittest.main()
