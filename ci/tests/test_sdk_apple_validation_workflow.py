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
JOBS = ("sdk-ios-validation-plan", *MATRICES, "sdk-collect-9", "sdk-ios-validation-result")


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
                    self.assertIn("matrix: ${{ fromJSON(needs.sdk-ios-validation-plan.outputs.sdk_matrix || '{\"include\":[]}') }}", job)
                    self.assertIn("needs.sdk-ios-validation-plan.result == 'success'", condition)
                    self.assertIn("needs.sdk-ios-validation-plan.outputs.sdk_workers_required == 'true'", condition)

    def test_failed_sibling_does_not_suppress_preparation_signing_or_collection(self):
        for name in ("sdk-apple-signing-prepare", "sdk-apple-validation-attestation", "sdk-collect-9"):
            with self.subTest(job=name):
                job = self.job(name)
                condition = self.condition(job)
                self.assertIn("always()", condition)
                self.assertIn("needs.sdk-ios-validation-plan.outputs.sdk_workers_required == 'true'", condition)
                for matrix in MATRICES:
                    self.assertNotIn("needs." + matrix + ".result", condition)
        self.assertIn("sdk-ios-validation", self.needs(self.job("sdk-apple-signing-prepare")))
        self.assertIn("sdk-apple-signing-prepare", self.needs(self.job("sdk-apple-validation-attestation")))
        self.assertTrue(set(MATRICES) <= self.needs(self.job("sdk-collect-9")))

    def test_no_tooling_election_skips_exact_four_setup_steps_but_still_captures_state(self):
        job = self.job("sdk-ios-validation-plan")
        self.assertNotIn("tooling_required", self.condition(job))
        steps = re.split(r"\n      - ", job)[1:]
        markers = ("name: Select installed caller Java", "id: tooling\n",
                   "uses: actions/download-artifact@", "id: apple-policy\n")
        for marker in markers:
            with self.subTest(step=marker):
                selected = [step for step in steps if marker in step]
                self.assertEqual(1, len(selected))
                self.assertEqual(["needs.plan.outputs.tooling_required == 'true'"],
                                 re.findall(r"(?m)^        if: (.+)$", selected[0]))
        self.assertEqual(4, job.count("if: needs.plan.outputs.tooling_required == 'true'"))
        capture = next(step for step in steps if step.startswith("id: capture\n"))
        self.assertNotRegex(capture, r"(?m)^        if:")
        self.assertIn("uses: ./.github/actions/capture-runtime-state", capture)
        self.assertIn("sdk-family: ios-validation", capture)
        self.assertIn("artifact-id: ${{ needs.sdk-native-result.outputs.artifact_id }}", capture)
        self.assertIn("sdk-validation-tooling: ${{ steps.tooling.outputs.tooling-policy }}", capture)
        self.assertIn("sdk-apple-validation-policy: ${{ steps.apple-policy.outputs.apple-policy }}", capture)

    def test_election_worker_and_collector_preserve_parent_and_caller_policy(self):
        for name, action in (("sdk-ios-validation-plan", "capture-runtime-state"),
                             ("sdk-ios-validation", "sdk-ios-validation-worker"),
                             ("sdk-collect-9", "collect-runtime-wave")):
            with self.subTest(job=name):
                job = self.job(name)
                block = job.split("uses: ./.github/actions/" + action, 1)[1].split("\n      - ", 1)[0]
                for flag, output in (("artifact-id", "artifact_id"), ("artifact-sha256", "artifact_digest"),
                                     ("state-wave", "state_wave"), ("sdk-state-wave", "sdk_state_wave")):
                    self.assertIn(flag + ": ${{ needs.sdk-native-result.outputs." + output + " }}", block)
                self.assertIn("sdk-validation-tooling: ${{ steps.tooling.outputs.tooling-policy }}", block)
                self.assertIn("sdk-apple-validation-policy: ${{ steps.apple-policy.outputs.apple-policy }}", block)
                self.assertIn("trusted-workflow-sha: ${{ inputs.trustedWorkflowSha }}", block)
                self.assertLess(job.index("uses: ./.github/actions/prepare-sdk-apple-policy"),
                                job.index("uses: ./.github/actions/" + action))
                if name != "sdk-ios-validation":
                    self.assertIn("product: sdk", block)
                    self.assertIn("sdk-family: ios-validation", block)
        self.assertIn("wave: '9'", self.job("sdk-collect-9"))
        worker = self.job("sdk-ios-validation")
        self.assertIn("name: sdk-sdk-ios-validation-${{ matrix.target }}", worker)
        self.assertIn("target: ${{ matrix.target }}", worker)
        self.assertIn("build-key: ${{ matrix.buildKey }}", worker)

    def test_signer_uses_same_fixed_reviewed_source_and_separate_candidate(self):
        job = self.job("sdk-apple-validation-attestation")
        self.assertIn("environment: product-attestation", job)
        self.assertIn("needs.workflow-lint.result == 'success'", self.condition(job))
        pin = re.search(r"(?m)^          trusted-source-sha: ([0-9a-f]{40})$", job)
        self.assertIsNotNone(pin)
        self.assertIn("ref: " + pin[1] + "\n          path: trusted-source", job)
        self.assertIn("repository: codex-agent-labs/codex-agent", job)
        self.assertIn("uses: ./trusted-source/.github/actions/attest-sdk-apple-validation", job)
        self.assertIn("ref: ${{ needs.plan.outputs.validation_commit }}\n          path: candidate-source", job)
        self.assertIn("candidate-root: ${{ github.workspace }}/candidate-source", job)
        self.assertIn("name: sdk-apple-validation-attestation-${{ matrix.target }}", job)
        self.assertIn("plan-path: ${{ runner.temp }}/sdk-apple-plan/impact-plan.json", job)
        for key in ("target", "build-key"):
            value = "target" if key == "target" else "buildKey"
            self.assertIn(key + ": ${{ matrix." + value + " }}", job)
        for name in ("sdk-ios-validation-plan", "sdk-ios-validation", "sdk-apple-signing-prepare",
                     "sdk-collect-9", "sdk-ios-validation-result"):
            self.assertNotIn("CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY", self.job(name))
        for forbidden in ("capture-sdk-tooling", "prepare-sdk-apple-policy", "setup-kmp", "setup-java", "gradlew"):
            self.assertNotIn(forbidden, job)

    def test_terminal_executes_selector_after_all_matrices_and_never_fabricates_output(self):
        job = self.job("sdk-ios-validation-result")
        expected_jobs = {"plan", "sdk-native-result", "sdk-ios-validation-plan", *MATRICES, "sdk-collect-9"}
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
