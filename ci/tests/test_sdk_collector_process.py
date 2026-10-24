"""One native/private context across collector capture and execution seams."""
from contextlib import contextmanager
from pathlib import Path
import json,os,unittest
from unittest.mock import patch

import sdk_workflow as workflow
import reuse_qualification as qualification
import product_reuse as products
from products.inventory import canonical_json_bytes
from ci.tests.test_sdk_checkpoint_collectors import CheckpointCollectorTest


class CollectorProcessTest(unittest.TestCase):
    def setUp(self):
        self.fixture=CheckpointCollectorTest();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.fixture.prepare(nested=True,new=True);self.root=self.fixture.f.root
        self.output=self.root/'runner-output';self.output.touch()
        self.plan=self.root/'caller-plan.json';self.plan.write_text('{}\n')
        self.events=[];self.calls=0;self.cap=None;self.failure=None
        self.arguments=['collect','--capture-plan',str(self.plan),'--capture-destination',str(self.root/'captured'),
            '--capture-artifact-id','101','--capture-artifact-sha256','sha256:'+'a'*64,
            '--capture-state-wave','0','--capture-sdk-state-wave','10',
            '--destination',str(self.root/'next'),'--repository-root',str(self.root),
            '--trusted-workflow-sha','c'*40,'--github-output',str(self.output),'--wave','11','--family','core-binary',
            '--completed-frozen-policy',str(self.root/'policy'),'--sdk-checkpoint-owner',str(self.root/'owner'),
            '--sdk-checkpoint','{"fixture":"selection"}','--checkpoint-controls']

    @contextmanager
    def boundaries(self):
        metadata=workflow.metadata_admission_options
        @contextmanager
        def native(arguments):
            self.calls+=1;self.events.append('authenticate')
            self.assertEqual(self.plan,arguments['plan'])
            for name in ('completed_frozen_policy','sdk_checkpoint_owner','sdk_checkpoint'):
                self.assertIsNotNone(arguments.pop(name))
            # The outer CLI policy/plan entrance is a fixture. Actual protected
            # checkpoint/native-wrapper/private-witness validation still runs.
            with self.fixture.open() as witness:
                self.cap=self.fixture.c.capability(witness)
                try:
                    yield {'completed_frozen':self.cap}
                    if self.failure=='late-native':raise ValueError('late native policy check failed')
                finally:self.events.append('native-exit')
        @contextmanager
        def policies(arguments):
            self.events.append('policies')
            with metadata(arguments) as value:yield value
        def capture(**arguments):
            self.events.append('capture');self.assertIs(self.cap,arguments['completed_frozen'])
            self.cap.check_consumer(self.fixture.c.consumer)
            self.assertEqual(self.plan,arguments['plan']);self.assertEqual(101,arguments['artifact_id'])
            self.assertEqual(10,arguments['sdk_state_wave']);self.assertEqual(self.output,arguments['github_output_path'])
            if self.failure=='capture':raise ValueError('capture gate failed')
            return {'input_root':self.root/'captured/original'}
        def collect(**arguments):
            self.events.append('collect');self.assertIs(self.cap,arguments['completed_frozen'])
            self.cap.check_consumer(self.fixture.c.consumer)
            self.assertEqual(self.root/'captured/original',arguments['input_root'])
            self.assertNotIn('plan',arguments);self.assertTrue(arguments['checkpoint_controls'])
            if self.failure=='collect':raise ValueError('new result failed')
            return {'fixture':'collection body stub'}
        with patch.dict(os.environ,{'GITHUB_OUTPUT':str(self.output),'GITHUB_TOKEN':'synthetic'}), \
                patch.object(qualification,'completed_frozen_options',side_effect=native), \
                patch.object(workflow,'metadata_admission_options',side_effect=policies), \
                patch.object(workflow,'capture_transport',side_effect=capture),patch.object(workflow,'collect',side_effect=collect):
            yield

    def test_one_live_native_context_covers_capture_then_policy_selection_and_collection(self):
        with self.boundaries():
            self.assertEqual({'fixture':'collection body stub'},workflow._workflow_main(self.arguments))
        self.assertEqual(1,self.calls)
        self.assertEqual(['authenticate','capture','policies','collect','native-exit'],self.events)
        with self.assertRaisesRegex(ValueError,'closed'):self.cap.completed_phases()

    def test_incomplete_conflicting_or_unsafe_capture_options_reject_before_authentication(self):
        for case in ('partial','both-sources','overlap','wrong-output','missing-root','orphan-option'):
            with self.subTest(case=case):
                arguments=list(self.arguments)
                if case in ('partial','missing-root'):
                    flag='--capture-artifact-id' if case=='partial' else '--repository-root'
                    i=arguments.index(flag);del arguments[i:i+2]
                elif case=='both-sources':arguments+=['--input-root',str(self.root/'other')]
                elif case=='overlap':arguments[arguments.index('--capture-destination')+1]=str(self.root/'next/nested')
                elif case=='wrong-output':arguments[arguments.index('--github-output')+1]=str(self.root/'not-runner')
                else:
                    i=arguments.index('--capture-plan');del arguments[i:i+2]
                    arguments+=['--input-root',str(self.root/'other')]
                with self.boundaries(),self.assertRaises(SystemExit) as raised:workflow._workflow_main(arguments)
                self.assertEqual(2,raised.exception.code)
        self.assertEqual([],self.events);self.assertEqual(0,self.calls)

    def test_capture_collection_and_late_native_failure_propagate_and_close_the_capability(self):
        for case in ('capture','collect','late-native'):
            with self.subTest(case=case):
                self.failure=case;self.events=[]
                with self.boundaries(),self.assertRaises(SystemExit) as raised:workflow._workflow_main(self.arguments)
                self.assertEqual(2,raised.exception.code)
                self.assertEqual('native-exit',self.events[-1])
                self.assertEqual(case!='capture','collect' in self.events)
                with self.assertRaisesRegex(ValueError,'closed'):self.cap.completed_phases()
        self.assertEqual(3,self.calls)

    def test_real_policy_entrance_uses_caller_plan_once_and_checks_it_after_collection(self):
        f=self.fixture.f
        owner=self.root/'owner';owner.write_bytes(canonical_json_bytes(f.policy))
        policy=self.root/'policy';policy.write_bytes(canonical_json_bytes({'schemaVersion':1,'kind':'completed-frozen-reuse',
            'consumerCommit':'c'*40,'verifierPolicySha256':'sha256:'+'a'*64,
            **f.policy['bootstrap'],'sdkCompletion':f.policy['bootstrap']}))
        arguments=list(self.arguments);arguments[arguments.index('--sdk-checkpoint')+1]=json.dumps(self.fixture.output)
        environment={'GITHUB_REPOSITORY':qualification.REPOSITORY,'GITHUB_EVENT_NAME':'pull_request',
            'GITHUB_REF':'refs/pull/31/merge','GITHUB_SHA':f.producer['commit'],
            'GITHUB_RUN_ID':str(f.producer['runId']),'GITHUB_RUN_ATTEMPT':str(f.producer['runAttempt']),
            'GITHUB_JOB':'sdk-collect-11','GITHUB_TOKEN':'synthetic','GITHUB_OUTPUT':str(self.output)}
        def blob(root,revision,path,**kwargs):
            self.assertEqual(f.policy['collectorWorkflowSha'],revision)
            return {'.github/workflows/product-validation.yml':self.fixture.parent,
                '.github/workflows/sdk-core-binary-validation.yml':self.fixture.child}[path]
        def download(artifact,token):
            self.assertEqual(self.fixture.output['native']['artifactId'],artifact['id']);return f.raw
        def fetch(destination,**kwargs):
            self.assertEqual(f.producer['commit'],kwargs['revision'])
            self.cap=self.fixture.c.capability(kwargs['_checkpoint']);return self.cap,{}
        for change in (False,True):
            with self.subTest(change=change):
                self.plan.write_text(f.spec['sourcePlan'])
                def capture(**kwargs):
                    self.assertIs(self.cap,kwargs['completed_frozen']);self.assertEqual(self.plan,kwargs['plan'])
                    return {'input_root':self.root/'captured/original'}
                def collect(**kwargs):
                    self.assertIs(self.cap,kwargs['completed_frozen']);self.cap.check_consumer(self.fixture.c.consumer)
                    if change:self.plan.write_text('{}\n')
                    return {'fixture':'actual policy, collection body stub'}
                with self.fixture.chain.boundaries(),patch.dict(os.environ,environment,clear=True), \
                        patch('products.inventory.git_regular_blob_bytes',side_effect=blob), \
                        patch.object(products,'download_artifact',side_effect=download) as downloads, \
                        patch.object(products,'_validate_plan',return_value=json.loads(f.spec['sourcePlan'])), \
                        patch.object(qualification,'fetch_completed_frozen',side_effect=fetch) as authenticated, \
                        patch.object(workflow,'capture_transport',side_effect=capture),patch.object(workflow,'collect',side_effect=collect):
                    if change:
                        with self.assertRaises(SystemExit) as failed:workflow._workflow_main(arguments)
                        self.assertEqual(2,failed.exception.code)
                    else:self.assertEqual({'fixture':'actual policy, collection body stub'},workflow._workflow_main(arguments))
                    self.assertEqual(1,authenticated.call_count);self.assertEqual(1,downloads.call_count)
                with self.assertRaisesRegex(ValueError,'closed'):self.cap.completed_phases()


