"""Native workflow wiring and executed selectors, not hosted/package evidence."""

from copy import deepcopy
import json
import os
from pathlib import Path
import re
import tempfile
import textwrap
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]


class SdkNativeWorkflowWiringTest(unittest.TestCase):
    def setUp(self):
        self.workflow = (ROOT / ".github/workflows/product-validation.yml").read_text()

    def job(self, name):
        return re.search(rf"(?ms)^  {re.escape(name)}:\n.*?(?=^  [a-z][a-z0-9-]*:|\Z)", self.workflow)[0]

    def snippet(self, job, environment):
        match = re.search(r"(?ms)^          python3 - <<'PY'\n(.*?)^          PY$", self.job(job))
        self.assertIsNotNone(match)
        with tempfile.TemporaryDirectory(prefix="sdk-native-wiring-") as temporary:
            output = Path(temporary) / "output"
            output.write_bytes(b"")
            with patch.dict(os.environ, {**environment, "GITHUB_OUTPUT": str(output)}, clear=True):
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

    def select(self, rows):
        return self.snippet("sdk-native-plan", {"MATRIX": json.dumps({"include": rows})})

    def summary(self, needs):
        return self.snippet("sdk-native-packages", {"RESULTS": json.dumps(needs)})

    @staticmethod
    def needs():
        return {"sdk-javascript": {"result": "success", "outputs": {
                    "artifact_id": "71", "artifact_digest": "sha256:" + "d" * 64,
                    "state_wave": "0", "sdk_state_wave": "2"}},
                "sdk-native-plan": {"result": "success", "outputs": {"sdk_workers_required": "true"}},
                "sdk-native-prepare": {"result": "success", "outputs": {"artifact_id": "72"}},
                "sdk-native-workers": {"result": "success", "outputs": {}},
                "sdk-collect-4": {"result": "success", "outputs": {"wave_failed": "false"}}}

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

    def test_preparation_chooses_one_sorted_exact_row_or_noop(self):
        rows = [self.row("rust", "e"), self.row("python", "d"), self.row("dart", "c"),
                self.row("csharp", "b"), self.row("cpp", "a")]
        expected = {"component": "cpp", "build_key": rows[-1]["buildKey"]}
        self.assertEqual(expected, self.select(rows))
        self.assertEqual(expected, self.select(list(reversed(rows))))
        self.assertEqual({"component": "rust", "build_key": rows[0]["buildKey"]}, self.select(rows[:1]))
        self.assertEqual({}, self.select([]))

    def test_selector_rejects_any_invalid_or_duplicate_row_before_outputs(self):
        changes = (("component", "javascript"), ("product", "runtime"), ("phase", "validation"),
                   ("target", "linux-x64"), ("runner", "caller-runner"), ("runnerOs", "macOS"),
                   ("runnerArch", "ARM64"), ("buildKey", "sha256:" + "a" * 63),
                   ("buildKey", "sha256:" + "A" * 64))
        for field, value in changes:
            invalid = {**self.row("rust"), field: value}
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.select([self.row("cpp"), invalid])
        with self.assertRaises(ValueError):
            self.select([self.row("rust"), self.row("rust", "b")])

    def test_summary_requires_planning_and_every_elected_result(self):
        base = self.needs()
        self.assertEqual({}, self.summary(base))
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
            if no_handoff:
                base["sdk-javascript"]["outputs"] = {}
                base["sdk-native-plan"] = {"result": "skipped", "outputs": {}}
            for name in ("sdk-native-prepare", "sdk-native-workers", "sdk-collect-4"):
                base[name] = {"result": "skipped", "outputs": {}}
            self.assertEqual({}, self.summary(base))
            for name in ("sdk-native-prepare", "sdk-native-workers", "sdk-collect-4"):
                needs = deepcopy(base)
                needs[name]["result"] = "success"
                with self.subTest(no_handoff=no_handoff, unexpected=name), self.assertRaises(ValueError):
                    self.summary(needs)
            if no_handoff:
                base["sdk-native-plan"]["result"] = "success"
                with self.assertRaises(ValueError): self.summary(base)


if __name__ == "__main__":
    unittest.main()
