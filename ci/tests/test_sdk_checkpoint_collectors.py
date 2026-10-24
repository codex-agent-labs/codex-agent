"""Actual collector capability; product collection/advance are explicit process seams."""
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

import completed_sdk_reuse as completed
import product_reuse as products
import sdk_workflow as workflow
from products.inventory import canonical_json_bytes,sha256_bytes
from ci.tests.test_sdk_checkpoint_core_consumer import SdkCheckpointCoreConsumerTest


class CheckpointCollectorTest(unittest.TestCase):
    def setUp(self):
        self.core=SdkCheckpointCoreConsumerTest();self.core.setUp();self.addCleanup(self.core.doCleanups)
        self.chain,self.c,self.f=self.core.chain,self.core.c,self.core.f
        root=Path(__file__).resolve().parents[2]
        self.parent=(root/'.github/workflows/product-validation.yml').read_bytes()
        self.child=(root/'.github/workflows/sdk-core-binary-validation.yml').read_bytes()
        self.f.policy['collectors'].append('product-validation / sdk-core-binary-wave / sdk-collect-11')
        self.f.policy['collectors'].sort();self.f.envelope['ownerPolicySha256']=sha256_bytes(canonical_json_bytes(self.f.policy))
        self.f.upload();self.c.output['subjectSha256']=sha256_bytes(self.f.subject)
        self.number=0

    def prepare(self,*,nested=False,new=False):
        self.nested=nested
        if nested:
            self.core.prepare(new=new);self.output=self.core.output
            self.current=self.core.current
            self.current['name']='product-validation / sdk-core-binary-wave / sdk-collect-11'
        else:
            self.output=self.c.output;self.current=self.chain.collector
            self.current.update(status='in_progress',conclusion=None,completed_at=None)
        self.job='sdk-collect-11' if nested else 'sdk-collect-10'
        self.f.downloads.clear();self.f.verified.clear();self.chain.reads.clear()

    @contextmanager
    def open(self):
        self.number+=1;f=self.f
        def blob(root,revision,path,**kwargs):
            self.assertEqual(f.policy['collectorWorkflowSha'],revision)
            return {'.github/workflows/product-validation.yml':self.parent,
                '.github/workflows/sdk-core-binary-validation.yml':self.child}[path]
        def download(artifact,token):
            self.assertEqual(self.output['native']['artifactId'],artifact['id'])
            f.downloads.append(artifact['id']);return f.raw
        with self.chain.boundaries(),patch('products.inventory.git_regular_blob_bytes',side_effect=blob), \
                patch.object(products,'download_artifact',side_effect=download), \
                completed.checkpoint_consumer(f.policy,self.output,f.root/('collector-'+str(self.number)),
                    root=f.root,consumer=self.c.consumer,job=self.job,token='synthetic') as witness:
            yield witness

    def check_collection(self):
        f=self.f
        with self.open() as witness:
            cap=self.c.capability(witness)
            original=f.root/'collector-input';destination=f.root/'collector-output'
            for name in ('product-resume-inputs','product-resume-state','runtime-state'):
                (original/name).mkdir(parents=True,exist_ok=True)
            calls=[]
            def collect(*args,**kwargs):
                self.assertIs(cap,kwargs['completed_frozen']);cap.check_consumer(self.c.consumer)
                self.assertEqual('core-binary' if self.nested else 'ios-metadata',kwargs['sdk_family'])
                calls.append('collect');return {'rows':[]}
            def advance(*args,**kwargs):
                self.assertIs(cap,kwargs['completed_frozen']);cap.check_consumer(self.c.consumer)
                self.assertTrue(kwargs['checkpoint_controls']);calls.append('advance')
                Path(args[4]).mkdir(parents=True);return {'matrices':{'sdk':[]}}
            with patch.object(products,'collect_runtime_workers',side_effect=collect), \
                    patch.object(products,'advance_products',side_effect=advance):
                workflow.collect(original,destination,f.root/'github-output',wave=11 if self.nested else 10,
                    family='core-binary' if self.nested else 'ios-metadata',trusted_workflow_sha=f.policy['collectorWorkflowSha'],
                    repository_root=f.root,token='synthetic',completed_frozen=cap,checkpoint_controls=True)
            self.assertEqual(['collect','advance'],calls)
            self.assertEqual([],self.chain.reads)
            self.assertEqual([self.output['native']['artifactId']],f.downloads)
            self.assertEqual(1,len(f.verified))
        with self.assertRaisesRegex(ValueError,'closed'):cap.completed_phases()

    def test_top_collector_consumes_nine_and_threads_live_capability_to_both_collection_stages(self):
        self.prepare();self.check_collection()

    def test_child_collector_consumes_ten_or_forwarded_nine_without_old_body_reads(self):
        for new in (True,False):
            other=CheckpointCollectorTest();other.setUp()
            try:other.prepare(nested=True,new=new);other.check_collection()
            finally:other.doCleanups()

    def test_wrong_current_collector_edge_or_selector_does_not_grant_capability(self):
        self.prepare();saved=deepcopy((self.parent,self.current))
        for case in ('needs','selector','duplicate-selector','role','failed','early'):
            with self.subTest(case=case):
                self.parent,current=deepcopy(saved);self.current.clear();self.current.update(current)
                if case=='needs':self.parent=self.parent.replace(b'[plan, sdk-plan, sdk-ios-validation-result, sdk-ios-metadata-plan, sdk-ios-metadata, sdk-checkpoint-9]',b'[plan, sdk-plan, sdk-ios-validation-result, sdk-ios-metadata-plan, sdk-ios-metadata]')
                elif case=='selector':self.parent=self.parent.replace(b'CODEX_AGENT_SDK_CHECKPOINT: ${{ needs.sdk-checkpoint-9.outputs.checkpoint }}',b'CODEX_AGENT_SDK_CHECKPOINT: wrong')
                elif case=='duplicate-selector':self.parent=self.parent.replace(b'      CODEX_AGENT_SDK_CHECKPOINT: ${{ needs.sdk-checkpoint-9.outputs.checkpoint }}',b'      CODEX_AGENT_SDK_CHECKPOINT: wrong\n      CODEX_AGENT_SDK_CHECKPOINT: ${{ needs.sdk-checkpoint-9.outputs.checkpoint }}')
                elif case=='role':self.current['name']='unrelated'
                elif case=='failed':self.current.update(status='completed',conclusion='failure')
                else:self.current['started_at']='2026-10-24T10:39:00Z'
                with self.assertRaises(ValueError):
                    with self.open():self.fail('invalid collector granted authority')

    def test_child_collector_requires_exact_local_role_selector_and_worker_edges(self):
        self.prepare(nested=True,new=False)
        saved=deepcopy((self.child,self.f.run,self.current))
        for case in ('missing-child','missing-job','wrong-needs','selector','duplicate-selector','skipped'):
            with self.subTest(case=case):
                self.child,self.f.run,current=deepcopy(saved);self.current.clear();self.current.update(current)
                if case=='missing-child':self.f.run['referenced_workflows'].pop()
                elif case=='missing-job':self.child=self.child.replace(b'\n  sdk-collect-11:\n',b'\n  unrelated-collector:\n')
                elif case=='wrong-needs':self.child=self.child.replace(b'needs: [sdk-core-binary-plan, sdk-core-binary]',b'needs: [sdk-core-binary-plan]')
                elif case=='selector':self.child=self.child.replace(b'CODEX_AGENT_SDK_CHECKPOINT: ${{ inputs.sdkCheckpoint }}',b'CODEX_AGENT_SDK_CHECKPOINT: wrong')
                elif case=='duplicate-selector':self.child=self.child.replace(b'      CODEX_AGENT_SDK_CHECKPOINT: ${{ inputs.sdkCheckpoint }}',b'      CODEX_AGENT_SDK_CHECKPOINT: wrong\n      CODEX_AGENT_SDK_CHECKPOINT: ${{ inputs.sdkCheckpoint }}')
                else:self.current.update(status='completed',conclusion='skipped')
                with self.assertRaises(ValueError):
                    with self.open():self.fail('invalid child collector granted authority')


