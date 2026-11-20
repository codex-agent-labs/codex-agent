"""Synthetic control originals exercise policy/semantic boundaries, not CI authority."""
from contextlib import ExitStack, contextmanager
from copy import deepcopy
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "ci"), str(ROOT)]
import sdk_android_evidence_capture as gate
from products import inventory
from legacy_lanes import LANES


def helper(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / ".github/actions/run-ci-lane" / (name + ".py"))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


native_reader = helper("runtime_source_validation")
swift_reader = helper("apple_source_validation")


class SourceValidationReuseTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.plan = dict(repository="codex-agent-labs/codex-agent", event="pull_request", pullRequest=31,
            validationCommit="a"*40, validationTree="b"*40,
            lanes={lane: dict(build=False, test=False, metadata=False) for lane in LANES})
        for lane in gate._SOURCE_WORKFLOWS:
            self.plan["lanes"][lane]["test"] = True
        self.current = gate.products._consumer(self.plan, {"GITHUB_RUN_ID":"42", "GITHUB_RUN_ATTEMPT":"2"})["producer"]
        self.original = {**self.current, "commit":"c"*40, "tree":"d"*40, "runId":40, "runAttempt":1}
        self.publisher = "e"*40
        self.pin = dict(artifactId=8, artifactSha256="sha256:"+"1"*64, runId=7, runAttempt=1,
                        signerCommit="2"*40, sourceCommit="3"*40)
        self.runtime_pin = {**self.pin, "artifactId":18}
        self.policy = dict(schemaVersion=1, kind="completed-source-validations", sdkCompletion=self.pin, runtimeCompletion=self.runtime_pin,
            originals={lane:dict(producer=self.original,workflowSha="f"*40,jobId=10+i,artifactId=20+i,
                artifactSha256="sha256:"+"4"*64,planSha256="sha256:"+"5"*64)
                for i,lane in enumerate(sorted(gate._SOURCE_WORKFLOWS))})
        self.native = dict(schemaVersion=1,kind="completed-frozen-reuse",sdkCompletion=deepcopy(self.pin), **self.runtime_pin)
        self.native_path = self.root/"native.json"
        self.native_path.write_bytes(gate.canonical_json_bytes(self.native))
        self.raw = gate.canonical_json_bytes(self.policy)
        self.absent = False; self.swift_changed = False; self.publisher_missing = False

    def git_inventory(self, root, revision, paths):
        if self.publisher_missing:
            raise subprocess.CalledProcessError(128, ["git", "ls-tree", revision])
        if paths == (gate._SOURCE_POLICY,): return "" if self.absent else "100644\tblob\tfixture\t"+gate._SOURCE_POLICY
        swift = ".github/actions/run-ci-lane/apple_source_validation.py" in paths
        return "changed" if self.swift_changed and swift and revision==self.current["commit"] else "same"

    def git_entry(self, root, *args, **kwargs):
        if self.publisher_missing:raise subprocess.CalledProcessError(128,['git','ls-tree'])
        return b'' if self.absent else b'100644 blob ' + b'0'*40 + b'\t' + gate._SOURCE_POLICY.encode() + b'\0'

    def blob(self, root, revision, path, *, max_bytes):
        self.assertEqual(self.publisher, revision)
        return self.raw if path == gate._SOURCE_POLICY else gate.canonical_json_bytes({"policy":self.native})

    def selection(self, **options):
        return gate.select_source_validation_reuse(self.plan,repository_root=self.root,
            revision=self.current["commit"], trusted_workflow_sha=self.publisher,
            completed_frozen_policy=self.native_path,native_source_tests=True,apple_source_tests=True,**options)

    def git_scope(self):
        stack=ExitStack()
        stack.enter_context(patch.object(inventory,"run_git",side_effect=self.git_entry))
        stack.enter_context(patch.object(inventory,"git_inventory",side_effect=self.git_inventory))
        stack.enter_context(patch.object(inventory,"git_regular_blob_bytes",side_effect=self.blob))
        return stack

    def test_optional_protected_leaf_and_current_recipe_selection(self):
        with self.git_scope():
            self.absent=True; self.assertEqual([],self.selection())
            self.absent=False; self.assertEqual(sorted(gate._SOURCE_WORKFLOWS),self.selection())
            self.swift_changed=True
            self.assertEqual(sorted(l for l in gate._SOURCE_WORKFLOWS if l!='ios-swift-build'),self.selection())
            self.publisher_missing=True
            with self.assertRaises(subprocess.CalledProcessError):self.selection()

    def test_new_native_pin_requires_real_rebind_and_unselected_lanes_are_not_granted(self):
        with self.git_scope():
            self.native['sdkCompletion']['artifactId']+=1
            self.native_path.write_bytes(gate.canonical_json_bytes(self.native))
            self.assertEqual(sorted(lane for lane in gate._SOURCE_WORKFLOWS if lane!='ios-swift-build'),self.selection())
            self.native['artifactId']+=1
            self.native_path.write_bytes(gate.canonical_json_bytes(self.native))
            self.assertEqual([],self.selection())
            self.native['sdkCompletion']=deepcopy(self.pin)
            self.native_path.write_bytes(gate.canonical_json_bytes(self.native))
            self.assertEqual(['ios-swift-build'],self.selection())
            self.native['artifactId']=self.runtime_pin['artifactId']
            self.native_path.write_bytes(gate.canonical_json_bytes(self.native))
            self.plan['lanes']['desktop-windows-x64']['test']=False
            self.assertNotIn('desktop-windows-x64',self.selection())
            self.assertEqual([],gate.select_source_validation_reuse(self.plan,repository_root=self.root,
                revision=self.current['commit'],trusted_workflow_sha=self.publisher))

    def test_policy_and_native_files_cannot_override_protected_git(self):
        supplied=self.root/'supplied.json';supplied.write_bytes(self.raw)
        with self.git_scope():
            self.assertEqual(4,len(self.selection(policy_path=supplied)))
            supplied.write_bytes(self.raw+b' ')
            with self.assertRaisesRegex(ValueError,'protected Git'):self.selection(policy_path=supplied)
            self.native_path.write_bytes(gate.canonical_json_bytes({**self.native,'kind':'caller-success'}))
            with self.assertRaisesRegex(ValueError,'protected publisher'):self.selection()
        for kind in (b'120000 blob ',b'040000 tree '):
            entry=kind+b'0'*40+b'\t'+gate._SOURCE_POLICY.encode()+b'\0'
            with patch.object(inventory,'run_git',return_value=entry):
                with self.assertRaisesRegex(ValueError,'regular'):self.selection()

    def test_policy_rejects_unknown_duplicate_and_malformed_originals(self):
        for mode in ('bool-schema','unknown','job','workflow','producer','digest','duplicate','empty'):
            value=deepcopy(self.policy);lane=next(iter(value['originals']));row=value['originals'][lane]
            if mode=='bool-schema':value['schemaVersion']=True
            elif mode=='unknown':value['originals']['other']=row
            elif mode=='job':row['jobId']=True
            elif mode=='workflow':row['workflowSha']='reuse-authority'
            elif mode=='producer':row['producer']['pullRequest']=32
            elif mode=='digest':row['artifactSha256']='none'
            elif mode=='duplicate':list(value['originals'].values())[1]['jobId']=row['jobId']
            elif mode=='empty':value['originals']={}
            with self.subTest(mode=mode),self.assertRaises(ValueError):
                gate.validate_source_validation_policy(gate.canonical_json_bytes(value))

    def controls(self,lane,producer,plan_sha):
        tuple_={"product":"runtime","component":"linux-x64","phase":"binary","target":"linux-x64",
                "buildKey":"sha256:"+"6"*64,"receiptSha256":"sha256:"+"7"*64,"objectSha256":"sha256:"+"8"*64}
        if lane=='ios-swift-build':
            expected=dict(originalInput=tuple_,frameworkFiles=[],sourceInventory=[],toolchain={
                'xcodeVersion':'26.6','xcodeBuild':'17F113','swiftVersion':'6.3.3'})
            report=gate.canonical_json_bytes(dict(schemaVersion=1,result='passed',target='iosSimulatorArm64',**expected['toolchain']))
            log=b'actual fixed command fixture\n'
            record=dict(schemaVersion=1,kind='retained-swift-source',result='passed',task=swift_reader._TASK,
                producer=producer,planSha256=plan_sha,**expected,executionElapsedNs=1,
                reportSha256=gate.sha256_bytes(report),executionSha256=gate.sha256_bytes(log))
            return expected,dict(zip(swift_reader._NAMES,(gate.canonical_json_bytes(record),report,log)))
        target=lane.removeprefix('desktop-')
        expected=dict(originalInputs=[tuple_],sourceInventory=[],retainedRuntimeValidations=[{'originalProducer':self.original}])
        discovery=b'Example.\n  completeTest\n';execution=b'[  PASSED  ] 1 test.\n'
        record=dict(schemaVersion=1,kind='retained-runtime-source-tests',result='passed',producer=producer,
            planSha256=plan_sha,component='native',target=target,lane=lane,originalInputs=expected['originalInputs'],
            sourceInventory=[],selection=dict(unfiltered=True,discoveredTests=['Example.completeTest'],passedTests=1),
            runtimeObservation=dict(host=target,runnerOs=native_reader.HOSTS[target][2],runnerArch=native_reader.HOSTS[target][3]),
            executionElapsedNs=1,discoverySha256=gate.sha256_bytes(discovery),executionSha256=gate.sha256_bytes(execution))
        return expected,{'retained-source-tests.json':gate.canonical_json_bytes(record),'discovery.log':discovery,'execution.log':execution}

    def exercise_controls(self,change=None):
        lanes=tuple(sorted(gate._SOURCE_WORKFLOWS));reused=deepcopy(self.policy['originals'])
        expected={};archives={};observed={'run':{'id':40,'run_attempt':1},'jobs':[]}
        for lane in lanes:
            row=reused[lane];before,members=self.controls(lane,self.original,row['planSha256']);expected[lane]=before
            if change in ('tuple','source') and lane=='ios-swift-build':
                changed=gate.load_json_bytes(members[swift_reader._NAMES[0]])
                if change=='tuple':changed['originalInput']['buildKey']='sha256:'+'0'*64
                else:changed['sourceInventory']=[{'path':'new source'}]
                members[swift_reader._NAMES[0]]=gate.canonical_json_bytes(changed)
            data=io.BytesIO()
            with zipfile.ZipFile(data,'w') as archive:
                for name,raw in members.items():archive.writestr(name,raw)
                if change=='extra':archive.writestr('unselected.bin',b'x')
            archives[row['artifactId']]=data.getvalue();row['artifactSha256']=gate.sha256_bytes(data.getvalue())
            if change=='digest':row['artifactSha256']='sha256:'+'0'*64
            job=('product-validation / retained-apple-source / retained-swift-simulator' if lane=='ios-swift-build' else
                'product-validation / retained-native-source / retained-native-'+lane.removeprefix('desktop-'))
            observed['jobs'].append(dict(name=job,id=row['jobId'],status='completed',conclusion='success'))
        if change=='job':observed['jobs'][0]['id']+=100
        downloads=[];current_consumer={'kind':'ci','producer':self.current};calls=[]
        def state(native,consumer,root,target=None):
            self.assertEqual(current_consumer,consumer);calls.append(target)
            result=deepcopy(expected['ios-swift-build' if target is None else 'desktop-'+target])
            if change=='late' and len(calls)>4:result['sourceInventory']=[{}]
            return result
        def metadata(identifier,digest,name,producer,run,token):
            self.assertEqual(self.original,producer);self.assertEqual(40,run['id'])
            return dict(id=identifier,size_in_bytes=len(archives[identifier]))
        def download(artifact,producer,run,token,**kwargs):
            self.assertEqual(1024*1024,kwargs['limit']);downloads.append(artifact['id'])
            kwargs['destination'].write_bytes(archives[artifact['id']])
        with patch.object(native_reader,'_native_merge_inputs',side_effect=state), \
                patch.object(swift_reader,'_expected',side_effect=state), \
                patch.object(gate.products,'_contract_ci_upload_metadata',side_effect=metadata), \
                patch.object(gate.products,'_require_artifact_job_window',side_effect=ValueError('expired/window') if change=='window' else None), \
                patch.object(gate.products,'_reuse_contract_ci_upload',side_effect=download), \
                patch.object(gate.products,'paginated_items',side_effect=AssertionError('originals require no listing')):
            result=gate._observed_source_validations(object(),lanes=lanes,native_reader=native_reader,
                swift_reader=swift_reader,plan_sha256='sha256:'+'9'*64,root=self.root,consumer=current_consumer,
                observations={(40,1):observed},token='fixture',listing=[],reused=reused,policy_sha256=gate.sha256_bytes(self.raw))
        self.assertEqual(4,len(downloads));self.assertEqual(8,len(calls))
        self.assertTrue(all(r['original']['producer']==self.original for r in result.values()))
        self.assertTrue(all(r['original']['planSha256']=='sha256:'+'5'*64 for r in result.values()))
        return result

    def test_all_four_historical_controls_recheck_current_inputs_keep_original_producer(self):
        self.assertEqual(set(gate._SOURCE_WORKFLOWS),set(self.exercise_controls()))

    def test_wrong_tuple_source_job_window_transport_or_late_inputs_fail(self):
        for change in ('tuple','source','job','window','extra','digest','late'):
            with self.subTest(change=change),self.assertRaises(ValueError):self.exercise_controls(change)

    def test_reused_native_only_gate_batches_original_jobs_and_publishes_after_owner_exit(self):
        import reuse_qualification
        lane='desktop-linux-x64';row=self.policy['originals'][lane]
        for name in gate._SOURCE_WORKFLOWS:self.plan['lanes'][name]['test']=name==lane
        self.plan.update(schemaVersion=1,mergeReady=True,remoteBuildAuthorized=True,
            remoteBuildAuthorizationReason='pull-request-final',androidEvidenceRequired=False)
        plan_path=self.root/'impact-plan.json';plan_path.write_bytes(gate.canonical_json_bytes(self.plan))
        env=dict(GITHUB_ACTIONS='true',GITHUB_JOB='merge-gate',GITHUB_TOKEN='fixture',GITHUB_RUN_ID='42',
            GITHUB_RUN_ATTEMPT='2',GITHUB_SHA=self.current['commit'],GITHUB_REPOSITORY=self.current['repository'],
            GITHUB_EVENT_NAME='pull_request')
        expected,members=self.controls(lane,self.original,row['planSha256'])
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as archive:
            for name,raw in members.items():archive.writestr(name,raw)
        raw=stream.getvalue();row['artifactSha256']=gate.sha256_bytes(raw)
        self.raw=gate.canonical_json_bytes(self.policy)
        job='product-validation / retained-native-source / retained-native-linux-x64'
        observed={'run':{'id':40,'run_attempt':1},'jobs':[dict(id=row['jobId'],name=job,status='completed',conclusion='success')]}
        live=False;late=False;cap=object()
        @contextmanager
        def authority(args):
            nonlocal live
            self.assertEqual(self.native_path,args['completed_frozen_policy']);live=True
            try:yield {'completed_frozen':cap}
            finally:
                live=False
                if late:raise ValueError('late native owner failure')
        def state(native,consumer,root,target):
            self.assertIs(cap,native);self.assertTrue(live)
            self.assertEqual(self.current,consumer['producer']);self.assertEqual('linux-x64',target)
            return deepcopy(expected)
        reader=SimpleNamespace(selected_native_source_targets=lambda plan,enabled:('linux-x64',),
            _native_merge_inputs=state,_validate_native_source_controls=native_reader._validate_native_source_controls)
        def observe(producers,**kwargs):
            self.assertEqual({'native-source-linux-x64':self.original},producers)
            self.assertEqual({'native-source-linux-x64':job},kwargs['jobs_by_phase'])
            self.assertEqual({'native-source-linux-x64':dict(path=gate._SOURCE_WORKFLOWS[lane],sha=row['workflowSha'])},
                             kwargs['trusted_workflows_by_phase'])
            return [observed]
        receipts=self.root/'receipts';receipts.mkdir()
        with self.git_scope(), \
                patch.object(gate.products,'_validate_plan',return_value=self.plan), \
                patch.object(gate.products,'_git_value',side_effect=lambda r,c,v:self.current['tree' if 'tree' in v else 'commit']), \
                patch.object(gate.products,'_observe_ci_producer_jobs',side_effect=observe) as observer, \
                patch.object(gate.products,'paginated_items',side_effect=AssertionError('all originals: no listing')), \
                patch.object(gate.products,'_contract_ci_upload_metadata',return_value={'id':row['artifactId'],'size_in_bytes':len(raw)}), \
                patch.object(gate.products,'_require_artifact_job_window'), \
                patch.object(gate.products,'_reuse_contract_ci_upload',side_effect=lambda *a,**k:k['destination'].write_bytes(raw)), \
                patch.object(reuse_qualification,'completed_frozen_options',authority), \
                patch.object(importlib.util,'spec_from_file_location',return_value=SimpleNamespace(loader=SimpleNamespace(exec_module=lambda m:None))), \
                patch.object(importlib.util,'module_from_spec',return_value=reader):
            args=dict(repository_root=self.root,trusted_workflow_sha=self.publisher,artifact_id=None,artifact_sha256=None,
                contribution_sha256=None,environ=env,native_source_tests=True,completed_frozen_policy=self.native_path,
                reused_source_lanes=[lane])
            destination=self.root/'accepted'
            result=gate.aggregate_retained_validation(plan_path,receipts,destination,**args)
            self.assertFalse(live);self.assertEqual(1,observer.call_count)
            self.assertEqual(self.original,result['nativeSourceTests'][lane]['original']['producer'])
            self.assertTrue((destination/'current-validation-contributions.json').is_file())
            late=True;denied=self.root/'denied'
            with self.assertRaisesRegex(ValueError,'late native owner'):
                gate.aggregate_retained_validation(plan_path,receipts,denied,**args)
            self.assertFalse(denied.exists());self.assertFalse(live)
            wrong=self.root/'wrong-scheduling'
            with self.assertRaisesRegex(ValueError,'scheduling differs'):
                gate.aggregate_retained_validation(plan_path,receipts,wrong,**{**args,'reused_source_lanes':[]})
            self.assertFalse(wrong.exists())


if __name__=='__main__':unittest.main()
