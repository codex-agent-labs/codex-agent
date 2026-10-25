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
    "sdk-core-package-wave", "sdk-core-validation-wave", "sdk-core-metadata-wave",
    "sdk-android-binary-result", "sdk-android-package-result", "sdk-android-validation-result",
    "sdk-android-metadata-result",
}


class SdkCompletionWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.source = (ROOT / ".github/workflows/product-validation.yml").read_text()

    def job(self, name):
        match = re.search(rf"(?ms)^  {re.escape(name)}:\n.*?(?=^  [a-z][a-z0-9-]*:|\Z)", self.source)
        self.assertIsNotNone(match, "Missing saved workflow job: " + name)
        return match[0]

    def test_javascript_workers_allow_authenticated_recovery_before_execution(self):
        # Genuine capture exceeded 60 minutes before reaching the key gate.
        # Both callers need time for recovery, input verification and upload.
        for name in ("sdk-workers-1", "sdk-workers-2", "sdk-csharp-binary",
                     "sdk-native-prepare", "sdk-native-workers", "sdk-ios-package",
                     "sdk-javascript-metadata", "sdk-native-validation", "sdk-native-metadata",
                     "sdk-ios-validation", "sdk-apple-signing-prepare", "sdk-ios-metadata"):
            with self.subTest(job=name):
                job = self.job(name)
                self.assertRegex(job, r"(?m)^    timeout-minutes: 180$")
                if name in ("sdk-workers-1", "sdk-workers-2"):
                    self.assertIn("uses: ./.github/actions/sdk-javascript-worker", job)
                    self.assertIn("build-key: ${{ matrix.buildKey }}", job)

    def test_sdk_workers_and_catalog_ignore_skipped_ancestors_not_failed_inputs(self):
        # Exercise the saved conjunctions, not GitHub's scheduler. Optional iOS
        # ancestors may be skipped on reuse; actual inputs must all succeed.
        for name in ("sdk-workers-1", "sdk-workers-2", "sdk-catalog"):
            job = self.job(name)
            condition = re.search(r"(?ms)^    if: >-\n(.*?)(?=^    \S)", job)[1]
            clauses = [value.strip() for value in condition.split("&&")]
            self.assertEqual(["always()", "!cancelled()"], clauses[:2])
            if name == "sdk-catalog":
                self.assertEqual("needs.plan.outputs.native_resume_full_reuse != 'true'", clauses.pop())
            comparisons = []
            for clause in clauses[2:]:
                comparison = re.fullmatch(r"([\w.-]+) == '([^']*)'", clause)
                self.assertIsNotNone(comparison, clause)
                comparisons.append(comparison.groups())
            expected = dict(comparisons)
            parents = re.search(r"needs: \[([^\]]+)\]", job)[1].split(", ")
            for parent in parents:
                self.assertEqual("success", expected[f"needs.{parent}.result"])
            for flag in ("event_authorized", "remote_build_authorized"):
                self.assertEqual("true", expected[f"needs.plan.outputs.{flag}"])
            if name == "sdk-catalog":
                self.assertEqual("true", expected["needs.sdk-completion.outputs.complete"])
                self.assertEqual("62", expected["needs.sdk-completion.outputs.phase_count"])
            else:
                selector = "sdk-plan" if name.endswith("1") else "sdk-collect-1"
                self.assertEqual("true", expected[f"needs.{selector}.outputs.sdk_workers_required"])
                if name.endswith("2"):
                    self.assertEqual("false", expected["needs.sdk-collect-1.outputs.wave_failed"])
            values = {**expected, "needs.sdk-collect-3.result": "skipped"}
            eligible = lambda: all(values[key] == value for key, value in comparisons)
            with self.subTest(job=name):
                self.assertTrue(eligible())
                for key in expected:
                    for rejected in ("", "failure", "cancelled", "skipped"):
                        values[key] = rejected
                        self.assertFalse(eligible(), (name, key, rejected))
                    values[key] = expected[key]

    @staticmethod
    def sdk_predecessors(source="released-default", aggregate_state="completed", binary=False):
        return {
            "product-resume": {"result": "success", "outputs": {"native_sdk_direct": "false"}},
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

    def test_native_full_reuse_skips_only_empty_continuations_with_existing_gates(self):
        guarded = (
            "sdk-ios-binary-plan", "runtime-continuation", "sdk-javascript-metadata-result",
            "sdk-csharp-binary-result", "sdk-native-packages", "sdk-ios-packages",
            "sdk-native-validation-result", "sdk-native-result", "sdk-ios-validation-result",
            "sdk-ios-metadata-result",
        )
        # Evaluate these saved conditions only, not a general Actions scheduler.
        def eligible(name, recovery=True, ready="true", full="true", authorization="true",
                     runtime_result="success"):
            job = self.job(name)
            parents = re.search(r"needs: \[([^\]]+)\]", job)[1].split(", ")
            values = {parent: {"result": "success", "outputs": {
                "event_authorized": authorization, "remote_build_authorized": authorization,
                "native_resume_ready": ready, "native_resume_full_reuse": full,
                "native_sdk_direct": "false", "ios_validation_direct": "false",
                "aggregate_state": "completed"}} for parent in parents}
            if "runtime-continuation" in values:
                values["runtime-continuation"]["result"] = runtime_result
            condition = re.search(r"(?ms)^    if: >-\n(.*?)(?=^    \S)", job)[1]
            condition = " ".join(condition.split())
            condition = condition.replace("always()", "True").replace("cancelled()", "False")
            condition = condition.replace("needs.*.result", repr([v["result"] for v in values.values()]))
            condition = re.sub(r"needs\.([a-z0-9-]+)\.(result|outputs\.[a-z0-9_]+)",
                lambda m: repr(values[m[1]]["result"] if m[2] == "result" else
                               values[m[1]]["outputs"].get(m[2].split(".")[1], "")), condition)
            condition = condition.replace("inputs.runtimeRecoveryOnly", "False")
            condition = condition.replace("inputs.sdkRecoveryOnly", repr(recovery))
            condition = re.sub(r"!(?!=)", " not ", condition).replace("&&", " and ").replace("||", " or ")
            return eval(condition.strip(), {"__builtins__": {}}, {"contains": lambda rows, value: value in rows})

        for name in guarded:
            self.assertIn("plan", re.search(r"needs: \[([^\]]+)\]", self.job(name))[1].split(", "))
            for recovery, ready, full in product((False, True), ("", "false", "true"), ("", "false", "true")):
                with self.subTest(job=name, recovery=recovery, ready=ready, full=full):
                    self.assertEqual(not (recovery and ready == full == "true"),
                                     eligible(name, recovery, ready, full))
                    self.assertFalse(eligible(name, recovery, ready, full, authorization="false"))
        for name in ("runtime-aggregate-continuation", "sdk-javascript"):
            with self.subTest(dependent=name):
                self.assertIn("needs.runtime-continuation.result == 'success'", self.job(name))
                self.assertFalse(eligible(name, runtime_result="skipped"))
                self.assertTrue(eligible(name, full="false"))
        # Resume remains the real successful transport boundary, not an invented
        # success for a skipped job. Completion still consumes the same needs.
        self.assertNotIn("!(inputs.sdkRecoveryOnly", self.job("product-resume"))
        self.assertIn("capture_planned_native_resume", self.job("product-resume"))
        self.assertIn("needs.product-resume.result == 'success'", self.job("sdk-completion"))

    def test_full_reuse_parent_shell_uses_real_selector_and_rejects_stale_or_failed_branches(self):
        job = self.job("sdk-completion")
        match = re.search(r"(?ms)^          python3 - <<'PY'\n(.*?)^          PY$", job)
        script = textwrap.dedent(match[1])
        locator = {"artifact_id": "91", "artifact_digest": "sha256:" + "a" * 64,
                   "state_wave": "0", "sdk_state_wave": ""}
        needs = {name: {"result": "skipped", "outputs": {}} for name in SELECTOR_JOBS}
        needs["product-resume"] = {"result": "success", "outputs": {
            **locator, "wave_failed": "false", "full_reuse": "true"}}
        cases = [(needs, True)]
        for field, value in (("full_reuse", "false"), ("full_reuse", ""), ("wave_failed", "true")):
            rejected = deepcopy(needs)
            rejected["product-resume"]["outputs"][field] = value
            cases.append((rejected, False))
        for name in SELECTOR_JOBS:
            for status in ("failure", "cancelled"):
                rejected = deepcopy(needs)
                rejected[name]["result"] = status
                cases.append((rejected, False))
            if name != "product-resume":
                rejected = deepcopy(needs)
                rejected[name]["outputs"] = dict(locator)
                cases.append((rejected, False))
        for number, (value, success) in enumerate(cases):
            before = deepcopy(value)
            with self.subTest(case=number), tempfile.TemporaryDirectory(prefix="sdk-full-reuse-parent-") as temporary:
                output = Path(temporary) / "output"
                environment = {name.upper().replace('-', '_'): json.dumps(v) for name, v in value.items()}
                with patch.dict(os.environ, {**environment, "GITHUB_OUTPUT": str(output)}, clear=True):
                    if success:
                        exec(compile(script, "saved-full-reuse-completion-parent", "exec"), {})
                        self.assertEqual(locator, dict(line.split("=", 1) for line in output.read_text().splitlines()))
                    else:
                        with self.assertRaises(ValueError):
                            exec(compile(script, "saved-full-reuse-completion-parent", "exec"), {})
                        self.assertFalse(output.exists())
            self.assertEqual(before, value)

    def test_tooling_is_job_local_from_contract_child_not_sdk_plan(self):
        job = self.job("sdk-completion")
        block = job.split("uses: ./.github/actions/capture-sdk-tooling", 1)[1].split("\n      - ", 1)[0]
        for flag, field in (("artifact-id", "artifact_id"), ("artifact-sha256", "artifact_sha256"),
                            ("transport-producer", "transport_producer")):
            self.assertIn(flag + ": ${{ needs.contract-validation.outputs.tooling_" + field + " }}", block)
        self.assertIn("policy-revision: ${{ needs.plan.outputs.validation_commit }}", block)
        self.assertIn("trusted-workflow-sha: ${{ needs.plan.outputs.publisher_sha }}", block)
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
        imported = re.search(r"from ([\w.]+) import [^\n]*\bselect_sdk_completion_state", script)
        self.assertIsNotNone(imported)
        selector_module = importlib.import_module(imported[1])
        self.assertIn("for name in _JOBS", script)
        needs = {name: {"result": "skipped", "outputs": {}} for name in SELECTOR_JOBS}
        locator = {"artifact_id": "91", "artifact_digest": "sha256:" + "a" * 64,
                   "state_wave": "0", "sdk_state_wave": "9"}
        for failure in (False, True):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory(prefix="sdk-completion-wiring-") as temporary:
                output = Path(temporary) / "output"
                environment = {name.upper().replace('-', '_'): json.dumps(value) for name, value in needs.items()}
                with patch.dict(os.environ, {**environment, "GITHUB_OUTPUT": str(output)}, clear=True), \
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
        outputs = job.split("    outputs:\n", 1)[1].split("    steps:\n", 1)[0]
        for name in ("artifact_id", "artifact_digest", "state_wave", "sdk_state_wave"):
            self.assertIn(name + ": ${{ steps.parent.outputs." + name + " }}", outputs)
            self.assertNotIn(name + ": ${{ steps.capture.outputs." + name + " }}", outputs)
        capture = job.split("      - id: capture\n", 1)[1].split("\n      - ", 1)[0]
        self.assertIn("uses: ./.github/actions/capture-runtime-state", capture)
        self.assertIn("product: sdk", capture)
        self.assertIn("plan-id: ${{ needs.plan.outputs.plan_id }}", capture)
        for flag, field in (("artifact-id", "artifact_id"), ("artifact-sha256", "artifact_digest"),
                            ("state-wave", "state_wave"), ("sdk-state-wave", "sdk_state_wave")):
            self.assertIn(flag + ": ${{ steps.parent.outputs." + field + " }}", capture)
        self.assertIn("sdk-validation-tooling: ${{ steps.tooling.outputs.tooling-policy }}", capture)
        self.assertIn("sdk-apple-validation-policy: ${{ steps.apple-policy.outputs.apple-policy }}", capture)
        self.assertIn("trusted-workflow-sha: ${{ needs.plan.outputs.publisher_sha }}", capture)
        completion = job.split("        id: completion\n", 1)[1]
        for name, output in (("PLAN", "plan-path"), ("DISCOVERY_ROOT", "discovery-root"), ("STATE_ROOT", "state-root")):
            self.assertIn(name + ": ${{ steps.capture.outputs." + output + " }}", completion)
        self.assertIn("SDK_VALIDATION_TOOLING: ${{ steps.tooling.outputs.tooling-policy }}", completion)
        self.assertIn("SDK_APPLE_VALIDATION_POLICY: ${{ steps.apple-policy.outputs.apple-policy }}", completion)
        self.assertIn("TRUSTED_WORKFLOW_SHA: ${{ needs.plan.outputs.publisher_sha }}", completion)
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
        self.assertIn("sdk-catalog", [name.strip() for name in needs[1].split(",")])
        self.assertIn("SDK_COMPLETION_RESULT: ${{ needs.sdk-completion.result }}", job)
        self.assertIn("SDK_COMPLETE: ${{ needs.sdk-completion.outputs.complete }}", job)
        self.assertIn("SDK_CATALOG_RESULT: ${{ needs.sdk-catalog.result }}", job)
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
                    "SDK_CATALOG_REQUIRED": "false", "SDK_CATALOG_RESULT": "skipped",
                    "AGGREGATE_STATE": "not-selected", "SDK_INPUTS_REQUIRED": "false", "CONTRACT_COMPLETE": "false"}
                process = subprocess.run(["bash", "-c", script], env=env, cwd=ROOT,
                                         capture_output=True, text=True)
                self.assertEqual(succeeds, process.returncode == 0, process.stderr)
        for catalog_result, succeeds in (("success", True), ("skipped", False), ("failure", False)):
            with self.subTest(catalog_result=catalog_result):
                env = {**os.environ, "EVENT_AUTHORIZED": "true", "REMOTE_BUILD_AUTHORIZED": "true",
                    "MERGE_READY": "true", "RESULTS": "success skipped", "TOOLING_MISS": "false",
                    "PRODUCT_RESUME_RESULT": "success", "SDK_COMPLETION_RESULT": "success",
                    "SDK_COMPLETE": "true", "SDK_CATALOG_REQUIRED": "true",
                    "SDK_CATALOG_RESULT": catalog_result, "AGGREGATE_STATE": "not-selected",
                    "SDK_CATALOG_NAME": "codex-agent-product-catalog-v1-pull-request-31-" + "a" * 40 + "-attempt-2",
                    "SDK_CATALOG_ID": "501", "SDK_CATALOG_DIGEST": "sha256:" + "b" * 64,
                    "SDK_CATALOG_KEY_SHA256": "sha256:" + "c" * 64,
                    "SDK_INPUTS_REQUIRED": "false", "CONTRACT_COMPLETE": "false"}
                process = subprocess.run(["bash", "-c", script], env=env, cwd=ROOT,
                                         capture_output=True, text=True)
                self.assertEqual(succeeds, process.returncode == 0, process.stderr)
                if catalog_result == "success":
                    env["SDK_CATALOG_KEY_SHA256"] = "not-a-digest"
                    bad = subprocess.run(["bash", "-c", script], env=env, cwd=ROOT,
                                         capture_output=True, text=True)
                    self.assertNotEqual(0, bad.returncode)

    def test_catalog_job_uses_completed_state_and_no_product_build(self):
        job = self.job("sdk-catalog")
        self.assertIn("github.event_name == 'pull_request'", job)
        self.assertIn("needs.sdk-completion.outputs.phase_count == '62'", job)
        self.assertIn("artifact-id: ${{ needs.sdk-completion.outputs.artifact_id }}", job)
        self.assertIn("artifact-sha256: ${{ needs.sdk-completion.outputs.artifact_digest }}", job)
        self.assertIn("python3 -B -m ci.sdk_campaign_catalog_caller", job)
        self.assertIn("--destination build/ci/sdk-catalog", job)
        self.assertIn("artifact_name: ${{ steps.identity.outputs.name }}", job)
        self.assertIn("artifact_id: ${{ steps.upload.outputs.artifact-id }}", job)
        self.assertIn("artifact_digest: sha256:${{ steps.upload.outputs.artifact-digest }}", job)
        self.assertIn("public_key_sha256: ${{ steps.catalog.outputs.publicKeySha256 }}", job)
        self.assertIn("name: ${{ steps.identity.outputs.name }}", job)
        self.assertNotIn("gradlew", job)
        script = textwrap.dedent(job.split("      - name: Assemble completed SDK same-PR cache catalog\n", 1)[1]
            .split("        run: |\n", 1)[1].split("\n      - id: identity", 1)[0])
        with tempfile.TemporaryDirectory(prefix="sdk-catalog-shell-") as temporary:
            root = Path(temporary)
            executable = root / "python3"
            executable.write_text(
                f"#!{sys.executable}\n"
                "import json, os, pathlib, sys\n"
                "pathlib.Path(os.environ['ARGV_CAPTURE']).write_text(json.dumps(sys.argv[1:]))\n")
            executable.chmod(0o755)
            arguments = root / "arguments.json"
            env = {**os.environ, "PATH": str(root) + os.pathsep + os.environ.get("PATH", ""),
                "PLAN": "/captured plan/impact-plan.json", "DISCOVERY_ROOT": "/captured discovery",
                "STATE_ROOT": "/captured state", "SDK_VALIDATION_TOOLING": "/tooling policy.json",
                "SDK_APPLE_VALIDATION_POLICY": "/apple policy.json", "TRUSTED_WORKFLOW_SHA": "c" * 40,
                "GITHUB_WORKSPACE": "/candidate repository", "GITHUB_TOKEN": "not-an-argument",
                "GITHUB_OUTPUT": str(root / "github-output"), "ARGV_CAPTURE": str(arguments)}
            process = subprocess.run(["bash", "-c", script], env=env, cwd=ROOT,
                                     capture_output=True, text=True)
            self.assertEqual(0, process.returncode, process.stderr)
            self.assertEqual(["-B", "-m", "ci.sdk_campaign_catalog_caller", "--plan", env["PLAN"],
                "--discovery-root", env["DISCOVERY_ROOT"], "--state-root", env["STATE_ROOT"],
                "--sdk-original-workflow-sha", env["TRUSTED_WORKFLOW_SHA"],
                "--repository-root", env["GITHUB_WORKSPACE"], "--destination", "build/ci/sdk-catalog",
                "--github-output", env["GITHUB_OUTPUT"],
                "--sdk-validation-tooling", env["SDK_VALIDATION_TOOLING"],
                "--sdk-apple-validation-policy", env["SDK_APPLE_VALIDATION_POLICY"]],
                json.loads(arguments.read_text()))
            identity = textwrap.dedent(job.split("      - id: identity\n", 1)[1]
                .split("        run: |\n", 1)[1].split("\n      - id: upload", 1)[0])
            name_output = root / "name-output"
            env.update({"PR": "31", "TREE": "a" * 40, "ATTEMPT": "2", "GITHUB_OUTPUT": str(name_output)})
            process = subprocess.run(["bash", "-c", identity], env=env, cwd=ROOT,
                                     capture_output=True, text=True)
            self.assertEqual(0, process.returncode, process.stderr)
            self.assertEqual("name=codex-agent-product-catalog-v1-pull-request-31-"
                + "a" * 40 + "-attempt-2\n", name_output.read_text())
            env["TREE"] = "not-a-tree"
            process = subprocess.run(["bash", "-c", identity], env=env, cwd=ROOT,
                                     capture_output=True, text=True)
            self.assertNotEqual(0, process.returncode)

    def test_catalog_is_unnecessary_only_for_authenticated_initial_full_reuse(self):
        guard = "needs.plan.outputs.native_resume_full_reuse != 'true'"
        header = self.job("sdk-catalog").split("    runs-on:", 1)[0]
        self.assertIn(guard, header)
        # Final completion is also true after new work: use the initial planner,
        # not final completion, to avoid suppressing a genuinely new catalog.
        self.assertNotIn("needs.sdk-completion.outputs.full_reuse", header)
        expression = re.search(r"(?m)^          SDK_CATALOG_REQUIRED: \$\{\{ (.+) \}\}$",
                               self.job("merge-gate"))[1]
        self.assertEqual("github.event_name == 'pull_request' && "
                         "needs.sdk-completion.outputs.phase_count == '62' && " + guard, expression)
        for event, count, reuse, required in (
                ("pull_request", "62", "true", False),
                ("pull_request", "62", "false", True),
                ("pull_request", "62", "", True),
                ("pull_request", "62", "unknown", True),
                ("push", "62", "false", False),
                ("pull_request", "61", "false", False)):
            with self.subTest(event=event, count=count, reuse=reuse):
                actual = expression.replace("github.event_name", repr(event)).replace(
                    "needs.sdk-completion.outputs.phase_count", repr(count)).replace(
                    "needs.plan.outputs.native_resume_full_reuse", repr(reuse)).replace("&&", "and")
                self.assertEqual(required, eval(actual, {"__builtins__": {}}))


    def parity_step(self, marker):
        source = (ROOT / ".github/workflows/sdk-binding-parity.yml").read_text()
        matches = [part for part in re.split(r"(?m)^      - ", source) if part.startswith(marker + "\n")]
        self.assertEqual(1, len(matches), marker)
        return matches[0]

    def test_hosted_parity_wiring_selects_only_explicit_complete_imported_reuse(self):
        source = (ROOT / ".github/workflows/sdk-binding-parity.yml").read_text()
        self.assertIn("reuseCompletedParity:\n        type: boolean\n        default: false", source)
        self.assertIn("sdk-parity: ${{ inputs.reuseCompletedParity }}", source)
        self.assertNotIn("parityPolicy:", source)
        for marker in ("id: tooling", "id: apple-policy", "id: capture"):
            self.assertIn("if: inputs.importedOnly\n", self.parity_step(marker))
        self.assertIn("if: inputs.importedOnly && !inputs.reuseCompletedParity",
                      self.parity_step("name: Verify full parity from authenticated immutable phases"))
        self.assertIn("if: inputs.importedOnly && inputs.reuseCompletedParity",
                      self.parity_step("name: Verify approved original parity against current native state"))
        self.assertIn("if: ${{ !inputs.reuseCompletedParity }}", self.parity_step("id: upload"))
        self.assertIn("plan-directory: ${{ runner.temp }}/sdk-parity-plan", self.parity_step("id: capture"))
        self.assertIn("path: ${{ runner.temp }}/sdk-parity-plan", source)
        parent_source = (ROOT / ".github/workflows/product-validation.yml").read_text()
        self.assertRegex(parent_source, r"reuseCompletedParity:\n        description: [^\n]+\n        type: boolean\n        default: false")
        caller = (ROOT / ".github/workflows/ci.yml").read_text()
        caller_selection = re.search(r"reuseCompletedParity: \$\{\{ (.*?) \}\}", caller)[1]
        for value in ("", "false", "true", "TRUE", "unknown"):
            # GitHub string comparisons ignore case; this evaluates only the saved Boolean selector.
            self.assertEqual(value.casefold() == "true", eval(caller_selection.replace("vars.CODEX_AGENT_REUSE_COMPLETED_SDK_PARITY", repr(value.casefold())), {"__builtins__": {}}))
        parent = self.job("sdk-parity")
        selection = re.search(r"reuseCompletedParity: \$\{\{ (.*?) \}\}", parent)[1]
        for opt_in, recovery, complete, count, full in product((False, True), (False, True), ("", "false", "true"), ("", "61", "62"), ("", "false", "true")):
            condition = selection.replace("inputs.reuseCompletedParity", repr(opt_in)).replace("inputs.sdkRecoveryOnly", repr(recovery))
            for field, value in (("complete", complete), ("phase_count", count), ("full_reuse", full)):
                condition = condition.replace("needs.sdk-completion.outputs." + field, repr(value))
            self.assertEqual(opt_in and recovery and complete == full == "true" and count == "62",
                             eval(condition.replace("&&", " and "), {"__builtins__": {}}))
        guard = textwrap.dedent(self.parity_step("name: Require imported complete state for original parity reuse").split("        run: |\n", 1)[1])
        correct = {"IMPORTED_ONLY": "true", "SDK_COMPLETE": "true", "SDK_PHASE_COUNT": "62", "SDK_FULL_REUSE": "true"}
        self.assertEqual(0, subprocess.run(["bash", "-c", guard], env=correct, capture_output=True).returncode)
        for key in correct:
            self.assertNotEqual(0, subprocess.run(["bash", "-c", guard], env={**correct, key: ""}, capture_output=True).returncode)
        merge = self.job("merge-gate")
        self.assertIn('[[ "$SDK_PARITY_ARTIFACT_RUN_ID" =~ ^[1-9][0-9]*$ ]] || exit 1', merge)
        download = merge.split("artifact-ids: ${{ needs.sdk-parity.outputs.artifact_id }}", 1)[1].split("\n      - ", 1)[0]
        self.assertIn("run-id: ${{ needs.sdk-parity.outputs.artifact_run_id }}", download)
        self.assertIn("github-token: ${{ github.token }}", download)
        self.assertIn("needs.sdk-completion.outputs.phase_count == '62'", parent)
        for gate in ("needs.plan.outputs.event_authorized == 'true'", "needs.plan.outputs.remote_build_authorized == 'true'",
                     "!contains(needs.*.result, 'failure')", "!contains(needs.*.result, 'cancelled')"):
            self.assertIn(gate, parent)

    def test_parity_output_keeps_original_run_and_rejects_invalid_reuse_without_fallback(self):
        step = self.parity_step("id: parity-output")
        script = textwrap.dedent(re.search(r"(?ms)^          python3 - <<'PY'\n(.*?)^          PY$", step)[1])
        report = {"result": "passed", "phaseCount": 112, "verificationContext": {
            "kind": "hosted-original-parity-reuse", "producer": {"runId": 200, "runAttempt": 2}},
            "sdkParity": {"artifactId": 71, "artifactSha256": "sha256:" + "a" * 64, "producer": {"runId": 100}}}
        cases = [("true", report, True), ("false", None, True)]
        for path, value in ((('result',), 'failed'), (('phaseCount',), 111),
                (('verificationContext', 'producer', 'runId'), 201),
                (('verificationContext', 'kind'), 'local'),
                (('sdkParity', 'artifactId'), True), (('sdkParity', 'artifactSha256'), 'bad'),
                (('sdkParity', 'producer', 'runId'), 0)):
            changed = deepcopy(report); cursor = changed
            for field in path[:-1]: cursor = cursor[field]
            cursor[path[-1]] = value; cases.append(('true', changed, False))
        cases.append(('unknown', report, False))
        for selected, value, accepted in cases:
            with self.subTest(selected=selected, report=value), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary); output = root / 'output'
                if value is not None:
                    (root / 'sdk-parity-reuse.log').write_text('throughput {"operation":"fixture"}\n' + json.dumps(value) + '\n')
                environment = {'RUNNER_TEMP': temporary, 'GITHUB_OUTPUT': str(output), 'GITHUB_RUN_ID': '200',
                    'GITHUB_RUN_ATTEMPT': '2', 'REUSE_COMPLETED_PARITY': selected,
                    'FRESH_ARTIFACT_ID': '81', 'FRESH_ARTIFACT_SHA256': 'b' * 64}
                with patch.dict(os.environ, environment, clear=True):
                    if accepted:
                        exec(compile(script, 'saved-parity-output', 'exec'), {})
                        self.assertEqual({'artifact_id': '71' if selected == 'true' else '81',
                            'artifact_digest': 'sha256:' + ('a' if selected == 'true' else 'b') * 64,
                            'artifact_run_id': '100' if selected == 'true' else '200'},
                            dict(row.split('=', 1) for row in output.read_text().splitlines()))
                    else:
                        with self.assertRaises((ValueError, KeyError)):
                            exec(compile(script, 'saved-parity-output', 'exec'), {})
                        self.assertFalse(output.exists())

    def test_hosted_parity_shell_keeps_current_inputs_and_withholds_outputs_on_failure(self):
        verify = textwrap.dedent(self.parity_step('name: Verify approved original parity against current native state').split('        run: |\n', 1)[1])
        publish = textwrap.dedent(self.parity_step('id: parity-output').split('        run: |\n', 1)[1])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); binary = root / 'bin'; binary.mkdir()
            wrapper = binary / 'python3'
            wrapper.write_text('#!' + sys.executable + '\nimport json,os,sys\n'
                'if sys.argv[1:] == ["-"]: os.execv(sys.executable, [sys.executable, "-"])\n'
                'open(os.environ["ARGV"], "w").write(json.dumps(sys.argv[1:]))\n'
                'print("throughput fixture")\n'
                'if os.environ["FAIL"] == "true": raise SystemExit(7)\n'
                'print(json.dumps({"result":"passed","phaseCount":112,"verificationContext":'
                '{"kind":"hosted-original-parity-reuse","producer":{"runId":200,"runAttempt":2}},'
                '"sdkParity":{"artifactId":71,"artifactSha256":"sha256:"+"a"*64,"producer":{"runId":100}}}))\n')
            wrapper.chmod(0o700)
            for failure, missing_policy in ((False, False), (True, False), (False, True)):
                with self.subTest(failure=failure, missing_policy=missing_policy):
                    work = root / f'{failure}-{missing_policy}'; work.mkdir(); output = work / 'output'; argv = work / 'argv'
                    environment = {**os.environ, 'PATH': str(binary) + os.pathsep + os.environ['PATH'],
                        'RUNNER_TEMP': str(work), 'GITHUB_WORKSPACE': str(root), 'GITHUB_OUTPUT': str(output),
                        'GITHUB_RUN_ID': '200', 'GITHUB_RUN_ATTEMPT': '2', 'REUSE_COMPLETED_PARITY': 'true',
                        'PLAN': '/fixture/plan', 'DISCOVERY_ROOT': '/fixture/discovery', 'STATE_ROOT': '/fixture/state',
                        'SDK_VALIDATION_TOOLING': '/fixture/tooling', 'SDK_APPLE_VALIDATION_POLICY': '/fixture/apple',
                        'TRUSTED_WORKFLOW_SHA': 'c' * 40, 'CODEX_AGENT_COMPLETED_REUSE_POLICY': '/protected/native',
                        'CODEX_AGENT_COMPLETED_SDK_PARITY_POLICY': '' if missing_policy else '/protected/parity',
                        'FAIL': str(failure).lower(), 'ARGV': str(argv)}
                    result = subprocess.run(['bash', '-c', verify + '\n' + publish], env=environment, capture_output=True, text=True)
                    if failure or missing_policy:
                        self.assertNotEqual(0, result.returncode); self.assertFalse(output.exists())
                        if missing_policy: self.assertFalse(argv.exists())
                    else:
                        self.assertEqual(0, result.returncode, result.stderr)
                        self.assertEqual(['-B', '-m', 'ci.sdk_completion', '--hosted-parity', '--plan', '/fixture/plan',
                            '--discovery-root', '/fixture/discovery', '--state-root', '/fixture/state',
                            '--sdk-original-workflow-sha', 'c' * 40, '--sdk-validation-tooling', '/fixture/tooling',
                            '--sdk-apple-validation-policy', '/fixture/apple', '--repository-root', str(root),
                            '--completed-frozen-policy', '/protected/native', '--parity-policy', '/protected/parity'],
                            json.loads(argv.read_text()))
                        self.assertIn('artifact_run_id=100\n', output.read_text())


if __name__ == "__main__":
    unittest.main()
