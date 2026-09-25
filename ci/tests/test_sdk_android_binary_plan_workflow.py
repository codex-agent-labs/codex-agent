"""Android wave 15 is a closed, original-pinned child route."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
PARENT = ROOT / ".github/workflows/product-validation.yml"
CHILD = PARENT.with_name("sdk-android-binary-validation.yml")


def job(source, name):
    match = re.search(rf"(?ms)^  {re.escape(name)}:\n.*?(?=^  [a-z][a-z0-9-]*:|\Z)", source)
    if match is None:
        raise AssertionError(f"Missing workflow job: {name}")
    return match[0]


class AndroidBinaryWorkflowTest(unittest.TestCase):
    def test_parent_delegates_exact_predecessors_and_final_gate_waits(self):
        source = PARENT.read_text()
        caller = job(source, "sdk-android-binary-result")
        self.assertIn("uses: ./.github/workflows/sdk-android-binary-validation.yml", caller)
        self.assertIn("needs.sdk-core-validation-wave.result == 'success'", caller)
        self.assertIn("needs.sdk-core-metadata-wave.result == 'success'", caller)
        self.assertIn("validationWave: ${{ toJSON(needs.sdk-core-validation-wave) }}", caller)
        self.assertIn("metadataWave: ${{ toJSON(needs.sdk-core-metadata-wave) }}", caller)
        for gate in ("sdk-completion", "sdk-parity", "merge-gate"):
            self.assertIn("sdk-android-binary-result", job(source, gate).split("    needs:", 1)[1])

    def test_child_fresh_core_route_and_fail_closed_reuse(self):
        source = CHILD.read_text()
        plan = job(source, "sdk-android-binary-plan")
        worker = job(source, "sdk-android-binary")
        collect = job(source, "sdk-collect-15")
        result = job(source, "sdk-android-binary-result")
        self.assertIn("sdk-family: android-binary", plan)
        self.assertIn("fromJSON(inputs.metadataWave).outputs.sdk_state_wave == '14'", worker)
        for field in ("metadata_build_key", "metadata_original_context", "metadata_receipt_sha256",
                      "metadata_artifact_id", "metadata_artifact_sha256"):
            self.assertIn(f"fromJSON(inputs.metadataWave).outputs.{field} != ''", worker)
        self.assertIn("core13-artifact-id: ${{ fromJSON(inputs.validationWave).outputs.artifact_id }}", worker)
        self.assertIn("metadata-artifact-id: ${{ fromJSON(inputs.metadataWave).outputs.metadata_artifact_id }}", worker)
        self.assertIn("uses: ./.github/actions/sdk-android-core14-caller", worker)
        self.assertIn("uses: ./.github/actions/sdk-android-maven-worker", worker)
        self.assertIn("phase: binary", worker)
        self.assertIn("ci.sdk_android_archive_provision", worker)
        self.assertIn("sdk-worker-workflow-path: .github/workflows/sdk-android-binary-validation.yml", collect)
        self.assertIn("sdk-worker-job-name: product-validation / sdk-android-binary-result / sdk-android-binary-android", collect)
        self.assertIn("select_native_state(needs, stage='android-binary')", result)


if __name__ == "__main__":
    unittest.main()
