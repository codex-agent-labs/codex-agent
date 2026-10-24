"""Small control custody, using real observers and validators with HTTP fixtures."""
from copy import deepcopy
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
import io
import json
import stat
import tempfile
import unittest
import warnings
import zipfile

import completed_sdk_reuse as completed
import product_reuse as products
import reuse
from products.inventory import canonical_json_bytes, sha256_bytes
from products.restore import object_relative_path
from ci.tests.test_completed_sdk_reuse import CompletedSdkControlsTest, control_bytes


class CollectorControlsTest(unittest.TestCase):
    def setUp(self):
        fixture = CompletedSdkControlsTest()
        fixture.setUp()
        self.controls = {path.replace('product-resume-state/', 'runtime-state/'): value
                         for path, value in fixture.controls.items()}
        self.producer = self.controls['runtime-state/producer.json']
        self.producer['workflowPath'] = '.github/workflows/ci.yml'
        self.role, self.pin = 'product-validation / sdk-collect-9', 'c' * 40
        plan = {key: self.producer[key] for key in ('repository', 'event', 'pullRequest')}
        plan.update(validationCommit=self.producer['commit'], validationTree=self.producer['tree'], remoteBuildAuthorized=True)
        self.controls[completed.SOURCE_PLAN] = json.dumps(plan, indent=2) + '\n'
        inventory = [{'relativePath': path, 'bytes': len(control_bytes(path, value)),
                      'sha256': sha256_bytes(control_bytes(path, value))}
                     for path, value in sorted(self.controls.items())]
        self.references = {'schemaVersion': 1, 'base': {'artifactId': 1,
            'artifactSha256': sha256_bytes(b'base'), 'stateWave': 0}, 'inventory': inventory,
            'references': [{**inventory[0], 'sourcePath': inventory[0]['relativePath']}]}
        self.reference_bytes = canonical_json_bytes(self.references)
        self.source = dict(producer=self.producer, workflowSha=self.pin, jobName=self.role, jobId=801,
            artifactId=700, artifactSha256=sha256_bytes(b'large state body never downloaded'),
            artifactBytes=6 * 1024**3, inventoryCommit=self.producer['commit'],
            referenceControlSha256=sha256_bytes(self.reference_bytes))
        self.run = dict(id=self.producer['runId'], run_attempt=self.producer['runAttempt'],
            path=self.producer['workflowPath'], head_sha='f' * 40, event='pull_request',
            status='in_progress', conclusion=None,
            pull_requests=[{'number': 31, 'base': {'sha': '1' * 40}, 'head': {'sha': 'f' * 40}}],
            repository={'full_name': self.producer['repository'], 'fork': False},
            head_repository={'full_name': self.producer['repository'], 'fork': False},
            referenced_workflows=[{'path': self.producer['repository'] + '/.github/workflows/product-validation.yml@' + self.pin,
                                   'sha': self.pin}])
        self.commit = dict(sha=self.producer['commit'], tree={'sha': self.producer['tree']},
                           parents=[{'sha': '1' * 40}, {'sha': 'f' * 40}])
        self.job = dict(id=801, name=self.role, run_id=self.producer['runId'], head_sha=self.run['head_sha'],
            status='completed', conclusion='success', started_at='2026-10-24T10:00:00Z',
            completed_at='2026-10-24T10:30:00Z')
        self.artifacts = {700: self.artifact(700, 'codex-agent-sdk-wave-9-state-' + self.producer['tree']
            + '-attempt-' + str(self.producer['runAttempt']), self.source['artifactSha256'], self.source['artifactBytes'])}
        self.urls, self.downloads = [], []
        temporary = tempfile.TemporaryDirectory(prefix='collector-control-test-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.output_index = 0

    def artifact(self, identity, name, digest, size):
        return dict(id=identity, name=name, digest=digest, size_in_bytes=size, expired=False,
            created_at='2026-10-24T10:10:00Z' if identity == 700 else '2026-10-24T10:20:00Z',
            workflow_run={'id': self.producer['runId'], 'head_sha': self.run['head_sha']},
            archive_download_url=f"https://api.github.com/repos/{self.producer['repository']}/actions/artifacts/{identity}/zip")

    def files(self):
        return completed.prepare_collector_controls(self.source, self.reference_bytes, self.controls)

    def upload(self, files=None, *, entries=None):
        buffer = io.BytesIO()
        with warnings.catch_warnings(), zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            warnings.simplefilter('ignore', UserWarning)
            for name, raw in (entries if entries is not None else (self.files() if files is None else files).items()):
                archive.writestr(name, raw)
        self.archive = buffer.getvalue()
        digest = sha256_bytes(self.archive)
        self.artifacts[701] = self.artifact(701, completed.collector_control_artifact_name(self.source), digest, len(self.archive))
        return {'artifactId': 701, 'artifactSha256': digest}

    def api(self, url, token):
        self.urls.append(url)
        base = f"https://api.github.com/repos/{self.producer['repository']}"
        run = f"{base}/actions/runs/{self.producer['runId']}/attempts/{self.producer['runAttempt']}"
        if url == run: value = self.run
        elif url.startswith(run + '/jobs?'): value = {'jobs': [self.job]}
        elif url == base + '/git/commits/' + self.producer['commit']: value = self.commit
        elif url.startswith(base + '/actions/artifacts/'):
            value = self.artifacts[int(url.rsplit('/', 1)[1])]
        else: raise AssertionError('Unexpected HTTP read: ' + url)
        return deepcopy(value)

    def download(self, artifact, token, destination, *, max_bytes):
        self.assertEqual(701, artifact['id'], 'the state or a product body must never be fetched')
        self.assertLessEqual(max_bytes, 2 * completed.LIMIT)
        self.downloads.append(artifact['id'])
        Path(destination).write_bytes(self.archive)

    def fetch(self, selector=None, **policy):
        selector = self.upload() if selector is None else selector
        self.output_index += 1
        with ExitStack() as stack:
            stack.enter_context(patch.object(reuse, 'api_request', side_effect=lambda url, token: json.dumps(self.api(url, token)).encode()))
            stack.enter_context(patch.object(products, 'download_artifact_to_file', side_effect=self.download))
            stack.enter_context(patch.object(completed, 'issue_extension', side_effect=AssertionError('custody is not native proof')))
            stack.enter_context(patch.object(products, '_capture_runtime_reference_members', side_effect=AssertionError('no state replay')))
            return completed.fetch_collector_controls(self.source, selector, self.root / str(self.output_index),
                **{'producer': self.producer, 'job_name': self.role, 'workflow_sha': self.pin, **policy}, token='synthetic')

    def test_successful_collector_in_live_run_transfers_only_whole_small_control_zip(self):
        files = self.files()
        reference = self.root / 'runtime-references.json'
        reference.write_bytes(self.reference_bytes)
        completed.stage_collector_controls(self.source, reference, self.controls, self.root / 'staged')
        self.assertEqual(files, {p.name: p.read_bytes() for p in (self.root / 'staged').iterdir()})
        before = canonical_json_bytes([self.source, self.controls, self.references])
        result = self.fetch()
        self.assertEqual(self.controls, result['controls'])
        self.assertEqual(self.references, result['references'])
        self.assertEqual(self.source, result['source'])
        self.assertEqual(700, result['stateLocator']['artifact']['id'])
        self.assertEqual([701], self.downloads)
        self.assertEqual(1, self.urls.count(
            f"https://api.github.com/repos/{self.producer['repository']}/actions/artifacts/701"))
        self.assertEqual(before, canonical_json_bytes([self.source, self.controls, self.references]))
        self.assertNotIn('extension', result)

    def test_caller_policy_cannot_be_selected_by_control_bytes(self):
        for policy in ({'producer': {**self.producer, 'runAttempt': 99}},
                       {'job_name': 'product-validation / sdk-collect-8'}, {'workflow_sha': 'd' * 40}):
            with self.subTest(policy=policy), self.assertRaisesRegex(ValueError, 'independent caller policy'):
                self.fetch(**policy)
        self.assertEqual([], self.urls)
        self.assertEqual([], self.downloads)

    def test_official_source_and_both_uploads_keep_exact_fresh_gates(self):
        cases = ('failed-job', 'running-job', 'wrong-job', 'wrong-attempt', 'wrong-tree', 'wrong-workflow',
                 'state-expired', 'state-digest', 'state-window', 'control-expired', 'control-digest',
                 'control-name', 'control-run', 'control-window', 'control-before-state', 'control-size')
        for case in cases:
            with self.subTest(case=case):
                self.setUp()
                selector = self.upload()
                if case == 'failed-job': self.job['conclusion'] = 'failure'
                elif case == 'running-job': self.job['status'] = 'in_progress'
                elif case == 'wrong-job': self.job['id'] += 1
                elif case == 'wrong-attempt': self.run['run_attempt'] += 1
                elif case == 'wrong-tree': self.commit['tree']['sha'] = 'd' * 40
                elif case == 'wrong-workflow': self.run['referenced_workflows'][0]['sha'] = 'd' * 40
                elif case.endswith('expired'): self.artifacts[700 if case.startswith('state') else 701]['expired'] = True
                elif case.endswith('digest'): self.artifacts[700 if case.startswith('state') else 701]['digest'] = sha256_bytes(b'wrong')
                elif case.endswith('window'): self.artifacts[700 if case.startswith('state') else 701]['created_at'] = '2026-10-24T11:00:00Z'
                elif case == 'control-name': self.artifacts[701]['name'] += '-sibling'
                elif case == 'control-run': self.artifacts[701]['workflow_run']['id'] += 1
                elif case == 'control-before-state': self.artifacts[701]['created_at'] = '2026-10-24T10:01:00Z'
                elif case == 'control-size': self.artifacts[701]['size_in_bytes'] = 2 * completed.LIMIT + 1
                with self.assertRaises(ValueError): self.fetch(selector)
                self.assertEqual([], self.downloads)

    def test_whole_zip_authentication_precedes_any_control_interpretation(self):
        selector = self.upload()
        raw = bytearray(self.archive)
        raw[len(raw) // 2] ^= 1
        self.archive = bytes(raw)
        with patch.object(completed, 'prepare_collector_controls', side_effect=AssertionError('unverified controls parsed')):
            with self.assertRaisesRegex(ValueError, 'bytes differ'): self.fetch(selector)

    def test_authenticated_zip_rejects_unexpected_duplicate_nonregular_and_oversized_members(self):
        for case in ('extra', 'duplicate', 'symlink', 'path', 'oversized', 'missing'):
            with self.subTest(case=case):
                files = self.files()
                entries = list(files.items())
                if case == 'extra': entries.append(('payload.zip', b'not a control'))
                elif case == 'duplicate': entries[1] = entries[0]
                elif case == 'symlink':
                    link = zipfile.ZipInfo(entries[0][0]); link.create_system = 3
                    link.external_attr = (stat.S_IFLNK | 0o777) << 16
                    entries[0] = (link, entries[0][1])
                elif case == 'path': entries[0] = ('../collector-controls.json', entries[0][1])
                elif case == 'oversized': entries[0] = (entries[0][0], b' ' * (completed.LIMIT + 1))
                elif case == 'missing': entries.pop()
                with self.assertRaises(ValueError): self.fetch(self.upload(entries=entries))

    def test_authenticated_control_cannot_replace_state_reference_receipt_or_pins(self):
        for case in ('state', 'references', 'plan', 'receipt', 'pins', 'schema'):
            with self.subTest(case=case):
                files = self.files()
                envelope = json.loads(files[completed.COLLECTOR_CONTROL_NAME])
                if case == 'state': envelope['source']['artifactId'] += 1
                elif case == 'references': files['runtime-references.json'] += b' '
                elif case == 'plan': envelope['controls'][completed.SOURCE_PLAN] += ' '
                elif case == 'receipt': envelope['controls']['runtime-state/original/csharp/phase-receipt.json']['productVersion'] = 'wrong'
                elif case == 'pins': envelope['controlPins'][0]['bytes'] += 1
                elif case == 'schema': envelope['schemaVersion'] = True
                files[completed.COLLECTOR_CONTROL_NAME] = canonical_json_bytes(envelope)
                with self.assertRaises(ValueError): self.fetch(self.upload(files))

    def test_embedded_receipt_is_bound_without_opening_its_product_object(self):
        old_path = 'runtime-state/original/csharp/phase-receipt.json'
        receipt = self.controls.pop(old_path)
        phase = next(row for row in self.controls['runtime-state/reuse-wave-request.json']['availableObjects']
                     if row['product'] == 'sdk')
        obj = 'runtime-state/original-objects/' + object_relative_path(phase['buildKey'], phase['receiptSha256'])
        self.controls[obj + '/phase-receipt.json'] = receipt
        self.references['inventory'] = sorted([row for row in self.references['inventory'] if row['relativePath'] != old_path]
            + [{'relativePath': obj, 'bytes': 1000, 'sha256': phase['objectSha256']}], key=lambda row: row['relativePath'])
        self.reference_bytes = canonical_json_bytes(self.references)
        self.source['referenceControlSha256'] = sha256_bytes(self.reference_bytes)
        result = self.fetch()
        self.assertEqual(receipt, result['controls'][obj + '/phase-receipt.json'])
        self.assertEqual([701], self.downloads)
        phase['objectSha256'] = sha256_bytes(b'wrong object')
        with self.assertRaises(ValueError): self.files()


if __name__ == '__main__':
    unittest.main()
