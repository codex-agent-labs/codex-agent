"""Android package child keeps fresh original authority and a fail-closed reuse edge."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
PARENT = ROOT / ".github/workflows/product-validation.yml"
CHILD = PARENT.with_name("sdk-android-package-validation.yml")


def job(source, name):
    match = re.search(rf"(?ms)^  {re.escape(name)}:\n.*?(?=^  [a-z][a-z0-9-]*:|\Z)", source)
    if match is None:
        raise AssertionError(f"Missing workflow job: {name}")
    return match[0]


class AndroidPackageWorkflowTest(unittest.TestCase):
    def test_parent_elects_after_binary_and_passes_original_predecessors(self):
        source = PARENT.read_text()
        plan = job(source, "sdk-android-package-plan")
        caller = job(source, "sdk-android-package-result")
        self.assertIn("family: android-package", plan)
        self.assertIn("needs.sdk-android-binary-result.result == 'success'", plan)
        self.assertIn("uses: ./.github/workflows/sdk-android-package-validation.yml", caller)
        for field in ("sdk-inputs", "sdk-core-validation-wave", "sdk-core-metadata-wave",
                      "sdk-android-binary-result", "sdk-android-package-plan"):
            self.assertIn(field, caller)
        for gate in ("sdk-completion", "sdk-parity", "merge-gate"):
            self.assertIn("sdk-android-package-result", job(source, gate).split("    needs:", 1)[1])

    def test_child_requires_fresh_binary_and_pins_nested_original(self):
        source = CHILD.read_text()
        worker = job(source, "sdk-android-package")
        collect = job(source, "sdk-collect-16")
        result = job(source, "sdk-android-package-result")
        for text in ("fromJSON(inputs.binaryWave).outputs.sdk_state_wave == '15'",
                     "fromJSON(inputs.binaryWave).outputs.binary_artifact_id != ''",
                     "fromJSON(inputs.binaryWave).outputs.binary_artifact_sha256 != ''",
                     "fromJSON(inputs.binaryWave).outputs.binary_original_context != ''",
                     "fromJSON(inputs.metadataWave).outputs.sdk_state_wave == '14'"):
            self.assertIn(text, worker)
        self.assertIn("ci.sdk_android_archive_provision", worker)
        archive_step = worker.split('      - id: android-archive\n', 1)[1].split('      - id: policy\n', 1)[0]
        self.assertIn('--plan "$GITHUB_WORKSPACE/${{ steps.selected.outputs.plan-path }}"', archive_step)
        self.assertIn("metadata_build_key == '' && 'android' || 'all'", worker)
        self.assertIn("ci.sdk_android_package_policy", worker)
        policy = worker.split('      - id: policy\n', 1)[1].split('      - id: native-archives\n', 1)[0]
        self.assertIn('GITHUB_TOKEN: ${{ github.token }}', policy.split('        run:', 1)[0])
        self.assertIn("uses: ./.github/actions/sdk-android-core14-caller", worker)
        self.assertIn("uses: ./.github/actions/sdk-android-maven-worker", worker)
        self.assertIn("phase: package", worker)
        self.assertIn("binary-artifact-id: ${{ fromJSON(inputs.binaryWave).outputs.binary_artifact_id }}", worker)
        self.assertIn("binary-original-workflow-path: .github/workflows/sdk-android-binary-validation.yml", worker)
        self.assertIn("binary-original-job-name: product-validation / sdk-android-binary-result / sdk-android-binary-android", worker)
        self.assertIn("sdk-worker-workflow-path: .github/workflows/sdk-android-package-validation.yml", collect)
        self.assertIn("sdk-worker-job-name: product-validation / sdk-android-package-result / sdk-android-package-android", collect)
        self.assertIn("select_native_state(needs, stage='android-package')", result)

    def test_qualified_package_reuses_captured_inputs_and_shared_scoped_controller(self):
        worker = job(CHILD.read_text(), 'sdk-android-package')
        self.assertIn("fromJSON(inputs.metadataWave).outputs.metadata_build_key == '' &&", worker)
        self.assertIn('ci.sdk_workflow maven-package', worker)
        qualified = worker.split('      - id: qualified\n', 1)[1].split('      - id: qualified-upload\n', 1)[0]
        self.assertIn('mode: execute', qualified)
        self.assertIn('--state-root "${{ steps.selected.outputs.state-root }}"', qualified)
        self.assertIn('--completed-frozen-policy', qualified)
        self.assertIn('--retained-sdk-inputs-source', qualified)
        self.assertIn('--binary-original-workflow-path .github/workflows/sdk-android-binary-validation.yml', qualified)
        self.assertNotIn('capture-transport', qualified)
        self.assertNotIn('capture-runtime-state', qualified)
        self.assertNotIn('core14', qualified)
        for step in ('native-archives', 'core14', 'package'):
            block = worker.split('      - id: ' + step + '\n', 1)[1]
            self.assertTrue(block.startswith("        if: fromJSON(inputs.metadataWave).outputs.metadata_build_key != ''\n"))
        outputs = worker.split('    outputs:', 1)[1].split('    steps:', 1)[0]
        self.assertIn("steps.qualified.outcome == 'success' && steps.qualified-upload.outcome == 'success'", outputs)


if __name__ == "__main__":
    unittest.main()
