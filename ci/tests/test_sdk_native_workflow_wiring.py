"""Native workflow wiring and executed selectors, not hosted/package evidence."""

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

from ci import sdk_workflow  # Bootstrap the existing script-module namespace.
from ci import product_reuse, sdk_native_continuation
from ci.tests import test_sdk_native_continuation as selector_fixture


ROOT = Path(__file__).resolve().parents[2]


class SdkNativeWorkflowWiringTest(unittest.TestCase):
    def setUp(self):
        self.workflow = (ROOT / ".github/workflows/product-validation.yml").read_text()

    def test_package_inspection_forwards_existing_caller_workflow_pin(self):
        source = (ROOT / "ci/sdk_native_package_workflow.py").read_text()
        for entry in ("inspected = product_reuse.inspect_products(",
                      "ready = product_reuse.materialize_product_predecessors("):
            call = source.split(entry, 1)[1].split(")\n", 1)[0]
            self.assertIn("sdk_original_workflow_sha=trusted_workflow_sha", call)

    def job(self, name):
        return re.search(rf"(?ms)^  {re.escape(name)}:\n.*?(?=^  [a-z][a-z0-9-]*:|\Z)", self.workflow)[0]

    def snippet(self, job, environment):
        match = re.search(r"(?ms)^          python3 - <<'PY'\n(.*?)^          PY$", self.job(job))
        self.assertIsNotNone(match)
        with tempfile.TemporaryDirectory(prefix="sdk-native-wiring-") as temporary:
            output = Path(temporary) / "output"
            output.write_bytes(b"")
            with patch.dict(os.environ, {"TRUSTED_WORKFLOW_SHA": "c" * 40,
                    **environment, "GITHUB_OUTPUT": str(output)}, clear=True):
                try:
                    exec(compile(textwrap.dedent(match[1]), "native-workflow-fixture", "exec"), {})
                except Exception:
                    self.assertEqual(b"", output.read_bytes(), "Failed election must not expose preparation identity")
                    raise
            lines = [line.split("=", 1) for line in output.read_text().splitlines()]
            self.assertEqual(len(lines), len(dict(lines)))
            return dict(lines)

    @staticmethod
    def row(component, digest="a"):
        return {"product": "sdk", "component": component, "phase": "package", "target": "desktop",
            "buildKey": "sha256:" + digest * 64, "runner": "ubuntu-24.04", "runnerOs": "Linux", "runnerArch": "X64",
            "toolchainProfile": None, "producerRole": None, "supervisor": None}

    def summary(self, needs):
        with patch.object(sdk_native_continuation, "select_native_state",
                          wraps=sdk_native_continuation.select_native_state) as select:
            result = self.snippet("sdk-native-packages", {"RESULTS": json.dumps(needs)})
        select.assert_called_once_with(needs, stage="package")
        return result

    @staticmethod
    def needs():
        return {"sdk-javascript": {"result": "success", "outputs": {
                    "artifact_id": "71", "artifact_digest": "sha256:" + "d" * 64,
                    "state_wave": "0", "sdk_state_wave": "2"}},
                "sdk-native-plan": {"result": "success", "outputs": {"sdk_workers_required": "true", "preparation_required": "true"}},
                "sdk-native-prepare": {"result": "success", "outputs": {"artifact_id": "72"}},
                "sdk-native-workers": {"result": "success", "outputs": {}},
                "sdk-collect-4": {"result": "success", "outputs": {"wave_failed": "false",
                    "artifact_id": "73", "artifact_digest": "sha256:" + "e" * 64}}}

    def test_original_terminal_state_is_recaptured_before_one_preparation_and_parallel_packages(self):
        planned = self.job("sdk-native-plan")
        self.assertIn("needs.sdk-javascript.result == 'success'", planned)
        self.assertIn("needs.plan.outputs.event_authorized == 'true'", self.job("sdk-javascript"))
        self.assertIn("needs.plan.outputs.remote_build_authorized == 'true'", planned)
        self.assertLess(planned.index("./.github/actions/capture-runtime-state"), planned.index("- id: preparation"))
        self.assertIn("sdk-family: native-package", planned)
        self.assertNotIn("setup-kmp", planned)
        prepare = self.job("sdk-native-prepare")
        self.assertIn("name: sdk-native-prepare", prepare)
        self.assertNotIn("strategy:", prepare)
        self.assertNotIn("matrix:", prepare)
        self.assertEqual(1, prepare.count("uses: ./.github/actions/sdk-native-prepare"))
        self.assertIn("component: ${{ needs.sdk-native-plan.outputs.preparation_component }}", prepare)
        self.assertIn("build-key: ${{ needs.sdk-native-plan.outputs.preparation_build_key }}", prepare)
        self.assertIn("needs.sdk-native-plan.outputs.preparation_required == 'true'", prepare)
        for field in ("phase", "target"):
            self.assertIn("preparation-" + field + ": ${{ needs.sdk-native-plan.outputs.preparation_" + field + " }}", prepare)
        workers = self.job("sdk-native-workers")
        self.assertIn("name: sdk-${{ matrix.component }}-package-desktop", workers)
        self.assertIn("fail-fast: false", workers)
        self.assertIn("fromJSON(needs.sdk-native-plan.outputs.sdk_matrix", workers)
        self.assertIn("runs-on: ${{ matrix.runner }}", workers)
        self.assertIn("sdk-native-prepare", workers.split("    if:", 1)[0])
        self.assertIn("uses: ./.github/actions/sdk-native-package-worker", workers)
        self.assertNotIn("uses: ./.github/actions/sdk-native-prepare\n", workers)
        for job in (planned, prepare, workers, self.job("sdk-collect-4")):
            for flag, field in (("artifact-id", "artifact_id"), ("artifact-sha256", "artifact_digest"),
                                ("state-wave", "state_wave"), ("sdk-state-wave", "sdk_state_wave")):
                self.assertIn(flag + ": ${{ needs.sdk-javascript.outputs." + field + " }}", job)
        for flag, field in (("prepared-artifact-id", "artifact_id"), ("prepared-artifact-sha256", "artifact_digest"),
                            ("preparation-component", "preparation_component"), ("preparation-build-key", "preparation_build_key"),
                            ("preparation-state-id", "preparation_state_id"), ("preparation-state-sha256", "preparation_state_digest"),
                            ("preparation-state-wave", "preparation_state_wave"), ("preparation-sdk-state-wave", "preparation_sdk_state_wave")):
            self.assertIn(flag + ": ${{ needs.sdk-native-prepare.outputs." + field + " }}", workers)

    def test_collection_waits_for_failed_workers_and_final_gate_is_required(self):
        collector = self.job("sdk-collect-4")
        self.assertIn("sdk-native-workers]", collector)
        condition = collector.split("    if: >-\n", 1)[1].split("    runs-on:", 1)[0]
        self.assertIn("always()", condition)
        self.assertIn("needs.sdk-native-prepare.result == 'success'", condition)
        self.assertIn("needs.sdk-native-plan.outputs.sdk_workers_required == 'true'", condition)
        self.assertNotIn("needs.sdk-native-workers.result", condition)
        self.assertIn("uses: ./.github/actions/collect-runtime-wave", collector)
        self.assertIn("sdk-family: native-package", collector)
        self.assertIn("wave: '4'", collector)
        summary = self.job("sdk-native-packages")
        self.assertIn("always()", summary)
        for name in ("sdk-javascript", "sdk-native-plan", "sdk-native-prepare", "sdk-native-workers", "sdk-collect-4"):
            self.assertIn(name, summary.split("    runs-on:", 1)[0])
        gate = self.job("merge-gate").split("    runs-on:", 1)[0]
        self.assertIn("sdk-native-packages", gate)

    def test_preparation_passes_full_ready_plans_and_caller_policy_to_existing_selector(self):
        # Selector semantics have dedicated real-plan tests; these are explicit
        # inspection/selector seams proving the workflow never forges a package.
        rows = [{"synthetic": "unchanged authenticated ready-plan boundary"}]
        for phase, target in (("package", "desktop"), ("validation", "macos-arm64"), ("metadata", "desktop")):
            selected = dict(preparation_required=True, component="rust", phase=phase, target=target, build_key="sha256:" + "a" * 64)
            policy = {"synthetic": "caller-owned policy boundary"}
            with self.subTest(phase=phase), patch.object(product_reuse, "inspect_products", return_value={"readyPlans": rows}) as inspect, \
                    patch.object(product_reuse, "_canonical_control", return_value=policy), \
                    patch.object(sdk_native_continuation, "select_preparation_anchor", return_value=selected) as select:
                output = self.snippet("sdk-native-plan", {"PLAN": "/original/plan", "DISCOVERY": "/original/discovery",
                    "STATE": "/original/state", "SDK_VALIDATION_TOOLING": "/caller/policy"})
                select.assert_called_once_with(rows)
                self.assertIs(rows, select.call_args.args[0])
                self.assertEqual((Path("/original/plan"), Path("/original/discovery"), Path("/original/state")), inspect.call_args.args)
                self.assertIs(policy, inspect.call_args.kwargs["sdk_validation_tooling"])
                self.assertEqual({**selected, "preparation_required": "true"}, output)

    def test_selector_failure_and_noop_do_not_manufacture_preparation(self):
        environment = {"PLAN": "/plan", "DISCOVERY": "/discovery", "STATE": "/state", "SDK_VALIDATION_TOOLING": ""}
        empty = dict(preparation_required=False, component="", phase="", target="", build_key="")
        with patch.object(product_reuse, "inspect_products", return_value={"readyPlans": []}) as inspect, \
                patch.object(sdk_native_continuation, "select_preparation_anchor", return_value=empty) as select:
            self.assertEqual({**empty, "preparation_required": "false"}, self.snippet("sdk-native-plan", environment))
            self.assertNotIn("sdk_validation_tooling", inspect.call_args.kwargs)
            select.side_effect = ValueError("invalid original ready plans")
            with self.assertRaises(ValueError):
                self.snippet("sdk-native-plan", environment)

    def test_saved_plan_imports_in_fresh_process_before_inspection_seam(self):
        match = re.search(r"(?ms)^          python3 - <<'PY'\n(.*?)^          PY$", self.job("sdk-native-plan"))
        code = textwrap.dedent(match[1])
        # Execute the exact production import prefix first. No fixture/bootstrap
        # imports in the child may mask missing script-module path setup.
        prefix, suffix = code.split("policy = os.environ['SDK_VALIDATION_TOOLING']", 1)
        seam = "\nimport json\nfrom unittest.mock import Mock\ninspect_products = Mock(return_value={'readyPlans': json.loads(os.environ['READY_PLANS'])})\n"
        code = prefix + seam + "policy = os.environ['SDK_VALIDATION_TOOLING']" + suffix
        anchor = selector_fixture.ready("python", "validation", "macos-arm64")
        for rows in ([], [anchor]):
            with self.subTest(ready=bool(rows)), tempfile.TemporaryDirectory(prefix="native-plan-import-") as temporary:
                output = Path(temporary) / "output"
                env = {key: value for key, value in os.environ.items() if not key.startswith("PYTHON")}
                env.update(PLAN="/original/plan", DISCOVERY="/original/discovery", STATE="/original/state",
                           SDK_VALIDATION_TOOLING="", TRUSTED_WORKFLOW_SHA="c" * 40,
                           GITHUB_OUTPUT=str(output), READY_PLANS=json.dumps(rows))
                result = subprocess.run([sys.executable, "-B", "-c", code], cwd=ROOT, env=env,
                                        capture_output=True, text=True)
                self.assertEqual(0, result.returncode, result.stderr)
                expected = dict(preparation_required="false", component="", phase="", target="", build_key="")
                if rows:
                    expected.update(preparation_required="true", component="python", phase="validation",
                                    target="macos-arm64", build_key=anchor["buildKey"])
                self.assertEqual(expected, dict(line.split("=", 1) for line in output.read_text().splitlines()))

    def test_summary_requires_planning_and_every_elected_result(self):
        base = self.needs()
        self.assertEqual({"artifact_id": "73", "artifact_digest": "sha256:" + "e" * 64,
                          "state_wave": "0", "sdk_state_wave": "4"}, self.summary(base))
        for name in ("sdk-javascript", "sdk-native-plan", "sdk-native-prepare", "sdk-native-workers", "sdk-collect-4"):
            for result in ("failure", "cancelled", "skipped"):
                needs = deepcopy(base)
                needs[name]["result"] = result
                with self.subTest(name=name, result=result), self.assertRaises(ValueError):
                    self.summary(needs)
        for field, value in (("sdk_workers_required", None), ("sdk_workers_required", "unknown"),
                             ("wave_failed", "true"), ("wave_failed", None)):
            needs = deepcopy(base)
            job = "sdk-native-plan" if field == "sdk_workers_required" else "sdk-collect-4"
            needs[job]["outputs"][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.summary(needs)

    def test_no_work_requires_all_producers_and_collection_skipped(self):
        for no_handoff in (False, True):
            base = self.needs()
            base["sdk-native-plan"]["outputs"]["sdk_workers_required"] = "false"
            base["sdk-native-plan"]["outputs"]["preparation_required"] = "false"
            if no_handoff:
                base["sdk-javascript"]["outputs"] = {}
                base["sdk-native-plan"] = {"result": "skipped", "outputs": {}}
            for name in ("sdk-native-prepare", "sdk-native-workers", "sdk-collect-4"):
                base[name] = {"result": "skipped", "outputs": {}}
            expected = base["sdk-javascript"]["outputs"] if not no_handoff else dict(artifact_id="", artifact_digest="", state_wave="", sdk_state_wave="")
            self.assertEqual(expected, self.summary(base))
            for name in ("sdk-native-prepare", "sdk-native-workers", "sdk-collect-4"):
                needs = deepcopy(base)
                needs[name]["result"] = "success"
                with self.subTest(no_handoff=no_handoff, unexpected=name), self.assertRaises(ValueError):
                    self.summary(needs)
            if no_handoff:
                base["sdk-native-plan"]["result"] = "success"
                with self.assertRaises(ValueError): self.summary(base)

    def test_preparation_can_run_for_later_anchor_without_package_work(self):
        needs = self.needs()
        needs["sdk-native-plan"]["outputs"].update(sdk_workers_required="false", preparation_required="true")
        for name in ("sdk-native-workers", "sdk-collect-4"):
            needs[name] = {"result": "skipped", "outputs": {}}
        self.assertEqual(needs["sdk-javascript"]["outputs"], self.summary(needs))
        needs["sdk-native-prepare"]["result"] = "skipped"
        with self.assertRaises(ValueError):
            self.summary(needs)


if __name__ == "__main__":
    unittest.main()
