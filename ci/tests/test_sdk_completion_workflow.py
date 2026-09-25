"""Saved completion-job wiring, not hosted execution or product admission.

The workflow's selector call is executed with an explicit routing mock. Actual
state/source authentication remains covered by the completion and replay suites.
"""

import importlib
from itertools import product
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
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SELECTOR_JOBS = {
    "product-resume", "runtime-continuation", "runtime-aggregate-continuation",
    "sdk-ios-binary-plan", "sdk-ios-binary", "sdk-collect-3", "sdk-plan", "sdk-native-result",
    "sdk-ios-validation-result", "sdk-ios-metadata-result", "sdk-core-binary-wave",
    "sdk-core-package-wave", "sdk-core-validation-result", "sdk-core-metadata-result",
}


class SdkCompletionWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.source = (ROOT / ".github/workflows/product-validation.yml").read_text()

    def job(self, name):
        match = re.search(rf"(?ms)^  {re.escape(name)}:\n.*?(?=^  [a-z][a-z0-9-]*:|\Z)", self.source)
        self.assertIsNotNone(match, "Missing saved workflow job: " + name)
        return match[0]

    @staticmethod
    def sdk_predecessors(source="released-default", aggregate_state="completed", binary=False):
        return {
            "runtime-continuation": {"result": "success", "outputs": {
                "artifact_id": "41", "artifact_digest": "sha256:" + "a" * 64, "state_wave": "4",
                "sdk_input_selection": json.dumps({"source": source}), "aggregate_state": aggregate_state}},
            "runtime-aggregate-continuation": {"result": "skipped" if aggregate_state == "not-selected" else "success",
                "outputs": {"artifact_id": "51", "artifact_digest": "sha256:" + "b" * 64, "state_wave": "5"}},
            "sdk-ios-binary-plan": {"result": "success", "outputs": {"sdk_workers_required": str(binary).lower()}},
            "sdk-ios-binary": {"result": "success" if binary else "skipped", "outputs": {}},
            "sdk-collect-3": {"result": "success" if binary else "skipped", "outputs": {
                "artifact_id": "61", "artifact_digest": "sha256:" + "c" * 64, "wave_failed": "false"}},
        }

    def sdk_parent(self, needs):
        parent = self.job("sdk-plan").split("      - id: parent\n", 1)[1].split("\n      - ", 1)[0]
        match = re.search(r"(?ms)^          python3 - <<'PY'\n(.*?)^          PY$", parent)
        self.assertIsNotNone(match)
        with tempfile.TemporaryDirectory(prefix="sdk-plan-parent-") as temporary:
            output = Path(temporary) / "output"
            with patch.dict(os.environ, {"PREDECESSORS": json.dumps(needs), "GITHUB_OUTPUT": str(output)}, clear=True):
                try:
                    exec(compile(textwrap.dedent(match[1]), "saved-sdk-plan-parent", "exec"), {})
                except Exception:
                    self.assertTrue(not output.exists() or output.read_bytes() == b"",
                                    "Rejected parent must not expose a partial state locator")
                    raise
            rows = [line.split("=", 1) for line in output.read_text().splitlines()]
            self.assertEqual(len(rows), len(dict(rows)))
            return dict(rows)

    def test_sdk_plan_preserves_latest_aggregate_for_both_runtime_sources(self):
        for source in ("current-runtime", "released-default"):
            for state in ("ready", "completed"):
                with self.subTest(source=source, state=state):
                    needs = self.sdk_predecessors(source, state)
                    self.assertEqual({**needs["runtime-aggregate-continuation"]["outputs"], "sdk_state_wave": ""},
                                     self.sdk_parent(needs))
        needs = self.sdk_predecessors(aggregate_state="not-selected")
        self.assertEqual({name: needs["runtime-continuation"]["outputs"][name]
                          for name in ("artifact_id", "artifact_digest", "state_wave")} | {"sdk_state_wave": ""},
                         self.sdk_parent(needs))

    def test_sdk_plan_retains_collected_ios_binary_precedence_without_losing_source_selection(self):
        for source, state in (("current-runtime", "ready"), ("current-runtime", "completed"),
                              ("released-default", "ready"), ("released-default", "completed"),
                              ("released-default", "not-selected")):
            with self.subTest(source=source, state=state):
                needs = self.sdk_predecessors(source, state, binary=True)
                self.assertEqual({"artifact_id": "61", "artifact_digest": "sha256:" + "c" * 64,
                                  "state_wave": "0", "sdk_state_wave": "3"}, self.sdk_parent(needs))

    def test_sdk_plan_rejects_invalid_or_failed_selected_parent_without_earlier_fallback(self):
        cases = [self.sdk_predecessors(source="unknown"), self.sdk_predecessors("current-runtime", "not-selected")]
        cases.extend(self.sdk_predecessors(aggregate_state=value) for value in ("", "complete", "failed", None))
        for source in ("current-runtime", "released-default"):
            for result in ("failure", "cancelled", "skipped"):
                needs = self.sdk_predecessors(source)
                needs["runtime-aggregate-continuation"]["result"] = result
                cases.append(needs)
            for field in ("artifact_id", "artifact_digest", "state_wave"):
                needs = self.sdk_predecessors(source)
                del needs["runtime-aggregate-continuation"]["outputs"][field]
                cases.append(needs)
        for field, value in (("wave_failed", "true"), ("wave_failed", ""), ("artifact_id", "")):
            needs = self.sdk_predecessors(binary=True)
            needs["sdk-collect-3"]["outputs"][field] = value
            cases.append(needs)
        needs = self.sdk_predecessors()
        needs["sdk-ios-binary-plan"]["outputs"] = {}
        cases.append(needs)
        for number, needs in enumerate(cases):
            before = deepcopy(needs)
            with self.subTest(case=number), self.assertRaises((ValueError, KeyError)):
                self.sdk_parent(needs)
            self.assertEqual(before, needs)

    def test_exact_dependencies_and_authorization_without_product_setup(self):
        job = self.job("sdk-completion")
        needs = re.search(r"(?m)^    needs: \[([^\]]+)\]$", job)
        self.assertIsNotNone(needs)
        names = [name.strip() for name in needs[1].split(",")]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(SELECTOR_JOBS | {"plan", "contract-validation"}, set(names))
        condition = job.split("    if:", 1)[1].split("    runs-on:", 1)[0]
        for expected in ("always()", "needs.plan.outputs.event_authorized == 'true'",
                         "needs.plan.outputs.remote_build_authorized == 'true'",
                         "needs.product-resume.result == 'success'"):
            self.assertIn(expected, condition)
        for forbidden in ("setup-kmp", "setup-java", "gradlew", "strategy:", "matrix:",
                          "PRIVATE_KEY", "attest-runtime", "finalize_phase"):
            self.assertNotIn(forbidden, job)
        self.assertIn("ref: ${{ needs.plan.outputs.validation_commit }}", job)

    def test_tooling_is_job_local_from_contract_child_not_sdk_plan(self):
        job = self.job("sdk-completion")
        block = job.split("uses: ./.github/actions/capture-sdk-tooling", 1)[1].split("\n      - ", 1)[0]
        for flag, field in (("artifact-id", "artifact_id"), ("artifact-sha256", "artifact_sha256"),
                            ("transport-producer", "transport_producer")):
            self.assertIn(flag + ": ${{ needs.contract-validation.outputs.tooling_" + field + " }}", block)
        self.assertIn("policy-revision: ${{ needs.plan.outputs.validation_commit }}", block)
        self.assertIn("trusted-workflow-sha: ${{ inputs.trustedWorkflowSha }}", block)
        self.assertIn("trusted-workflow-path: .github/workflows/contract-validation.yml", block)
        self.assertNotIn("needs.sdk-plan.outputs.tooling_", job)
        self.assertLess(job.index("select_sdk_completion_state"), job.index("./.github/actions/capture-sdk-tooling"))
        self.assertLess(job.index("./.github/actions/capture-sdk-tooling"), job.index("./.github/actions/capture-runtime-state"))

    def test_apple_policy_uses_original_plan_and_captured_tooling_only_when_required(self):
        job = self.job("sdk-completion")
        steps = re.split(r"\n      - ", job)
        download = next(step for step in steps if "uses: actions/download-artifact@" in step)
        policy = next(step for step in steps if "id: apple-policy\n" in step)
        tooling = next(step for step in steps if "id: tooling\n" in step)
        for step in (download, policy, tooling):
            self.assertIn("if: needs.plan.outputs.tooling_required == 'true'", step)
        self.assertIn("artifact-ids: ${{ needs.plan.outputs.plan_id }}", download)
        self.assertIn("path: ${{ runner.temp }}/sdk-apple-plan", download)
        self.assertIn("merge-multiple: true", download)
        self.assertIn("uses: ./.github/actions/prepare-sdk-apple-policy", policy)
        self.assertIn("plan-path: ${{ runner.temp }}/sdk-apple-plan/impact-plan.json", policy)
        self.assertIn("tooling-policy: ${{ steps.tooling.outputs.tooling-policy }}", policy)
        self.assertNotIn("needs.sdk-plan.outputs", policy)
        self.assertNotIn("steps.capture.outputs", policy)
        for earlier, later in ((tooling, download), (download, policy)):
            self.assertLess(job.index(earlier), job.index(later))
        self.assertLess(job.index(policy), job.index("uses: ./.github/actions/capture-runtime-state"))

    def test_parent_snippet_forwards_selector_tuple_and_never_outputs_on_failure(self):
        job = self.job("sdk-completion")
        match = re.search(r"(?ms)^          python3 - <<'PY'\n(.*?)^          PY$", job)
        self.assertIsNotNone(match)
        script = textwrap.dedent(match[1])
        imported = re.search(r"from ([\w.]+) import select_sdk_completion_state", script)
        self.assertIsNotNone(imported)
        selector_module = importlib.import_module(imported[1])
        environment_name = re.search(r"json.loads\(os.environ\[['\"]([^'\"]+)['\"]\]\)", script)
        self.assertIsNotNone(environment_name)
        needs = {name: {"result": "skipped", "outputs": {}} for name in SELECTOR_JOBS}
        locator = {"artifact_id": "91", "artifact_digest": "sha256:" + "a" * 64,
                   "state_wave": "0", "sdk_state_wave": "9"}
        for failure in (False, True):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory(prefix="sdk-completion-wiring-") as temporary:
                output = Path(temporary) / "output"
                with patch.dict(os.environ, {environment_name[1]: json.dumps(needs), "GITHUB_OUTPUT": str(output)}, clear=True), \
                        patch.object(selector_module, "select_sdk_completion_state", return_value=locator,
                                     side_effect=ValueError("synthetic routing failure") if failure else None) as select:
                    if failure:
                        with self.assertRaisesRegex(ValueError, "synthetic routing failure"):
                            exec(compile(script, "saved-sdk-completion-parent", "exec"), {})
                        self.assertFalse(output.exists())
                    else:
                        exec(compile(script, "saved-sdk-completion-parent", "exec"), {})
                        self.assertEqual(locator, dict(line.split("=", 1) for line in output.read_text().splitlines()))
                select.assert_called_once_with(needs)

    def test_capture_uses_only_selected_parent_and_completion_uses_captured_paths(self):
        job = self.job("sdk-completion")
        capture = job.split("      - id: capture\n", 1)[1].split("\n      - ", 1)[0]
        self.assertIn("uses: ./.github/actions/capture-runtime-state", capture)
        self.assertIn("product: sdk", capture)
        self.assertIn("plan-id: ${{ needs.plan.outputs.plan_id }}", capture)
        for flag, field in (("artifact-id", "artifact_id"), ("artifact-sha256", "artifact_digest"),
                            ("state-wave", "state_wave"), ("sdk-state-wave", "sdk_state_wave")):
            self.assertIn(flag + ": ${{ steps.parent.outputs." + field + " }}", capture)
        self.assertIn("sdk-validation-tooling: ${{ steps.tooling.outputs.tooling-policy }}", capture)
        self.assertIn("sdk-apple-validation-policy: ${{ steps.apple-policy.outputs.apple-policy }}", capture)
        self.assertIn("trusted-workflow-sha: ${{ inputs.trustedWorkflowSha }}", capture)
        completion = job.split("        id: completion\n", 1)[1]
        for name, output in (("PLAN", "plan-path"), ("DISCOVERY_ROOT", "discovery-root"), ("STATE_ROOT", "state-root")):
            self.assertIn(name + ": ${{ steps.capture.outputs." + output + " }}", completion)
        self.assertIn("SDK_VALIDATION_TOOLING: ${{ steps.tooling.outputs.tooling-policy }}", completion)
        self.assertIn("SDK_APPLE_VALIDATION_POLICY: ${{ steps.apple-policy.outputs.apple-policy }}", completion)
        self.assertIn("TRUSTED_WORKFLOW_SHA: ${{ inputs.trustedWorkflowSha }}", completion)
        self.assertIn("GITHUB_TOKEN: ${{ github.token }}", completion)
        for name, output in (("complete", "complete"), ("phase_count", "phaseCount"), ("full_reuse", "fullReuse")):
            self.assertIn(name + ": ${{ steps.completion.outputs." + output + " }}", job)

    def test_final_shell_invokes_only_fixed_completion_cli_with_optional_policy(self):
        block = self.job("sdk-completion").split("        id: completion\n", 1)[1]
        script = textwrap.dedent(block.split("        run: |\n", 1)[1])
        with tempfile.TemporaryDirectory(prefix="sdk-completion-shell-") as temporary:
            root = Path(temporary)
            executable = root / "python3"
            executable.write_text(
                f"#!{sys.executable}\n"
                "import json, os, pathlib, sys\n"
                "pathlib.Path(os.environ['ARGV_CAPTURE']).write_text(json.dumps(sys.argv[1:]))\n"
                "sys.exit(int(os.environ['MOCK_EXIT']))\n")
            executable.chmod(0o755)
            for policy, apple_policy in product(("", "/caller policy/tooling.json"),
                                                (None, "", "/caller policy/apple.json")):
                for status in (0, 7):
                    with self.subTest(policy=policy, apple_policy=apple_policy, status=status):
                        arguments = root / "arguments.json"
                        output = root / "output"
                        env = {**os.environ, "PATH": str(root) + os.pathsep + os.environ.get("PATH", ""),
                            "PLAN": "/captured plan/impact-plan.json", "DISCOVERY_ROOT": "/captured discovery",
                            "STATE_ROOT": "/captured state", "SDK_VALIDATION_TOOLING": policy,
                            "TRUSTED_WORKFLOW_SHA": "c" * 40,
                            "GITHUB_WORKSPACE": "/candidate repository", "GITHUB_OUTPUT": str(output),
                            "GITHUB_TOKEN": "not-a-command-argument", "ARGV_CAPTURE": str(arguments), "MOCK_EXIT": str(status)}
                        env.pop("SDK_APPLE_VALIDATION_POLICY", None)
                        if apple_policy is not None:
                            env["SDK_APPLE_VALIDATION_POLICY"] = apple_policy
                        process = subprocess.run(["bash", "-c", script], env=env, cwd=ROOT,
                                                 capture_output=True, text=True)
                        self.assertEqual(status, process.returncode, process.stderr)
                        expected = ["-B", "-m", "ci.sdk_completion", "--plan", env["PLAN"],
                            "--discovery-root", env["DISCOVERY_ROOT"], "--state-root", env["STATE_ROOT"],
                            "--sdk-original-workflow-sha", env["TRUSTED_WORKFLOW_SHA"],
                            "--repository-root", env["GITHUB_WORKSPACE"], "--github-output", str(output)]
                        if policy:
                            expected.extend(("--sdk-validation-tooling", policy))
                        if apple_policy:
                            expected.extend(("--sdk-apple-validation-policy", apple_policy))
                        self.assertEqual(expected, json.loads(arguments.read_text()))
                        self.assertFalse(output.exists(), "The wrapper must not manufacture completion output")

    def test_merge_requires_actual_final_completion_and_uses_no_earlier_full_reuse_fallback(self):
        job = self.job("merge-gate")
        needs = re.search(r"(?m)^    needs: \[([^\]]+)\]$", job)
        self.assertIn("sdk-completion", [name.strip() for name in needs[1].split(",")])
        self.assertIn("SDK_COMPLETION_RESULT: ${{ needs.sdk-completion.result }}", job)
        self.assertIn("SDK_COMPLETE: ${{ needs.sdk-completion.outputs.complete }}", job)
        full_reuse = re.search(r"(?m)^          PRODUCT_FULL_REUSE: (.+)$", job)
        self.assertEqual("${{ needs.sdk-completion.outputs.full_reuse }}", full_reuse[1])
        script = textwrap.dedent(job.split("        run: |\n", 1)[1].split("\n      - ", 1)[0])
        for resume, result, complete, succeeds in (
                ("success", "success", "true", True), ("success", "skipped", "true", False),
                ("success", "failure", "true", False), ("success", "success", "false", False),
                ("success", "success", "", False), ("skipped", "skipped", "", True)):
            with self.subTest(resume=resume, result=result, complete=complete):
                env = {**os.environ, "EVENT_AUTHORIZED": "true", "REMOTE_BUILD_AUTHORIZED": "true",
                    "MERGE_READY": "true", "RESULTS": "success skipped", "TOOLING_MISS": "false",
                    "PRODUCT_RESUME_RESULT": resume, "SDK_COMPLETION_RESULT": result, "SDK_COMPLETE": complete,
                    "AGGREGATE_STATE": "not-selected", "SDK_INPUTS_REQUIRED": "false", "CONTRACT_COMPLETE": "false"}
                process = subprocess.run(["bash", "-c", script], env=env, cwd=ROOT,
                                         capture_output=True, text=True)
                self.assertEqual(succeeds, process.returncode == 0, process.stderr)


if __name__ == "__main__":
    unittest.main()
