"""APK transport checks do not stand in for genuine product/device admission."""

from argparse import Namespace
import json
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from ci import sdk_android_evidence_capture as apk
from ci import sdk_android_evidence_capture as capture
from ci import sdk_android_validation_policy as policy_stage
from ci.products import sdk_android_observation as observation
from ci.tests import test_ci as fixtures


class AndroidApkTest(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.ReceiptTest(methodName="runTest")
        self.addCleanup(self.f.doCleanups)
        self.f.setUp()
        self.addCleanup(self.f.tearDown)
        self.plan = self.f.plan_path.resolve()
        self.value = json.loads(self.plan.read_bytes())
        self.value["androidEvidenceRequired"] = True
        self.plan.write_text(json.dumps(self.value))
        self.lane = self.f.root.resolve() / "apk"
        self.lane.mkdir()
        self.originals = set(apk.SUBMISSION_FILES.values()) - {"lane-receipt.json"}
        for relative in apk.CONTROL_FILES | self.originals:
            target = self.lane / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((relative + " fixture\n").encode())
        apk.write_canonical_json(self.lane / "apk-execution.json", {
            "kind": apk.SCOPE, "tasks": list(apk.TASKS), "exitCode": 0,
            "candidateCommit": self.value["validationCommit"], "candidateTree": self.value["validationTree"],
            **{phase + "ReceiptSha256": apk.sha256_bytes((self.lane / (phase + "-receipt.json")).read_bytes())
               for phase in ("binary", "package")},
        })
        self.receipt()

    def receipt(self, actions="build"):
        apk.create_receipt(Namespace(plan=self.plan, lane="android", output=self.lane,
            workflow_path=".github/workflows/ci.yml",
            artifact_name="codex-agent-ci-android-" + self.value["validationTree"],
            run_id=101, run_attempt=2, runner=["os=Linux", "arch=X64"],
            toolchain=["java=fixture", "evidenceScope=" + apk.SCOPE, "validationActions=" + actions],
            artifact=[p + "=apk-consumer-input" for p in sorted(apk.CONTROL_FILES | self.originals)], evidence=[]))

    def firebase(self):
        source = self.f.root.resolve() / "firebase-apk"
        source.mkdir()
        for relative in capture._FIREBASE_FILES:
            name = Path(relative).name
            original = next((p for p in self.originals if Path(p).name == name), None)
            (source / name).write_bytes((self.lane / original).read_bytes() if original else b"fixture evidence\n")
        return source

    def retained_source_checks(self, destination, failure=None):
        receipt=json.loads((self.lane/'lane-receipt.json').read_bytes())
        producer={**{key:receipt[key] for key in ('repository','workflowPath','event','runId','runAttempt','pullRequest')},
            'commit':receipt['validationCommit'],'tree':receipt['validationTree']}
        real_run,real_output=subprocess.run,subprocess.check_output
        def execute(command,**kwargs):
            if command[0] != str(self.f.root.resolve()/'gradlew'):return real_run(command,**kwargs)
            self.assertEqual(apk._check_tasks(self.value),command[1:1+len(apk._check_tasks(self.value))])
            self.assertFalse(any('assemble' in x or 'ciProductPhase' in x for x in command))
            if failure=='process':raise subprocess.CalledProcessError(1,command)
            if failure!='missing':
                for action,(_,pattern,_) in apk.SOURCE_CHECKS.items():
                    if self.value['lanes']['android'][action]:
                        p=self.f.root/pattern.replace('**/*.xml','debug/TEST-unit.xml')
                        p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'<testsuite tests="1" failures="0"/>')
            if failure=='mutation':self.plan.write_bytes(self.plan.read_bytes()+b' ')
        def java(command,**kwargs):
            return 'fixture Java' if command==['/fixture/java/bin/java','-version'] else real_output(command,**kwargs)
        with patch.object(apk.products,'_validate_plan',return_value=self.value), \
                patch.object(apk.products,'_consumer',return_value={'producer':producer}), \
                patch.object(apk.products,'_runtime_worker_checkout'), \
                patch.object(apk.subprocess,'run',side_effect=execute), \
                patch.object(apk.subprocess,'check_output',side_effect=java), \
                patch.dict(os.environ,{'JAVA_HOME':'/fixture/java','RUNNER_OS':'Linux','RUNNER_ARCH':'X64'}):
            apk.source_checks(self.f.root,self.plan,destination)
        return producer

    def test_retained_gate_joins_source_subset_without_old_schema_or_firebase(self):
        import tempfile,shutil
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve();checks=root/'receipts/android'
            producer=self.retained_source_checks(checks)
            receipt=json.loads((checks/'lane-receipt.json').read_bytes())
            self.assertNotIn('build',receipt['toolchain']['validationActions'])
            self.assertTrue(all(row['kind']=='android-source-check' for row in receipt['evidence']))
            contribution={'consumer':producer,'kind':'mocked observed original boundary'}
            args=dict(repository_root=self.f.root,trusted_workflow_sha='a'*40,artifact_id=12,
                artifact_sha256='sha256:'+'b'*64,contribution_sha256='sha256:'+'c'*64,environ={},android=True)
            before=self.plan.read_bytes()
            with patch.object(apk,'observed_validation_contributions',return_value=(contribution,None)) as observe:
                value=apk.aggregate_retained_validation(self.plan,checks.parent,root/'accepted',**args)
                observe.assert_called_once()
                self.assertEqual('current-validation-contributions',value['kind'])
                self.assertEqual({'android'},set(value['laneReceipts']))
                self.assertEqual(before,self.plan.read_bytes())
                for change in ('missing-test','fake-build','fake-firebase','duplicate'):
                    with self.subTest(change=change):
                        raw=(checks/'lane-receipt.json').read_bytes();changed=json.loads(raw)
                        if change=='missing-test':changed['toolchain']['validationActions']=''
                        elif change=='fake-build':changed['toolchain']['validationActions']='build,metadata,test'
                        elif change=='fake-firebase':changed['evidence'][0]['kind']='firebase-runtime-evidence'
                        else:shutil.copytree(checks,root/'receipts/duplicate')
                        (checks/'lane-receipt.json').write_text(json.dumps(changed))
                        with self.assertRaises(ValueError):apk.aggregate_retained_validation(self.plan,checks.parent,root/change,**args)
                        self.assertFalse((root/change).exists());(checks/'lane-receipt.json').write_bytes(raw)
                        if change=='duplicate':shutil.rmtree(root/'receipts/duplicate')

    def test_source_checks_process_missing_output_and_mutation_never_publish(self):
        import tempfile,shutil
        raw=self.plan.read_bytes()
        for failure in ('process','missing','mutation'):
            with self.subTest(failure=failure),tempfile.TemporaryDirectory() as temporary:
                self.plan.write_bytes(raw)
                directory=self.f.root/'codex-agent-runtime-android/build'
                if directory.exists():shutil.rmtree(directory)
                destination=Path(temporary).resolve()/'checks'
                with self.assertRaises((ValueError,subprocess.CalledProcessError)):
                    self.retained_source_checks(destination,failure)
                self.assertFalse(destination.exists())
        self.plan.write_bytes(raw)

    def test_build_only_initial_and_separate_final_preserve_original(self):
        before = apk.regular_file_inventory(self.lane, allow_empty=True)
        checked = apk.check(self.plan, self.lane)
        self.assertEqual("build", checked["toolchain"]["validationActions"])
        with self.assertRaisesRegex(ValueError, "action coverage mismatch"):
            apk.validate_receipt(self.lane / "lane-receipt.json", self.plan, self.lane, "android")
        observed = self.f.root.resolve() / "apk-observation"
        arguments = dict(repository=self.f.root.resolve(), lane=self.lane, plan=self.plan, observation=observed,
            candidate_commit=self.value["validationCommit"], candidate_tree=self.value["validationTree"],
            trusted_source_commit=self.value["validationCommit"], trusted_source_tree=self.value["validationTree"],
            apk_consumer=True)
        observation.bind_submission(**arguments, create=True)
        observation.bind_submission(**arguments, create=False)
        self.assertEqual((self.lane / "lane-receipt.json").read_bytes(), (observed / "lane-receipt.json").read_bytes())
        final = self.f.root.resolve() / "final-apk"
        apk.attach(self.plan, self.lane, self.firebase(), final)
        result = apk.check(self.plan, final, final=True)
        self.assertEqual(before, apk.regular_file_inventory(self.lane, allow_empty=True))
        self.assertEqual(apk.CONTROL_FILES, {r["relativePath"] for r in result["artifacts"]})
        self.assertEqual(capture._FIREBASE_FILES, {r["relativePath"] for r in result["evidence"]})
        self.assertTrue(all(not (final / name).exists() for name in self.originals))
        self.assertEqual(checked["runId"], result["runId"])
        self.assertEqual((final / "lane-receipt.json").read_bytes(),
                         capture._check_lane(self.plan, final, self.value))

    def test_reject_invented_test_claim_and_unsuccessful_execution(self):
        self.receipt(actions="build,metadata,test")
        with self.assertRaisesRegex(ValueError, "build only"):
            apk.check(self.plan, self.lane)
        for exit_code in (False, 1):
            execution = json.loads((self.lane / "apk-execution.json").read_bytes())
            execution["exitCode"] = exit_code
            apk.write_canonical_json(self.lane / "apk-execution.json", execution)
            self.receipt()
            with self.assertRaisesRegex(ValueError, "execution differs"):
                apk.check(self.plan, self.lane)

    def test_final_rejects_substitution_extra_files_and_overwrite(self):
        source = self.firebase()
        final = self.f.root.resolve() / "final-apk"
        target = source / "codex-agent-runtime-android-release.aar"
        raw = target.read_bytes()
        target.write_bytes(raw + b"tamper")
        with self.assertRaisesRegex(ValueError, "substituted"):
            apk.attach(self.plan, self.lane, source, final)
        target.write_bytes(raw)
        (source / "extra").write_bytes(b"extra")
        with self.assertRaisesRegex(ValueError, "seven-file"):
            apk.attach(self.plan, self.lane, source, final)
        self.assertFalse(final.exists())
        with self.assertRaises(ValueError):
            apk.attach(self.plan, self.lane, source, self.lane)

    def test_failed_consumer_preserves_diagnostics_without_success_receipt(self):
        root = self.f.root.resolve()
        policy = {name: str(self.lane / (name + ".json")) for name in apk.POLICY_PROPERTIES}
        for name, path in policy.items():
            Path(path).write_bytes(b'{"productVersion":"0.8.0"}\n')
        destination = root / "failed-consumer"
        real_run = subprocess.run

        def run(argv, **kwargs):
            if argv[0] == "fixture-gradle":
                self.assertEqual("--init-script", argv[1])
                self.assertEqual(apk.CONTRACT_ANDROID_INIT, Path(argv[2]).read_text())
                kwargs["stdout"].write(b"causal consumer failure\n")
                return subprocess.CompletedProcess(argv, 7)
            return real_run(argv, **kwargs)

        with patch.dict(os.environ, {"GITHUB_RUN_ID": "101", "GITHUB_RUN_ATTEMPT": "2"}), \
                patch.object(apk, "command", side_effect=lambda *_: ["fixture-gradle"]), \
                patch.object(apk.subprocess, "run", side_effect=run), \
                self.assertRaises(subprocess.CalledProcessError):
            apk.produce(root, self.plan, policy, destination)
        diagnostics = destination.with_name(destination.name + "-diagnostics")
        self.assertEqual(b"causal consumer failure\n", (diagnostics / "apk-build.log").read_bytes())
        self.assertEqual(7, json.loads((diagnostics / "apk-execution.json").read_bytes())["exitCode"])
        self.assertEqual(apk.sha256_bytes(apk.CONTRACT_ANDROID_INIT.encode()),
            json.loads((diagnostics / "apk-execution.json").read_bytes())["repositoryPolicySha256"])
        self.assertFalse(destination.exists())
        self.assertFalse((diagnostics / "lane-receipt.json").exists())

    def test_compact_plan_projects_exact_android_controls_and_successful_receipt(self):
        root = self.f.root.resolve()
        compact = root / "build/compact-plan/impact-plan.json"
        compact.parent.mkdir(parents=True)
        compact.write_bytes(self.plan.read_bytes())
        projected = root / "build/projected-plan"
        revision = self.value["validationCommit"]
        policy_stage._stage_android_plan(root, compact, revision, projected)
        plan = projected / "impact-plan.json"
        self.assertEqual(self.plan.read_bytes(), plan.read_bytes())
        for name in apk.INPUT_NAMES.values():
            self.assertEqual((self.plan.parent / "inventories/android" / name).read_bytes(),
                             (projected / "inventories/android" / name).read_bytes())
        self.assertEqual([compact], list(compact.parent.iterdir()))
        with self.assertRaisesRegex(ValueError, "authenticated candidate"):
            policy_stage._stage_android_plan(root, compact, "f" * 40, root / "wrong-source")
        (projected / "inventories/android/production-inputs.git-tree").write_bytes(b"wrong\n")
        with self.assertRaisesRegex(ValueError, "authenticated Git"):
            policy_stage._stage_android_plan(root, plan, revision, root / "wrong-inventory")
        (projected / "inventories/android/production-inputs.git-tree").write_bytes(
            (self.plan.parent / "inventories/android/production-inputs.git-tree").read_bytes())
        policy = {name: str(self.lane / (name + ".json")) for name in apk.POLICY_PROPERTIES}
        for path in policy.values():
            Path(path).write_bytes(b'{"productVersion":"0.8.0"}\n')
        binary = root / "binary-stage"
        aar = binary / "outputs/maven/io/github/codex-agent-labs/codex-agent-runtime-android/0.8.0/codex-agent-runtime-android-0.8.0.aar"
        aar.parent.mkdir(parents=True)
        aar.write_bytes(b"original AAR")
        policy["binaryStage"] = str(binary)
        real_run, real_output = subprocess.run, subprocess.check_output
        consumer_calls = []

        def run(argv, **kwargs):
            if argv[0] != "fixture-gradle":
                return real_run(argv, **kwargs)
            consumer_calls.append(argv)
            for name in ("application.apk", "test.apk"):
                output = root / apk.SUBMISSION_FILES[name].removeprefix("payload/")
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(name.encode())
            kwargs["stdout"].write(b"fixture successful consumer\n")
            return subprocess.CompletedProcess(argv, 0)

        def output(argv, **kwargs):
            return "fixture Java" if argv[-1] == "-version" else real_output(argv, **kwargs)

        with patch.dict(os.environ, {"GITHUB_RUN_ID": "101", "GITHUB_RUN_ATTEMPT": "2",
                "JAVA_HOME": str(root), "RUNNER_OS": "Linux", "RUNNER_ARCH": "X64"}), \
                patch.object(apk, "command", side_effect=lambda *_: ["fixture-gradle"]), \
                patch.object(apk.subprocess, "run", side_effect=run), \
                patch.object(apk.subprocess, "check_output", side_effect=output):
            with self.assertRaisesRegex(ValueError, "missing or unsafe"):
                apk.produce(root, compact, policy, root / "missing-controls")
            self.assertEqual([], consumer_calls)
            destination = root / "successful-consumer"
            apk.produce(root, plan, policy, destination)
            self.assertEqual(1, len(consumer_calls))
            self.assertEqual("build", apk.check(plan, destination)["toolchain"]["validationActions"])

    def test_command_only_uses_two_allowed_consumer_tasks_and_explicit_artifacts(self):
        root = self.f.root.resolve()
        policy = {name: str(self.lane / (name + ".json")) for name in apk.POLICY_PROPERTIES}
        for path in policy.values():
            Path(path).write_bytes(b"fixture\n")
        request = {name: Path(policy["compatibilityRequest"]) for name in (
            "contract_payload", "contract_metadata_receipt", "contract_attestation",
            "contract_attestation_signature", "contract_public_key")}
        version = root / "gradle/release/versions/contract.txt"
        version.parent.mkdir(parents=True, exist_ok=True)
        version.write_text("0.8.0\n")
        with patch.object(apk, "load_sdk_compatibility_request", return_value=request):
            command = apk.command(root, policy)
            self.assertEqual(list(apk.TASKS), [part for part in command if part.startswith(":")])
            self.assertEqual(12, len([part for part in command if part.startswith("-PcodexAgent.")]))
            self.assertIn("-PcodexAgent.contractVersion=0.8.0", command)
            with self.assertRaisesRegex(ValueError, "exact six"):
                apk.command(root, {**policy, "extra": str(root)})



