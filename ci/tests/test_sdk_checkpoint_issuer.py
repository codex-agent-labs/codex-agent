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
            originals=[f.originals[0]], source=deepcopy(f.source),
            contractControls=f.policy['contractControls'], contractFiles=f.policy['contractFiles'])
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

    def issue(self, **options):
        f=self.fixture;self.number+=1;work=self.root/str(self.number)
        with ExitStack() as stack:
            stack.enter_context(patch.object(products,'api_json',side_effect=self.api))
            stack.enter_context(patch.object(products,'paginated_items',side_effect=self.listing))
            self.prime=stack.enter_context(patch.object(products,'_prime_runtime_artifact_metadata',
                wraps=products._prime_runtime_artifact_metadata))
            stack.enter_context(patch('sdk_handoff._ensure_observed_sdk_commit'))
            stack.enter_context(patch.object(products,'_validate_plan',return_value={}))
            stack.enter_context(patch.object(completed,'_inventory_revision',
                side_effect=lambda spec,root,**kw:spec['source']['inventoryCommit']))
            stack.enter_context(patch.object(native,'_sdk_completed_spec_path',return_value='fixed-native-recipe.json'))
            stack.enter_context(patch('products.inventory.git_regular_blob_bytes',
                return_value=canonical_json_bytes(f.previous['extension']['spec'])))
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
                root=self.root,revision=self.policy['issuerCommit'],frozen=f.base,token='synthetic',**options)
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

    def test_rotated_source_authenticates_bootstrap_at_its_original_inventory_only(self):
        original_revision = '1' * 40
        self.fixture.previous['extension']['spec']['source']['inventoryCommit'] = original_revision
        before = canonical_json_bytes(self.fixture.previous)
        report, _ = self.issue()
        self.assertEqual(original_revision, self.native_fetch.call_args.kwargs['revision'])
        self.assertEqual(original_revision, self.native_fetch.call_args.kwargs['requalification_baseline'])
        self.assertEqual(self.producer['commit'], self.native_fetch.call_args.kwargs['consumer_revision'])
        self.assertEqual([445], self.member_reads)
        self.assertEqual(len(self.body), report['verifiedObjectBytes'])
        self.assertEqual(before, canonical_json_bytes(self.fixture.previous))

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

class SuccessfulSubsetIssuerTest(unittest.TestCase):
    def setUp(self):
        self.f = SdkCheckpointIssuerTest(); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        f = self.f.fixture
        f.source['jobName'] = 'product-validation / sdk-collect-4'
        self.f.policy['collectors'] = [f.source['jobName']]
        failed = {'product':'sdk','component':'rust','phase':'package','target':'desktop',
                  'buildKey':sha256_bytes(b'failed Rust package')}
        f.result['phases'].append({**failed,'state':'build'})
        f.controls['runtime-state/wave-failures.json'] = {
            'schemaVersion':1,'producer':deepcopy(f.producer),'failedPhases':[failed]}
        f.bind(); self.f.collected['references'] = f.references

    def test_partial_wave_keeps_failed_partition_and_only_opens_successful_new_object(self):
        before = canonical_json_bytes(self.f.fixture.controls['runtime-state/wave-failures.json'])
        report, work = self.f.issue()
        self.assertEqual([445], self.f.member_reads)
        self.assertEqual(len(self.f.body), report['verifiedObjectBytes'])
        value = json.loads((work/'completion.json').read_bytes())
        controls = value['completion']['controls']
        self.assertEqual(before, canonical_json_bytes(controls['runtime-state/wave-failures.json']))
        self.assertEqual({'csharp','python'}, {row['component'] for row in value['recipe']['completedPhases']})
        self.assertEqual(1, report['failedPhasesPreserved'])
        self.assertTrue(report['originalWaveFailed'])
        self.assertTrue(report['successfulSubset'])
        self.assertFalse(report['nativeAttestationIssued'])

    def test_failed_original_successful_sibling_does_not_gain_qualification(self):
        self.f.job['conclusion'] = 'failure'
        with self.assertRaises(ValueError): self.f.issue()
        self.assertEqual([], self.f.member_reads)
        self.assertFalse((self.f.root/'1'/'completion.json').exists())

