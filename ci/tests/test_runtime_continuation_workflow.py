"""Run the actual workflow selector; no hosted execution or product trust is claimed."""

from copy import deepcopy
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest

from ci.tests.test_contract_attestation_workflow import workflow_job


ROOT = Path(__file__).resolve().parents[2]


class RuntimeContinuationWorkflowTest(unittest.TestCase):
    def test_all_runtime_reference_consumers_restore_caller_authority_before_capture(self):
        jobs = ['runtime-linux-arm64-supervisor', 'runtime-continuation', 'runtime-aggregate',
                'runtime-aggregate-continuation', 'runtime-collect-5']
        jobs += [f'runtime-{role}-{wave}' for wave in range(1, 5) for role in ('workers', 'collect')]
        restore = 'uses: codex-agent-labs/codex-agent/.github/actions/restore-reuse-qualification@reuse-authority'
        for name in jobs:
            with self.subTest(job=name):
                job = workflow_job(self.workflow, name)
                self.assertEqual(1, job.count(restore))
                self.assertIn('authority-read-token: ${{ secrets.REUSE_AUTHORITY_READ_TOKEN }}', job)
                self.assertLess(job.index(restore), job.index('uses: ./.github/actions/capture-sdk-tooling'))
        supervisor = workflow_job(self.workflow, 'runtime-linux-arm64-supervisor')
        self.assertIn('tooling+=(--completed-frozen-policy "$CODEX_AGENT_COMPLETED_REUSE_POLICY")', supervisor)

    def test_retained_signed_handoffs_cover_ready_and_recovered_aggregate(self):
        step = self.job.split("      - id: retained\n", 1)[1].split("        env:", 1)[0]
        expression = " ".join(step.split("if: >-\n", 1)[1].split())
        for state in ("ready", "completed", "not-selected", ""):
            for matrix in ('{"include":[{}]}', '{"include":[]}'):
                for recovery in ("exact original locator", ""):
                    for authorized in (True, False):
                        values = {
                            "inputs.sdkRecoveryOnly": True,
                            "inputs.runtimeAggregateRequalification": authorized,
                            "steps.captured.outputs.aggregate_state": state,
                            "steps.captured.outputs.native_attestation_matrix": matrix,
                            "inputs.runtimeNativeHandoffRecovery": recovery,
                        }
                        condition = expression
                        for name, value in values.items():
                            condition = condition.replace(name, repr(value))
                        condition = re.sub(r"!(?!=)", "not ", condition).replace("&&", "and").replace("||", "or")
                        with self.subTest(**values):
                            self.assertEqual(authorized and state in ("ready", "completed")
                                             and matrix != '{"include":[]}' and bool(recovery),
                                             eval(condition, {"__builtins__": {}}))
        self.assertIn("--selected-receipts-json", self.job)
        self.assertIn("steps.retained.outputs.native_attestation_matrix", self.job)

    def test_aggregate_executes_only_after_election_and_collects_even_failed_metadata(self):
        aggregate = workflow_job(self.workflow, "runtime-aggregate")
        collector = workflow_job(self.workflow, "runtime-collect-5")
        for value in ("name: runtime-runtime-aggregate-metadata-aggregate",
                      "needs.runtime-continuation.outputs.aggregate_required == 'true'",
                      "needs.runtime-native-attestation.result == 'success'",
                      "needs.plan.outputs.remote_build_authorized == 'true'",
                      "component: runtime-aggregate", "phase: metadata", "target: aggregate",
                      "build-key: ${{ needs.runtime-continuation.outputs.aggregate_key }}"):
            self.assertIn(value, aggregate)
        self.assertLess(aggregate.index("./.github/actions/capture-runtime-state"),
                        aggregate.index("./.github/actions/setup-kmp"))
        self.assertLess(aggregate.index("ci/runtime_workflow.py variant-trust"),
                        aggregate.index("./.github/actions/setup-kmp"))
        self.assertIn("merge-multiple: false", aggregate)
        self.assertIn("for target in macos-arm64 macos-x64 linux-arm64 linux-x64 windows-x64", aggregate)
        self.assertIn("ci/product_reuse.py execute-runtime-aggregate", aggregate)
        self.assertIn("--variant-trust-root build/runtime-variant-trust", aggregate)
        self.assertIn("codex-agent-runtime-worker-runtime-aggregate-metadata-aggregate-${{ steps.identity.outputs.key_hex }}", aggregate)
        self.assertIn("path: build/runtime-aggregate-worker", aggregate)
        self.assertEqual(["REUSE_AUTHORITY_READ_TOKEN"], re.findall(r"secrets\.([A-Z_]+)", aggregate))
        self.assertNotRegex(aggregate.replace("secrets.REUSE_AUTHORITY_READ_TOKEN", ""),
                            r"secrets\.|PRIVATE_KEY|runtime_release.py|ssh-keygen")
        self.assertIn("always()", collector)
        self.assertIn("needs: [plan, runtime-continuation, runtime-aggregate, contract-validation]", collector)
        self.assertNotIn("needs.runtime-aggregate.result == 'success'", collector)
        self.assertIn("wave: '5'", collector)
        for forwarding in ("artifact-id: ${{ needs.runtime-continuation.outputs.artifact_id }}",
                           "artifact-sha256: ${{ needs.runtime-continuation.outputs.artifact_digest }}",
                           "state-wave: ${{ needs.runtime-continuation.outputs.state_wave }}"):
            self.assertIn(forwarding, aggregate)
            self.assertIn(forwarding, collector)
        self.assertIn("runtime-aggregate, runtime-collect-5", self.gate)
        self.assertIn("needs.runtime-collect-5.outputs.wave_failed", self.gate)
        full_reuse = self.gate.split('PRODUCT_FULL_REUSE: ', 1)[1].split('\n', 1)[0]
        self.assertEqual('${{ needs.sdk-completion.outputs.full_reuse }}', full_reuse)

    @classmethod
    def setUpClass(cls):
        cls.workflow = (ROOT / ".github/workflows/product-validation.yml").read_text(encoding="utf-8")
        cls.job = workflow_job(cls.workflow, "runtime-continuation")
        cls.gate = workflow_job(cls.workflow, "merge-gate")
        matches = re.findall(r"^          python3 - <<'PY'\n(.*?)^          PY$", cls.job,
                             re.MULTILINE | re.DOTALL)
        if len(matches) != 1:
            raise AssertionError("Expected the sole original Runtime parent-selector heredoc")
        cls.selector = textwrap.dedent(matches[0])
        cls.selector = 'import sys; sys.path.insert(0, ' + repr(str(Path(__file__).resolve().parents[2])) + ')\n' + cls.selector

    def predecessors(self, successful=()):
        values = {"plan": {"result": "success", "outputs": {}}}
        for wave in range(5):
            name = "product-resume" if wave == 0 else f"runtime-collect-{wave}"
            values[name] = {"result": "success" if wave == 0 or wave in successful else "skipped",
                            "outputs": {"artifact_id": str(700 + wave),
                                        "artifact_digest": "sha256:" + str(wave + 1) * 64,
                                        "wave_failed": "false"}}
            if wave:
                values[f"runtime-workers-{wave}"] = {"result": "success" if wave in successful else "skipped",
                                                     "outputs": {}}
        return values

    def select(self, predecessors, *, expected_wave=None, sentinel=b""):
        with tempfile.TemporaryDirectory(prefix="runtime-selector-") as temporary:
            output = Path(temporary) / "github-output"
            if sentinel:
                output.write_bytes(sentinel)
            environment = {key: value for key, value in os.environ.items() if key in {"SYSTEMROOT", "WINDIR"}}
            environment.update(PREDECESSORS=json.dumps(predecessors), GITHUB_OUTPUT=str(output))
            result = subprocess.run([sys.executable, "-I", "-B", "-c", self.selector],
                                    cwd=temporary, env=environment, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, check=False)
            if expected_wave is None:
                self.assertNotEqual(0, result.returncode)
                self.assertEqual(sentinel, output.read_bytes() if output.exists() else b"")
                if not sentinel:
                    self.assertFalse(output.exists(), "Rejected parent selection must not emit partial outputs")
                return
            self.assertEqual(0, result.returncode, result.stderr.decode(errors="replace"))
            selected = "product-resume" if expected_wave == 0 else f"runtime-collect-{expected_wave}"
            original = predecessors[selected]["outputs"]
            self.assertEqual({"state_wave": str(expected_wave), "sdk_state_wave": "", "artifact_id": original["artifact_id"],
                              "artifact_digest": original["artifact_digest"]},
                             dict(line.split("=", 1) for line in output.read_text().splitlines()))

    def test_reused_wave_zero_selects_original_resume_without_worker_outputs(self):
        predecessors = self.predecessors()
        predecessors["product-resume"]["outputs"]["full_reuse"] = "true"
        for wave in range(1, 5):
            predecessors[f"runtime-collect-{wave}"]["outputs"] = {}
        self.select(predecessors, expected_wave=0)
        resume = workflow_job(self.workflow, "product-resume")
        self.assertRegex(resume, r"(?m)^      wave_failed: 'false'$")

    def test_latest_successful_wave_one_through_four_wins_over_skips(self):
        for last in range(1, 5):
            for successful in (tuple(range(1, last + 1)), (last,)):
                with self.subTest(last=last, successful=successful):
                    predecessors = self.predecessors(successful)
                    for wave in range(last + 1, 5):
                        predecessors[f"runtime-collect-{wave}"]["outputs"] = {}
                    self.select(predecessors, expected_wave=last)

    def test_failed_cancelled_missing_and_incomplete_parents_never_emit_outputs(self):
        for wave in range(5):
            name = "product-resume" if wave == 0 else f"runtime-collect-{wave}"
            for status in ("failure", "cancelled", "", "in_progress"):
                with self.subTest(wave=wave, status=status):
                    predecessors = self.predecessors((1, 2, 3, 4))
                    predecessors[name]["result"] = status
                    self.select(predecessors)
            predecessors = self.predecessors((1, 2, 3, 4))
            del predecessors[name]
            with self.subTest(wave=wave, missing=True):
                self.select(predecessors)
        predecessors = self.predecessors()
        predecessors["product-resume"]["result"] = "skipped"
        self.select(predecessors)

    def test_unqualified_uploads_and_failed_wave_flags_reject_before_any_output(self):
        good = self.predecessors((1, 2, 3, 4))
        for wave in (0, 2, 4):
            name = "product-resume" if wave == 0 else f"runtime-collect-{wave}"
            for field, value in (("artifact_id", ""), ("artifact_id", "0"), ("artifact_id", "007"),
                                 ("artifact_digest", ""), ("artifact_digest", "a" * 64),
                                 ("artifact_digest", "sha256:" + "A" * 64),
                                 ("wave_failed", "true"), ("wave_failed", ""), ("wave_failed", True)):
                with self.subTest(wave=wave, field=field, value=value):
                    predecessors = deepcopy(good)
                    predecessors[name]["outputs"][field] = value
                    self.select(predecessors)
            for field in ("artifact_digest", "artifact_id", "wave_failed"):
                predecessors = deepcopy(good)
                del predecessors[name]["outputs"][field]
                with self.subTest(wave=wave, missing=field):
                    self.select(predecessors, sentinel=b"unrelated=preserved\n")

    def test_authorization_precedes_runner_and_all_workers_collectors_are_dependencies(self):
        condition = re.search(r"^    if: (?P<body>.*?)(?=^    [a-z][a-z-]*:)", self.job,
                              re.MULTILINE | re.DOTALL)
        self.assertIsNotNone(condition)
        for guard in ("always()", "needs.plan.outputs.event_authorized == 'true'",
                      "needs.plan.outputs.remote_build_authorized == 'true'",
                      "needs.product-resume.result == 'success'",
                      "!contains(needs.*.result, 'failure')", "!contains(needs.*.result, 'cancelled')"):
            self.assertIn(guard, condition.group("body"))
        self.assertLess(condition.start(), self.job.index("    runs-on:"))
        needs = re.search(r"(?m)^    needs: \[(.*?)\]$", self.job)
        self.assertIsNotNone(needs)
        self.assertEqual({"plan", "product-resume", "contract-validation", *(f"runtime-workers-{wave}" for wave in range(1, 5)),
                          *(f"runtime-collect-{wave}" for wave in range(1, 5))},
                         {name.strip() for name in needs.group(1).split(",")})

    def test_capture_precedes_full_replay_without_setup_signing_or_product_build(self):
        self.assertIn("if: inputs.sdkRecoveryOnly != true || inputs.runtimeAggregateRequalification\n        uses: ./.github/actions/capture-runtime-state", self.job)
        self.assertIn("if: inputs.sdkRecoveryOnly && !inputs.runtimeAggregateRequalification\n        uses: ./.github/actions/capture-runtime-state/route", self.job)
        self.assertLess(self.job.index("id: parent"), self.job.index("id: captured"))
        for forwarding in ("artifact-id: ${{ steps.parent.outputs.artifact_id }}",
                           "artifact-sha256: ${{ steps.parent.outputs.artifact_digest }}",
                           "state-wave: ${{ steps.parent.outputs.state_wave }}",
                           "trusted-workflow-sha: ${{ needs.plan.outputs.publisher_sha }}",
                           "routing: ${{ steps.parent.outputs.routing }}",
                           "continuation: selected"):
            self.assertIn(forwarding, self.job)
        self.assertNotRegex(self.job, r"PRIVATE_KEY|ssh-keygen|actions/setup-|actions/cache|\.github/actions/setup-")
        self.assertNotRegex(self.job, r"(?:\./gradlew|\bcargo\s+(?:build|test)|\bcmake\s|\bxcodebuild\b|\bnpm\s+(?:ci|install|run)|\bpip\s+install)")
        needs = re.search(r"(?m)^    needs: \[(.*?)\]$", self.gate)
        self.assertIsNotNone(needs)
        self.assertIn("runtime-continuation", {name.strip() for name in needs.group(1).split(",")})
        self.assertIn("RESULTS: ${{ join(needs.*.result, ' ') }}", self.gate)


if __name__ == "__main__":
    unittest.main()
