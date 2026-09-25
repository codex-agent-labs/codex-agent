"""Workflow routing checks; synthetic Java paths are not hosted-runner evidence."""

from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[2]
NAMES = ('contract-continuation', 'runtime-linux-arm64-supervisor',
         *(f'runtime-workers-{i}' for i in range(1, 5)),
         *(f'runtime-collect-{i}' for i in range(1, 6)),
         'runtime-continuation', 'runtime-aggregate', 'runtime-aggregate-continuation',
         'sdk-ios-binary-plan', 'sdk-ios-binary', 'sdk-collect-3')


class RuntimeToolingWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / '.github/workflows/product-validation.yml').read_text()
        cls.contract = (ROOT / '.github/workflows/contract-validation.yml').read_text()

    def job(self, name):
        source = self.contract if name == 'contract-continuation' else self.source
        return re.search(r'^  ' + name + r':\n.*?(?=^  [a-z][a-z0-9-]*:\n)',
                         source, re.M | re.S).group()

    def test_every_replay_job_captures_immutable_locator_locally_before_consumption(self):
        for name in NAMES:
            job = self.job(name)
            with self.subTest(job=name):
                header = job.split('    steps:', 1)[0]
                self.assertIn('product-tooling' if name == 'contract-continuation' else
                              'contract-validation', header)
                self.assertIn('always()', header)
                self.assertNotIn('tooling-policy', header)
                self.assertEqual(1, job.count('uses: ./.github/actions/capture-sdk-tooling'))
                self.assertIn('fetch-depth: 0', job)
                capture = job.index('      - id: tooling')
                for field in ('artifact_id', 'artifact_sha256', 'transport_producer'):
                    source_field = field if name == 'contract-continuation' else 'tooling_' + field
                    self.assertIn(('needs.product-tooling.outputs.' if name == 'contract-continuation'
                                   else 'needs.contract-validation.outputs.') + source_field, job)
                self.assertIn('policy-revision: ${{ fromJSON(inputs.planOutputs).validation_commit }}'
                              if name == 'contract-continuation' else
                              'policy-revision: ${{ needs.plan.outputs.validation_commit }}', job)
                self.assertNotIn('needs.sdk-plan', job)
                for step in re.split(r'(?=^      - )', job, flags=re.M):
                    if any('uses: ./.github/actions/' + action in step for action in (
                            'capture-runtime-state', 'run-runtime-product-phase', 'collect-runtime-wave',
                            'sdk-ios-binary-worker')):
                        self.assertLess(capture, job.index(step))
                        self.assertIn('sdk-validation-tooling: ${{ steps.tooling.outputs.tooling-policy }}', step)
                    if re.search(r'ci/(product_reuse.py (advance-contract|execute-runtime-)|runtime_workflow.py continuation)', step):
                        self.assertLess(capture, job.index(step))
                        self.assertIn('SDK_VALIDATION_TOOLING: ${{ steps.tooling.outputs.tooling-policy }}', step)
                        self.assertIn('--sdk-validation-tooling "$SDK_VALIDATION_TOOLING"', step)
                        self.assertIn('${tooling[@]+"${tooling[@]}"}', step)
        self.assertEqual(4, self.job('contract-continuation').count('ci/product_reuse.py advance-contract'))

    def test_installed_java_selection_uses_host_architecture_and_fails_when_missing(self):
        scripts = []
        for name in NAMES:
            step = self.job(name).split('      - name: Select installed caller Java for SDK tooling\n', 1)[1].split('      - id: tooling', 1)[0]
            scripts.append(textwrap.dedent(step.split('        run: |\n', 1)[1]))
        self.assertEqual(1, len(set(scripts)))
        with tempfile.TemporaryDirectory(prefix='runtime-java-selector-') as temporary:
            root = Path(temporary)
            for platform, arch, binary in (('Linux', 'ARM64', 'java'), ('macOS', 'X64', 'java'),
                                           ('Windows', 'X64', 'java.exe')):
                home = root / (platform + ' java home')
                (home / 'bin').mkdir(parents=True)
                (home / 'bin' / binary).touch()
                output = root / (platform + '.env')
                env = {'RUNNER_OS': platform, 'RUNNER_ARCH': arch, 'JAVA_HOME_17_' + arch: str(home),
                       'GITHUB_ENV': str(output)}
                with self.subTest(platform=platform):
                    result = subprocess.run([shutil.which('bash'), '-e', '-c', scripts[0]],
                                            env=env, capture_output=True, text=True)
                    self.assertEqual(0, result.returncode, result.stderr)
                    self.assertEqual('JAVA_HOME=' + str(home) + '\n', output.read_text())
            output = root / 'missing.env'
            result = subprocess.run([shutil.which('bash'), '-e', '-c', scripts[0]],
                env={'RUNNER_OS': 'Linux', 'RUNNER_ARCH': 'ARM64', 'GITHUB_ENV': str(output)},
                capture_output=True, text=True)
            self.assertNotEqual(0, result.returncode)
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
