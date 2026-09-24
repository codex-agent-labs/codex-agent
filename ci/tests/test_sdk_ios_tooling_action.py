"""iOS caller policy routing only; no compiler, signing or host acceptance."""

import os
from itertools import product
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest
from unittest.mock import patch

from ci import sdk_workflow as workflow
from ci.tests import test_sdk_family_actions as actions
from ci.tests import test_sdk_ios_binary_cli as cli
from ci.tests import test_sdk_ios_binary_execution as execution


ROOT = Path(__file__).resolve().parents[2]


class SdkIosToolingActionTest(unittest.TestCase):
    def setUp(self):
        self.action = (ROOT / '.github/actions/sdk-ios-binary-worker/action.yml').read_text()
        self.harness = actions.SdkFamilyActionsTest(methodName='runTest')
        self.harness.setUp()

    def test_local_optional_capture_precedes_identity_and_setup(self):
        self.assertIn("  sdk-validation-tooling:\n    default: ''", self.action)
        self.assertIn("  sdk-apple-validation-policy:\n    default: ''", self.action)
        capture = self.action.split('    - id: captured\n', 1)[1].split('    - id: identity\n', 1)[0]
        self.assertIn('sdk-validation-tooling: ${{ inputs.sdk-validation-tooling }}', capture)
        self.assertIn('sdk-apple-validation-policy: ${{ inputs.sdk-apple-validation-policy }}', capture)
        self.assertIn('product: sdk-ios-binary', capture)
        self.assertLess(self.action.index('- id: captured'), self.action.index('- id: identity'))
        self.assertLess(self.action.index('- id: identity'), self.action.index('./.github/actions/setup-kmp'))
        for forbidden in ('capture-sdk-tooling', 'ci.tooling_capture', 'ci.tooling_discovery'):
            self.assertNotIn(forbidden, self.action)
        for policy, apple in product(('', '/caller policy/tooling.json'), ('', '/caller policy/apple.json')):
            result, args, _, output = self.harness.run_action('capture', STATE_PRODUCT='sdk-ios-binary',
                SDK_VALIDATION_TOOLING=policy, SDK_APPLE_VALIDATION_POLICY=apple)
            self.assertEqual(0, result.returncode, result.stderr)
            selected = ['--ios-binary'] + (['--sdk-validation-tooling', policy] if policy else [])
            if apple:
                selected += ['--sdk-apple-validation-policy', apple]
            self.assertEqual(self.harness.capture_arguments(output, selected, sdk=True), args)

    def test_actual_execution_shell_keeps_upload_tuple_and_optional_policy(self):
        block = self.action.split('    - name: Execute exact iOS SDK binary within verified original input lifetimes\n', 1)[1].split('\n    - ', 1)[0]
        self.assertIn('SDK_VALIDATION_TOOLING: ${{ inputs.sdk-validation-tooling }}', block)
        self.assertIn('SDK_APPLE_VALIDATION_POLICY: ${{ inputs.sdk-apple-validation-policy }}', block)
        script = textwrap.dedent(block.split('      run: |\n', 1)[1])
        with tempfile.TemporaryDirectory(prefix='ios-tooling-shell-') as temporary:
            root = Path(temporary)
            binary = root / 'bin'
            binary.mkdir()
            python = binary / 'python3'
            python.write_text('#!/bin/sh\nprintf \'%s\\0\' "$@" > "$RECORDED_ARGS"\nexit "${PYTHON_EXIT:-0}"\n')
            python.chmod(0o700)
            record = root / 'argv'
            base = {'PATH': str(binary), 'RECORDED_ARGS': str(record), 'GITHUB_WORKSPACE': str(root),
                'PLAN': '/original plan', 'DISCOVERY': '/original discovery', 'STATE': '/original state',
                'BUILD_KEY': 'sha256:' + 'a' * 64, 'TRUSTED_WORKFLOW_SHA': 'b' * 40}
            lanes = (('native-tests', 'NATIVE_TESTS'), ('rust-device', 'RUST_DEVICE'), ('rust-simulator', 'RUST_SIMULATOR'))
            for number, (_, variable) in enumerate(lanes, 1):
                base[variable + '_ID'] = str(number)
                base[variable + '_SHA256'] = 'sha256:' + str(number) * 64
            for (policy, status), apple in product((('', 0), ('/caller policy/tooling.json', 0),
                                                    ('/caller/policy.json', 17)),
                                                   (None, '', '/caller policy/apple with spaces.json')):
                environment = dict(base, SDK_VALIDATION_TOOLING=policy, PYTHON_EXIT=str(status))
                if apple is not None:
                    environment['SDK_APPLE_VALIDATION_POLICY'] = apple
                result = subprocess.run([self.harness.shell, '--noprofile', '--norc', '-c', script],
                    cwd=root, env=environment,
                    capture_output=True, text=True)
                self.assertEqual(status, result.returncode, result.stderr)
                expected = ['-B', '-m', 'ci.sdk_workflow', 'ios-binary', '--plan', base['PLAN'],
                    '--discovery-root', base['DISCOVERY'], '--state-root', base['STATE'],
                    '--destination', str(root / 'build/sdk-ios-worker'), '--repository-root', str(root),
                    '--expected-build-key', base['BUILD_KEY'], '--trusted-workflow-sha', base['TRUSTED_WORKFLOW_SHA']]
                for lane, variable in lanes:
                    expected += ['--' + lane + '-artifact-id', base[variable + '_ID'],
                                 '--' + lane + '-artifact-sha256', base[variable + '_SHA256']]
                if policy:
                    expected += ['--sdk-validation-tooling', policy]
                if apple:
                    expected += ['--sdk-apple-validation-policy', apple]
                self.assertEqual(expected, record.read_bytes().decode().split('\0')[:-1])

    def test_cli_canonical_policy_and_legacy_omission(self):
        fixture = cli.SdkIosBinaryCliTest(methodName='runTest')
        fixture.setUp()
        with tempfile.TemporaryDirectory(prefix='ios-tooling-cli-') as temporary:
            path = Path(temporary).resolve() / 'caller policy.json'
            policy = {'evidence': '/caller/original-tooling'}
            path.write_bytes(workflow.canonical_json_bytes(policy))
            for supplied in (False, True):
                with patch.object(workflow, 'execute_ios_binary') as execute, patch.dict(os.environ, {'GITHUB_TOKEN': 'caller'}, clear=True):
                    argv = fixture.argv() + (['--sdk-validation-tooling', str(path)] if supplied else [])
                    self.assertEqual(0, workflow.main(argv))
                    if supplied:
                        self.assertEqual(policy, execute.call_args.kwargs['sdk_validation_tooling'])
                    else:
                        self.assertNotIn('sdk_validation_tooling', execute.call_args.kwargs)
                    self.assertEqual('caller', execute.call_args.kwargs['token'])
                    self.assertEqual(3, len(execute.call_args.kwargs['native_uploads']))
            path.write_bytes(b'{"evidence":"a","evidence":"b"}\n')
            with patch.object(workflow, 'execute_ios_binary') as execute, self.assertRaises(SystemExit) as error:
                workflow.main(fixture.argv() + ['--sdk-validation-tooling', str(path)])
            self.assertEqual(2, error.exception.code)
            execute.assert_not_called()

    def test_controller_lifetime_and_original_replay_receive_same_caller_policy(self):
        for policy in (None, {'evidence': '/caller/original-tooling'}):
            with self.subTest(policy=policy):
                fixture = execution.SdkIosBinaryExecutionTest(methodName='runTest')
                self.addCleanup(fixture.doCleanups)
                fixture.setUp()
                if policy is not None:
                    fixture.options['sdk_validation_tooling'] = policy
                fixture.invoke()
                self.assertEqual(['enter', 'worker', 'exit-check', 'exited', 'finalize'], fixture.events)
                replay_destination = fixture.repository / 'build/replay-inputs'
                # Stop only at authenticated state replay, before semantic admission.
                with patch.object(workflow.product_reuse, '_verified_product_state', side_effect=ValueError('replay sentinel')) as replay:
                    with self.assertRaisesRegex(ValueError, 'replay sentinel'):
                        with workflow.verified_ios_binary_inputs(fixture.plan, fixture.discovery, fixture.state,
                                replay_destination, **fixture.options):
                            self.fail('Rejected replay must not yield')
                    replay.assert_called_once_with(fixture.plan, fixture.discovery, fixture.state,
                        fixture.repository, fixture.options['environ'], policy,
                        sdk_original_workflow_sha=fixture.options['trusted_workflow_sha'])
                self.assertFalse(replay_destination.exists())


if __name__ == '__main__':
    unittest.main()