class PackageCheckpointCollectorTest(unittest.TestCase):
    def setUp(self):
        from ci.tests.test_sdk_checkpoint_core_issuer import CoreCheckpointIssuerTest
        self.core=CoreCheckpointIssuerTest();self.core.setUp();self.addCleanup(self.core.doCleanups)
        self.f,self.c,self.chain=self.core.f,self.core.c,self.core.chain
        self.f.policy['collectors'].append(completed._CORE_PACKAGE_COLLECTOR)
        self.f.policy['collectors'].sort()
        self.f.envelope['ownerPolicySha256']=sha256_bytes(canonical_json_bytes(self.f.policy))
        self.f.upload();self.c.output['subjectSha256']=sha256_bytes(self.f.subject)
        self.number=0

    def prepare(self,mode='new'):
        self.core.prepare(previous_new=mode!='nine',skipped=mode=='skipped')
        if mode=='new':
            self.core.add_new();_,work=self.core.issue();self.core.promote(work)
        elif mode!='skipped':self.core.issue()
        self.core.package_ready()
        self.core.current.update(status='completed',conclusion='success',completed_at='2026-10-24T11:11:00Z')
        self.current={**self.core.current,'id':2010,'name':completed._CORE_PACKAGE_COLLECTOR,
            'status':'in_progress','conclusion':None,'started_at':'2026-10-24T11:12:00Z','completed_at':None}
        self.f.jobs.append(self.current)

    @contextmanager
    def open(self):
        self.number+=1
        with self.core.boundaries(),completed.checkpoint_consumer(self.f.policy,self.core.previous,
                self.f.root/('package-collector-'+str(self.number)),root=self.f.root,
                consumer=self.c.consumer,job='sdk-collect-12',token='synthetic') as witness:
            yield witness

    def collect(self,cap,*,fail=None):
        original=self.f.root/'collector-input';destination=self.f.root/('collector-output-'+str(self.number))
        for name in ('product-resume-inputs','product-resume-state','runtime-state'):
            (original/name).mkdir(parents=True,exist_ok=True)
        calls=[]
        def collect(*args,**kwargs):
            self.assertIs(cap,kwargs['completed_frozen']);cap.check_consumer(self.c.consumer)
            self.assertEqual('core-package',kwargs['sdk_family'])
            self.assertEqual('.github/workflows/sdk-core-package-validation.yml',kwargs['sdk_worker_workflow_path'])
            self.assertEqual(self.core.current['name'],kwargs['sdk_worker_job_name'])
            calls.append('collect')
            if fail=='collect':raise ValueError('new package verification failed')
            return {'rows':[]}
        def advance(*args,**kwargs):
            self.assertIs(cap,kwargs['completed_frozen']);cap.check_consumer(self.c.consumer)
            self.assertEqual('core-package',kwargs['sdk_family'])
            self.assertFalse(kwargs['checkpoint_controls']);calls.append('advance')
            if fail=='advance':raise ValueError('new package verification failed')
            Path(args[4]).mkdir(parents=True);return {'matrices':{'sdk':[]}}
        with patch.object(products,'collect_runtime_workers',side_effect=collect), \
                patch.object(products,'advance_products',side_effect=advance):
            workflow.collect(original,destination,self.f.root/'github-output',wave=12,family='core-package',
                trusted_workflow_sha=self.f.policy['collectorWorkflowSha'],repository_root=self.f.root,
                sdk_worker_workflow_path='.github/workflows/sdk-core-package-validation.yml',
                sdk_worker_job_name=self.core.current['name'],token='synthetic',completed_frozen=cap)
        self.assertEqual(['collect','advance'],calls)

    def test_package_collector_accepts_eleven_and_exact_ten_nine_or_skipped_forwarding(self):
        for mode in ('new','ten','nine','skipped'):
            with self.subTest(mode=mode):
                other=PackageCheckpointCollectorTest();other.setUp()
                try:
                    other.prepare(mode)
                    with other.open() as witness:
                        cap=other.c.capability(witness);other.collect(cap)
                        self.assertEqual([],other.chain.reads)
                        self.assertEqual([other.core.previous['native']['artifactId']],other.f.downloads)
                        self.assertEqual(1,len(other.f.verified))
                    with self.assertRaisesRegex(ValueError,'closed'):cap.completed_phases()
                finally:other.doCleanups()

    def test_package_collector_requires_exact_owner_role_edges_and_fresh_observation(self):
        self.prepare()
        saved=deepcopy((self.core.package,self.f.run,self.current,self.f.policy))
        for fault in ('missing-child','duplicate-child','missing-job','name','needs','selector','duplicate-selector',
                      'owner','wrong-job','duplicate-job','finished','early','wrong-head'):
            with self.subTest(fault=fault):
                self.core.package,self.f.run,current,self.f.policy=deepcopy(saved)
                self.current.clear();self.current.update(current)
                if fault=='missing-child':self.f.run['referenced_workflows'].pop()
                elif fault=='duplicate-child':self.f.run['referenced_workflows'].append(deepcopy(self.f.run['referenced_workflows'][-1]))
                elif fault=='missing-job':self.core.package=self.core.package.replace(b'\n  sdk-collect-12:\n',b'\n  unrelated:\n')
                elif fault=='name':self.core.package=self.core.package.replace(b'\n  sdk-collect-12:\n',b'\n  sdk-collect-12:\n    name: unrelated\n')
                elif fault=='needs':self.core.package=self.core.package.replace(b'needs: [sdk-core-package]',b'needs: [unrelated]')
                elif fault=='selector':self.core.package=self.core.package.replace(b'CODEX_AGENT_SDK_CHECKPOINT: ${{ fromJSON(inputs.binaryWave).outputs.checkpoint }}',b'CODEX_AGENT_SDK_CHECKPOINT: wrong')
                elif fault=='duplicate-selector':self.core.package=self.core.package.replace(b'      CODEX_AGENT_SDK_CHECKPOINT: ${{ fromJSON(inputs.binaryWave).outputs.checkpoint }}',b'      CODEX_AGENT_SDK_CHECKPOINT: wrong\n      CODEX_AGENT_SDK_CHECKPOINT: ${{ fromJSON(inputs.binaryWave).outputs.checkpoint }}')
                elif fault=='owner':self.f.policy['collectors'].remove(completed._CORE_PACKAGE_COLLECTOR)
                elif fault=='wrong-job':self.current['name']='product-validation / sdk-collect-12'
                elif fault=='duplicate-job':self.f.jobs.append(deepcopy(self.current))
                elif fault=='finished':self.current.update(status='completed',conclusion='success')
                elif fault=='early':self.current['started_at']='2026-10-24T11:08:30Z'
                else:self.current['head_sha']='a'*40
                try:
                    with self.assertRaises(ValueError):
                        with self.open():self.fail('invalid package collector granted authority')
                finally:
                    if fault=='duplicate-job':self.f.jobs.pop()

    def test_package_collection_failure_propagates_and_closes_dependency_capability(self):
        self.prepare()
        for stage in ('collect','advance'):
            with self.subTest(stage=stage):
                with self.assertRaisesRegex(ValueError,'new package verification failed'):
                    with self.open() as witness:
                        cap=self.c.capability(witness);self.collect(cap,fail=stage)
                with self.assertRaisesRegex(ValueError,'closed'):cap.completed_phases()


if __name__=='__main__':unittest.main()
