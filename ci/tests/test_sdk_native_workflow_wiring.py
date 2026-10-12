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
    def test_same_preparation_transport_reuses_capture_but_every_difference_recaptures(self):
        source = (ROOT / ".github/actions/sdk-native-package-worker/action.yml").read_text()
        block = source.split("    - id: preparation\n", 1)[1].split("    - id: identity\n", 1)[0]
        script = textwrap.dedent(block.split("      run: |\n", 1)[1])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = root / "python3"
            executable.write_text('#!/bin/sh\nprintf "%s\\n" "$*" > "$CAPTURE_CALL"\n')
            executable.chmod(0o700)
            output, call = root / "output", root / "call"
            environment = {**os.environ, "PATH": str(root) + os.pathsep + os.environ["PATH"],
                "GITHUB_OUTPUT": str(output), "CAPTURE_CALL": str(call), "PLAN": "plan.json",
                "GITHUB_WORKSPACE": str(root), "TRUSTED_WORKFLOW_SHA": "a" * 40,
                "SDK_VALIDATION_TOOLING": "", "SDK_APPLE_VALIDATION_POLICY": "",
                "CURRENT_MATRIX": json.dumps({"include": [self.row("python")]}),
                "CURRENT_STATE_ROOT": str(root / "already-captured")}
            values = dict(ARTIFACT_ID="71", ARTIFACT_SHA256="sha256:" + "a" * 64,
                          STATE_WAVE="0", SDK_STATE_WAVE="19")
            environment.update(values)
            environment.update({"CURRENT_" + key: value for key, value in values.items()})
            for changed in (None, *values):
                output.write_text("")
                if call.exists():
                    call.unlink()
                current = dict(environment)
                if changed:
                    current[changed] = "different"
                subprocess.run(["bash", "-c", script], env=current, check=True)
                if changed:
                    self.assertIn("ci.sdk_workflow capture --family native-package", call.read_text())
                    self.assertEqual("", output.read_text())
                else:
                    self.assertFalse(call.exists())
                    self.assertIn("state_root=" + environment["CURRENT_STATE_ROOT"], output.read_text())
                    self.assertIn("sdk_matrix=" + environment["CURRENT_MATRIX"], output.read_text())

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
        return {"sdk-csharp-binary-result": {"result": "success", "outputs": {
                    "artifact_id": "71", "artifact_digest": "sha256:" + "d" * 64,
                    "state_wave": "0", "sdk_state_wave": "2"}},
                "sdk-native-plan": {"result": "success", "outputs": {"sdk_workers_required": "true", "preparation_required": "true"}},
                "sdk-native-prepare": {"result": "success", "outputs": {"artifact_id": "72"}},
                "sdk-native-workers": {"result": "success", "outputs": {}},
                "sdk-collect-4": {"result": "success", "outputs": {"wave_failed": "false",
                    "artifact_id": "73", "artifact_digest": "sha256:" + "e" * 64}}}

    def test_original_terminal_state_is_recaptured_before_one_preparation_and_parallel_packages(self):
        planned = self.job("sdk-native-plan")
        self.assertIn("needs.sdk-csharp-binary-result.result == 'success'", planned)
        self.assertIn("needs.plan.outputs.event_authorized == 'true'", self.job("sdk-javascript"))
        self.assertIn("needs.plan.outputs.remote_build_authorized == 'true'", planned)
        self.assertIn("steps.capture.outputs.native-preparation-required", planned)
        self.assertNotIn("inspect_products", planned)
        self.assertIn("family: native-package", planned)
        self.assertNotIn("setup-kmp", planned)

        legacy = self.job("sdk-native-wrappers")
        self.assertIn("needs: [workflow-lint, plan, sdk-plan, sdk-csharp-binary-result, sdk-native-prepare, sdk-inputs]", legacy)
        self.assertIn("needs.sdk-csharp-binary-result.result == 'success'", legacy)
        for field, output in (("stateArtifactId", "artifact_id"),
                              ("stateArtifactSha256", "artifact_digest"),
                              ("stateWave", "state_wave"),
                              ("sdkStateWave", "sdk_state_wave")):
            self.assertIn(f"{field}: ${{{{ needs.sdk-csharp-binary-result.outputs.{output} }}}}", legacy)
            self.assertNotIn(f"{field}: ${{{{ needs.sdk-javascript.outputs.{output} }}}}", legacy)
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
                self.assertIn(flag + ": ${{ needs.sdk-csharp-binary-result.outputs." + field + " }}", job)
        for flag, field in (("prepared-artifact-id", "artifact_id"), ("prepared-artifact-sha256", "artifact_digest"),
                            ("preparation-component", "preparation_component"), ("preparation-build-key", "preparation_build_key"),
                            ("preparation-state-id", "preparation_state_id"), ("preparation-state-sha256", "preparation_state_digest"),
                            ("preparation-state-wave", "preparation_state_wave"), ("preparation-sdk-state-wave", "preparation_sdk_state_wave")):
            self.assertIn(flag + ": ${{ needs.sdk-native-prepare.outputs." + field + " }}", workers)

    def test_csharp_binary_is_authenticated_and_collected_before_package_election(self):
        planned = self.job("sdk-csharp-binary-plan")
        worker = self.job("sdk-csharp-binary")
        collector = self.job("sdk-collect-19")
        result = self.job("sdk-csharp-binary-result")
        native = self.job("sdk-native-plan")
        for job in (planned, worker, result, native):
            self.assertIn("needs.plan.outputs.remote_build_authorized == 'true'", job)
        self.assertIn("family: csharp-binary", planned)
        self.assertNotIn("setup-kmp", planned)
        self.assertIn("fromJSON(needs.sdk-csharp-binary-plan.outputs.sdk_matrix", worker)
        self.assertIn("uses: ./.github/actions/sdk-csharp-binary-worker", worker)
        self.assertIn("needs.sdk-inputs.result == 'success'", worker)
        self.assertIn("sdk-family: csharp-binary", collector)
        self.assertIn("wave: '19'", collector)
        self.assertIn("always()", collector)
        self.assertNotIn("needs.sdk-csharp-binary.result", collector.split("    runs-on:", 1)[0])
        self.assertIn("select_native_state(json.loads(os.environ['RESULTS']), stage='csharp-binary')", result)
        self.assertIn("sdk-csharp-binary-result", native.split("    runs-on:", 1)[0])
        for flag, field in (("artifact-id", "artifact_id"), ("artifact-sha256", "artifact_digest"),
                            ("state-wave", "state_wave"), ("sdk-state-wave", "sdk_state_wave")):
            self.assertIn(flag + ": ${{ needs.sdk-csharp-binary-result.outputs." + field + " }}", native)
        action = (ROOT / ".github/actions/sdk-csharp-binary-worker/action.yml").read_text()
        self.assertLess(action.index("uses: ./.github/actions/capture-runtime-state"),
                        action.index("uses: ./.github/actions/setup-kmp"))
        self.assertIn("--sdk-inputs-artifact-sha256", action)
        self.assertIn("--expected-build-key", action)
        self.assertIn("codex-agent-sdk-worker-sdk-csharp-binary-desktop-", action)

    def test_legacy_package_job_restores_authenticated_csharp_without_compiling_it(self):
        child = (ROOT / ".github/workflows/sdk-validation.yml").read_text()
        job = re.search(r"(?ms)^  native-wrapper-package-validation:\n.*?(?=^  [a-z][a-z0-9-]*:|\Z)", child)[0]
        self.assertIn("fetch-depth: 0", job)
        self.assertLess(job.index("uses: ./.github/actions/capture-sdk-tooling"),
                        job.index("uses: ./.github/actions/capture-runtime-state"))
        self.assertLess(job.index("uses: ./.github/actions/capture-runtime-state"),
                        job.index("ci.sdk_csharp_binary_workflow stage-original"))
        self.assertLess(job.index("ci.sdk_csharp_binary_workflow stage-original"),
                        job.index("python \"$tool/ci/native_wrappers.py\" package"))
        self.assertIn("--sdk-inputs-artifact-id \"$SDK_INPUTS_ARTIFACT_ID\"", job)
        self.assertIn("--csharp-binary \"$PWD/build/sdk-native-csharp-original/csharp-binary\"", job)
        self.assertIn("--dotnet-profile \"$PWD/build/sdk-native-csharp-original/sdk-csharp-toolchain.json\"", job)
        self.assertNotIn("sdk_csharp_binary_workflow --expected-build-key", job)

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
        for name in ("sdk-csharp-binary-result", "sdk-native-plan", "sdk-native-prepare", "sdk-native-workers", "sdk-collect-4"):
            self.assertIn(name, summary.split("    runs-on:", 1)[0])
        gate = self.job("merge-gate").split("    runs-on:", 1)[0]
        self.assertIn("sdk-native-packages", gate)

    def matrix_outputs(self, policy=None):
        with tempfile.TemporaryDirectory(prefix="native-routing-") as temporary:
            output = Path(temporary) / "github-output"
            sdk_workflow.matrix(Path("/original/plan"), Path("/original/discovery"), Path("/original/state"),
                output, family="native-package", trusted_workflow_sha="c" * 40,
                **({"sdk_validation_tooling": policy} if policy else {}))
            return dict(line.split("=", 1) for line in output.read_text().splitlines())

    def test_preparation_and_matrix_share_one_authenticated_election(self):
        for phase, target in (("package", "desktop"), ("validation", "macos-arm64"), ("metadata", "desktop")):
            rows = [selector_fixture.ready("python", phase, target)]
            policy = {"synthetic": "caller-owned policy boundary"}
            with self.subTest(phase=phase), patch.object(sdk_workflow.product_reuse, "inspect_products",
                    return_value={"readyPlans": rows}) as inspect:
                output = self.matrix_outputs(policy)
                inspect.assert_called_once()
                self.assertIs(policy, inspect.call_args.kwargs["sdk_validation_tooling"])
                scope = inspect.call_args.kwargs["requested_scope"]
                self.assertTrue(all(row.component in sdk_workflow.NATIVE_BINDINGS for row in scope))
                self.assertEqual("true", output["native_preparation_required"])
                self.assertEqual(phase, output["native_preparation_phase"])
                self.assertEqual(rows[0]["buildKey"], output["native_preparation_build_key"])
                self.assertEqual(phase == "package", bool(json.loads(output["sdk_matrix"])["include"]))

    def test_selector_failure_and_noop_do_not_manufacture_preparation(self):
        with patch.object(sdk_workflow.product_reuse, "inspect_products", return_value={"readyPlans": []}) as inspect:
            output = self.matrix_outputs()
            self.assertEqual("false", output["native_preparation_required"])
            self.assertEqual("", output["native_preparation_build_key"])
            self.assertNotIn("sdk_validation_tooling", inspect.call_args.kwargs)
            inspect.return_value = {"readyPlans": [{"invalid": "original plan"}]}
            with self.assertRaises(ValueError):
                self.matrix_outputs()

    def test_saved_plan_imports_in_fresh_process_before_inspection_seam(self):
        code = """from pathlib import Path
import json, os
from ci import sdk_workflow
from unittest.mock import patch
with patch.object(sdk_workflow.product_reuse, 'inspect_products', return_value={'readyPlans': json.loads(os.environ['READY_PLANS'])}):
    sdk_workflow.matrix(Path('/plan'), Path('/discovery'), Path('/state'), Path(os.environ['GITHUB_OUTPUT']), family='native-package')
"""
        rows = [selector_fixture.ready("python", "validation", "macos-arm64")]
        with tempfile.TemporaryDirectory(prefix="native-plan-import-") as temporary:
            output = Path(temporary) / "output"
            env = {key: value for key, value in os.environ.items() if not key.startswith("PYTHON")}
            env.update(GITHUB_OUTPUT=str(output), READY_PLANS=json.dumps(rows))
            result = subprocess.run([sys.executable, "-B", "-c", code], cwd=ROOT, env=env,
                                    capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("native_preparation_phase=validation", output.read_text())


    def test_summary_requires_planning_and_every_elected_result(self):
        base = self.needs()
        self.assertEqual({"artifact_id": "73", "artifact_digest": "sha256:" + "e" * 64,
                          "state_wave": "0", "sdk_state_wave": "4"}, self.summary(base))
        for name in ("sdk-csharp-binary-result", "sdk-native-plan", "sdk-native-prepare", "sdk-native-workers", "sdk-collect-4"):
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
                base["sdk-csharp-binary-result"]["outputs"] = {}
                base["sdk-native-plan"] = {"result": "skipped", "outputs": {}}
            for name in ("sdk-native-prepare", "sdk-native-workers", "sdk-collect-4"):
                base[name] = {"result": "skipped", "outputs": {}}
            expected = base["sdk-csharp-binary-result"]["outputs"] if not no_handoff else dict(artifact_id="", artifact_digest="", state_wave="", sdk_state_wave="")
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
        self.assertEqual(needs["sdk-csharp-binary-result"]["outputs"], self.summary(needs))
        needs["sdk-native-prepare"]["result"] = "skipped"
        with self.assertRaises(ValueError):
            self.summary(needs)


if __name__ == "__main__":
    unittest.main()
