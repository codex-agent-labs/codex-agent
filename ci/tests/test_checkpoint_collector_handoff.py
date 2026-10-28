"""Whole SDK collector handoff; reuse the real signed Contract/Core fixture."""
from pathlib import Path
from copy import copy
import shutil,time
from unittest.mock import patch

import product_reuse as adapter
import sdk_workflow as workflow
from ci.tests.test_checkpoint_collector_execution import CheckpointCollectorExecutionTest,CORE,CHILD,WORKER,PIN
from products.inventory import load_canonical_json,regular_file_inventory,write_canonical_json
import reuse_qualification as native


class CheckpointCollectorHandoffTest(CheckpointCollectorExecutionTest):
    measurements=[]

    def test_outer_collector_handoff_and_next_consumer_do_not_reopen_qualified_contract_bodies(self):
        cap,plan,resumed,_=self.prepared()
        original=self.scratch/'original';original.mkdir()
        shutil.move(plan.parents[1],original/'product-resume-inputs')
        shutil.move(resumed,original/'product-resume-state')
        plan=original/'product-resume-inputs/plan/impact-plan.json'
        discovery=original/'product-resume-state'
        with self.control_seams():
            state=adapter._verified_product_state(plan,discovery,discovery,self.repository,
                self.environment,None,completed_frozen=cap)
        ready=state.prior_ready_plans[CORE];obj,body=self.new_upload(ready)
        old_bytes=sum(path.stat().st_size for path in state.sources.values())
        destination=self.scratch/'collected';start=time.perf_counter_ns()
        with self.control_seams(),self.reads(state.sources.values()) as opened,self.official(ready,body) as api:
            value=workflow.collect(original,destination,self.scratch/'collect-output',wave=11,family='core-binary',
                trusted_workflow_sha=PIN,sdk_worker_workflow_path=CHILD,sdk_worker_job_name=WORKER,
                repository_root=self.repository,environ=self.environment,token='synthetic-token',
                completed_frozen=cap,checkpoint_controls=True)
            handoff=destination/'handoff'
            replay=adapter._verified_product_state(handoff/'product-resume-inputs/plan/impact-plan.json',
                handoff/'product-resume-state',handoff/'runtime-state',self.repository,self.environment,None,
                sdk_original_workflow_sha=PIN,completed_frozen=cap)
        measurement={'oldObjectBytes':old_bytes,'newUploadBytes':len(body),'oldObjectOpens':len(opened),
            'oldOperations':opened,'elapsedNs':time.perf_counter_ns()-start,
            'selectedTargetJobs':len(replay.prior_ready_plans)}
        type(self).measurements.append(measurement)
        self.assertTrue(value['fullReuse']);self.assertEqual({},replay.prior_ready_plans)
        phase=next(row for row in value['phases'] if adapter._identity(row)==CORE)
        self.assertEqual(obj['receiptSha256'],phase['receiptSha256'])
        self.assertEqual(obj['objectSha256'],phase['objectSha256'])
        self.assertEqual(1,api[2].call_count)
        self.assertEqual([],opened,measurement)

    def test_forwarding_preserves_fallback_controls_and_rejects_mutation_or_unsafe_sources(self):
        cap,_,resumed,state=self.prepared()
        spec,_=cap._values()
        limited=native.CompletedFrozenReuse(spec,[load_canonical_json(self.receipts[name])
            for name in ('binary','package','validation','metadata')],native._COMPLETED_FROZEN,revision=self.commit)
        no_members=copy(cap);no_members._sdk=None
        self.assertTrue(no_members.deferred_objects(include_contract=True))
        self.assertIsNone(no_members.contract_members())
        before=regular_file_inventory(resumed)
        for name,authority in (('ordinary',None),('limited',limited),('no-native-members',no_members)):
            destination=self.scratch/name
            with self.reads(state.sources.values()) as opened:
                adapter.snapshot_reuse_inputs(resumed,destination,completed_frozen=authority)
            self.assertTrue(opened);self.assertEqual(before,regular_file_inventory(destination))
        request=resumed/'reuse-wave-request.json';raw=request.read_bytes()
        for case in ('identity','control-path','symlink','overlap','during-copy'):
            with self.subTest(case=case):
                destination=self.scratch/('guard-'+case);old=next(iter(state.sources.values()));old_raw=None
                try:
                    value=load_canonical_json(request)
                    if case=='identity':value['availableObjects'][0]['objectSha256']='sha256:'+'f'*64
                    if case=='control-path':
                        for row in value['availableObjects']:row['objectPath']='authenticated-contract/contract-input/contract-manifest.json'
                    write_canonical_json(request,value)
                    if case=='control-path':
                        adapter.snapshot_reuse_inputs(resumed,destination,completed_frozen=cap)
                        self.assertEqual(regular_file_inventory(resumed),regular_file_inventory(destination))
                        continue
                    if case=='symlink':
                        old_raw=old.read_bytes();target=self.scratch/'safe-original.zip';target.write_bytes(old_raw)
                        old.unlink();old.symlink_to(target)
                    if case=='overlap':destination=resumed/'nested-output'
                    import runtime_reference_transport as transport
                    copy_file=transport._copy_exact
                    def copying(*args,**kwargs):
                        result=copy_file(*args,**kwargs)
                        if case=='during-copy':request.write_bytes(raw+b' ')
                        return result
                    with patch.object(transport,'_copy_exact',side_effect=copying),self.assertRaises((ValueError,OSError)):
                        adapter.snapshot_reuse_inputs(resumed,destination,completed_frozen=cap)
                    self.assertFalse(destination.exists())
                finally:
                    request.write_bytes(raw)
                    if old_raw is not None:old.unlink();old.write_bytes(old_raw)
