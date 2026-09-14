"""JavaScript worker caller-policy routing, not product/tooling admission."""

from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest

from ci.tests import test_sdk_family_actions as action_harness


ROOT = Path(__file__).resolve().parents[2]


class SdkJavascriptToolingForwardingTest(unittest.TestCase):
    def setUp(self):
        self.action = (ROOT / '.github/actions/sdk-javascript-worker/action.yml').read_text()
        self.harness = action_harness.SdkFamilyActionsTest(methodName='runTest')
        self.harness.setUp()

    def test_optional_caller_policy_is_forwarded_to_original_capture_before_identity(self):
        inputs = self.action.split('inputs:\n', 1)[1].split('runs:\n', 1)[0]
        self.assertIn("  sdk-validation-tooling:\n    default: ''", inputs)
        capture = self.action.split('    - id: captured\n', 1)[1].split('    - id: identity\n', 1)[0]
        self.assertIn('sdk-validation-tooling: ${{ inputs.sdk-validation-tooling }}', capture)
        self.assertIn('sdk-state-wave: ${{ inputs.sdk-state-wave }}', capture)
        self.assertIn('state-wave: ${{ inputs.state-wave }}', capture)
        self.assertLess(self.action.index('- id: captured'), self.action.index('- id: identity'))
        self.assertLess(self.action.index('- id: identity'), self.action.index('./.github/actions/setup-kmp'))
        for forbidden in ('ci.tooling_discovery', 'ci.tooling_capture', '--tooling-java-executable', '--tooling-workflow-sha'):
            self.assertNotIn(forbidden, self.action)

    def test_actual_capture_shell_retains_optional_sdk_wave_and_exact_policy_argument(self):
        for wave, tooling in (('', ''), ('1', '/caller policy/tooling.json'), ('2', '/caller policy/tooling.json')):
            with self.subTest(wave=wave, tooling=tooling):
                result, arguments, token, output = self.harness.run_action('capture', STATE_PRODUCT='sdk',
                    SDK_STATE_WAVE=wave, SDK_VALIDATION_TOOLING=tooling)
                self.assertEqual(0, result.returncode, result.stderr)
                selected = (['--sdk-state-wave', wave] if wave else [])
                if tooling:
                    selected += ['--sdk-validation-tooling', tooling]
                self.assertEqual(self.harness.capture_arguments(output, selected, sdk=True), arguments)
                self.assertEqual('synthetic environment-only token', token)

    def test_runtime_capture_forwards_policy_after_elected_component_arguments(self):
        policy = '/caller policy/tooling.json'
        for component in ('', 'jvm'):
            with self.subTest(component=component):
                selected = (['--component', component, '--phase', 'binary', '--target', 'jvm',
                             '--expected-build-key', 'sha256:' + 'a' * 64] if component else [])
                result, arguments, token, output = self.harness.run_action('capture',
                    STATE_PRODUCT='runtime', SDK_VALIDATION_TOOLING=policy, COMPONENT=component,
                    PHASE='binary' if component else '', TARGET='jvm' if component else '',
                    BUILD_KEY='sha256:' + 'a' * 64 if component else '')
                self.assertEqual(0, result.returncode, result.stderr)
                selected += ['--sdk-validation-tooling', policy]
                self.assertEqual(self.harness.capture_arguments(output, selected, sdk=False), arguments)

    def test_actual_execution_shell_preserves_both_phases_and_optional_policy_without_word_splitting(self):
        block = self.action.split('    - name: Execute exact SDK phase within verified original input lifetimes\n', 1)[1].split('\n    - ', 1)[0]
        self.assertIn('SDK_VALIDATION_TOOLING: ${{ inputs.sdk-validation-tooling }}', block)
        script = textwrap.dedent(block.split('      run: |\n', 1)[1])
        self.assertIn('${selected[@]+"${selected[@]}"}', script)
        with tempfile.TemporaryDirectory(prefix='javascript-tooling-shell-') as temporary:
            root = Path(temporary)
            binary = root / 'bin'
            binary.mkdir()
            python = binary / 'python3'
            python.write_text('#!/bin/sh\nprintf \'%s\\0\' "$@" > "$RECORDED_ARGS"\nexit "${PYTHON_EXIT:-0}"\n')
            python.chmod(0o700)
            recorded = root / 'argv'
            base = {'PATH': str(binary), 'RECORDED_ARGS': str(recorded), 'PLAN': '/original plan/impact.json',
                'DISCOVERY': '/original discovery', 'STATE': '/original state', 'GITHUB_WORKSPACE': str(root),
                'BUILD_KEY': 'sha256:' + 'a' * 64, 'SDK_INPUTS_ID': '71',
                'SDK_INPUTS_SHA256': 'sha256:' + 'b' * 64, 'TRUSTED_WORKFLOW_SHA': 'c' * 40}
            for phase in ('package', 'validation'):
                for policy in ('', '/caller policy/with spaces.json'):
                    with self.subTest(phase=phase, policy=policy):
                        environment = dict(base, PHASE=phase, SDK_VALIDATION_TOOLING=policy)
                        result = subprocess.run([self.harness.shell, '--noprofile', '--norc', '-c', script],
                            cwd=root, env=environment, capture_output=True, text=True)
                        self.assertEqual(0, result.returncode, result.stderr)
                        arguments = recorded.read_bytes().decode().split('\0')[:-1]
                        expected = ['-B', '-m', 'ci.sdk_workflow', 'javascript',
                            '--plan', base['PLAN'], '--discovery-root', base['DISCOVERY'], '--state-root', base['STATE'],
                            '--destination', str(root / 'build/sdk-worker'), '--repository-root', str(root),
                            '--phase', phase, '--expected-build-key', base['BUILD_KEY'], '--artifact-id', base['SDK_INPUTS_ID'],
                            '--artifact-sha256', base['SDK_INPUTS_SHA256'], '--trusted-workflow-sha', base['TRUSTED_WORKFLOW_SHA'],
                            '--keyring', str(root / 'gradle/release/product-signing-keys.json'),
                            '--keys-directory', str(root / 'gradle/release/keys')]
                        if policy:
                            expected += ['--sdk-validation-tooling', policy]
                        self.assertEqual(expected, arguments)
            result = subprocess.run([self.harness.shell, '--noprofile', '--norc', '-c', script],
                cwd=root, env=dict(base, PHASE='validation', SDK_VALIDATION_TOOLING='/caller/policy.json', PYTHON_EXIT='17'),
                capture_output=True, text=True)
            self.assertEqual(17, result.returncode)


if __name__ == '__main__':
    unittest.main()
