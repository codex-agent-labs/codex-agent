"""Local nested issuance and package witness; external trust seams stay explicit."""
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
from ci import sdk_native_continuation as routing
from products.inventory import canonical_json_bytes, sha256_bytes
from products.receipt import compute_build_key, write_output_manifest
from products.restore import PHASE_PLAN_KEYS, finalize_phase_object
from sdk_campaign_original_locator import fresh_sdk_worker_route
from ci.tests.test_sdk_checkpoint_core_consumer import SdkCheckpointCoreConsumerTest
from ci.tests.test_sdk_native_continuation import needs_for, job


class CoreCheckpointRoutingTest(unittest.TestCase):
    def test_new_noop_skip_and_disabled_routing_and_failed_gates(self):
        for required in (True, False):
            needs=needs_for('core-binary',required=required)
            needs['sdk-checkpoint-11']=job('success',checkpoint='new') if required else job()
            before=deepcopy(needs)
            self.assertEqual('new' if required else 'old',routing.select_checkpoint_output(needs,'old',stage='core-binary',enabled=True))
            self.assertEqual(before,needs)
            for fault in ('failed','empty','sibling','worker','malformed','live'):
                broken=deepcopy(needs)
                if fault=='failed':broken['sdk-checkpoint-11']['result']='failure'
                elif fault=='empty':broken['sdk-checkpoint-11']=job('success',checkpoint='')
                elif fault=='sibling':broken['sdk-collect-11']['result']='failure'
                elif fault=='worker':broken['sdk-core-binary']['result']='failure'
                elif fault=='malformed':broken['sdk-checkpoint-11']['outputs']['checkpoint']='x\ny'
                else:broken['sdk-checkpoint-11']['result']='in_progress'
                with self.subTest(required=required,fault=fault),self.assertRaises(ValueError):
                    routing.select_checkpoint_output(broken,'old',stage='core-binary',enabled=True)
        needs=needs_for('core-binary');needs['sdk-checkpoint-11']=job()
        self.assertEqual('',routing.select_checkpoint_output(needs,'',stage='core-binary',enabled=False))
        with self.assertRaises(ValueError):routing.select_checkpoint_output(needs,'old',stage='core-binary',enabled=False)
        needs['sdk-checkpoint-11']=job('success',checkpoint='old')
        with self.assertRaises(ValueError):routing.select_checkpoint_output(needs,'old',stage='core-binary',enabled=True)


