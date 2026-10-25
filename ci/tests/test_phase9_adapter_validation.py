"""Small control fixtures only: subprocess/host/Git seams are explicit, no product execution."""
import copy
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ci.tests import phase9_adapter_validation as check
from products.inventory import sha256_file, write_canonical_json


class AdapterValidationTest(unittest.TestCase):
    def test_fixed_selection_ownership_and_exact_task_identity(self):
        from products.registry import PHASE_INSTANCE_IDS
        from products.selection import phase_inventory_paths
        from products.runtime_evidence import IMPORTED_JVM_RUNTIME_EVIDENCE_TASK
        spec = check.specification()
        self.assertEqual(183, len(set(spec['retainedKeys'])))
        self.assertEqual(6, len(spec['plans']))
        for host in spec['hosts'].values():
            self.assertEqual(11, len(host['files']))
            self.assertEqual(3, sum(r['relativePath'].startswith('executor/') for r in host['files']))
            self.assertFalse(any(r['relativePath'].startswith(('binary/','contract/','source/')) for r in host['files']))
        paths=['ci/tests/phase9_adapter_validation.py','ci/tests/test_phase9_adapter_validation.py',
            *[p.relative_to(check.ROOT).as_posix() for p in check.FIXTURES.rglob('*') if p.is_file()]]
        self.assertTrue(all(not phase_inventory_paths(paths,instance) for instance in PHASE_INSTANCE_IDS))
        fixture=(check.FIXTURES/'codex-agent-runtime-desktop/build.gradle').read_text()
        self.assertIn("testTask.set('"+IMPORTED_JVM_RUNTIME_EVIDENCE_TASK+"')",fixture)
        for name in ('RecordJvmRuntimeEvidenceTask','RecordNodeRuntimeEvidenceTask','stageAdapterRuntimeValidation',
                     'writeAdapterRuntimeValidationOutputManifest','graph.allTasks.collect { it.path }.toSet() != expected'):
            self.assertIn(name,fixture)
        self.assertNotIn('Compile',fixture);self.assertNotIn('CAbi',fixture)
        with patch.object(check,'SELECTION_SHA256','sha256:'+'0'*64):
            with self.assertRaisesRegex(ValueError,'reviewed original pins'):check.specification()

    def test_wrong_event_fails_before_shared_intake(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve();event=root/'event.json';event.write_text('{}')
            storage=root/'cache'
            with patch.dict(os.environ,{'GITHUB_EVENT_PATH':str(event),'GITHUB_ACTIONS':'false'}), \
                    patch.object(check.mutation,'git',return_value='a'*40), \
                    patch.object(check,'receive') as intake,patch.object(check,'prepare_windows_source') as source:
                with self.assertRaisesRegex(ValueError,'same-repository'):
                    check.prepare(root/'out',storage,'windows-x64')
                intake.assert_not_called();source.assert_not_called();self.assertFalse((root/'out').exists())
                self.assertFalse(storage.exists())

    def test_shared_storage_exists_before_source_acquisition_and_preserves_warm_cache(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve();storage=root/'cache';marker=storage/'retained'
            def source_acquisition(destination, selected_storage):
                self.assertEqual(storage,selected_storage)
                self.assertTrue(storage.is_dir())
                raise RuntimeError('stop at source acquisition')
            with patch.object(check,'hosted_context',return_value={}), \
                    patch.object(check,'prepare_windows_source',side_effect=source_acquisition) as source, \
                    patch.object(check,'receive') as intake:
                self.assertFalse(storage.exists())
                for warm in (False,True):
                    with self.subTest(warm=warm):
                        with self.assertRaisesRegex(RuntimeError,'stop at source acquisition'):
                            check.prepare(root/'out',storage,'windows-x64')
                        self.assertEqual(int(warm)+1,source.call_count)
                        intake.assert_not_called()
                        if warm:
                            self.assertEqual(b'original cache bytes',marker.read_bytes())
                        else:
                            marker.write_bytes(b'original cache bytes')

    def test_real_receipt_member_election_and_tamper_checks(self):
        from ci.tests.test_product_plan import receipt as fixture_receipt, file_record, VERSIONS
        from products.registry import PhaseInstanceId
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve();component='jvm';target='windows-x64'
            adapter=copy.deepcopy(fixture_receipt(PhaseInstanceId('runtime',component,'package',component)))
            native=copy.deepcopy(fixture_receipt(PhaseInstanceId('runtime',target,'package',target)))
            files=[]
            for receipt,path,kind,receipt_relative in (
                (adapter,'adapters/jvm/runner/runner.zip','validation-runner','outputs/validation-runner/runner.zip'),
                (native,'native/outputs/app-server/native.zip','app-server','outputs/app-server/native.zip')):
                p=root/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'tiny fixture bytes')
                receipt['outputs']=[dict(relativePath=receipt_relative,kind=kind,bytes=p.stat().st_size,sha256=sha256_file(p))]
                files.append(dict(relativePath=path,bytes=p.stat().st_size,sha256=sha256_file(p)))
            for name,receipt in [('jvm',adapter),('native',native)]:
                p=root/'receipts'/f'{name}.json';p.parent.mkdir(exist_ok=True);write_canonical_json(p,receipt)
                files.append(dict(relativePath=p.relative_to(root).as_posix(),bytes=p.stat().st_size,sha256=sha256_file(p)))
            spec=dict(hosts={target:dict(files=files,nativeProducer=copy.deepcopy(native['producer']),nativePackageBuildKey=native['buildKey'])},
                productVersion=adapter['productVersion'],adapterProducers={'jvm':copy.deepcopy(adapter['producer'])},sourceCommit='a'*40,
                sourceTree='b'*40,buildLogicTree='c'*40,retainedKeys=[])
            receipts=check.verify_inputs(spec,root,target,component)
            inventory=[file_record()]
            expected=check.plan_phase(PhaseInstanceId('runtime',component,'validation',target),inventory=inventory,
                versions=VERSIONS,upstream_receipts=[adapter,native],toolchain_profile_digest=check.NOT_APPLICABLE_TOOLCHAIN_DIGEST,
                flags_digest=check.NOT_APPLICABLE_FLAGS_DIGEST)
            spec['plans']={'jvm:windows-x64':expected}
            def git(*args,**kwargs):return 'a'*40 if args[-1]=='HEAD' else 'b'*40 if args[-1]=='HEAD^{tree}' else 'c'*40
            with patch.object(check.mutation,'git',side_effect=git),patch.object(check,'phase_git_inventory',return_value=inventory), \
                    patch.object(check,'git_product_versions',return_value=VERSIONS):
                self.assertEqual(expected,check.elect(spec,root,root,target,component,receipts))
                spec['retainedKeys']=[expected['buildKey']]
                with self.assertRaisesRegex(ValueError,'already-retained'):check.elect(spec,root,root,target,component,receipts)
            (root/'adapters/jvm/runner/runner.zip').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'Consumed original'):check.verify_inputs(spec,root,target,component)
            (root/'adapters/jvm/runner/runner.zip').write_bytes(b'tiny fixture bytes')
            adapter['producer']['commit']='d'*40;write_canonical_json(root/'receipts/jvm.json',adapter)
            row=next(r for r in files if r['relativePath']=='receipts/jvm.json')
            row.update(bytes=(root/'receipts/jvm.json').stat().st_size,sha256=sha256_file(root/'receipts/jvm.json'))
            with self.assertRaisesRegex(ValueError,'identity or producer'):check.verify_inputs(spec,root,target,component)

    def test_independent_raw_success_and_late_failure_no_replay(self):
        import product_reuse
        import runtime_adapter_phase
        from products.receipt import write_output_manifest
        spec=check.specification();target='windows-x64'
        controller_producer=dict(repository='codex-agent-labs/codex-agent',commit='a'*40,tree='b'*40,event='pull_request',
            pullRequest=31,workflowPath='.github/workflows/portable-reuse-proof.yml',runId=3,runAttempt=1)
        controller=dict(producer=controller_producer,target=target,javaExecutable='/fixture/java',nodeExecutable='/fixture/node')
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve();source=root/'source';source.mkdir()
            env=dict(GIT_DIR=str(root/'git'),GIT_WORK_TREE=str(source),GIT_ALTERNATE_OBJECT_DIRECTORIES=str(root/'objects'))
            write_canonical_json(root/'source-preparation.json',dict(environment=env,sourceCommit=spec['sourceCommit'],sourceTree=spec['sourceTree']))
            write_canonical_json(root/'preparation.json',dict(passed=True,selectionSha256=check.SELECTION_SHA256,
                target=target,controller=controller,sourcePreparationSha256=sha256_file(root/'source-preparation.json'),
                plans={c:spec['plans'][c+':'+target] for c in check.COMPONENTS}))
            def execute(command,**kwargs):
                context=json.loads(Path(next(s for s in command if s.startswith('-Pphase9.context=')).split('=',1)[1]).read_bytes())
                stage=Path(context['stageRoot']);component=context['component'];kind='jvm-evidence' if component=='jvm' else 'node-evidence'
                for name in (kind,'execution','test-report'):
                    p=stage/'outputs'/name/'fixture.json';p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'{}')
                write_output_manifest(stage,'runtime',component,'validation',target,'0.8.0',
                    {kind:'outputs/'+kind,'execution':'outputs/execution','test-report':'outputs/test-report'})
                kwargs['stdout'].write(b'Synthetic task success; no JVM/Node/toolchain executed\n')
                return SimpleNamespace(returncode=0)
            receipts={k:dict(producer=spec['hosts'][target]['nativeProducer'] if k=='native' else spec['adapterProducers'][k])
                      for k in ('native','jvm','node-js')}
            with patch.object(check,'hosted_context',return_value=controller),patch.object(check.mutation,'git',return_value=str(root/'objects')), \
                    patch.object(check,'verify_inputs',return_value=receipts) as verify, \
                    patch.object(check,'elect',side_effect=lambda s,i,r,t,c,v:spec['plans'][c+':'+t]), \
                    patch.object(product_reuse,'_runtime_worker_checkout'), \
                    patch.object(product_reuse,'_runtime_worker_environment',return_value=({'JAVA_HOME':'/fixture'},source/'gradlew.bat')), \
                    patch.object(runtime_adapter_phase,'preflight',return_value={'nodeExecutable':'/fixture/node','nodeVersion':'24.18.0'}), \
                    patch.object(check.subprocess,'run',side_effect=execute) as process:
                result=check.execute(root,target,'jvm')
                self.assertTrue(result['passed']);self.assertTrue(result['semanticAdmissionPending']);self.assertFalse(result['phaseAdmitted'])
                self.assertEqual(1,process.call_count);original=(root/'jvm/result.json').read_bytes()
                with self.assertRaises(FileExistsError):check.execute(root,target,'jvm')
                self.assertEqual(1,process.call_count)
                verify.side_effect=[receipts,ValueError('late original mutation')]
                with self.assertRaisesRegex(ValueError,'late original mutation'):check.execute(root,target,'node-js')
                self.assertEqual(original,(root/'jvm/result.json').read_bytes())
                self.assertTrue((root/'node-js/stage/output-manifest.json').exists())
                self.assertFalse((root/'node-js/phase-receipt.json').exists());self.assertFalse((root/'node-js/result.json').exists())

if __name__=='__main__':
    unittest.main()
