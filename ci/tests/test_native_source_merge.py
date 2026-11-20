from contextlib import ExitStack, contextmanager
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'ci'),str(ROOT)]

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value

gate=module('native_gate_candidate',ROOT/'ci/sdk_android_evidence_capture.py')
reader=module('native_reader_candidate',ROOT/'.github/actions/run-ci-lane/runtime_source_validation.py')
import reuse_qualification
from products import inventory
from products.registry import PhaseInstanceId, phase_instance_dependencies
from products.restore import PHASE_PLAN_KEYS
from legacy_lanes import LANES

class NativeMergeTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()
        self.plan=self.root/'impact-plan.json'
        self.value=dict(schemaVersion=1,repository='codex-agent-labs/codex-agent',event='pull_request',pullRequest=31,
            validationCommit='a'*40,validationTree='b'*40,mergeReady=True,remoteBuildAuthorized=True,
            remoteBuildAuthorizationReason='pull-request-final',androidEvidenceRequired=False,
            lanes={lane:dict(build=False,test=False,metadata=False) for lane in LANES})
        self.value['lanes']['desktop-linux-x64']['test']=True
        self.plan.write_bytes(gate.canonical_json_bytes(self.value))
        self.env=dict(GITHUB_ACTIONS='true',GITHUB_JOB='merge-gate',GITHUB_TOKEN='fixture',
            GITHUB_REPOSITORY=self.value['repository'],GITHUB_EVENT_NAME='pull_request',GITHUB_SHA='a'*40,
            GITHUB_RUN_ID='21',GITHUB_RUN_ATTEMPT='2')
        self.producer=gate.products._consumer(self.value,self.env)['producer']
        self.original={**self.producer,'commit':'c'*40,'tree':'d'*40,'runId':10,'runAttempt':1}
        self.cap=object.__new__(reuse_qualification.CompletedFrozenReuse)
        self.source=[dict(relativePath='codex-agent-runtime-desktop/src/commonTest/kotlin/Test.kt',bytes=4,sha256='sha256:'+'e'*64)]
        roots=[PhaseInstanceId('runtime','linux-x64',phase,'linux-x64') for phase in ('binary','package','validation')]
        roots += [PhaseInstanceId('runtime',name,'validation','linux-x64') for name in ('jvm','node-js','node-wasm')]
        identities=set(roots)
        for identity in roots:identities.update(phase_instance_dependencies(identity))
        self.records={i:{**dict(zip(('product','component','phase','target'),(i.product,i.component,i.phase,i.target))),
            'buildKey':'sha256:'+'1'*64,'receiptSha256':'sha256:'+'2'*64,'objectSha256':'sha256:'+'3'*64} for i in identities}
        output=dict(kind='validation-runner',relativePath='outputs/tests/native.kexe',bytes=3,sha256='sha256:'+'4'*64)
        self.receipts={i:{**{k:v for k,v in row.items() if k not in ('receiptSha256','objectSha256')},
            'schemaVersion':1,'producer':self.original,'outputs':[output],
            'inputs':dict(inventory=self.source,toolchainProfileDigest='sha256:'+'5'*64,flagsDigest='sha256:'+'6'*64,outputSchemaVersion=1)}
            for i,row in self.records.items()}
        self.live=False;self.late=False;self.downloads=[]
        p=self.root/'.github/actions/run-ci-lane/runtime_source_validation.py';p.parent.mkdir(parents=True)
        shutil.copyfile(ROOT/'.github/actions/run-ci-lane/runtime_source_validation.py',p)

    def envelope(self,row):
        if not self.live or row != self.records.get(gate.products._identity(row)):raise ValueError('fixture authority or exact tuple')
        return dict(receipt=self.receipts[gate.products._identity(row)],receiptSha256=row['receiptSha256'],objectSha256=row['objectSha256'])

    def current(self,consumer):
        if not self.live or consumer != {'kind':'ci','producer':self.producer}:raise ValueError('fixture current consumer/lifetime')

    def scopes(self):
        stack=ExitStack()
        stack.enter_context(patch.object(reuse_qualification.CompletedFrozenReuse,'check_consumer',side_effect=self.current))
        stack.enter_context(patch.object(reuse_qualification.CompletedFrozenReuse,'_values',return_value=({},self.records)))
        stack.enter_context(patch.object(reuse_qualification.CompletedFrozenReuse,'envelope',side_effect=self.envelope))
        def phase(identity,values,envelope,upstream):
            self.assertEqual({gate.products._identity(x['receipt']) for x in upstream},set(phase_instance_dependencies(identity)))
            return {key:envelope['receipt'][key] for key in PHASE_PLAN_KEYS}
        stack.enter_context(patch.object(reuse_qualification.CompletedFrozenReuse,'phase_plan',side_effect=phase))
        stack.enter_context(patch.object(gate.products,'_versions',return_value={'runtime-release':'fixture'}))
        for owner in (inventory,reader):
            stack.enter_context(patch.object(owner,'git_inventory',return_value='fixture'))
            stack.enter_context(patch.object(owner,'git_inventory_paths',return_value=[r['relativePath'] for r in self.source]))
            stack.enter_context(patch.object(owner,'git_file_inventory',return_value=self.source))
        return stack

    def controls(self):
        expected=reader._native_merge_inputs(self.cap,{'kind':'ci','producer':self.producer},self.root,'linux-x64')
        discovery=b'Example.\n  completeTest\n';execution=b'[  PASSED  ] 1 test.\n'
        record=dict(schemaVersion=1,kind='retained-runtime-source-tests',result='passed',producer=self.producer,
            planSha256=gate.sha256_bytes(self.plan.read_bytes()),component='native',target='linux-x64',lane='desktop-linux-x64',
            originalInputs=expected['originalInputs'],sourceInventory=expected['sourceInventory'],
            selection=dict(unfiltered=True,discoveredTests=['Example.completeTest'],passedTests=1),
            runtimeObservation=dict(host='linux-x64',runnerOs='Linux',runnerArch='X64'),executionElapsedNs=1,
            discoverySha256=gate.sha256_bytes(discovery),executionSha256=gate.sha256_bytes(execution))
        return expected,record,dict(discovery_log=discovery,execution_log=execution)

    def test_exact_controls_current_original_host_and_complete_suite(self):
        self.live=True
        with self.scopes():
            expected,record,logs=self.controls()
            members={'retained-source-tests.json':gate.canonical_json_bytes(record),'discovery.log':logs['discovery_log'],'execution.log':logs['execution_log']}
            self.assertEqual(record,reader._validate_native_source_controls(members,self.producer,record['planSha256'],'linux-x64',expected))
            self.assertTrue(all(x['originalProducer']==self.original for x in expected['retainedRuntimeValidations']))
            for field in ('producer','planSha256','originalInputs','sourceInventory','selection','runtimeObservation','executionElapsedNs'):
                changed=deepcopy(record);changed[field]=None
                bad={**members,'retained-source-tests.json':gate.canonical_json_bytes(changed)}
                with self.subTest(field=field),self.assertRaises((ValueError,TypeError)):
                    reader._validate_native_source_controls(bad,self.producer,record['planSha256'],'linux-x64',expected)
            with self.assertRaises(ValueError):reader._validate_native_source_controls({**members,'execution.log':b'[  PASSED  ] 0 tests.\n'},self.producer,record['planSha256'],'linux-x64',expected)
            identity=PhaseInstanceId('runtime','node-wasm','validation','linux-x64')
            self.records.pop(identity)
            with self.assertRaises(ValueError):reader._native_merge_inputs(self.cap,{'kind':'ci','producer':self.producer},self.root,'linux-x64')

    def exercise(self,change):
        self.live=True
        expected,record,logs=self.controls()
        if change=='original':record['originalInputs'][0]['objectSha256']='sha256:'+'0'*64
        if change=='source':record['sourceInventory']=[]
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as archive:
            archive.writestr('retained-source-tests.json',gate.canonical_json_bytes(record))
            archive.writestr('discovery.log',logs['discovery_log']);archive.writestr('execution.log',logs['execution_log'])
            if change=='extra':archive.writestr('unwanted',b'x')
        raw=stream.getvalue();digest=gate.sha256_bytes(raw)
        if change=='digest':digest='sha256:'+'0'*64
        name=f"codex-agent-retained-native-source-linux-x64-{self.producer['tree']}-attempt-2"
        artifact=dict(id=22,name=name,digest=digest,size_in_bytes=len(raw),expired=False,
            archive_download_url='https://api.github.com/repos/codex-agent-labs/codex-agent/actions/artifacts/22/zip',
            workflow_run=dict(id=21,head_sha='9'*40),created_at='2026-11-01T10:03:00Z')
        if change=='window':artifact['created_at']='2026-11-01T09:59:00Z'
        if change=='size':artifact['size_in_bytes']=1024*1024+1
        job='product-validation / retained-native-source / retained-native-linux-x64'
        observed=dict(run=dict(id=21,head_sha='9'*40,status='in_progress'),jobs=[dict(id=5,name=job,
            status='completed',conclusion='success',started_at='2026-11-01T10:00:00Z',completed_at='2026-11-01T10:05:00Z')])
        @contextmanager
        def authority(args):
            self.assertEqual(self.root/'policy.json',args['completed_frozen_policy'])
            self.live=True
            try:yield {'completed_frozen':self.cap}
            finally:
                self.live=False
                if change=='owner-exit':raise ValueError('late native owner failure')
        def download(*args,**kwargs):
            self.downloads.append(kwargs['limit']);kwargs['destination'].write_bytes(raw)
            if change=='plan':self.plan.write_bytes(self.plan.read_bytes()+b' ')
        def observe(producers,**kwargs):
            self.assertEqual({'native-source-linux-x64':self.producer},producers)
            self.assertEqual({'native-source-linux-x64':job},kwargs['jobs_by_phase'])
            self.assertEqual({'native-source-linux-x64':dict(path='.github/workflows/desktop-runtime-evidence.yml',sha='4'*40)},kwargs['trusted_workflows_by_phase'])
            return [observed]
        receipts=self.root/'receipts';receipts.mkdir(exist_ok=True)
        destination=self.root/('accepted-'+change)
        with patch.object(gate.products,'_validate_plan',return_value=self.value), \
                patch.object(gate.products,'_git_value',side_effect=lambda r,c,v:self.producer['tree' if 'tree' in v else 'commit']), \
                patch.object(gate.products,'_observe_ci_producer_jobs',side_effect=observe), \
                patch.object(gate.products,'paginated_items',return_value=[artifact,artifact] if change=='duplicate' else [artifact]), \
                patch.object(gate.products,'api_json',return_value=artifact), \
                patch.object(gate.products,'_reuse_contract_ci_upload',side_effect=download), \
                patch.object(reuse_qualification,'completed_frozen_options',authority):
            args=dict(repository_root=self.root,trusted_workflow_sha='4'*40,artifact_id=None,artifact_sha256=None,
                contribution_sha256=None,environ=self.env,native_source_tests=True,completed_frozen_policy=self.root/'policy.json')
            if change=='none':
                result=gate.aggregate_retained_validation(self.plan,receipts,destination,**args)
                self.assertFalse(self.live);self.assertNotIn('canonical',result)
                self.assertEqual({'desktop-linux-x64'},set(result['nativeSourceTests']))
                self.assertTrue((destination/'current-validation-contributions.json').is_file())
            else:
                with self.assertRaises(ValueError):gate.aggregate_retained_validation(self.plan,receipts,destination,**args)
                self.assertFalse(destination.exists())

    def test_authenticated_transport_and_owner_exit_before_publication(self):
        with self.scopes():
            for change in ('none','window','size','duplicate','extra','digest','source','original','plan','owner-exit'):
                with self.subTest(change=change):
                    self.plan.write_bytes(gate.canonical_json_bytes(self.value));self.exercise(change)
        self.assertTrue(all(limit==1024*1024 for limit in self.downloads))

    def test_disabled_selection_and_exact_merge_wiring(self):
        self.assertEqual((),reader.selected_native_source_targets(self.value,False))
        self.assertEqual(('linux-x64',),reader.selected_native_source_targets(self.value,True))
        with self.assertRaises(ValueError):reader.selected_native_source_targets(self.value,'true')
        parent=(ROOT/'.github/workflows/product-validation.yml').read_text().split('  merge-gate:\n',1)[1]
        self.assertIn('desktop, retained-native-source, sdk-native-wrappers',parent)
        self.assertIn('test "$RETAINED_NATIVE_SOURCE_RESULT" = success || exit 1',parent)
        self.assertIn("native_source_tests=native",parent)
        self.assertIn("needs.plan.outputs.retained_native_source != 'true'",parent)

if __name__=='__main__':unittest.main()
