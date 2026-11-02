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



class HistoricalCheckpointConsumerTest(unittest.TestCase):
    def setUp(self):
        self.fixture = SdkCheckpointConsumerTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.f = self.fixture.f
        self.owner = deepcopy(self.f.policy)
        self.owner.update(issuerCommit="b"*40, collectorWorkflowSha="b"*40)
        self.history = {"schemaVersion":1, "kind":"sdk-checkpoint-history",
            "consumerCommit":"9"*40, "currentOwner":self.owner,
            "historicalPolicies":[{"sha256":sha256_bytes(canonical_json_bytes(self.f.policy)),
                                   "policy":deepcopy(self.f.policy)}]}
        self.policy = {"schemaVersion":1, "kind":"completed-frozen-reuse",
            "consumerCommit":"9"*40, "verifierPolicySha256":"sha256:"+"a"*64,
            **self.owner["bootstrap"], "sdkCompletion":deepcopy(self.owner["bootstrap"])}
        self.selection = {"ownerPolicySha256":self.history["historicalPolicies"][0]["sha256"],
                          "checkpoint":deepcopy(self.fixture.output)}
        self.producer = {**self.f.producer, "runId":self.f.producer["runId"]+1,
                         "commit":"e"*40, "tree":"d"*40}
        self.consumer = {"kind":"ci", "producer":self.producer}
        self.bind_current()

    def bind_current(self):
        self.current_run = deepcopy(self.f.run)
        self.current_run.update(id=self.producer["runId"], run_attempt=self.producer["runAttempt"],
                                status="in_progress", conclusion=None)
        self.current_run["referenced_workflows"] = [{"path":native.REPOSITORY+
            "/.github/workflows/product-validation.yml@"+self.owner["collectorWorkflowSha"],
            "sha":self.owner["collectorWorkflowSha"]}]
        self.current_commit = {**deepcopy(self.f.commit), "sha":self.producer["commit"],
                               "tree":{"sha":self.producer["tree"]}}
        self.current_job = {"id":1001, "name":"product-validation / plan",
            "run_id":self.producer["runId"], "head_sha":self.current_run["head_sha"],
            "status":"in_progress", "conclusion":None, "started_at":"2026-10-24T11:00:00Z"}

    def api(self, url, token):
        base = "https://api.github.com/repos/"+native.REPOSITORY
        attempt = base+f"/actions/runs/{self.producer['runId']}/attempts/{self.producer['runAttempt']}"
        if url == attempt: value = self.current_run
        elif url.startswith(attempt+"/jobs?"): value = {"jobs":[self.current_job]}
        elif url == base+"/git/commits/"+self.producer["commit"] and self.producer["commit"] != self.f.producer["commit"]:
            value = self.current_commit
        else: return self.f.api(url,token)
        return json.dumps(deepcopy(value)).encode()

    @contextmanager
    def boundaries(self):
        with self.fixture.boundaries(), patch.object(reuse,"api_request",side_effect=self.api):
            yield

    @contextmanager
    def open(self):
        self.f.number += 1
        with self.boundaries(), completed.historical_checkpoint_consumer(
                self.history,self.selection,self.f.root/str(self.f.number),
                root=self.f.root,current_policy=self.policy,consumer=self.consumer,job="plan",token="synthetic") as witness:
            yield witness

    def validate(self, witness, *, wrong_key=False):
        issued=self.fixture.issued
        with ExitStack() as stack:
            stack.enter_context(patch.object(native,"_validate_completed_sdk",return_value=deepcopy(issued.fixture.parent_sdk)))
            stack.enter_context(patch.object(completed,"_base",return_value=issued.fixture.base))
            stack.enter_context(patch.object(completed,"_contract_files"))
            stack.enter_context(patch.object(completed,"_inventory_revision",return_value=self.f.producer["commit"]))
            current=stack.enter_context(patch.object(completed,"validate_current",
                side_effect=ValueError("current key differs") if wrong_key else None))
            locators={completed._identity(row["instance"]):row for row in self.f.envelope["completion"]["originals"]}
            def original(record,receipt,locator,token):
                self.assertEqual(locators[completed._identity(receipt)],locator)
                return {},[],locator
            stack.enter_context(patch.object(completed._HistoricalCheckpointConsumer,"original",side_effect=original))
            stack.enter_context(patch.object(completed,"observe_source",
                return_value=({},[],self.f.envelope["completion"]["contractSource"])))
            result=witness.validate(root=self.f.root,revision=self.producer["commit"],consumer_revision=self.producer["commit"],
                frozen=issued.fixture.base,token="synthetic")
            self.assertEqual(self.f.producer["commit"],current.call_args.kwargs["revision"])
            self.assertEqual(self.f.producer["commit"],current.call_args.kwargs["original_revision"])
            return result

    def test_rotated_owner_and_later_consumer_keep_original_native_and_current_key_gates(self):
        with self.open() as witness:
            self.assertIs(type(witness),completed._HistoricalCheckpointConsumer)
            value=self.validate(witness)
            self.assertEqual(self.f.envelope["completion"],value["extension"]["proof"])
            self.assertEqual(self.owner["bootstrap"],witness.bootstrap())
            witness.check(consumer=self.consumer,token="synthetic")
            self.assertEqual([990],self.f.downloads)
            self.assertEqual(1,len(self.f.verified))
            with self.assertRaisesRegex(ValueError,"current key"):
                self.validate(witness,wrong_key=True)
            with self.assertRaisesRegex(ValueError,"separate current-source"):
                witness.inherit({}, {})
        with self.assertRaisesRegex(ValueError,"closed"): witness.check()

    def test_later_attempt_keeps_original_attempt_and_same_producer_path_rejects_it(self):
        self.producer.update(self.f.producer)
        self.producer["runAttempt"] += 1
        self.bind_current()
        with self.open() as witness:
            witness.check(consumer=self.consumer)
            self.assertEqual(self.f.producer["runAttempt"],self.selection["checkpoint"]["source"]["producer"]["runAttempt"])
        with self.fixture.boundaries(), self.assertRaisesRegex(ValueError,"current consumer edge"):
            with completed.checkpoint_consumer(self.f.policy,self.fixture.output,self.f.root/"old-path",
                    root=self.f.root,consumer=self.consumer,job="sdk-ios-metadata",token="synthetic"):
                self.fail("old same-producer path must remain strict")

    def test_unapproved_owner_current_policy_and_failed_original_reject(self):
        original=deepcopy((self.history,self.policy,self.selection,self.current_run,self.current_job,self.f.collector,self.f.issuer))
        for fault in ("owner","history-hash","current-consumer","baseline","current-workflow","current-run","current-attempt","current-repository","current-fork","current-job","source-tree","collector","issuer","subject"):
            (self.history,self.policy,self.selection,self.current_run,self.current_job,self.f.collector,self.f.issuer)=deepcopy(original)
            self.f.jobs=[self.f.collector,self.f.issuer,self.fixture.current,deepcopy(self.fixture.issued.job)]
            if fault=="owner":self.selection["ownerPolicySha256"]="sha256:"+"0"*64
            elif fault=="history-hash":self.history["historicalPolicies"][0]["policy"]["issuerCommit"]="f"*40
            elif fault=="current-consumer":self.policy["consumerCommit"]="f"*40
            elif fault=="baseline":self.policy["sdkCompletion"]["artifactId"]+=1
            elif fault=="current-workflow":self.current_run["referenced_workflows"]=[]
            elif fault=="current-run":self.current_run["id"]+=1
            elif fault=="current-attempt":self.current_run["run_attempt"]+=1
            elif fault=="current-repository":self.current_run["repository"]["full_name"]="untrusted/repository"
            elif fault=="current-fork":self.current_run["head_repository"]["fork"]=True
            elif fault=="current-job":self.current_job.update(status="completed",conclusion="failure")
            elif fault=="source-tree":self.current_commit["tree"]={"sha":"f"*40}
            elif fault=="collector":self.f.collector["conclusion"]="failure"
            elif fault=="issuer":self.f.issuer["conclusion"]="failure"
            else:self.selection["checkpoint"]["subjectSha256"]="sha256:"+"0"*64
            with self.subTest(fault=fault),self.assertRaises(ValueError):
                with self.open():self.fail("invalid history must not yield")
            self.current_commit["tree"]={"sha":self.producer["tree"]}

    def test_explicit_cli_holds_history_and_expires_witness_after_sync_and_deferred_use(self):
        f=self.f
        plan=f.root/"historical-plan.json";plan.write_text(self.f.spec["sourcePlan"])
        history=f.root/"historical-policy.json";history.write_bytes(canonical_json_bytes(self.history))
        policy=f.root/"historical-caller.json"
        self.policy["sdkCheckpointHistory"]={"path":str(history),"sha256":sha256_bytes(history.read_bytes())}
        policy.write_bytes(canonical_json_bytes(self.policy))
        current_plan={**json.loads(self.f.spec["sourcePlan"]),"validationCommit":self.producer["commit"],"validationTree":self.producer["tree"]}
        environment={"GITHUB_REPOSITORY":native.REPOSITORY,"GITHUB_EVENT_NAME":"pull_request","GITHUB_REF":"refs/pull/31/merge",
            "GITHUB_SHA":self.producer["commit"],"GITHUB_RUN_ID":str(self.producer["runId"]),
            "GITHUB_RUN_ATTEMPT":str(self.producer["runAttempt"]),"GITHUB_JOB":"plan","GITHUB_TOKEN":"synthetic"}
        witnesses=[]
        def admit(destination,**kw):
            self.assertEqual(self.producer["commit"],kw["revision"])
            self.assertEqual(self.policy["consumerCommit"],kw["consumer_commit"])
            self.assertEqual(self.policy["sdkCompletion"],kw["sdk_completion"])
            witnesses.append(kw["_checkpoint"])
            sdk=self.validate(kw["_checkpoint"])
            request,phases,receipts=completed.validate_controls(
                self.f.spec,sdk["extension"]["proof"]["controls"],self.fixture.issued.fixture.base)
            spec=deepcopy(self.fixture.issued.fixture.base)
            spec["request"].setdefault("availableObjects",deepcopy(spec["expectedResult"]["phases"]))
            identities={completed._identity(row) for row in phases}
            for field in ("availableObjects","phaseAuthorities"):
                spec["request"][field]=sorted([*spec["request"][field],
                    *(row for row in request[field] if completed._identity(row) in identities)],key=completed._identity)
            spec["expectedResult"]["phases"]=sorted([*spec["expectedResult"]["phases"],*phases],key=completed._identity)
            spec["request"]["repositoryRevision"]=self.producer["commit"]
            return native.CompletedFrozenReuse(spec,receipts,native._COMPLETED_FROZEN,
                revision=self.producer["commit"],sdk=sdk,_checkpoint=kw["_checkpoint"]),{}
        for deferred in (False,True):
            with self.boundaries(),patch.dict(os.environ,environment,clear=True),                    patch.object(products,"_validate_plan",return_value=current_plan),                    patch.object(native,"fetch_completed_frozen",side_effect=admit):
                args={"plan":plan,"repository_root":f.root,"completed_frozen_policy":policy,
                      "sdk_historical_checkpoint":json.dumps(self.selection)}
                with native.completed_frozen_options(args,defer=deferred) as options:
                    cap=options["completed_frozen_future"].result(timeout=5) if deferred else options["completed_frozen"]
                    self.assertIs(type(cap),native.CompletedFrozenReuse)
                    cap.check_consumer(self.consumer)
                    self.assertNotIn("sdk_historical_checkpoint",args)
            with self.assertRaisesRegex(ValueError,"closed"):witnesses[-1].check()
            with self.assertRaisesRegex(ValueError,"closed"):cap.check_consumer(self.consumer)
        with self.boundaries(),patch.dict(os.environ,environment,clear=True),                patch.object(products,"_validate_plan",return_value=current_plan),                patch.object(native,"fetch_completed_frozen",side_effect=admit),self.assertRaisesRegex(ValueError,"historical owner policy changed"):
            with native.completed_frozen_options({"plan":plan,"repository_root":f.root,"completed_frozen_policy":policy,
                    "sdk_historical_checkpoint":json.dumps(self.selection)}):
                history.write_bytes(history.read_bytes()+b" ")
        with self.assertRaisesRegex(ValueError,"closed"):witnesses[-1].check()



    def test_auto_cli_uses_current_policy_and_one_live_factory_before_export(self):
        f = self.f
        plan = f.root/"auto-plan.json"
        plan.write_text(f.spec["sourcePlan"])
        history = f.root/"auto-history.json"
        history.write_bytes(canonical_json_bytes(self.history))
        policy = f.root/"auto-policy.json"
        self.policy["sdkCheckpointHistory"] = {"path":str(history), "sha256":sha256_bytes(history.read_bytes())}
        policy.write_bytes(canonical_json_bytes(self.policy))
        current_plan = {**json.loads(f.spec["sourcePlan"]),
            "validationCommit":self.producer["commit"], "validationTree":self.producer["tree"]}
        env = {"GITHUB_REPOSITORY":native.REPOSITORY, "GITHUB_EVENT_NAME":"pull_request",
            "GITHUB_REF":"refs/pull/31/merge", "GITHUB_SHA":self.producer["commit"],
            "GITHUB_RUN_ID":str(self.producer["runId"]), "GITHUB_RUN_ATTEMPT":str(self.producer["runAttempt"]),
            "GITHUB_JOB":"plan", "GITHUB_TOKEN":"synthetic"}
        held = []
        class Live:
            def check_consumer(inner, consumer):
                held[-1].check(consumer=consumer)
        def admit(destination, **kwargs):
            held.append(kwargs["_checkpoint"])
            held[-1].check(consumer=self.consumer)
            self.assertEqual(self.producer["commit"],kwargs["revision"])
            self.assertEqual(self.policy["consumerCommit"],kwargs["consumer_commit"])
            self.assertEqual(self.policy["sdkCompletion"],kwargs["sdk_completion"])
            return Live(), {}
        with self.boundaries(), patch.dict(os.environ, env, clear=True), \
                patch.object(products,"_validate_plan",return_value=current_plan), \
                patch.object(completed,"discover_historical_checkpoint",return_value=(self.selection,f.raw)) as discovery, \
                patch.object(native,"fetch_completed_frozen",side_effect=admit) as gate:
            with native.completed_frozen_options({"plan":plan,"repository_root":f.root,
                    "completed_frozen_policy":policy,"sdk_historical_checkpoint":"auto"}) as options:
                options["completed_frozen"].check_consumer(self.consumer)
                self.assertEqual(1, discovery.call_count)
                self.assertEqual(1, gate.call_count)
                self.assertEqual([], f.downloads)
                self.assertEqual(1, len(f.verified))
            with self.assertRaisesRegex(ValueError,"closed"):
                held[-1].check()
            env["GITHUB_JOB"] = "unregistered-worker"
            with patch.dict(os.environ,env,clear=True), self.assertRaisesRegex(ValueError,"actual current CI source"):
                with native.completed_frozen_options({"plan":plan,"repository_root":f.root,
                        "completed_frozen_policy":policy,"sdk_historical_checkpoint":"auto"}):
                    self.fail("unregistered job cannot discover or export checkpoint authority")
            self.assertEqual(1, discovery.call_count)

    def prepare_wave6_discovery(self):
        f = self.f
        f.policy["collectors"] = sorted(set(f.policy["collectors"]) | {"product-validation / sdk-collect-6"})
        f.source["jobName"] = "product-validation / sdk-collect-6"
        f.spec["source"] = deepcopy(f.source)
        f.envelope["sourceCheckpoint"]["source"] = deepcopy(f.source)
        f.collector["name"] = f.source["jobName"]
        f.identity = completed.checkpoint_archive_identity(f.policy, f.source,
            **{k: v for k, v in native._native_pin_arguments(f.selector).items()
               if k in ("signer_commit", "source_commit", "run_id", "run_attempt")})
        f.issuer["name"] = f.identity["jobName"]
        f.artifacts[f.source["artifactId"]]["name"] = (
            f"codex-agent-sdk-wave-6-state-{f.producer['tree']}-attempt-{f.producer['runAttempt']}")
        f.artifacts[992]["name"] = completed.collector_control_artifact_name(f.source)
        f.envelope["ownerPolicySha256"] = sha256_bytes(canonical_json_bytes(f.policy))
        f.envelope["completion"]["specSha256"] = sha256_bytes(canonical_json_bytes(f.spec))
        f.envelope["completion"]["source"] = products._runtime_original_locator(
            f.artifacts[f.source["artifactId"]], f.source["workflowSha"],
            PhaseInstanceId("sdk", "javascript", "metadata", "node"), f.collector)
        self.history["historicalPolicies"] = [{"sha256": f.envelope["ownerPolicySha256"], "policy": deepcopy(f.policy)}]
        f.upload()
        return {completed._identity(row): {field: row[field] for field in completed.IDENTITY + completed.OBJECT}
                for row in f.spec["completedPhases"][:1]}

    def test_auto_wave6_discovery_acquires_once_then_requires_original_and_current_native_custody(self):
        retained = self.prepare_wave6_discovery()
        f = self.f
        def download(artifact, token, destination, limit, digest, size):
            self.assertEqual(990, artifact["id"])
            self.assertEqual(2 * completed.LIMIT, limit)
            self.assertEqual((sha256_bytes(f.raw), len(f.raw)), (digest, size))
            Path(destination).write_bytes(f.raw)
            return artifact, destination
        reports = []
        acquire = native._fetch_qualification_archive
        def capture(*args, **kwargs):
            value = acquire(*args, **kwargs)
            reports.append(value[0])
            return value
        with self.boundaries(), ExitStack() as stack:
            stack.enter_context(patch.object(native, "_fetch_qualification_archive", side_effect=capture))
            stack.enter_context(patch("products.inventory.git_regular_blob_bytes", return_value=canonical_json_bytes(f.spec)))
            current = {completed._identity(row): {field: row[field] for field in completed.IDENTITY + completed.OBJECT}
                       for row in f.spec["completedPhases"]}
            stack.enter_context(patch.object(completed, "_current_checkpoint_baseline", side_effect=[retained, current]))
            listed = stack.enter_context(patch.object(products, "_catalog_artifacts", return_value=[f.artifacts[990]]))
            transfer = stack.enter_context(patch.object(products, "_download_contract_ci_upload_bytes", side_effect=download))
            selection, raw = completed.discover_historical_checkpoint(
                self.history, self.policy, root=f.root, consumer=self.consumer, token="synthetic")
            self.assertEqual("product-validation / sdk-collect-6", selection["checkpoint"]["source"]["jobName"])
            self.assertEqual(f.producer, selection["checkpoint"]["source"]["producer"])
            self.assertEqual(1, listed.call_count)
            self.assertEqual(1, transfer.call_count)
            self.assertEqual([], f.verified)  # Selector bytes have no authority.
            with completed.historical_checkpoint_consumer(
                    self.history, selection, f.root/"automatic", root=f.root, current_policy=self.policy,
                    consumer=self.consumer, job="plan", token="synthetic", _archive_bytes=raw) as witness:
                self.assertIs(type(witness), completed._HistoricalCheckpointConsumer)
                witness.check(consumer=self.consumer)
                self.assertEqual(1, len(f.verified))
                self.assertEqual([], f.downloads)  # Original bytes, no second acquisition.
                self.assertEqual(0, reports[-1]["downloadedQualificationBytes"])
                self.assertEqual(len(raw), reports[-1]["heldCheckpointArchiveBytes"])
            with self.assertRaisesRegex(ValueError, "closed"):
                witness.check()
            with self.assertRaisesRegex(ValueError, "fresh original transport"):
                with completed.historical_checkpoint_consumer(
                        self.history, selection, f.root/"changed-transport", root=f.root, current_policy=self.policy,
                        consumer=self.consumer, job="plan", token="synthetic", _archive_bytes=raw+b"x"):
                    self.fail("changed discovery bytes cannot acquire authority")
            self.assertEqual(1, len(f.verified))

    def test_auto_discovery_skips_complete_baseline_and_never_overwrites_retained_or_adds_owner(self):
        from products.registry import PHASE_INSTANCE_IDS
        retained = self.prepare_wave6_discovery()
        f = self.f
        complete = {key: {} for key in PHASE_INSTANCE_IDS if key.product == "sdk"
                    and key != PhaseInstanceId("sdk", "sdk-ios", "binary", "ios")}
        self.assertEqual(61, len(complete))
        with patch.object(native, "_ensure_native_issuer_commit"), \
                patch("products.inventory.git_regular_blob_bytes", return_value=canonical_json_bytes(f.spec)), \
                patch.object(completed, "_current_checkpoint_baseline", return_value=complete), \
                patch.object(products, "_catalog_artifacts") as listed:
            self.assertEqual((None, None), completed.discover_historical_checkpoint(
                self.history, self.policy, root=f.root, consumer=self.consumer, token="synthetic"))
            listed.assert_not_called()
        original = deepcopy(f.envelope)
        for case in ("unknown-owner", "missing-baseline", "conflicting-tuple"):
            f.envelope = deepcopy(original)
            if case == "unknown-owner":
                f.envelope["ownerPolicySha256"] = "sha256:"+"0"*64
            elif case == "missing-baseline":
                f.envelope["recipe"]["completedPhases"].pop(0)
            else:
                f.envelope["recipe"]["completedPhases"][0]["objectSha256"] = "sha256:"+"0"*64
            f.upload()
            def download(artifact, token, destination, *args):
                Path(destination).write_bytes(f.raw)
                return artifact, destination
            with self.subTest(case=case), patch.object(native, "_ensure_native_issuer_commit"), \
                    patch("products.inventory.git_regular_blob_bytes", return_value=canonical_json_bytes(f.spec)), \
                    patch.object(completed, "_current_checkpoint_baseline", side_effect=[retained,
                        {completed._identity(row): {field: row[field] for field in completed.IDENTITY + completed.OBJECT}
                         for row in f.envelope["recipe"]["completedPhases"]}]), \
                    patch.object(products, "_catalog_artifacts", return_value=[f.artifacts[990]]), \
                    patch.object(products, "_download_contract_ci_upload_bytes", side_effect=download):
                if case == "conflicting-tuple":
                    with self.assertRaisesRegex(ValueError, "conflicts"):
                        completed.discover_historical_checkpoint(
                            self.history, self.policy, root=f.root, consumer=self.consumer, token="synthetic")
                else:
                    self.assertEqual((None, None), completed.discover_historical_checkpoint(
                        self.history, self.policy, root=f.root, consumer=self.consumer, token="synthetic"))
        self.assertEqual([], f.verified)


    def test_discovery_skips_newer_stale_112_hint_for_older_current_javascript_checkpoint(self):
        # Selection is deliberately not admission: native/Git formats are fixture
        # seams; the real inventory/dependency eligibility calculation runs here.
        import io
        import zipfile
        from products.registry import PHASE_INSTANCE_IDS
        self.prepare_wave6_discovery()
        f = self.f
        original_revision, new_revision = "1"*40, "2"*40
        ids = sorted(key for key in PHASE_INSTANCE_IDS if key.product == "sdk"
                     and key != PhaseInstanceId("sdk", "sdk-ios", "binary", "ios"))
        rows = [{**products._identity_record(key), **{name:"sha256:"+"1"*64 for name in completed.OBJECT}}
                for key in ids]
        baseline = {"source":{"inventoryCommit":original_revision}, "completedPhases":rows}
        baseline["source"]["producer"] = deepcopy(f.producer)
        old = deepcopy(f.envelope)
        old["recipe"] = deepcopy(baseline)
        old["recipe"]["source"] = deepcopy(f.source)
        old["recipe"]["source"]["inventoryCommit"] = original_revision
        old["sourceCheckpoint"]["source"] = deepcopy(old["recipe"]["source"])
        newer = deepcopy(old)
        newer["recipe"]["source"]["inventoryCommit"] = new_revision
        newer["sourceCheckpoint"]["source"] = deepcopy(newer["recipe"]["source"])
        for row in newer["recipe"]["completedPhases"]:
            if row["component"] == "javascript":
                for field in completed.OBJECT:
                    row[field] = "sha256:"+"2"*64
        # Keep exact required selector source shape: inventoryCommit equals producer.commit.
        for value in (old, newer):
            value["recipe"]["source"]["producer"]["commit"] = value["recipe"]["source"]["inventoryCommit"]
            value["sourceCheckpoint"]["source"] = deepcopy(value["recipe"]["source"])
        def archive(value):
            out=io.BytesIO()
            with zipfile.ZipFile(out,"w") as z:
                z.writestr("completion.json",canonical_json_bytes(value))
                z.writestr("bundle.jsonl",b"untrusted discovery fixture; not a native signature")
            return out.getvalue()
        bodies={993:archive(old),992:archive(newer)}
        artifacts=[{**f.artifacts[990],"id":key,"digest":sha256_bytes(raw),"size_in_bytes":len(raw),
            "archive_download_url":f"https://api.github.com/repos/{native.REPOSITORY}/actions/artifacts/{key}/zip"}
            for key,raw in bodies.items()]
        reads=[]
        def download(artifact,token,destination,*args):
            reads.append(artifact["id"])
            Path(destination).write_bytes(bodies[artifact["id"]])
            return artifact,destination
        def tree(root,revision):
            return [("codex-agent-bindings/javascript/package.json",
                     "old" if revision==original_revision else "new")]
        with patch.object(native,"_ensure_native_issuer_commit"), \
                patch("products.inventory.git_regular_blob_bytes",return_value=canonical_json_bytes(baseline)), \
                patch.object(completed,"_spec"), \
                patch.object(completed,"_inventory_revision",side_effect=lambda spec,*args,**kwargs:spec["source"]["inventoryCommit"]), \
                patch("products.inventory.tree_entries",side_effect=tree), \
                patch.object(products,"_catalog_artifacts",return_value=artifacts), \
                patch.object(products,"_download_contract_ci_upload_bytes",side_effect=download):
            retained=completed._current_checkpoint_baseline(baseline,f.root,self.producer["commit"],"synthetic")
            self.assertEqual(109,51+len(retained))
            selected,raw=completed.discover_historical_checkpoint(
                self.history,self.policy,root=f.root,consumer=self.consumer,token="synthetic")
            self.assertEqual(992,selected["checkpoint"]["native"]["artifactId"])
            self.assertEqual([993,992],reads)
            self.assertEqual(bodies[992],raw)
        self.assertEqual([],f.verified)  # Actual factory/signature/current-source gates must still follow.

    def test_factory_to_native_export_restricts_changed_javascript_and_keeps_109_originals(self):
        # Synthetic native/Git boundaries; real factory, sealed capability and
        # dependency restriction. No actual hosted proof or product is executed.
        from ci.tests.test_completed_frozen_reuse import CompletedFrozenReuseTest, POLICY
        from ci.tests.test_products import phase_receipt
        from products import inventory
        from products.plan import _phase_version_identity
        from products.receipt import compute_build_key, validate_phase_receipt
        from products.registry import PHASE_INSTANCE_IDS
        fixture = CompletedFrozenReuseTest()
        fixture.setUp()
        sdk, parent_phase, _, _ = fixture.sdk_fixture()
        parent_receipt = sdk["original"]["receipt"]
        parent_id = products._identity(parent_phase)
        request = deepcopy(fixture.spec["request"])
        request["availableObjects"].append(parent_phase)
        request["phaseAuthorities"].append({
            **{field: parent_receipt[field] for field in completed.IDENTITY},
            **{field: parent_receipt["inputs"][field] for field in
               ("flagsDigest", "toolchainProfileDigest", "outputSchemaVersion")}})
        phases, receipts = [], []
        for instance in sorted(PHASE_INSTANCE_IDS):
            if instance.product != "sdk" or instance == parent_id:
                continue
            receipt = phase_receipt()
            receipt.update({field:getattr(instance, field) for field in completed.IDENTITY})
            receipt["productVersion"] = request["versions"]["sdk"]
            receipt["inputs"]["versionIdentity"] = _phase_version_identity(instance, request["versions"])
            receipt["buildKey"] = compute_build_key(**{
                field:receipt[field] for field in (*completed.IDENTITY, "inputs")})
            validate_phase_receipt(receipt)
            phase = {**{field:receipt[field] for field in (*completed.IDENTITY, "buildKey")},
                "receiptSha256":sha256_bytes(canonical_json_bytes(receipt)),
                "objectSha256":sha256_bytes(("synthetic:" + str(instance)).encode()), "state":"retained"}
            phases.append(phase)
            receipts.append(receipt)
            request["availableObjects"].append(phase)
            request["phaseAuthorities"].append({
                **{field:receipt[field] for field in completed.IDENTITY},
                **{field:receipt["inputs"][field] for field in
                   ("flagsDigest", "toolchainProfileDigest", "outputSchemaVersion")}})
        self.assertEqual(61, len(phases))
        source_revision = self.f.spec["source"]["inventoryCommit"]
        sdk["extension"] = {"spec":{"schemaVersion":4,
            "source":{"inventoryCommit":source_revision},
            "sourcePredecessors":[{field:row[field] for field in (*completed.IDENTITY,*completed.OBJECT)}
                                  for row in [*fixture.spec["expectedResult"]["phases"],parent_phase]],
            "completedPhases":phases}, "proof":{"controls":{}}}
        native_controls = {"qualification.json":b"synthetic native subject",
            "bundle.jsonl":b"synthetic native bundle", "proof.json":canonical_json_bytes(fixture.proof)}
        js = {instance for instance in PHASE_INSTANCE_IDS
              if instance.product == "sdk" and instance.component == "javascript"}
        package_path = "codex-agent-bindings/javascript/package.json"
        for changed, partial in ((False, False), (True, False), (True, True)):
            active_sdk = deepcopy(sdk)
            pairs = [(phase, receipt) for phase, receipt in zip(phases, receipts)
                     if not partial or (phase["component"], phase["phase"]) == ("javascript", "metadata")]
            active_phases, active_receipts = ([pair[index] for pair in pairs] for index in (0, 1))
            active_ids = {products._identity(phase) for phase in active_phases}
            active_sdk["extension"]["spec"]["completedPhases"] = active_phases
            active_sdk["extension"]["spec"]["sourcePredecessors"] = [
                {field: row[field] for field in (*completed.IDENTITY, *completed.OBJECT)}
                for row in request["availableObjects"] if products._identity(row) not in active_ids]
            with self.subTest(changed=changed, partial=partial), self.open() as witness, ExitStack() as stack:
                stack.enter_context(patch.object(native,"_compatible_verifier",return_value=True))
                stack.enter_context(patch.object(native,"_ensure_native_issuer_commit"))
                stack.enter_context(patch.object(native,"_fetch_qualification_archive",
                    return_value=({"downloadedQualificationBytes":1234},native_controls)))
                stack.enter_context(patch.object(native,"_authenticate_bytes",return_value=fixture.qualified))
                stack.enter_context(patch.object(inventory,"git_regular_blob_bytes",
                    return_value=canonical_json_bytes(fixture.spec)))
                stack.enter_context(patch.object(native,"_sdk_parent_frozen_spec",return_value=fixture.spec))
                stack.enter_context(patch.object(native,"_capture_completed_contract_receipts",
                    return_value=[r for i,r in fixture.receipts.items() if i.product=="contract"]))
                stack.enter_context(patch.object(native,"_completed_sdk_controls",
                    return_value=(request,parent_phase,parent_receipt,{})))
                stack.enter_context(patch.object(completed,"_base",return_value=fixture.spec))
                stack.enter_context(patch.object(completed,"validate_controls",
                    return_value=(request,active_phases,active_receipts)))
                original = stack.enter_context(patch.object(completed,"_inventory_revision",
                    return_value=source_revision))
                def semantic(spec, proof, arguments, **kwargs):
                    self.assertEqual(self.f.spec, spec)
                    self.assertEqual(self.f.envelope["completion"], proof)
                    self.assertEqual(source_revision, kwargs["revision"])
                    self.assertEqual(source_revision, kwargs["requalification_baseline"])
                    self.assertEqual(self.producer["commit"], kwargs["consumer_revision"])
                    self.assertIs(witness, kwargs["_checkpoint"])
                    return deepcopy(active_sdk)
                admitted = stack.enter_context(patch.object(completed,"validate_extension",side_effect=semantic))
                stack.enter_context(patch.object(inventory,"tree_entries",side_effect=lambda root, revision:
                    [(package_path,"new" if changed and revision==self.producer["commit"] else "old")]))
                stack.enter_context(patch.object(products,"_authorities",side_effect=lambda root, revision, ids:
                    (sorted([r for r in request["phaseAuthorities"] if products._identity(r) in ids],
                            key=products._identity),None)))
                stack.enter_context(patch.object(products,"_versions",return_value=request["versions"]))
                stack.enter_context(patch("products.restore.verify_object",
                    side_effect=AssertionError("no unchanged product body replay")))
                cap, report = native.fetch_completed_frozen(self.f.root/"native-projection",
                    consumer_commit=self.policy["consumerCommit"],verifier_policy_sha256=POLICY,
                    repository_root=self.f.root,revision=self.producer["commit"],
                    sdk_completion=self.policy["sdkCompletion"],_checkpoint=witness,
                    signer_commit="b"*40,source_commit="a"*40,artifact_id=71,
                    artifact_sha256=POLICY,run_id=72,run_attempt=1,token="synthetic")
                self.assertEqual(1, admitted.call_count)
                original.assert_called_once_with(self.f.spec,self.f.root,token="synthetic")
                self.assertEqual(51 if partial else 109 if changed else 112,len(cap.completed_phases()))
                self.assertEqual(js & active_ids if changed else set(),{
                    products._identity(row) for row in report["invalidatedPhases"]})
                self.assertEqual(0,report["productBodiesDownloaded"])
                for phase,receipt in pairs:
                    if changed and products._identity(phase) in js:
                        self.assertIsNone(cap.envelope(phase))
                        self.assertNotIn(phase["objectSha256"],cap.deferred_objects())
                        self.assertIsNone(cap.phase_plan(products._identity(phase),{},None,[]))
                    else:
                        self.assertEqual(receipt,cap.envelope(phase,canonical_json_bytes(receipt))["receipt"])
                cap.check_consumer(self.consumer)
            with self.assertRaisesRegex(ValueError,"closed"):
                cap.completed_phases()

