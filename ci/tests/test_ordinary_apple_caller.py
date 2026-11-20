"""Fixed Apple caller seams; synthetic transport grants no original authority."""
from contextlib import ExitStack, contextmanager, redirect_stderr
from copy import deepcopy
import importlib.util
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from ci import sdk_android_evidence_capture as gate
from ci.tests.test_runtime_reference_transport import RangeOpener

ROOT=Path(__file__).resolve().parents[2]
SPEC=importlib.util.spec_from_file_location('apple_source_validation',ROOT/'.github/actions/run-ci-lane/apple_source_validation.py')
swift=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(swift)

class OrdinaryAppleCallerTest(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup);self.root=Path(temporary.name).resolve()

    def test_report_binds_task_source_original_timing_and_bounded_exact_members(self):
        expected={'originalInput':{'buildKey':'sha256:'+'a'*64},'frameworkFiles':[],'sourceInventory':[],
            'toolchain':{'xcodeVersion':'26.6','xcodeBuild':'17F113','swiftVersion':'6.3.3'}}
        report=swift.canonical_json_bytes({'schemaVersion':1,'result':'passed','target':'iosSimulatorArm64',**expected['toolchain']})
        log=b'fixed actual command fixture\n';producer={'commit':'a'*40};digest='sha256:'+'b'*64
        record={'schemaVersion':1,'kind':'retained-swift-source','result':'passed','task':swift._TASK,
            'producer':producer,'planSha256':digest,**expected,'executionElapsedNs':1,
            'reportSha256':swift.sha256_bytes(report),'executionSha256':swift.sha256_bytes(log)}
        members=dict(zip(swift._NAMES,(swift.canonical_json_bytes(record),report,log)))
        self.assertEqual(record,swift._validate_controls(members,producer,digest,expected))
        for field,value in [('task','linkReleaseFrameworkIosArm64'),('originalInput',{}),('sourceInventory',[{}]),('executionElapsedNs',True)]:
            bad={**record,field:value}
            with self.subTest(field=field),self.assertRaises(ValueError):
                swift._validate_controls({**members,swift._NAMES[0]:swift.canonical_json_bytes(bad)},producer,digest,expected)
        for bad in ({**members,'body':b'x'},{**members,swift._NAMES[2]:b'x'*swift._LIMIT},
                    {**members,swift._NAMES[1]:report.replace(b'"schemaVersion":1',b'"schemaVersion":true')}):
            with self.assertRaises(ValueError):swift._validate_controls(bad,producer,digest,expected)

    def transport(self):
        leaves={swift._PREFIX+n:n.encode() for n in swift._LEAVES};inner=io.BytesIO()
        with zipfile.ZipFile(inner,'w',compression=zipfile.ZIP_STORED) as z:
            z.writestr('stage/outputs/device/unconsumed.bin',b'x'*(2*1024**2))
            for n,v in leaves.items():z.writestr('stage/'+n,v)
        member={'relativePath':'objects/b.zip','bytes':len(inner.getvalue()),'sha256':swift.sha256_bytes(inner.getvalue())};outer=io.BytesIO()
        with zipfile.ZipFile(outer,'w',compression=zipfile.ZIP_STORED) as z:z.writestr(member['relativePath'],inner.getvalue())
        artifact={'id':1,'size_in_bytes':len(outer.getvalue()),'digest':swift.sha256_bytes(outer.getvalue()),
            'archive_download_url':'https://api.github.com/repos/codex-agent-labs/codex-agent/actions/artifacts/1/zip'}
        native=SimpleNamespace(envelope=lambda record:{'receipt':{}},sdk_extension=lambda:{'spec':{},'proof':{'members':[member]}},
            observe_extended_sdk=lambda *a,**k:({},artifact,[]))
        expected={'frameworkFiles':[dict(relativePath=n,bytes=len(v),sha256=swift.sha256_bytes(v)) for n,v in leaves.items()]}
        return SimpleNamespace(completed_frozen=native,producer={}),{'objectSha256':member['sha256']},expected,RangeOpener({1:outer.getvalue()}),leaves

    def test_streams_only_four_original_leaves_and_holds_authority_until_exit(self):
        import runtime_reference_archive as transport
        state,record,expected,opener,leaves=self.transport()
        stderr = io.StringIO()
        with patch.object(transport.urllib.request,'build_opener',return_value=opener),patch.object(swift,'original_worker_member',return_value=True), \
             patch.object(swift,'_retained_dependency_plan'),patch.object(zipfile.ZipFile,'read',side_effect=AssertionError('no read-all')), \
             patch.object(swift.products,'_restore_product_objects',side_effect=AssertionError('no whole object restore')), \
             patch.dict(os.environ, CODEX_AGENT_THROUGHPUT_TRACE='1'), redirect_stderr(stderr):
            with ExitStack() as stack:
                swift._copy_framework(state,record,expected,self.root/'framework',stack,'fixture')
                self.assertEqual(set(swift._LEAVES),{p.relative_to(self.root/'framework').as_posix() for p in (self.root/'framework').rglob('*') if p.is_file()})
                for n,v in leaves.items():self.assertEqual(v,(self.root/'framework'/n[len(swift._PREFIX):]).read_bytes())
            self.assertLess(sum(b-a+1 for _,a,b in opener.requests),1024**2)
        trace, = [json.loads(line.removeprefix('throughput ')) for line in stderr.getvalue().splitlines() if line.startswith('throughput ')]
        self.assertEqual('_copy_framework', trace['operation'])
        self.assertTrue(trace['success']); self.assertGreater(trace['elapsedSeconds'], 0)
        self.assertEqual(sum(map(len, leaves.values())), trace['inclusiveCounters']['swiftSourceFrameworkLogicalBytes'])
        self.assertEqual(sum(b-a+1 for _,a,b in opener.requests), trace['inclusiveCounters']['swiftSourceOriginalRangeBytes'])

    def test_wrong_digest_and_late_native_failure_deny(self):
        import runtime_reference_archive as transport
        for mode in ('digest','late'):
            state,record,expected,opener,_=self.transport()
            if mode=='digest':expected['frameworkFiles'][0]['sha256']='sha256:'+'0'*64
            with patch.object(transport.urllib.request,'build_opener',return_value=opener),patch.object(swift,'original_worker_member',return_value=True),patch.object(swift,'_retained_dependency_plan'):
                with self.assertRaises(ValueError),ExitStack() as stack:
                    swift._copy_framework(state,record,expected,self.root/mode,stack,'fixture')
                    state.completed_frozen.envelope=lambda record:{'changed':True}

    def test_outer_owner_failure_prevents_publication(self):
        (self.root/'build').mkdir();plan=self.root/'plan.json';plan.write_bytes(b'{}')
        @contextmanager
        def owner(*a,**k):
            yield {'completed_frozen':object()}
            raise ValueError('late native exit')
        def capture(_plan,destination,**k):
            p=destination/'original/product-resume-inputs/plan/impact-plan.json';p.parent.mkdir(parents=True);p.write_bytes(b'{}')
        def inspect(_plan,_state,**k):k['_verified_state_consumer'](object())
        import reuse_qualification
        with patch.object(swift,'__file__',str(self.root/'.github/actions/run-ci-lane/apple_source_validation.py')), \
             patch.object(swift.products,'_validate_plan',return_value={'mergeReady':True}), \
             patch.object(swift.products,'validate_remote_build_authorization',return_value=(True,'')), \
             patch.object(reuse_qualification,'completed_frozen_options',owner), \
             patch.object(swift.products,'capture_runtime_resume_upload',side_effect=capture), \
             patch.object(swift.products,'inspect_products',side_effect=inspect), \
             patch.object(swift,'run_retained_swift_source',return_value={n:b'x' for n in swift._NAMES}), \
             patch.object(swift,'publish_regular_tree') as publish, \
             patch.dict(swift.os.environ,{'GITHUB_RUN_ID':'1','GITHUB_RUN_ATTEMPT':'1','GITHUB_TOKEN':'fixture'},clear=True):
            with self.assertRaisesRegex(ValueError,'late native exit'):
                swift.main(['--plan',str(plan),'--completed-frozen-policy',str(self.root/'policy'),
                    '--artifact-id','1','--artifact-sha256','sha256:'+'a'*64,'--trusted-workflow-sha','b'*40])
            publish.assert_not_called()
            self.assertFalse((self.root/'build/ci/retained-swift-source/controls').exists())

    def test_graph_keeps_import_toolchain_checks_and_no_arbitrary_task(self):
        script=swift._init_script(self.root)
        for text in ('if (gradle.parent != null) return',"':codex-agent-runtime-ios:verifyAppleToolchain'",
            "':codex-agent-runtime-ios:importCodexAgentIosSimulatorFramework'",'(graph.allTasks.collect { it.path } as Set) != wanted'):
            self.assertIn(text,script)
        self.assertNotIn('setDependsOn',script);self.assertNotIn('linkReleaseFramework',script)

    def test_review_profile_requires_fixed_selection_and_immutable_publisher(self):
        self.assertFalse(gate._apple_review_profile({},False))
        env={gate._APPLE_REVIEW_ENV:gate._APPLE_REVIEW_PROFILE,'TRUSTED_WORKFLOW_SHA':'b'*40}
        self.assertTrue(gate._apple_review_profile(env,True))
        for bad,selected in [(env,False),({gate._APPLE_REVIEW_ENV:'arbitrary'},True),({gate._APPLE_REVIEW_ENV:gate._APPLE_REVIEW_PROFILE},True)]:
            with self.assertRaises(ValueError):gate._apple_review_profile(bad,selected)


