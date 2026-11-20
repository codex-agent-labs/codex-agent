"""Actual Core caller/child and forwarded no-op witness; external trust seams explicit."""
from contextlib import contextmanager
from copy import deepcopy
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import zipfile

import completed_sdk_reuse as completed
import product_reuse as products
import reuse_qualification as native
from products.inventory import canonical_json_bytes, sha256_bytes
from ci.tests.test_sdk_checkpoint_chain import SdkCheckpointChainTest


class SdkCheckpointCoreConsumerTest(unittest.TestCase):
    def setUp(self):
        self.chain=SdkCheckpointChainTest();self.chain.setUp();self.addCleanup(self.chain.doCleanups)
        self.c=self.chain.fixture;self.f=self.chain.f
        candidate=Path(__file__).resolve().parents[2]
        self.parent=(candidate/'.github/workflows/product-validation.yml').read_bytes()
        self.child=(candidate/'.github/workflows/sdk-core-binary-validation.yml').read_bytes()
        self.number=0

    def prepare(self,*,new=False):
        chain,c,f=self.chain,self.c,self.f
        if new:chain.add_new()
        report,work=chain.issue()
        if new:
            f.envelope=json.loads((work/'completion.json').read_bytes());f.spec=f.envelope['recipe']
            f.source=f.spec['source'];f.collector=chain.collector;f.issuer=chain.current
            f.identity=completed.checkpoint_archive_identity(f.policy,f.source,signer_commit=f.policy['issuerCommit'],
                source_commit=f.producer['commit'],run_id=f.producer['runId'],run_attempt=f.producer['runAttempt'])
            f.selector={**f.selector,'artifactId':1990}
            f.artifacts[998]=f.artifact(998,completed.collector_control_artifact_name(f.source),
                f.envelope['sourceCheckpoint']['controlArtifact']['artifactSha256'],1000,'10:52:00')
            f.subject=canonical_json_bytes(f.envelope);stream=io.BytesIO()
            with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr('completion.json',f.subject);archive.writestr('bundle.jsonl',b'explicit native crypto fixture')
            f.raw=stream.getvalue();f.selector['artifactSha256']=sha256_bytes(f.raw)
            f.artifacts[1990]=f.artifact(1990,f.identity['artifactName'],f.selector['artifactSha256'],len(f.raw),'10:58:00')
            self.output={'kind':'sdk-checkpoint','source':f.source,'native':f.selector,'subjectSha256':sha256_bytes(f.subject)}
        else:
            self.assertFalse((work/'completion.json').exists())
            self.assertEqual(c.output,report['reusedCheckpointOutput'])
            self.output=report['reusedCheckpointOutput']
        chain.current.update(status='completed',conclusion='success',completed_at='2026-10-24T11:00:00Z')
        self.current={'id':2000,'name':'product-validation / sdk-core-binary-wave / sdk-core-binary-common',
            'run_id':f.producer['runId'],'head_sha':f.run['head_sha'],'status':'in_progress','conclusion':None,
            'started_at':'2026-10-24T11:01:00Z','completed_at':None}
        f.jobs.append(self.current)
        f.run['referenced_workflows'].append({'path':native.REPOSITORY+'/.github/workflows/sdk-core-binary-validation.yml@'+f.policy['collectorWorkflowSha'],
            'sha':f.policy['collectorWorkflowSha']})
        f.downloads.clear();f.verified.clear();f.urls.clear();chain.reads.clear()

    @contextmanager
    def open(self):
        f=self.f;self.number+=1
        def blob(root,revision,path,**kwargs):
            self.assertEqual(f.policy['collectorWorkflowSha'],revision)
            if path=='.github/workflows/product-validation.yml':return self.parent
            if path=='.github/workflows/sdk-core-binary-validation.yml':return self.child
            raise AssertionError(path)
        def download(artifact,token):
            self.assertEqual(self.output['native']['artifactId'],artifact['id'])
            f.downloads.append(artifact['id']);return f.raw
        with self.chain.boundaries(),patch('products.inventory.git_regular_blob_bytes',side_effect=blob), \
                patch.object(products,'download_artifact',side_effect=download), \
                completed.checkpoint_consumer(f.policy,self.output,f.root/('core-'+str(self.number)),root=f.root,
                    consumer=self.c.consumer,job='sdk-core-binary',token='synthetic') as witness:
            yield witness

    def check_capability(self,witness):
        cap=self.c.capability(witness)
        self.assertIs(type(cap),native.CompletedFrozenReuse)
        cap.check_consumer(self.c.consumer)
        for phase in self.f.spec['completedPhases']:self.assertIsNotNone(cap.envelope(phase))
        self.assertEqual([],self.chain.reads)
        self.assertEqual([self.output['native']['artifactId']],self.f.downloads)
        self.assertEqual(1,len(self.f.verified))
        self.assertEqual(self.f.policy['bootstrap'],witness.bootstrap())
        return cap

    def test_new_checkpoint_ten_reaches_actual_core_child_capability(self):
        self.prepare(new=True)
        with self.open() as witness:cap=self.check_capability(witness)
        with self.assertRaisesRegex(ValueError,'closed'):cap.completed_phases()

    def test_actual_noop_ten_forwards_nine_to_core_without_inventing_upload(self):
        self.prepare()
        self.assertEqual(990,self.output['native']['artifactId'])
        with self.open() as witness:cap=self.check_capability(witness)
        with self.assertRaisesRegex(ValueError,'closed'):cap.completed_phases()

    def test_wrong_child_forwarder_or_literal_selector_path_never_grants_capability(self):
        self.prepare()
        saved=deepcopy((self.parent,self.child,self.f.jobs,self.f.run))
        for fault in ('missing-child','wrong-child','duplicate-child','forwarder-failed','forwarder-live',
                      'forwarder-ambiguous','forwarder-early','wrong-caller','wrong-input','wrong-env','duplicate-input','duplicate-env','missing-edge'):
            with self.subTest(fault=fault):
                self.parent,self.child,self.f.jobs,self.f.run=deepcopy(saved)
                forwarder=next(row for row in self.f.jobs if row['id']==997)
                if fault=='missing-child':self.f.run['referenced_workflows'].pop()
                elif fault=='wrong-child':self.f.run['referenced_workflows'][-1]['sha']='a'*40
                elif fault=='duplicate-child':self.f.run['referenced_workflows'].append(deepcopy(self.f.run['referenced_workflows'][-1]))
                elif fault=='forwarder-failed':forwarder['conclusion']='failure'
                elif fault=='forwarder-live':forwarder.update(status='in_progress',conclusion=None,completed_at=None)
                elif fault=='forwarder-ambiguous':self.f.jobs.append(deepcopy(forwarder))
                elif fault=='forwarder-early':forwarder['started_at']='2026-10-24T10:39:00Z'
                elif fault=='wrong-caller':self.parent=self.parent.replace(b'uses: ./.github/workflows/sdk-core-binary-validation.yml',b'uses: ./.github/workflows/other.yml')
                elif fault=='wrong-input':self.parent=self.parent.replace(b'sdkCheckpoint: ${{ needs.sdk-checkpoint-10.outputs.checkpoint }}',b'sdkCheckpoint: ${{ needs.sdk-checkpoint-9.outputs.checkpoint }}')
                elif fault=='wrong-env':self.child=self.child.replace(b'CODEX_AGENT_SDK_CHECKPOINT: ${{ inputs.sdkCheckpoint }}',b'CODEX_AGENT_SDK_CHECKPOINT: wrong')
                elif fault=='duplicate-input':self.parent=self.parent.replace(b'      sdkCheckpoint: ${{ needs.sdk-checkpoint-10.outputs.checkpoint }}',b'      sdkCheckpoint: ${{ needs.sdk-checkpoint-10.outputs.checkpoint }}\n      sdkCheckpoint: wrong')
                elif fault=='duplicate-env':self.child=self.child.replace(b'      CODEX_AGENT_SDK_CHECKPOINT: ${{ inputs.sdkCheckpoint }}',b'      CODEX_AGENT_SDK_CHECKPOINT: ${{ inputs.sdkCheckpoint }}\n      CODEX_AGENT_SDK_CHECKPOINT: wrong')
                else:self.parent=self.parent.replace(b'[plan, sdk-plan, sdk-ios-metadata-result, sdk-checkpoint-10]',b'[plan, sdk-plan, sdk-ios-metadata-result]')
                with self.assertRaises(ValueError):
                    with self.open():self.fail('invalid child or forwarded checkpoint granted witness')


if __name__=='__main__':unittest.main()
