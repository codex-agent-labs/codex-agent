"""Native/needs/inner semantics, with explicit external crypto and Git fixtures."""
from contextlib import ExitStack, contextmanager
from copy import deepcopy
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import completed_sdk_reuse as completed
import product_reuse as products
import reuse
import reuse_qualification as native
from products.inventory import canonical_json_bytes, sha256_bytes
from products.registry import PhaseInstanceId
from products.restore import object_relative_path
from ci.tests.test_sdk_checkpoint_intake import SdkCheckpointIntakeTest
from ci.tests.test_sdk_checkpoint_issuer import SdkCheckpointIssuerTest


class SdkCheckpointConsumerTest(unittest.TestCase):
    def setUp(self):
        self.f=SdkCheckpointIntakeTest();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.issued=SdkCheckpointIssuerTest();self.issued.setUp();self.addCleanup(self.issued.doCleanups)
        old_phase=self.issued.fixture.previous['extension']['spec']['completedPhases'][0]
        self.issued.old_locator['instance']={key:old_phase[key] for key in completed.IDENTITY}
        self.issued.policy['bootstrapProofSha256']=sha256_bytes(canonical_json_bytes(self.issued.fixture.previous['extension']['proof']))
        for row in self.issued.fixture.request['availableObjects']:
            row.setdefault('objectPath',object_relative_path(row['buildKey'],row['receiptSha256']))
        self.issued.fixture.bind();self.issued.collected['references']=self.issued.fixture.references
        _,work=self.issued.issue()
        f,issued=self.f,self.issued
        f.envelope=json.loads((work/'completion.json').read_bytes())
        f.spec=f.envelope['recipe'];f.source=f.spec['source'];f.producer=f.source['producer'];f.policy=deepcopy(issued.policy)
        # The native schema1 parent is an explicit fixture seam, with its shape
        # marker included in the signed synthetic wrapper rather than bypassed.
        parent=f.envelope['completion']['parentProof'];parent['schemaVersion']=1
        f.policy['parentProofSha256']=sha256_bytes(canonical_json_bytes(parent))
        f.spec['parentProofSha256']=f.policy['parentProofSha256']
        f.envelope['ownerPolicySha256']=sha256_bytes(canonical_json_bytes(f.policy))
        f.envelope['completion']['specSha256']=sha256_bytes(canonical_json_bytes(f.spec))
        f.selector.update(runId=f.producer['runId'],runAttempt=f.producer['runAttempt'],
            sourceCommit=f.producer['commit'],signerCommit=f.policy['issuerCommit'])
        f.identity=completed.checkpoint_archive_identity(f.policy,f.source,**{k:v for k,v in native._native_pin_arguments(f.selector).items()
            if k in ('signer_commit','source_commit','run_id','run_attempt')})
        f.run=deepcopy(issued.run);f.commit=deepcopy(issued.commit)
        f.run['referenced_workflows'].append({'path':native.REPOSITORY+'/'+native.ISSUER_WORKFLOW+'@'+f.policy['issuerCommit'],
                                             'sha':f.policy['issuerCommit']})
        f.collector.update(id=f.source['jobId'],name=f.source['jobName'],run_id=f.producer['runId'])
        f.issuer.update(name=f.identity['jobName'],run_id=f.producer['runId'])
        self.current={'id':993,'name':'product-validation / sdk-sdk-ios-metadata-ios',
            'run_id':f.producer['runId'],'head_sha':f.run['head_sha'],'status':'in_progress','conclusion':None,
            'started_at':'2026-10-24T10:41:00Z','completed_at':None}
        f.jobs=[f.collector,f.issuer,self.current,deepcopy(issued.job)]
        f.artifacts={f.source['artifactId']:f.artifact(f.source['artifactId'],
            f'codex-agent-sdk-wave-9-state-{f.producer["tree"]}-attempt-{f.producer["runAttempt"]}',
            f.source['artifactSha256'],f.source['artifactBytes'],'10:10:00'),
            992:f.artifact(992,completed.collector_control_artifact_name(f.source),sha256_bytes(b'control fixture'),1000,'10:20:00'),
            445:deepcopy(issued.artifact)}
        f.envelope['sourceCheckpoint']['controlArtifact']={'artifactId':992,'artifactSha256':f.artifacts[992]['digest']}
        f.envelope['completion']['source']=products._runtime_original_locator(f.artifacts[f.source['artifactId']],
            f.source['workflowSha'],PhaseInstanceId('sdk','javascript','metadata','node'),f.collector)
        f.upload()
        self.output={'kind':'sdk-checkpoint','source':f.source,'native':f.selector,'subjectSha256':sha256_bytes(f.subject)}
        self.consumer={'kind':'ci','producer':f.producer}
        source=Path(products.__file__).resolve().parents[1]/'.github/workflows/product-validation.yml'
        self.workflow=source.read_bytes()
        if b'\n  sdk-checkpoint-9:\n' not in self.workflow:
            self.workflow=self.workflow.replace(b'    needs: [plan, sdk-plan, sdk-ios-validation-result, sdk-ios-metadata-plan]',
                b'    needs: [plan, sdk-plan, sdk-ios-validation-result, sdk-ios-metadata-plan, sdk-checkpoint-9]',1)
            self.workflow=self.workflow.replace(b'  sdk-ios-metadata:\n',
                b'  sdk-checkpoint-9:\n    needs: [plan, sdk-collect-9]\n    uses: codex-agent-labs/codex-agent/.github/workflows/reuse-qualification.yml@reuse-authority\n\n  sdk-ios-metadata:\n',1)
    @contextmanager
    def boundaries(self):
        f=self.f
        with ExitStack() as stack:
            stack.enter_context(patch.object(reuse,'api_request',side_effect=f.api))
            stack.enter_context(patch.object(products,'download_artifact',side_effect=f.download))
            stack.enter_context(patch.object(native,'_authenticate_native_subject',side_effect=f.verify))
            stack.enter_context(patch.object(native,'_ensure_native_issuer_commit'))
            graph=stack.enter_context(patch('products.inventory.git_regular_blob_bytes',return_value=self.workflow))
            yield graph

    @contextmanager
    def open(self,*,output=None,consumer=None,job='sdk-ios-metadata'):
        f=self.f;f.number+=1
        with self.boundaries() as graph, completed.checkpoint_consumer(
                f.policy,output or self.output,f.root/str(f.number),root=f.root,
                consumer=consumer or self.consumer,job=job,token='synthetic') as witness:
            if witness is not None:
                self.assertEqual(f.policy['collectorWorkflowSha'],graph.call_args.args[1])
                self.assertEqual('.github/workflows/product-validation.yml',graph.call_args.args[2])
            yield witness

    def validate(self,witness,*,proof=None):
        f,issued=self.f,self.issued
        with ExitStack() as stack:
            stack.enter_context(patch.object(native,'_validate_completed_sdk',return_value=deepcopy(issued.fixture.parent_sdk)))
            stack.enter_context(patch.object(completed,'_base',return_value=issued.fixture.base))
            stack.enter_context(patch.object(completed,'_contract_files'))
            self.current_inputs=stack.enter_context(patch.object(completed,'validate_current'))
            stack.enter_context(patch.object(completed,'_inventory_revision',return_value=f.producer['commit']))
            actual=completed.observe_original
            def observe(original,receipt,token,**kw):
                if receipt['component']=='csharp':
                    self.assertEqual(issued.old_locator,kw['native_locator'])
                    return {},[],issued.old_locator
                self.assertIn('_fresh_observation',kw)
                return actual(original,receipt,token,**kw)
            self.originals=stack.enter_context(patch.object(completed,'observe_original',side_effect=observe))
            def contract(source,token,**kw):
                self.assertTrue(kw['contract'])
                return {},[],f.envelope['completion']['contractSource']
            stack.enter_context(patch.object(completed,'observe_source',side_effect=contract))
            return completed.validate_extension(f.spec,proof or f.envelope['completion'],native._native_pin_arguments(f.selector),
                root=f.root,revision=f.producer['commit'],consumer_revision=f.producer['commit'],
                frozen=issued.fixture.base,token='synthetic',_checkpoint=witness)

    def test_native_wrapper_full_inner_semantics_and_original_metadata_reused_in_scope(self):
        with self.open() as witness:
            sdk=self.validate(witness)
            self.assertEqual(self.f.envelope['completion'],sdk['extension']['proof'])
            self.current_inputs.assert_called_once()
            originals=self.originals.call_count
            for receipt,locator in zip(completed.validate_controls(self.f.spec,sdk['extension']['proof']['controls'],self.issued.fixture.base)[2],sdk['extension']['proof']['originals']):
                original=next(row for row in self.f.spec['originals'] if completed._identity(row)==completed._identity(receipt))
                witness.original(original,receipt,locator,'synthetic')
            self.assertEqual(originals,self.originals.call_count)
            self.assertEqual([990],self.f.downloads)
            self.assertEqual(1,sum('/actions/artifacts/445' in url for url in self.f.urls))
            self.assertEqual(1,sum('/git/commits/' in url for url in self.f.urls))
            self.assertEqual(1,sum('/jobs?' in url for url in self.f.urls))
            self.assertEqual(1,len(self.f.verified))
            with self.assertRaisesRegex(ValueError,'another consumer'):witness.check(consumer={**self.consumer,'producer':{**self.f.producer,'runAttempt':99}})
            with self.assertRaisesRegex(ValueError,'another observation token'):witness.check(token='different')
        with self.assertRaisesRegex(ValueError,'closed'):witness.check()

    def test_wrong_edge_job_retry_subject_or_native_signature_never_grants_witness(self):
        original=deepcopy((self.workflow,self.current,self.output))
        for fault in ('missing-edge','consumer-role','later-start','duplicate-consumer','failed-consumer','retry','subject','signature'):
            with self.subTest(fault=fault):
                self.workflow,self.current,self.output=deepcopy(original)
                self.f.jobs=[self.f.collector,self.f.issuer,self.current,deepcopy(self.issued.job)]
                consumer=deepcopy(self.consumer);job='sdk-ios-metadata'
                if fault=='missing-edge':self.workflow=self.workflow.replace(b', sdk-checkpoint-9]',b']')
                elif fault=='consumer-role':job='sdk-collect-10'
                elif fault=='later-start':self.current['started_at']='2026-10-24T10:39:00Z'
                elif fault=='duplicate-consumer':self.f.jobs.append(deepcopy(self.current))
                elif fault=='failed-consumer':self.current.update(status='completed',conclusion='failure')
                elif fault=='retry':consumer['producer']['runAttempt']+=1
                elif fault=='subject':self.output['subjectSha256']=sha256_bytes(b'wrong subject')
                else:self.f.verify=lambda *a,**k: (_ for _ in ()).throw(ValueError('native signature fails'))
                with self.assertRaises(ValueError):
                    with self.open(consumer=consumer,job=job):self.fail('must not yield an invalid witness')

    def test_inner_subject_mutation_or_unsealed_witness_rejects(self):
        with self.open() as witness:
            for field in ('controls','members','originals'):
                proof=deepcopy(self.f.envelope['completion']);proof[field]=[]
                with self.subTest(field=field),self.assertRaisesRegex(ValueError,'exact authenticated subject'):
                    self.validate(witness,proof=proof)
            with self.assertRaisesRegex(ValueError,'private authenticated'):self.validate({})
            with self.assertRaisesRegex(ValueError,'private native'):
                completed._CheckpointConsumer(self.consumer,{},witness.observation,'synthetic',(),object())

    def test_requalification_baseline_never_replaces_checkpoint_consumer_identity(self):
        with self.open() as witness, ExitStack() as stack:
            # Existing validate fixture supplies the native parent/source seams;
            # execute the real witness wrapper and match with a separate baseline.
            original = completed.validate_extension
            baseline = 'd' * 40
            def validate(spec, proof, arguments, **kwargs):
                kwargs.update(revision=baseline, requalification_baseline=baseline)
                return original(spec, proof, arguments, **kwargs)
            stack.enter_context(patch.object(completed, 'validate_extension', side_effect=validate))
            self.validate(witness)
            self.assertEqual(baseline, self.current_inputs.call_args.kwargs['revision'])
            envelope = self.f.envelope
            with self.assertRaisesRegex(ValueError, 'exact authenticated subject/consumer'):
                original(envelope['recipe'], envelope['completion'],
                    {'signer_commit': envelope['issuerCommit']}, root=self.f.root,
                    revision=baseline, consumer_revision='f' * 40, token='synthetic',
                    frozen=self.issued.fixture.base, _checkpoint=witness, requalification_baseline=baseline)

    def test_noop_names_only_declared_bootstrap_and_never_fetches_checkpoint(self):
        output={'kind':'existing-sdk-completion','native':self.f.policy['bootstrap'],
            'subjectSha256':self.f.policy['bootstrapProofSha256']}
        with self.open(output=output) as witness:self.assertIsNone(witness)
        self.assertEqual([],self.f.urls)
        output['subjectSha256']=sha256_bytes(b'wrong')
        with self.assertRaises(ValueError):
            with self.open(output=output):self.fail('invalid no-op')

    def capability(self,witness):
        sdk=self.validate(witness)
        request,phases,receipts=completed.validate_controls(self.f.spec,sdk['extension']['proof']['controls'],self.issued.fixture.base)
        spec=deepcopy(self.issued.fixture.base)
        spec['request'].setdefault('availableObjects',deepcopy(spec['expectedResult']['phases']))
        identities={completed._identity(row) for row in phases}
        for field in ('availableObjects','phaseAuthorities'):
            spec['request'][field]=sorted([*spec['request'][field],
                *(row for row in request[field] if completed._identity(row) in identities)],key=completed._identity)
        spec['expectedResult']['phases']=sorted([*spec['expectedResult']['phases'],*phases],key=completed._identity)
        spec['request']['repositoryRevision']=self.f.producer['commit']
        return native.CompletedFrozenReuse(spec,receipts,native._COMPLETED_FROZEN,
            revision=self.f.producer['commit'],sdk=sdk,_checkpoint=witness)

    def test_existing_capability_and_cli_bind_active_witness_and_close_after_sync_or_deferred_use(self):
        f=self.f
        plan=f.root/'cli-plan.json';plan.write_text(f.spec['sourcePlan'])
        owner=f.root/'cli-owner.json';owner.write_bytes(canonical_json_bytes(f.policy))
        policy=f.root/'cli-policy.json'
        policy.write_bytes(canonical_json_bytes({'schemaVersion':1,'kind':'completed-frozen-reuse',
            'consumerCommit':'c'*40,'verifierPolicySha256':'sha256:'+'a'*64,
            **f.policy['bootstrap'],'sdkCompletion':f.policy['bootstrap']}))
        env={'GITHUB_REPOSITORY':native.REPOSITORY,'GITHUB_EVENT_NAME':'pull_request','GITHUB_REF':'refs/pull/31/merge',
            'GITHUB_SHA':f.producer['commit'],'GITHUB_RUN_ID':str(f.producer['runId']),
            'GITHUB_RUN_ATTEMPT':str(f.producer['runAttempt']),'GITHUB_JOB':'sdk-ios-metadata','GITHUB_TOKEN':'synthetic'}
        def fetch(destination,**kw):
            self.assertEqual(f.policy['bootstrap'],kw['sdk_completion'])
            self.assertEqual(f.producer['commit'],kw['revision'])
            return self.capability(kw['_checkpoint']),{}
        for deferred in (False,True):
            with self.subTest(deferred=deferred),self.boundaries(),patch.dict(os.environ,env,clear=True), \
                 patch.object(products,'_validate_plan',return_value=json.loads(f.spec['sourcePlan'])), \
                 patch.object(native,'fetch_completed_frozen',side_effect=fetch) as authenticated:
                values={'plan':plan,'repository_root':f.root,'completed_frozen_policy':policy,
                        'sdk_checkpoint_owner':owner,'sdk_checkpoint':json.dumps(self.output)}
                with native.completed_frozen_options(values,defer=deferred) as options:
                    cap=options['completed_frozen_future'].result(timeout=5) if deferred else options['completed_frozen']
                    self.assertIs(type(cap),native.CompletedFrozenReuse)
                    self.assertNotIn('sdk_checkpoint',values)
                    record=next(row for row in f.spec['completedPhases'] if row['component']=='python')
                    cap.check_consumer(self.consumer)
                    self.assertIsNotNone(cap.envelope(record))
                    _,artifact,_=cap.observe_extended_sdk(record,producer=f.producer,token='synthetic')
                    self.assertEqual(445,artifact['id'])
                    self.assertEqual(1,authenticated.call_count)
                with self.assertRaisesRegex(ValueError,'closed'):cap.envelope(record)
        # Each command freshly authenticates the wrapper; metadata is not a disk verdict.
        self.assertEqual([990,990],f.downloads)
        self.assertEqual(2,sum('/actions/artifacts/445' in url for url in f.urls))
        with self.assertRaisesRegex(ValueError,'paired'):
            with native.completed_frozen_options({'sdk_checkpoint':json.dumps(self.output)}):pass
        for changed in ('owner','plan'):
            with self.subTest(changed=changed),self.boundaries(),patch.dict(os.environ,env,clear=True), \
                 patch.object(products,'_validate_plan',return_value=json.loads(f.spec['sourcePlan'])), \
                 patch.object(native,'fetch_completed_frozen',side_effect=fetch):
                changed_path=owner if changed=='owner' else plan
                saved=changed_path.read_bytes()
                try:
                    with self.assertRaisesRegex(ValueError,'changed during'):
                        with native.completed_frozen_options({'plan':plan,'repository_root':f.root,
                                'completed_frozen_policy':policy,'sdk_checkpoint_owner':owner,
                                'sdk_checkpoint':json.dumps(self.output)},defer=True) as options:
                            cap=options['completed_frozen_future'].result(timeout=5)
                            changed_path.write_bytes(b'changed during this command')
                    with self.assertRaisesRegex(ValueError,'closed'):cap.completed_phases()
                finally:changed_path.write_bytes(saved)
        for bad in ('environment','selector'):
            with self.subTest(bad=bad),patch.dict(os.environ,{**env,'GITHUB_SHA':'a'*40},clear=True), \
                 patch.object(products,'_validate_plan',return_value=json.loads(f.spec['sourcePlan'])), \
                 patch.object(native,'fetch_completed_frozen',side_effect=AssertionError('invalid checkpoint fell back')):
                with self.assertRaises(ValueError):
                    with native.completed_frozen_options({'plan':plan,'repository_root':f.root,
                            'completed_frozen_policy':policy,'sdk_checkpoint_owner':owner,
                            'sdk_checkpoint':'{}' if bad=='selector' else json.dumps(self.output)}):pass

    def test_selected_graph_accepts_real_workflow_and_rejects_ambiguous_structure(self):
        check=lambda raw:completed._checkpoint_workflow_edges(raw,'sdk-collect-9','sdk-checkpoint-9','sdk-ios-metadata')
        self.assertEqual(sha256_bytes(self.workflow),check(self.workflow))
        cases=[self.workflow+b'\njobs:\n',self.workflow+b'\n"jobs": {}\n',b'---\n'+self.workflow,
            self.workflow.replace(b'jobs:\n',b'jobs: &hidden\n',1),
            self.workflow.replace(b'  sdk-checkpoint-9:\n',b'  "sdk-checkpoint-9":\n',1),
            self.workflow.replace(b'    needs: [plan, sdk-collect-9]',b'    needs: [plan, sdk-collect-9, sdk-collect-9]',1),
            self.workflow.replace(b'    needs: [plan, sdk-collect-9]',b'    needs: [sdk-checkpoint-9, sdk-collect-9]',1),
            self.workflow.replace(b'    needs: [plan, sdk-collect-9]',b'    needs: [plan, sdk-collect-9]\n    needs: [plan]',1),
            self.workflow.replace(b'    needs: [plan, sdk-collect-9]',b'    "needs": [plan, sdk-collect-9]',1),
            self.workflow.replace(b'    needs: [plan, sdk-collect-9]',b'    <<: *edges\n    needs: [plan, sdk-collect-9]',1),
            self.workflow.replace(b'    needs: [plan, sdk-collect-9]',b'    needs: *edges',1),
            self.workflow.replace(b'    needs: [plan, sdk-collect-9]',b'    needs: >-\n      [plan, sdk-collect-9]',1),
            self.workflow.replace(b'  sdk-checkpoint-9:\n',b'  sdk-checkpoint-9:\n    name: "unterminated\n',1),
            self.workflow.replace(b'  sdk-checkpoint-9:\n',b'\tsdk-checkpoint-9:\n',1),
            self.workflow.replace(b'    needs: [plan, sdk-collect-9]',b'    needs: [plan, sdk-collect-9]\n    # comment\n    needs: [plan]',1)]
        for raw in cases:
            with self.subTest(sha=sha256_bytes(raw)),self.assertRaises(ValueError):check(raw)
        # Fake fields inside unrelated literal/folded script content contribute nothing.
        for indicator in (b'|',b'>-',b'|2-'):
            raw=self.workflow.replace(b'  sdk-checkpoint-9:\n',b'  harmless:\n    steps:\n      - run: '+indicator+b'\n          jobs:\n            sdk-checkpoint-9:\n              needs: [wrong]\n\n  sdk-checkpoint-9:\n',1)
            self.assertEqual(sha256_bytes(raw),check(raw))

    def test_fetch_uses_checkpoint_sdk_branch_and_existing_merge_without_bootstrap_refetch(self):
        from products import inventory
        from products.receipt import compute_build_key
        f,base=self.f,deepcopy(self.issued.fixture.base)
        base['inventoryBaseline']=f.producer['commit']
        base['request']['availableObjects']=deepcopy(base['expectedResult']['phases'])
        receipt=deepcopy(self.issued.receipt)
        receipt.update(component='javascript',phase='metadata',target='node')
        receipt['buildKey']=compute_build_key(**{field:receipt[field] for field in (*completed.IDENTITY,'inputs')})
        phase={**{field:receipt[field] for field in (*completed.IDENTITY,'buildKey')},
            'receiptSha256':sha256_bytes(canonical_json_bytes(receipt)),
            'objectSha256':sha256_bytes(b'bootstrap SDK fixture')}
        request={'availableObjects':[phase],'phaseAuthorities':[{**{field:receipt[field] for field in completed.IDENTITY},
            **{field:receipt['inputs'][field] for field in ('flagsDigest','toolchainProfileDigest','outputSchemaVersion')}}]}
        # This test exercises branch selection and the real SDK-only merge. The
        # independent frozen/parent authenticity gates have explicit fixtures.
        self.issued.fixture.parent_sdk.update(original={})
        self.issued.fixture.parent_sdk['proof']['controls']={}
        with self.open() as witness,ExitStack() as stack:
            stack.enter_context(patch.object(native,'_compatible_verifier',return_value=True))
            stack.enter_context(patch.object(inventory,'git_regular_blob_bytes',return_value=canonical_json_bytes(base)))
            stack.enter_context(patch.object(inventory,'tree_entries',return_value=()))
            stack.enter_context(patch.object(products,'_authorities',return_value=(base['request']['phaseAuthorities'],None)))
            stack.enter_context(patch.object(products,'_versions',return_value=base['request']['versions']))
            stack.enter_context(patch.object(native,'_fetch_qualification_archive',return_value=({},
                {'qualification.json':b'fixture','bundle.jsonl':b'fixture','proof.json':canonical_json_bytes({})})))
            frozen=stack.enter_context(patch.object(native,'_authenticate_bytes',return_value={'originals':[]}))
            stack.enter_context(patch.object(native,'_completed_frozen_controls',return_value=completed._records(base['expectedResult']['phases'],'fixture')))
            stack.enter_context(patch.object(native,'_sdk_parent_frozen_spec',return_value=self.issued.fixture.base))
            stack.enter_context(patch.object(native,'_capture_completed_contract_receipts',return_value=[]))
            stack.enter_context(patch.object(native,'_completed_sdk_controls',return_value=(request,phase,receipt,None)))
            stack.enter_context(patch.object(completed,'_base',return_value=self.issued.fixture.base))
            semantic=stack.enter_context(patch.object(completed._CheckpointConsumer,'validate',side_effect=lambda **kw:self.validate(witness)))
            bootstrap=stack.enter_context(patch.object(native,'_fetch_completed_sdk',side_effect=AssertionError('bootstrap refetched')))
            arguments=dict(consumer_commit='c'*40,verifier_policy_sha256=sha256_bytes(b'policy'),
                repository_root=f.root,revision=f.producer['commit'],sdk_completion=f.policy['bootstrap'],
                signer_commit='b'*40,source_commit='a'*40,artifact_id=71,artifact_sha256=sha256_bytes(b'original'),
                run_id=72,run_attempt=1,token='synthetic',_checkpoint=witness)
            cap,report=native.fetch_completed_frozen(f.root/'frozen',**arguments)
            self.assertIs(type(cap),native.CompletedFrozenReuse)
            self.assertEqual(4,len(cap.completed_phases()))
            self.assertEqual(3,report['completedSdkPhases'])
            self.assertEqual(0,report['productBodiesDownloaded'])
            for row in f.spec['completedPhases']:
                self.assertIsNotNone(cap.envelope(row))
            frozen.assert_called_once();semantic.assert_called_once();bootstrap.assert_not_called()
            with self.assertRaisesRegex(ValueError,'exact private native/bootstrap'):
                native.fetch_completed_frozen(f.root/'mismatched',**{**arguments,'sdk_completion':{}})
            with self.assertRaisesRegex(ValueError,'exact private native/bootstrap'):
                native.fetch_completed_frozen(f.root/'unsealed',**{**arguments,'_checkpoint':{}})
        with self.assertRaisesRegex(ValueError,'closed'):cap.completed_phases()


if __name__=='__main__':unittest.main()
