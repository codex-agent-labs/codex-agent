"""Actual action shell routing only; no preparation/tooling admission is mocked as proof."""

from itertools import product
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest

from ci.tests import test_sdk_family_actions as action_harness


ROOT = Path(__file__).resolve().parents[2]


class NativePrepareToolingActionTest(unittest.TestCase):
    def setUp(self):
        self.action = (ROOT / '.github/actions/sdk-native-prepare/action.yml').read_text()
        self.harness = action_harness.SdkFamilyActionsTest(methodName='runTest')
        self.harness.setUp()

    def test_optional_policy_stays_local_and_capture_precedes_setup(self):
        inputs, outputs = self.action.split('outputs:\n', 1)
        self.assertIn("  sdk-validation-tooling:\n    default: ''", inputs)
        self.assertIn("  sdk-apple-validation-policy:\n    default: ''", inputs)
        self.assertNotIn('tooling', outputs.split('runs:\n', 1)[0])
        self.assertNotIn('apple-policy', outputs.split('runs:\n', 1)[0])
        capture = self.action.split('    - id: captured\n', 1)[1].split('    - id: identity\n', 1)[0]
        self.assertIn("sdk-family: ${{ format('native-{0}', inputs.preparation-phase) }}", capture)
        self.assertIn("  preparation-phase:\n    default: 'package'", inputs)
        self.assertIn('sdk-validation-tooling: ${{ inputs.sdk-validation-tooling }}', capture)
        self.assertIn('sdk-apple-validation-policy: ${{ inputs.sdk-apple-validation-policy }}', capture)
        for name in ('state-wave', 'sdk-state-wave'):
            self.assertIn(f'{name}: ${{{{ inputs.{name} }}}}', capture)
        self.assertLess(self.action.index('- id: captured'), self.action.index('- id: identity'))
        self.assertLess(self.action.index('- id: identity'), self.action.index('./.github/actions/setup-kmp'))
        for forbidden in ('ci.tooling_discovery', 'ci.tooling_capture', 'capture-sdk-tooling'):
            self.assertNotIn(forbidden, self.action)

    def test_shared_capture_preserves_family_wave_and_optional_policy(self):
        for (wave, policy), apple in product((('', ''), ('2', '/caller policy/tooling.json')),
                                             ('', '/caller policy/apple.json')):
            with self.subTest(wave=wave, policy=policy, apple=apple):
                result, arguments, _, output = self.harness.run_action('capture', STATE_PRODUCT='sdk',
                    SDK_FAMILY='native-package', SDK_STATE_WAVE=wave, SDK_VALIDATION_TOOLING=policy,
                    SDK_APPLE_VALIDATION_POLICY=apple)
                self.assertEqual(0, result.returncode, result.stderr)
                selected = ['--sdk-state-wave', wave] if wave else []
                selected += ['--family', 'native-package']
                if policy:
                    selected += ['--sdk-validation-tooling', policy]
                if apple:
                    selected += ['--sdk-apple-validation-policy', apple]
                self.assertEqual(self.harness.capture_arguments(output, selected, sdk=True), arguments)

    def test_execution_exact_legacy_and_policy_arguments_and_failure(self):
        block = self.action.split('    - id: execute\n', 1)[1].split('\n    - ', 1)[0]
        self.assertIn('SDK_VALIDATION_TOOLING: ${{ inputs.sdk-validation-tooling }}', block)
        self.assertIn('SDK_APPLE_VALIDATION_POLICY: ${{ inputs.sdk-apple-validation-policy }}', block)
        script = textwrap.dedent(block.split('      run: |\n', 1)[1])
        with tempfile.TemporaryDirectory(prefix='native-prepare-tooling-shell-') as temporary:
            root = Path(temporary)
            binary = root / 'bin'
            binary.mkdir()
            python = binary / 'python3'
            python.write_text('#!/bin/sh\nprintf \'%s\\0\' "$@" > "$RECORDED_ARGS"\nexit "${PYTHON_EXIT:-0}"\n')
            python.chmod(0o700)
            recorded = root / 'argv'
            base = {'PATH': str(binary), 'RECORDED_ARGS': str(recorded), 'PLAN': '/original plan/impact.json',
                'DISCOVERY': '/original discovery', 'STATE': '/original state', 'GITHUB_WORKSPACE': str(root),
                'COMPONENT': 'csharp', 'BUILD_KEY': 'sha256:' + 'a' * 64, 'SDK_INPUTS_ID': '71',
                'PREPARATION_PHASE': 'package', 'PREPARATION_TARGET': 'desktop',
                'SDK_INPUTS_SHA256': 'sha256:' + 'b' * 64, 'TRUSTED_WORKFLOW_SHA': 'c' * 40}
            for (policy, status), apple in product((('', 0), ('/caller policy/with spaces.json', 0),
                                                    ('/caller/policy.json', 17)),
                                                   (None, '', '/caller policy/apple with spaces.json')):
                with self.subTest(policy=policy, status=status, apple=apple):
                    environment = dict(base, SDK_VALIDATION_TOOLING=policy, PYTHON_EXIT=str(status))
                    if apple is not None:
                        environment['SDK_APPLE_VALIDATION_POLICY'] = apple
                    result = subprocess.run([self.harness.shell, '--noprofile', '--norc', '-c', script],
                        cwd=root, env=environment,
                        capture_output=True, text=True)
                    self.assertEqual(status, result.returncode, result.stderr)
                    expected = ['-B', '-m', 'ci.sdk_workflow', 'native-prepare',
                        '--plan', base['PLAN'], '--discovery-root', base['DISCOVERY'], '--state-root', base['STATE'],
                        '--destination', str(root / 'build/sdk-native-prepare'), '--repository-root', str(root),
                        '--component', base['COMPONENT'], '--expected-build-key', base['BUILD_KEY'],
                        '--preparation-phase', 'package', '--preparation-target', 'desktop',
                        '--artifact-id', base['SDK_INPUTS_ID'], '--artifact-sha256', base['SDK_INPUTS_SHA256'],
                        '--trusted-workflow-sha', base['TRUSTED_WORKFLOW_SHA'],
                        '--keyring', str(root / 'gradle/release/product-signing-keys.json'),
                        '--keys-directory', str(root / 'gradle/release/keys')]
                    if policy:
                        expected += ['--sdk-validation-tooling', policy]
                    if apple:
                        expected += ['--sdk-apple-validation-policy', apple]
                    self.assertEqual(expected, recorded.read_bytes().decode().split('\0')[:-1])


if __name__ == '__main__':
    unittest.main()