class AppleCompositionTest(unittest.TestCase):
    def setUp(self):
        from ci.tests.test_sdk_android_apk import OrdinaryAppleContributionTest
        self.fixture = OrdinaryAppleContributionTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_reviewed_producer_binds_current_publisher_without_copying_receipts(self):
        f = self.fixture
        f.env.update({gate._APPLE_REVIEW_ENV: gate._APPLE_REVIEW_PROFILE, 'TRUSTED_WORKFLOW_SHA': '4'*40})
        def reviewed(state, plan, **kwargs):
            self.assertEqual('4'*40, kwargs['trusted_workflow_sha'])
            originals = [dict(buildKey=f.records[i]['buildKey'], receiptSha256=f.records[i]['receiptSha256'],
                objectSha256=f.records[i]['objectSha256'], receipt=f.receipts[i])
                for i in sorted((gate._APPLE_B, gate._APPLE_P, gate._APPLE_DEVICE_V, gate._APPLE_SIMULATOR_V))]
            if mutate: f.env['TRUSTED_WORKFLOW_SHA'] = '5'*40
            return dict(originals=originals, selectedLanes=['ios-privacy-metrics'], result='scoped-passed')
        helper = SimpleNamespace(reviewed_apple_contribution=reviewed)
        for mutate in (False, True):
            f.env['TRUSTED_WORKFLOW_SHA'] = '4'*40
            with f.node_scopes(), patch.object(gate, '_apple_review_module', return_value=helper):
                if mutate:
                    with self.assertRaises(ValueError): f.contribution()
                else:
                    value = f.contribution()
                    self.assertNotIn('originals', value['apple']['reviewedChecks'])
                    self.assertEqual(4, len(value['apple']['originals']))

    def test_scoped_aggregate_exempts_only_reviewed_source_lanes_and_keeps_package(self):
        f = self.fixture
        with f.node_scopes(): value = f.contribution()
        value['apple']['reviewedChecks'] = {'selectedLanes': ['ios-privacy-metrics', 'ios-kotlin-tests', 'ios-native-tests', 'ios-rust-device', 'ios-rust-simulator']}
        required = [*gate._APPLE, 'ios-privacy-metrics', 'ios-swift-build', 'ios-package', 'ios-kotlin-tests', 'ios-native-tests', 'ios-rust-device', 'ios-rust-simulator']
        receipts = f.root/'receipts'; receipts.mkdir()
        for lane in ('ios-package',):
            path = receipts/lane; path.mkdir(); (path/'lane-receipt.json').write_bytes(gate.canonical_json_bytes({'lane': lane}))
        options = dict(repository_root=f.root, trusted_workflow_sha='4'*40, artifact_id=22,
            artifact_sha256='sha256:'+'a'*64, contribution_sha256='sha256:'+'b'*64, environ=f.env,
            apple=True, apple_reviewed=True, apple_source_tests=True, completed_frozen_policy=f.root/'policy')
        with patch.object(gate, '_authorized_plan', return_value=f.plan_value), \
             patch('receipt.required_lanes', return_value=required), \
             patch.object(gate, 'observed_validation_contributions', return_value=(value,None,None,None,{'ios-swift-build':{}})) as observe, \
             patch.object(gate, 'validate_receipt', side_effect=lambda p,*a,**k:gate.load_json_bytes(p.read_bytes())):
            result = gate.aggregate_retained_validation(f.plan, receipts, f.root/'accepted', **options)
            self.assertEqual({'ios-package'}, set(result['laneReceipts']))
            self.assertTrue(observe.call_args.kwargs['apple_source_tests'])
            (receipts/'ios-package/lane-receipt.json').unlink()
            with self.assertRaises(ValueError): gate.aggregate_retained_validation(f.plan, receipts, f.root/'denied', **options)
            self.assertFalse((f.root/'denied').exists())


    def test_reviewed_source_lanes_reject_unmatched_actions_and_preserve_attribution(self):
        spec = importlib.util.spec_from_file_location('reviewed_apple_test', ROOT/'.github/actions/run-ci-lane/apple_package_validation.py')
        helper = importlib.util.module_from_spec(spec); spec.loader.exec_module(helper)
        f = self.fixture
        lanes = {'ios-kotlin-tests':'test','ios-native-tests':'test','ios-rust-device':'build','ios-rust-simulator':'build'}
        for lane, action in lanes.items(): f.plan_value['lanes'][lane][action] = True
        selected = helper._selected_lanes(f.plan_value, True)
        self.assertTrue(set(lanes).issubset(selected))
        self.assertEqual({}, helper._selected_lanes(f.plan_value, False))
        for lane, action in lanes.items():
            wrong = 'test' if action == 'build' else 'build'
            f.plan_value['lanes'][lane][wrong] = True
            with self.assertRaises(ValueError): helper._selected_lanes(f.plan_value, True)
            f.plan_value['lanes'][lane][wrong] = False
        source = (ROOT/'.github/workflows/apple-runtime-evidence.yml').read_text()
        script = source.split('              # Remaining duties',1)[1]
        script = script.split("python3 -B - <<'PYCODE'\n",1)[1].split('          PYCODE',1)[0]
        script = '\n'.join(line[10:] for line in script.splitlines())
        for reviewed in ('true','false'):
            with patch.dict(os.environ,{'RETAINED_APPLE_REVIEWED':reviewed,'RETAINED_SWIFT_SOURCE':'false'},clear=True), \
                 patch.object(Path,'read_text',return_value=json.dumps(f.plan_value)):
                if reviewed == 'true': exec(compile(script,'apple-unmatched-duty-guard','exec'),{})
                else:
                    with self.assertRaisesRegex(ValueError,'distinct retained-input checks'):
                        exec(compile(script,'apple-unmatched-duty-guard','exec'),{})

    def test_fixed_workflow_selection_requires_authorized_ordinary_callback(self):
        f = self.fixture
        source = (ROOT/'.github/workflows/product-validation.yml').read_text()
        block = source.split('      - id: retained-apple-selection\n',1)[1].split('      - name:',1)[0]
        script = block.split("python3 -B - <<'PYCODE'\n",1)[1].split('          PYCODE',1)[0]
        script = '\n'.join(line[10:] for line in script.splitlines())
        f.plan_value['lanes']['ios-swift-build']['build'] = True
        f.plan_value['lanes']['ios-privacy-metrics']['test'] = True
        expected = dict(enabled='true', reviewed='true', swift_source='true')
        env = dict(ORDINARY_MODE='true', AUTHORIZED='true', VALIDATION_REUSED='false',
            NATIVE_READY='true', NATIVE_FULL_REUSE='true', CANONICAL_CALLBACK='true', GITHUB_OUTPUT=str(f.root/'output'))
        import reuse
        for changed in (None, 'ORDINARY_MODE', 'AUTHORIZED', 'NATIVE_READY', 'NATIVE_FULL_REUSE', 'CANONICAL_CALLBACK', 'VALIDATION_REUSED'):
            case = dict(env)
            if changed: case[changed] = 'true' if changed == 'VALIDATION_REUSED' else 'false'
            with patch.dict(os.environ,case,clear=True), patch.object(Path,'read_text',return_value=json.dumps(f.plan_value)), \
                 patch.object(reuse,'github_output') as output:
                exec(compile(script, 'fixed-retained-apple-selector', 'exec'), {})
                self.assertEqual(expected if changed is None else {k:'false' for k in expected}, output.call_args.args[1])

