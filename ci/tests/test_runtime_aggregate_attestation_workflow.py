"""Execute local workflow shell routing, never signing or hosted jobs."""

import os
from pathlib import Path
import re
import subprocess
import unittest

from ci.tests.test_contract_attestation_workflow import workflow_job


ROOT = Path(__file__).resolve().parents[2]
PIN = "994ff55a2eae12fbc39025bfef7b45aeb5c16bd9"


def shell(step):
    return "\n".join(line[10:] for line in step.split("        run: |\n", 1)[1].splitlines())


class RuntimeAggregateAttestationWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / ".github/workflows/product-validation.yml").read_text()
        cls.job = workflow_job(cls.source, "runtime-aggregate-attestation")
        cls.steps = re.split(r"(?=^      - )", cls.job, flags=re.MULTILINE)
        cls.signing_step, = [step for step in cls.steps if "secrets." in step]
        cls.gate = workflow_job(cls.source, "merge-gate")

    def test_authorized_completed_state_and_pinned_code_precede_signing(self):
        guards = self.job.split("    runs-on:", 1)[0]
        for guard in ("always()", "needs.plan.outputs.event_authorized == 'true'",
                      "needs.plan.outputs.remote_build_authorized == 'true'",
                      "github.event_name != 'workflow_dispatch'",
                      "needs.runtime-aggregate-continuation.result == 'success'",
                      "needs.runtime-aggregate-continuation.outputs.aggregate_payload_complete == 'true'",
                      "!contains(needs.*.result, 'failure')", "!contains(needs.*.result, 'cancelled')"):
            self.assertIn(guard, guards)
        self.assertIn("environment: product-attestation", self.job)
        self.assertEqual(2, self.job.count("uses: actions/checkout@"))
        self.assertEqual(2, self.job.count("persist-credentials: false"))
        for setting in (f"ref: {PIN}", f"TRUSTED_SOURCE_SHA: {PIN}", "path: trusted-source",
                        "path: candidate-source", "fetch-depth: 0"):
            self.assertIn(setting, self.job)
        self.assertNotRegex(self.job, r"uses: (?:\./|actions/setup-|actions/cache)")
        self.assertNotRegex(self.job, r"(?:\./gradlew|\bcargo\s|\bcmake\s|\bxcodebuild\b|\bpip\s|\bnpm\s)")
        pinned = subprocess.run(["git", "show", f"{PIN}:ci/runtime_aggregate_release.py"], cwd=ROOT,
                                check=True, capture_output=True, text=True).stdout
        self.assertIn("def attest_runtime_aggregate_state_ci(", pinned)
        self.assertIn("materialize_runtime_aggregate_release_evidence(", pinned)
        for field in ("artifact_id", "artifact_digest", "state_wave", "aggregate_key"):
            self.assertIn(f"needs.runtime-aggregate-continuation.outputs.{field}", self.signing_step)
        self.assertIn("artifact-ids: ${{ needs.plan.outputs.plan_id }}", self.job)
        for setting in ("overwrite: false", "if-no-files-found: error", "include-hidden-files: true",
                        "artifact_id: ${{ steps.upload.outputs.artifact-id }}",
                        "artifact_digest: sha256:${{ steps.upload.outputs.artifact-digest }}"):
            self.assertIn(setting, self.job)

    def test_shell_forwards_five_exact_handoffs_or_leaves_retained_selection_to_existing_gate(self):
        environment = {**os.environ, "GITHUB_WORKSPACE": "/candidate workspace", "RUNNER_TEMP": "/runner temp",
            "GITHUB_RUN_ATTEMPT": "2", "VALIDATION_TREE": "d" * 40, "TRUSTED_SOURCE_SHA": PIN,
            "TRUSTED_WORKFLOW_SHA": "e" * 40, "ARTIFACT_ID": "71", "ARTIFACT_SHA256": "sha256:" + "a" * 64,
            "STATE_WAVE": "5", "BUILD_KEY": "sha256:" + "b" * 64,
            "PREPARATION_ID": "72", "PREPARATION_SHA256": "sha256:" + "f" * 64}
        # The shell runs, but the only Python invocation is replaced before it can execute any code.
        script = 'python3() { printf "%s\\n" "$@"; }\n' + shell(self.signing_step)
        for result, count in (("success", 5), ("skipped", 0), ("failure", None), ("cancelled", None), ("", None)):
            with self.subTest(result=result):
                run = subprocess.run(["bash", "-c", script], env={**environment, "NATIVE_RESULT": result},
                                     capture_output=True, text=True)
                if count is None:
                    self.assertNotEqual(0, run.returncode)
                    self.assertEqual("", run.stdout)
                    continue
                self.assertEqual(0, run.returncode, run.stderr)
                arguments = run.stdout.splitlines()
                self.assertEqual(count, arguments.count("--variant-handoff"))
                self.assertEqual("aggregate", arguments[arguments.index("--target") + 1])
                self.assertEqual("5", arguments[arguments.index("--state-wave") + 1])
                self.assertEqual("72", arguments[arguments.index("--preparation-artifact-id") + 1])
                self.assertEqual("sha256:" + "f" * 64,
                                 arguments[arguments.index("--preparation-artifact-sha256") + 1])
                self.assertEqual("/candidate workspace/trusted-source", arguments[arguments.index("--repository-root") + 1])
                if count:
                    for target in ("macos-arm64", "macos-x64", "linux-arm64", "linux-x64", "windows-x64"):
                        self.assertIn(f"{target}=/runner temp/runtime-aggregate-native-handoffs/"
                            f"codex-agent-runtime-release-handoff-{target}-{'d' * 40}-attempt-2/runtime-input", arguments)

    def test_merge_gate_rejects_missing_or_failed_selected_aggregate_trust(self):
        self.assertIn("runtime-aggregate-attestation", self.gate.split("    runs-on:", 1)[0])
        step = re.split(r"(?=^      - )", self.gate, flags=re.MULTILINE)[1]
        environment = {**os.environ, "EVENT_AUTHORIZED": "true", "REMOTE_BUILD_AUTHORIZED": "true",
            "MERGE_READY": "true", "RESULTS": "success skipped", "CONTRACT_COMPLETE": "false",
            "AGGREGATE_STATE": "completed", "AGGREGATE_PAYLOAD_COMPLETE": "true",
            "AGGREGATE_ATTESTATION_RESULT": "success", "AGGREGATE_ATTESTATION_ARTIFACT_ID": "71",
            "AGGREGATE_ATTESTATION_ARTIFACT_DIGEST": "sha256:" + "c" * 64}
        for changes, success in (({}, True), ({"AGGREGATE_ATTESTATION_RESULT": "skipped"}, False),
                ({"AGGREGATE_ATTESTATION_RESULT": "failure"}, False), ({"AGGREGATE_PAYLOAD_COMPLETE": "false"}, False),
                ({"AGGREGATE_ATTESTATION_ARTIFACT_ID": ""}, False),
                ({"AGGREGATE_ATTESTATION_ARTIFACT_DIGEST": "bad"}, False),
                ({"AGGREGATE_STATE": "not-selected", "AGGREGATE_ATTESTATION_RESULT": "skipped"}, True)):
            with self.subTest(changes=changes):
                result = subprocess.run(["bash", "-c", shell(step)], env={**environment, **changes},
                                        capture_output=True, text=True)
                self.assertEqual(success, result.returncode == 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
