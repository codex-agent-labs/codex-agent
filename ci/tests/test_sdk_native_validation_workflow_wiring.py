"""Saved wave-7 wiring and executed final gate; not hosted/native acceptance."""

from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from ci import sdk_native_continuation
from ci.tests import test_sdk_native_workflow_wiring as fixture


class SdkNativeValidationWorkflowWiringTest(unittest.TestCase):
    def setUp(self):
        self.harness = fixture.SdkNativeWorkflowWiringTest(methodName="runTest")
        self.harness.setUp()

    def test_validation_inspection_forwards_existing_caller_workflow_pin(self):
        source = (fixture.ROOT / "ci/sdk_native_validation_workflow.py").read_text()
        for entry in ("inspected = product_reuse.inspect_products(",
                      "ready = product_reuse.materialize_product_predecessors("):
            call = source.split(entry, 1)[1].split(")\n", 1)[0]
            self.assertIn("sdk_original_workflow_sha=trusted_workflow_sha", call)

    def job(self, name):
        return self.harness.job(name)

    @staticmethod
    def needs():
        return {
            "sdk-javascript-metadata-result": {"result": "success", "outputs": {
                "artifact_id": "74", "artifact_digest": "sha256:" + "a" * 64,
                "state_wave": "0", "sdk_state_wave": "4"}},
            "sdk-native-validation-plan": {"result": "success", "outputs": {"sdk_workers_required": "true"}},
            "sdk-native-validation": {"result": "success", "outputs": {}},
            "sdk-collect-7": {"result": "success", "outputs": {
                "artifact_id": "77", "artifact_digest": "sha256:" + "b" * 64, "wave_failed": "false"}},
        }

    def summary(self, needs):
        with patch.object(sdk_native_continuation, "select_native_state",
                          wraps=sdk_native_continuation.select_native_state) as select:
            result = self.harness.snippet("sdk-native-validation-result", {"RESULTS": json.dumps(needs)})
        select.assert_called_once_with(needs, stage="validation")
        return result

    def test_exact_elected_hosts_and_original_preparation_are_forwarded_with_local_tooling(self):
        plan = self.job("sdk-native-validation-plan")
        worker = self.job("sdk-native-validation")
        collector = self.job("sdk-collect-7")
        self.assertIn("needs.sdk-javascript-metadata-result.result == 'success'", plan)
        self.assertIn("needs.sdk-javascript-metadata-result.outputs.artifact_id != ''", plan)
        self.assertIn("sdk-family: native-validation", plan)
        self.assertNotIn("setup-kmp", plan)
        self.assertIn("name: sdk-${{ matrix.component }}-validation-${{ matrix.target }}", worker)
        self.assertIn("fail-fast: false", worker)
        self.assertIn("fromJSON(needs.sdk-native-validation-plan.outputs.sdk_matrix", worker)
        self.assertIn("runs-on: ${{ matrix.runner }}", worker)
        self.assertIn("needs.sdk-native-prepare.result == 'success'", worker)
        self.assertEqual(1, worker.count("uses: ./.github/actions/sdk-native-validation-worker"))
        for field, value in (("component", "matrix.component"), ("target", "matrix.target"), ("build-key", "matrix.buildKey")):
            self.assertIn(field + ": ${{ " + value + " }}", worker)
        for flag, field in (("prepared-artifact-id", "artifact_id"), ("prepared-artifact-sha256", "artifact_digest"),
                ("preparation-component", "preparation_component"), ("preparation-build-key", "preparation_build_key"),
                ("preparation-phase", "preparation_phase"), ("preparation-target", "preparation_target"),
                ("preparation-state-id", "preparation_state_id"), ("preparation-state-sha256", "preparation_state_digest"),
                ("preparation-state-wave", "preparation_state_wave"), ("preparation-sdk-state-wave", "preparation_sdk_state_wave")):
            self.assertIn(flag + ": ${{ needs.sdk-native-prepare.outputs." + field + " }}", worker)
        for job in (plan, worker, collector):
            self.assertIn("needs.plan.outputs.event_authorized == 'true'", job)
            self.assertIn("needs.plan.outputs.remote_build_authorized == 'true'", job)
            self.assertIn("sdk-plan", job.split("    if:", 1)[0])
            self.assertIn('java_home_variable="JAVA_HOME_17_${RUNNER_ARCH}"', job)
            self.assertIn("if [ \"$RUNNER_OS\" = Windows ]; then java_binary=java.exe; fi", job)
            self.assertIn("sdk-validation-tooling: ${{ steps.tooling.outputs.tooling-policy }}", job)
            self.assertLess(job.index("- id: tooling"), job.index("sdk-validation-tooling:"))
            for flag, field in (("artifact-id", "tooling_artifact_id"), ("artifact-sha256", "tooling_artifact_sha256"),
                                ("transport-producer", "tooling_transport_producer")):
                self.assertIn(flag + ": ${{ needs.sdk-plan.outputs." + field + " }}", job)
            for flag, field in (("artifact-id", "artifact_id"), ("artifact-sha256", "artifact_digest"),
                                ("state-wave", "state_wave"), ("sdk-state-wave", "sdk_state_wave")):
                self.assertIn(flag + ": ${{ needs.sdk-javascript-metadata-result.outputs." + field + " }}", job)

    def test_only_elected_dart_warms_external_cache_and_retains_diagnostics_after_failure(self):
        worker = self.job("sdk-native-validation")
        cache = worker.split("      - id: dart-cache\n", 1)[1].split("      - uses:", 1)[0]
        self.assertIn("if: matrix.component == 'dart'", cache)
        self.assertIn("uses: ./.github/actions/provision-sdk-dart-cache", cache)
        self.assertIn("revision: ${{ needs.plan.outputs.validation_commit }}", cache)
        self.assertLess(worker.index("- id: tooling"), worker.index("- id: dart-cache"))
        self.assertLess(worker.index("- id: dart-cache"), worker.index("uses: ./.github/actions/sdk-native-validation-worker"))
        self.assertIn("dart-pub-cache: ${{ steps.dart-cache.outputs.pub-cache }}", worker)
        diagnostic = worker.split("      - name: Retain caller Dart cache diagnostics", 1)[1]
        self.assertIn("if: always() && steps.dart-cache.outputs.diagnostics != ''", diagnostic)
        self.assertIn("path: ${{ steps.dart-cache.outputs.diagnostics }}", diagnostic)
        self.assertIn("overwrite: false", diagnostic)
        self.assertIn("include-hidden-files: true", diagnostic)
        self.assertNotIn("pub get", worker)

    def test_election_tooling_is_conditional_but_elected_execution_and_collection_require_it(self):
        for name in ("sdk-native-validation-plan", "sdk-native-metadata-plan",
                     "sdk-native-validation", "sdk-native-metadata", "sdk-collect-7", "sdk-collect-8"):
            job = self.job(name)
            java = job.split("      - name: Select installed caller Java for SDK tooling\n", 1)[1].split("\n      - ", 1)[0]
            tooling = job.split("      - id: tooling\n", 1)[1].split("\n      - ", 1)[0]
            with self.subTest(job=name):
                for block in (java, tooling):
                    if name.endswith("-plan"):
                        self.assertIn("if: needs.plan.outputs.tooling_required == 'true'", block)
                    else:
                        self.assertNotIn("if:", block)
                self.assertIn("sdk-validation-tooling: ${{ steps.tooling.outputs.tooling-policy }}", job)

    def test_collection_runs_after_failed_workers_and_merge_waits_for_final_gate(self):
        collector = self.job("sdk-collect-7")
        self.assertIn("sdk-native-validation]", collector.split("    if:", 1)[0])
        condition = collector.split("    if: >-\n", 1)[1].split("    runs-on:", 1)[0]
        self.assertIn("always()", condition)
        self.assertIn("needs.sdk-native-validation-plan.outputs.sdk_workers_required == 'true'", condition)
        self.assertNotIn("needs.sdk-native-validation.result", condition)
        self.assertNotIn("contains(needs.*.result", condition)
        self.assertIn("sdk-family: native-validation", collector)
        self.assertIn("wave: '7'", collector)
        self.assertIn("uses: ./.github/actions/collect-runtime-wave", collector)
        gate = self.job("sdk-native-validation-result")
        self.assertIn("always()", gate)
        for name in self.needs():
            self.assertIn(name, gate.split("    runs-on:", 1)[0])
        self.assertIn("sdk-native-result", self.job("merge-gate").split("    runs-on:", 1)[0])
        self.assertIn("sdk-native-validation-result", self.job("sdk-native-result").split("    runs-on:", 1)[0])

    def test_final_gate_selects_wave7_or_exact_retained_parent_and_never_masks_failure(self):
        base = self.needs()
        self.assertEqual({"artifact_id": "77", "artifact_digest": "sha256:" + "b" * 64,
                          "state_wave": "0", "sdk_state_wave": "7"}, self.summary(base))
        for name in base:
            for status in ("failure", "cancelled", "skipped"):
                needs = deepcopy(base)
                needs[name]["result"] = status
                with self.subTest(name=name, status=status), self.assertRaises(ValueError):
                    self.summary(needs)
        for field, value in (("wave_failed", "true"), ("wave_failed", ""), ("artifact_id", ""),
                             ("artifact_digest", "sha256:bad")):
            needs = deepcopy(base)
            needs["sdk-collect-7"]["outputs"][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.summary(needs)
        base["sdk-native-validation-plan"]["outputs"]["sdk_workers_required"] = "false"
        for name in ("sdk-native-validation", "sdk-collect-7"):
            base[name] = {"result": "skipped", "outputs": {}}
        self.assertEqual(base["sdk-javascript-metadata-result"]["outputs"], self.summary(base))
        for name in ("sdk-native-validation", "sdk-collect-7"):
            needs = deepcopy(base)
            needs[name]["result"] = "success"
            with self.subTest(unexpected=name), self.assertRaises(ValueError):
                self.summary(needs)
        base["sdk-javascript-metadata-result"]["outputs"] = {}
        base["sdk-native-validation-plan"] = {"result": "skipped", "outputs": {}}
        self.assertEqual(dict(artifact_id="", artifact_digest="", state_wave="", sdk_state_wave=""), self.summary(base))


if __name__ == "__main__":
    unittest.main()
