"""Execute routing shells only; no worker collection or tooling trust is claimed."""

import unittest

from ci.tests import test_sdk_family_actions as fixtures


class RuntimeCollectToolingActionTest(unittest.TestCase):
    def setUp(self):
        self.harness = fixtures.SdkFamilyActionsTest(methodName='runTest')
        self.harness.setUp()

    def test_runtime_capture_and_collection_keep_exact_wave_and_optional_policy(self):
        for predecessor in ('0', '3', '4'):
            for policy in ('', '/caller policy/tooling.json'):
                with self.subTest(predecessor=predecessor, policy=policy):
                    selected = ['--sdk-validation-tooling', policy] if policy else []
                    result, args, token, output = self.harness.run_action('capture',
                        STATE_WAVE=predecessor, SDK_VALIDATION_TOOLING=policy)
                    self.assertEqual(0, result.returncode, result.stderr)
                    self.assertEqual(self.harness.capture_arguments(output, selected,
                        state_wave=predecessor), args)
                    self.assertEqual('synthetic environment-only token', token)
                    wave = str(int(predecessor) + 1)
                    result, args, token, output = self.harness.run_action('collect',
                        STATE_WAVE=predecessor, WAVE=wave, SDK_VALIDATION_TOOLING=policy)
                    self.assertEqual(0, result.returncode, result.stderr)
                    self.assertEqual(self.harness.collect_arguments(output,
                        ['--state-wave', predecessor, *selected], wave=wave), args)
                    self.assertEqual('synthetic environment-only token', token)

    def test_sdk_scopes_unchanged_and_runtime_rejects_sdk_family(self):
        policy = '/caller policy/tooling.json'
        for product, family, selected in (
                ('sdk', '', []), ('sdk', 'native-package', ['--family', 'native-package']),
                ('sdk-ios-binary', '', ['--ios-binary'])):
            with self.subTest(product=product, family=family):
                result, args, _, output = self.harness.run_action('collect', PRODUCT=product,
                    SDK_FAMILY=family, SDK_VALIDATION_TOOLING=policy)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual(self.harness.collect_arguments(output,
                    [*selected, '--sdk-validation-tooling', policy], sdk=True), args)
        for action in ('capture', 'collect'):
            with self.subTest(action=action):
                result, args, _, _ = self.harness.run_action(action,
                    SDK_FAMILY='native-package', SDK_VALIDATION_TOOLING=policy)
                self.assertNotEqual(0, result.returncode)
                self.assertIsNone(args)

    def test_capture_forwarding_locality_and_collection_failure_are_preserved(self):
        source = self.harness.collect
        capture = source.split('    - id: captured\n', 1)[1].split('    - id: collect\n', 1)[0]
        self.assertIn('sdk-validation-tooling: ${{ inputs.sdk-validation-tooling }}', capture)
        for name in ('product', 'state-wave', 'sdk-state-wave', 'sdk-family'):
            self.assertIn(f'{name}: ${{{{ inputs.{name} }}}}', capture)
        outputs = source.split('outputs:\n', 1)[1].split('runs:\n', 1)[0]
        self.assertNotIn('tooling', outputs)
        for forbidden in ('capture-sdk-tooling', 'ci.tooling_capture', 'ci.tooling_discovery'):
            self.assertNotIn(forbidden, source)
        result, args, _, _ = self.harness.run_action('collect',
            SDK_VALIDATION_TOOLING='/caller/tooling.json', PYTHON_EXIT='17')
        self.assertEqual(17, result.returncode)
        self.assertIn('--sdk-validation-tooling', args)
        self.assertIn("    - if: always()", source)
        self.assertIn("failure() && 'build/runtime-next' || 'build/runtime-next/collection'", source)


if __name__ == '__main__':
    unittest.main()
