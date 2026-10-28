"""Original upload authentication with synthetic products; HTTP is the only mock."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from ci.tests import test_contract_ci_originals as fixture
from ci.tests.test_products import phase_receipt
from products.inventory import publish_regular_tree as actual_publish_regular_tree
from products.registry import PhaseInstanceId

adapter = fixture.product_reuse
TARGET = "linux-x64"


class RuntimeOriginalCiTest(unittest.TestCase):
    api = fixture.ContractOriginalCiCaptureTest.api

    def test_current_runtime_publisher_remains_exactly_admitted_after_rotation(self):
        for publisher in ("d2243aac89368df2776b6617fd5a623bd6754cb2",
                          "a1cbc80b15a96cb2915d06afe1e29e319dda52fc"):
            reference = {"path": f"{fixture.REPOSITORY}/.github/workflows/product-validation.yml@reuse-authority",
                         "ref": "refs/heads/reuse-authority", "sha": publisher}
            run = {"referenced_workflows": [reference]}
            self.assertEqual(publisher, adapter._runtime_prior_workflow_sha(run, "a" * 40))
            for changed in ({"sha": "b" * 40}, {"ref": "refs/heads/unreviewed"},
                            {"path": "other/repository/.github/workflows/product-validation.yml@reuse-authority"}):
                with self.subTest(changed=changed):
                    self.assertIsNone(adapter._runtime_prior_workflow_sha(
                        {"referenced_workflows": [{**reference, **changed}]}, "a" * 40))

    def download_fixture(self, artifact, token, destination, **_):
        phase = next(phase for phase, value in self.artifacts.items() if value["id"] == artifact["id"])
        Path(destination).write_bytes(self.archives[phase])

    def setUp(self):
        # Reuse the real original-CI run/attempt/commit/HTTP fixture, not a
        # mocked observer or shard verifier. No native execution is claimed.
        fixture.ContractOriginalCiCaptureTest.setUp(self)
        # Persistent bytes and verifier-owned authority are separate, disposable
        # roots in tests; no test reads or writes the user's machine authority.
        for name, value in (("_authority_root", self.root / "authority"),
                            ("native_cache_root", self.root / "persistent-cache")):
            patch = mock.patch(f"products.verified_evidence.{name}", return_value=value)
            patch.start()
            self.addCleanup(patch.stop)
        self.receipts = {}
        self.jobs = []
        from products.receipt import compute_build_key, write_output_manifest
        for index, phase in enumerate(fixture.PHASES, 101):
            stage = self.root / "runtime-stages" / phase
            (stage / "outputs").mkdir(parents=True)
            (stage / "outputs/value.bin").write_bytes(f"synthetic {phase}\n".encode())
            write_output_manifest(stage, "runtime", TARGET, phase, TARGET, "0.2.0", {"binary": "outputs"})
            identity = {"product": "runtime", "component": TARGET, "phase": phase, "target": TARGET}
            inputs = phase_receipt()["inputs"]
            plan = {"schemaVersion": 1, **identity, "inputs": inputs,
                    "buildKey": compute_build_key(**identity, inputs=inputs)}
            upload = self.root / "runtime-uploads" / phase
            fixture.finalize_phase_object(stage_root=stage, phase_plan=plan, producer=self.producer,
                product_version="0.2.0", trust_domain="development", destination=upload / "shard")
            self.receipts[phase] = upload / "shard/phase-receipt.json"
            raw = fixture.archive_tree(upload)
            name = (f"codex-agent-runtime-worker-{TARGET}-{phase}-{TARGET}-"
                    f"{plan['buildKey'][7:]}-{self.producer['tree']}-attempt-2")
            self.artifacts[phase].update(name=name, digest=fixture.sha256_bytes(raw), size_in_bytes=len(raw))
            self.archives[phase] = raw
            self.jobs.append({"id": index, "name": f"product-validation / runtime-{TARGET}-{phase}-{TARGET}",
                "run_id": 71, "head_sha": self.run["head_sha"], "status": "completed", "conclusion": "success",
                "started_at": "2026-09-06T10:00:00Z", "completed_at": "2026-09-06T10:30:00Z"})

    def test_native_artifact_batch_keeps_full_metadata_checks_and_fresh_scope(self):
        sources = [{"receipt": json.loads(self.receipts[phase].read_bytes()),
                    "artifactId": self.artifacts[phase]["id"]} for phase in fixture.PHASES]
        rows = list(self.artifacts.values())
        def read(url, token):
            if "/runs/" in url:
                return {"total_count": len(rows), "artifacts": copy.deepcopy(rows)}
            return copy.deepcopy(next(row for row in self.artifacts.values()
                                      if url.endswith('/' + str(row['id']))))
        def metadata(phase, *, token='fixture', run=None):
            original = self.artifacts[phase]
            return adapter._contract_ci_upload_metadata(original['id'], original['digest'],
                original['name'], self.producer, self.run if run is None else run, token)

        with mock.patch.object(adapter, 'api_json', side_effect=read) as api:
            with adapter._ci_observation_batch():
                adapter._prime_runtime_artifact_metadata(sources, 'fixture')
                for phase in fixture.PHASES:
                    self.assertEqual(self.artifacts[phase], metadata(phase))
                self.assertEqual(1, api.call_count)
                metadata('binary')['expired'] = True
                self.assertFalse(metadata('binary')['expired'])
                metadata('binary', token='different-token')
                metadata('binary', run={**self.run, 'status': 'in_progress'})
                self.assertEqual(3, api.call_count)
            metadata('binary')
            self.assertEqual(4, api.call_count)
            with adapter._ci_observation_batch(tuple(str(self.producer[k]) for k in ('runId', 'runAttempt'))):
                adapter._prime_runtime_artifact_metadata(sources, 'fixture')
                metadata('binary')
                self.assertEqual(6, api.call_count)
            with adapter._ci_observation_batch():
                rows = [{**self.artifacts['binary'], 'expired': True}]
                adapter._prime_runtime_artifact_metadata(sources, 'fixture')
                with self.assertRaisesRegex(ValueError, 'caller-bound transport identity'):
                    metadata('binary')

    def test_native_artifact_batch_falls_back_for_absence_and_rejects_malformed_or_changed_metadata(self):
        sources = [{"receipt": json.loads(self.receipts[phase].read_bytes()),
                    "artifactId": self.artifacts[phase]['id']} for phase in fixture.PHASES]
        first = self.artifacts['binary']
        def metadata():
            return adapter._contract_ci_upload_metadata(first['id'], first['digest'], first['name'],
                self.producer, self.run, 'fixture')
        with adapter._ci_observation_batch(), mock.patch.object(adapter, 'api_json',
                side_effect=[{'total_count': 101, 'artifacts': []}, first]) as api:
            adapter._prime_runtime_artifact_metadata(sources, 'fixture')
            self.assertEqual(first, metadata())
            self.assertEqual(2, api.call_count)
        with adapter._ci_observation_batch(), mock.patch.object(adapter, 'api_json', return_value=first) as api:
            adapter._prime_runtime_artifact_metadata(sources[:1], 'fixture')
            api.assert_not_called()
            metadata()
            api.assert_called_once()
        malformed = ({'total_count': 2, 'artifacts': [first, first]},
                     {'total_count': 0, 'artifacts': [first]},
                     {'total_count': '1', 'artifacts': [first]},
                     {'total_count': 1, 'artifacts': [{'id': True}]})
        for response in malformed:
            with self.subTest(response=response), adapter._ci_observation_batch(), \
                    mock.patch.object(adapter, 'api_json', return_value=response), self.assertRaises(ValueError):
                adapter._prime_runtime_artifact_metadata(sources, 'fixture')
        for field, value in (('digest', 'sha256:' + '0' * 64), ('name', 'wrong'), ('expired', True),
                ('size_in_bytes', 0), ('archive_download_url', 'https://wrong.invalid/zip'),
                ('workflow_run', {**first['workflow_run'], 'id': 999})):
            with self.subTest(field=field), adapter._ci_observation_batch(), \
                    mock.patch.object(adapter, 'api_json', return_value={
                        'total_count': 1, 'artifacts': [{**first, field: value}]}):
                adapter._prime_runtime_artifact_metadata(sources, 'fixture')
                with self.assertRaises(ValueError):
                    metadata()
        with adapter._ci_observation_batch(), mock.patch.object(adapter, 'api_json') as api, \
                self.assertRaisesRegex(ValueError, 'conflicting runs'):
            adapter._prime_runtime_artifact_metadata([sources[0], {**sources[0], 'receipt': {
                **sources[0]['receipt'], 'producer': {**self.producer, 'runId': 999}}}], 'fixture')
        api.assert_not_called()

    def test_single_artifact_metadata_is_shared_without_sharing_admission(self):
        from products.restore import bounded_verify
        original = self.artifacts['binary']
        def metadata(*, token='fixture', run=None, **changes):
            expected = {**original, **changes}
            return adapter._contract_ci_upload_metadata(original['id'], expected['digest'],
                expected['name'], self.producer, self.run if run is None else run, token)
        with mock.patch.object(adapter, 'api_json', return_value=original) as api:
            with adapter._ci_observation_batch():
                self.assertEqual([original] * 8, bounded_verify(lambda _: metadata(), range(8)))
                self.assertEqual(1, api.call_count)
                metadata()['expired'] = True
                self.assertFalse(metadata()['expired'])
                for changes in ({'digest': 'sha256:' + '0' * 64}, {'name': 'wrong'}):
                    with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, 'caller-bound'):
                        metadata(**changes)
                with self.assertRaisesRegex(ValueError, 'caller-bound'):
                    metadata(run={**self.run, 'head_sha': '0' * 40})
                self.assertEqual(1, api.call_count)
                metadata(token='different-token')
                self.assertEqual(2, api.call_count)
                for _ in range(2):
                    metadata(run={**self.run, 'status': 'in_progress'})
                self.assertEqual(4, api.call_count)
            metadata()
            with adapter._ci_observation_batch():
                metadata()
            self.assertEqual(6, api.call_count)
            with adapter._ci_observation_batch(tuple(str(self.producer[k]) for k in ('runId', 'runAttempt'))):
                metadata()
                metadata()
            self.assertEqual(8, api.call_count)
        with adapter._ci_observation_batch(), mock.patch.object(adapter, 'api_json',
                side_effect=[OSError('unavailable'), original]) as api:
            with self.assertRaisesRegex(OSError, 'unavailable'):
                metadata()
            self.assertEqual(original, metadata())
            self.assertEqual(2, api.call_count)

    def test_native_job_lookup_preserves_every_fresh_identity_gate(self):
        job = {**self.jobs[0], 'run_attempt': 2}
        name = job['name']
        original = self.api()
        def http(url, token):
            if url.endswith('/actions/jobs/101'):
                return json.dumps(job).encode()
            return original(url, token)
        def observe(**changes):
            options = dict(jobs_by_phase={'binary': name}, trusted_workflow_sha=self.pin,
                           token='not-a-real-token', native_job_ids_by_phase={'binary': 101})
            return adapter._observe_ci_producer_jobs({'binary': self.producer}, **{**options, **changes})
        with mock.patch('reuse.api_request', side_effect=http) as api:
            self.assertEqual([job], observe()[0]['jobs'])
            self.assertFalse(any('/jobs?' in call.args[0] for call in api.call_args_list))
            for field, value in (('id', 102), ('run_attempt', 1), ('run_attempt', None),
                                 ('run_id', 72), ('head_sha', '0' * 40), ('name', 'unrelated'),
                                 ('status', 'in_progress'), ('conclusion', 'failure')):
                before = job[field]
                job[field] = value
                with self.subTest(job=field, value=value), self.assertRaises(ValueError):
                    observe()
                job[field] = before
            for field, value in (('status', 'in_progress'), ('run_attempt', 1), ('event', 'workflow_dispatch')):
                before = self.run[field]
                self.run[field] = value
                with self.subTest(run=field), self.assertRaises(ValueError):
                    observe()
                self.run[field] = before
            before = self.commit['tree']
            self.commit['tree'] = {'sha': '0' * 40}
            with self.assertRaisesRegex(ValueError, 'commit/tree'):
                observe()
            self.commit['tree'] = before
            with self.assertRaisesRegex(ValueError, 'workflow'):
                observe(trusted_workflow_sha='0' * 40)
            job['name'] = f"{name} (sha256:{'b' * 64}, ..."
            observe(build_keys_by_phase={'binary': 'sha256:' + 'b' * 64})
            with self.assertRaisesRegex(ValueError, 'ambiguous'):
                observe(build_keys_by_phase={'binary': 'sha256:' + 'a' * 64})
            job['name'] = name
            for pins in ({'binary': True}, {'binary': 0}, {'other': 101}):
                with self.subTest(pins=pins), self.assertRaises(ValueError):
                    observe(native_job_ids_by_phase=pins)

    def test_native_job_observation_cannot_replace_full_selection_or_cross_scope(self):
        job = {**self.jobs[0], 'run_attempt': 2}
        name = job['name']
        original = self.api()
        def http(url, token):
            if url.endswith('/actions/jobs/101'):
                return json.dumps(job).encode()
            return original(url, 'not-a-real-token')
        def observe(*, native=True, token='not-a-real-token', pin=None):
            return adapter._observe_ci_producer_jobs({'binary': self.producer},
                jobs_by_phase={'binary': name}, trusted_workflow_sha=self.pin if pin is None else pin, token=token,
                **({'native_job_ids_by_phase': {'binary': 101}} if native else {}))
        with mock.patch('reuse.api_request', side_effect=http) as api:
            with adapter._ci_observation_batch():
                observed = observe()
                observed[0]['jobs'][0]['conclusion'] = 'failure'
                self.assertEqual('success', observe()[0]['jobs'][0]['conclusion'])
                self.assertEqual(1, sum('/actions/jobs/101' in c.args[0] for c in api.call_args_list))
                with self.assertRaisesRegex(ValueError, 'workflow'):
                    observe(pin='0' * 40)
                observe(token='other-token')
                self.assertEqual(2, sum('/actions/jobs/101' in c.args[0] for c in api.call_args_list))
                # A first-time/full selector still rejects ambiguous names;
                # the sealed native identity never supplies its partial list.
                self.jobs.append({**self.jobs[0], 'id': 999})
                with self.assertRaisesRegex(ValueError, 'ambiguous'):
                    observe(native=False)
                self.assertTrue(any('/jobs?' in c.args[0] for c in api.call_args_list))
                self.jobs.pop()
            api.reset_mock()
            with adapter._ci_observation_batch(('71', '2')):
                observe()
                observe()
            self.assertEqual(2, sum('/actions/jobs/101' in c.args[0] for c in api.call_args_list))

    def test_full_graph_metadata_reuses_completed_observations_without_sharing_verdicts(self):
        jobs = [{**self.jobs[0], 'id': 1000 + index, 'run_attempt': 2,
                 'name': f'product-validation / capacity-{index}'} for index in range(112)]
        artifacts = [{**self.artifacts['binary'], 'id': 2000 + index,
                      'name': f'capacity-{index}',
                      'archive_download_url': f'https://api.github.com/repos/{fixture.REPOSITORY}/actions/artifacts/{2000 + index}/zip'}
                     for index in range(112)]
        original = self.api()
        def http(url, token):
            if '/actions/jobs/' in url:
                return json.dumps(next(job for job in jobs if url.endswith('/' + str(job['id'])))).encode()
            if '/actions/artifacts/' in url:
                return json.dumps(next(row for row in artifacts if url.endswith('/' + str(row['id'])))).encode()
            return original(url, token)
        def observe(job, pin=None):
            return adapter._observe_ci_producer_jobs({'original': self.producer},
                jobs_by_phase={'original': job['name']}, trusted_workflow_sha=pin or self.pin,
                token='not-a-real-token', native_job_ids_by_phase={'original': job['id']})
        def metadata(row, digest=None):
            return adapter._contract_ci_upload_metadata(row['id'], digest or row['digest'], row['name'],
                self.producer, self.run, 'not-a-real-token')
        self.measurements = []
        with mock.patch('reuse.api_request', side_effect=http) as requests:
            for invocation in (1, 2):
                with adapter._ci_observation_batch(('100', '1')):
                    for pass_number in (1, 2):
                        before = requests.call_count
                        for job, row in zip(jobs, artifacts):
                            self.assertEqual(job['id'], observe(job)[0]['jobs'][0]['id'])
                            self.assertEqual(row, metadata(row))
                        self.measurements.append({'invocation': invocation, 'pass': pass_number,
                            'httpRequests': requests.call_count - before,
                            'cachedKeys': len(adapter._CI_OBSERVATIONS.get()['observationGuards'][1])})
                        self.assertEqual(226 if pass_number == 1 else 0, requests.call_count - before)
                    with self.assertRaises(ValueError):
                        observe(jobs[-1], pin='0' * 40)
                    with self.assertRaises(ValueError):
                        metadata(artifacts[-1], digest='sha256:' + '0' * 64)
                    observe(jobs[-1])[0]['jobs'][0]['id'] = -1
                    self.assertEqual(jobs[-1]['id'], observe(jobs[-1])[0]['jobs'][0]['id'])
                self.assertIsNone(adapter._CI_OBSERVATIONS.get())

    def test_large_observation_batch_keeps_a_fixed_bound_and_fresh_overflow(self):
        fetched = []
        def read(key):
            def fetch():
                fetched.append(key)
                return {'run': {'status': 'completed'}, 'key': key}
            return adapter._historical_ci_observation(adapter._CI_OBSERVATIONS.get(), key, ('71', '2'), fetch)
        with adapter._ci_observation_batch(('100', '1')):
            for key in range(512):
                self.assertEqual(key, read(key)['key'])
            self.assertEqual(512, len(adapter._CI_OBSERVATIONS.get()['observationGuards'][1]))
            read(511)['key'] = 'mutated'
            self.assertEqual(511, read(511)['key'])
            for _ in range(2):
                self.assertEqual('overflow', read('overflow')['key'])
            self.assertEqual(2, fetched.count('overflow'))
            self.assertEqual(512, len(adapter._CI_OBSERVATIONS.get()['observationGuards'][1]))
        self.assertIsNone(adapter._CI_OBSERVATIONS.get())

    def test_distinct_native_jobs_share_tested_commit_only_in_private_batch(self):
        from products.restore import bounded_verify
        original = self.api()
        jobs = [{**job, 'run_attempt': 2} for job in self.jobs]
        def http(url, token):
            if '/actions/jobs/' in url:
                return json.dumps(next(job for job in jobs if url.endswith('/' + str(job['id'])))).encode()
            return original(url, token)
        def observe(job):
            return adapter._observe_ci_producer_jobs({'original': self.producer},
                jobs_by_phase={'original': job['name']}, trusted_workflow_sha=self.pin,
                token='not-a-real-token', native_job_ids_by_phase={'original': job['id']})
        for current, expected in ((None, 1), (('71', '2'), len(jobs))):
            with self.subTest(current=current), mock.patch('reuse.api_request', side_effect=http) as api:
                for batch in range(2):
                    with adapter._ci_observation_batch(current):
                        results = bounded_verify(observe, jobs)
                        self.assertEqual([job['id'] for job in jobs],
                                         [result[0]['jobs'][0]['id'] for result in results])
                        results[0][0]['testedCommit']['tree']['sha'] = '0' * 40
                        self.assertEqual(self.producer['tree'], observe(jobs[0])[0]['testedCommit']['tree']['sha'])
                    self.assertEqual((batch + 1) * (expected + int(current is not None)),
                        sum('/git/commits/' in call.args[0] for call in api.call_args_list))
                    self.assertEqual((batch + 1) * (len(jobs) + int(current is not None)),
                        sum('/actions/jobs/' in call.args[0] for call in api.call_args_list))

    def test_shared_tested_commit_revalidates_every_callers_exact_pins(self):
        arguments = dict(api='https://api.github.com', repository=self.producer['repository'],
            token='fixture', expected_commit=self.producer['commit'],
            expected_tree=self.producer['tree'], pull_request=31)
        with adapter._ci_observation_batch(), mock.patch.object(adapter, 'api_json',
                return_value=self.commit) as api:
            adapter._observe_tested_commit(self.run, **arguments)
            for changes in ({'expected_tree': '0' * 40}, {'pull_request': 32}):
                with self.subTest(changes=changes), self.assertRaises(ValueError):
                    adapter._observe_tested_commit(self.run, **{**arguments, **changes})
            self.assertEqual(1, api.call_count)
            adapter._observe_tested_commit(self.run, **{**arguments, 'token': 'different'})
            self.assertEqual(2, api.call_count)
            for _ in range(2):
                adapter._observe_tested_commit({**self.run, 'status': 'in_progress'}, **arguments)
            self.assertEqual(4, api.call_count)

    def test_operation_batch_binds_positional_environment_and_never_leaks(self):
        prior_context = adapter._CI_OBSERVATIONS.get()
        @adapter._fresh_ci_observations
        def read(environment, *, fail=False):
            for _ in range(2):
                adapter._observe_ci_producer_jobs({'binary': self.producer},
                    jobs_by_phase={'binary': self.jobs[0]['name']}, trusted_workflow_sha=self.pin,
                    token='not-a-real-token')
            if fail:
                raise ValueError('after observations')
        for keyword in (False, True):
            for current, expected in (('72', 1), ('71', 2)):
                environment = {'GITHUB_RUN_ID': current, 'GITHUB_RUN_ATTEMPT': '2'}
                with self.subTest(keyword=keyword, current=current), \
                        mock.patch('reuse.api_request', side_effect=self.api()) as http:
                    for fail in (False, True):
                        arguments = {'environment': environment} if keyword else {}
                        positional = () if keyword else (environment,)
                        if fail:
                            with self.assertRaisesRegex(ValueError, 'after observations'):
                                read(*positional, **arguments, fail=True)
                        else:
                            read(*positional, **arguments)
                        calls = [c for c in http.call_args_list
                                 if c.args[0].endswith('/actions/runs/71/attempts/2')]
                        self.assertEqual(expected * (2 if fail else 1), len(calls))
                        self.assertIs(prior_context, adapter._CI_OBSERVATIONS.get())

    def test_sdk_command_composes_completed_observations_only_for_its_current_consumer(self):
        from ci import sdk_workflow
        self.assertIs(adapter, sdk_workflow.product_reuse)
        prior_context = adapter._CI_OBSERVATIONS.get()
        argv = ['matrix', '--plan', str(self.root / 'plan'),
                '--discovery-root', str(self.root / 'discovery'),
                '--state-root', str(self.root / 'state'), '--github-output', str(self.root / 'output')]

        @adapter._fresh_ci_observations
        def read(environment):
            for _ in range(2):
                adapter._observe_ci_producer_jobs({'binary': self.producer},
                    jobs_by_phase={'binary': self.jobs[0]['name']}, trusted_workflow_sha=self.pin,
                    token='not-a-real-token')

        for current, child, status, expected in (
                ('72', '72', 'completed', 1), ('71', '71', 'completed', 4),
                ('72', '72', 'in_progress', 4), ('72', '73', 'completed', 2),
                (None, None, 'completed', 2)):
            environment = {} if current is None else {'GITHUB_RUN_ID': current, 'GITHUB_RUN_ATTEMPT': '2'}
            nested = {} if child is None else {'GITHUB_RUN_ID': child, 'GITHUB_RUN_ATTEMPT': '2'}
            def dispatch(**_):
                read(nested)
                read(nested)
            with self.subTest(current=current, child=child, status=status), \
                    mock.patch.dict(os.environ, environment, clear=True), \
                    mock.patch('reuse.api_request', side_effect=self.api(run={**self.run, 'status': status})) as http, \
                    mock.patch.object(sdk_workflow, 'matrix', side_effect=dispatch):
                for invocation in (1, 2):
                    self.assertEqual(0, sdk_workflow.main(argv))
                    calls = [call for call in http.call_args_list
                             if call.args[0].endswith('/actions/runs/71/attempts/2')]
                    self.assertEqual(expected * invocation, len(calls))
                    self.assertIs(prior_context, adapter._CI_OBSERVATIONS.get())

        with mock.patch.dict(os.environ, {'GITHUB_RUN_ID': '72', 'GITHUB_RUN_ATTEMPT': '2'}), \
                mock.patch.object(sdk_workflow, 'matrix', side_effect=RuntimeError('failed acquisition')):
            with self.assertRaisesRegex(RuntimeError, 'failed acquisition'):
                sdk_workflow.main(argv)
        self.assertIs(prior_context, adapter._CI_OBSERVATIONS.get())

    def test_completion_and_parity_share_only_same_consumer_historical_observations(self):
        from contextlib import contextmanager, redirect_stdout, redirect_stderr
        import io
        from ci import sdk_completion
        self.assertIs(adapter, sdk_completion.products)
        prior_context = adapter._CI_OBSERVATIONS.get()
        argv = ['--plan', str(self.root / 'plan'), '--discovery-root', str(self.root / 'discovery'),
                '--state-root', str(self.root / 'state'), '--repository-root', str(self.root),
                '--completed-frozen-policy', str(self.root / 'policy')]
        self.measurements = []

        @adapter._fresh_ci_observations
        def read(environment, *, workflow=None):
            for _ in range(2):
                adapter._observe_ci_producer_jobs({'binary': self.producer},
                    jobs_by_phase={'binary': self.jobs[0]['name']},
                    trusted_workflow_sha=self.pin if workflow is None else workflow,
                    token='not-a-real-token')

        for mode, verifier in (('completion', 'require_sdk_completion'),
                               ('parity', 'require_hosted_sdk_parity')):
            command = argv + (['--hosted-parity', '--parity-policy', str(self.root / 'parity')]
                              if mode == 'parity' else [])
            for current, child, status, expected in (
                    ('72', '72', 'completed', 1), ('71', '71', 'completed', 4),
                    ('72', '72', 'in_progress', 4), ('72', '73', 'completed', 2),
                    (None, None, 'completed', 2), ('invalid', 'invalid', 'completed', 2)):
                environment = {} if current is None else {'GITHUB_RUN_ID': current, 'GITHUB_RUN_ATTEMPT': '2'}
                nested = {} if child is None else {'GITHUB_RUN_ID': child, 'GITHUB_RUN_ATTEMPT': '2'}

                @contextmanager
                def authority(_):
                    read(nested)
                    yield {}  # Real observation batching; semantic admission is a separate fixture boundary.

                def verify(*_, **__):
                    read(nested)
                    return {'result': 'fixture-only'}

                with self.subTest(mode=mode, current=current, child=child, status=status), \
                        mock.patch.dict(os.environ, environment, clear=True), \
                        mock.patch('reuse.api_request', side_effect=self.api(run={**self.run, 'status': status})) as http, \
                        mock.patch.object(sdk_completion, 'completed_frozen_options', authority), \
                        mock.patch.object(sdk_completion, verifier, side_effect=verify), \
                        redirect_stdout(io.StringIO()):
                    for invocation in (1, 2):
                        before = http.call_count
                        self.assertEqual(0, sdk_completion.main(command))
                        calls = [call for call in http.call_args_list
                                 if call.args[0].endswith('/actions/runs/71/attempts/2')]
                        self.measurements.append(dict(mode=mode, current=current, child=child,
                            status=status, invocation=invocation, totalHttpRequests=http.call_count - before,
                            cumulativeAttemptRequests=len(calls)))
                        self.assertEqual(expected * invocation, len(calls))
                        self.assertIs(prior_context, adapter._CI_OBSERVATIONS.get())

            for failure in ('wrong-workflow', 'consumer-error'):
                @contextmanager
                def authority(_):
                    read({'GITHUB_RUN_ID': '72', 'GITHUB_RUN_ATTEMPT': '2'})
                    yield {}

                def fail(*_, **__):
                    if failure == 'consumer-error':
                        raise RuntimeError('consumer failed after observation')
                    read({'GITHUB_RUN_ID': '72', 'GITHUB_RUN_ATTEMPT': '2'}, workflow='0' * 40)

                output = io.StringIO()
                with self.subTest(mode=mode, failure=failure), \
                        mock.patch.dict(os.environ, {'GITHUB_RUN_ID': '72', 'GITHUB_RUN_ATTEMPT': '2'}, clear=True), \
                        mock.patch('reuse.api_request', side_effect=self.api()), \
                        mock.patch.object(sdk_completion, 'completed_frozen_options', authority), \
                        mock.patch.object(sdk_completion, verifier, side_effect=fail), \
                        redirect_stdout(output), redirect_stderr(io.StringIO()), \
                        self.assertRaises(SystemExit if failure == 'wrong-workflow' else RuntimeError):
                    sdk_completion.main(command)
                self.assertEqual('', output.getvalue())
                self.assertIs(prior_context, adapter._CI_OBSERVATIONS.get())

    def test_completed_attempt_observations_are_shared_only_inside_one_operation(self):
        from products.restore import verification_session
        with mock.patch('reuse.api_request', side_effect=self.api()) as http:
            with verification_session(), adapter._ci_observation_batch():
                for index, phase in enumerate(fixture.PHASES):
                    adapter._observe_ci_producer_jobs({phase: self.producer},
                        jobs_by_phase={phase: self.jobs[index]['name']}, trusted_workflow_sha=self.pin,
                        token='not-a-real-token')
                    if index == 0:
                        first = http.call_count
                    self.assertEqual(first, http.call_count)
                with self.assertRaises(ValueError):
                    adapter._observe_ci_producer_jobs({'binary': self.producer},
                        jobs_by_phase={'binary': self.jobs[0]['name']}, trusted_workflow_sha='0' * 40,
                        token='not-a-real-token')
            adapter._observe_ci_producer_jobs({'binary': self.producer},
                jobs_by_phase={'binary': self.jobs[0]['name']}, trusted_workflow_sha=self.pin,
                token='not-a-real-token')
            self.assertEqual(2 * first, http.call_count)

    def test_predecessor_restoration_batches_only_historical_reads_and_rechecks_each_operation(self):
        """Real object restoration; synthetic acquisition uses the real HTTP observer."""
        from types import SimpleNamespace
        records, objects = {}, {}
        for phase in fixture.PHASES:
            raw = self.receipts[phase].read_bytes()
            receipt = fixture.load_canonical_json_bytes(raw)
            identity = adapter._identity(receipt)
            path = self.receipts[phase].parent / adapter.object_relative_path(
                receipt['buildKey'], fixture.sha256_bytes(raw))
            objects[identity] = path.read_bytes()
            records[identity] = {**adapter._identity_record(identity), 'buildKey': receipt['buildKey'],
                'receiptSha256': fixture.sha256_bytes(raw), 'objectSha256': fixture.sha256_bytes(objects[identity])}
        for current, status in ((False, 'completed'), (True, 'completed'), (False, 'in_progress')):
            state = SimpleNamespace(producer={**self.producer, 'runId': 71 if current else 100},
                prior_carrier_phases=records, sources={key: self.root / 'missing' for key in records},
                completed_frozen=object(), ensure_original_source=None)
            corrupt = False

            def capture(record, destination):
                identity = adapter._identity(record)
                adapter._observe_ci_producer_jobs({identity.phase: self.producer},
                    jobs_by_phase={identity.phase: f'product-validation / runtime-{TARGET}-{identity.phase}-{TARGET}'},
                    trusted_workflow_sha=self.pin, token='not-a-real-token')
                destination.write_bytes(objects[identity] + (b'changed' if corrupt else b''))

            state.capture_deferred_object = capture
            with self.subTest(current=current, status=status), mock.patch('reuse.api_request',
                    side_effect=self.api(run={**self.run, 'status': status})) as http:
                for attempt in range(2):
                    destination = self.root / f'restored-{current}-{status}-{attempt}'
                    destination.mkdir()
                    restored = adapter._restore_product_objects(state, tuple(records), destination)
                    self.assertEqual(set(records), set(restored))
                    for identity in restored:
                        self.assertEqual(self.receipts[identity.phase].read_bytes(), restored[identity]['receiptBytes'])
                    reads = [call for call in http.call_args_list
                             if call.args[0].endswith('/actions/runs/71/attempts/2')]
                    self.assertEqual((attempt + 1) * (4 if current or status != 'completed' else 1), len(reads))
                    self.assertIsNone(adapter._CI_OBSERVATIONS.get())
                corrupt = True
                destination = self.root / f'corrupt-{current}-{status}'
                destination.mkdir()
                with self.assertRaises(ValueError):
                    adapter._restore_product_objects(state, tuple(records), destination)
                self.assertIsNone(adapter._CI_OBSERVATIONS.get())

    def test_raw_run_selection_and_full_observation_share_only_completed_historical_reads(self):
        for current, status, expected_reads in ((None, 'completed', 1),
                (('71', '2'), 'completed', 2), (None, 'in_progress', 2)):
            with self.subTest(current=current, status=status), adapter._ci_observation_batch(current), \
                    mock.patch('reuse.api_request', side_effect=self.api(run={**self.run, 'status': status})) as http:
                run = adapter._original_ci_run(self.producer, 'not-a-real-token')
                run['status'] = 'mutated caller copy'
                observed = adapter._observe_ci_producer_jobs({'binary': self.producer},
                    jobs_by_phase={'binary': self.jobs[0]['name']}, trusted_workflow_sha=self.pin,
                    token='not-a-real-token')
                self.assertEqual(status, observed[0]['run']['status'])
                calls = [call for call in http.call_args_list
                         if call.args[0].endswith('/actions/runs/71/attempts/2')]
                self.assertEqual(expected_reads, len(calls))
                with self.assertRaises(ValueError):
                    adapter._observe_ci_producer_jobs({'binary': self.producer},
                        jobs_by_phase={'binary': self.jobs[0]['name']}, trusted_workflow_sha='0' * 40,
                        token='not-a-real-token')

    def test_single_phase_captures_share_historical_lists_with_warm_metadata_batch(self):
        later_receipt, artifact, raw, job = self.second_attempt_phase('package')
        original = self.two_attempt_api({'package': artifact}, [job], {'package': raw})
        warm = [{**self.artifacts['binary'], 'id': 1000 + index, 'name': f'warm-original-{index}',
                 'archive_download_url': f'https://api.github.com/repos/{fixture.REPOSITORY}/actions/artifacts/{1000 + index}/zip'}
                for index in range(32)]
        def request(url, token):
            for row in warm:
                if url == row['archive_download_url'].removesuffix('/zip'):
                    return json.dumps(row).encode()
            return original(url, token)
        with adapter._ci_observation_batch(('100', '1')), \
                mock.patch('reuse.api_request', side_effect=request) as http:
            for row in warm:
                adapter._contract_ci_upload_metadata(row['id'], row['digest'], row['name'],
                    self.producer, self.failed_run(), 'not-a-real-token')
            for index in range(32):
                phase, receipt = ('binary', self.receipts['binary']) if index % 2 == 0 else ('package', later_receipt)
                destination = self.root / f'shared-single-phase-{index}'
                adapter.capture_runtime_original_ci_phases({phase: receipt}, destination,
                    target=TARGET, trusted_workflow_sha=self.pin, token='not-a-real-token')
                self.assertEqual(receipt.read_bytes(),
                    (destination / f'phases/{phase}/original/shard/phase-receipt.json').read_bytes())
            urls = [call.args[0] for call in http.call_args_list]
            for run, attempt in ((71, 2), (72, 3)):
                self.assertEqual(1, sum(url.endswith(f'/actions/runs/{run}/attempts/{attempt}') for url in urls))
                self.assertEqual(1, sum(f'/actions/runs/{run}/artifacts?' in url for url in urls))
            pending = adapter._CI_OBSERVATIONS.get()['observationGuards'][1]
            self.assertGreaterEqual(len(pending), 32)
            self.assertLess(len(pending), 64)

    def test_single_phase_capture_lists_refresh_for_current_and_live_attempts(self):
        for current, status in ((('71', '2'), 'completed'), (('100', '1'), 'in_progress')):
            with self.subTest(current=current, status=status), adapter._ci_observation_batch(current), \
                    mock.patch('reuse.api_request', side_effect=self.api(run={**self.run, 'status': status})) as http:
                for index in range(2):
                    adapter.capture_runtime_original_ci_phases({'binary': self.receipts['binary']},
                        self.root / f'fresh-single-phase-{status}-{index}', target=TARGET,
                        trusted_workflow_sha=self.pin, token='not-a-real-token')
                urls = [call.args[0] for call in http.call_args_list]
                self.assertEqual(4, sum(url.endswith('/actions/runs/71/attempts/2') for url in urls))
                self.assertEqual(2, sum('/actions/runs/71/artifacts?' in url for url in urls))

    def test_shared_historical_capture_keeps_workflow_and_ambiguous_list_checks(self):
        with adapter._ci_observation_batch(('100', '1')), mock.patch('reuse.api_request', side_effect=self.api()):
            adapter.capture_runtime_original_ci_phases({'binary': self.receipts['binary']},
                self.root / 'known-original', target=TARGET, trusted_workflow_sha=self.pin,
                token='not-a-real-token')
            with self.assertRaisesRegex(ValueError, 'reviewed producer workflow'):
                adapter.capture_runtime_original_ci_phases({'binary': self.receipts['binary']},
                    self.root / 'wrong-workflow', target=TARGET, trusted_workflow_sha='0' * 40,
                    token='not-a-real-token')
        ambiguous = {**self.artifacts, 'duplicate': {**self.artifacts['binary'], 'id': 999}}
        with adapter._ci_observation_batch(('100', '1')), \
                mock.patch('reuse.api_request', side_effect=self.api(artifacts=ambiguous)) as http:
            for index in range(2):
                with self.assertRaisesRegex(ValueError, 'missing or ambiguous'):
                    adapter.capture_runtime_original_ci_phases({'binary': self.receipts['binary']},
                        self.root / f'ambiguous-original-{index}', target=TARGET,
                        trusted_workflow_sha=self.pin, token='not-a-real-token')
            self.assertEqual(1, sum('/actions/runs/71/artifacts?' in call.args[0] for call in http.call_args_list))

    def test_parallel_original_reads_share_completed_attempt_but_refresh_current_attempt(self):
        from threading import Barrier
        import time
        from products.restore import bounded_verify
        for current, status in ((None, 'completed'), (('71', '2'), 'completed'), (None, 'in_progress')):
            entered = Barrier(4, timeout=5)
            original = self.api(run={**self.run, 'status': status})
            def http(url, token):
                if url.endswith('/actions/runs/71/attempts/2'):
                    time.sleep(0.05)  # Keep a real in-flight read while its siblings arrive.
                return original(url, token)
            def observe(_):
                entered.wait()
                return adapter._observe_ci_producer_jobs({'binary': self.producer},
                    jobs_by_phase={'binary': self.jobs[0]['name']}, trusted_workflow_sha=self.pin,
                    token='not-a-real-token')
            with self.subTest(current=current, status=status), mock.patch('reuse.api_request', side_effect=http) as reads:
                with adapter._ci_observation_batch(current):
                    results = bounded_verify(observe, range(4))
                self.assertTrue(all(result == results[0] for result in results))
                original_reads = [call for call in reads.call_args_list
                    if call.args[0].endswith('/actions/runs/71/attempts/2')]
                self.assertEqual(4 if current or status != 'completed' else 1, len(original_reads))

    def test_reference_sources_reuse_completed_run_lookup_but_refresh_each_artifact(self):
        plan = {'repository': self.producer['repository'], 'event': self.producer['event']}
        consumer = {**self.producer, 'runId': 100}
        for current, status in ((None, 'completed'), (('71', '2'), 'completed'), (None, 'in_progress')):
            with self.subTest(current=current, status=status), \
                    mock.patch('reuse.api_request', side_effect=self.api(run={**self.run, 'status': status})) as http:
                with adapter._ci_observation_batch(current):
                    for phase in fixture.PHASES:
                        source = {'kind': 'phase', 'receipt': fixture.load_canonical_json_bytes(self.receipts[phase].read_bytes()),
                                  'artifactId': self.artifacts[phase]['id'], 'artifactSha256': self.artifacts[phase]['digest']}
                        result = adapter._authenticate_runtime_original_reference_source(plan, consumer, source,
                            trusted_workflow_sha=self.pin, token='not-a-real-token')
                        self.assertEqual('.github/workflows/ci.yml', result[2][0]['run']['path'])
                        result[2][0]['run']['path'] = 'caller mutation must remain private'
                    run_reads = [call for call in http.call_args_list
                                 if call.args[0].endswith('/actions/runs/71/attempts/2')]
                    self.assertEqual(8 if current or status != 'completed' else 1, len(run_reads))
                    artifact_reads = [call for call in http.call_args_list if '/actions/artifacts/' in call.args[0]]
                    self.assertEqual(4, len(artifact_reads))
                    with self.assertRaisesRegex(ValueError, 'caller-bound transport identity'):
                        adapter._authenticate_runtime_original_reference_source(plan, consumer,
                            {**source, 'artifactSha256': 'sha256:' + '0' * 64},
                            trusted_workflow_sha=self.pin, token='not-a-real-token')
                before = http.call_count
                adapter._authenticate_runtime_original_reference_source(plan, consumer, source,
                    trusted_workflow_sha=self.pin, token='not-a-real-token')
                self.assertGreater(http.call_count, before)

    def test_original_source_and_jobs_overlap_and_either_failure_rejects(self):
        from threading import Barrier
        for failure in (None, 'run', 'commit', 'jobs'):
            entered = Barrier(2, timeout=5)
            original = self.api()
            def http(url, token):
                kind = ('jobs' if '/jobs?' in url else
                        'commit' if '/git/commits/' in url else 'run')
                if kind in ('run', 'jobs'):
                    entered.wait()
                if kind == failure:
                    raise ValueError(f'{kind} observation failed')
                return original(url, token)
            with self.subTest(failure=failure), mock.patch('reuse.api_request', side_effect=http):
                def observe():
                    return adapter._observe_ci_producer_jobs({'binary': self.producer},
                        jobs_by_phase={'binary': self.jobs[0]['name']},
                        trusted_workflow_sha=self.pin, token='not-a-real-token')
                if failure is None:
                    result = observe()[0]
                    self.assertEqual(self.run, result['run'])
                    self.assertEqual(self.jobs, result['jobs'])
                    self.assertEqual(self.producer['commit'], result['testedCommit']['sha'])
                else:
                    with self.assertRaisesRegex(ValueError, f'{failure} observation failed'):
                        observe()

    def test_independent_originals_still_overlap_and_failed_reads_release_their_guard(self):
        from threading import Barrier
        from products.restore import bounded_verify
        _, artifact, raw, job = self.second_attempt_phase('binary')
        original = self.two_attempt_api({'binary': artifact}, [job], {'binary': raw})
        entered = Barrier(2, timeout=5)
        def http(url, token):
            if url.endswith(('/actions/runs/71/attempts/2', '/actions/runs/72/attempts/3')):
                entered.wait()
            return original(url, token)
        producers = [self.producer, {**self.producer, 'runId': 72, 'runAttempt': 3}]
        def observe(producer):
            return adapter._observe_ci_producer_jobs({'binary': producer},
                jobs_by_phase={'binary': self.jobs[0]['name']}, trusted_workflow_sha=self.pin,
                token='not-a-real-token')
        with mock.patch('reuse.api_request', side_effect=http), adapter._ci_observation_batch():
            self.assertEqual(2, len(bounded_verify(observe, producers)))
        with adapter._ci_observation_batch():
            with mock.patch('reuse.api_request', side_effect=ValueError('original read failed')):
                with self.assertRaisesRegex(ValueError, 'original read failed'):
                    bounded_verify(observe, [self.producer] * 4)
            with mock.patch('reuse.api_request', side_effect=self.api()):
                self.assertEqual(self.run, observe(self.producer)[0]['run'])

    def test_concurrent_read_failure_is_fanned_out_and_next_call_retries(self):
        from concurrent.futures import Future
        from threading import Barrier
        from products.restore import bounded_verify
        waiting = Barrier(4, timeout=5)
        class ObservedFuture(Future):
            def result(self, timeout=None):
                waiting.wait()
                return super().result(timeout)
        original = self.api()
        def failed_read(url, token):
            if '/jobs?' in url:
                return original(url, token)
            waiting.wait()  # All three siblings have joined this one read.
            raise OSError('slow original read failed')
        def observe(_):
            try:
                adapter._observe_ci_producer_jobs({'binary': self.producer},
                    jobs_by_phase={'binary': self.jobs[0]['name']}, trusted_workflow_sha=self.pin,
                    token='not-a-real-token')
            except OSError as error:
                return str(error)
            self.fail('Failed metadata must not yield an observation')
        with adapter._ci_observation_batch():
            with mock.patch.object(adapter, 'Future', ObservedFuture), \
                    mock.patch('reuse.api_request', side_effect=failed_read) as reads:
                self.assertEqual(['slow original read failed'] * 4, bounded_verify(observe, range(4)))
                self.assertEqual(2, reads.call_count)
                self.assertEqual(1, sum('/jobs?' in call.args[0] for call in reads.call_args_list))
            with mock.patch('reuse.api_request', side_effect=self.api()):
                value = adapter._observe_ci_producer_jobs({'binary': self.producer},
                    jobs_by_phase={'binary': self.jobs[0]['name']}, trusted_workflow_sha=self.pin,
                    token='not-a-real-token')
                self.assertEqual(self.run, value[0]['run'])

    def test_shared_metadata_does_not_share_a_callers_workflow_verdict(self):
        from threading import Barrier
        from products.restore import bounded_verify
        entered = Barrier(2, timeout=5)
        def observe(pin):
            entered.wait()
            try:
                return adapter._observe_ci_producer_jobs({'binary': self.producer},
                    jobs_by_phase={'binary': self.jobs[0]['name']}, trusted_workflow_sha=pin,
                    token='not-a-real-token')
            except ValueError:
                return None
        with mock.patch('reuse.api_request', side_effect=self.api()), adapter._ci_observation_batch():
            wrong, correct = bounded_verify(observe, ['0' * 40, self.pin])
            self.assertIsNone(wrong)
            self.assertEqual(self.run, correct[0]['run'])

    def capture(self, **changes):
        with mock.patch("reuse.api_request", side_effect=self.api(**changes)):
            return adapter.capture_runtime_original_ci_phases(self.receipts, self.output,
                target=TARGET, trusted_workflow_sha=self.pin, token="not-a-real-token")

    def failed_run(self, run_id=71, attempt=2):
        return {**self.run, "id": run_id, "run_attempt": attempt,
                "status": "completed", "conclusion": "failure"}

    def second_attempt_phase(self, phase, *, changed_output=False):
        """Make one genuine shard from another producer without changing its build key."""
        producer = {**self.producer, "runId": 72, "runAttempt": 3}
        original = fixture.load_canonical_json_bytes(self.receipts[phase].read_bytes())
        phase_plan = {key: original[key] for key in
                      ("schemaVersion", "product", "component", "phase", "target", "buildKey", "inputs")}
        stage = self.root / "runtime-stages" / phase
        if changed_output:
            from products.receipt import write_output_manifest
            stage = self.root / "changed-runtime-stage" / phase
            (stage / "outputs").mkdir(parents=True)
            (stage / "outputs/value.bin").write_bytes(b"different product bytes\n")
            write_output_manifest(stage, "runtime", TARGET, phase, TARGET, "0.2.0",
                                  {"binary": "outputs"})
        upload = self.root / "second-attempt" / phase
        fixture.finalize_phase_object(stage_root=stage, phase_plan=phase_plan, producer=producer,
            product_version="0.2.0", trust_domain="development", destination=upload / "shard")
        raw = fixture.archive_tree(upload)
        artifact = {**self.artifacts[phase], "id": 201 + fixture.PHASES.index(phase),
                    "name": f"codex-agent-runtime-worker-{TARGET}-{phase}-{TARGET}-"
                            f"{original['buildKey'][7:]}-{producer['tree']}-attempt-3",
                    "digest": fixture.sha256_bytes(raw), "size_in_bytes": len(raw),
                    "workflow_run": {"id": 72, "head_sha": self.run["head_sha"]}}
        artifact["archive_download_url"] = (
            f"https://api.github.com/repos/{fixture.REPOSITORY}/actions/artifacts/{artifact['id']}/zip")
        job = {**self.jobs[fixture.PHASES.index(phase)], "id": 201 + fixture.PHASES.index(phase),
               "run_id": 72}
        return upload / "shard/phase-receipt.json", artifact, raw, job

    def two_attempt_api(self, later_artifacts, later_jobs, later_archives, *, first_artifacts=None,
                        first_jobs=None):
        original_api = self.api(artifacts=self.artifacts if first_artifacts is None else first_artifacts,
                                jobs=self.jobs if first_jobs is None else first_jobs,
                                run=self.failed_run())
        prefix = f"https://api.github.com/repos/{fixture.REPOSITORY}"
        by_id = {artifact["id"]: artifact for artifact in later_artifacts.values()}
        by_url = {later_artifacts[phase]["archive_download_url"]: raw
                  for phase, raw in later_archives.items()}

        def request(url, token):
            self.assertEqual("not-a-real-token", token)
            if url == prefix + "/actions/runs/72/attempts/3":
                return json.dumps(self.failed_run(72, 3)).encode()
            if url.startswith(prefix + "/actions/runs/72/attempts/3/jobs?"):
                return json.dumps({"jobs": later_jobs}).encode()
            if url.startswith(prefix + "/actions/runs/72/artifacts?"):
                return json.dumps({"artifacts": list(later_artifacts.values())}).encode()
            if url in by_url:
                return by_url[url]
            if url.startswith(prefix + "/actions/artifacts/"):
                artifact_id = url.removeprefix(prefix + "/actions/artifacts/")
                if artifact_id.isdigit() and int(artifact_id) in by_id:
                    return json.dumps(by_id[int(artifact_id)]).encode()
            return original_api(url, token)

        return request

    def download_two_attempt_fixture(self, later_artifacts, later_archives, *, first_archives=None):
        raw_by_id = {artifact["id"]: later_archives[phase]
                     for phase, artifact in later_artifacts.items()}
        raw_by_id.update({artifact["id"]: (self.archives if first_archives is None else first_archives)[phase]
                          for phase, artifact in self.artifacts.items()})

        def download(artifact, token, destination, **_):
            self.assertEqual("not-a-real-token", token)
            Path(destination).write_bytes(raw_by_id[artifact["id"]])

        return download

    def test_original_uploads_and_receipts_are_retained_exactly(self):
        before = {phase: path.read_bytes() for phase, path in self.receipts.items()}
        result = self.capture()
        self.assertEqual(TARGET, result["target"])
        for phase in fixture.PHASES:
            retained = self.output / "phases" / phase
            self.assertEqual(self.archives[phase], (retained / "transport.zip").read_bytes())
            self.assertEqual(before[phase], (retained / "original/shard/phase-receipt.json").read_bytes())
            self.assertEqual(before[phase], self.receipts[phase].read_bytes())
        with self.assertRaisesRegex(ValueError, "must not exist"):
            self.capture()

    def test_successful_phase_jobs_remain_authentic_after_overall_run_failure(self):
        failed_run = {**self.run, "status": "completed", "conclusion": "failure"}
        originals = {phase: path.read_bytes() for phase, path in self.receipts.items()}
        result = self.capture(run=failed_run)
        self.assertEqual("failure", result["observed"][0]["run"]["conclusion"])
        for phase in fixture.PHASES:
            self.assertEqual(originals[phase],
                (self.output / "phases" / phase / "original/shard/phase-receipt.json").read_bytes())

    def test_ci_capture_accepts_independent_phases_but_release_requires_all_four(self):
        failed_run = {**self.run, "status": "completed", "conclusion": "failure"}
        receipts = {phase: self.receipts[phase] for phase in ("package", "validation")}
        with mock.patch("reuse.api_request", side_effect=self.api(run=failed_run)):
            result = adapter.capture_runtime_original_ci_phases(receipts, self.output,
                target=TARGET, trusted_workflow_sha=self.pin, token="not-a-real-token")
        self.assertEqual({"package", "validation"}, set(result["artifacts"]))
        self.assertFalse((self.output / "phases/binary").exists())
        self.assertFalse((self.output / "phases/metadata").exists())
        for phase, source in receipts.items():
            self.assertEqual(source.read_bytes(),
                (self.output / "phases" / phase / "original/shard/phase-receipt.json").read_bytes())

        with self.assertRaisesRegex(ValueError, "release requires all four"):
            adapter.capture_runtime_original_ci_phases(receipts, self.root / "incomplete-release",
                target=TARGET, trusted_workflow_sha=self.pin, token="not-a-real-token",
                release_handoffs=(self.root / "release-handoff",),
                keyring=self.root / "keyring.json", keys_directory=self.root / "keys")

    def test_prior_failed_attempt_discovers_and_authenticates_requested_phases(self):
        failed_run = self.failed_run()
        listed = {phase: self.artifacts[phase] for phase in ("binary", "package")}
        plan = {"event": "pull_request", "pullRequest": 31,
                "repository": fixture.REPOSITORY}
        destination = self.root / "prior-capture"
        requested = {PhaseInstanceId("runtime", TARGET, phase, TARGET):
                     fixture.load_canonical_json_bytes(self.receipts[phase].read_bytes())["buildKey"]
                     for phase in ("binary", "package")}
        with mock.patch.object(adapter, "download_artifact_to_file", side_effect=self.download_fixture), \
                mock.patch("reuse.api_request", side_effect=self.api(run=failed_run, artifacts=listed)):
            result = adapter.capture_prior_failed_runtime_phases(
                plan, {"runId": 100, "runAttempt": 1}, requested, destination,
                trusted_workflow_sha=self.pin, token="not-a-real-token", attempts=(failed_run,))
            real_temp = self.root / "real-temp"
            real_temp.mkdir()
            linked_temp = self.root / "linked-temp"
            linked_temp.symlink_to(real_temp, target_is_directory=True)
            with mock.patch.object(tempfile, "tempdir", str(linked_temp)):
                records = adapter._prior_failed_runtime_objects(
                    destination, self.root, trusted_workflow_sha=self.pin,
                    token="not-a-real-token")
        self.assertEqual(set(requested), set(result))
        self.assertEqual({"binary", "package"}, {record["phase"] for record in records})
        for phase in ("binary", "package"):
            self.assertEqual(self.receipts[phase].read_bytes(),
                (destination / TARGET / phase / TARGET / "phases" / phase / "original/shard/phase-receipt.json").read_bytes())
        self.assertFalse((destination / TARGET / "validation").exists())
        # Replay authenticates the pinned producer even if a later failed run
        # becomes the newest recovery candidate.
        with mock.patch("reuse.api_request", side_effect=self.api(run=failed_run)):
            replayed = adapter._prior_failed_runtime_objects(
                destination, self.root, trusted_workflow_sha=self.pin,
                token="not-a-real-token", plan=plan,
                consumer_producer={"runId": 100, "runAttempt": 1})
            same_run = adapter._prior_failed_runtime_objects(
                destination, self.root, trusted_workflow_sha=self.pin,
                token="not-a-real-token", plan=plan,
                consumer_producer={"runId": 71, "runAttempt": 3})
        self.assertEqual({"binary", "package"}, {record["phase"] for record in replayed})
        self.assertEqual(replayed, same_run)

    def test_completed_projection_reuse_keeps_fresh_origin_authentication_and_mutation_guards(self):
        from products.restore import verification_session
        upload = self.root / 'runtime-uploads/binary'
        (upload / 'raw-proof.bin').write_bytes(b'opaque original proof\n' * 65_536)
        self.archives['binary'] = fixture.archive_tree(upload)
        self.artifacts['binary'].update(digest=fixture.sha256_bytes(self.archives['binary']),
                                        size_in_bytes=len(self.archives['binary']))
        with verification_session() as session, mock.patch('reuse.api_request', side_effect=self.api()) as api, \
                mock.patch.object(adapter, '_extract_runtime_original_projection', wraps=adapter._extract_runtime_original_projection) as extract:
            # Existing verified objects leave room for bounded metadata, but no
            # duplicate original proof body. The previous body memo missed here.
            session['bytes'] = session['limit'] - 64 * 1024
            for number in range(2):
                adapter.capture_runtime_original_ci_phases({'binary': self.receipts['binary']},
                    self.root / f'memo-{number}', target=TARGET, trusted_workflow_sha=self.pin,
                    token='not-a-real-token', recovery_projection=True)
            self.assertEqual(1, extract.call_count)
            artifact_url = self.artifacts['binary']['archive_download_url'].removesuffix('/zip')
            self.assertEqual(2, sum(call.args[0] == artifact_url for call in api.call_args_list))
            cached, *_ = next(iter(session['originalCaptures'].values()))
            self.assertEqual(self.root / 'memo-0/phases/binary/original', cached)
            self.assertFalse(any(session['root'].glob('original-*')))
            # Publication preserves exact bytes and retargets only this private
            # invocation's metadata; no second product/proof body is retained.
            relocated = self.root / 'relocated'
            actual_publish_regular_tree(self.root / 'memo-0', relocated, allow_empty=True)
            adapter._retarget_runtime_original_captures(self.root / 'memo-0', relocated)
            import shutil
            shutil.rmtree(self.root / 'memo-0')
            adapter.capture_runtime_original_ci_phases({'binary': self.receipts['binary']},
                self.root / 'memo-relocated', target=TARGET, trusted_workflow_sha=self.pin,
                token='not-a-real-token', recovery_projection=True)
            self.assertEqual(1, extract.call_count)
            cached, *_ = next(iter(session['originalCaptures'].values()))
            self.assertEqual(relocated / 'phases/binary/original', cached)
            (cached / 'shard/phase-receipt.json').write_bytes(b'changed private receipt')
            with self.assertRaisesRegex(ValueError, 'Private verified original Runtime capture changed'):
                adapter.capture_runtime_original_ci_phases({'binary': self.receipts['binary']},
                    self.root / 'memo-corrupt', target=TARGET, trusted_workflow_sha=self.pin,
                    token='not-a-real-token', recovery_projection=True)
            self.assertFalse((self.root / 'memo-corrupt').exists())

    def test_recovery_projection_omits_only_duplicates_and_reauthenticates_original(self):
        upload = self.root / "runtime-uploads/binary"
        (upload / "inputs").mkdir()
        (upload / "inputs/predecessor.bin").write_bytes(b"duplicated authenticated predecessor")
        (upload / "raw-validation").mkdir()
        (upload / "raw-validation/proof.json").write_bytes(b"unique original proof")
        raw = fixture.archive_tree(upload)
        self.archives["binary"] = raw
        self.artifacts["binary"].update(digest=fixture.sha256_bytes(raw), size_in_bytes=len(raw))
        instance = PhaseInstanceId("runtime", TARGET, "binary", TARGET)
        key = fixture.load_canonical_json_bytes(self.receipts["binary"].read_bytes())["buildKey"]
        plan = {"event": "pull_request", "pullRequest": 31, "repository": fixture.REPOSITORY}
        destination = self.root / "projected-recovery"
        run = self.failed_run()
        from runtime_reference_transport import _copy_exact

        def copy_projection(source, *args, **kwargs):
            self.assertNotEqual("transport.zip", Path(source).name, "replayed whole upload")
            return _copy_exact(source, *args, **kwargs)

        with mock.patch.object(adapter, "download_artifact_to_file", side_effect=self.download_fixture), \
                mock.patch("reuse.api_request", side_effect=self.api(run=run)), \
                mock.patch.object(adapter, "_extract_runtime_original_projection", wraps=adapter._extract_runtime_original_projection) as extract, \
                mock.patch("runtime_reference_transport._copy_exact", side_effect=copy_projection):
            adapter.capture_prior_failed_runtime_phases(plan, {"runId": 100, "runAttempt": 1},
                {instance: key}, destination, trusted_workflow_sha=self.pin,
                token="not-a-real-token", attempts=(run,))
            self.assertEqual(1, extract.call_count)
            captured = destination / TARGET / "binary" / TARGET
            self.assertFalse((captured / "phases/binary/transport.zip").exists())
            self.assertFalse((captured / "phases/binary/original/inputs").exists())
            proof = captured / "phases/binary/original/raw-validation/proof.json"
            self.assertEqual(b"unique original proof", proof.read_bytes())
            observation = fixture.load_canonical_json_bytes(
                (captured / "transport/original-ci-phases.json").read_bytes())
            self.assertEqual(self.artifacts["binary"]["digest"], observation["artifacts"]["binary"]["digest"])
            self.assertIn("inputs/predecessor.bin", {record["relativePath"] for record in
                observation["recoveryProjection"]["originalFiles"]["binary"]})
            records = adapter._prior_failed_runtime_objects(destination, self.root,
                trusted_workflow_sha=self.pin, token="not-a-real-token", plan=plan,
                consumer_producer={"runId": 100, "runAttempt": 1})
            self.assertEqual(key, records[0]["buildKey"])
            self.assertEqual(self.receipts["binary"].read_bytes(),
                (captured / "phases/binary/original/shard/phase-receipt.json").read_bytes())
            observation_path = captured / "transport/original-ci-phases.json"
            original_observation = observation_path.read_bytes()
            changed_run = copy.deepcopy(run)
            changed_run["pull_requests"][0]["head"]["sha"] = "a" * 40
            changed_run["updated_at"] = "2026-09-30T13:00:00Z"
            changed_jobs = copy.deepcopy(self.jobs)
            changed_jobs.append({"name": "unrelated later job", "status": "completed"})
            with mock.patch("reuse.api_request", side_effect=self.api(run=changed_run, jobs=changed_jobs)):
                self.assertEqual(records, adapter._prior_failed_runtime_objects(destination, self.root,
                    trusted_workflow_sha=self.pin, token="not-a-real-token", plan=plan,
                    consumer_producer={"runId": 100, "runAttempt": 1}))
            self.assertEqual(original_observation, observation_path.read_bytes())
            tampered = copy.deepcopy(observation)
            tampered["observed"][0]["jobs"][0]["id"] += 1
            observation_path.write_bytes(fixture.canonical_json_bytes(tampered))
            with self.assertRaisesRegex(ValueError, "differs from original CI"):
                adapter._prior_failed_runtime_objects(destination, self.root,
                    trusted_workflow_sha=self.pin, token="not-a-real-token", plan=plan,
                    consumer_producer={"runId": 100, "runAttempt": 1})
            observation_path.write_bytes(original_observation)
            proof.write_bytes(b"tampered proof")
            with self.assertRaisesRegex(ValueError, "differs from original CI"):
                adapter._prior_failed_runtime_objects(destination, self.root,
                    trusted_workflow_sha=self.pin, token="not-a-real-token", plan=plan,
                    consumer_producer={"runId": 100, "runAttempt": 1})

    def test_unqualified_physical_projection_reuses_bytes_with_partial_native_proof(self):
        from ci.tests.test_completed_frozen_reuse import CompletedFrozenReuseTest
        from products.restore import verification_session
        native_fixture = CompletedFrozenReuseTest()
        native_fixture.setUp()
        (self.root / "native-proof").mkdir()
        cap, _ = native_fixture.fetched(self.root / "native-proof")
        cap._eligible = frozenset()  # The new physical original is not in this native proof.
        captured = self.root / "qualified-carrier"
        with mock.patch.object(adapter, "download_artifact_to_file", side_effect=self.download_fixture), \
                mock.patch("reuse.api_request", side_effect=self.api()):
            observation = adapter.capture_runtime_original_ci_phases(
                {"binary": self.receipts["binary"]}, captured, target=TARGET,
                trusted_workflow_sha=self.pin, token="not-a-real-token", recovery_projection=True)
        projected = captured / "phases/binary/original"
        receipt = fixture.load_canonical_json_bytes((projected / "shard/phase-receipt.json").read_bytes())
        source = {"kind": "phase", "relativePath": projected.relative_to(self.root).as_posix(), "receipt": receipt}
        transport = {"artifact": self.artifacts["binary"], "observed": observation["observed"]}
        # Signing preparation also has native proof, but no hosted cache setup.
        with mock.patch("hydrated_evidence.root", return_value=None), \
                verification_session() as session, \
                mock.patch("reuse.api_request", side_effect=self.api()) as http, \
                mock.patch.object(adapter, "download_artifact_to_file", side_effect=AssertionError("duplicate body transfer")):
            adapter._register_qualified_original_projections(self.root, {"sources": [source]}, [transport],
                trusted_workflow_sha=self.pin, completed_frozen=cap)
            self.assertEqual(1, len(session["qualifiedOriginalProjections"]))
            replay = self.root / "replayed-physical"
            adapter.capture_runtime_original_ci_phases({"binary": self.receipts["binary"]}, replay,
                target=TARGET, trusted_workflow_sha=self.pin, token="not-a-real-token", recovery_projection=True)
            self.assertGreater(http.call_count, 0)  # Original CI remains freshly authenticated.
            self.assertEqual(adapter.regular_file_inventory(projected),
                             adapter.regular_file_inventory(replay / "phases/binary/original"))
            (replay / "phases/binary/original/shard/phase-receipt.json").write_bytes(b"changed private evidence")
            with self.assertRaisesRegex(ValueError, "capture changed"):
                adapter.capture_runtime_original_ci_phases({"binary": self.receipts["binary"]},
                    self.root / "rejected-physical", target=TARGET, trusted_workflow_sha=self.pin,
                    token="not-a-real-token", recovery_projection=True)

    def test_original_carrier_restores_cross_process_and_later_wave_projection_without_rebuilding(self):
        from products.restore import verification_session
        from runtime_reference_transport import stage_original_reference_handoff
        import hydrated_evidence
        original = self.root / "later-wave/original"
        state = original / "product-resume-state"
        captured = state / f"prior-failed-runtime/{TARGET}/binary/{TARGET}"
        with mock.patch("reuse.api_request", side_effect=self.api(run=self.failed_run())), \
                mock.patch("products.verified_evidence.runtime_original_cache", return_value=None):
            adapter.capture_runtime_original_ci_phases({"binary": self.receipts["binary"]}, captured,
                target=TARGET, trusted_workflow_sha=self.pin, token="not-a-real-token", recovery_projection=True)
        receipt = fixture.load_canonical_json_bytes(self.receipts["binary"].read_bytes())
        producer = {**self.producer, "runId": 72, "runAttempt": 3}
        plan = {"repository": fixture.REPOSITORY, "event": "pull_request", "pullRequest": 31,
                "validationCommit": producer["commit"], "validationTree": producer["tree"]}
        inputs = original / "product-resume-inputs"
        (inputs / "plan").mkdir(parents=True)
        (inputs / "plan/impact-plan.json").write_bytes(fixture.canonical_json_bytes(plan))
        source = {"relativePath": (captured / "phases/binary/original").relative_to(original).as_posix(),
                  "kind": "phase", "receipt": receipt, "artifactId": self.artifacts["binary"]["id"],
                  "artifactSha256": self.artifacts["binary"]["digest"]}
        carrier = self.root / "reference-carrier"
        stage_original_reference_handoff({"product-resume-inputs": inputs, "product-resume-state": state},
            [source], carrier)
        raw = fixture.archive_tree(carrier)
        artifact = {**self.artifacts["binary"], "id": 900,
            "name": f"codex-agent-product-resume-{producer['tree']}",
            "workflow_run": {"id": 72, "head_sha": self.run["head_sha"]},
            "digest": fixture.sha256_bytes(raw), "size_in_bytes": len(raw),
            "archive_download_url": f"https://api.github.com/repos/{fixture.REPOSITORY}/actions/artifacts/900/zip"}
        job = {**self.jobs[0], "id": 900, "run_id": 72, "name": "product-validation / product-resume"}
        originals = fixture.regular_file_inventory(state)
        api = self.two_attempt_api({"resume": artifact}, [job], {"resume": raw})
        downloads = []
        def download(upload, _token, destination, **_):
            self.assertEqual(900, upload["id"], "must never redownload the original phase")
            downloads.append(upload["id"])
            Path(destination).write_bytes(raw)
        def replay():
            return adapter._prior_failed_runtime_objects(state / "prior-failed-runtime", state,
                plan=plan, consumer_producer=producer, trusted_workflow_sha=self.pin, token="not-a-real-token")
        with mock.patch.dict(os.environ, {"CODEX_AGENT_HYDRATED_EVIDENCE": str(self.root / "byte-storage")}), \
                mock.patch("products.verified_evidence.runtime_original_cache", return_value=None), \
                mock.patch.object(adapter, "download_artifact_to_file", side_effect=download), \
                mock.patch("reuse.api_request", side_effect=api) as http:
            for _ in range(2):
                with verification_session() as session:
                    self.assertNotIn("qualifiedOriginalProjections", session)
                    records = replay()
                    self.assertEqual(receipt["buildKey"], records[0]["buildKey"])
                    self.assertEqual(1, len(session["qualifiedOriginalProjections"]))
                self.assertEqual(originals, fixture.regular_file_inventory(state))
            self.assertEqual([900], downloads)
            self.assertEqual(2, sum('/runs/72/attempts/3/jobs?' in call.args[0] for call in http.call_args_list))
            self.assertFalse((self.root / "persistent-cache/v1/verified-runtime-originals/records").exists())
            observation = captured / "transport/original-ci-phases.json"
            saved = observation.read_bytes()
            observation.write_bytes(saved.replace(b'"target":"linux-x64"', b'"target":"wrong-x64"'))
            with verification_session(), self.assertRaisesRegex(ValueError, "observation differs"):
                replay()
            observation.write_bytes(saved)
            failed = {**job, "conclusion": "failure"}
            with mock.patch("reuse.api_request", side_effect=self.two_attempt_api(
                    {"resume": artifact}, [failed], {"resume": raw})), verification_session(), self.assertRaises(ValueError):
                replay()
            blob = hydrated_evidence.blob({"sha256": artifact["digest"]})
            blob.write_bytes(raw[:-1] + b"x")
            with verification_session(), self.assertRaises(ValueError):
                replay()
            self.assertEqual([900], downloads)

    def test_completed_candidate_mutation_rejects_after_fresh_origin_authentication(self):
        from products.restore import verification_session
        instance = PhaseInstanceId("runtime", TARGET, "binary", TARGET)
        key = fixture.load_canonical_json_bytes(self.receipts["binary"].read_bytes())["buildKey"]
        plan = {"event": "pull_request", "pullRequest": 31, "repository": fixture.REPOSITORY}
        run = self.failed_run()
        metadata_url = self.artifacts["binary"]["archive_download_url"].removesuffix("/zip")
        for target in ("transport.zip", "original/shard/phase-receipt.json"):
            destination = self.root / ("mutated-candidate-" + target.split("/")[-1])
            original_api = self.api(run=run)
            with verification_session() as session:
                observations = []
                def changed(url, *args, **kwargs):
                    result = original_api(url, *args, **kwargs)
                    if url == metadata_url:
                        observations.append(url)
                        candidates = session.get("runtimeCandidates", {})
                        if candidates:
                            original, *_ = next(iter(candidates.values()))
                            path = original.parent / target
                            before = path.stat()
                            data = path.read_bytes()
                            path.write_bytes(bytes([data[0] ^ 1]) + data[1:])
                            os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
                    return result
                with mock.patch.object(adapter, "download_artifact_to_file", side_effect=self.download_fixture), \
                        mock.patch("reuse.api_request", side_effect=changed), \
                        self.assertRaisesRegex(ValueError, "Private verified Runtime upload candidate changed"):
                    adapter.capture_prior_failed_runtime_phases(plan, {"runId": 100, "runAttempt": 1},
                        {instance: key}, destination, trusted_workflow_sha=self.pin,
                        token="not-a-real-token", attempts=(run,))
                self.assertGreaterEqual(len(observations), 2)
                self.assertFalse((destination / TARGET / "binary" / TARGET).exists())

    def test_prior_planner_recovers_only_requested_original_without_whole_phase_transfers(self):
        from products.restore import verification_session
        from runtime_reference_transport import stage_original_reference_handoff
        from ci.tests.test_runtime_reference_transport import RangeOpener
        original = self.root / 'old-planner'
        state = original / 'product-resume-state'
        sources = []
        with mock.patch('reuse.api_request', side_effect=self.api(run=self.failed_run())):
            for phase in ('binary', 'package'):
                capture = state / f'prior-failed-runtime/{TARGET}/{phase}/{TARGET}'
                adapter.capture_runtime_original_ci_phases({phase: self.receipts[phase]}, capture,
                    target=TARGET, trusted_workflow_sha=self.pin, token='not-a-real-token', recovery_projection=True)
                sources.append(dict(kind='phase', relativePath=(capture / f'phases/{phase}/original').relative_to(original).as_posix(),
                    receipt=fixture.load_canonical_json_bytes(self.receipts[phase].read_bytes()),
                    artifactId=self.artifacts[phase]['id'], artifactSha256=self.artifacts[phase]['digest']))
        plan = dict.fromkeys(adapter._PLAN_KEYS)
        plan.update(schemaVersion=1, repository=fixture.REPOSITORY, event='pull_request', pullRequest=31,
            validationCommit=self.producer['commit'], validationTree=self.producer['tree'],
            remoteBuildAuthorized=True, mergeReady=True, remoteBuildAuthorizationReason='pull-request-final')
        inputs = original / 'product-resume-inputs'
        (inputs / 'plan').mkdir(parents=True)
        (inputs / 'plan/impact-plan.json').write_bytes(fixture.canonical_json_bytes(plan))
        carrier = self.root / 'small-planner-carrier'
        stage_original_reference_handoff({'product-resume-inputs': inputs, 'product-resume-state': state}, sources, carrier)
        raw = fixture.archive_tree(carrier)
        artifact = {**self.artifacts['binary'], 'id':900,
            'name':f"codex-agent-planned-product-resume-{self.producer['tree']}",
            'workflow_run':{'id':72, 'head_sha':self.run['head_sha']},
            'digest':fixture.sha256_bytes(raw), 'size_in_bytes':len(raw),
            'archive_download_url':f'https://api.github.com/repos/{fixture.REPOSITORY}/actions/artifacts/900/zip'}
        job = {**self.jobs[0], 'id':900, 'run_id':72, 'name':'product-validation / plan'}
        base_api = self.two_attempt_api({'plan':artifact}, [job], {'plan':raw})
        def api(url, token):
            if url.endswith(('/runs/72', '/runs/72/attempts/1')):
                return json.dumps(self.failed_run(72, 1)).encode()
            if '/runs/72/attempts/1/jobs?' in url:
                return json.dumps({'jobs':[job]}).encode()
            return base_api(url, token)
        def download(upload, _token, destination, **_):
            self.assertEqual(900, upload['id'], 'whole original phase must never be transferred')
            Path(destination).write_bytes(raw)
        current = {**self.producer, 'runId':100, 'runAttempt':1}
        instance = PhaseInstanceId('runtime', TARGET, 'binary', TARGET)
        requested = {instance:sources[0]['receipt']['buildKey']}
        ranges = RangeOpener({self.artifacts['binary']['id']:self.archives['binary']})
        with mock.patch.dict(os.environ, {'CODEX_AGENT_HYDRATED_EVIDENCE':str(self.root / 'storage')}), \
                mock.patch('products.verified_evidence.runtime_original_cache', return_value=None), \
                mock.patch.object(adapter, 'download_artifact_to_file', side_effect=download) as whole, \
                mock.patch('runtime_reference_archive.urllib.request.build_opener', return_value=ranges), \
                mock.patch('reuse.api_request', side_effect=api), verification_session() as session:
            work = self.root / 'new-planner'
            adapter._prepare_prior_runtime_checkpoint(plan, current, work, [artifact],
                trusted_workflow_sha=self.pin, token='not-a-real-token', completed_frozen=None)
            self.assertFalse(session.get('qualifiedOriginalProjections'))
            self.assertEqual([], ranges.requests)  # Only controls until an exact original is requested.
            recovered = self.root / 'new-capture'
            result = adapter.capture_prior_failed_runtime_phases(plan, current, requested, recovered,
                trusted_workflow_sha=self.pin, token='not-a-real-token', attempts=(self.failed_run(),))
            self.assertEqual({instance}, set(result))
            self.assertEqual(1, whole.call_count)
            self.assertEqual({self.artifacts['binary']['id']}, {row[0] for row in ranges.requests})
            self.assertEqual(self.receipts['binary'].read_bytes(),
                (recovered / TARGET / 'binary' / TARGET / 'phases/binary/original/shard/phase-receipt.json').read_bytes())
            self.assertFalse((work / 'original' / sources[1]['relativePath']).exists())
            observation = work / 'original' / Path(sources[0]['relativePath']).parents[2] / 'transport/original-ci-phases.json'
            observation.write_bytes(b'changed private controls')
            session['qualifiedOriginalProjections'].clear()
            locator = adapter._runtime_original_locator(self.artifacts['binary'], self.pin, instance, self.jobs[0])
            with self.assertRaisesRegex(ValueError, 'observation changed'):
                adapter._qualified_original_projection(locator)
        job['conclusion'] = 'failure'
        with mock.patch('reuse.api_request', side_effect=api), \
                mock.patch.object(adapter, 'download_artifact_to_file', side_effect=download), verification_session():
            with self.assertRaises(ValueError):
                adapter._prepare_prior_runtime_checkpoint(plan, current, self.root / 'failed-planner', [artifact],
                    trusted_workflow_sha=self.pin, token='not-a-real-token', completed_frozen=None)

    def test_candidate_zip_replacement_after_download_rejects_official_digest_mismatch(self):
        upload = self.root / "runtime-uploads/binary"
        (upload / "raw-validation").mkdir()
        (upload / "raw-validation/proof.json").write_bytes(b"original proof")
        raw = fixture.archive_tree(upload)
        self.archives["binary"] = raw
        self.artifacts["binary"].update(digest=fixture.sha256_bytes(raw), size_in_bytes=len(raw))
        (upload / "raw-validation/proof.json").write_bytes(b"replaced proof")
        forged = fixture.archive_tree(upload)
        download = adapter._download_contract_ci_upload
        def replaced(*args, **kwargs):
            result = download(*args, **kwargs)
            if kwargs.get("destination") is not None:
                kwargs["destination"].write_bytes(forged)
            return result
        instance = PhaseInstanceId("runtime", TARGET, "binary", TARGET)
        key = fixture.load_canonical_json_bytes(self.receipts["binary"].read_bytes())["buildKey"]
        destination = self.root / "replaced-candidate"
        run = self.failed_run()
        with mock.patch.object(adapter, "download_artifact_to_file", side_effect=self.download_fixture), \
                mock.patch("reuse.api_request", side_effect=self.api(run=run)), \
                mock.patch.object(adapter, "_download_contract_ci_upload", side_effect=replaced), \
                self.assertRaisesRegex(ValueError, "candidate archive differs from its authenticated upload"):
            adapter.capture_prior_failed_runtime_phases(
                {"event": "pull_request", "pullRequest": 31, "repository": fixture.REPOSITORY},
                {"runId": 100, "runAttempt": 1}, {instance: key}, destination,
                trusted_workflow_sha=self.pin, token="not-a-real-token", attempts=(run,))
        self.assertFalse((destination / TARGET / "binary" / TARGET).exists())

    def test_prior_failed_completed_aggregate_is_recovered_without_re_election(self):
        from products.receipt import compute_build_key, write_output_manifest
        instance = PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate")
        stage = self.root / "aggregate-stage"
        (stage / "outputs").mkdir(parents=True)
        (stage / "outputs/value.bin").write_bytes(b"synthetic immutable aggregate")
        write_output_manifest(stage, "runtime", instance.component, instance.phase, instance.target,
                              "0.2.0", {"metadata": "outputs"})
        inputs = phase_receipt()["inputs"]
        plan = {"schemaVersion": 1, **adapter._identity_record(instance), "inputs": inputs,
                "buildKey": compute_build_key(**adapter._identity_record(instance), inputs=inputs)}
        upload = self.root / "aggregate-upload"
        verified = fixture.finalize_phase_object(stage_root=stage, phase_plan=plan, producer=self.producer,
            product_version="0.2.0", trust_domain="development", destination=upload / "shard")
        self.receipts["metadata"] = upload / "shard/phase-receipt.json"
        raw = fixture.archive_tree(upload)
        self.archives["metadata"] = raw
        self.artifacts["metadata"].update(name=(
            f"codex-agent-runtime-worker-runtime-aggregate-metadata-aggregate-{plan['buildKey'][7:]}-"
            f"{self.producer['tree']}-attempt-2"), digest=fixture.sha256_bytes(raw), size_in_bytes=len(raw))
        self.jobs[-1]["name"] = "product-validation / runtime-runtime-aggregate-metadata-aggregate"
        destination = self.root / "aggregate-recovery"
        run = self.failed_run()
        with mock.patch.object(adapter, "download_artifact_to_file", side_effect=self.download_fixture), \
                mock.patch("reuse.api_request", side_effect=self.api(run=run)):
            result = adapter.capture_prior_failed_runtime_phases(
                {"event": "pull_request", "pullRequest": 31, "repository": fixture.REPOSITORY},
                {"runId": 100, "runAttempt": 1}, {instance: plan["buildKey"]}, destination,
                trusted_workflow_sha=self.pin, token="not-a-real-token", attempts=(run,))
            records = adapter._prior_failed_runtime_objects(destination, self.root,
                trusted_workflow_sha=self.pin, token="not-a-real-token")
        self.assertEqual({instance}, set(result))
        self.assertEqual(1, len(records))
        for field in ("buildKey", "receiptSha256", "objectSha256"):
            self.assertEqual(verified[field], records[0][field])

    def test_reviewed_original_workflow_survives_current_workflow_pin_rotation(self):
        legacy = adapter._PRIOR_RUNTIME_WORKFLOW_SHA
        current = "b4148a6320d3dfe8bfb556c6327937c6b304cf4c"
        self.pin = legacy
        self.run["referenced_workflows"] = [{
            "path": f"{fixture.REPOSITORY}/.github/workflows/product-validation.yml@{legacy}",
            "sha": legacy,
        }]
        failed_run = self.failed_run()
        instance = PhaseInstanceId("runtime", TARGET, "binary", TARGET)
        key = fixture.load_canonical_json_bytes(self.receipts["binary"].read_bytes())["buildKey"]
        plan = {"event": "pull_request", "pullRequest": 31, "repository": fixture.REPOSITORY}
        destination = self.root / "rotated-pin-capture"
        with mock.patch.object(adapter, "download_artifact_to_file", side_effect=self.download_fixture), \
                mock.patch("reuse.api_request", side_effect=self.api(
                    run=failed_run, artifacts={"binary": self.artifacts["binary"]})):
            captured = adapter.capture_prior_failed_runtime_phases(
                plan, {"runId": 100, "runAttempt": 1}, {instance: key}, destination,
                trusted_workflow_sha=current, token="not-a-real-token", attempts=(failed_run,))
            records = adapter._prior_failed_runtime_objects(
                destination, self.root, trusted_workflow_sha=current, token="not-a-real-token",
                plan=plan, consumer_producer={"runId": 100, "runAttempt": 1})
        self.assertEqual({instance}, set(captured))
        self.assertEqual(key, records[0]["buildKey"])
        self.assertEqual(self.receipts["binary"].read_bytes(),
                         (destination / TARGET / "binary" / TARGET / "phases/binary/original/shard/phase-receipt.json").read_bytes())

    def test_current_genuine_producer_pin_survives_next_control_rotation(self):
        for original in ("9be996a3269c324ad1beae37a06ff65219e69806",
                         "8a1c2a0c9a9ee1f3c5629d2d77278580f48a489c",
                         "cec458a479c0556d39aa6a75b18311500ce66d71",
                         "e07a185513acf0b73c0ab3114f7694999bab1845",
                         "92dddb0fc4c431b9c989c0dcd09cb200c9bc7f89",
                         "b0947995481dec088fce8e9490a17a3399e9dc2b",
                         "dcf647126e955c37f7b3c89b44cbb8497792d72f",
                         "6b982f894a12503f772c361781c89f52e01f15d9",
                         "ab1efe4f956d4e403e431544be0caf01eb7a39a0",
                         "a3620d11911883e6541ee2ac93f08b9811dfde20",
                         "a1cbc80b15a96cb2915d06afe1e29e319dda52fc"):
            with self.subTest(original=original):
                run = {"referenced_workflows": [{
                    "path": f"{fixture.REPOSITORY}/.github/workflows/product-validation.yml@{original}",
                    "sha": original,
                }]}
                self.assertEqual(original, adapter._runtime_prior_workflow_sha(run, "e" * 40))
                run["referenced_workflows"][0]["sha"] = "f" * 40
                self.assertIsNone(adapter._runtime_prior_workflow_sha(run, "e" * 40))

    def test_mixed_original_phase_workflows_are_independently_authenticated(self):
        older = "9be996a3269c324ad1beae37a06ff65219e69806"
        newer = "8a1c2a0c9a9ee1f3c5629d2d77278580f48a489c"
        self.run["referenced_workflows"] = [{
            "path": f"{fixture.REPOSITORY}/.github/workflows/product-validation.yml@{older}",
            "sha": older,
        }]
        receipt, artifact, raw, job = self.second_attempt_phase("package")
        original_api = self.two_attempt_api({"package": artifact}, [job], {"package": raw})
        later_pin = newer

        def request(url, token):
            response = original_api(url, token)
            if url.endswith("/actions/runs/72/attempts/3"):
                run = json.loads(response)
                run["referenced_workflows"] = [{
                    "path": f"{fixture.REPOSITORY}/.github/workflows/product-validation.yml@{later_pin}",
                    "sha": later_pin,
                }]
                return json.dumps(run).encode()
            return response

        receipts = {"binary": self.receipts["binary"], "package": receipt}
        with mock.patch("reuse.api_request", side_effect=request), \
                mock.patch.object(adapter, "download_artifact_to_file", side_effect=
                    self.download_two_attempt_fixture({"package": artifact}, {"package": raw})):
            result = adapter.capture_runtime_original_ci_phases(
                receipts, self.output, target=TARGET, trusted_workflow_sha="e" * 40,
                token="not-a-real-token")
            self.assertEqual({71, 72}, {value["run"]["id"] for value in result["observed"]})
            for phase, path in receipts.items():
                self.assertEqual(path.read_bytes(),
                    (self.output / f"phases/{phase}/original/shard/phase-receipt.json").read_bytes())
            later_pin = "f" * 40
            rejected = self.root / "unreviewed-workflow-capture"
            with self.assertRaisesRegex(ValueError, "reviewed producer workflow"):
                adapter.capture_runtime_original_ci_phases(
                    receipts, rejected, target=TARGET, trusted_workflow_sha="e" * 40,
                    token="not-a-real-token")
            self.assertFalse(rejected.exists())

    def test_prior_failed_phase_upload_is_diagnostic_not_a_reusable_shard(self):
        failed_run = self.failed_run()
        jobs = copy.deepcopy(self.jobs)
        jobs[1]["conclusion"] = "failure"
        listed = {phase: self.artifacts[phase] for phase in ("binary", "package")}
        destination = self.root / "prior-capture"
        plan = {"event": "pull_request", "pullRequest": 31,
                "repository": fixture.REPOSITORY}
        requested = {PhaseInstanceId("runtime", TARGET, phase, TARGET):
                     fixture.load_canonical_json_bytes(self.receipts[phase].read_bytes())["buildKey"]
                     for phase in ("binary", "package")}
        with mock.patch.object(adapter, "download_artifact_to_file", side_effect=self.download_fixture), \
                mock.patch("reuse.api_request", side_effect=self.api(run=failed_run, jobs=jobs,
                                                            artifacts=listed)):
            result = adapter.capture_prior_failed_runtime_phases(
                plan, {"runId": 100, "runAttempt": 1}, requested, destination,
                trusted_workflow_sha=self.pin, token="not-a-real-token", attempts=(failed_run,))
        self.assertEqual({PhaseInstanceId("runtime", TARGET, "binary", TARGET)}, set(result))
        self.assertFalse((destination / TARGET / "package").exists())

    def test_prior_failed_attempt_rejects_tampered_phase_without_publishing(self):
        failed_run = self.failed_run()
        malformed = copy.deepcopy(self.artifacts)
        malformed["binary"]["name"] = malformed["binary"]["name"].replace(
            self.producer["tree"], "0" * 40)
        destination = self.root / "prior-capture"
        plan = {"event": "pull_request", "pullRequest": 31,
                "repository": fixture.REPOSITORY}
        requested = {PhaseInstanceId("runtime", TARGET, "binary", TARGET):
                     fixture.load_canonical_json_bytes(self.receipts["binary"].read_bytes())["buildKey"]}
        with mock.patch.object(adapter, "download_artifact_to_file", side_effect=self.download_fixture), \
                mock.patch("reuse.api_request", side_effect=self.api(run=failed_run, artifacts=malformed,
                                                            details=malformed)), \
                self.assertRaisesRegex(ValueError, "selected attempt"):
            adapter.capture_prior_failed_runtime_phases(
                plan, {"runId": 100, "runAttempt": 1}, requested, destination,
                trusted_workflow_sha=self.pin, token="not-a-real-token", attempts=(failed_run,))
        self.assertFalse(destination.exists())

    def test_prior_failed_phases_recover_independently_from_different_attempts(self):
        _, later_validation, raw_validation, later_job = self.second_attempt_phase("validation")
        requested = {
            PhaseInstanceId("runtime", TARGET, phase, TARGET):
                fixture.load_canonical_json_bytes(self.receipts[phase].read_bytes())["buildKey"]
            for phase in ("package", "validation")
        }
        destination = self.root / "phase-wise-capture"
        plan = {"event": "pull_request", "pullRequest": 31, "repository": fixture.REPOSITORY}
        with mock.patch("reuse.api_request", side_effect=self.two_attempt_api(
                {"validation": later_validation}, [later_job], {"validation": raw_validation},
                first_artifacts={"package": self.artifacts["package"]})), \
                mock.patch.object(adapter, "download_artifact_to_file", side_effect=
                                  self.download_two_attempt_fixture(
                                      {"validation": later_validation}, {"validation": raw_validation})):
            adapter.capture_prior_failed_runtime_phases(
                plan, {"runId": 100, "runAttempt": 1}, requested, destination,
                trusted_workflow_sha=self.pin, token="not-a-real-token",
                attempts=(self.failed_run(), self.failed_run(72, 3)))
            records = adapter._prior_failed_runtime_objects(
                destination, self.root, trusted_workflow_sha=self.pin,
                token="not-a-real-token", plan=plan,
                consumer_producer={"runId": 100, "runAttempt": 1})
        self.assertEqual({"package", "validation"}, {record["phase"] for record in records})
        for phase in ("package", "validation"):
            retained = destination / TARGET / phase / TARGET / "phases" / phase / "original/shard/phase-receipt.json"
            self.assertTrue(retained.is_file())
        package = fixture.load_canonical_json_bytes(
            (destination / TARGET / "package" / TARGET / "phases/package/original/shard/phase-receipt.json").read_bytes())
        validation = fixture.load_canonical_json_bytes(
            (destination / TARGET / "validation" / TARGET / "phases/validation/original/shard/phase-receipt.json").read_bytes())
        self.assertEqual((71, 2), (package["producer"]["runId"], package["producer"]["runAttempt"]))
        self.assertEqual((72, 3), (validation["producer"]["runId"], validation["producer"]["runAttempt"]))

    def test_prior_failed_adapter_validation_target_is_captured_independently(self):
        from products.receipt import compute_build_key, write_output_manifest

        instance = PhaseInstanceId("runtime", "jvm", "validation", TARGET)
        stage = self.root / "adapter-validation-stage"
        (stage / "outputs").mkdir(parents=True)
        (stage / "outputs/value.bin").write_bytes(b"jvm validation on linux x64\n")
        write_output_manifest(stage, "runtime", "jvm", "validation", TARGET, "0.2.0",
                              {"binary": "outputs"})
        inputs = phase_receipt()["inputs"]
        phase_plan = {"schemaVersion": 1, "product": "runtime", "component": "jvm",
                      "phase": "validation", "target": TARGET, "inputs": inputs,
                      "buildKey": compute_build_key(product="runtime", component="jvm",
                          phase="validation", target=TARGET, inputs=inputs)}
        upload = self.root / "adapter-validation-upload"
        fixture.finalize_phase_object(stage_root=stage, phase_plan=phase_plan, producer=self.producer,
            product_version="0.2.0", trust_domain="development", destination=upload / "shard")
        raw = fixture.archive_tree(upload)
        artifact = {**self.artifacts["validation"], "id": 501,
                    "name": f"codex-agent-runtime-worker-jvm-validation-{TARGET}-"
                            f"{phase_plan['buildKey'][7:]}-{self.producer['tree']}-attempt-2",
                    "digest": fixture.sha256_bytes(raw), "size_in_bytes": len(raw)}
        artifact["archive_download_url"] = (
            f"https://api.github.com/repos/{fixture.REPOSITORY}/actions/artifacts/501/zip")
        job = {**self.jobs[2], "id": 501,
               "name": f"product-validation / runtime-jvm-validation-{TARGET}"}
        original_api = self.api(run=self.failed_run())
        prefix = f"https://api.github.com/repos/{fixture.REPOSITORY}"

        def request(url, token):
            if url.startswith(prefix + "/actions/runs/71/artifacts?"):
                return json.dumps({"artifacts": [artifact]}).encode()
            if url.startswith(prefix + "/actions/runs/71/attempts/2/jobs?"):
                return json.dumps({"jobs": [job]}).encode()
            if url == prefix + "/actions/artifacts/501":
                return json.dumps(artifact).encode()
            if url == artifact["archive_download_url"]:
                return raw
            return original_api(url, token)

        def download(candidate, token, destination, **_):
            self.assertEqual(501, candidate["id"])
            Path(destination).write_bytes(raw)

        plan = {"event": "pull_request", "pullRequest": 31, "repository": fixture.REPOSITORY}
        destination = self.root / "adapter-phase-capture"
        with mock.patch("reuse.api_request", side_effect=request), \
                mock.patch.object(adapter, "download_artifact_to_file", side_effect=download):
            captured = adapter.capture_prior_failed_runtime_phases(
                plan, {"runId": 100, "runAttempt": 1}, {instance: phase_plan["buildKey"]}, destination,
                trusted_workflow_sha=self.pin, token="not-a-real-token",
                attempts=(self.failed_run(),))
            records = adapter._prior_failed_runtime_objects(
                destination, self.root, trusted_workflow_sha=self.pin,
                token="not-a-real-token", plan=plan,
                consumer_producer={"runId": 100, "runAttempt": 1})
        self.assertEqual({instance}, set(captured))
        self.assertEqual([(instance.component, instance.phase, instance.target)],
                         [(record["component"], record["phase"], record["target"]) for record in records])
        self.assertEqual((upload / "shard/phase-receipt.json").read_bytes(),
            (destination / "jvm/validation" / TARGET / "phases/validation/original/shard/phase-receipt.json").read_bytes())

    def test_prior_failed_phase_rejects_failed_or_partial_job_upload(self):
        instance = PhaseInstanceId("runtime", TARGET, "package", TARGET)
        requested = {instance: fixture.load_canonical_json_bytes(self.receipts["package"].read_bytes())["buildKey"]}
        plan = {"event": "pull_request", "pullRequest": 31, "repository": fixture.REPOSITORY}
        failed_jobs = copy.deepcopy(self.jobs)
        failed_jobs[1]["conclusion"] = "failure"
        destination = self.root / "failed-phase-capture"
        with mock.patch("reuse.api_request", side_effect=self.two_attempt_api({}, [], {},
                first_jobs=failed_jobs)), \
                mock.patch.object(adapter, "download_artifact_to_file", side_effect=
                                  self.download_two_attempt_fixture({}, {})):
            result = adapter.capture_prior_failed_runtime_phases(
                plan, {"runId": 100, "runAttempt": 1}, requested, destination,
                trusted_workflow_sha=self.pin, token="not-a-real-token",
                attempts=(self.failed_run(),))
        self.assertFalse(result)
        self.assertFalse(destination.exists())

        # A success-labelled job with only a diagnostic upload cannot become
        # a successful phase shard.
        partial = self.root / "partial-upload"
        partial.mkdir()
        (partial / "gradle.log").write_text("phase failed\n", encoding="utf-8")
        raw = fixture.archive_tree(partial)
        artifact = {**self.artifacts["package"], "digest": fixture.sha256_bytes(raw),
                    "size_in_bytes": len(raw)}
        original_api = self.api(artifacts={"package": artifact}, details={"package": artifact},
                                archives={**self.archives, "package": raw}, run=self.failed_run())
        with mock.patch("reuse.api_request", side_effect=original_api), \
                mock.patch.object(adapter, "download_artifact_to_file", side_effect=
                                  self.download_two_attempt_fixture({}, {},
                                      first_archives={**self.archives, "package": raw})), \
                self.assertRaises(ValueError):
            adapter.capture_prior_failed_runtime_phases(
                plan, {"runId": 100, "runAttempt": 1}, requested, destination,
                trusted_workflow_sha=self.pin, token="not-a-real-token",
                attempts=(self.failed_run(),))
        self.assertFalse(destination.exists())

    def test_prior_failed_same_key_different_product_object_is_rejected(self):
        second_receipt, second_artifact, second_raw, second_job = self.second_attempt_phase(
            "package", changed_output=True)
        instance = PhaseInstanceId("runtime", TARGET, "package", TARGET)
        key = fixture.load_canonical_json_bytes(self.receipts["package"].read_bytes())["buildKey"]
        destination = self.root / "conflicting-phase-capture"
        plan = {"event": "pull_request", "pullRequest": 31, "repository": fixture.REPOSITORY}
        warm = False
        api = self.two_attempt_api({"package": second_artifact}, [second_job], {"package": second_raw})
        download = self.download_two_attempt_fixture({"package": second_artifact}, {"package": second_raw})

        def request(url, *args):
            self.assertFalse(warm and url.endswith("/zip"), "warm body download")
            return api(url, *args)

        def transfer(*args, **kwargs):
            self.assertFalse(warm, "warm body download")
            return download(*args, **kwargs)

        with mock.patch("reuse.api_request", side_effect=request), \
                mock.patch.object(adapter, "download_artifact_to_file", side_effect=transfer):
            for number, receipt in enumerate((self.receipts["package"], second_receipt)):
                # Seed both complete genuine original verifications. Warm
                # discovery must still scan both receipts and reject conflicts.
                adapter.capture_runtime_original_ci_phases({"package": receipt}, self.root / f"seed-{number}",
                    target=TARGET, trusted_workflow_sha=self.pin, token="not-a-real-token",
                    recovery_projection=True)
            warm = True
            with self.assertRaisesRegex(ValueError, "conflict|different|same.key"):
                adapter.capture_prior_failed_runtime_phases(
                    plan, {"runId": 100, "runAttempt": 1}, {instance: key}, destination,
                    trusted_workflow_sha=self.pin, token="not-a-real-token",
                    attempts=(self.failed_run(), self.failed_run(72, 3)))
        self.assertFalse(destination.exists())

    def test_late_original_shard_mutation_cannot_publish(self):
        def mutate_before_copy(source, destination, **kwargs):
            (Path(source) / "phases/binary/original/shard/phase-receipt.json").write_bytes(
                b"changed after verification")
            actual_publish_regular_tree(source, destination, **kwargs)

        with mock.patch.object(adapter, "publish_regular_tree", side_effect=mutate_before_copy), \
                self.assertRaisesRegex(ValueError, "pinned inventory"):
            self.capture()
        self.assertFalse(self.output.exists())

    def test_failed_job_wrong_attempt_window_digest_and_workflow_reject(self):
        failed = copy.deepcopy(self.jobs)
        failed[2]["conclusion"] = "failure"
        window = copy.deepcopy(self.artifacts)
        window["metadata"]["created_at"] = "2026-09-06T11:00:00Z"
        wrong_pin = copy.deepcopy(self.run)
        wrong_pin["referenced_workflows"][0]["sha"] = "a" * 40
        for changes in ({"jobs": failed}, {"artifacts": window, "details": window},
                        {"run": wrong_pin}, {"archives": {**self.archives, "binary": b"changed"}}):
            with self.subTest(changes=list(changes)), self.assertRaises(ValueError):
                self.capture(**changes)
            self.assertFalse(self.output.exists())

    def test_wrong_receipt_and_missing_upload_reject_without_output(self):
        self.receipts["metadata"] = self.receipts["binary"]
        with self.assertRaisesRegex(ValueError, "phase identity"):
            self.capture()
        self.receipts["metadata"] = self.root / "runtime-uploads/metadata/shard/phase-receipt.json"
        missing = {phase: value for phase, value in self.artifacts.items() if phase != "metadata"}
        with self.assertRaisesRegex(ValueError, "missing or ambiguous"):
            self.capture(artifacts=missing)
        self.assertFalse(self.output.exists())

    def test_valid_but_different_receipt_is_not_laundered_by_the_upload(self):
        path = self.receipts["metadata"]
        value = fixture.load_canonical_json_bytes(path.read_bytes())
        value["productVersion"] = "0.2.1"
        path.write_bytes(fixture.canonical_json_bytes(value))
        with self.assertRaisesRegex(ValueError, "differs from the requested original receipt"):
            self.capture()
        self.assertFalse(self.output.exists())

    def test_mixed_original_run_attempts_keep_their_receipts(self):
        producer = {**self.producer, "runId": 72, "runAttempt": 3}
        prior = fixture.load_canonical_json_bytes(self.receipts["metadata"].read_bytes())
        plan = {key: prior[key] for key in ("schemaVersion", "product", "component", "phase", "target", "buildKey", "inputs")}
        upload = self.root / "later-original"
        fixture.finalize_phase_object(stage_root=self.root / "runtime-stages/metadata", phase_plan=plan,
            producer=producer, product_version="0.2.0", trust_domain="development", destination=upload / "shard")
        self.receipts["metadata"] = upload / "shard/phase-receipt.json"
        raw = fixture.archive_tree(upload)
        self.archives["metadata"] = raw
        artifact = self.artifacts["metadata"]
        artifact.update(name=artifact["name"].removesuffix("attempt-2") + "attempt-3",
                        digest=fixture.sha256_bytes(raw), size_in_bytes=len(raw),
                        workflow_run={"id": 72, "head_sha": self.run["head_sha"]})
        later_run = {**self.run, "id": 72, "run_attempt": 3}
        later_job = {**self.jobs[-1], "run_id": 72}
        original_api = self.api()
        prefix = f"https://api.github.com/repos/{fixture.REPOSITORY}/actions/runs/72"

        def request(url, token):
            if url == prefix + "/attempts/3":
                return json.dumps(later_run).encode()
            if url.startswith(prefix + "/attempts/3/jobs?"):
                return json.dumps({"jobs": [later_job]}).encode()
            if url.startswith(prefix + "/artifacts?"):
                return json.dumps({"artifacts": [artifact]}).encode()
            return original_api(url, token)

        with mock.patch("reuse.api_request", side_effect=request):
            result = adapter.capture_runtime_original_ci_phases(self.receipts, self.output,
                target=TARGET, trusted_workflow_sha=self.pin, token="not-a-real-token")
        self.assertEqual(2, len(result["observed"]))
        self.assertEqual(self.receipts["metadata"].read_bytes(),
            (self.output / "phases/metadata/original/shard/phase-receipt.json").read_bytes())


class RuntimeRetainedOriginalTest(unittest.TestCase):
    api = fixture.ContractOriginalCiCaptureTest.api

    def setUp(self):
        RuntimeOriginalCiTest.setUp(self)
        from ci.tests import test_product_runtime_variant as variant
        from products.runtime_attestation import build_runtime_variant_attestation
        from products.signatures import generate_development_key
        self.private, self.public, signing = generate_development_key(self.root / "release-key")
        self.signing = {**signing, "trustDomain": "release", "keyId": "retained-fixture"}
        self.keys = self.root / "public-policy/keys"
        self.keys.mkdir(parents=True)
        (self.keys / "retained-fixture.pub").write_bytes(self.public.read_bytes())
        self.keyring = self.keys.parent / "keyring.json"
        policy = {"schemaVersion": 1, **{key: self.signing[key] for key in ("algorithm", "namespace", "trustDomain")},
                  "activeKey": {key: self.signing[key] for key in ("keyId", "fingerprint")}, "retiredKeys": []}
        self.keyring.write_bytes(fixture.canonical_json_bytes(policy))
        original = variant.Fixture(self.root / "native-original", self.private, self.public, signing)
        self.payload = variant.produce_runtime_variant(**original.arguments())["bundlePath"]
        self.receipts = {**original.receipt_paths, "metadata": variant._write_metadata_receipt(original, self.payload)}
        self.handoff = self.root / "release-handoff"
        build_runtime_variant_attestation(self.payload, *(self.receipts[phase] for phase in fixture.PHASES),
            original.validation, self.signing, self.private, self.public, self.handoff,
            keyring=self.keyring, keys_directory=self.keys, complete_handoff=True)

    def capture(self, **changes):
        arguments = dict(target=TARGET, trusted_workflow_sha=self.pin, token="not-a-real-token",
                         release_handoffs=(self.handoff,), keyring=self.keyring, keys_directory=self.keys)
        arguments.update(changes)
        return adapter.capture_runtime_original_ci_phases(self.receipts, self.output, **arguments)

    def test_complete_retired_release_reuses_without_network_or_signing(self):
        policy = fixture.load_canonical_json_bytes(self.keyring.read_bytes())
        policy["retiredKeys"] = [policy["activeKey"]]
        policy["activeKey"] = None
        self.keyring.write_bytes(fixture.canonical_json_bytes(policy))
        before = fixture.regular_file_inventory(self.handoff)
        with mock.patch("reuse.api_request", side_effect=AssertionError("network")), \
                mock.patch("products.runtime_attestation.sign_manifest", side_effect=AssertionError("sign")):
            result = self.capture()
        self.assertEqual([], result["observed"])
        self.assertEqual({}, result["artifacts"])
        self.assertEqual(dict.fromkeys(fixture.PHASES, 0), result["releaseAttestations"])
        self.assertEqual(before, fixture.regular_file_inventory(self.output / "release-handoffs/0"))
        self.assertEqual(before, fixture.regular_file_inventory(self.handoff))

    def test_private_release_policy_swap_cannot_publish(self):
        original = adapter.load_keyring
        caller_bytes = self.keyring.read_bytes()
        swapped = False

        def swap_after_private_copy(keyring, keys):
            nonlocal swapped
            result = original(keyring, keys)
            keyring, keys = Path(keyring), Path(keys)
            if not swapped and keys.parent == keyring.parent:
                value = fixture.load_canonical_json_bytes(keyring.read_bytes())
                value["retiredKeys"] = [value["activeKey"]]
                value["activeKey"] = None
                keyring.write_bytes(fixture.canonical_json_bytes(value))
                swapped = True
            return result

        with mock.patch.object(adapter, "load_keyring", side_effect=swap_after_private_copy), \
                mock.patch("reuse.api_request", side_effect=AssertionError("network")), \
                self.assertRaisesRegex(ValueError, "release policy differs from caller"):
            self.capture()
        self.assertTrue(swapped)
        self.assertEqual(caller_bytes, self.keyring.read_bytes())
        self.assertFalse(self.output.exists())

    def test_mixed_release_and_ci_preserves_originals_and_fetches_only_missing_phase(self):
        from products.receipt import write_output_manifest
        receipt = fixture.load_canonical_json_bytes(self.receipts["metadata"].read_bytes())
        stage = self.root / "new-metadata-stage"
        (stage / "outputs").mkdir(parents=True)
        (stage / "outputs" / self.payload.name).write_bytes(self.payload.read_bytes())
        write_output_manifest(stage, "runtime", TARGET, "metadata", TARGET, receipt["productVersion"],
                              {"runtime-variant": "outputs"})
        upload = self.root / "new-metadata-upload"
        plan = {key: receipt[key] for key in ("schemaVersion", "product", "component", "phase", "target", "buildKey", "inputs")}
        fixture.finalize_phase_object(stage_root=stage, phase_plan=plan, producer=self.producer,
            product_version=receipt["productVersion"], trust_domain="development", destination=upload / "shard")
        self.receipts["metadata"] = upload / "shard/phase-receipt.json"
        raw = fixture.archive_tree(upload)
        self.archives["metadata"] = raw
        self.artifacts["metadata"].update(digest=fixture.sha256_bytes(raw), size_in_bytes=len(raw),
            name=f"codex-agent-runtime-worker-{TARGET}-metadata-{TARGET}-{receipt['buildKey'][7:]}-{self.producer['tree']}-attempt-2")
        with mock.patch("reuse.api_request", side_effect=self.api()) as http:
            result = self.capture()
        self.assertEqual({"metadata"}, set(result["artifacts"]))
        self.assertEqual(dict.fromkeys(("binary", "package", "validation"), 0), result["releaseAttestations"])
        downloaded = [call.args[0] for call in http.call_args_list if call.args[0].endswith("/zip")]
        self.assertEqual([self.artifacts["metadata"]["archive_download_url"]], downloaded)

    def test_invalid_retained_evidence_never_falls_back_to_ci(self):
        with mock.patch("reuse.api_request", side_effect=AssertionError("network")):
            for changes in ({"keyring": None}, {"keys_directory": None}, {"release_handoffs": ()},
                            {"target": "macos-x64"}):
                with self.subTest(changes=changes), self.assertRaises(ValueError):
                    self.capture(**changes)
                self.assertFalse(self.output.exists())
            (self.handoff / "unexpected").write_bytes(b"untrusted")
            with self.assertRaises(ValueError):
                self.capture()
            self.assertFalse(self.output.exists())