if __name__=='__main__':unittest.main()

class HistoricalCheckpointIssuerTest(unittest.TestCase):
    def setUp(self):
        self.h=HistoricalCheckpointConsumerTest(); self.h.setUp(); self.addCleanup(self.h.doCleanups)
        h=self.h
        h.owner['collectors']=sorted(set(h.owner['collectors'])|{'product-validation / sdk-collect-4'})
        h.current_job['name']='product-validation / sdk-checkpoint-4 / completed-sdk-checkpoint'
        h.current_run['referenced_workflows'].append({'path':native.REPOSITORY+'/'+native.ISSUER_WORKFLOW+'@'+h.owner['issuerCommit'],
                                                     'sha':h.owner['issuerCommit']})
        self.source={**deepcopy(h.f.source),'producer':h.producer,'inventoryCommit':h.producer['commit'],
            'workflowSha':h.owner['collectorWorkflowSha'],'jobName':'product-validation / sdk-collect-4',
            'jobId':1002,'artifactId':1003}
        self.collector={**h.current_job,'id':1002,'name':self.source['jobName'],
            'status':'completed','conclusion':'success','started_at':'2026-10-24T10:45:00Z','completed_at':'2026-10-24T10:55:00Z'}
        artifact=h.f.artifact(1003,'codex-agent-sdk-wave-4-state-'+h.producer['tree']+'-attempt-'+str(h.producer['runAttempt']),
                              self.source['artifactSha256'],self.source['artifactBytes'],'10:50:00')
        artifact['workflow_run']={'id':h.producer['runId'],'head_sha':h.current_run['head_sha']}
        h.f.artifacts[1003]=artifact

    def api(self,url,token):
        h=self.h
        if f"/actions/runs/{h.producer['runId']}/attempts/{h.producer['runAttempt']}/jobs?" in url:
            return json.dumps({'jobs':[h.current_job,self.collector]}).encode()
        return h.api(url,token)

    @contextmanager
    def open(self):
        h=self.h;h.f.number+=1
        with h.fixture.boundaries(), patch.object(reuse,'api_request',side_effect=self.api), \
                completed._historical_checkpoint_issuer(h.history,h.selection,h.f.root/str(h.f.number),
                    root=h.f.root,current_policy=h.policy,source=self.source,token='synthetic') as witness:
            yield witness

    def test_historical_issuer_binds_both_real_jobs_and_exact_inner_subject_then_closes(self):
        h=self.h
        with self.open() as witness:
            self.assertIs(type(witness),completed._HistoricalCheckpointIssuer)
            prior=h.validate(witness)
            new={**deepcopy(h.f.spec),'source':self.source}
            new.pop('reuseCompletion',None);new.pop('reuseCompletionProofSha256',None)
            witness.inherit(new,prior)
            changed=deepcopy(prior);changed['extension']['proof']['members'][0]['bytes']+=1
            with self.assertRaises(ValueError):witness.inherit(new,changed)
            with self.assertRaises(ValueError):witness.inherit({**new,'source':h.f.source},prior)
            self.assertEqual([990],h.f.downloads)
        with self.assertRaisesRegex(ValueError,'closed'):witness.inherit(new,prior)

    def test_wrong_current_issuer_collector_or_unapproved_predecessor_never_inherits(self):
        h=self.h;baseline=deepcopy((h.history,h.current_job,self.collector,h.current_run))
        for fault in ('history','issuer','collector-failed','collector-running','collector-late','workflow','duplicate'):
            with self.subTest(fault=fault):
                h.history,h.current_job,self.collector,h.current_run=deepcopy(baseline)
                if fault=='history':h.history['historicalPolicies'].clear()
                elif fault=='issuer':h.current_job['name']='product-validation / plan'
                elif fault=='collector-failed':self.collector['conclusion']='failure'
                elif fault=='collector-running':self.collector.update(status='in_progress',conclusion=None)
                elif fault=='collector-late':self.collector['completed_at']='2026-10-24T11:01:00Z'
                elif fault=='workflow':h.current_run['referenced_workflows'].pop()
                else:self.collector['id']=h.current_job['id']
                with self.assertRaises(ValueError):
                    with self.open():self.fail('invalid historical issuer yielded authority')

    def test_signed_historical_predecessor_shape_requires_independent_owner_history(self):
        h=self.h;f=h.f
        previous={'native':{**f.selector,'artifactId':777,'runId':f.producer['runId']-1},
            'subjectSha256':sha256_bytes(b'original predecessor'),
            'ownerPolicySha256':h.selection['ownerPolicySha256'],
            'source':{**deepcopy(f.source),'jobId':7771,'producer':{**f.producer,'runId':f.producer['runId']-1}}}
        f.envelope['precedingCheckpoint']=previous
        f.spec.pop('reuseCompletion');f.spec.pop('reuseCompletionProofSha256')
        f.envelope['completion']['specSha256']=sha256_bytes(canonical_json_bytes(f.spec))
        f.upload();h.selection['checkpoint']['native']=deepcopy(f.selector)
        h.selection['checkpoint']['subjectSha256']=sha256_bytes(f.subject)
        with self.open() as witness:self.assertIs(type(witness),completed._HistoricalCheckpointIssuer)
        for fault in ('owner','signer','future','same-upload'):
            with self.subTest(fault=fault):
                f.envelope['precedingCheckpoint']=deepcopy(previous)
                p=f.envelope['precedingCheckpoint']
                if fault=='owner':p['ownerPolicySha256']=sha256_bytes(b'unknown')
                elif fault=='signer':p['native']['signerCommit']='a'*40
                elif fault=='future':p['native']['runId']=f.producer['runId']
                else:p['native']['artifactId']=f.selector['artifactId']
                f.upload();h.selection['checkpoint']['native']=deepcopy(f.selector)
                h.selection['checkpoint']['subjectSha256']=sha256_bytes(f.subject)
                with self.assertRaises(ValueError):
                    with self.open():self.fail('unapproved inherited owner yielded authority')

