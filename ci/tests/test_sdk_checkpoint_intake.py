"""Native wrapper custody with HTTP/native-verifier fixtures, never live authority."""
from contextlib import ExitStack
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import completed_sdk_reuse as completed
import product_reuse as products
import reuse
import reuse_qualification as native
from products.inventory import canonical_json_bytes, sha256_bytes
from products.registry import PhaseInstanceId


class SdkCheckpointIntakeTest(unittest.TestCase):
    def setUp(self):
        # Historical recipe shape only. No archived subject is changed or issued;
        # the source inventory is normalized solely for this synthetic new route.
        self.spec = json.loads((Path(products.__file__).resolve().parent /
            'tests/data/requalified-sdk-completed-resume.json').read_bytes())
        self.source = self.spec['source']
        self.producer = self.source['producer']
        self.source['inventoryCommit'] = self.producer['commit']
        self.policy = {'schemaVersion': 1, 'kind': 'sdk-checkpoint-owner', 'issuerCommit': 'b' * 40,
            'collectorWorkflowSha': self.source['workflowSha'], 'parent': self.spec['parent'],
            'parentProofSha256': self.spec['parentProofSha256'], 'bootstrap': self.spec['reuseCompletion'],
            'bootstrapProofSha256': self.spec['reuseCompletionProofSha256'], 'collectors': [self.source['jobName']]}
        self.selector = dict(artifactId=990, artifactSha256=sha256_bytes(b'pending'),
            runId=self.producer['runId'], runAttempt=self.producer['runAttempt'],
            signerCommit=self.policy['issuerCommit'], sourceCommit=self.producer['commit'])
        self.identity = completed.checkpoint_archive_identity(self.policy, self.source,
            **{key: value for key, value in native._native_pin_arguments(self.selector).items()
               if key in ('signer_commit', 'source_commit', 'run_id', 'run_attempt')})
        self.run = dict(id=self.producer['runId'], run_attempt=self.producer['runAttempt'],
            path=self.producer['workflowPath'], head_sha='f' * 40, event='pull_request', status='in_progress',
            conclusion=None, pull_requests=[{'number': 31, 'base': {'sha': '1' * 40}, 'head': {'sha': 'f' * 40}}],
            repository={'full_name': native.REPOSITORY, 'fork': False},
            head_repository={'full_name': native.REPOSITORY, 'fork': False},
            referenced_workflows=[{'path': self.identity['collectorWorkflow'], 'sha': self.source['workflowSha']},
                {'path': f'{native.REPOSITORY}/{native.ISSUER_WORKFLOW}@{self.policy["issuerCommit"]}',
                 'sha': self.policy['issuerCommit']}])
        self.commit = dict(sha=self.producer['commit'], tree={'sha': self.producer['tree']},
                           parents=[{'sha': '1' * 40}, {'sha': 'f' * 40}])
        self.collector = dict(id=self.source['jobId'], name=self.source['jobName'],
            run_id=self.producer['runId'], head_sha=self.run['head_sha'], status='completed', conclusion='success',
            started_at='2026-10-24T10:00:00Z', completed_at='2026-10-24T10:30:00Z')
        self.issuer = {**self.collector, 'id': 991, 'name': self.identity['jobName'],
            'started_at': '2026-10-24T10:31:00Z', 'completed_at': '2026-10-24T10:40:00Z'}
        self.jobs = [self.collector, self.issuer]
        self.artifacts = {self.source['artifactId']: self.artifact(self.source['artifactId'],
            f'codex-agent-sdk-wave-{completed._COLLECTED_WAVES[self.source["jobName"]]}-state-{self.producer["tree"]}-attempt-{self.producer["runAttempt"]}',
            self.source['artifactSha256'], self.source['artifactBytes'], '10:10:00'),
            992: self.artifact(992, completed.collector_control_artifact_name(self.source),
                sha256_bytes(b'small controls already qualified by native issuer'), 1000, '10:20:00')}
        locator = products._runtime_original_locator(self.artifacts[self.source['artifactId']],
            self.source['workflowSha'], PhaseInstanceId('sdk', 'javascript', 'metadata', 'node'), self.collector)
        self.envelope = {'schemaVersion': 1, 'kind': 'completed-sdk-checkpoint',
            'issuerCommit': self.policy['issuerCommit'], 'ownerPolicySha256': sha256_bytes(canonical_json_bytes(self.policy)),
            'recipe': self.spec, 'completion': {'schemaVersion': 4, 'kind': 'completed-sdk-reuse',
                'issuerCommit': self.policy['issuerCommit'], 'specSha256': sha256_bytes(canonical_json_bytes(self.spec)),
                'source': locator}, 'sourceCheckpoint': {'source': self.source,
                    'controlArtifact': {'artifactId': 992, 'artifactSha256': self.artifacts[992]['digest']}},
            'precedingCheckpoint': {'native': self.policy['bootstrap'], 'subjectSha256': self.policy['bootstrapProofSha256']}}
        temporary = tempfile.TemporaryDirectory(prefix='sdk-checkpoint-intake-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.urls, self.downloads, self.verified = [], [], []
        self.number = 0
        self.upload()

    def artifact(self, identity, name, digest, size, clock):
        return dict(id=identity, name=name, digest=digest, size_in_bytes=size, expired=False,
            created_at='2026-10-24T' + clock + 'Z',
            workflow_run={'id': self.producer['runId'], 'head_sha': self.run['head_sha']},
            archive_download_url=f'https://api.github.com/repos/{native.REPOSITORY}/actions/artifacts/{identity}/zip')

    def upload(self, *, subject=None, extra=False):
        self.subject = canonical_json_bytes(self.envelope) if subject is None else subject
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('completion.json', self.subject)
            archive.writestr('bundle.jsonl', b'fixture native bundle; not genuine authority\n')
            if extra: archive.writestr('extra', b'unexpected')
        self.raw = stream.getvalue()
        self.selector['artifactSha256'] = sha256_bytes(self.raw)
        self.artifacts[990] = self.artifact(990, self.identity['artifactName'],
            self.selector['artifactSha256'], len(self.raw), '10:35:00')

    def api(self, url, token):
        self.urls.append(url)
        base = f'https://api.github.com/repos/{native.REPOSITORY}'
        attempt = f'{base}/actions/runs/{self.producer["runId"]}/attempts/{self.producer["runAttempt"]}'
        if url == attempt: result = self.run
        elif url.startswith(attempt + '/jobs?'): result = {'jobs': self.jobs}
        elif url == base + '/git/commits/' + self.producer['commit']: result = self.commit
        elif url.startswith(base + '/actions/artifacts/'): result = self.artifacts[int(url.rsplit('/', 1)[1])]
        else: raise AssertionError('unexpected HTTP: ' + url)
        return json.dumps(deepcopy(result)).encode()

    def download(self, artifact, token):
        self.assertEqual(990, artifact['id'], 'never download state, controls or product bodies here')
        self.downloads.append(artifact['id'])
        return self.raw

    def verify(self, subject, bundle, name, **pins):
        self.assertEqual(self.subject, subject)
        self.assertEqual('completion.json', name)
        self.assertEqual({'signer_commit': self.policy['issuerCommit'], 'source_commit': self.producer['commit']}, pins)
        self.verified.append(subject)

    def fetch(self, *, verifier=None):
        self.number += 1
        with ExitStack() as stack:
            stack.enter_context(patch.object(reuse, 'api_request', side_effect=self.api))
            stack.enter_context(patch.object(products, 'download_artifact', side_effect=self.download))
            stack.enter_context(patch.object(native, '_authenticate_native_subject', side_effect=verifier or self.verify))
            stack.enter_context(patch.object(native, 'CompletedFrozenReuse', side_effect=AssertionError('custody is not completion')))
            return completed.fetch_checkpoint_envelope(self.policy, self.source, self.selector,
                self.root / str(self.number), token='synthetic')

    def test_live_run_native_checkpoint_transfers_only_small_proof_and_grants_no_semantics(self):
        result = self.fetch()
        self.assertFalse(result['semanticAuthority'])
        self.assertEqual(self.envelope, result['envelope'])
        self.assertEqual(sha256_bytes(self.subject), result['subjectSha256'])
        self.assertEqual([990], self.downloads)
        self.assertEqual(1, len(self.verified))
        self.assertEqual(1, sum(url.endswith('/actions/artifacts/990') for url in self.urls))
        base = f'https://api.github.com/repos/{native.REPOSITORY}'
        attempt = f'{base}/actions/runs/{self.producer["runId"]}/attempts/{self.producer["runAttempt"]}'
        self.assertEqual(1, self.urls.count(attempt))
        self.assertEqual(1, self.urls.count(base + '/git/commits/' + self.producer['commit']))
        self.assertEqual(1, sum(url.startswith(attempt + '/jobs?') for url in self.urls))

    def test_fresh_observation_is_private_exact_immutable_and_closes_on_exit(self):
        with patch.object(reuse, 'api_request', side_effect=self.api):
            with products._fresh_ci_observation(self.producer, 'synthetic') as observation:
                data = products._fresh_ci_observation_values(observation, self.producer, 'synthetic')
                with self.assertRaises(ValueError):
                    products._fresh_ci_observation_values(data, self.producer, 'synthetic')
                with self.assertRaises(ValueError):
                    products._FreshCIObservation(self.producer, 'synthetic', data, object())
                data['jobs'].clear()
                self.assertEqual(2, len(products._fresh_ci_observation_values(observation, self.producer, 'synthetic')['jobs']))
                for producer, token in (({**self.producer, 'runAttempt': 99}, 'synthetic'),
                                        (self.producer, 'other')):
                    with self.assertRaises(ValueError):
                        products._fresh_ci_observation_values(observation, producer, token)
                with self.assertRaisesRegex(ValueError, 'full-discovery'):
                    products._observe_ci_producer_jobs({'source': self.producer},
                        jobs_by_phase={'source': self.source['jobName']}, token='synthetic',
                        trusted_workflow_sha=self.source['workflowSha'],
                        native_job_ids_by_phase={'source': self.source['jobId']}, _fresh_observation=observation)
            with self.assertRaisesRegex(ValueError, 'closed'):
                products._fresh_ci_observation_values(observation, self.producer, 'synthetic')

    def test_whole_zip_then_native_authentication_precedes_dynamic_json(self):
        self.raw += b'tampered'
        with self.assertRaises(ValueError): self.fetch()
        self.assertFalse(self.verified)
        self.upload(subject=b'{ invalid JSON must not be parsed before native verification')
        def reject(*args, **kwargs): raise RuntimeError('native signature rejected')
        with self.assertRaisesRegex(RuntimeError, 'native signature rejected'): self.fetch(verifier=reject)

    def test_official_issuer_identity_and_legacy_names_reject_before_any_body(self):
        original = deepcopy((self.run, self.jobs, self.artifacts, self.commit))
        cases = ('portable-path', 'wrong-role', 'failed', 'duplicate-job', 'retry', 'tree',
                 'workflow', 'duplicate-reference', 'legacy-name', 'expired', 'window', 'size')
        for case in cases:
            with self.subTest(case=case):
                self.run, self.jobs, self.artifacts, self.commit = deepcopy(original)
                issuer = self.jobs[1]
                if case == 'portable-path': self.run['path'] = '.github/workflows/portable-reuse-proof.yml'
                elif case == 'wrong-role': issuer['name'] = 'completion / completed-sdk'
                elif case == 'failed': issuer['conclusion'] = 'failure'
                elif case == 'duplicate-job': self.jobs.append(deepcopy(issuer))
                elif case == 'retry': self.run['run_attempt'] += 1
                elif case == 'tree': self.commit['tree']['sha'] = 'd' * 40
                elif case == 'workflow': self.run['referenced_workflows'][1]['sha'] = 'd' * 40
                elif case == 'duplicate-reference': self.run['referenced_workflows'].append(deepcopy(self.run['referenced_workflows'][1]))
                elif case == 'legacy-name': self.artifacts[990]['name'] = f'sdk-completed-reuse-{self.producer["runId"]}-1'
                elif case == 'expired': self.artifacts[990]['expired'] = True
                elif case == 'window': self.artifacts[990]['created_at'] = '2026-10-24T12:00:00Z'
                elif case == 'size': self.artifacts[990]['size_in_bytes'] = 2 * completed.LIMIT + 1
                with self.assertRaises(ValueError): self.fetch()
                self.assertEqual([], self.downloads)

    def test_authenticated_envelope_cannot_change_owner_recipe_bootstrap_or_source(self):
        original = deepcopy(self.envelope)
        for case in ('owner', 'issuer', 'recipe', 'parent', 'previous', 'source', 'proof', 'schema', 'control'):
            with self.subTest(case=case):
                self.envelope = deepcopy(original)
                if case == 'owner': self.envelope['ownerPolicySha256'] = sha256_bytes(b'wrong')
                elif case == 'issuer': self.envelope['issuerCommit'] = 'd' * 40
                elif case == 'recipe': self.envelope['recipe']['originals'][0]['artifactId'] += 1
                elif case == 'parent': self.envelope['recipe']['parent']['artifactId'] += 1
                elif case == 'previous': self.envelope['precedingCheckpoint']['native']['artifactId'] += 1
                elif case == 'source': self.envelope['sourceCheckpoint']['source']['jobId'] += 1
                elif case == 'proof': self.envelope['completion']['source']['job']['id'] += 1
                elif case == 'schema': self.envelope['schemaVersion'] = True
                elif case == 'control': self.envelope['sourceCheckpoint']['controlArtifact']['artifactId'] = self.source['artifactId']
                self.upload()
                with self.assertRaises(ValueError): self.fetch()

    def test_current_attempt_predecessor_stays_closed_without_order_witness(self):
        self.policy['bootstrap']['runId'] = self.producer['runId']
        self.policy['bootstrap']['runAttempt'] = self.producer['runAttempt']
        self.envelope['ownerPolicySha256'] = sha256_bytes(canonical_json_bytes(self.policy))
        self.envelope['completion']['specSha256'] = sha256_bytes(canonical_json_bytes(self.spec))
        self.upload()
        with self.assertRaisesRegex(ValueError, 'must precede'): self.fetch()

    def test_failed_collector_expired_control_and_reverse_job_order_never_admit(self):
        for case in ('failed', 'expired-control', 'reverse'):
            with self.subTest(case=case):
                if case == 'failed': self.collector['conclusion'] = 'failure'
                elif case == 'expired-control': self.artifacts[992]['expired'] = True
                else: self.issuer['started_at'] = '2026-10-24T10:29:00Z'
                with self.assertRaises(ValueError): self.fetch()
                self.collector['conclusion'] = 'success'
                self.artifacts[992]['expired'] = False
                self.issuer['started_at'] = '2026-10-24T10:31:00Z'

    def test_extra_archive_member_rejects_before_native_and_legacy_ci_route_stays_closed(self):
        self.upload(extra=True)
        with self.assertRaises(ValueError): self.fetch()
        self.assertFalse(self.verified)
        with patch.object(reuse, 'api_request', side_effect=self.api), \
                patch.object(products, 'download_artifact', side_effect=AssertionError('no legacy body')):
            with self.assertRaisesRegex(ValueError, 'fixed original producer'):
                native._fetch_qualification_archive(self.root / 'legacy',
                    **native._native_pin_arguments(self.selector), token='synthetic', _completed_sdk=True)


if __name__ == '__main__':
    unittest.main()
