"""Native metadata workflow state wiring, not hosted or semantic evidence."""

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


class SdkNativeMetadataWorkflowWiringTest(unittest.TestCase):
    def setUp(self):
        self.workflow = (ROOT / ".github/workflows/product-validation.yml").read_text()

    def job(self, name):
        match = re.search(rf"(?ms)^  {re.escape(name)}:\n.*?(?=^  [a-z][a-z0-9-]*:|\Z)", self.workflow)
        self.assertIsNotNone(match, name)
        return match[0]

    def result(self, needs):
        source = self.job("sdk-native-result")
        match = re.search(r"(?ms)^          python3 - <<'PY'\n(.*?)^          PY$", source)
        self.assertIsNotNone(match)
        with tempfile.TemporaryDirectory(prefix="sdk-native-metadata-result-") as temporary:
            output = Path(temporary) / "output"
            output.write_bytes(b"")
            with patch.dict(os.environ, {"RESULTS": json.dumps(needs), "GITHUB_OUTPUT": str(output)}, clear=True):
                try:
                    exec(compile(textwrap.dedent(match[1]), "metadata-result", "exec"), {})
                except Exception:
                    self.assertEqual(b"", output.read_bytes())
                    raise
            return dict(line.split("=", 1) for line in output.read_text().splitlines())

    @staticmethod
    def locator(artifact="81", sdk_wave="7"):
        return {"artifact_id": artifact, "artifact_digest": "sha256:" + artifact[-1] * 64,
                "state_wave": "0", "sdk_state_wave": sdk_wave}

    def needs(self, *, required="true", worker="success", collector="success", failed="false"):
        return {
            "sdk-native-validation-result": {"result": "success", "outputs": self.locator()},
            "sdk-native-metadata-plan": {"result": "success", "outputs": {"sdk_workers_required": required}},
            "sdk-native-metadata": {"result": worker, "outputs": {}},
            "sdk-collect-8": {"result": collector, "outputs": {
                **self.locator("82", "8"), "wave_failed": failed,
            }},
        }

    def test_plan_and_linux_worker_use_the_validation_state_and_original_preparation(self):
        planned = self.job("sdk-native-metadata-plan")
        self.assertIn("sdk-native-validation-result.result == 'success'", planned)
        self.assertIn("sdk-family: native-metadata", planned)
        self.assertLess(planned.index("capture-sdk-tooling"), planned.index("capture-runtime-state"))
        for field in ("artifact_id", "artifact_digest", "state_wave", "sdk_state_wave"):
            output = "artifact-sha256" if field == "artifact_digest" else field.replace("_", "-")
            self.assertIn(f"{output}: ${{{{ needs.sdk-native-validation-result.outputs.{field} }}}}", planned)

        worker = self.job("sdk-native-metadata")
        self.assertIn("name: sdk-${{ matrix.component }}-metadata-${{ matrix.target }}", worker)
        self.assertIn("runs-on: ${{ matrix.runner }}", worker)
        self.assertIn("uses: ./.github/actions/sdk-native-metadata-worker", worker)
        self.assertIn("sdk-native-prepare", worker.split("    if:", 1)[0])
        self.assertIn("sdk-inputs", worker.split("    if:", 1)[0])
        for field in ("artifact_id", "artifact_digest", "state_wave", "sdk_state_wave"):
            argument = {"artifact_id": "artifact-id", "artifact_digest": "artifact-sha256",
                        "state_wave": "state-wave", "sdk_state_wave": "sdk-state-wave"}[field]
            self.assertIn(f"{argument}: ${{{{ needs.sdk-native-validation-result.outputs.{field} }}}}", worker)
        for argument, field in (
            ("prepared-artifact-id", "artifact_id"), ("prepared-artifact-sha256", "artifact_digest"),
            ("preparation-component", "preparation_component"), ("preparation-build-key", "preparation_build_key"),
            ("preparation-phase", "preparation_phase"), ("preparation-target", "preparation_target"),
            ("preparation-state-id", "preparation_state_id"),
            ("preparation-state-sha256", "preparation_state_digest"),
            ("preparation-state-wave", "preparation_state_wave"),
            ("preparation-sdk-state-wave", "preparation_sdk_state_wave"),
        ):
            self.assertIn(f"{argument}: ${{{{ needs.sdk-native-prepare.outputs.{field} }}}}", worker)
        self.assertIn("sdk-validation-tooling: ${{ steps.tooling.outputs.tooling-policy }}", worker)
        action = (ROOT / ".github/actions/sdk-native-metadata-worker/action.yml").read_text()
        self.assertIn("host_classifier() != 'linux-x64'", action)
        self.assertIn("_HOSTS[target if phase == 'validation' else 'linux-x64']", action)

    def test_collection_waits_for_worker_completion_but_runs_after_worker_failure(self):
        collector = self.job("sdk-collect-8")
        self.assertIn("sdk-native-metadata]", collector)
        condition = collector.split("    if: >-\n", 1)[1].split("    runs-on:", 1)[0]
        self.assertIn("always()", condition)
        self.assertIn("sdk-native-metadata-plan.outputs.sdk_workers_required == 'true'", condition)
        self.assertNotIn("needs.sdk-native-metadata.result", condition)
        self.assertIn("sdk-family: native-metadata", collector)
        self.assertIn("wave: '8'", collector)
        self.assertIn("artifact-id: ${{ needs.sdk-native-validation-result.outputs.artifact_id }}", collector)
        with self.assertRaisesRegex(ValueError, "workers or collection failed"):
            self.result(self.needs(worker="failure"))

    def test_final_gate_forwards_collected_or_noop_state_and_rejects_mutation(self):
        self.assertEqual(self.locator("82", "8"), self.result(self.needs()))

        noop = self.needs(required="false", worker="skipped", collector="skipped")
        noop["sdk-collect-8"]["outputs"] = {}
        noop["sdk-native-validation-result"]["outputs"] = self.locator("74", "4")
        self.assertEqual(self.locator("74", "4"), self.result(noop))

        for mutation in (
            ("sdk-native-metadata", "result", "success"),
            ("sdk-collect-8", "result", "success"),
            ("sdk-native-validation-result", "artifact_digest", "sha256:" + "f" * 63),
        ):
            invalid = deepcopy(noop)
            job, field, value = mutation
            if field == "result":
                invalid[job][field] = value
            else:
                invalid[job]["outputs"][field] = value
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.result(invalid)

    def test_final_result_and_merge_gate_depend_on_metadata_collection(self):
        packages = self.job("sdk-native-packages")
        self.assertIn("select_native_state(json.loads(os.environ['RESULTS']), stage='package')", packages)
        for output in ("artifact_id", "artifact_digest", "state_wave", "sdk_state_wave"):
            self.assertIn(f"{output}: ${{{{ steps.result.outputs.{output} }}}}", packages)

        result = self.job("sdk-native-result")
        for dependency in ("sdk-native-validation-result", "sdk-native-metadata-plan",
                           "sdk-native-metadata", "sdk-collect-8"):
            self.assertIn(dependency, result.split("    runs-on:", 1)[0])
        self.assertIn("select_native_state(json.loads(os.environ['RESULTS']), stage='metadata')", result)
        for output in ("artifact_id", "artifact_digest", "state_wave", "sdk_state_wave"):
            self.assertIn(f"{output}: ${{{{ steps.result.outputs.{output} }}}}", result)
        gate = self.job("merge-gate").split("    runs-on:", 1)[0]
        self.assertIn("sdk-native-result", gate)


if __name__ == "__main__":
    unittest.main()