class CumulativeHistoricalIssuerTest(unittest.TestCase):
    def test_later_source_reuses_two_qualified_siblings_and_reads_only_new_rust_object(self):
        from ci.tests.test_sdk_checkpoint_consumer import HistoricalCheckpointIssuerTest
        from products.receipt import compute_build_key
        htest=HistoricalCheckpointIssuerTest();htest.setUp();self.addCleanup(htest.doCleanups)
        h=htest.h;f=h.fixture.issued;current=f.fixture
        with htest.open() as witness:
            current.parent_sdk['proof']=deepcopy(h.f.envelope['completion']['parentProof'])
            prior=h.validate(witness)
            old_raw=canonical_json_bytes(prior)
            current.previous=prior;current.parent_sdk={key:value for key,value in prior.items() if key!='extension'}
            f.producer=deepcopy(h.producer);current.producer=f.producer
            current.source=deepcopy(htest.source);current.request['repositoryRevision']=f.producer['commit']
            current.controls['runtime-state/producer.json']=f.producer
            plan=json.loads(current.controls[completed.SOURCE_PLAN]);plan.update(validationCommit=f.producer['commit'],validationTree=f.producer['tree'])
            current.controls[completed.SOURCE_PLAN]=json.dumps(plan,indent=2)+'\n'
            phase_plan={key:deepcopy(f.receipt[key]) for key in PHASE_PLAN_KEYS}
            phase_plan['component']='rust';phase_plan['buildKey']=compute_build_key(**{key:phase_plan[key] for key in (*completed.IDENTITY,'inputs')})
            stage=f.root/'rust-stage';(stage/'outputs').mkdir(parents=True);(stage/'outputs/value').write_bytes(b'new successful Rust sibling')
            write_output_manifest(stage,'sdk','rust','package','desktop','0.2.0',{'evidence':'outputs'})
            f.verified=finalize_phase_object(stage_root=stage,phase_plan=phase_plan,producer=f.producer,
                product_version='0.2.0',trust_domain='development',destination=f.root/'rust-shard')
            f.body=(f.root/'rust-shard'/f.verified['objectPath']).read_bytes();f.receipt=f.verified['receipt']
            row={**{key:f.receipt[key] for key in completed.IDENTITY},**{key:f.verified[key] for key in completed.OBJECT}}
            current.request['availableObjects'].append(row);current.result['phases'].append({**row,'state':'retained'})
            current.request['phaseAuthorities'].append({**{key:row[key] for key in completed.IDENTITY},
                **{key:f.receipt['inputs'][key] for key in ('toolchainProfileDigest','flagsDigest','outputSchemaVersion')}})
            current.controls['runtime-state/new-rust/phase-receipt.json']=f.receipt
            current.object={'relativePath':'runtime-state/original-objects/'+f.verified['objectPath'],
                'bytes':len(f.body),'sha256':f.verified['objectSha256']}
            current.bind();f.policy=deepcopy(h.owner)
            current.policy['parentProofSha256']=f.policy['parentProofSha256']
            f.collected={'source':current.source,'controls':current.controls,'references':current.references,
                'stateLocator':{'source':current.source['artifactId']},'controlArchive':{'bytes':4096}}
            f.run=deepcopy(h.current_run);f.commit=deepcopy(h.current_commit)
            job,name=fresh_sdk_worker_route(completed._identity(f.receipt),f.receipt)
            f.job.update(name=job,run_id=f.producer['runId'],head_sha=f.run['head_sha'])
            f.artifact.update(name=name,digest=sha256_bytes(b'new Rust worker upload'),size_in_bytes=len(f.body)+1000,
                              workflow_run={'id':f.producer['runId'],'head_sha':f.run['head_sha']})
            f.member_reads.clear()
            htest.source=deepcopy(current.source)
            with htest.open() as successor:
                prior=h.validate(successor)
                @contextmanager
                def borrow(*args,**kw):
                    self.assertEqual(h.selection,args[1]);successor.check();yield successor;successor.check()
                old_spec,old_proof=prior['extension']['spec'],prior['extension']['proof']
                old_rows={completed._identity(row):(row,locator) for row,locator in
                          zip(old_spec['completedPhases'],old_proof['originals'],strict=True)}
                def retained_original(record,receipt,locator,token):
                    row,expected=old_rows[completed._identity(receipt)]
                    self.assertEqual(expected,locator)
                    self.assertEqual(old_proof['controls'][row['receiptPath']],receipt)
                    self.assertEqual(next(item for item in old_spec['originals'] if completed._identity(item)==completed._identity(row)),record)
                    return {},[],locator
                with patch.object(completed,'_historical_checkpoint_issuer',side_effect=borrow), \
                        patch.object(completed._HistoricalCheckpointIssuer,'validate',return_value=prior), \
                        patch.object(completed._HistoricalCheckpointIssuer,'original',side_effect=retained_original):
                    report,work=f.issue(previous=h.selection,history=h.history,current_policy=h.policy)
            value=json.loads((work/'completion.json').read_bytes())
            self.assertEqual([445],f.member_reads)
            self.assertEqual(len(f.body),report['verifiedObjectBytes'])
            self.assertEqual({'csharp','python','rust'},{row['component'] for row in value['recipe']['completedPhases']})
            self.assertEqual(h.selection['ownerPolicySha256'],value['precedingCheckpoint']['ownerPolicySha256'])
            self.assertEqual(2,report['checkpointPreparation']['inheritedSdkObjects'])
            self.assertEqual(1,report['checkpointPreparation']['newSdkObjectsRequiringQualification'])
            self.assertEqual(old_raw,canonical_json_bytes(prior))
