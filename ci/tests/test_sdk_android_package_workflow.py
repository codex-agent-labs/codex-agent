"""Android package child keeps fresh original authority and a fail-closed reuse edge."""

from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import textwrap
from unittest.mock import patch
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

    def test_child_routes_fresh_or_native_binary_and_pins_nested_original(self):
        source = CHILD.read_text()
        worker = job(source, "sdk-android-package")
        collect = job(source, "sdk-collect-16")
        result = job(source, "sdk-android-package-result")
        for text in ("fromJSON(inputs.binaryWave).outputs.sdk_state_wave == '15'",
                     "fromJSON(inputs.binaryWave).outputs.binary_build_key == '' &&",
                     "fromJSON(inputs.binaryWave).outputs.routing != ''",
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
        self.assertIn("binary-artifact-id: ${{ steps.policy.outputs.binary-artifact-id }}", worker)
        self.assertIn('if [ -n "$BINARY_ID$BINARY_SHA256$BINARY_CONTEXT" ]; then', policy)
        self.assertIn("binary-original-workflow-path: .github/workflows/sdk-android-binary-validation.yml", worker)
        self.assertIn("binary-original-job-name: product-validation / sdk-android-binary-result / sdk-android-binary-android", worker)
        self.assertIn("sdk-worker-workflow-path: .github/workflows/sdk-android-package-validation.yml", collect)
        self.assertIn("sdk-worker-job-name: product-validation / sdk-android-package-result / sdk-android-package-android", collect)
        self.assertIn("select_native_state(needs, stage='android-package')", result)

    def test_native_archive_shell_passes_absolute_plan_to_strict_provider(self):
        from ci import sdk_core_native_archive_provision as provider

        block = job(CHILD.read_text(), 'sdk-android-package').split(
            '      - id: native-archives\n', 1)[1].split('      - id: core14\n', 1)[0]
        script = textwrap.dedent(block.split('        run: |\n', 1)[1])
        relative_plan = 'build/runtime-input/original/product-resume-inputs/plan/impact-plan.json'
        script = script.replace('${{ steps.selected.outputs.plan-path }}', relative_plan)
        with tempfile.TemporaryDirectory(prefix='android-native-plan-') as temporary:
            base = Path(temporary).resolve()
            repository, scratch = base / 'repository', base / 'scratch'
            repository.mkdir(); scratch.mkdir()
            plan = repository / relative_plan
            plan.parent.mkdir(parents=True); plan.write_bytes(b'plan boundary fixture')
            calls = base / 'calls.jsonl'
            # Execute the actual shell argument construction without acquiring archives.
            interceptor = """python3() {
              "$TEST_PYTHON" -c 'import json, os, sys
with open(os.environ["TEST_CALLS"], "a") as stream:
    stream.write(json.dumps(sys.argv[1:])+"\\n")
print(sys.argv[sys.argv.index("--destination")+1])' "$@"
            }
"""
            result = subprocess.run(['bash', '-c', interceptor + script], cwd=repository,
                env={**os.environ, 'GITHUB_WORKSPACE': str(repository), 'RUNNER_TEMP': str(scratch),
                     'GITHUB_OUTPUT': str(base / 'outputs'), 'TEST_PYTHON': sys.executable,
                     'TEST_CALLS': str(calls)}, capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stderr)
            arguments = [json.loads(line) for line in calls.read_text().splitlines()]
            self.assertEqual(4, len(arguments))
            class ReachedPlanValidation(Exception):
                pass
            with patch.object(provider.product_reuse, '_validate_plan', side_effect=ReachedPlanValidation) as validate, \
                    patch.object(provider, '_open_archive') as download:
                for argv in arguments:
                    self.assertEqual(['-B', '-m', 'ci.sdk_core_native_archive_provision'], argv[:3])
                    with self.assertRaises(ReachedPlanValidation):
                        provider.main(argv[3:])
                self.assertEqual(4, validate.call_count)
                self.assertTrue(all(call.args == (plan, repository) for call in validate.call_args_list))
                download.assert_not_called()

    def test_qualified_package_reuses_captured_inputs_and_shared_scoped_controller(self):
        worker = job(CHILD.read_text(), 'sdk-android-package')
        self.assertIn("fromJSON(inputs.metadataWave).outputs.metadata_build_key == '' &&", worker)
        self.assertIn('ci.sdk_workflow maven-package', worker)
        qualified = worker.split('      - id: qualified\n', 1)[1].split('      - id: qualified-upload\n', 1)[0]
        self.assertIn('mode: execute', qualified)
        self.assertIn('--state-root "${{ steps.selected.outputs.state-root }}"', qualified)
        self.assertIn('--completed-frozen-policy', qualified)
        self.assertIn('--retained-sdk-inputs-source', qualified)
        self.assertIn('BINARY_ID: ${{ steps.policy.outputs.binary-artifact-id }}', qualified)
        self.assertIn('BINARY_SHA256: ${{ steps.policy.outputs.binary-artifact-sha256 }}', qualified)
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
