"""Historical original provenance and one full new-object check, not hosted evidence."""
from copy import deepcopy
from contextlib import ExitStack
import json
import unittest
from unittest.mock import patch

import completed_sdk_reuse as completed
import product_reuse as products
from products.inventory import canonical_json_bytes, sha256_bytes
from products.receipt import compute_build_key
from products.restore import PHASE_PLAN_KEYS, finalize_phase_object
from sdk_campaign_original_locator import fresh_sdk_worker_route
from ci.tests.test_sdk_checkpoint_issuer import SdkCheckpointIssuerTest


class CheckpointOriginalRecoveryTest(unittest.TestCase):
    def fixture(self, *, retry=False):
        f=SdkCheckpointIssuerTest();f.setUp();self.addCleanup(f.doCleanups)
        if retry:
            # Preserve attempt-one replay context, with the actual collector now
            # in attempt two. The producer-separation repair already covers this.
            f.producer={**f.producer,'runAttempt':f.producer['runAttempt']+1}
            f.fixture.source={**f.fixture.source,'producer':f.producer}
            f.collected['source']=f.fixture.source
            f.run['run_attempt']=f.producer['runAttempt']
        original={**f.producer,'runAttempt':f.producer['runAttempt']-1} if retry else {
            **f.producer,'runId':f.producer['runId']-1,'commit':'2'*40,'tree':'3'*40}
        f.verified=finalize_phase_object(stage_root=f.root/'stage',
            phase_plan={name:f.receipt[name] for name in PHASE_PLAN_KEYS},producer=original,
            product_version='0.2.0',trust_domain='development',destination=f.root/'historical-shard')
        f.body=(f.root/'historical-shard'/f.verified['objectPath']).read_bytes()
        f.receipt=f.verified['receipt'];held=f.fixture
        held.controls['held-python/phase-receipt.json']=f.receipt
        row={**{key:f.receipt[key] for key in completed.IDENTITY},**{key:f.verified[key] for key in completed.OBJECT}}
        held.request['availableObjects'][-1].update(row);held.result['phases'][-1].update(row)
        held.object.update(relativePath='runtime-state/original-objects/'+f.verified['objectPath'],bytes=len(f.body),sha256=f.verified['objectSha256'])
        held.bind();f.collected['references']=held.references
        pin=f.policy['collectorWorkflowSha'] if retry else products._PRIOR_RUNTIME_WORKFLOW_SHA
        run=deepcopy(f.run);run.update(id=original['runId'],run_attempt=original['runAttempt'],status='completed',conclusion='failure')
        run['referenced_workflows']=[{'path':original['repository']+'/.github/workflows/product-validation.yml@'+pin,'sha':pin}]
        commit={**deepcopy(f.commit),'sha':original['commit'],'tree':{'sha':original['tree']}}
        job=deepcopy(f.job);job['run_id']=original['runId']
        f.artifact.update(name=fresh_sdk_worker_route(completed._identity(f.receipt),f.receipt)[1],size_in_bytes=len(f.body)+1000,
            workflow_run={'id':original['runId'],'head_sha':run['head_sha']})
        old_attempt=f"/actions/runs/{original['runId']}/attempts/{original['runAttempt']}"
        old_artifacts=f"/actions/runs/{original['runId']}/artifacts"
        actual_api=f.api;actual_listing=f.listing
        def api(url,token):
            if url.endswith(old_attempt):f.urls.append(url);return deepcopy(run)
            if url.endswith('/git/commits/'+original['commit']):f.urls.append(url);return deepcopy(commit)
            return actual_api(url,token)
        def listing(url,key,token):
            if url.endswith(old_attempt+'/jobs'):f.urls.append(url);return [deepcopy(job)]
            if url.endswith(old_artifacts):f.urls.append(url);return [deepcopy(f.artifact)]
            return actual_listing(url,key,token)
        f.api,f.listing=api,listing
        return f,original,pin,run,job,old_attempt

    def test_new_historical_object_keeps_original_identity_and_reuses_completed_observation(self):
        for retry in (False,True):
            with self.subTest(retry=retry):
                f,producer,pin,run,job,attempt=self.fixture(retry=retry)
                receipt=canonical_json_bytes(f.receipt);prior=canonical_json_bytes(f.fixture.previous)
                report,work=f.issue()
                envelope=json.loads((work/'completion.json').read_bytes())
                selected=next(row for row in envelope['recipe']['originals'] if row['component']=='python')
                self.assertEqual(pin,selected['workflowSha'])
                self.assertEqual(445,selected['artifactId']);self.assertEqual(job['id'],selected['jobId'])
                original=next(value for value in envelope['completion']['controls'].values()
                    if isinstance(value,dict) and value.get('component')=='python')
                self.assertEqual(receipt,canonical_json_bytes(original))
                self.assertEqual(producer,original['producer']);self.assertEqual(prior,canonical_json_bytes(f.fixture.previous))
                self.assertEqual([445],f.member_reads);self.assertEqual(len(f.body),report['verifiedObjectBytes'])
                self.assertEqual(37,report['reusedObjectBytes']);f.native_fetch.assert_called_once()
                self.assertEqual(1,sum(url.endswith(attempt) for url in f.urls))
                self.assertEqual(1,sum(url.endswith(attempt+'/jobs') for url in f.urls))
                self.assertEqual(1,sum(url.endswith('/actions/artifacts/445') for url in f.urls))
                self.assertEqual(1,sum(url.endswith('/artifacts') for url in f.urls))
                self.assertEqual('failure',run['conclusion'],'whole-run success must not be required')

    def test_unreviewed_or_failed_original_never_reaches_body_and_tampering_never_publishes(self):
        for fault in ('workflow','duplicate-reference','failed-job','expired','wrong-upload','future','tampered'):
            with self.subTest(fault=fault):
                f,producer,pin,run,job,attempt=self.fixture()
                if fault=='workflow':
                    run['referenced_workflows']=[{'path':producer['repository']+'/.github/workflows/product-validation.yml@'+'9'*40,'sha':'9'*40}]
                elif fault=='duplicate-reference':run['referenced_workflows']*=2
                elif fault=='failed-job':job['conclusion']='failure'
                elif fault=='expired':f.artifact['expired']=True
                elif fault=='wrong-upload':f.artifact['name']+='-another-attempt'
                elif fault=='future':
                    # This is an untrusted locator selection, rejected before it
                    # can reinterpret the originally authenticated receipt/body.
                    f.receipt['producer']['runId']=f.producer['runId']+1
                    row=f.fixture.request['availableObjects'][-1];row['receiptSha256']=sha256_bytes(canonical_json_bytes(f.receipt))
                    f.fixture.result['phases'][-1]['receiptSha256']=row['receiptSha256']
                else:f.tamper=True
                with self.assertRaises(ValueError):f.issue()
                self.assertEqual([445] if fault=='tampered' else [],f.member_reads)
                self.assertFalse((f.root/'1/completion.json').exists())

    def test_mixed_original_publishers_keep_their_own_routes_and_group_listing_by_run(self):
        for mixed in (False,True):
            with self.subTest(mixed=mixed):
                f,producer,pin,run,job,attempt=self.fixture()
                controls=deepcopy(f.fixture.controls)
                receipt=controls['runtime-state/original/csharp/phase-receipt.json']
                receipt['producer']=deepcopy(f.producer if mixed else producer)
                selected=next(row for row in controls['runtime-state/reuse-wave-request.json']['availableObjects'] if row['component']=='csharp')
                selected['receiptSha256']=sha256_bytes(canonical_json_bytes(receipt))
                csharp_job,name=fresh_sdk_worker_route(completed._identity(receipt),receipt)
                csharp_job={**deepcopy(job),'id':446,'name':csharp_job,'run_id':receipt['producer']['runId']}
                artifact={**deepcopy(f.artifact),'id':447,'name':name,'digest':sha256_bytes(b'untrusted csharp upload selector'),
                    'workflow_run':{'id':receipt['producer']['runId'],'head_sha':run['head_sha']}}
                previous=deepcopy(f.fixture.previous)
                previous['extension']['spec'].update(completedPhases=[],originals=[])
                current=f"/actions/runs/{f.producer['runId']}/attempts/{f.producer['runAttempt']}"
                def listing(url,key,token):
                    f.urls.append(url)
                    if key=='jobs' and url.endswith(attempt+'/jobs'):return [job]+([] if mixed else [csharp_job])
                    if key=='jobs' and url.endswith(current+'/jobs'):return [csharp_job] if mixed else []
                    if key=='artifacts' and url.endswith(f"/actions/runs/{producer['runId']}/artifacts"):
                        return [f.artifact]+([] if mixed else [artifact])
                    if key=='artifacts' and mixed and url.endswith(f"/actions/runs/{f.producer['runId']}/artifacts"):return [artifact]
                    raise AssertionError((url,key))
                raw=canonical_json_bytes(controls)
                with patch.object(products,'api_json',side_effect=f.api),patch.object(products,'paginated_items',side_effect=listing), \
                        products._fresh_ci_observation(f.producer,'synthetic') as observation, \
                        products._ci_observation_batch(tuple(str(f.producer[k]) for k in ('runId','runAttempt')),share_nested=True):
                    originals=completed._checkpoint_originals(controls,previous,f.fixture.base,f.fixture.source,observation,'synthetic')
                self.assertEqual(raw,canonical_json_bytes(controls))
                selected={row['component']:row for row in originals}
                self.assertEqual(pin,selected['python']['workflowSha'])
                self.assertEqual(f.policy['collectorWorkflowSha'] if mixed else pin,selected['csharp']['workflowSha'])
                self.assertEqual((445,447),(selected['python']['artifactId'],selected['csharp']['artifactId']))
                self.assertEqual(2 if mixed else 1,sum(url.endswith('/artifacts') for url in f.urls))
                self.assertEqual(1,sum(url.endswith(attempt+'/jobs') for url in f.urls))
                self.assertFalse(any('/actions/artifacts/' in url for url in f.urls),'selector discovery must not fetch full metadata twice')
                self.assertEqual([],f.member_reads)

    def test_current_publisher_substitution_cannot_replace_historical_workflow_checks(self):
        f,producer,pin,run,job,attempt=self.fixture()
        with patch.object(products,'_runtime_prior_workflow_sha',return_value=f.policy['collectorWorkflowSha']):
            with self.assertRaisesRegex(ValueError,'caller-pinned workflow'):f.issue()
        self.assertEqual([],f.member_reads)

    def test_exact_retained_locator_precedes_generic_parent_history_without_granting_content_admission(self):
        for fault in (None,'receipt','object','producer','route','job','digest','workflow'):
            with self.subTest(fault=fault):
                f,producer,pin,run,job,attempt=self.fixture()
                # An independently reviewed exact-origin helper may cover a
                # publisher absent from general parent history. Its result is
                # a fixture here; ordinary source/job/content checks are real.
                pin='7'*40
                run['referenced_workflows']=[{'path':producer['repository']+'/.github/workflows/product-validation.yml@'+pin,'sha':pin}]
                origin={'producer':deepcopy(producer),'artifact_id':445,'artifact_sha256':f.artifact['digest'],
                    'job_id':job['id'],'workflow_sha':pin,'workflow_path':'.github/workflows/product-validation.yml',
                    'job_name':job['name'],'receipt_sha256':f.verified['receiptSha256'],'object_sha256':f.verified['objectSha256']}
                if fault in ('receipt','object'):origin[fault+'_sha256']=sha256_bytes(b'conflict')
                elif fault=='producer':origin['producer']['runId']-=1
                elif fault=='route':origin['workflow_path']='.github/workflows/sdk-core-binary-validation.yml'
                elif fault=='job':origin['job_id']+=1
                elif fault=='digest':origin['artifact_sha256']=sha256_bytes(b'wrong original upload')
                elif fault=='workflow':origin['workflow_sha']=f.policy['collectorWorkflowSha']
                before=canonical_json_bytes(f.receipt)
                with patch('sdk_campaign_original_locator.retained_core_origin',return_value=origin):
                    if fault:
                        with self.assertRaises(ValueError):f.issue()
                        self.assertEqual([],f.member_reads)
                    else:
                        report,work=f.issue();envelope=json.loads((work/'completion.json').read_bytes())
                        original=next(row for row in envelope['recipe']['originals'] if row['component']=='python')
                        self.assertEqual(pin,original['workflowSha'])
                        self.assertEqual([445],f.member_reads);self.assertEqual(len(f.body),report['verifiedObjectBytes'])
                        self.assertEqual(0,sum(url.endswith('/artifacts') for url in f.urls))
                        self.assertEqual(1,sum(url.endswith('/actions/artifacts/445') for url in f.urls))
                self.assertEqual(before,canonical_json_bytes(f.receipt))

    def test_reviewed_parent_does_not_authorize_a_missing_or_different_registered_child(self):
        for child in ('correct','missing','wrong'):
            with self.subTest(child=child):
                f,producer,pin,run,job,attempt=self.fixture()
                receipt=deepcopy(f.receipt);receipt.update(component='sdk-core',phase='binary',target='common')
                receipt['buildKey']=compute_build_key(**{key:receipt[key] for key in (*completed.IDENTITY,'inputs')})
                controls=deepcopy(f.fixture.controls);controls['held-python/phase-receipt.json']=receipt
                phase=controls['runtime-state/reuse-wave-request.json']['availableObjects'][-1]
                phase.update({key:receipt[key] for key in (*completed.IDENTITY,'buildKey')})
                phase['receiptSha256']=sha256_bytes(canonical_json_bytes(receipt))
                job['name'],f.artifact['name']=fresh_sdk_worker_route(completed._identity(receipt),receipt)
                path='.github/workflows/sdk-core-binary-validation.yml'
                if child!='missing':run['referenced_workflows'].append({'path':producer['repository']+'/'+path+'@'+pin,
                    'sha':pin if child=='correct' else '9'*40})
                with patch.object(products,'api_json',side_effect=f.api),patch.object(products,'paginated_items',side_effect=f.listing), \
                        products._fresh_ci_observation(f.producer,'synthetic') as observation, \
                        products._ci_observation_batch(tuple(str(f.producer[k]) for k in ('runId','runAttempt')),share_nested=True):
                    def select():return completed._checkpoint_originals(controls,f.fixture.previous,f.fixture.base,f.fixture.source,observation,'synthetic')
                    if child!='correct':
                        with self.assertRaisesRegex(ValueError,'caller-pinned workflow'):select()
                    else:
                        original=next(row for row in select() if row['component']=='sdk-core')
                        artifact,_,locator=completed.observe_original(original,receipt,'synthetic')
                        self.assertEqual(445,artifact['id']);self.assertEqual(pin,original['workflowSha'])
                        self.assertEqual(job['id'],locator['job']['id'])
                self.assertEqual([],f.member_reads)


if __name__=='__main__':unittest.main()
