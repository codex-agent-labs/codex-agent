"""Control checks only; actual Intel execution is a separate hosted requirement."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci.tests import phase9_native_validation as check


class NativeValidationTest(unittest.TestCase):
    def test_windows_exact_consumed_inputs_and_four_task_fixture(self):
        from products.registry import PHASE_INSTANCE_IDS
        from products.selection import phase_inventory_paths
        spec = check.windows_specification()
        self.assertEqual((15, 137476042), (len(spec['files']), sum(row['bytes'] for row in spec['files'])))
        self.assertEqual(7, sum(row['relativePath'].startswith('package/outputs/') for row in spec['files']))
        self.assertEqual({'executor', 'package', 'receipts', 'source'},
                         {row['relativePath'].split('/')[0] for row in spec['files']})
        self.assertEqual('pull_request', spec['binaryProducer']['event'])
        self.assertEqual(40220815135, spec['binaryProducer']['runId'])
        self.assertEqual('local', spec['packageProducer']['event'])
        self.assertEqual(176, spec['retainedKeyCount'])
        paths = ['ci/tests/phase9_native_validation.py', 'ci/tests/test_phase9_native_validation.py',
            'ci/tests/fixtures/phase9-native-windows-validation-transfer.json',
            'ci/tests/fixtures/phase9-native-validation-windows.gradle', '.github/workflows/portable-reuse-proof.yml']
        self.assertTrue(all(not phase_inventory_paths(paths, phase) for phase in PHASE_INSTANCE_IDS))
        fixture = (check.FIXTURES / 'phase9-native-validation-windows.gradle').read_text()
        self.assertIn("target.set('mingwX64')", fixture)
        self.assertIn("runnerOs.set('Windows')", fixture)
        self.assertIn("outputs/validation-runner/test.exe", fixture)
        self.assertIn("gnuC: 'gcc', gnuCpp: 'g++'", fixture)
        self.assertIn('graph.allTasks.collect { it.path }.toSet() != expected', fixture)
        self.assertIn('writeMingwX64RuntimeValidationOutputManifest', fixture)
        self.assertNotIn('RuntimeBinaryOutputManifest', fixture)
        self.assertNotIn('RuntimePackageOutputManifest', fixture)
        with patch.object(check, 'WINDOWS_TRANSFER_SHA256', 'sha256:'+'0'*64):
            with self.assertRaisesRegex(ValueError, 'reviewed original pins'):
                check.windows_specification()

    def test_windows_real_receipt_manifest_and_lineage_checks(self):
        import copy
        from ci.tests.test_product_plan import receipt as fixture_receipt, file_record, VERSIONS
        from products.inventory import write_canonical_json, sha256_file
        from products.receipt import compute_build_key, write_output_manifest
        from products.plan import plan_phase, NOT_APPLICABLE_FLAGS_DIGEST, NOT_APPLICABLE_TOOLCHAIN_DIGEST
        from products.registry import PhaseInstanceId
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            binary = fixture_receipt(PhaseInstanceId('runtime', 'windows-x64', 'binary', 'windows-x64'))
            package = fixture_receipt(PhaseInstanceId('runtime', 'windows-x64', 'package', 'windows-x64'),
                producer=dict(binary['producer'], event='local', workflowPath=None, runId=None, runAttempt=None, pullRequest=None))
            edge = {key: binary[key] for key in ('product', 'component', 'phase', 'target', 'buildKey')}
            edge['outputsDigest'] = check.output_inventory_digest(binary['outputs'])
            package['inputs']['upstreamArtifacts'] = [edge]
            package['buildKey'] = compute_build_key(product='runtime', component='windows-x64', phase='package',
                target='windows-x64', inputs=package['inputs'])
            for index in range(7):
                p = root / f'package/outputs/artifact/{index}.bin'; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(b'x')
            manifest = write_output_manifest(root / 'package', 'runtime', 'windows-x64', 'package',
                'windows-x64', package['productVersion'], {'artifact': 'outputs/artifact'})
            package['outputs'] = manifest['outputs']
            (root / 'receipts').mkdir()
            for phase, value in [('binary', binary), ('package', package)]:
                write_canonical_json(root / 'receipts' / (phase + '.json'), value)
            def controls():
                rows = [dict(relativePath=name, bytes=(root/name).stat().st_size, sha256=sha256_file(root/name))
                        for name in ('package/output-manifest.json', 'receipts/binary.json', 'receipts/package.json')]
                return sorted(rows + [dict(relativePath='package/'+r['relativePath'], bytes=r['bytes'], sha256=r['sha256'])
                                      for r in package['outputs']], key=lambda r:r['relativePath'])
            inventory = [file_record()]
            expected = plan_phase(check.WINDOWS_INSTANCE, inventory=inventory, versions=VERSIONS,
                upstream_receipts=[package], toolchain_profile_digest=NOT_APPLICABLE_TOOLCHAIN_DIGEST,
                flags_digest=NOT_APPLICABLE_FLAGS_DIGEST)
            spec = dict(files=controls(), productVersion=package['productVersion'], sourceCommit='a'*40,
                sourceTree='b'*40, buildLogicTree='c'*40, binaryProducer=copy.deepcopy(binary['producer']),
                packageProducer=copy.deepcopy(package['producer']), binaryBuildKey=binary['buildKey'],
                packageBuildKey=package['buildKey'], validationBuildKey=expected['buildKey'],
                validationInputDigest=expected['inputs']['phaseInputDigest'])
            def git(*args, **kwargs):
                return 'a'*40 if args[-1]=='HEAD' else 'b'*40 if args[-1]=='HEAD^{tree}' else 'c'*40
            with patch.object(check, 'windows_specification', return_value=spec), patch.object(check, 'git', side_effect=git), \
                    patch.object(check, 'phase_git_inventory', return_value=inventory), \
                    patch.object(check, 'git_product_versions', return_value=VERSIONS):
                self.assertEqual(expected, check.prepare_windows(root, root/'source'))
                package['producer']['commit'] = 'd'*40
                write_canonical_json(root/'receipts/package.json', package); spec['files'] = controls()
                with self.assertRaisesRegex(ValueError, 'identity/provenance'):
                    check.prepare_windows(root, root/'source')
                package['producer'] = copy.deepcopy(spec['packageProducer'])
                package['inputs']['upstreamArtifacts'][0]['outputsDigest'] = 'sha256:'+'f'*64
                package['buildKey'] = compute_build_key(product='runtime', component='windows-x64', phase='package',
                    target='windows-x64', inputs=package['inputs'])
                write_canonical_json(root/'receipts/package.json', package)
                spec['files'] = controls(); spec['packageBuildKey'] = package['buildKey']
                with self.assertRaisesRegex(ValueError, 'does not bind'):
                    check.prepare_windows(root, root/'source')

    def test_windows_context_and_late_failure_prevent_receipt(self):
        from ci.tests import phase9_runtime_mutation as mutation
        import product_reuse
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(); out = root/'out'
            event = root/'event.json'; event.write_text('{}')
            with patch.dict(os.environ, {'GITHUB_EVENT_PATH':str(event),'GITHUB_ACTIONS':'false'}), \
                    patch.object(check,'git',return_value='a'*40), patch.object(check,'receive') as receive:
                with self.assertRaisesRegex(ValueError,'same-repository'):
                    check.hosted_windows(out,root)
                receive.assert_not_called(); self.assertFalse(out.exists())
            spec = check.windows_specification()
            java_home=root/'java';(java_home/'bin').mkdir(parents=True);(java_home/'bin/java.exe').write_bytes(b'fixture')
            def source(destination, storage):
                destination.mkdir(); (destination/'source').mkdir(); (destination/'source-inputs').mkdir()
                return {'environment':{}},None
            def receive(records,destination,storage):
                self.assertFalse(any(r['relativePath'].startswith(('source/','binary/','contract/')) for r in records))
                destination.mkdir();return {'downloadedBytes':0,'fixture':True}
            def execute(command,**kwargs):
                self.assertEqual(str(java_home/'bin/java.exe'),command[0]);self.assertEqual(check.WINDOWS_TASK,command[-1])
                self.assertEqual('true',kwargs['env']['GITHUB_ACTIONS'])
                kwargs['stdout'].write(b'synthetic task process success\n');return SimpleNamespace(returncode=0)
            controller={'producer':dict(spec['binaryProducer'],commit='a'*40,tree='b'*40,runId=3)}
            with patch.object(check,'windows_hosted_context',return_value=controller), \
                    patch.object(mutation,'prepare_windows_source',side_effect=source), \
                    patch.object(check,'receive',side_effect=receive), patch.object(check,'git',return_value=spec['buildLogicTree']), \
                    patch.object(check,'prepare_windows',side_effect=[{'buildKey':spec['validationBuildKey'],'inputs':{}},ValueError('late input mutation')]), \
                    patch.object(product_reuse,'_runtime_worker_checkout'), \
                    patch.object(product_reuse,'_runtime_worker_environment',return_value=({'JAVA_HOME':str(java_home),'GITHUB_ACTIONS':'true'},out/'source/gradlew.bat')), \
                    patch.object(check.subprocess,'run',side_effect=execute), \
                    patch.object(check,'project_native_validation_stage') as project, patch.object(check,'write_phase_receipt') as receipt:
                with self.assertRaisesRegex(ValueError,'late input mutation'):
                    check.hosted_windows(out,root)
                receipt.assert_not_called();project.assert_not_called()
                self.assertFalse((out/'phase-receipt.json').exists());self.assertFalse((out/'result.json').exists())

    def test_fixed_consumed_inputs_and_zero_product_ownership(self):
        from products.registry import PHASE_INSTANCE_IDS
        from products.selection import phase_inventory_paths
        spec = check.specification()
        self.assertEqual(13, len(spec['files']))
        self.assertEqual({'executor', 'package', 'receipts'},
                         {row['relativePath'].split('/')[0] for row in spec['files']})
        paths = ['ci/tests/phase9_native_validation.py', 'ci/tests/test_phase9_native_validation.py',
            'ci/tests/fixtures/phase9-native-validation-transfer.json',
            'ci/tests/fixtures/phase9-native-validation/settings.gradle',
            'ci/tests/fixtures/phase9-native-validation/codex-agent-runtime-desktop/build.gradle',
            '.github/workflows/portable-reuse-proof.yml']
        self.assertTrue(all(not phase_inventory_paths(paths, phase) for phase in PHASE_INSTANCE_IDS))
        with patch.object(check, 'TRANSFER_SHA256', 'sha256:'+'0'*64):
            with self.assertRaisesRegex(ValueError, 'reviewed original pins'):
                check.specification()

    def test_wrong_event_before_transfer_and_tamper_before_plan(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            event = root / 'event.json'
            event.write_text(json.dumps({}))
            with patch.dict(os.environ, {'GITHUB_EVENT_PATH': str(event), 'GITHUB_ACTIONS': 'false'}), \
                    patch.object(check, 'git', return_value='a'*40), patch.object(check, 'receive') as receive:
                with self.assertRaisesRegex(ValueError, 'same-repository'):
                    check.hosted(root / 'out', root)
                receive.assert_not_called()
                self.assertFalse((root / 'out').exists())
            first = root / check.specification()['files'][0]['relativePath']
            first.parent.mkdir()
            first.write_bytes(b'tampered executor')
            with patch.object(check, 'plan_phase') as plan:
                with self.assertRaisesRegex(ValueError, 'immutable original'):
                    check.prepare(root, 'a'*40)
                plan.assert_not_called()


if __name__ == '__main__':
    unittest.main()
