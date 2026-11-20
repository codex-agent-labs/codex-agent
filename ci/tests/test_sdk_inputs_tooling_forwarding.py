"""SDK-input caller policy composition; existing replay/content gates are mocked."""

import os
import unittest
from unittest.mock import patch

from ci import sdk_workflow as workflow
from ci.tests import test_sdk_workflow as fixtures


class SdkInputsToolingForwardingTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.SdkWorkflowTest(methodName='runTest')
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.policy = {'evidence': '/caller/original-tooling', 'publicKey': '/caller/public-key',
            'javaExecutable': '/caller/java', 'requiredTrustDomain': 'release',
            'keyring': '/caller/keyring', 'keysDirectory': '/caller/keys'}

    def test_both_sources_forward_exact_caller_policy_and_omit_legacy_keyword(self):
        f = self.fixture
        for source in ('released-default', 'current-runtime'):
            for policy in (None, self.policy):
                with self.subTest(source=source, policy=policy):
                    f.selection['source'] = source
                    for mock in (f.inspect, f.released, f.fresh):
                        mock.reset_mock()
                    optional = {'sdk_validation_tooling': policy} if policy is not None else {}
                    with patch.object(workflow, '_selection', wraps=workflow._selection) as selected:
                        f.stage(**f.upload, **optional)
                    self.assertEqual({'trusted_workflow_sha': f.upload['trusted_workflow_sha'], **optional},
                        selected.call_args.kwargs)
                    f.inspect.assert_called_once_with(f.plan, f.discovery, f.state,
                        repository_root=f.repository, environ=f.arguments['environ'],
                        include_sdk_selection=True,
                        sdk_original_workflow_sha=f.upload['trusted_workflow_sha'], **optional)
                    if source == 'released-default':
                        f.released.assert_called_once_with(f.plan, f.discovery, f.state, f.destination,
                            keyring=f.arguments['keyring'], keys_directory=f.arguments['keys_directory'],
                            repository_root=f.repository, environ=f.arguments['environ'],
                            sdk_original_workflow_sha=f.upload['trusted_workflow_sha'], **optional)
                        f.fresh.assert_not_called()
                    else:
                        f.released.assert_not_called()
                        f.fresh.assert_called_once()
                        self.assertNotIn('sdk_validation_tooling', f.fresh.call_args.kwargs)
                        self.assertEqual(f.selection['contractPayloadSha256'],
                            f.fresh.call_args.kwargs['expected_contract_payload_sha256'])
                    if policy is not None:
                        self.assertIs(policy, f.inspect.call_args.kwargs['sdk_validation_tooling'])

    def argv(self):
        f = self.fixture
        paths = {'plan': f.plan, 'discovery-root': f.discovery, 'state-root': f.state,
            'destination': f.destination, 'repository-root': f.repository,
            'keyring': f.arguments['keyring'], 'keys-directory': f.arguments['keys_directory']}
        return [value for name, path in paths.items() for value in ('--' + name, str(path))]

    def test_default_cli_reads_canonical_local_policy_and_preserves_environment(self):
        f = self.fixture
        policy_path = f.root / 'caller policy.json'
        policy_path.write_bytes(workflow.canonical_json_bytes(self.policy))
        for present in (False, True):
            with self.subTest(present=present), patch.dict(os.environ, {'GITHUB_TOKEN': 'caller-token'}, clear=True), \
                    patch.object(workflow, 'stage') as stage:
                argv = self.argv() + (['--sdk-validation-tooling', str(policy_path)] if present else [])
                self.assertEqual(0, workflow.main(argv))
                stage.assert_called_once_with(f.plan, f.discovery, f.state, f.destination,
                    keyring=f.arguments['keyring'], keys_directory=f.arguments['keys_directory'],
                    repository_root=f.repository, artifact_id=None, artifact_sha256=None,
                    trusted_workflow_sha=None, expected_build_key=None, expected_metadata_receipt_sha256=None,
                    environ=os.environ, token='caller-token',
                    **({'sdk_validation_tooling': self.policy} if present else {}))

    def test_malformed_policy_rejects_before_stage_without_output(self):
        f = self.fixture
        policy_path = f.root / 'bad-policy.json'
        for raw in (b'{"evidence":"one","evidence":"two"}\n', b'[]\n', b'{"evidence": "noncanonical"}\n'):
            policy_path.write_bytes(raw)
            with self.subTest(raw=raw), patch.object(workflow, 'stage') as stage, self.assertRaises(SystemExit) as error:
                workflow.main(self.argv() + ['--sdk-validation-tooling', str(policy_path)])
            self.assertEqual(2, error.exception.code)
            stage.assert_not_called()
            self.assertFalse(f.destination.exists())

    def test_replay_policy_rejection_never_dispatches_a_writer(self):
        f = self.fixture
        f.inspect.side_effect = ValueError('caller tooling policy rejected')
        with self.assertRaisesRegex(ValueError, 'caller tooling policy rejected'):
            f.stage(**f.upload, sdk_validation_tooling=self.policy)
        f.fresh.assert_not_called()
        f.released.assert_not_called()
        self.assertFalse(f.destination.exists())


if __name__ == '__main__':
    unittest.main()
