"""Preflight controls only; never substitute these tests for real host evidence."""
import json
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from ci.tests import phase9_runtime_mutation as fixture


class RuntimeMutationPreflightTest(unittest.TestCase):
    def test_missing_targets_and_independent_arm_roles(self):
        self.assertEqual({'linux-arm64', 'linux-x64', 'macos-x64', 'windows-x64'}, set(fixture.KEYS))
        self.assertEqual('linux-x64', fixture.selected_role('linux-arm64', 'cross-builder'))
        self.assertEqual('linux-arm64', fixture.selected_role('linux-arm64', 'supervisor-builder'))
        for target in ('linux-x64', 'macos-x64', 'windows-x64'):
            self.assertEqual(target, fixture.selected_role(target, 'builder'))
        for target, role in (('macos-arm64', 'builder'), ('linux-arm64', 'builder'),
                             ('windows-x64', 'cross-builder'), ('linux-x64', 'supervisor-builder')):
            with self.assertRaisesRegex(ValueError, 'missing target'):
                fixture.selected_role(target, role)

    def test_rejected_context_never_transfers_or_observes(self):
        with patch.object(fixture, 'hosted_context', side_effect=ValueError('wrong host')), \
                patch.object(fixture, 'prepare') as prepare, patch.object(fixture, 'observe_producer') as observe:
            with self.assertRaisesRegex(ValueError, 'wrong host'):
                fixture.hosted('linux-x64', 'builder', Path('unused'), Path('unused-cache'))
            prepare.assert_not_called()
            observe.assert_not_called()

    def test_real_context_scope_and_wrong_event_or_host(self):
        with tempfile.TemporaryDirectory() as temporary:
            event = Path(temporary) / 'event.json'
            event.write_text(json.dumps(dict(label=dict(name=fixture.LABEL),
                pull_request=dict(number=31, head=dict(sha='a'*40,
                    repo=dict(full_name='codex-agent-labs/codex-agent', fork=False))))))
            environment = dict(GITHUB_ACTIONS='true', GITHUB_EVENT_NAME='pull_request',
                GITHUB_REPOSITORY='codex-agent-labs/codex-agent', GITHUB_EVENT_PATH=str(event),
                GITHUB_RUN_ID='123', GITHUB_RUN_ATTEMPT='2', GITHUB_SHA='b'*40)
            def git(*args):
                return '' if args[0] == 'diff' else 'c'*40 if args[-1] == 'HEAD^{tree}' else 'a'*40
            with patch.dict(os.environ, environment), patch.object(fixture.mutation, 'git', side_effect=git), \
                    patch.object(fixture, 'host_classifier', return_value='linux-x64') as host:
                context = fixture.hosted_context('linux-arm64', 'cross-builder')
                self.assertEqual(('a'*40, 'b'*40, 123, 2, False), tuple(context[key] for key in
                    ('sourceCommit', 'workflowEventCommit', 'runId', 'runAttempt', 'releaseAdmission')))
                host.return_value = 'macos-arm64'
                with self.assertRaisesRegex(ValueError, 'actual selected'):
                    fixture.hosted_context('linux-arm64', 'cross-builder')
                host.return_value = 'linux-x64'
                with patch.dict(os.environ, GITHUB_EVENT_NAME='push'):
                    with self.assertRaisesRegex(ValueError, 'same-repository'):
                        fixture.hosted_context('linux-arm64', 'cross-builder')
                payload = json.loads(event.read_bytes())
                payload['label']['name'] = fixture.WINDOWS_LABEL
                event.write_text(json.dumps(payload))
                with self.assertRaisesRegex(ValueError, 'same-repository'):
                    fixture.hosted_context('linux-arm64', 'cross-builder')
                host.return_value = 'windows-x64'
                self.assertEqual('windows-x64', fixture.hosted_context('windows-x64', 'builder')['target'])

    def test_scope_excludes_all_product_inventories_and_completed_mac(self):
        from products.registry import PHASE_INSTANCE_IDS
        from products.selection import phase_inventory_paths
        paths = ['ci/tests/phase9_runtime_mutation.py', 'ci/tests/test_phase9_runtime_mutation.py',
                 '.github/workflows/portable-reuse-proof.yml']
        self.assertTrue(all(not phase_inventory_paths(paths, phase) for phase in PHASE_INSTANCE_IDS))
        workflow = (fixture.ROOT / paths[-1]).read_text().split('  phase9-ios-package-check:')[0]
        retry, original = [json.loads(value) for value in re.findall(r"fromJSON\('([^']+)'\)", workflow)]
        self.assertEqual([dict(target='windows-x64', role='builder', runner='windows-2025')], retry)
        self.assertEqual({('macos-x64', 'builder'), ('linux-x64', 'builder'), ('windows-x64', 'builder'),
                          ('linux-arm64', 'cross-builder'), ('linux-arm64', 'supervisor-builder')},
                         {(row['target'], row['role']) for row in original})
        with patch.object(fixture, 'receive') as receive:
            with self.assertRaisesRegex(ValueError, 'existing target'):
                fixture.prepare('macos-arm64', Path('unused'), Path('unused-cache'))
            receive.assert_not_called()

    def test_profile_mismatch_is_preserved_and_never_grants_admission(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary).resolve() / 'diagnostic'
            destination.mkdir()
            prepared = dict(environment={}, sourceCommit='a'*40, sourceTree='b'*40,
                            originalContractProducer={'event': 'local'}, profileDigest='sha256:'+'1'*64)
            observation = dict(producer=dict(role='supervisor-builder', runner=dict(os='Linux', arch='ARM64'), tools=[]),
                               imageProvenance={'image': 'test', 'imageVersion': 'test'})
            def observe(*args, **kwargs):
                # dict(os.environ) loses Windows' native case-insensitive lookup.
                self.assertIs(kwargs['environment'], os.environ)
                self.assertEqual('', os.environ['GH_TOKEN'])
                self.assertEqual('', os.environ['GITHUB_TOKEN'])
                return observation
            with patch.object(fixture, 'hosted_context', return_value=dict(runId=123, runAttempt=1)), \
                    patch.object(fixture, 'prepare', return_value=(prepared, SimpleNamespace())), \
                    patch.object(fixture, '_runtime_worker_environment', side_effect=lambda *args: ({}, None)), \
                    patch.object(fixture, 'observe_producer', side_effect=observe), \
                    patch.dict(os.environ, GH_TOKEN='test-only-ambient-token', GITHUB_TOKEN='test-only-ambient-token'), \
                    patch.object(fixture, '_provision_runtime_native_toolchain') as provision, \
                    patch.object(fixture, 'verify_toolchain_profile', side_effect=ValueError('actual tool mismatch')):
                with self.assertRaisesRegex(ValueError, 'actual tool mismatch'):
                    fixture.hosted('linux-arm64', 'supervisor-builder', destination, Path('unused'))
                provision.assert_not_called()
            result = json.loads((destination/'result.json').read_bytes())
            self.assertFalse(result['profileMatches'])
            self.assertEqual(0, result['productExecutions'])
            self.assertEqual(observation, json.loads((destination/'toolchain-observation.json').read_bytes()))


if __name__ == '__main__':
    unittest.main()
