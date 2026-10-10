"""Real CI transport parsers, mocked HTTP and plan/Git boundary; no signing proof."""

from copy import deepcopy
import io
import json
from pathlib import Path
import unittest
import zipfile
from unittest.mock import patch

from ci import runtime_preparation_capture as capture
from ci.tests import test_runtime_aggregate_upload as fixtures
from products.inventory import (canonical_json_bytes, publish_regular_tree as actual_publish_regular_tree,
    regular_file_inventory, write_canonical_json as actual_write_canonical_json)
from products.inventory import sha256_bytes
from products.registry import NATIVE_TARGETS


class RuntimePreparationCaptureTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.RuntimeAggregateUploadTest(methodName='runTest')
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.configure('linux-x64')

    def configure(self, target, *, retained=False):
        f = self.fixture
        self.target = target
        f.jobs[0]['name'] = f'product-validation / runtime-signing-prepare-{target}'
        f.artifact['name'] = f"codex-agent-runtime-signing-preparation-{target}-{f.producer['tree']}-attempt-2"
        # Deliberately non-authoritative records: this helper verifies transport,
        # while the separate protected consumer validates their content.
        f.files = {'preparation.json': canonical_json_bytes({'synthetic': 'transport only'}),
            'selected-inputs/selection.json': b'{"synthetic":"original selection"}\n',
            'selected-state-transport/capture-transport.json': b'{"synthetic":"original state"}\n',
            'selected-inputs/empty-diagnostics.log': b''}
        if retained:
            f.files['release-handoff/original.bin'] = b'opaque retained original bytes\n'
        f.archive()

    def call(self, **changes):
        f = self.fixture
        def stream(artifact, token, destination, *, max_bytes):
            self.assertEqual(f.artifact, artifact)
            self.assertEqual('synthetic-token', token)
            self.assertEqual(capture.products._CATALOG_LIMIT, max_bytes)
            Path(destination).write_bytes(f.raw)
        with patch.object(capture.products, '_validate_plan', return_value=f.plan), \
                patch('reuse.api_request', side_effect=f.api), \
                patch.object(capture.products, 'download_artifact_to_file', side_effect=stream):
            return capture.capture_runtime_signing_preparation(f.plan_path, f.output, **{
                'target': self.target, 'artifact_id': 701, 'artifact_sha256': f.artifact['digest'],
                'trusted_workflow_sha': f.pin, 'repository_root': f.root,
                'environ': {'GITHUB_RUN_ID': '71', 'GITHUB_RUN_ATTEMPT': '2'},
                'token': 'synthetic-token', **changes})

    def test_preparation_above_inline_limit_uses_verified_streaming(self):
        f = self.fixture
        with patch.object(capture.products, '_INLINE_UPLOAD_LIMIT', len(f.raw) - 1), \
                patch.object(capture.products, 'download_artifact',
                             side_effect=AssertionError('Preparation must not download into memory')) as inline:
            self.call()
        inline.assert_not_called()
        self.assertEqual(f.raw, (f.output / 'original-upload.zip').read_bytes())

    def test_all_targets_preserve_exact_original_zip_and_empty_diagnostics(self):
        f = self.fixture
        for target, retained in [(target, False) for target in NATIVE_TARGETS] + [('aggregate', False), ('aggregate', True)]:
            with self.subTest(target=target, retained=retained):
                self.configure(target, retained=retained)
                f.output = f.work / f'capture-{target}-{retained}'
                before = f.plan_path.read_bytes()
                result = self.call()
                self.assertEqual(f.producer, result['captureProducer'])
                self.assertEqual(target, result['target'])
                self.assertEqual({'original', 'original-upload.zip', 'capture-transport.json'},
                                 {path.name for path in f.output.iterdir()})
                self.assertEqual(f.raw, (f.output / 'original-upload.zip').read_bytes())
                for name, raw in f.files.items():
                    self.assertEqual(raw, (f.output / 'original' / name).read_bytes())
                self.assertEqual(before, f.plan_path.read_bytes())
                inventory = regular_file_inventory(f.output, allow_empty=True)
                with self.assertRaisesRegex(ValueError, 'must not exist'):
                    self.call()
                self.assertEqual(inventory, regular_file_inventory(f.output, allow_empty=True))

    def test_failed_wrong_attempt_pin_job_window_or_upload_reject(self):
        f = self.fixture
        baseline = deepcopy((f.run, f.jobs, f.artifact))
        for case in ('failed', 'job', 'attempt', 'pin', 'window', 'missing-window', 'name', 'digest'):
            f.run, f.jobs, f.artifact = deepcopy(baseline)
            if case == 'failed': f.jobs[0]['conclusion'] = 'failure'
            elif case == 'job': f.jobs[0]['name'] += '-other'
            elif case == 'attempt': f.run['run_attempt'] = 1
            elif case == 'pin': f.run['referenced_workflows'][0]['sha'] = 'd' * 40
            elif case == 'window': f.artifact['created_at'] = '2026-09-11T09:15:00Z'
            elif case == 'missing-window': del f.artifact['created_at']
            elif case == 'name': f.artifact['name'] += '-other'
            else: f.artifact['digest'] = 'sha256:' + 'd' * 64
            with self.subTest(case=case), self.assertRaises(ValueError):
                self.call()
            self.assertFalse(f.output.exists())

    def test_wrong_root_layout_and_traversal_reject(self):
        f = self.fixture
        for path in ('extra.json', 'release-handoff/forbidden-native.bin', '../escape'):
            self.configure('linux-x64')
            f.files[path] = b'not allowed\n'
            f.archive()
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.call()
            self.assertFalse(f.output.exists())
        self.configure('aggregate')
        del f.files['selected-state-transport/capture-transport.json']
        f.archive()
        with self.assertRaises(ValueError):
            self.call()
        self.assertFalse(f.output.exists())

    def test_invalid_scope_authorization_and_overlap_reject_before_observation(self):
        f = self.fixture
        for changes in ({'target': 'javascript'}, {'artifact_id': True}, {'token': ''}):
            with self.subTest(changes=changes), patch.object(capture.products, '_observe_ci_producer_jobs') as observed, \
                    self.assertRaises(ValueError):
                self.call(**changes)
            observed.assert_not_called()
        for event, authorized in (('workflow_dispatch', True), ('pull_request', False)):
            f.plan.update(event=event, remoteBuildAuthorized=authorized)
            with patch.object(capture.products, '_observe_ci_producer_jobs') as observed, self.assertRaises(ValueError):
                self.call()
            observed.assert_not_called()
        f.output = f.root / 'nested-output'
        with patch.object(capture.products, '_observe_ci_producer_jobs') as observed, self.assertRaises(ValueError):
            self.call()
        observed.assert_not_called()
        self.assertFalse(f.output.exists())

    def test_original_plan_mutation_prevents_publication(self):
        f = self.fixture
        gate = capture.products._require_artifact_job_window
        def mutate(*args):
            gate(*args)
            f.plan_path.write_bytes(b'changed original plan\n')
        with patch.object(capture.products, '_require_artifact_job_window', side_effect=mutate), \
                self.assertRaisesRegex(ValueError, 'changed before publication'):
            self.call()
        self.assertFalse(f.output.exists())

    def test_pre_pin_and_late_copy_mutations_do_not_publish(self):
        f = self.fixture

        def mutate_before_pin(path, value):
            actual_write_canonical_json(path, value)
            (Path(path).parent / "original/selected-inputs/selection.json").write_bytes(b"changed before pin\n")

        with patch.object(capture, "write_canonical_json", side_effect=mutate_before_pin), \
                self.assertRaisesRegex(ValueError, "changed before publication"):
            self.call()
        self.assertFalse(f.output.exists())

        def mutate_before_copy(source, destination, **kwargs):
            (Path(source) / "original/selected-inputs/selection.json").write_bytes(b"changed after pin\n")
            actual_publish_regular_tree(source, destination, **kwargs)

        with patch.object(capture, "publish_regular_tree", side_effect=mutate_before_copy), \
                self.assertRaisesRegex(ValueError, "pinned inventory"):
            self.call()
        self.assertFalse(f.output.exists())


class RuntimeNativeReleaseCaptureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from ci.tests.test_runtime_aggregate_release import RuntimeAggregateReleaseTest
        cls.signed = RuntimeAggregateReleaseTest
        cls.signed.setUpClass()
        cls.addClassCleanup(cls.signed.doClassCleanups)

    def setUp(self):
        self.f = fixtures.RuntimeAggregateUploadTest(methodName='runTest')
        self.addCleanup(self.f.doCleanups)
        self.f.setUp()
        f = self.f
        f.root = self.signed.repository
        f.plan['validationCommit'] = self.signed.pin
        self.output = f.root / 'build' / f.work.name
        self.uploads, self.raw, self.selected = {}, {}, {}
        self.original_files = {}
        f.jobs = []
        for index, target in enumerate(NATIVE_TARGETS):
            files = {record['relativePath']: (self.signed.handoffs[target] / record['relativePath']).read_bytes()
                     for record in regular_file_inventory(self.signed.handoffs[target])}
            self.original_files[target] = files
            self.selected[target] = {phase: sha256_bytes(files[f'receipts/{phase}.json'])
                                    for phase in ('binary', 'package', 'validation', 'metadata')}
            output = io.BytesIO()
            with zipfile.ZipFile(output, 'w') as archive:
                for path, raw in files.items():
                    archive.writestr('runtime-input/' + path, raw)
                archive.writestr('external-originals/not-a-product.bin', b'not forwarded')
            artifact = deepcopy(f.artifact)
            artifact.update(id=701 + index,
                name=f"codex-agent-runtime-release-handoff-{target}-{f.producer['tree']}-attempt-2",
                archive_download_url=f"https://api.github.com/repos/{f.producer['repository']}/actions/artifacts/{701 + index}/zip")
            self.raw[701 + index] = output.getvalue()
            artifact.update(digest=sha256_bytes(output.getvalue()), size_in_bytes=len(output.getvalue()))
            self.uploads[701 + index] = artifact
            f.jobs.append({'id': 81 + index, 'name': f'product-validation / runtime-native-attestation-{target}',
                'run_id': 71, 'head_sha': 'f' * 40, 'status': 'completed', 'conclusion': 'success',
                'started_at': '2026-09-11T10:00:00Z', 'completed_at': '2026-09-11T10:30:00Z'})
        self.recovery = {'producer': f.producer, 'trustedWorkflowSha': f.pin,
            'artifacts': [{'target': target, 'artifactId': 701 + index,
                          'artifactSha256': self.uploads[701 + index]['digest']}
                         for index, target in enumerate(NATIVE_TARGETS)]}

    def call(self):
        f = self.f
        def api(url, token):
            for artifact in self.uploads.values():
                if url == artifact['archive_download_url'].removesuffix('/zip'):
                    return json.dumps(artifact).encode()
            return f.api(url, token)
        def stream(artifact, token, destination, *, max_bytes):
            self.assertEqual(capture.products._CATALOG_LIMIT, max_bytes)
            Path(destination).write_bytes(self.raw[artifact['id']])
        with patch.object(capture.products, '_validate_plan', return_value=f.plan), \
                patch('reuse.api_request', side_effect=api), \
                patch.object(capture.products, 'download_artifact_to_file', side_effect=stream):
            return capture.capture_runtime_native_release_handoffs(f.plan_path, self.output,
                recovery=self.recovery, selected_receipt_sha256s=self.selected,
                trusted_workflow_sha=self.signed.pin, repository_root=f.root,
                environ={'GITHUB_RUN_ID': '72', 'GITHUB_RUN_ATTEMPT': '1'}, token='synthetic-token')

    def test_signed_originals_survive_failed_campaign_in_current_workspace(self):
        self.f.run['conclusion'] = 'failure'
        self.assertEqual(self.output, self.call())
        self.assertEqual(46, len(regular_file_inventory(self.output)))
        for target, files in self.original_files.items():
            for path, raw in files.items():
                self.assertEqual(raw, (self.output / target / 'runtime-input' / path).read_bytes())
        transport = json.loads((self.output / 'transport.json').read_bytes())
        self.assertEqual(self.f.producer, transport['producer'])
        self.assertEqual(72, transport['captureProducer']['runId'])
        self.assertEqual(self.f.pin, transport['trustedWorkflowSha'])

    def test_missing_target_failed_job_wrong_source_or_current_receipt_reject(self):
        baseline = deepcopy((self.recovery, self.selected, self.f.jobs, self.f.run))
        for case in ('missing', 'duplicate', 'failed', 'source', 'receipt'):
            self.recovery, self.selected, self.f.jobs, self.f.run = deepcopy(baseline)
            if case == 'missing': self.recovery['artifacts'].pop()
            elif case == 'duplicate': self.recovery['artifacts'][-1] = deepcopy(self.recovery['artifacts'][0])
            elif case == 'failed': self.f.jobs[0]['conclusion'] = 'failure'
            elif case == 'source': self.recovery['trustedWorkflowSha'] = 'd' * 40
            else: self.selected[NATIVE_TARGETS[0]]['binary'] = 'sha256:' + 'd' * 64
            with self.subTest(case=case), self.assertRaises(ValueError):
                self.call()
            self.assertFalse(self.output.exists())

    def test_outer_authenticated_upload_cannot_hide_tampered_signature(self):
        record = self.recovery['artifacts'][0]
        original = self.raw[record['artifactId']]
        output = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(original)) as source, zipfile.ZipFile(output, 'w') as archive:
            for entry in source.infolist():
                raw = source.read(entry.filename)
                if entry.filename.endswith('.attestation.sig'): raw = b'invalid signature\n'
                archive.writestr(entry.filename, raw)
        self.raw[record['artifactId']] = output.getvalue()
        record['artifactSha256'] = sha256_bytes(output.getvalue())
        self.uploads[record['artifactId']].update(digest=record['artifactSha256'], size_in_bytes=len(output.getvalue()))
        with self.assertRaises(ValueError):
            self.call()
        self.assertFalse(self.output.exists())


if __name__ == '__main__':
    unittest.main()