class RetainedAndroidContributionTest(unittest.TestCase):
    """Synthetic native boundary; real receipt/content, private files and upload checks."""
    def setUp(self):
        from copy import deepcopy
        from ci.tests.test_products import phase_receipt
        from products.receipt import compute_build_key
        from products.plan import _upstream_record
        from products.sdk_android_validation_content import android_validation_content
        self.tmp = __import__('tempfile').TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.plan = self.root / 'impact-plan.json'
        self.plan_value = dict(repository='codex-agent-labs/codex-agent', event='pull_request', pullRequest=31,
            validationCommit='a'*40, validationTree='b'*40, mergeReady=True, remoteBuildAuthorized=True,
            remoteBuildAuthorizationReason='pull-request-final',
            lanes={'android':dict(build=True,test=True,metadata=True),'node-js':dict(build=True,test=True,metadata=True)})
        self.plan.write_bytes(apk.canonical_json_bytes(self.plan_value))
        self.env = dict(GITHUB_ACTIONS='true', GITHUB_JOB='merge-gate', GITHUB_TOKEN='fixture',
            GITHUB_REPOSITORY=self.plan_value['repository'], GITHUB_EVENT_NAME='pull_request',
            GITHUB_SHA='a'*40, GITHUB_RUN_ID='21', GITHUB_RUN_ATTEMPT='2')
        self.current = apk.products._consumer(self.plan_value, self.env)['producer']
        package = phase_receipt()
        package.update(product='sdk', component='sdk-android', phase='package', target='android')
        package['producer'].update(workflowPath='.github/workflows/ci.yml', commit='c'*40, tree='d'*40)
        package['buildKey'] = compute_build_key(product='sdk', component='sdk-android', phase='package',
            target='android', inputs=package['inputs'])
        content = android_validation_content(sdk_version=package['productVersion'],
            package_outputs_digest=_upstream_record(package)['outputsDigest'],
            release_aar_sha256='sha256:'+'d'*64, bundled_runtime_sha256='sha256:'+'e'*64)
        self.content = apk.canonical_json_bytes(content)
        validation = deepcopy(package)
        validation['phase'] = 'validation'
        validation['inputs']['upstreamArtifacts'] = [_upstream_record(package)]
        validation['buildKey'] = compute_build_key(product='sdk', component='sdk-android', phase='validation',
            target='android', inputs=validation['inputs'])
        validation['outputs'] = [dict(kind='android-validation-content',
            relativePath='outputs/validation/android-validation.json', bytes=len(self.content),
            sha256=apk.sha256_bytes(self.content))]
        self.receipts = {apk._ANDROID_V: validation, apk._ANDROID_P: package}
        self.records = {key: {**{field:getattr(key,field) for field in apk.products._IDENTITY_KEYS},
            'buildKey':value['buildKey'], 'receiptSha256':apk.sha256_bytes(apk.canonical_json_bytes(value)),
            'objectSha256':'sha256:' + ('1' if key == apk._ANDROID_V else '2')*64}
            for key,value in self.receipts.items()}
        import reuse_qualification
        self.native = object.__new__(reuse_qualification.CompletedFrozenReuse)
        self.state = apk.products._VerifiedProductState(self.plan_value, self.current,
            {'kind':'ci','producer':self.current}, (apk._ANDROID_V,), (apk._ANDROID_P,apk._ANDROID_V),
            {}, {}, {}, {}, {}, self.records, {}, self.native)
        self.alive = True
        self.materializations = []

    def envelope(self, row):
        identity = apk.products._identity(row)
        if row != self.records[identity]:
            raise ValueError('fixture native tuple changed')
        receipt = self.receipts[identity]
        return dict(receipt=receipt,receiptBytes=apk.canonical_json_bytes(receipt),
            receiptSha256=row['receiptSha256'],objectSha256=row['objectSha256'])

    def materialize(self, state, identities, destination):
        self.assertIs(state,self.state);self.assertEqual((apk._ANDROID_V,),identities)
        self.materializations.append(identities)
        path=destination/'sdk-sdk-android-validation-android/stage/outputs/validation/android-validation.json'
        path.parent.mkdir(parents=True);path.write_bytes(self.content)
        return {apk._ANDROID_V:self.envelope(self.records[apk._ANDROID_V])}

    def consumer(self, value):
        if not self.alive or value != {'kind':'ci','producer':self.current}:
            raise ValueError('fixture authority lifetime/current consumer')

    def scopes(self):
        from contextlib import ExitStack
        import reuse_qualification
        from products.restore import verification_session
        stack=ExitStack();stack.enter_context(verification_session())
        stack.enter_context(patch.object(reuse_qualification.CompletedFrozenReuse,'check_consumer',side_effect=self.consumer))
        stack.enter_context(patch.object(reuse_qualification.CompletedFrozenReuse,'envelope',side_effect=self.envelope))
        stack.enter_context(patch.object(apk.products,'_restore_product_objects',side_effect=self.materialize))
        return stack

    def contribution(self):
        return apk.retained_android_contribution(self.state,self.plan,environ=self.env)

    def test_original_v_and_p_bind_current_consumer_with_one_v_body_only(self):
        from copy import deepcopy
        original=deepcopy(self.receipts)
        with self.scopes():
            value=self.contribution()
        self.assertEqual([ (apk._ANDROID_V,) ],self.materializations)
        self.assertEqual(original,self.receipts)
        self.assertEqual(self.current,value['consumer'])
        self.assertNotEqual(self.current,value['validation']['receipt']['producer'])
        self.assertEqual(original[apk._ANDROID_P],value['package']['receipt'])
        self.assertEqual(apk.sha256_bytes(self.plan.read_bytes()),value['planSha256'])

    def test_wrong_type_selection_dependency_and_late_mutation_reject(self):
        from dataclasses import replace
        from copy import deepcopy
        for change in ('type','selection','dependency','plan','lifetime'):
            with self.subTest(change=change),self.scopes():
                state=self.state
                original=deepcopy(self.receipts)
                raw=self.plan.read_bytes()
                if change=='type':state=replace(state,completed_frozen=object())
                if change=='selection':state=replace(state,closure=(apk._ANDROID_P,))
                if change=='dependency':self.receipts[apk._ANDROID_V]['inputs']['upstreamArtifacts'][0]['outputsDigest']='sha256:'+'f'*64
                materialize=self.materialize
                def restore(*args):
                    result=materialize(*args)
                    if change=='plan':self.plan.write_bytes(raw+b' ')
                    if change=='lifetime':self.alive=False
                    return result
                with patch.object(apk.products,'_restore_product_objects',side_effect=restore),self.assertRaises(ValueError):
                    apk.retained_android_contribution(state,self.plan,environ=self.env)
                self.receipts=original;self.plan.write_bytes(raw);self.alive=True

    def test_observed_completion_upload_checks_source_window_digest_and_singleton(self):
        import io,zipfile
        from copy import deepcopy
        with self.scopes():android=self.contribution()
        value=dict(schemaVersion=1,kind=apk._VALIDATION_KIND,consumer=self.current,
                   planSha256=apk.sha256_bytes(self.plan.read_bytes()),android=android)
        raw=apk.canonical_json_bytes(value)
        options=dict(repository_root=self.root,trusted_workflow_sha='4'*40,artifact_id=22,
            artifact_sha256='',contribution_sha256=apk.sha256_bytes(raw),environ=self.env,android=True)
        observation=dict(run=dict(id=21,head_sha='9'*40,status='in_progress'),jobs=[dict(
            id=5,name='product-validation / sdk-completion',status='completed',conclusion='success',
            started_at='2026-11-01T10:00:00Z',completed_at='2026-11-01T10:05:00Z')])
        for change in ('none','source','window','digest','extra','plan','owner-exit'):
            with self.subTest(change=change):
                report=deepcopy(value)
                if change=='source':report['consumer']['commit']='f'*40
                report_raw=apk.canonical_json_bytes(report)
                stream=io.BytesIO()
                with zipfile.ZipFile(stream,'w') as archive:
                    archive.writestr(apk._VALIDATION_FILE,report_raw)
                    if change=='extra':archive.writestr('unexpected',b'extra')
                uploaded=stream.getvalue()
                artifact=dict(id=22,name=f"codex-agent-sdk-validation-contributions-{self.current['tree']}-attempt-2",
                    digest=apk.sha256_bytes(uploaded),size_in_bytes=len(uploaded),expired=False,
                    archive_download_url='https://api.github.com/repos/codex-agent-labs/codex-agent/actions/artifacts/22/zip',
                    workflow_run=dict(id=21,head_sha='9'*40),created_at='2026-11-01T10:03:00Z')
                if change=='window':artifact['created_at']='2026-11-01T09:59:00Z'
                options.update(artifact_sha256=apk.sha256_bytes(uploaded),contribution_sha256=apk.sha256_bytes(report_raw))
                if change=='digest':options['contribution_sha256']='sha256:'+'0'*64
                original_plan=self.plan.read_bytes()
                def download(*args,**kwargs):
                    kwargs['destination'].write_bytes(uploaded)
                    if change=='plan':self.plan.write_bytes(original_plan+b' ')
                from contextlib import contextmanager
                from products.restore import verification_session
                @contextmanager
                def session():
                    with verification_session():yield
                    if change=='owner-exit':raise ValueError('late observation owner')
                with patch.object(apk.products,'_validate_plan',return_value=self.plan_value), \
                        patch.object(apk.products,'_git_value',side_effect=lambda r,c,v:self.current['tree' if 'tree' in v else 'commit']), \
                        patch.object(apk.products,'_observe_ci_producer_jobs',return_value=[observation]) as observe, \
                        patch.object(apk.products,'api_json',return_value=artifact), \
                        patch.object(apk.products,'_reuse_contract_ci_upload',side_effect=download), \
                        patch('products.restore.verification_session',session):
                    if change=='none':
                        self.assertEqual((value,None),apk.observed_validation_contributions(self.plan,**options))
                        self.assertEqual({'completion':{'path':'.github/workflows/product-validation.yml','sha':'4'*40}},
                            observe.call_args.kwargs['trusted_workflows_by_phase'])
                        self.assertEqual({'completion':self.current},observe.call_args.args[0])
                    else:
                        with self.assertRaises(ValueError):apk.observed_validation_contributions(self.plan,**options)
                self.plan.write_bytes(original_plan)