class SameAttemptNativeIssuerTest(unittest.TestCase):
    def fixture(self,old_wave,new_wave):
        t=HistoricalCheckpointIssuerTest();t.setUp();self.addCleanup(t.doCleanups)
        h=t.h;f=h.f
        f.policy['collectors']=sorted(set(f.policy['collectors'])|{f'product-validation / sdk-collect-{wave}' for wave in (4,6,7,8)})
        f.source['jobName']=f'product-validation / sdk-collect-{old_wave}'
        f.collector['name']=f.source['jobName']
        f.envelope['sourceCheckpoint']['source']=f.source
        f.identity=completed.checkpoint_archive_identity(f.policy,f.source,**{key:value for key,value in native._native_pin_arguments(f.selector).items()
            if key in ('signer_commit','source_commit','run_id','run_attempt')})
        f.issuer['name']=f.identity['jobName'];f.envelope['ownerPolicySha256']=sha256_bytes(canonical_json_bytes(f.policy))
        f.envelope['completion']['specSha256']=sha256_bytes(canonical_json_bytes(f.spec))
        f.envelope['completion']['source']['job']['name']=f.source['jobName']
        f.artifacts[f.source['artifactId']]['name']=f'codex-agent-sdk-wave-{old_wave}-state-'+f.producer['tree']+'-attempt-'+str(f.producer['runAttempt'])
        f.artifacts[992]['name']=completed.collector_control_artifact_name(f.source)
        f.envelope['completion']['source']=products._runtime_original_locator(f.artifacts[f.source['artifactId']],
            f.source['workflowSha'],PhaseInstanceId('sdk','javascript','metadata','node'),f.collector)
        f.upload()
        h.owner=deepcopy(f.policy);h.history['currentOwner']=h.owner;h.history['historicalPolicies']=[]
        h.policy['sdkCompletion']=deepcopy(h.owner['bootstrap']);h.producer=deepcopy(f.producer)
        h.selection={'ownerPolicySha256':sha256_bytes(canonical_json_bytes(h.owner)),
                     'checkpoint':{'kind':'sdk-checkpoint','source':f.source,'native':f.selector,'subjectSha256':sha256_bytes(f.subject)}}
        h.bind_current();h.current_run=deepcopy(f.run);h.current_run['conclusion']=None
        h.current_job['name']=f'product-validation / sdk-checkpoint-{new_wave} / completed-sdk-checkpoint'
        t.source.update(producer=h.producer,inventoryCommit=h.producer['commit'],workflowSha=h.owner['collectorWorkflowSha'],
                        jobName=f'product-validation / sdk-collect-{new_wave}')
        t.collector.update(name=t.source['jobName'],run_id=h.producer['runId'])
        f.artifacts[1003]['name']=f'codex-agent-sdk-wave-{new_wave}-state-'+h.producer['tree']+'-attempt-'+str(h.producer['runAttempt'])
        f.artifacts[1003]['workflow_run']['id']=h.producer['runId']
        original=t.api
        def api(url,token):
            if f"/actions/runs/{h.producer['runId']}/attempts/{h.producer['runAttempt']}/jobs?" in url:
                return json.dumps({'jobs':[f.collector,f.issuer,h.current_job,t.collector]}).encode()
            return original(url,token)
        t.api=api
        return t

    def test_exact_native_edges_use_completed_predecessor_without_a_whole_campaign_wait(self):
        for edge in ((4,7),(4,8),(7,8)):
            with self.subTest(edge=edge):
                t=self.fixture(*edge)
                with t.open() as witness:
                    self.assertIs(type(witness),completed._HistoricalCheckpointIssuer)
                    self.assertIs(witness.observation,witness._current_observation)
                    self.assertEqual([990],t.h.f.downloads)
                with self.assertRaisesRegex(ValueError,'closed'):witness.check()

    def test_wrong_edge_later_issuer_or_reordered_collectors_never_inherits(self):
        for fault in ('reverse','same-wave','future-issuer','late-collector','rotated-owner'):
            with self.subTest(fault=fault):
                t=self.fixture(*( (7,4) if fault=='reverse' else (4,4) if fault=='same-wave' else (4,7)))
                if fault=='future-issuer':t.h.f.issuer['completed_at']='2026-10-24T11:01:00Z'
                elif fault=='late-collector':t.h.f.collector['completed_at']='2026-10-24T10:46:00Z'
                elif fault=='rotated-owner':t.h.owner['issuerCommit']='e'*40
                with self.assertRaises(ValueError):
                    with t.open():self.fail('unregistered or future native predecessor yielded authority')

