"""One real new object through the existing issuer; native/Git/Contract seams explicit."""
from contextlib import ExitStack, contextmanager
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

import completed_sdk_reuse as completed
import product_reuse as products
import reuse_qualification as native
from products.inventory import canonical_json_bytes, sha256_bytes
from products.receipt import write_output_manifest
from products.restore import PHASE_PLAN_KEYS, finalize_phase_object, object_relative_path
from ci.tests.test_prepare_sdk_completion import PrepareSdkCompletionTest
from sdk_campaign_original_locator import fresh_sdk_worker_route


class SdkCheckpointIssuerTest(unittest.TestCase):
    def setUp(self):
        self.fixture = PrepareSdkCompletionTest(); self.fixture.setUp()
        f = self.fixture
        temporary = tempfile.TemporaryDirectory(prefix='checkpoint-issuer-test-')
        self.addCleanup(temporary.cleanup); self.root = Path(temporary.name).resolve()
        self.producer = f.producer
        self.producer["workflowPath"] = ".github/workflows/ci.yml"
        f.source['inventoryCommit'] = self.producer['commit']
        receipt = f.controls['held-python/phase-receipt.json']
        stage = self.root / 'stage'; (stage / 'outputs').mkdir(parents=True)
        (stage / 'outputs/value').write_bytes(b'genuine local object bytes; synthetic SDK product')
        write_output_manifest(stage, 'sdk', 'python', 'package', 'desktop', '0.2.0', {'evidence':'outputs'})
        self.verified = finalize_phase_object(stage_root=stage,
            phase_plan={name: receipt[name] for name in PHASE_PLAN_KEYS}, producer=self.producer,
            product_version='0.2.0', trust_domain='development', destination=self.root / 'shard')
        self.body = (self.root / 'shard' / self.verified['objectPath']).read_bytes()
        receipt = self.verified['receipt']; self.receipt = receipt
        f.controls['held-python/phase-receipt.json'] = receipt
        row = {**{key: receipt[key] for key in completed.IDENTITY},
               **{key: self.verified[key] for key in completed.OBJECT}}
        f.request['availableObjects'][-1].update(row); f.result['phases'][-1].update(row)
        f.object.update(relativePath='runtime-state/original-objects/' + self.verified['objectPath'],
                        bytes=len(self.body), sha256=self.verified['objectSha256'])
        f.bind()
        old = f.previous['extension']; old['spec'].update(
            originals=[f.originals[0]], contractControls=f.policy['contractControls'], contractFiles=f.policy['contractFiles'])
        self.old_locator = {'original':'already native-qualified'}
        old['proof']['originals'] = [self.old_locator]
        old_phase = old['spec']['completedPhases'][0]
        old['proof']['members'] = [{'relativePath':'shard/' + object_relative_path(old_phase['buildKey'],old_phase['receiptSha256']),
                                  'sha256':old_phase['objectSha256'], 'bytes':37}]
        f.previous.update(spec=f.parent_sdk['spec'])
        self.policy = {'schemaVersion':1,'kind':'sdk-checkpoint-owner','issuerCommit':'d'*40,
            'collectorWorkflowSha':f.source['workflowSha'], 'parent':f.policy['parent'],
            'parentProofSha256':f.policy['parentProofSha256'], 'bootstrap':f.policy['reuseCompletion'],
            'bootstrapProofSha256':sha256_bytes(canonical_json_bytes(old['proof'])), 'collectors':[f.source['jobName']]}
        self.control_selector = {'artifactId':990,'artifactSha256':sha256_bytes(b'authenticated control fixture')}
        self.collected = {'source':f.source,'controls':f.controls,'references':f.references,
            'stateLocator':{'source':f.source['artifactId']},'controlArchive':{'bytes':4096}}
        self.run = {'id':self.producer['runId'],'run_attempt':self.producer['runAttempt'],
            'path':'.github/workflows/ci.yml','event':'pull_request','head_sha':'f'*40,'status':'in_progress',
            'pull_requests':[{'number':31,'base':{'sha':'1'*40},'head':{'sha':'f'*40}}],
            'repository':{'full_name':native.REPOSITORY,'fork':False},
            'head_repository':{'full_name':native.REPOSITORY,'fork':False},
            'referenced_workflows':[{'path':native.REPOSITORY+'/.github/workflows/product-validation.yml@'+f.source['workflowSha'],
                                     'sha':f.source['workflowSha']}]}
        self.commit = {'sha':self.producer['commit'],'tree':{'sha':self.producer['tree']},
                       'parents':[{'sha':'1'*40},{'sha':'f'*40}]}
        job,name = fresh_sdk_worker_route(completed._identity(receipt),receipt)
        self.job = {'id':444,'name':job,'run_id':self.producer['runId'],'head_sha':self.run['head_sha'],
            'status':'completed','conclusion':'success','started_at':'2026-10-24T10:00:00Z','completed_at':'2026-10-24T10:10:00Z'}
        self.artifact = {'id':445,'name':name,'digest':sha256_bytes(b'outer worker upload'), 'size_in_bytes':len(self.body)+1000,
            'expired':False,'created_at':'2026-10-24T10:05:00Z',
            'archive_download_url':f'https://api.github.com/repos/{native.REPOSITORY}/actions/artifacts/445/zip',
            'workflow_run':{'id':self.producer['runId'],'head_sha':self.run['head_sha']}}
        self.urls=[];self.member_reads=[];self.number=0;self.tamper=False

    def api(self,url,token):
        self.urls.append(url)
        if '/git/commits/' in url:return deepcopy(self.commit)
        if '/actions/artifacts/445' in url:return deepcopy(self.artifact)
        if '/attempts/' in url:return deepcopy(self.run)
        raise AssertionError(url)

    def listing(self,url,key,token):
        self.urls.append(url)
        if key=='jobs':return [deepcopy(self.job)]
        if key=='artifacts':return [deepcopy(self.artifact)]
        raise AssertionError((url,key))

    @contextmanager
    def member(self,artifact,token,**bounds):
        self.assertEqual(445,artifact['id'],'old objects must never open')
        self.member_reads.append(artifact['id'])
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as out:
            out.writestr('shard/'+self.verified['objectPath'],self.body + (b'tamper' if self.tamper else b''))
        with zipfile.ZipFile(io.BytesIO(stream.getvalue())) as archive:
            yield archive,SimpleNamespace(transferred=len(stream.getvalue()))

    def issue(self):
        f=self.fixture;self.number+=1;work=self.root/str(self.number)
        with ExitStack() as stack:
            stack.enter_context(patch.object(products,'api_json',side_effect=self.api))
            stack.enter_context(patch.object(products,'paginated_items',side_effect=self.listing))
            self.prime=stack.enter_context(patch.object(products,'_prime_runtime_artifact_metadata',
                wraps=products._prime_runtime_artifact_metadata))
            stack.enter_context(patch('sdk_handoff._ensure_observed_sdk_commit'))
            stack.enter_context(patch.object(products,'_validate_plan',return_value={}))
            stack.enter_context(patch.object(completed,'_inventory_revision',return_value=self.producer['commit']))
            stack.enter_context(patch.object(completed,'validate_current'))
            stack.enter_context(patch.object(completed,'_base',return_value=f.base))
            stack.enter_context(patch.object(native,'_sdk_parent_frozen_spec',return_value=f.base))
            self.native_fetch=stack.enter_context(patch.object(native,'_fetch_completed_sdk',return_value=f.previous))
            self.capture=stack.enter_context(patch.object(completed,'fetch_collector_controls',return_value=self.collected))
            stack.enter_context(patch.object(products,'_capture_runtime_reference_members',side_effect=AssertionError('no carrier replay')))
            actual=completed.observe_original
            def observe(original,receipt,token,**kw):
                if completed._identity(receipt).component=='csharp':
                    self.assertEqual(self.old_locator,kw['native_locator'])
                    return {},[],self.old_locator
                if receipt['producer']==self.producer:self.assertIn('_fresh_observation',kw)
                else:self.assertNotIn('_fresh_observation',kw)
                return actual(original,receipt,token,**kw)
            stack.enter_context(patch.object(completed,'observe_original',side_effect=observe))
            stack.enter_context(patch('runtime_reference_archive.open_reference_archive',side_effect=self.member))
            stack.enter_context(patch.object(completed,'_contract_files'))
            def source(item,token,**kw):
                self.assertTrue(kw['contract'])
                return {'name':'contract'},[{'run':{}}],{'contract':'native fixture'}
            stack.enter_context(patch.object(completed,'observe_source',side_effect=source))
            def download(*args,destination,**kw):
                with zipfile.ZipFile(destination,'w') as out:
                    for row in f.policy['contractFiles']:out.writestr(row['relativePath'],b'{}')
            stack.enter_context(patch.object(products,'_download_contract_ci_upload',side_effect=download))
            report=completed.issue_checkpoint(self.policy,f.source,self.control_selector,work,
                root=self.root,revision=self.policy['issuerCommit'],frozen=f.base,token='synthetic')
        return report,work

    def test_one_new_object_is_verified_and_old_parent_is_not_refetched(self):
        before=canonical_json_bytes(self.fixture.previous)
        report,work=self.issue()
        self.assertEqual([445],self.member_reads)
        self.assertEqual(len(self.body),report['verifiedObjectBytes'])
        self.assertEqual(37,report['reusedObjectBytes'])
        self.assertEqual(1,self.native_fetch.call_count)
        self.assertEqual(self.policy['bootstrap'],self.native_fetch.call_args.args[1])
        self.capture.assert_called_once()
        self.assertFalse(report['nativeAttestationIssued'])
        value=json.loads((work/'completion.json').read_bytes())
        self.assertEqual(2,len(value['completion']['members']))
        self.assertEqual(self.policy['parentProofSha256'],sha256_bytes(canonical_json_bytes(value['completion']['parentProof'])))
        self.assertEqual(before,canonical_json_bytes(self.fixture.previous))
        self.assertEqual(1,sum('/git/commits/' in url for url in self.urls))
        self.assertEqual(1,sum(url.endswith('/jobs') for url in self.urls))
        self.assertEqual(1,sum(url.endswith('/artifacts') for url in self.urls))
        self.assertEqual(1,sum('/actions/artifacts/445' in url for url in self.urls))
        self.assertEqual(['csharp'],[row['receipt']['component'] for row in self.prime.call_args.args[0]])
        self.assertFalse(any('per_page=' in url for url in self.urls))
        with self.assertRaisesRegex(ValueError,'private authenticated'):
            completed.issue_extension(value['recipe'],self.root/'bad',root=self.root,revision=self.policy['issuerCommit'],
                frozen={},token='synthetic',_checkpoint={})

    def test_tampered_new_body_never_publishes_checkpoint(self):
        self.tamper=True
        with self.assertRaises(ValueError):self.issue()
        self.assertEqual([445],self.member_reads)
        self.assertFalse((self.root/'1/completion.json').exists())

    def test_unchanged_tuples_return_exact_existing_proof_without_issuing(self):
        f=self.fixture
        f.request['availableObjects']=[row for row in f.request['availableObjects'] if row.get('component')!='python']
        f.result['phases']=[row for row in f.result['phases'] if row.get('component')!='python']
        f.bind();self.collected['references']=f.references
        report,work=self.issue()
        self.assertEqual(self.policy['bootstrap'],report['reusedCheckpoint'])
        self.assertEqual([],self.member_reads)
        self.assertEqual(0,report['verifiedObjectBytes'])
        self.assertFalse((work/'completion.json').exists())
        self.native_fetch.assert_called_once()

    def test_changed_bootstrap_or_inherited_tuple_fails_before_new_body(self):
        for case in ('bootstrap','old-object'):
            with self.subTest(case=case):
                self.setUp()
                if case=='bootstrap': self.policy['bootstrapProofSha256']=sha256_bytes(b'wrong bootstrap')
                else:
                    old=next(row for row in self.fixture.request['availableObjects'] if row.get('component')=='csharp')
                    old['objectSha256']=sha256_bytes(b'wrong retained object')
                with self.assertRaises(ValueError):self.issue()
                self.assertEqual([],self.member_reads)
                self.assertFalse((self.root/'1/completion.json').exists())

    def test_private_issuer_inputs_reject_mutation_before_reusing_authority(self):
        actual=completed.issue_extension
        def mutate(*args,**kwargs):
            kwargs['_checkpoint'].source['source']='changed after capture'
            return actual(*args,**kwargs)
        with patch.object(completed,'issue_extension',side_effect=mutate):
            with self.assertRaisesRegex(ValueError,'changed during use'):self.issue()
        self.assertEqual([],self.member_reads)
        self.assertFalse((self.root/'1/completion.json').exists())


if __name__=='__main__':unittest.main()