class SharedCanonicalContributionTest(unittest.TestCase):
    envelope = RetainedAndroidContributionTest.envelope
    materialize = RetainedAndroidContributionTest.materialize
    consumer = RetainedAndroidContributionTest.consumer
    scopes = RetainedAndroidContributionTest.scopes

    def setUp(self):
        RetainedAndroidContributionTest.setUp(self)
        from copy import deepcopy
        from dataclasses import replace
        from ci.tests.test_products import phase_receipt
        from products.receipt import compute_build_key
        from products.registry import phase_instance_dependencies
        from products.plan import _upstream_record
        from ci.tests.test_sdk_completion import phase, inspected
        receipts = {}
        def receipt(identity):
            if identity in receipts: return receipts[identity]
            value = phase_receipt()
            value.update({key:getattr(identity,key) for key in apk.products._IDENTITY_KEYS})
            value['producer'].update(workflowPath='.github/workflows/ci.yml',commit='c'*40,tree='d'*40)
            value['inputs']['upstreamArtifacts'] = sorted(
                [_upstream_record(receipt(parent)) for parent in phase_instance_dependencies(identity)], key=apk.products._identity)
            value['buildKey'] = compute_build_key(**{key:getattr(identity,key) for key in apk.products._IDENTITY_KEYS},inputs=value['inputs'])
            receipts[identity]=value
            return value
        for identity in apk.products.PHASE_INSTANCE_IDS: receipt(identity)
        receipts.update(self.receipts)  # Existing real tiny Android P/V content fixture.
        self.receipts=receipts
        self.records={identity:{**phase(identity),'buildKey':value['buildKey'],
            'receiptSha256':apk.sha256_bytes(apk.canonical_json_bytes(value)),
            'objectSha256':apk.sha256_bytes(str(identity).encode())} for identity,value in receipts.items()}
        self.state=replace(self.state,closure=apk.products.PHASE_INSTANCE_IDS,
            prior=inspected([self.records[i] for i in sorted(self.records)])['result'],
            prior_by_instance=self.records,prior_carrier_phases=self.records)
        self.inventories=self.plan.parent/'inventories/node-js';self.inventories.mkdir(parents=True)
        for name in apk.INPUT_NAMES.values():(self.inventories/name).write_bytes(b'original-git-record\n')

    def node_scopes(self):
        stack=self.scopes()
        stack.enter_context(patch.object(apk.products,'_validate_plan',return_value=self.plan_value))
        stack.enter_context(patch.object(apk.products,'_git_value',return_value=self.current['commit']))
        stack.enter_context(patch('impact.inventory',return_value='original-git-record\n'))
        stack.enter_context(patch('impact.effective_pathspecs',return_value=('fixed-original-input',)))
        return stack

    def contribution(self, android=False):
        return apk.retained_validation_contributions(self.state,self.plan,repository_root=self.root,
            environ=self.env,android=android,node_js=True)

    def test_shared_originals_use_no_node_bodies_or_second_full_context(self):
        from copy import deepcopy
        originals=deepcopy(self.receipts)
        for android in (False,True):
            self.materializations.clear()
            for path in self.inventories.iterdir():path.unlink()
            with self.subTest(android=android),self.node_scopes(), \
                    patch.object(apk.products,'_full_sdk_parity_context',side_effect=AssertionError('redundant full context')):
                value=self.contribution(android)
            self.assertEqual([(apk._ANDROID_V,)] if android else [],self.materializations)
            node=value['nodeJs'];self.assertEqual(112,len(node['parityExpectedPhases']))
            self.assertEqual([originals[i] for i in apk._NODE_RUNTIME],[row['receipt'] for row in node['originals']])
            self.assertEqual([originals[i] for i in apk._NODE_SDK],[row['receipt'] for row in node['sdkJavaScript']])
            self.assertEqual(originals,self.receipts)
            self.assertNotEqual(value['consumer'],node['originals'][0]['receipt']['producer'])
            for name in apk.INPUT_NAMES.values():(self.inventories/name).write_bytes(b'original-git-record\n')

    def test_missing_parity_context_uses_existing_private_join_and_late_exit_denies(self):
        from contextlib import contextmanager
        from dataclasses import replace
        full=self.state
        missing=apk._NODE_SDK[0]
        records={key:row for key,row in self.records.items() if key != missing}
        self.state=replace(full,prior_by_instance=records,prior_carrier_phases=records,
            prior={**full.prior,'phases':[records[key] for key in sorted(records)]})
        for fail in (False,True):
            calls=[]
            @contextmanager
            def context(actual,root):
                self.assertIs(self.state,actual);calls.append('enter')
                yield full
                calls.append('exit')
                if fail:raise ValueError('late parity context failure')
            with self.subTest(fail=fail),self.node_scopes(),patch.object(apk.products,'_full_sdk_parity_context',context):
                if fail:
                    with self.assertRaisesRegex(ValueError,'late parity context'):self.contribution()
                else:self.assertEqual(112,len(self.contribution()['nodeJs']['parityExpectedPhases']))
            self.assertEqual(['enter','exit'],calls);self.assertEqual([],self.materializations)

    def test_changed_selection_tuple_parent_inventory_or_lifetime_rejects(self):
        from copy import deepcopy
        from dataclasses import replace
        original_state=self.state
        for change in ('unselected','closure','tuple','parent','inventory','lifetime','source'):
            records,receipts=deepcopy(self.records),deepcopy(self.receipts)
            plan=self.plan.read_bytes();self.alive=True
            with self.subTest(change=change),self.node_scopes() as scope:
                if change=='unselected':self.plan_value['lanes']['node-js'].update(build=False,test=False)
                if change=='closure':self.state=replace(self.state,closure=())
                if change=='tuple':self.records[apk._NODE_RUNTIME[1]]['receiptSha256']='sha256:'+'f'*64
                if change=='parent':self.receipts[apk._NODE_RUNTIME[1]]['inputs']['upstreamArtifacts'][0]['outputsDigest']='sha256:'+'f'*64
                if change=='inventory':scope.enter_context(patch('impact.inventory',side_effect=['original-git-record\n']*3+['changed\n']*3))
                if change=='lifetime':self.alive=False
                if change=='source':self.plan.write_bytes(apk.canonical_json_bytes(dict(self.plan_value,validationCommit='f'*40)))
                with self.assertRaises(ValueError):self.contribution()
            self.receipts=receipts;self.records=records
            self.plan_value['lanes']['node-js'].update(build=True,test=True)
            self.plan.write_bytes(plan);self.alive=True
            self.state=replace(original_state,prior_by_instance=self.records,prior_carrier_phases=self.records,
                prior={**original_state.prior,'phases':[self.records[i] for i in sorted(self.records)]})
            for path in self.inventories.iterdir():path.write_bytes(b'original-git-record\n')

    def test_exact_receipt_union_preserves_android_subset_and_rejects_legacy_node(self):
        from copy import deepcopy
        from receipt import VALIDATION_ACTIONS_KEY
        with self.node_scopes():value=self.contribution(True)
        receipts=self.root/'receipts';receipts.mkdir()
        def lane(name):
            directory=receipts/name;directory.mkdir(exist_ok=True)
            row=dict(lane=name,**{key:self.current[key] for key in ('repository','workflowPath','event','runId','runAttempt','pullRequest')},
                validationCommit=self.current['commit'],validationTree=self.current['tree'],
                toolchain={VALIDATION_ACTIONS_KEY:'metadata,test', 'evidenceScope':apk.SOURCE_CHECK_SCOPE},evidence=[])
            (directory/'lane-receipt.json').write_bytes(apk.canonical_json_bytes(row))
        lane('android');lane('portable')
        options=dict(repository_root=self.root,trusted_workflow_sha='4'*40,artifact_id=22,
            artifact_sha256='sha256:'+'a'*64,contribution_sha256='sha256:'+'b'*64,
            environ=self.env,android=True,node_js=True,parity={'fixture':'locator'})
        for change in ('none','extra-node','missing-android','unselected-node'):
            with self.subTest(change=change), \
                    patch.object(apk,'_authorized_plan',return_value=self.plan_value), \
                    patch('receipt.required_lanes',return_value=['android','node-js','portable']), \
                    patch.object(apk,'observed_validation_contributions',return_value=(value,{'result':'passed'})) as observe, \
                    patch.object(apk,'validate_receipt',side_effect=lambda path,*a,**k:apk.load_json_bytes(path.read_bytes())) as validate, \
                    patch.object(apk,'_check_source_checks'):
                if change=='extra-node':lane('node-js')
                if change=='missing-android':(receipts/'android/lane-receipt.json').unlink()
                if change=='unselected-node':self.plan_value['lanes']['node-js'].update(build=False,test=False)
                destination=self.root/('result-'+change)
                if change=='none':
                    result=apk.aggregate_retained_validation(self.plan,receipts,destination,**options)
                    self.assertEqual({'android','portable'},set(result['laneReceipts']))
                    self.assertEqual('current-validation-contributions',result['kind'])
                    self.assertEqual(('test','metadata'),next(call.kwargs['categories'] for call in validate.call_args_list if 'categories' in call.kwargs))
                    observe.assert_called_once()
                else:
                    with self.assertRaises(ValueError):apk.aggregate_retained_validation(self.plan,receipts,destination,**options)
                    self.assertFalse(destination.exists())
                if change=='extra-node':(receipts/'node-js/lane-receipt.json').unlink()
                if change=='missing-android':lane('android')
                self.plan_value['lanes']['node-js'].update(build=True,test=True)

    def test_current_m11_fresh_and_reused_controls_bind_exact_phases_and_window(self):
        import io,zipfile
        from copy import deepcopy
        from ci import sdk_completion as completion
        from products.registry import NATIVE_BINDINGS
        with self.node_scopes():value=self.contribution()
        expected=value['nodeJs']['parityExpectedPhases']
        observation=dict(run=dict(id=21,head_sha='9'*40,status='in_progress'),jobs=[dict(
            id=5,name='product-validation / sdk-parity / sdk-parity',status='completed',conclusion='success',
            started_at='2026-11-01T10:00:00Z',completed_at='2026-11-01T10:05:00Z')])
        names={'binding-obligations-m11.json','canonical-api.json','canonical-coverage.json',
            *(name+'-parity.json' for name in (*NATIVE_BINDINGS,'kotlin','java','javascript-typescript','swift','objective-c','c-abi'))}
        evidence={name:apk.canonical_json_bytes({'fixture':name}) for name in names}
        sha=lambda raw:apk.sha256_bytes(raw).removeprefix('sha256:')
        report=dict(schemaVersion=2,phase='M11',result='passed',capabilityCount=556,languageCount=11,
            scenarioCount=14,active=6104,pending=0,excluded=12,satisfied=6104,missing=0,
            canonicalApiSha256=sha(evidence['canonical-api.json']),canonicalCoverageSha256=sha(evidence['canonical-coverage.json']),
            evidenceFiles=[dict(path=name,bytes=len(raw),sha256=sha(raw)) for name,raw in sorted(evidence.items())])
        for reused in (False,True):
            for change in ('none','tuple','window','partial-locator','wrong-run','content'):
                with self.subTest(reused=reused,change=change):
                    rows=deepcopy(expected)
                    if change=='tuple':rows[0]['receiptSha256']='sha256:'+'f'*64
                    locator=dict(artifact_id=22,artifact_digest='sha256:'+'1'*64,artifact_run_id=12 if reused else 21,
                        report_artifact_id=23 if reused else None,report_artifact_sha256=None,report_sha256=None)
                    if change=='wrong-run':locator['artifact_run_id']=24
                    if reused:
                        current=completion._repository_report(dict(schemaVersion=1,result='complete',fullReuse=True,
                            phases=rows,matrices=dict(contract=[],runtime=[],sdk=[]),continuationRequirements=[]))
                        current.update(verificationContext=dict(kind='hosted-original-parity-reuse',producer=self.current),
                            sdkParity=dict(result='passed',reportSha256='sha256:'+'d'*64,phaseCount=112,languageCount=11,
                                satisfied=6104,excluded=12,scenarioCount=14,
                                producer=dict(self.current,commit='e'*40,tree='f'*40,runId=12,runAttempt=1),
                                jobId=13,artifactId=22,artifactSha256='sha256:'+'1'*64,
                                policySha256='sha256:'+'2'*64,verifierInputsSha256='sha256:'+'3'*64))
                        raw=apk.canonical_json_bytes(current);members={'hosted-parity-report.json':raw}
                        locator['report_sha256']=apk.sha256_bytes(raw)
                    else:
                        members={**{'m11/'+name:raw for name,raw in evidence.items()},'consumer.log':b'fixture\n',
                            'sdk-parity.json':apk.canonical_json_bytes(report),
                            'original-phase-identities.json':apk.canonical_json_bytes(rows)}
                    if change=='content':members['unexpected']=b'wrong'
                    stream=io.BytesIO()
                    with zipfile.ZipFile(stream,'w') as archive:
                        for name,raw in members.items():archive.writestr(name,raw)
                    uploaded=stream.getvalue();digest=apk.sha256_bytes(uploaded)
                    locator['report_artifact_sha256' if reused else 'artifact_digest']=digest
                    if change=='partial-locator':locator['report_sha256']='sha256:'+'f'*64;locator['report_artifact_id']=None
                    artifact=dict(id=23 if reused else 22,name=('codex-agent-hosted-parity-report-' if reused else
                        'codex-agent-sdk-binding-parity-')+self.current['tree'],digest=digest,size_in_bytes=len(uploaded),
                        expired=False,workflow_run=dict(id=21,head_sha='9'*40),
                        created_at='2026-11-01T09:59:00Z' if change=='window' else '2026-11-01T10:03:00Z',
                        archive_download_url=f'https://api.github.com/repos/codex-agent-labs/codex-agent/actions/artifacts/{23 if reused else 22}/zip')
                    def download(*args,**kwargs):kwargs['destination'].write_bytes(uploaded)
                    with patch.object(apk.products,'api_json',return_value=artifact), \
                            patch.object(apk.products,'_reuse_contract_ci_upload',side_effect=download) as fetch, \
                            patch.object(completion,'_completed_parity',side_effect=AssertionError('no old parity replay')):
                        if change=='none':
                            result=apk._observed_node_parity(self.current,observation,expected,locator,'fixture')
                            self.assertEqual('passed',result['verification']['result']);fetch.assert_called_once()
                        else:
                            with self.assertRaises(ValueError):apk._observed_node_parity(self.current,observation,expected,locator,'fixture')

    def test_shared_observation_authenticates_both_current_jobs_once(self):
        import io,zipfile
        with self.node_scopes():value=self.contribution(True)
        raw=apk.canonical_json_bytes(value);stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as archive:archive.writestr(apk._VALIDATION_FILE,raw)
        uploaded=stream.getvalue();digest=apk.sha256_bytes(uploaded)
        observation=dict(run=dict(id=21,head_sha='9'*40,status='in_progress'),jobs=[dict(
            id=5,name='product-validation / sdk-completion',status='completed',conclusion='success',
            started_at='2026-11-01T10:00:00Z',completed_at='2026-11-01T10:05:00Z')])
        artifact=dict(id=22,name=f"codex-agent-sdk-validation-contributions-{self.current['tree']}-attempt-2",
            digest=digest,size_in_bytes=len(uploaded),expired=False,workflow_run=dict(id=21,head_sha='9'*40),
            created_at='2026-11-01T10:03:00Z',archive_download_url='https://api.github.com/repos/codex-agent-labs/codex-agent/actions/artifacts/22/zip')
        with self.node_scopes(), \
                patch.object(apk.products,'_git_value',side_effect=lambda r,c,v:self.current['tree' if 'tree' in v else 'commit']), \
                patch.object(apk.products,'_observe_ci_producer_jobs',return_value=[observation]) as observe, \
                patch.object(apk.products,'api_json',return_value=artifact), \
                patch.object(apk.products,'_reuse_contract_ci_upload',side_effect=lambda *a,**k:k['destination'].write_bytes(uploaded)) as fetch, \
                patch.object(apk,'_observed_node_parity',return_value={'result':'passed'}) as parity:
            actual=apk.observed_validation_contributions(self.plan,repository_root=self.root,trusted_workflow_sha='4'*40,
                artifact_id=22,artifact_sha256=digest,contribution_sha256=apk.sha256_bytes(raw),environ=self.env,
                android=True,node_js=True,parity={'fixture':'locator'})
        self.assertEqual(value,actual[0]);fetch.assert_called_once();observe.assert_called_once();parity.assert_called_once()
        self.assertEqual({'completion':self.current,'parity':self.current},observe.call_args.args[0])
        self.assertEqual({'completion':{'path':'.github/workflows/product-validation.yml','sha':'4'*40},
            'parity':{'path':'.github/workflows/sdk-binding-parity.yml','sha':'4'*40}},observe.call_args.kwargs['trusted_workflows_by_phase'])


if __name__ == "__main__":
    unittest.main()
