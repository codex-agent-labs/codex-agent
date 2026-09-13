"""Static SDK job wiring and executed summary controls, not hosted execution."""

from copy import deepcopy
import json
import os
from pathlib import Path
import re
import textwrap
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]


class SdkWorkflowWiringTest(unittest.TestCase):
    def setUp(self):
        self.workflow = (ROOT / ".github/workflows/product-validation.yml").read_text()

    def job(self, name):
        return re.search(rf"(?ms)^  {re.escape(name)}:\n.*?(?=^  [a-z][a-z0-9-]*:|\Z)", self.workflow)[0]

    def test_elected_workers_capture_before_isolated_setup_and_always_collect(self):
        action = (ROOT / ".github/actions/sdk-javascript-worker/action.yml").read_text()
        self.assertLess(action.index("./.github/actions/capture-runtime-state"), action.index("./.github/actions/setup-kmp"))
        self.assertLess(action.index("JavaScript worker differs"), action.index("./.github/actions/setup-kmp"))
        self.assertIn("product-worker: 'true'", action)
        self.assertIn("ci.sdk_workflow javascript", action)
        self.assertIn("if: always() && steps.identity.outcome == 'success'", action)
        self.assertIn("overwrite: false", action)
        self.assertIn("attempt-${{ github.run_attempt }}", action)
        plan = self.job("sdk-plan")
        self.assertIn("needs.plan.outputs.remote_build_authorized == 'true'", plan)
        self.assertIn("runtime-aggregate-continuation' if source == 'current-runtime'", plan)
        self.assertNotIn("setup-kmp", plan)
        for wave in (1, 2):
            worker = self.job(f"sdk-workers-{wave}")
            self.assertIn("fail-fast: false", worker)
            self.assertIn("remote_build_authorized == 'true'", worker)
            self.assertIn("name: sdk-javascript-${{ matrix.phase }}-node", worker)
            self.assertIn("./.github/actions/sdk-javascript-worker", worker)
            collector = self.job(f"sdk-collect-{wave}")
            self.assertIn("always()", collector)
            self.assertIn(f"sdk-workers-{wave}]", collector)
            self.assertIn("product: sdk", collector)
        self.assertNotIn("one_directory", self.job("sdk-javascript"))

    def summary(self, needs):
        source = self.job("sdk-javascript").split("python3 - <<'PY'\n", 1)[1].rsplit("          PY", 1)[0]
        with patch.dict(os.environ, {"RESULTS": json.dumps(needs)}):
            exec(compile(textwrap.dedent(source), "sdk-summary-fixture", "exec"), {})

    def test_summary_requires_every_elected_collection_and_explicit_next_wave(self):
        base = {"runtime-continuation": {"outputs": {"sdk_handoff_required": "true"}},
            "sdk-plan": {"result": "success", "outputs": {"sdk_workers_required": "true"}},
            "sdk-collect-1": {"result": "success", "outputs": {"wave_failed": "false", "sdk_workers_required": "true"}},
            "sdk-collect-2": {"result": "success", "outputs": {"wave_failed": "false"}}}
        self.summary(base)
        cases = (("sdk-plan", "result", "failure"), ("sdk-collect-1", "result", "skipped"),
                 ("sdk-collect-2", "result", "failure"), ("sdk-collect-1", "wave_failed", "true"),
                 ("sdk-collect-1", "sdk_workers_required", None))
        for job, field, value in cases:
            needs = deepcopy(base)
            target = needs[job] if field == "result" else needs[job]["outputs"]
            target[field] = value
            with self.subTest(job=job, field=field), self.assertRaises(ValueError):
                self.summary(needs)
        one_wave = deepcopy(base)
        one_wave["sdk-collect-1"]["outputs"]["sdk_workers_required"] = "false"
        one_wave["sdk-collect-2"] = {"result": "skipped", "outputs": {}}
        self.summary(one_wave)
        none = deepcopy(one_wave)
        none["sdk-plan"]["outputs"]["sdk_workers_required"] = "false"
        none["sdk-collect-1"] = {"result": "skipped", "outputs": {}}
        self.summary(none)
        none["sdk-plan"]["result"] = "skipped"
        with self.assertRaises(ValueError):
            self.summary(none)
        none["runtime-continuation"]["outputs"]["sdk_handoff_required"] = "false"
        self.summary(none)


if __name__ == "__main__":
    unittest.main()
