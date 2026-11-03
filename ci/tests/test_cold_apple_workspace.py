"""Cold admission reclaims only unused hosted tools, before artifact transfer."""
import io
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ci.tests import test_sdk_ios_package_upload as uploads


capture = uploads.capture
HOSTED = {
    "CODEX_AGENT_COLD_APPLE_WORKSPACE": "true", "GITHUB_ACTIONS": "true",
    "RUNNER_OS": "Linux", "RUNNER_ENVIRONMENT": "github-hosted", "GITHUB_JOB": "product-resume",
}


class ColdAppleWorkspaceTest(unittest.TestCase):
    def test_insufficient_capacity_stops_before_package_transfer(self):
        fixture = uploads.SdkIosPackageUploadTest()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        with patch.object(capture, "_prepare_cold_apple_workspace",
                          side_effect=ValueError("cold Apple workspace capacity")) as capacity, \
                patch.object(capture, "_reuse_contract_ci_upload", side_effect=AssertionError("body acquired")) as body:
            with self.assertRaisesRegex(ValueError, "cold Apple workspace capacity"):
                fixture.call(compact_recovery=True, environ=HOSTED)
            capacity.assert_called_once()
            body.assert_not_called()
        self.assertFalse(fixture.output.exists())

    def test_no_opt_in_has_no_disk_or_cleanup_cost(self):
        with patch.object(capture.shutil, "disk_usage", side_effect=AssertionError("disk")), \
                patch.object(capture.subprocess, "run", side_effect=AssertionError("cleanup")):
            capture._prepare_cold_apple_workspace(Path("unused"), {}, 1)

    def test_composed_plan_has_the_same_explicit_capacity_preflight(self):
        workflow = (Path(__file__).resolve().parents[2] / ".github/workflows/product-validation.yml").read_text()
        step = workflow.split("      - id: product-reuse\n", 1)[1].split("      - id:", 1)[0]
        self.assertIn("CODEX_AGENT_COLD_APPLE_WORKSPACE: 'true'", step)
        self.assertIn("--native-resume-handoff", step)
        required = 4 * 22_117_834_439 + 8 * 1024**3
        with patch.object(capture.shutil, "disk_usage", return_value=SimpleNamespace(free=required)), \
                patch.object(capture.subprocess, "run") as cleanup, \
                patch("sys.stdout", new=io.StringIO()):
            capture._prepare_cold_apple_workspace(Path("workspace"), {**HOSTED, "GITHUB_JOB": "plan"}, 22_117_834_439)
        cleanup.assert_not_called()

    def test_reclaim_refuses_local_self_hosted_or_other_jobs(self):
        for field in ("GITHUB_ACTIONS", "RUNNER_OS", "RUNNER_ENVIRONMENT", "GITHUB_JOB"):
            with self.subTest(field=field), patch.object(capture.subprocess, "run") as cleanup:
                with self.assertRaisesRegex(ValueError, "hosted product-resume"):
                    capture._prepare_cold_apple_workspace(Path("unused"), {**HOSTED, field: "wrong"}, 1)
                cleanup.assert_not_called()

    def test_existing_capacity_skips_cleanup_and_reclaim_failure_stops(self):
        required = 4 * 22_117_834_439 + 8 * 1024**3
        for before, after, cleans, passes in (
            (required, required, False, True),
            (required - 1, required, True, True),
            (required - 1, required - 1, True, False),
        ):
            with self.subTest(before=before, after=after), \
                    patch.object(capture.shutil, "disk_usage", side_effect=[
                        SimpleNamespace(free=before), SimpleNamespace(free=after)]), \
                    patch.object(capture.subprocess, "run") as cleanup, \
                    patch("sys.stdout", new=io.StringIO()) as output:
                if passes:
                    capture._prepare_cold_apple_workspace(Path("workspace"), HOSTED, 22_117_834_439)
                else:
                    with self.assertRaisesRegex(ValueError, "cold Apple workspace capacity"):
                        capture._prepare_cold_apple_workspace(Path("workspace"), HOSTED, 22_117_834_439)
                self.assertEqual(int(cleans), cleanup.call_count)
                self.assertIn('"requiredFreeBytes":' + str(required), output.getvalue())
                if cleans:
                    command = cleanup.call_args.args[0]
                    self.assertEqual(["sudo", "-n", "rm", "-rf", "--"], command[:5])
                    self.assertEqual({"/usr/local/lib/android", "/usr/share/dotnet", "/opt/ghc",
                                      "/usr/local/.ghcup", "/opt/hostedtoolcache/CodeQL"}, set(command[5:]))
                    self.assertTrue(cleanup.call_args.kwargs["check"])

