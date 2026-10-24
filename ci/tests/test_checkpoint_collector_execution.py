"""Real Core collection/advance and next replay; synthetic CI/native admission only."""
from contextlib import ExitStack,contextmanager
from copy import deepcopy
import io,json,os,shutil
from pathlib import Path
from unittest.mock import patch
import zipfile

import product_reuse as adapter
import reuse_qualification as native
from products.inventory import canonical_json_bytes,load_canonical_json,regular_file_inventory,sha256_bytes,write_canonical_json
from products.receipt import write_output_manifest
from products.restore import CARRIER_REFERENCES_NAME,finalize_phase_object,object_relative_path
from ci.tests.test_product_contract_resume import ContractProductResumeTest
from ci.tests.test_runtime_adapter_collection import RuntimeAdapterCollectionTest

CORE=adapter.PhaseInstanceId('sdk','sdk-core','binary','common')
CHILD='.github/workflows/sdk-core-binary-validation.yml'
WORKER='product-validation / sdk-core-binary-wave / sdk-core-binary-common'
PIN='c'*40


class CheckpointCollectorExecutionTest(ContractProductResumeTest):
    measurements=[]

    @classmethod
    def control_seams(cls):
        stack=ExitStack()
        stack.enter_context(patch.object(adapter,'_validate_plan',return_value=cls.plan))
        stack.enter_context(patch.object(adapter,'_requested',return_value=(CORE,)))
        return stack

    def names(self,instance,key):
        self.assertEqual(CORE,instance)
        return WORKER,f"codex-agent-sdk-worker-sdk-core-binary-common-{key[7:]}-{self.producer['tree']}-attempt-{self.producer['runAttempt']}"

    @contextmanager
    def official(self,ready,body):
        with RuntimeAdapterCollectionTest.official_api(self,{CORE:ready},{CORE:body}) as observed:
            original=observed[0].side_effect
            def api(url,token):
                result=original(url,token)
                if 'referenced_workflows' in result:
                    result=deepcopy(result)
                    result['referenced_workflows'].append({'path':f"{self.producer['repository']}/{CHILD}@{PIN}",'sha':PIN})
                return result
            observed[0].side_effect=api
            yield observed

    def prepared(self,*,local=True):
        cap,discovery=self.completed_contract_fixture()
        controls,release,resumed=self.scratch/'controls',self.scratch/'release',self.scratch/'resumed'
        with self.control_seams():
            adapter.prepare_contract_resume_controls(self.plan_path,discovery,self.state,controls,completed_frozen=cap,
                repository_root=self.repository,environ=self.environment)
            adapter.prepare_contract_release_controls(self.handoff,release)
            with patch('sdk_ios_binary_recovery.capture_completed_ios_binary',return_value=[]):
                adapter.resume_products(controls/'plan/impact-plan.json',controls/'plan/product-reuse',controls/'state',
                    release/'contract-input',resumed,self.scratch/'native-output',completed_frozen=cap,
                    repository_root=self.repository,environ=self.environment,sdk_original_workflow_sha=PIN)
            state=adapter._verified_product_state(controls/'plan/impact-plan.json',resumed,resumed,self.repository,
                self.environment,None,completed_frozen=cap)
        self.assertEqual({CORE},set(state.prior_ready_plans))
        originals={adapter._identity(row):self.state/row['objectPath'] for row in
            load_canonical_json(discovery/'contract-reuse-request.json')['availableObjects']}
        if local:
            references_path=resumed/'contract-state/carrier'/CARRIER_REFERENCES_NAME
            references=load_canonical_json(references_path)
            request_path=resumed/'reuse-wave-request.json';request=load_canonical_json(request_path)
            replacements={}
            for identity,path in state.sources.items():
                self.assertFalse(path.exists())
                phase=state.prior_by_instance[identity]
                key=object_relative_path(phase['buildKey'],phase['receiptSha256'])
                relative='original-objects/'+key;target=resumed/'contract-state'/relative
                target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(originals[identity],target)
                references[key]=relative
                replacements[path.relative_to(resumed).as_posix()]=target.relative_to(resumed).as_posix()
            write_canonical_json(references_path,references)
            for row in request['availableObjects']:
                self.assertIn(row['objectPath'],replacements)
                row['objectPath']=replacements[row['objectPath']]
            write_canonical_json(request_path,request)
            retained_path=resumed/'reused-carrier'/CARRIER_REFERENCES_NAME
            retained=load_canonical_json(retained_path)
            write_canonical_json(retained_path,{key:replacements[value] for key,value in retained.items()})
            with self.control_seams():
                state=adapter._verified_product_state(controls/'plan/impact-plan.json',resumed,resumed,self.repository,
                    self.environment,None,completed_frozen=cap)
        return cap,controls/'plan/impact-plan.json',resumed,state

    def new_upload(self,ready,*,tamper=False):
        stage=self.scratch/'core-stage';(stage/'outputs').mkdir(parents=True)
        (stage/'outputs/core.bin').write_bytes(b'synthetic Core build output; no compiler invoked')
        write_output_manifest(stage,'sdk','sdk-core','binary','common','0.2.0',{'evidence':'outputs'})
        shard=self.scratch/'core-shard'
        obj=finalize_phase_object(stage_root=stage,phase_plan=ready,producer=self.producer,
            product_version='0.2.0',trust_domain='development',destination=shard)
        raw=io.BytesIO()
        with zipfile.ZipFile(raw,'w',compression=zipfile.ZIP_STORED) as archive:
            for row in regular_file_inventory(shard):
                contents=(shard/row['relativePath']).read_bytes()
                if tamper and row['relativePath']==obj['objectPath']:contents+=b'changed new bytes'
                archive.writestr('shard/'+row['relativePath'],contents)
            archive.writestr('execution.json',b'{"fixture":"synthetic successful worker"}\n')
        return obj,raw.getvalue()

    @contextmanager
    def reads(self,old):
        import builtins
        # Object names are exact receipt digests. Matching these names also sees
        # descriptor-relative opens and later private copies of the same object.
        old={path.name for path in old};events=[]
        def watched(function,label):
            def call(path,*args,**kwargs):
                if not isinstance(path,int) and Path(path).name in old:
                    events.append({'operation':label,'path':str(path)})
                return function(path,*args,**kwargs)
            return call
        with patch('builtins.open',side_effect=watched(builtins.open,'open')), \
                patch('io.open',side_effect=watched(io.open,'io.open')), \
                patch('os.open',side_effect=watched(os.open,'os.open')):
            yield events

    def pipeline(self,*,local=True,tamper=False):
        import time
        cap,plan,resumed,state=self.prepared(local=local);ready=state.prior_ready_plans[CORE]
        obj,body=self.new_upload(ready,tamper=tamper)
        old_bytes=sum(path.stat().st_size for path in state.sources.values()) if local else 0
        collected,advanced=self.scratch/'collected',self.scratch/'advanced'
        # Authentication is fixture-native; all state replay, original ZIP/shard
        # verification, collection, advancement, reference publication and next
        # replay below execute without replacing their production functions.
        start=time.perf_counter_ns()
        with self.control_seams(),self.reads(state.sources.values()) as opened, \
                self.official(ready,body) as api:
            result=adapter.collect_runtime_workers(plan,resumed,resumed,collected,trusted_workflow_sha=PIN,
                repository_root=self.repository,environ=self.environment,token='synthetic-token',sdk_family='core-binary',
                sdk_worker_workflow_path=CHILD,sdk_worker_job_name=WORKER,completed_frozen=cap)
            self.assertEqual(1,len(result['rows']))
            row=result['rows'][0]
            self.assertEqual('failure' if tamper else 'success',row['result'],row.get('reason'))
            shards=[] if tamper else [collected/row['shardDirectory']]
            value=adapter.advance_products(plan,resumed,resumed,shards,advanced,self.scratch/'advanced-output',
                repository_root=self.repository,environ=self.environment,sdk_family='core-binary',
                sdk_original_workflow_sha=PIN,completed_frozen=cap,failed_instances=(CORE,) if tamper else (),
                checkpoint_controls=True)
            replay=adapter._verified_product_state(plan,resumed,advanced,self.repository,self.environment,None,
                sdk_original_workflow_sha=PIN,completed_frozen=cap)
        measurement={'localOldBodies':local,'newTampered':tamper,'oldObjectBytes':old_bytes,
            'newUploadBytes':len(body),'oldObjectOpens':len(opened),'elapsedNs':time.perf_counter_ns()-start,
            'oldOperations':opened,'selectedTargetJobs':len(replay.prior_ready_plans)}
        type(self).measurements.append(measurement)
        self.assertEqual([],opened,measurement)
        phases={adapter._identity(row):row for row in value['phases']}
        self.assertEqual('build' if tamper else 'retained',phases[CORE]['state'])
        self.assertEqual({CORE} if tamper else set(),set(replay.prior_ready_plans))
        self.assertEqual(not tamper,value['fullReuse'])
        for identity,path in replay.sources.items():
            if identity.product=='contract':self.assertFalse(path.exists(),'qualified dependency must remain a reference')
        if not tamper:
            self.assertEqual(obj['receiptSha256'],phases[CORE]['receiptSha256'])
            self.assertEqual(obj['objectSha256'],phases[CORE]['objectSha256'])
        self.assertEqual(1,api[2].call_count,'only new original upload is downloaded')
        return cap,state

    def test_actual_core_collection_advance_and_next_replay_do_not_open_local_qualified_contract_objects(self):
        self.pipeline()

    def test_absent_qualified_contract_bodies_still_allow_actual_new_result_and_next_replay(self):
        self.pipeline(local=False)

    def test_new_body_tampering_stays_failed_while_qualified_dependencies_remain_references(self):
        self.pipeline(tamper=True)

    def test_contract_without_qualified_original_members_keeps_original_bytes(self):
        cap,plan,resumed,state=self.prepared()
        spec,_=cap._values()
        receipts=[load_canonical_json(self.receipts[name]) for name in ('binary','package','validation','metadata')]
        limited=native.CompletedFrozenReuse(spec,receipts,native._COMPLETED_FROZEN,revision=self.commit)
        self.assertEqual(frozenset(),limited.deferred_objects(include_contract=True))
        phases=[state.prior_by_instance[identity] for identity in sorted(state.sources)]
        staged=adapter._stage_completed_objects(phases,state.sources,self.scratch/'limited-stage',limited)
        for identity,path in staged.items():self.assertEqual(state.sources[identity].read_bytes(),path.read_bytes())

    def test_reference_handoff_still_rejects_changed_controls_and_unsafe_paths(self):
        cap,plan,resumed,_=self.prepared()
        state=resumed/'contract-state';handoff=resumed/'authenticated-contract/contract-input'
        result=state/'contract-reuse-result.json'
        refs=state/'carrier'/CARRIER_REFERENCES_NAME
        for case in ('object-tuple','reference-path','symlink-result','manifest','signature','receipt'):
            with self.subTest(case=case):
                path={'object-tuple':result,'reference-path':refs,'symlink-result':result,
                    'manifest':handoff/'contract-manifest.json',
                    'signature':handoff/'codex-agent-contract-0.2.0.attestation.sig',
                    'receipt':handoff/'execution-closure/receipts/binary.json'}[case]
                raw=path.read_bytes();destination=self.scratch/('rejected-'+case)
                try:
                    if case=='object-tuple':
                        value=load_canonical_json(path);value['phases'][0]['objectSha256']='sha256:'+'f'*64
                        write_canonical_json(path,value)
                    elif case=='reference-path':
                        value=load_canonical_json(path);value[next(iter(value))]='../../outside.zip'
                        write_canonical_json(path,value)
                    elif case=='symlink-result':
                        target=self.scratch/'symlink-result.json';target.write_bytes(raw)
                        path.unlink();path.symlink_to(target)
                    else:path.write_bytes(raw+b' ')
                    with self.control_seams(),self.assertRaises((ValueError,OSError)):
                        adapter._capture_completed_contract_handoff(plan,state,handoff,destination,
                            repository_root=self.repository,environ=self.environment,completed_frozen=cap)
                    self.assertFalse(destination.exists(),'invalid controls must not publish a handoff')
                finally:
                    if path.is_symlink():path.unlink()
                    path.write_bytes(raw)