class SwiftStorageMeasurementTest(unittest.TestCase):
    def test_existing_disk_samples_and_gradle_elapsed_are_reported_without_receipt_changes(self):
        controls, trace, failure = self.exercise('success')
        self.assertEqual(set(swift._NAMES), set(controls))
        self.assertFalse(failure.exists())
        counters = trace['inclusiveCounters']
        self.assertTrue(trace['success'])
        self.assertEqual(14 * 1024**3, counters['swiftSourceEntryFreeBytes'])
        self.assertEqual(13 * 1024**3, counters['swiftSourceAfterFrameworkFreeBytes'])
        self.assertEqual(10 * 1024**3, counters['swiftSourceMinimumObservedFreeBytes'])
        self.assertEqual(5, counters['swiftSourceDiskSamples'])
        self.assertGreater(counters['swiftSourceGradleElapsedNs'], 0)
        record = swift.load_json_bytes(controls[swift._NAMES[0]])
        self.assertNotIn('swiftSourceMinimumObservedFreeBytes', record)

    def test_oversized_failure_log_keeps_bounded_diagnostics_and_original_error(self):
        for mode in ('oversized', 'existing-diagnostic'):
            with self.subTest(mode=mode):
                _, trace, failure = self.exercise(mode)
                self.assertFalse(trace['success'])
                self.assertGreater(trace['inclusiveCounters']['swiftSourceGradleElapsedNs'], 0)
                if mode == 'oversized':
                    self.assertEqual(swift._LIMIT, failure.stat().st_size)
                    self.assertTrue(failure.read_bytes().startswith(b'original compiler diagnostic\n'))
                    self.assertEqual(1, trace['inclusiveCounters']['swiftSourceFailureLogTruncated'])
                else:
                    self.assertEqual(b'held earlier diagnostic', failure.read_bytes())
                    self.assertEqual(1, trace['inclusiveCounters']['swiftSourceFailureLogCaptureErrors'])

    def exercise(self, mode):
        from contextlib import redirect_stderr
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        root = Path(temporary.name).resolve(); (root/'build').mkdir(); (root/'gradlew').write_bytes(b'wrapper')
        producer = {'commit': 'a'*40}; consumer = {'producer': producer}
        plan = {'validationCommit': 'a'*40, 'validationTree': 'b'*40,
                'lanes': {'ios-swift-build': {'build': True, 'test': False}}}
        plan_path = root/'plan.json'; plan_path.write_bytes(swift.canonical_json_bytes(plan))
        original = {k: 'held-'+k for k in swift._FIELDS}
        expected = dict(originalInput=original, frameworkFiles=[], sourceInventory=[],
            toolchain={'xcodeVersion':'26.6','xcodeBuild':'17F113','swiftVersion':'6.3.3'})
        native = SimpleNamespace(check_request=lambda request: None)
        state = swift.products._VerifiedProductState(plan, producer, consumer, (), (), {}, {}, {},
            {swift._BINARY: original}, {}, {}, {}, completed_frozen=native)
        environment = dict(GITHUB_ACTIONS='true',GITHUB_JOB='retained-swift-source',
            CI_VALIDATION_COMMIT='a'*40,CI_VALIDATION_TREE='b'*40,RUNNER_OS='macOS',RUNNER_ARCH='ARM64',GITHUB_TOKEN='fixture')
        failure = root/'build/ci/retained-swift-source/failure.log'
        if mode == 'existing-diagnostic':
            failure.parent.mkdir(parents=True); failure.write_bytes(b'held earlier diagnostic')
        class Child:
            pid = 123; returncode = 0
            def __init__(self, command, **kwargs):
                self.polls = iter((None, None, 0))
                kwargs['stdout'].write(b'fixture success\n' if mode == 'success'
                    else b'original compiler diagnostic\n' + b'x'*swift._LIMIT)
                kwargs['stdout'].flush()
                out = Path(kwargs['env']['CODEX_AGENT_SWIFT_SOURCE_OUTPUT']); out.mkdir()
                (out/'swift-simulator-compilation.json').write_bytes(swift.canonical_json_bytes(
                    {'schemaVersion':1,'result':'passed','target':'iosSimulatorArm64',**expected['toolchain']}))
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def poll(self): return next(self.polls)
            def wait(self, **kwargs): self.returncode = 1; return 1
        stderr = io.StringIO()
        with swift.verification_session(), patch.dict(os.environ, CODEX_AGENT_THROUGHPUT_TRACE='1'), \
             patch.object(swift, '_expected', return_value=expected), \
             patch.object(swift, '_copy_framework', side_effect=lambda s,r,e,d,stack,t:d.mkdir()), \
             patch.object(swift, 'memoized_file_inventory', return_value=[]), \
             patch.object(swift, 'host_classifier', return_value='macos-arm64'), \
             patch.object(swift, 'git_regular_blob_bytes', return_value=b'wrapper'), \
             patch.object(swift.products, '_consumer', return_value=consumer), \
             patch.object(swift.products, '_runtime_worker_checkout'), \
             patch.object(swift.subprocess, 'Popen', Child), patch.object(swift.os, 'killpg'), \
             patch.object(swift.time, 'sleep'), \
             patch.object(swift.shutil, 'disk_usage', side_effect=[SimpleNamespace(free=n*1024**3) for n in (14,13,12,11,10)]), \
             redirect_stderr(stderr):
            controls = None
            if mode == 'success':
                controls = swift.run_retained_swift_source(state,plan_path=plan_path,repository_root=root,environ=environment)
            else:
                with self.assertRaisesRegex(ValueError, 'crossed its 2 GiB free-space or control-log bound'):
                    swift.run_retained_swift_source(state,plan_path=plan_path,repository_root=root,environ=environment)
        traces = [json.loads(line.removeprefix('throughput ')) for line in stderr.getvalue().splitlines() if line.startswith('throughput ')]
        trace, = [r for r in traces if r['operation']=='run_retained_swift_source']
        return controls, trace, failure


if __name__=='__main__':unittest.main()
