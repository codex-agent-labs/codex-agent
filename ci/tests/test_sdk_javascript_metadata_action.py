"""Executed composite guards/argv; source, content, host and HTTP are not admitted."""

from copy import deepcopy
import json
import subprocess
import sys
import unittest
from unittest.mock import patch

from ci.tests import test_sdk_native_validation_worker_action as action_fixture
from ci import sdk_javascript_metadata_workflow as controller
from ci.products.inventory import canonical_json_bytes


class SdkJavaScriptMetadataActionTest(unittest.TestCase):
    def setUp(self):
        self.f = action_fixture.SdkNativeValidationWorkerActionTest(methodName="runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.f.action = (action_fixture.ROOT / '.github/actions/sdk-javascript-metadata-worker/action.yml').read_text()
        self.f.current.update(component='javascript', phase='metadata', target='node')
        self.f.environment.update(VALIDATION_ARTIFACT_ID='93', VALIDATION_ARTIFACT_SHA256='sha256:' + '9' * 64)
        self.f.environment['MATRIX'] = json.dumps({'include': [self.f.current]})

    def test_policy_and_exact_election_precede_setup_and_whole_worker_is_retained(self):
        action = self.f.action
        for first, second in (('- id: policy', '- id: captured'), ('- id: captured', '- id: identity'),
                              ('- id: identity', './.github/actions/setup-kmp')):
            self.assertLess(action.index(first), action.index(second))
        capture = self.f.block('captured')
        self.assertIn('sdk-family: javascript-metadata', capture)
        for field in ('plan-id', 'artifact-id', 'artifact-sha256', 'state-wave', 'sdk-state-wave',
                      'trusted-workflow-sha', 'sdk-validation-tooling', 'sdk-apple-validation-policy'):
            self.assertIn(field + ': ${{ inputs.' + field + ' }}', capture)
        self.assertIn("product-worker: 'true'", action)
        self.assertIn("if: always() && steps.identity.outcome == 'success'", action)
        self.assertIn('name: codex-agent-sdk-worker-javascript-metadata-node-${{ steps.identity.outputs.key_hex }}-${{ inputs.tree }}-attempt-${{ github.run_attempt }}', action)
        self.assertIn('path: build/sdk-worker\n', action)
        self.assertIn('include-hidden-files: true', action)
        self.assertNotIn('original-consumer-directory:', action)
        self.assertNotIn('capture-sdk-tooling', action)
        self.assertNotIn('secrets.', action)
        self.f.execute('policy')
        with patch.object(action_fixture.native_wrappers, 'host_classifier', return_value='linux-x64'):
            self.f.execute('identity')
        self.assertIn('policy_revision=' + 'c' * 40, self.f.output.read_text())

    def test_bad_policy_election_host_tree_and_policy_mutation_fail_before_output(self):
        f = self.f
        for field in ('evidence', 'publicKey', 'javaExecutable'):
            f.policy_path.write_bytes(canonical_json_bytes(dict(f.policy, **{field: None})))
            with self.subTest(field=field), self.assertRaises(ValueError):
                f.execute('policy')
            self.assertFalse(f.output.exists())
        f.policy_path.write_bytes(canonical_json_bytes(f.policy))
        original = deepcopy(f.current)
        for changes in ({'phase': 'validation'}, {'target': 'desktop'}, {'runnerArch': 'ARM64'},
                        {'buildKey': 'sha256:' + '0' * 64}):
            f.environment['MATRIX'] = json.dumps({'include': [dict(original, **changes)]})
            with self.subTest(changes=changes), patch.object(action_fixture.native_wrappers, 'host_classifier', return_value='linux-x64'), self.assertRaises(ValueError):
                f.execute('identity')
            self.assertFalse(f.output.exists())
        f.environment['MATRIX'] = json.dumps({'include': [original, original]})
        with patch.object(action_fixture.native_wrappers, 'host_classifier', return_value='linux-x64'), self.assertRaises(ValueError):
            f.execute('identity')
        f.environment['MATRIX'] = json.dumps({'include': [original]})
        with patch.object(action_fixture.native_wrappers, 'host_classifier', return_value='macos-arm64'), self.assertRaises(ValueError):
            f.execute('identity')
        f.environment['TREE'] = '0' * 40
        with patch.object(action_fixture.native_wrappers, 'host_classifier', return_value='linux-x64'), self.assertRaises(ValueError):
            f.execute('identity')
        f.environment['TREE'] = 'b' * 40
        f.policy_path.write_bytes(canonical_json_bytes(dict(f.policy, evidence='/changed')))
        with patch('subprocess.run') as run, self.assertRaises(ValueError):
            f.execute('execute')
        run.assert_not_called()
        self.assertFalse(f.output.exists())

    def test_fixed_command_passes_original_uploads_and_policy_through_actual_cli(self):
        f = self.f
        for trust in ('release', 'development'):
            with self.subTest(trust=trust):
                policy = dict(f.policy, requiredTrustDomain=trust)
                if trust == 'development':
                    policy.update(keyring=None, keysDirectory=None)
                f.policy_path.write_bytes(canonical_json_bytes(policy))
                f.output.unlink(missing_ok=True)
                f.execute('policy')
                f.environment['POLICY_SHA256'] = f.output.read_text().strip().split('=', 1)[1]
                with patch('subprocess.run') as run:
                    f.execute('execute')
                command = run.call_args.args[0]
                self.assertEqual([sys.executable, '-B', '-m', 'ci.sdk_workflow', 'javascript-metadata'], command[:5])
                self.assertEqual({'cwd': f.root, 'check': True}, run.call_args.kwargs)
                with patch.object(controller, 'execute') as execute:
                    self.assertEqual(0, controller.main(command[5:]))
                arguments = execute.call_args.kwargs
                self.assertEqual(93, arguments['validation_artifact_id'])
                self.assertEqual(f.environment['VALIDATION_ARTIFACT_SHA256'], arguments['validation_artifact_sha256'])
                self.assertEqual(92, arguments['sdk_inputs_artifact_id'])
                self.assertEqual(f.environment['SDK_INPUTS_SHA256'], arguments['sdk_inputs_artifact_sha256'])
                self.assertEqual(f.root / 'current/state', arguments['state'])
                self.assertEqual(f.root / 'build/sdk-worker', arguments['destination'])
                self.assertEqual(f.environment['POLICY_REVISION'], arguments['policy_revision'])
                self.assertEqual(trust, arguments['required_trust_domain'])
                self.assertEqual(f.root / 'evidence', arguments['tooling_evidence'])
                self.assertEqual(f.root / 'java', arguments['java_executable'])
                self.assertEqual(None if trust == 'development' else f.root / 'keyring.json', arguments['tooling_keyring'])
                self.assertNotIn('original_consumer_directory', arguments)

    def test_absent_locator_requests_original_discovery_and_unpaired_locator_rejects(self):
        self.f.environment.update(VALIDATION_ARTIFACT_ID='', VALIDATION_ARTIFACT_SHA256='')
        with patch('subprocess.run') as run:
            self.f.execute('execute')
        command = run.call_args.args[0]
        with patch.object(controller, 'execute') as execute:
            self.assertEqual(0, controller.main(command[5:]))
        self.assertIsNone(execute.call_args.kwargs['validation_artifact_id'])
        self.assertIsNone(execute.call_args.kwargs['validation_artifact_sha256'])
        self.f.environment['VALIDATION_ARTIFACT_ID'] = '93'
        with patch('subprocess.run') as run, self.assertRaisesRegex(ValueError, 'supplied together'):
            self.f.execute('execute')
        run.assert_not_called()

    def test_process_failure_propagates_without_claiming_success(self):
        with patch('subprocess.run', side_effect=subprocess.CalledProcessError(17, ['fixed-controller'])), \
                self.assertRaises(subprocess.CalledProcessError):
            self.f.execute('execute')
        self.assertFalse(self.f.output.exists())

    def test_optional_apple_policy_is_forwarded_only_when_supplied(self):
        self.assertIn("  sdk-apple-validation-policy:\n    default: ''", self.f.action)
        self.assertIn('SDK_APPLE_VALIDATION_POLICY: ${{ inputs.sdk-apple-validation-policy }}',
                      self.f.block('execute'))
        for policy in ('', '/caller policies/apple validation.json'):
            with self.subTest(policy=policy), patch('subprocess.run') as run:
                self.f.environment['SDK_APPLE_VALIDATION_POLICY'] = policy
                self.f.execute('execute')
            command = run.call_args.args[0]
            fields = dict(zip(command[5::2], command[6::2]))
            self.assertEqual(policy or None, fields.get('--sdk-apple-validation-policy'))
            self.assertEqual(self.f.environment['VALIDATION_ARTIFACT_ID'], fields['--validation-artifact-id'])


if __name__ == '__main__':
    unittest.main()