class QualifiedCoreMetadataWorkspaceTest(unittest.TestCase):
    def qualification(self):
        from reuse_qualification import CompletedFrozenReuse
        from products.registry import PhaseInstanceId, SDK_FACADE_TARGETS
        identities = [PhaseInstanceId('sdk', 'sdk-core', 'package', 'common'),
            *(PhaseInstanceId('sdk', 'sdk-core', 'validation', t) for t in SDK_FACADE_TARGETS)]
        return CompletedFrozenReuse, object.__new__(CompletedFrozenReuse), {
            i: {'state': 'retained'} for i in identities}

    def test_collect_capacity_failure_precedes_body_and_success_uses_one_metadata_get(self):
        from ci.tests.test_sdk_worker_collection import SdkWorkerCollectionTest, PIN
        from ci.tests.test_product_resume_capture import archive
        from products.restore import verification_session
        f = SdkWorkerCollectionTest()
        f.setUp()
        self.addCleanup(f.doCleanups)
        instance, ready, _, expected, files = f.shard('metadata', component='sdk-core', target='common')
        raw = archive(files)
        authority, cap, predecessors = self.qualification()
        state = f.state({instance: ready})
        state.prior_by_instance = predecessors
        environment = {**f.environment, **HOSTED, 'GITHUB_JOB': 'sdk-collect-14',
            'CODEX_AGENT_CORE_METADATA_WORKSPACE': 'true',
            **{name: str(f.repository) for name in ('GITHUB_WORKSPACE', 'RUNNER_TEMP', 'CODEX_SDK_ARCHIVE_CACHE')}}
        required = 2 * len(raw) + 8 * 1024**3
        for enough in (False, True):
            with self.subTest(enough=enough), verification_session(), \
                    patch.object(authority, 'envelope', return_value={}), \
                    patch.object(capture, '_verified_product_state', return_value=state), \
                    patch.object(capture.shutil, 'disk_usage', return_value=SimpleNamespace(free=100*1024**3 if enough else required-1)), \
                    patch.object(capture.subprocess, 'run') as cleanup, \
                    patch('sys.stdout', new=io.StringIO()), \
                    f.official_api({instance: ready}, {instance: raw}) as (query, _, downloaded):
                result = capture.collect_runtime_workers(f.plan_path, f.discovery, f.discovery,
                    f.repository / ('build/capacity-' + str(enough)), trusted_workflow_sha=PIN,
                    repository_root=f.repository, environ=environment, token='synthetic-token',
                    sdk_family='core-metadata', completed_frozen=cap)
                row = result['rows'][0]
                self.assertEqual('success' if enough else 'failure', row['result'], row['reason'])
                self.assertEqual(1, sum('/actions/artifacts/' in call.args[0] for call in query.call_args_list))
                self.assertEqual(int(enough), downloaded.call_count)
                self.assertEqual(int(not enough), cleanup.call_count)
                if enough:
                    shard = f.repository / ('build/capacity-' + str(enough)) / row['shardDirectory']
                    self.assertEqual(expected['receiptBytes'], (shard / 'phase-receipt.json').read_bytes())
                else:
                    self.assertIn('Insufficient qualified Core metadata workspace capacity', row['reason'])

    def test_qualified_gate_rejects_wrong_role_missing_native_and_wrong_volume(self):
        import tempfile
        from products.restore import verification_session
        authority, cap, predecessors = self.qualification()
        with tempfile.TemporaryDirectory() as temporary, verification_session() as session:
            root = Path(temporary).resolve()
            environment = {**HOSTED, 'GITHUB_JOB': 'sdk-collect-14',
                'CODEX_AGENT_CORE_METADATA_WORKSPACE': 'true',
                **{name: str(root) for name in ('GITHUB_WORKSPACE', 'RUNNER_TEMP', 'CODEX_SDK_ARCHIVE_CACHE')}}
            state = SimpleNamespace(prior_by_instance=predecessors)
            with patch.object(authority, 'envelope', return_value={}) as envelope, \
                    patch.object(capture.subprocess, 'run') as cleanup:
                for changed, family, value in (({'GITHUB_JOB': 'plan'}, 'core-metadata', cap),
                        ({'RUNNER_ENVIRONMENT': 'self-hosted'}, 'core-metadata', cap),
                        ({}, 'android-metadata', cap), ({}, 'core-metadata', object())):
                    with self.subTest(changed=changed, family=family), self.assertRaisesRegex(ValueError, 'hosted sdk-collect-14'):
                        capture._prepare_qualified_core_metadata_workspace(root, {**environment, **changed}, state, value, family)
                envelope.return_value = None
                with self.assertRaisesRegex(ValueError, 'eleven validation'):
                    capture._prepare_qualified_core_metadata_workspace(root, environment, state, cap, 'core-metadata')
                envelope.return_value = {}
                capture._prepare_qualified_core_metadata_workspace(root, environment, state, cap, 'core-metadata')
                roots = session['qualifiedCoreMetadataWorkspace']
                differing = SimpleNamespace(is_dir=lambda: True, stat=lambda: SimpleNamespace(st_dev=root.stat().st_dev+1))
                session['qualifiedCoreMetadataWorkspace'] = (*roots, differing)
                with self.assertRaisesRegex(ValueError, 'same volume'), \
                        patch.object(capture.shutil, 'disk_usage', side_effect=AssertionError('disk before volume gate')):
                    capture._require_core_metadata_workspace(session, 1, 'fixture', reclaim=True)
                cleanup.assert_not_called()

    def test_exact_reserve_cleanup_and_later_inventory_budget(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            session = {'qualifiedCoreMetadataWorkspace': (root,)}
            archive = 20_246_282_939
            required = 2 * archive + 8 * 1024**3
            self.assertEqual(49_082_500_470, required)
            for before, after, cleans, passes in ((required, required, False, True),
                    (required-1, required, True, True), (required-1, required-1, True, False)):
                with self.subTest(before=before, after=after), \
                        patch.object(capture.shutil, 'disk_usage', side_effect=[SimpleNamespace(free=before), SimpleNamespace(free=after)]), \
                        patch.object(capture.subprocess, 'run') as cleanup, patch('sys.stdout', new=io.StringIO()) as output:
                    if passes:
                        capture._require_core_metadata_workspace(session, 2*archive, 'outer-download-and-snapshot', reclaim=True)
                    else:
                        with self.assertRaisesRegex(ValueError, 'Insufficient qualified Core metadata'):
                            capture._require_core_metadata_workspace(session, 2*archive, 'outer-download-and-snapshot', reclaim=True)
                    self.assertEqual(int(cleans), cleanup.call_count)
                    self.assertIn('"requiredFreeBytes":49082500470', output.getvalue())
                    self.assertIn('"device":', output.getvalue())
                    if cleans:
                        self.assertEqual(['/usr/local/lib/android', '/usr/share/dotnet', '/opt/ghc',
                            '/usr/local/.ghcup', '/opt/hostedtoolcache/CodeQL'], cleanup.call_args.args[0][5:])
            rows = [{'relativePath': 'worker/gradle.log', 'bytes': 7},
                    {'relativePath': 'shard/phase-receipt.json', 'bytes': 11},
                    {'relativePath': 'originals/validations/jvm/capture/transport.zip', 'bytes': 29},
                    {'relativePath': 'originals/validations/macos-arm64/capture/transport.zip', 'bytes': 31},
                    {'relativePath': 'originals/validations/macos-arm64/capture/original/large', 'bytes': 1_000_000}]
            with patch.object(capture, '_require_core_metadata_workspace') as checked:
                capture._require_core_metadata_projection_space(session, rows, root / 'archive.zip')
            self.assertEqual(4*(7+11) + 2*31, checked.call_args.args[1])
            self.assertEqual('qualified-projection-and-nested-snapshot', checked.call_args.args[2])

    def test_cold_snapshot_and_inventory_hit_keep_authentication_and_capacity_gates(self):
        import tempfile
        from ci.tests.test_product_resume_capture import archive
        from products.restore import verification_session
        from products.registry import PhaseInstanceId
        with tempfile.TemporaryDirectory() as temporary, verification_session() as session:
            root = Path(temporary).resolve()
            path = root / 'metadata.zip'
            path.write_bytes(archive({'worker/execution.json': b'{}\n', 'shard/small': b'x'}))
            identity = {'bytes': path.stat().st_size, 'sha256': capture.sha256_file(path)}
            instance = PhaseInstanceId('sdk', 'sdk-core', 'metadata', 'common')
            session['qualifiedCoreMetadataWorkspace'] = (root,)
            with patch.object(capture.shutil, 'disk_usage', return_value=SimpleNamespace(free=100*1024**3)), \
                    patch.object(capture, 'verified_zip_contents', wraps=capture.verified_zip_contents) as scanner, \
                    patch.object(capture, '_require_core_metadata_workspace', wraps=capture._require_core_metadata_workspace) as checked, \
                    patch('sys.stdout', new=io.StringIO()):
                first = capture._core_metadata_upload_inventory(path, identity, instance)
                self.assertEqual(first, capture._core_metadata_upload_inventory(path, identity, instance))
                self.assertEqual(1, scanner.call_count)
                self.assertEqual(['cold-zip-snapshot', 'qualified-projection-and-nested-snapshot',
                    'qualified-projection-and-nested-snapshot'], [call.args[2] for call in checked.call_args_list])
                path.write_bytes(path.read_bytes() + b'mutation')
                with self.assertRaisesRegex(ValueError, 'changed'):
                    capture._core_metadata_upload_inventory(path, identity, instance)
                self.assertEqual(1, scanner.call_count)

    def test_cold_archive_cache_initializes_after_qualified_gates_and_rejects_symlink(self):
        import tempfile
        from products.restore import verification_session
        authority, cap, predecessors = self.qualification()
        with tempfile.TemporaryDirectory() as temporary, verification_session() as session:
            root = Path(temporary).resolve()
            cache = root / 'sdk-archive-cache-v1'
            env = {**HOSTED, 'GITHUB_JOB': 'sdk-collect-14', 'CODEX_AGENT_CORE_METADATA_WORKSPACE': 'true',
                'GITHUB_WORKSPACE': str(root), 'RUNNER_TEMP': str(root), 'CODEX_SDK_ARCHIVE_CACHE': str(cache)}
            state = SimpleNamespace(prior_by_instance=predecessors)
            with patch.object(authority, 'envelope', return_value={}), \
                    patch.object(capture.subprocess, 'run', side_effect=AssertionError('real cleanup')):
                with self.assertRaisesRegex(ValueError, 'native predecessors'):
                    capture._prepare_qualified_core_metadata_workspace(root, env, state, object(), 'core-metadata')
                self.assertFalse(cache.exists())
                capture._prepare_qualified_core_metadata_workspace(root, env, state, cap, 'core-metadata')
                self.assertTrue(cache.is_dir())
                with patch.object(capture.shutil, 'disk_usage', return_value=SimpleNamespace(free=100*1024**3)), \
                        patch('sys.stdout', new=io.StringIO()):
                    capture._require_core_metadata_workspace(session, 1, 'cold-cache-ready')
                cache.rmdir()
                cache.symlink_to(root, target_is_directory=True)
                with self.assertRaises(ValueError):
                    capture._prepare_qualified_core_metadata_workspace(root, env, state, cap, 'core-metadata')
                cache.unlink()
                env['CODEX_SDK_ARCHIVE_CACHE'] = str(root / 'missing' / '..' / 'cache')
                with self.assertRaises((ValueError, FileNotFoundError)):
                    capture._prepare_qualified_core_metadata_workspace(root, env, state, cap, 'core-metadata')
                self.assertFalse((root / 'cache').exists())

    def test_failed_worker_preserves_official_diagnostics_without_capacity_environment(self):
        from ci.tests.test_sdk_worker_collection import SdkWorkerCollectionTest, PIN
        from ci.tests.test_product_resume_capture import archive
        f = SdkWorkerCollectionTest(); f.setUp(); self.addCleanup(f.doCleanups)
        instance, ready, _, _, files = f.shard('metadata', component='sdk-core', target='common')
        raw = archive(files)
        with patch.object(capture, '_verified_product_state', return_value=f.state({instance: ready})), \
                patch.object(capture, '_prepare_qualified_core_metadata_workspace', side_effect=AssertionError('failed worker capacity')), \
                patch.object(capture.subprocess, 'run', side_effect=AssertionError('cleanup')), \
                f.official_api({instance: ready}, {instance: raw}) as (query, listing, downloaded):
            previous = listing.side_effect
            def failed(url, field, token):
                rows = previous(url, field, token)
                return [{**row, 'conclusion': 'failure'} if field == 'jobs' and row['id'] == 901 else row for row in rows]
            listing.side_effect = failed
            result = capture.collect_runtime_workers(f.plan_path, f.discovery, f.discovery,
                f.repository / 'build/failed-diagnostic', trusted_workflow_sha=PIN, repository_root=f.repository,
                environ={**f.environment, 'CODEX_AGENT_CORE_METADATA_WORKSPACE': 'true'}, token='synthetic-token',
                sdk_family='core-metadata')
            row, = result['rows']
            self.assertEqual('failure', row['result'])
            self.assertIn('did not succeed', row['reason'])
            self.assertEqual(capture.sha256_bytes(raw), row['artifact']['digest'])
            self.assertEqual(901, row['artifact']['id'])
            self.assertEqual(1, sum('/actions/artifacts/' in call.args[0] for call in query.call_args_list))
            self.assertIsNone(row['originalDirectory'])
            downloaded.assert_not_called()

    def test_retained_core_metadata_uses_one_fresh_metadata_get_and_rejects_wrong_digest(self):
        from ci.tests.test_sdk_worker_collection import SdkWorkerCollectionTest, PIN
        from ci.tests.test_product_resume_capture import archive
        from products.restore import verification_session
        f = SdkWorkerCollectionTest(); f.setUp(); self.addCleanup(f.doCleanups)
        instance, ready, _, expected, files = f.shard('metadata', component='sdk-core', target='common')
        raw = archive(files); original = dict(f.producer)
        artifact_name = f.names(instance, ready['buildKey'])[1]
        child = '.github/workflows/sdk-core-metadata-validation.yml'
        job_name = 'product-validation / sdk-core-metadata-wave / sdk-core-metadata-common'
        f.producer = {**original, 'runId': 8, 'runAttempt': 1, 'commit': 'd'*40, 'tree': 'e'*40}
        authority, cap, predecessors = self.qualification()
        state = f.state({instance: ready}); state.prior_by_instance = predecessors
        env = {**f.environment, **HOSTED, 'GITHUB_RUN_ID': '8', 'GITHUB_RUN_ATTEMPT': '1',
            'GITHUB_JOB': 'sdk-collect-14', 'CODEX_AGENT_CORE_METADATA_WORKSPACE': 'true',
            'GITHUB_WORKSPACE': str(f.repository), 'RUNNER_TEMP': str(f.repository),
            'CODEX_SDK_ARCHIVE_CACHE': str(f.repository / 'cold-cache')}
        origin = {'producer': original, 'artifact_id': 901, 'artifact_sha256': capture.sha256_bytes(raw),
            'job_id': 901, 'workflow_sha': 'f'*40, 'workflow_path': child, 'job_name': job_name}
        original_job = {'id': 901, 'name': job_name, 'run_id': original['runId'], 'head_sha': original['commit'],
            'status': 'completed', 'conclusion': 'success', 'started_at': '2026-09-08T10:00:00Z',
            'completed_at': '2026-09-08T10:10:00Z'}
        observe = capture._observe_ci_producer_jobs
        def observed(producers, **kwargs):
            if 'worker' not in producers: return observe(producers, **kwargs)
            self.assertEqual(original, producers['worker'])
            self.assertEqual({'worker': {'path': child, 'sha': origin['workflow_sha']}}, kwargs['trusted_workflows_by_phase'])
            return [{'run': {'head_sha': original['commit']}, 'jobs': [original_job]}]
        (f.repository / 'cold-cache').mkdir()
        for wrong in (False, True):
            with self.subTest(wrong=wrong), verification_session(), \
                    patch.object(authority, 'envelope', return_value={}), \
                    patch.object(capture, '_verified_product_state', return_value=state), \
                    patch('sdk_campaign_original_locator.retained_core_origin', return_value=origin), \
                    patch.object(capture, '_observe_ci_producer_jobs', side_effect=observed), \
                    patch('sdk_handoff._ensure_observed_sdk_commit'), \
                    patch.object(capture.shutil, 'disk_usage', return_value=SimpleNamespace(free=100*1024**3)), \
                    patch.object(capture.subprocess, 'run', side_effect=AssertionError('cleanup')), \
                    patch('sys.stdout', new=io.StringIO()), \
                    f.official_api({instance: ready}, {instance: raw}) as (query, _, downloaded):
                previous = query.side_effect
                def metadata(url, token):
                    value = previous(url, token)
                    if '/actions/artifacts/' in url:
                        return {**value, 'name': artifact_name, 'digest': 'sha256:'+'0'*64 if wrong else origin['artifact_sha256'],
                            'workflow_run': {'id': original['runId'], 'head_sha': original['commit']}}
                    if url.endswith('/attempts/1'):
                        return {**value, 'referenced_workflows': [*value['referenced_workflows'],
                            {'path': f"{f.producer['repository']}/{child}@{PIN}", 'sha': PIN}]}
                    return value
                query.side_effect = metadata
                destination = f.repository / ('build/retained-capacity-' + str(wrong))
                result = capture.collect_runtime_workers(f.plan_path, f.discovery, f.discovery, destination,
                    trusted_workflow_sha=PIN, repository_root=f.repository, environ=env, token='synthetic-token',
                    sdk_family='core-metadata', sdk_worker_workflow_path=child, sdk_worker_job_name=job_name,
                    completed_frozen=cap)
                row, = result['rows']
                self.assertEqual('failure' if wrong else 'success', row['result'], row['reason'])
                self.assertEqual(1, sum('/actions/artifacts/' in call.args[0] for call in query.call_args_list))
                self.assertEqual(int(not wrong), downloaded.call_count)
                if wrong:
                    self.assertIn('caller-bound transport identity', row['reason'])
                    self.assertIsNone(row['artifact'])
                else:
                    self.assertEqual(original['runId'], row['artifact']['workflow_run']['id'])
                    self.assertEqual(expected['receiptBytes'], (destination / row['shardDirectory'] / 'phase-receipt.json').read_bytes())
                    self.assertTrue((f.repository / 'cold-cache').is_dir())



if __name__ == "__main__":
    unittest.main()
