"""Preflight controls only; never substitute these tests for real host evidence."""
import json
from contextlib import ExitStack
import hashlib
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
        paths = ['ci/tests/phase9_runtime_mutation.py', 'ci/tests/phase9_ios_mutation.py',
                 'ci/tests/test_phase9_runtime_mutation.py',
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
            with self.assertRaisesRegex(ValueError, 'only missing Linux x64'):
                fixture.prepare_binary('macos-arm64', Path('unused'), Path('unused-cache'))
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


    def test_windows_binary_requires_its_own_exact_context(self):
        with tempfile.TemporaryDirectory() as temporary:
            event = Path(temporary) / 'event.json'
            payload = dict(label=dict(name=fixture.WINDOWS_BINARY_LABEL), pull_request=dict(number=31,
                head=dict(sha='a'*40, repo=dict(full_name='codex-agent-labs/codex-agent', fork=False))))
            event.write_text(json.dumps(payload))
            environment = dict(GITHUB_ACTIONS='true', GITHUB_EVENT_NAME='pull_request',
                GITHUB_REPOSITORY='codex-agent-labs/codex-agent', GITHUB_EVENT_PATH=str(event),
                GITHUB_RUN_ID='123', GITHUB_RUN_ATTEMPT='2', GITHUB_SHA='b'*40)
            def git(*args):
                return '' if args[0] == 'diff' else 'c'*40 if args[-1] == 'HEAD^{tree}' else 'a'*40
            with patch.dict(os.environ, environment), patch.object(fixture.mutation, 'git', side_effect=git), \
                    patch.object(fixture, 'host_classifier', return_value='windows-x64') as host:
                context = fixture.hosted_context('windows-x64', 'builder', windows_binary=True)
                self.assertEqual((123, 2, 'a'*40), tuple(context[k] for k in ('runId', 'runAttempt', 'sourceCommit')))
                with self.assertRaisesRegex(ValueError, 'same-repository'):
                    fixture.hosted_context('windows-x64', 'builder')
                payload['label']['name'] = fixture.WINDOWS_LABEL
                event.write_text(json.dumps(payload))
                with self.assertRaisesRegex(ValueError, 'same-repository'):
                    fixture.hosted_context('windows-x64', 'builder', windows_binary=True)
                payload['label']['name'] = fixture.WINDOWS_BINARY_LABEL
                event.write_text(json.dumps(payload))
                host.return_value = 'linux-x64'
                with self.assertRaisesRegex(ValueError, 'actual selected'):
                    fixture.hosted_context('windows-x64', 'builder', windows_binary=True)

    def test_windows_source_intake_is_tiny_and_rejects_wrong_bundle_head(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary).resolve() / 'worker'
            raw = b'tiny-source-fixture'
            record = dict(relativePath='source/windows-mutation-source.bundle', bytes=len(raw),
                sha256='sha256:'+hashlib.sha256(raw).hexdigest())
            def receive(records, inputs, storage):
                self.assertEqual(['source/mutation-source.bundle', record['relativePath']],
                    [r['relativePath'] for r in records])
                inputs.mkdir(parents=True)
                (inputs / 'source').mkdir()
                (inputs / record['relativePath']).write_bytes(raw)
                return dict(downloadedBytes=len(raw))
            with patch.object(fixture, 'WINDOWS_BUNDLE', record), \
                    patch.object(fixture, 'receive', side_effect=receive), \
                    patch.object(fixture.mutation, 'source_fixture', return_value=(destination/'source', {})), \
                    patch.object(fixture.mutation, 'git', return_value='wrong HEAD'), \
                    patch.object(fixture.mutation, 'contract_inputs') as contract:
                with self.assertRaisesRegex(ValueError, 'unexpected heads'):
                    fixture.prepare_windows_source(destination, Path(temporary))
                contract.assert_not_called()
                self.assertFalse((destination/'inputs').exists())

    def test_windows_binary_profile_then_single_execution_and_late_failure_gates(self):
        from types import SimpleNamespace
        import product_reuse
        import products.receipt
        import products.toolchain_capture_bootstrap
        import runtime_native_phase
        command_builder = product_reuse._runtime_worker_command
        for mode in ('profile-mismatch', 'process-failure', 'input-mutation', 'success'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
                destination = Path(temporary).resolve() / 'worker'
                context = dict(sourceCommit='a'*40, sourceTree='b'*40, workflowEventCommit='c'*40,
                    runId=123, runAttempt=2, target='windows-x64', role='builder')
                prepared = dict(environment={}, originalContractProducer={'event':'local'},
                    sourceCommit=fixture.WINDOWS_SOURCE, sourceTree=fixture.WINDOWS_TREE)
                plan = dict(inputs={}, buildKey=fixture.WINDOWS_BINARY_KEY)
                calls = []
                def source(*args):
                    destination.mkdir()
                    (destination/'source-inputs').mkdir()
                    (destination/'source-inputs/source.bundle').write_bytes(b'original-source')
                    policy = destination/'source/codex-agent-runtime-desktop/src/mingwMain/gradle/deterministic-native-link.init.gradle'
                    policy.parent.mkdir(parents=True)
                    policy.write_bytes(b'policy')
                    return prepared, SimpleNamespace(digest=fixture.WINDOWS_PROFILE)
                def binary(*args):
                    calls.append('contract')
                    (destination/'inputs/contract').mkdir(parents=True)
                    (destination/'inputs/contract/original').write_bytes(b'original-contract')
                    return prepared, SimpleNamespace(digest=fixture.WINDOWS_PROFILE), plan
                def provision(root, revision, target, output, environment):
                    environment['KONAN_DATA_DIR'] = str(destination/'konan')
                    return {'codexAgent.kotlinPluginJar':'plugin.jar','codexAgent.nativeArchive':'native.zip'}
                observation = dict(producer=dict(runner=dict(os='Windows',arch='X64'),tools=[]), imageProvenance={})
                def observe(*args, **kwargs):
                    self.assertIs(kwargs['environment'], os.environ)
                    self.assertEqual('', os.environ['GH_TOKEN'])
                    self.assertEqual('true', os.environ['GITHUB_ACTIONS'])
                    return observation
                def verify(*args, **kwargs):
                    calls.append('profile')
                    if mode == 'profile-mismatch':
                        raise ValueError('actual tool mismatch')
                def process(command, **kwargs):
                    calls.append('execute')
                    self.assertEqual('C:\\Java17\\bin\\java.exe', command[0])
                    self.assertIn('ciProductPhase', command)
                    self.assertIn('-PcodexAgent.candidateCommit='+fixture.WINDOWS_SOURCE, command)
                    self.assertIn('-PcodexAgent.component=windows-x64', command)
                    self.assertIn('-PcodexAgent.phase=binary', command)
                    self.assertEqual('/Brepro', kwargs['env']['LINK'])
                    self.assertEqual('', kwargs['env']['GH_TOKEN'])
                    self.assertEqual('false', kwargs['env']['GITHUB_ACTIONS'])
                    self.assertEqual('true', os.environ['GITHUB_ACTIONS'])
                    if mode == 'input-mutation':
                        (destination/'inputs/contract/original').write_bytes(b'changed-contract')
                    return SimpleNamespace(returncode=1 if mode == 'process-failure' else 0)
                def receipt(stage, output, *args):
                    calls.append('receipt')
                    value = dict(outputs=[dict(bytes=3)], producer=args[-2])
                    (output/'phase-receipt.json').write_text(json.dumps(value))
                    return value
                stack.enter_context(patch.object(fixture,'hosted_context',return_value=context))
                stack.enter_context(patch.object(fixture,'prepare_windows_source',side_effect=source))
                capture = stack.enter_context(patch.object(fixture,'prepare_windows_binary',side_effect=binary))
                stack.enter_context(patch.object(fixture,'_runtime_worker_environment',return_value=(
                    dict(JAVA_HOME='C:\\Java17',GH_TOKEN='ambient',GITHUB_TOKEN='ambient',
                         GITHUB_ACTIONS='true'),Path('C:/fixture/gradlew.bat'))))
                stack.enter_context(patch.dict(os.environ, GITHUB_ACTIONS='true'))
                stack.enter_context(patch.object(fixture,'_provision_runtime_native_toolchain',side_effect=provision))
                stack.enter_context(patch.object(fixture,'observe_producer',side_effect=observe))
                stack.enter_context(patch.object(fixture,'verify_toolchain_profile',side_effect=verify))
                stack.enter_context(patch.object(fixture,'git_regular_blob_bytes',return_value=b'policy'))
                stack.enter_context(patch.object(product_reuse,'_runtime_worker_checkout'))
                stack.enter_context(patch.object(product_reuse,'_runtime_worker_command',side_effect=lambda *a,**kw:
                    command_builder(*a,**kw,platform_name='nt')))
                stack.enter_context(patch.object(runtime_native_phase,'archive_spec',return_value=dict(
                    asset='pinned.zip',url='https://example.invalid/pinned.zip',sha256='sha256:'+hashlib.sha256(b'zip').hexdigest())))
                stack.enter_context(patch.object(runtime_native_phase,'properties',return_value={}))
                download = stack.enter_context(patch.object(products.toolchain_capture_bootstrap,'_pinned_file',
                    side_effect=lambda url,path,digest,unused:path.write_bytes(b'zip')))
                execute = stack.enter_context(patch.object(fixture.subprocess,'run',side_effect=process))
                writer = stack.enter_context(patch.object(products.receipt,'write_phase_receipt',side_effect=receipt))
                if mode == 'success':
                    fixture.hosted_windows_binary(destination, Path(temporary))
                    self.assertEqual(['profile','contract','execute','receipt'],calls)
                    result = json.loads((destination/'result.json').read_bytes())
                    self.assertEqual(fixture.WINDOWS_SOURCE,result['producer']['commit'])
                    self.assertEqual(context,result['hostedContext'])
                    self.assertEqual(1,result['productExecutions'])
                    self.assertFalse(result['baselineAdmission'])
                    self.assertFalse(result['releaseAdmission'])
                else:
                    with self.assertRaisesRegex(ValueError, 'mismatch|failed|changed'):
                        fixture.hosted_windows_binary(destination,Path(temporary))
                    writer.assert_not_called()
                    self.assertFalse((destination/'binary-receipt').exists())
                    if mode == 'profile-mismatch':
                        capture.assert_not_called(); download.assert_not_called(); execute.assert_not_called()
                        self.assertTrue((destination/'toolchain-observation.json').is_file())
                    else:
                        self.assertTrue((destination/'binary-execution.json').is_file())
                        execute.assert_called_once()

    def test_windows_binary_workflow_and_fixed_identity(self):
        workflow = (fixture.ROOT/'.github/workflows/portable-reuse-proof.yml').read_text()
        job = workflow.split('  phase9-runtime-windows-binary:')[1].split('  phase9-ios-package-check:')[0]
        self.assertIn("github.event.label.name == 'ci:phase9-runtime-windows-binary'",job)
        self.assertIn('runs-on: windows-2025',job)
        self.assertIn('hosted-windows-binary',job)
        self.assertIn('if: always()',job)
        self.assertNotIn('product-attestation',job)
        self.assertIn('binary-receipt',job)
        self.assertNotIn('build/phase9-runtime-windows-binary/inputs',job)
        self.assertEqual('sha256:459daab114ea2b62b6994e162f033c959bf95bfdd649bcda6c46b7dc96f2fcc5',fixture.WINDOWS_BINARY_KEY)
        self.assertEqual('sha256:3944685c3a9dcfa21e48adf67b72b1946928b119ad83390c3334842baa65cc5a',fixture.RETAINED_CHECKPOINT)


if __name__ == '__main__':
    unittest.main()