from ci.tests.test_checkpoint_collector_export import CheckpointCollectorExportTest


class CollectorProcessExecutionTest(CheckpointCollectorExportTest):
    measurements=[]
    export_measurements=[]

    def test_combined_cli_keeps_actual_collection_export_and_next_replay_at_zero_old_opens(self):
        original_collect=workflow.collect;events=[]
        def combined(input_root,destination,output,**arguments):
            cap=arguments['completed_frozen'];plan=input_root/'product-resume-inputs/plan/impact-plan.json'
            @contextmanager
            def native(values):
                events.append('authenticate');self.assertEqual(plan,values['plan'])
                for name in ('completed_frozen_policy','sdk_checkpoint_owner','sdk_checkpoint'):values.pop(name,None)
                yield {'completed_frozen':cap}
                events.append('native-exit')
            def capture(**values):
                events.append('capture');self.assertIs(cap,values['completed_frozen'])
                self.assertEqual(plan,values['plan'])
                # Existing full collector fixture starts with authenticated input
                # files. Transport/native-policy entrance remain explicit seams.
                return {'input_root':input_root}
            def collect(**values):
                events.append('collect');self.assertIs(cap,values['completed_frozen'])
                return original_collect(**values)
            argv=['collect','--capture-plan',str(plan),'--capture-destination',str(self.scratch/'capture-request'),
                '--capture-artifact-id','101','--capture-artifact-sha256','sha256:'+'a'*64,
                '--capture-sdk-state-wave','10','--destination',str(destination),
                '--repository-root',str(self.repository),'--github-output',str(output),'--family',arguments['family'],
                '--wave',str(arguments['wave']),'--trusted-workflow-sha',arguments['trusted_workflow_sha'],
                '--sdk-worker-workflow-path',arguments['sdk_worker_workflow_path'],
                '--sdk-worker-job-name',arguments['sdk_worker_job_name'],'--checkpoint-controls',
                '--completed-frozen-policy',str(self.scratch/'policy')]
            with patch.dict(os.environ,{**self.environment,'GITHUB_OUTPUT':str(output),'GITHUB_TOKEN':'synthetic-token'}), \
                    patch.object(qualification,'completed_frozen_options',side_effect=native), \
                    patch.object(workflow,'capture_transport',side_effect=capture), \
                    patch.object(workflow,'collect',side_effect=collect):
                return workflow._workflow_main(argv)
        with patch.object(workflow,'collect',side_effect=combined):
            super().test_actual_collector_export_resolution_and_next_consumer_leave_old_bodies_unopened()
        self.assertEqual(['authenticate','capture','collect','native-exit'],events)