class CoreCheckpointIssuerTest(unittest.TestCase):
    def setUp(self):
        self.core=SdkCheckpointCoreConsumerTest();self.core.setUp();self.addCleanup(self.core.doCleanups)
        self.chain,self.f,self.c=self.core.chain,self.core.f,self.core.c
        self.candidate=Path(__file__).resolve().parents[2]
        self.parent=(self.candidate/'.github/workflows/product-validation.yml').read_bytes()
        self.child=(self.candidate/'.github/workflows/sdk-core-binary-validation.yml').read_bytes()
        self.package=(self.candidate/'.github/workflows/sdk-core-package-validation.yml').read_bytes()
        self.f.policy['collectors'].append('product-validation / sdk-core-binary-wave / sdk-collect-11')
        self.f.policy['collectors'].sort()
        self.f.envelope['ownerPolicySha256']=sha256_bytes(canonical_json_bytes(self.f.policy))
        self.f.upload();self.c.output['subjectSha256']=sha256_bytes(self.f.subject)
        self.number=0

    def prepare(self,*,previous_new=True,skipped=False):
        self.core.prepare(new=previous_new)
        f,chain=self.f,self.chain
        self.previous=deepcopy(self.core.output)
        chain.current.update(status='completed',conclusion='success',completed_at='2026-10-24T11:00:00Z')
        self.core.current.update(status='completed',conclusion='skipped' if skipped else 'success',completed_at='2026-10-24T11:03:00Z')
        self.plan={**self.core.current,'id':2001,'name':'product-validation / sdk-core-binary-wave / sdk-core-binary-plan',
            'conclusion':'success','started_at':'2026-10-24T11:00:01Z','completed_at':'2026-10-24T11:00:30Z'}
        self.source={**deepcopy(chain.source),'jobName':'product-validation / sdk-core-binary-wave / sdk-collect-11',
            'jobId':2002,'artifactId':2003,'artifactSha256':sha256_bytes(b'state eleven')}
        self.collector={**self.core.current,'id':2002,'name':self.source['jobName'],
            'started_at':'2026-10-24T11:04:00Z','completed_at':'2026-10-24T11:05:00Z'}
        self.issuer={**self.core.current,'id':2004,
            'name':'product-validation / sdk-core-binary-wave / sdk-checkpoint-11 / completed-sdk-checkpoint',
            'status':'in_progress','conclusion':None,'started_at':'2026-10-24T11:06:00Z','completed_at':None}
        f.jobs.extend([self.plan,self.collector])
        if not skipped:f.jobs.append(self.issuer)
        f.artifacts[2003]=f.artifact(2003,f'codex-agent-sdk-wave-11-state-{f.producer["tree"]}-attempt-{f.producer["runAttempt"]}',
            self.source['artifactSha256'],self.source['artifactBytes'],'11:04:30')

    def add_new(self):
        f,chain=self.f,self.chain
        receipt=deepcopy(self.c.issued.receipt)
        receipt.update(component='sdk-core',phase='binary',target='common')
        receipt['buildKey']=compute_build_key(**{key:receipt[key] for key in (*completed.IDENTITY,'inputs')})
        stage=f.root/'core-stage';(stage/'outputs').mkdir(parents=True)
        (stage/'outputs/value').write_bytes(b'new Core binary fixture; no compiler invocation')
        write_output_manifest(stage,'sdk','sdk-core','binary','common','0.2.0',{'evidence':'outputs'})
        obj=finalize_phase_object(stage_root=stage,phase_plan={key:receipt[key] for key in PHASE_PLAN_KEYS},
            producer=f.producer,product_version='0.2.0',trust_domain='development',destination=f.root/'core-object')
        self.body=(f.root/'core-object'/obj['objectPath']).read_bytes();self.object=obj
        row={**{key:obj['receipt'][key] for key in completed.IDENTITY},**{key:obj[key] for key in completed.OBJECT},'objectPath':obj['objectPath']}
        request=chain.controls['runtime-state/reuse-wave-request.json']
        request['availableObjects'].append(row)
        request['phaseAuthorities'].append({**{key:row[key] for key in completed.IDENTITY},
            **{key:receipt['inputs'][key] for key in ('flagsDigest','toolchainProfileDigest','outputSchemaVersion')}})
        chain.controls['runtime-state/reuse-wave-result.json']['phases'].append({**row,'state':'retained'})
        chain.controls['runtime-state/original/sdk-core/phase-receipt.json']=obj['receipt']
        name,artifact=fresh_sdk_worker_route(completed._identity(receipt),obj['receipt'])
        self.assertEqual(self.core.current['name'],name)
        f.artifacts[2005]=f.artifact(2005,artifact,sha256_bytes(b'core original'),len(self.body)+1000,'11:02:00')

    def bind(self):
        self.chain.source=self.source;self.chain.collector=self.collector
        self.chain.bind()

    @contextmanager
    def boundaries(self):
        f=self.f
        def blob(root,revision,path,**kwargs):
            self.assertEqual(f.policy['collectorWorkflowSha'],revision)
            return {'.github/workflows/product-validation.yml':self.parent,
                '.github/workflows/sdk-core-binary-validation.yml':self.child,
                '.github/workflows/sdk-core-package-validation.yml':self.package}[path]
        def download(artifact,token):
            self.assertEqual(self.previous['native']['artifactId'],artifact['id'])
            f.downloads.append(artifact['id']);return f.raw
        @contextmanager
        def member(artifact,token,**kwargs):
            self.assertEqual(2005,artifact['id'],'qualified dependency body must not open')
            self.chain.reads.append(artifact['id']);stream=io.BytesIO()
            with zipfile.ZipFile(stream,'w') as archive:
                archive.writestr('shard/'+self.object['objectPath'],self.body)
            with zipfile.ZipFile(io.BytesIO(stream.getvalue())) as archive:
                from types import SimpleNamespace
                yield archive,SimpleNamespace(transferred=len(stream.getvalue()))
        with self.chain.boundaries(),patch('products.inventory.git_regular_blob_bytes',side_effect=blob), \
                patch.object(products,'download_artifact',side_effect=download), \
                patch('runtime_reference_archive.open_reference_archive',side_effect=member):
            collected={'controls':self.chain.controls,'references':self.chain.references,'controlArchive':{'bytes':4096},
                'stateLocator':products._runtime_original_locator(f.artifacts[2003],self.source['workflowSha'],
                    completed.PhaseInstanceId('sdk','javascript','metadata','node'),self.collector)}
            with patch.object(completed,'fetch_collector_controls',return_value=collected):yield

    def issue(self):
        self.bind();self.number+=1;work=self.f.root/('nested-'+str(self.number))
        with self.boundaries():
            report=completed.issue_checkpoint(self.f.policy,self.source,{'artifactId':2006,'artifactSha256':sha256_bytes(b'eleven controls')},
                work,root=self.f.root,revision=self.f.policy['issuerCommit'],frozen=self.c.issued.fixture.base,
                token='synthetic',previous=self.previous)
        return report,work

    def promote(self,work):
        f=self.f;f.envelope=json.loads((work/'completion.json').read_bytes());f.spec=f.envelope['recipe']
        f.source=f.spec['source'];f.collector=self.collector;f.issuer=self.issuer
        f.identity=completed.checkpoint_archive_identity(f.policy,f.source,signer_commit=f.policy['issuerCommit'],
            source_commit=f.producer['commit'],run_id=f.producer['runId'],run_attempt=f.producer['runAttempt'])
        f.selector={**f.selector,'artifactId':2007}
        f.artifacts[2006]=f.artifact(2006,completed.collector_control_artifact_name(f.source),
            f.envelope['sourceCheckpoint']['controlArtifact']['artifactSha256'],1000,'11:04:40')
        f.subject=canonical_json_bytes(f.envelope);stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('completion.json',f.subject);archive.writestr('bundle.jsonl',b'explicit native crypto fixture')
        f.raw=stream.getvalue();f.selector['artifactSha256']=sha256_bytes(f.raw)
        f.artifacts[2007]=f.artifact(2007,f.identity['artifactName'],f.selector['artifactSha256'],len(f.raw),'11:06:30')
        self.previous={'kind':'sdk-checkpoint','source':f.source,'native':f.selector,'subjectSha256':sha256_bytes(f.subject)}

    def package_ready(self):
        f=self.f
        self.issuer.update(status='completed',conclusion='success',completed_at='2026-10-24T11:07:00Z')
        self.result={**self.issuer,'id':2008,'name':'product-validation / sdk-core-binary-wave / sdk-core-binary-result',
            'started_at':'2026-10-24T11:08:00Z','completed_at':'2026-10-24T11:09:00Z'}
        self.current={**self.issuer,'id':2009,'name':'product-validation / sdk-core-package-wave / sdk-core-package-common',
            'status':'in_progress','conclusion':None,'started_at':'2026-10-24T11:10:00Z','completed_at':None}
        f.jobs.extend([self.result,self.current])
        f.run['referenced_workflows'].append({'path':native.REPOSITORY+'/.github/workflows/sdk-core-package-validation.yml@'+f.policy['collectorWorkflowSha'],
            'sha':f.policy['collectorWorkflowSha']})
        f.downloads.clear();f.verified.clear();f.urls.clear();self.chain.reads.clear()

    @contextmanager
    def open_package(self):
        self.number+=1
        with self.boundaries(),completed.checkpoint_consumer(self.f.policy,self.previous,self.f.root/('package-'+str(self.number)),
                root=self.f.root,consumer=self.c.consumer,job='sdk-core-package',token='synthetic') as witness:
            yield witness

    def check_package(self):
        with self.open_package() as witness:
            cap=self.c.capability(witness)
            cap.check_consumer(self.c.consumer)
            self.assertEqual([],self.chain.reads)
            self.assertEqual([self.previous['native']['artifactId']],self.f.downloads)
            self.assertEqual(1,len(self.f.verified))
        with self.assertRaisesRegex(ValueError,'closed'):cap.completed_phases()

    def test_third_issuance_reads_only_new_core_body_then_package_reuses_flat_result(self):
        self.prepare();self.add_new();report,work=self.issue()
        self.assertEqual([2005],self.chain.reads)
        self.assertEqual([1990],self.f.downloads)
        self.assertEqual(len(self.body),report['verifiedObjectBytes'])
        self.assertEqual(4,len(json.loads((work/'completion.json').read_bytes())['completion']['members']))
        self.promote(work);self.package_ready();self.check_package()

    def test_noop_eleven_forwards_ten_or_nine_without_new_subject(self):
        for previous_new in (True,False):
            other=CoreCheckpointIssuerTest();other.setUp()
            try:
                other.prepare(previous_new=previous_new);report,work=other.issue()
                self.assertEqual(other.previous,report['reusedCheckpointOutput'])
                self.assertFalse((work/'completion.json').exists());self.assertEqual([],other.chain.reads)
                other.package_ready();other.check_package()
            finally:other.doCleanups()

    def test_full_reuse_skips_issuer_and_forwards_exact_previous_to_package(self):
        for previous_new in (True,False):
            other=CoreCheckpointIssuerTest();other.setUp()
            try:
                other.prepare(previous_new=previous_new,skipped=True);other.package_ready()
                self.assertNotIn(other.issuer,other.f.jobs)
                other.check_package()
            finally:other.doCleanups()

    def test_nested_issuer_requires_exact_child_previous_input_and_successful_collector(self):
        self.prepare();saved=deepcopy((self.child,self.collector,self.issuer,self.f.run))
        for fault in ('wrong-input','missing-edge','collector-failed','issuer-early','issuer-failed','duplicate-child'):
            with self.subTest(fault=fault):
                self.child,collected,issued,self.f.run=deepcopy(saved)
                self.collector.clear();self.collector.update(collected)
                self.issuer.clear();self.issuer.update(issued)
                if fault=='wrong-input':self.child=self.child.replace(b'sdk-preceding-checkpoint: ${{ inputs.sdkCheckpoint }}',b'sdk-preceding-checkpoint: wrong')
                elif fault=='missing-edge':self.child=self.child.replace(b'[sdk-core-binary-plan, sdk-core-binary, sdk-collect-11, sdk-checkpoint-11]',b'[sdk-core-binary-plan, sdk-core-binary, sdk-collect-11]')
                elif fault=='collector-failed':self.collector['conclusion']='failure'
                elif fault=='issuer-early':self.issuer['started_at']='2026-10-24T11:04:00Z'
                elif fault=='issuer-failed':self.issuer.update(status='completed',conclusion='failure')
                else:self.f.run['referenced_workflows'].append(deepcopy(self.f.run['referenced_workflows'][-1]))
                with self.assertRaises(ValueError):self.issue()
                self.assertEqual([],self.chain.reads)

    def test_wrong_child_output_forwarder_or_skip_role_never_grants_package_witness(self):
        self.prepare(skipped=True);self.package_ready()
        saved=deepcopy((self.parent,self.child,self.package,self.f.jobs,self.f.run))
        for fault in ('missing-child','duplicate-child','wrong-child','result-failed','result-early','plan-late','collector-missing',
                      'worker-failed','worker-wrong-run','duplicate-result','call-output','job-output','package-input','package-env','duplicate-output'):
            with self.subTest(fault=fault):
                self.parent,self.child,self.package,self.f.jobs,self.f.run=deepcopy(saved)
                by_id={row['id']:row for row in self.f.jobs}
                if fault=='missing-child':self.f.run['referenced_workflows'].pop()
                elif fault=='duplicate-child':self.f.run['referenced_workflows'].append(deepcopy(self.f.run['referenced_workflows'][-1]))
                elif fault=='wrong-child':self.f.run['referenced_workflows'][-1]['sha']='a'*40
                elif fault=='result-failed':by_id[2008]['conclusion']='failure'
                elif fault=='result-early':by_id[2008]['started_at']='2026-10-24T10:59:00Z'
                elif fault=='plan-late':by_id[2001]['completed_at']='2026-10-24T11:08:30Z'
                elif fault=='collector-missing':self.f.jobs.remove(by_id[2002])
                elif fault=='worker-failed':by_id[2000]['conclusion']='failure'
                elif fault=='worker-wrong-run':by_id[2000]['run_id']+=1
                elif fault=='duplicate-result':self.f.jobs.append(deepcopy(by_id[2008]))
                elif fault=='call-output':self.child=self.child.replace(b'value: ${{ jobs.sdk-core-binary-result.outputs.checkpoint }}',b'value: wrong')
                elif fault=='job-output':self.child=self.child.replace(b'checkpoint: ${{ steps.result.outputs.checkpoint }}',b'checkpoint: wrong')
                elif fault=='package-input':self.parent=self.parent.replace(b'binaryWave: ${{ toJSON(needs.sdk-core-binary-wave) }}',b'binaryWave: wrong')
                elif fault=='package-env':self.package=self.package.replace(b'CODEX_AGENT_SDK_CHECKPOINT: ${{ fromJSON(inputs.binaryWave).outputs.checkpoint }}',b'CODEX_AGENT_SDK_CHECKPOINT: wrong')
                else:self.child=self.child.replace(b'      checkpoint:\n        value:',b'      checkpoint:\n        value: wrong\n      checkpoint:\n        value:',1)
                with self.assertRaises(ValueError):
                    with self.open_package():self.fail('invalid route granted authority')


if __name__=='__main__':unittest.main()
