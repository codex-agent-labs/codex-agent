"""Wave-6 workflow composition, not original CI or SDK content acceptance.

These checks intentionally require the saved jobs; they do not skip missing
wiring or substitute a test workflow for the production source.
"""

from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from ci import sdk_native_continuation
from ci.tests import test_sdk_native_workflow_wiring as fixture


class SdkJavaScriptMetadataWorkflowWiringTest(unittest.TestCase):
    def setUp(self):
        self.harness = fixture.SdkNativeWorkflowWiringTest(methodName="runTest")
        self.harness.setUp()

    def job(self, name):
        return self.harness.job(name)

    @staticmethod
    def needs():
        return {
            "sdk-native-packages": {"result": "success", "outputs": {
                "artifact_id": "75", "artifact_digest": "sha256:" + "a" * 64,
                "state_wave": "0", "sdk_state_wave": "4"}},
            "sdk-javascript-metadata-plan": {"result": "success", "outputs": {"sdk_workers_required": "true"}},
            "sdk-javascript-metadata": {"result": "success", "outputs": {}},
            "sdk-collect-6": {"result": "success", "outputs": {
                "artifact_id": "76", "artifact_digest": "sha256:" + "b" * 64, "wave_failed": "false"}},
        }

    def summary(self, needs):
        with patch.object(sdk_native_continuation, "select_native_state",
                          wraps=sdk_native_continuation.select_native_state) as select:
            result = self.harness.snippet("sdk-javascript-metadata-result", {"RESULTS": json.dumps(needs)})
        select.assert_called_once_with(needs, stage="javascript-metadata")
        return result

    def test_exact_native_package_parent_and_local_tooling_flow_to_metadata_capture_worker_and_collection(self):
        plan = self.job("sdk-javascript-metadata-plan")
        worker = self.job("sdk-javascript-metadata")
        collector = self.job("sdk-collect-6")
        self.assertIn("needs.sdk-native-packages.result == 'success'", plan)
        self.assertIn("needs.sdk-native-packages.outputs.artifact_id != ''", plan)
        self.assertIn("uses: ./.github/actions/capture-runtime-state", plan)
        self.assertIn("sdk-family: javascript-metadata", plan)
        self.assertNotIn("setup-kmp", plan)
        self.assertIn("name: sdk-javascript-metadata-node", worker)
        self.assertIn("runs-on: ${{ matrix.runner }}", worker)
        self.assertIn("fromJSON(needs.sdk-javascript-metadata-plan.outputs.sdk_matrix", worker)
        self.assertIn("fail-fast: false", worker)
        self.assertIn("build-key: ${{ matrix.buildKey }}", worker)
        action = (fixture.ROOT / ".github/actions/sdk-javascript-metadata-worker/action.yml").read_text()
        self.assertIn("if host_classifier() != 'linux-x64':", action)
        self.assertIn("('sdk', 'javascript', 'metadata', 'node')", action)
        self.assertIn("(rows[0]['runnerOs'], rows[0]['runnerArch']) != ('Linux', 'X64')", action)
        routing = (fixture.ROOT / "ci/sdk_workflow.py").read_text()
        self.assertIn('if family == "javascript-metadata":\n            return {"runner": "ubuntu-24.04", "runnerOs": "Linux", "runnerArch": "X64"}', routing)
        self.assertIn("needs.sdk-javascript-metadata-plan.outputs.sdk_workers_required == 'true'", worker)
        self.assertEqual(1, worker.count("uses: ./.github/actions/sdk-javascript-metadata-worker"))
        # The existing controller locates the authenticated original validation
        # receipt's producer, not the newest/current validation upload.
        self.assertNotIn("validation-artifact-id:", worker)
        self.assertNotIn("validation-artifact-sha256:", worker)
        self.assertNotIn("original-consumer-directory:", worker)
        self.assertIn("sdk-inputs-id: ${{ needs.sdk-inputs.outputs.artifact_id }}", worker)
        self.assertIn("sdk-inputs-sha256: ${{ needs.sdk-inputs.outputs.artifact_digest }}", worker)
        for job in (plan, worker, collector):
            self.assertIn("needs.plan.outputs.event_authorized == 'true'", job)
            self.assertIn("needs.plan.outputs.remote_build_authorized == 'true'", job)
            self.assertIn("sdk-plan", job.split("    if:", 1)[0])
            self.assertIn("uses: ./.github/actions/capture-sdk-tooling", job)
            self.assertIn("sdk-validation-tooling: ${{ steps.tooling.outputs.tooling-policy }}", job)
            self.assertLess(job.index("- id: tooling"), job.index("sdk-validation-tooling:"))
            for flag, field in (("artifact-id", "tooling_artifact_id"), ("artifact-sha256", "tooling_artifact_sha256"),
                                ("transport-producer", "tooling_transport_producer")):
                self.assertIn(flag + ": ${{ needs.sdk-plan.outputs." + field + " }}", job)
            for flag, field in (("artifact-id", "artifact_id"), ("artifact-sha256", "artifact_digest"),
                                ("state-wave", "state_wave"), ("sdk-state-wave", "sdk_state_wave")):
                self.assertIn(flag + ": ${{ needs.sdk-native-packages.outputs." + field + " }}", job)
            self.assertNotIn("needs.sdk-ios-packages", job)

    def test_collect6_waits_for_worker_failure_and_final_gate_feeds_native_validation(self):
        collector = self.job("sdk-collect-6")
        self.assertIn("sdk-javascript-metadata", collector.split("    if:", 1)[0])
        condition = collector.split("    if: >-\n", 1)[1].split("    runs-on:", 1)[0]
        self.assertIn("always()", condition)
        self.assertIn("needs.sdk-javascript-metadata-plan.outputs.sdk_workers_required == 'true'", condition)
        self.assertNotIn("needs.sdk-javascript-metadata.result", condition)
        self.assertNotIn("contains(needs.*.result", condition)
        self.assertIn("uses: ./.github/actions/collect-runtime-wave", collector)
        self.assertIn("sdk-family: javascript-metadata", collector)
        self.assertIn("wave: '6'", collector)
        gate = self.job("sdk-javascript-metadata-result")
        self.assertIn("always()", gate)
        for name in self.needs():
            self.assertIn(name, gate.split("    runs-on:", 1)[0])
        for name in ("sdk-native-validation-plan", "sdk-native-validation", "sdk-collect-7"):
            child = self.job(name)
            self.assertIn("sdk-javascript-metadata-result", child.split("    if:", 1)[0])
            self.assertIn("artifact-id: ${{ needs.sdk-javascript-metadata-result.outputs.artifact_id }}", child)
            self.assertIn("sdk-state-wave: ${{ needs.sdk-javascript-metadata-result.outputs.sdk_state_wave }}", child)

    def test_summary_returns_wave6_only_after_every_elected_result_and_valid_locator(self):
        base = self.needs()
        self.assertEqual({"artifact_id": "76", "artifact_digest": "sha256:" + "b" * 64,
                          "state_wave": "0", "sdk_state_wave": "6"}, self.summary(base))
        for name in base:
            for status in ("failure", "cancelled", "skipped"):
                needs = deepcopy(base)
                needs[name]["result"] = status
                with self.subTest(name=name, status=status), self.assertRaises(ValueError):
                    self.summary(needs)
        for field, value in (("wave_failed", "true"), ("wave_failed", ""), ("artifact_id", ""),
                             ("artifact_digest", "sha256:bad")):
            needs = deepcopy(base)
            needs["sdk-collect-6"]["outputs"][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.summary(needs)

    def test_reuse_retains_exact_parent_and_missing_handoff_cannot_invent_work(self):
        base = self.needs()
        base["sdk-javascript-metadata-plan"]["outputs"]["sdk_workers_required"] = "false"
        for name in ("sdk-javascript-metadata", "sdk-collect-6"):
            base[name] = {"result": "skipped", "outputs": {}}
        self.assertEqual(base["sdk-native-packages"]["outputs"], self.summary(base))
        for name in ("sdk-javascript-metadata", "sdk-collect-6"):
            needs = deepcopy(base)
            needs[name]["result"] = "success"
            with self.subTest(unexpected=name), self.assertRaises(ValueError):
                self.summary(needs)
        base["sdk-native-packages"]["outputs"] = {}
        base["sdk-javascript-metadata-plan"] = {"result": "skipped", "outputs": {}}
        self.assertEqual(dict(artifact_id="", artifact_digest="", state_wave="", sdk_state_wave=""), self.summary(base))
        base["sdk-javascript-metadata-plan"]["result"] = "success"
        with self.assertRaises(ValueError):
            self.summary(base)


if __name__ == "__main__":
    unittest.main()