class NativeIssuerDiscoveryTest(unittest.TestCase):
    def test_only_finished_registered_same_attempt_predecessor_is_selected_without_waiting(self):
        for status in ('success','running','failed','plan-consumer','wrong-edge'):
            with self.subTest(status=status):
                factory=SameAttemptNativeIssuerTest();t=factory.fixture(4,6 if status=='wrong-edge' else 7)
                self.addCleanup(factory.doCleanups);h=t.h;f=h.f
                if status=='running':f.issuer.update(status='in_progress',conclusion=None,completed_at=None)
                elif status=='failed':f.issuer['conclusion']='failure'
                phases=completed._records(f.spec['completedPhases'],'fixture phases')
                current={key:{field:row[field] for field in completed.IDENTITY+completed.OBJECT} for key,row in phases.items()}
                baseline=dict(list(current.items())[:1]);reads=[]
                def download(artifact,token,path,*args):
                    reads.append(artifact['id']);Path(path).write_bytes(f.raw);return artifact,path
                with h.fixture.boundaries(), patch.object(reuse,'api_request',side_effect=t.api), \
                        patch('products.inventory.git_regular_blob_bytes',return_value=canonical_json_bytes(f.spec)), \
                        patch.object(completed,'_current_checkpoint_baseline',side_effect=[baseline,current]), \
                        patch.object(products,'_catalog_artifacts',return_value=[f.artifacts[990]]), \
                        patch.object(products,'_download_contract_ci_upload_bytes',side_effect=download):
                    result,raw=completed.discover_historical_checkpoint(h.history,h.policy,root=f.root,
                        consumer={'kind':'ci','producer':h.producer},token='synthetic',
                        **({} if status=='plan-consumer' else {'_issuer_source':t.source}))
                if status=='success':
                    self.assertEqual(990,result['checkpoint']['native']['artifactId']);self.assertEqual(f.raw,raw)
                    self.assertEqual([990],reads)
                else:self.assertEqual((None,None,[]),(result,raw,reads))
                self.assertEqual([],f.verified)
