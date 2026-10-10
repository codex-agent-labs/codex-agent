"""Reference custody is byte reuse, never receipt or provenance admission."""
import copy
import io
import re
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from ci.tests.test_product_resume_capture import product_reuse
from ci.tests.test_product_resume_capture import archive
from ci.tests import test_runtime_resume_capture as resume_fixture
from runtime_reference_transport import (
    REFERENCE_NAME, stage_reference_handoff, resolve_reference_handoff, validate_references,
)
from products.inventory import regular_file_inventory, snapshot_regular_tree, write_canonical_json, sha256_bytes


class RangeOpener:
    def __init__(self, archives):
        self.archives = archives
        self.requests = []
        self.etag = '"immutable-fixture"'

    def open(self, request, timeout):
        identifier = int(request.full_url.split('/')[-2])
        raw = self.archives[identifier]
        start, end = map(int, re.fullmatch(r'bytes=(\d+)-(\d+)', request.get_header('Range')).groups())
        self.requests.append((identifier, start, end))
        response = io.BytesIO(raw[start:end+1])
        response.status = 206
        response.headers = {'Content-Range': f'bytes {start}-{end}/{len(raw)}', 'ETag': self.etag}
        return response


class RuntimeReferenceTransportTest(unittest.TestCase):
    def test_initial_resume_local_aliases_keep_exact_logical_inventory(self):
        from runtime_reference_transport import (ORIGINAL_REFERENCE_NAME,
            stage_original_reference_handoff, validate_original_references)
        fixture = resume_fixture.RuntimeResumeCaptureTest()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.job.update(started_at='2026-01-01T01:00:00Z', completed_at='2026-01-01T01:02:00Z')
        fixture.artifact['created_at'] = '2026-01-01T01:01:00Z'
        roots = {name: fixture.root / 'build' / name for name in
                 ('product-resume-inputs', 'product-resume-state')}
        for path, raw in fixture.contents.items():
            target = fixture.root / 'build' / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        duplicate = roots['product-resume-state'] / 'duplicate-plan.json'
        duplicate.write_bytes(fixture.plan_path.read_bytes())
        destination = fixture.root / 'build/thin-initial'
        value = stage_original_reference_handoff(roots, [], destination)
        self.assertEqual(1, len(value['references']))
        physical = {path.relative_to(destination).as_posix(): path.read_bytes()
                    for path in destination.rglob('*') if path.is_file()}
        self.assertIn(ORIGINAL_REFERENCE_NAME, physical)
        result, _, _, _ = fixture.capture_members(fixture.root / 'build/captured-thin', physical)
        self.assertEqual(fixture.producer, result['captureProducer'])
        self.assertEqual(value['inventory'], regular_file_inventory(fixture.root / 'build/captured-thin/original',
                                                                   allow_empty=True))
        # Later wave envelopes must resolve this initial format as an ancestor,
        # including aliases whose source path differs from the requested path.
        raw = archive(physical)
        artifact = {**fixture.artifact, 'digest': sha256_bytes(raw), 'size_in_bytes': len(raw)}
        base = {'artifactId': artifact['id'], 'artifactSha256': artifact['digest'], 'stateWave': 0,
                'referenceControlSha256': result['referenceControlSha256']}
        wanted = {row['relativePath']: row for row in value['inventory']}
        ranges = RangeOpener({artifact['id']: raw})
        observation = [{'run': fixture.run, 'testedCommit': fixture.commit, 'jobs': [fixture.job]}]
        resolved = fixture.root / 'build/ancestor-initial'
        with mock.patch.object(product_reuse, '_observe_ci_producer_jobs', return_value=observation), \
                mock.patch.object(product_reuse, '_contract_ci_upload_metadata', return_value=artifact), \
                mock.patch.object(product_reuse, '_reuse_contract_ci_upload',
                                  side_effect=AssertionError('unnecessary full initial archive transfer')), \
                mock.patch('runtime_reference_archive.urllib.request.build_opener', return_value=ranges):
            product_reuse._capture_runtime_reference_members({}, fixture.plan_path.read_bytes(),
                fixture.producer, base, resolved, trusted_workflow_sha=fixture.pin,
                token='not-a-real-token', wanted=wanted)
        self.assertEqual(value['inventory'], regular_file_inventory(resolved, allow_empty=True))
        changed = copy.deepcopy(value)
        changed['references'][0]['sourcePath'] = changed['references'][0]['relativePath']
        with self.assertRaisesRegex(ValueError, 'cyclic'):
            validate_original_references(changed)

    def test_initial_original_members_require_fresh_authentication_and_exact_hashes(self):
        from ci.tests.test_runtime_original_ci import RuntimeOriginalCiTest, adapter, TARGET
        from runtime_reference_transport import (stage_original_reference_handoff,
            resolve_original_reference_handoff, validate_original_references)
        from products.inventory import load_canonical_json_bytes
        fixture = RuntimeOriginalCiTest()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        phase = 'binary'
        receipt = load_canonical_json_bytes(fixture.receipts[phase].read_bytes())
        prefix = f'product-resume-state/prior-failed-runtime/{TARGET}/{phase}/{TARGET}/phases/{phase}/original'
        artifact = fixture.artifacts[phase]
        source = {'relativePath': prefix, 'kind': 'phase', 'receipt': receipt,
                  'artifactId': artifact['id'], 'artifactSha256': artifact['digest']}
        roots = {name: fixture.root / 'thin-inputs' / name for name in
                 ('product-resume-inputs', 'product-resume-state')}
        roots['product-resume-inputs'].mkdir(parents=True)
        (roots['product-resume-inputs'] / 'control.json').write_bytes(b'current qualified control\n')
        snapshot_regular_tree(fixture.receipts[phase].parent.parent,
                              fixture.root / 'thin-inputs' / prefix, allow_empty=True)
        # The same immutable object may also appear inside a legacy discovery
        # carrier. Keep its logical path while referring to the same original.
        (roots['product-resume-inputs'] / 'duplicate-receipt.json').write_bytes(fixture.receipts[phase].read_bytes())
        thin = fixture.root / 'thin-upload'
        value = stage_original_reference_handoff(roots, [source], thin)
        self.assertFalse(any(row['relativePath'].startswith(prefix + '/')
                             for row in regular_file_inventory(thin)))
        self.assertFalse((thin / 'product-resume-inputs/duplicate-receipt.json').exists())
        consumer = {**fixture.producer, 'runId': fixture.producer['runId'] + 1}
        plan = {'repository': fixture.producer['repository'], 'event': 'pull_request'}
        for bad in ('none', 'digest', 'job', 'window'):
            target = fixture.root / ('resolved-' + bad)
            snapshot_regular_tree(thin, target, allow_empty=True)
            changed = copy.deepcopy(value)
            if bad == 'digest':
                member = changed['references'][0]['sourcePath']
                for row in changed['references']:
                    if row['sourcePath'] == member:
                        row['sha256'] = 'sha256:' + 'f' * 64
                        next(item for item in changed['inventory'] if item['relativePath'] == row['relativePath'])['sha256'] = row['sha256']
            jobs = copy.deepcopy(fixture.jobs)
            artifacts = copy.deepcopy(fixture.artifacts)
            if bad == 'job':
                jobs[0]['conclusion'] = 'failure'
            if bad == 'window':
                artifacts[phase]['created_at'] = '2026-09-06T09:00:00Z'
            ranges = RangeOpener({artifact['id']: fixture.archives[phase]})
            def capture_source(locator, records, root):
                return adapter._capture_runtime_original_reference_members(plan, consumer, locator,
                    records, root, trusted_workflow_sha=fixture.pin, token='not-a-real-token')
            with mock.patch('reuse.api_request', side_effect=fixture.api(jobs=jobs, artifacts=artifacts, details=artifacts)), \
                    mock.patch('runtime_reference_archive.urllib.request.build_opener', return_value=ranges):
                if bad == 'none':
                    resolve_original_reference_handoff(target, changed, capture_source)
                    self.assertEqual(value['inventory'], regular_file_inventory(target, allow_empty=True))
                else:
                    with self.assertRaises(ValueError):
                        resolve_original_reference_handoff(target, changed, capture_source)
        changed = copy.deepcopy(value)
        changed['sources'][0]['relativePath'] += '-other'
        with self.assertRaisesRegex(ValueError, 'registered destination'):
            validate_original_references(changed)

    def test_nested_reference_controls_are_digest_qualified_before_following(self):
        fixture = resume_fixture.RuntimeResumeCaptureTest()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        from products.inventory import canonical_json_bytes
        plan_path = 'product-resume-inputs/plan/impact-plan.json'
        plan_bytes = fixture.contents[plan_path]
        record = {'relativePath': plan_path, 'bytes': len(plan_bytes), 'sha256': sha256_bytes(plan_bytes)}
        base_raw = archive(fixture.contents)
        controls = {'schemaVersion': 1, 'base': {'artifactId': 101, 'artifactSha256': sha256_bytes(base_raw),
                    'stateWave': 0}, 'inventory': [record],
                    'references': [{**record, 'sourcePath': plan_path}]}
        raw_control = canonical_json_bytes(controls)
        nested_raw = archive({REFERENCE_NAME: raw_control})
        altered = copy.deepcopy(controls)
        altered['references'][0]['sourcePath'] = plan_path.replace('impact-plan', 'impact-blan')
        changed_raw = archive({REFERENCE_NAME: canonical_json_bytes(altered)})
        self.assertEqual(len(nested_raw), len(changed_raw))
        artifacts = {101: {**fixture.artifact, 'digest': sha256_bytes(base_raw),
                         'size_in_bytes': len(base_raw), 'created_at': '2026-01-01T01:01:00Z'},
                     102: {**fixture.artifact, 'id': 102, 'digest': sha256_bytes(nested_raw),
                         'size_in_bytes': len(nested_raw), 'created_at': '2026-01-01T01:01:00Z',
                         'archive_download_url': fixture.artifact['archive_download_url'].replace('/101/', '/102/')}}
        jobs = [{**fixture.job, 'name': name, 'started_at': '2026-01-01T01:00:00Z',
                 'completed_at': '2026-01-01T01:02:00Z'} for name in
                ('product-validation / runtime-collect-1', 'product-validation / product-resume')]
        observed = [{'run': fixture.run, 'testedCommit': fixture.commit, 'jobs': jobs}]
        base = {'artifactId': 102, 'artifactSha256': sha256_bytes(nested_raw), 'stateWave': 1,
                'referenceControlSha256': sha256_bytes(raw_control)}
        for changed in (False, True):
            ranges = RangeOpener({101: base_raw, 102: changed_raw if changed else nested_raw})
            with mock.patch.object(product_reuse, '_observe_ci_producer_jobs', return_value=observed), \
                    mock.patch.object(product_reuse, '_contract_ci_upload_metadata',
                                      side_effect=lambda identifier, *args: artifacts[identifier]), \
                    mock.patch.object(product_reuse, '_reuse_contract_ci_upload',
                                      side_effect=AssertionError('unnecessary full ancestor transfer')), \
                    mock.patch('runtime_reference_archive.urllib.request.build_opener', return_value=ranges):
                destination = fixture.root / f'nested-{changed}'
                arguments = ({}, plan_bytes, fixture.producer, base, destination)
                options = {'trusted_workflow_sha': fixture.pin, 'token': 'synthetic-token', 'wanted': {plan_path: record}}
                if changed:
                    with self.assertRaisesRegex(ValueError, 'authenticated digest'):
                        product_reuse._capture_runtime_reference_members(*arguments, **options)
                    self.assertFalse(any(identifier == 101 for identifier, *_ in ranges.requests))
                else:
                    product_reuse._capture_runtime_reference_members(*arguments, **options)
                    self.assertEqual(plan_bytes, (destination / plan_path).read_bytes())

    def test_range_reads_reject_changed_etags_and_unbounded_bodies(self):
        from runtime_reference_archive import _Archive
        raw = b'qualified bytes'
        opener = RangeOpener({101: raw})
        artifact = {'id': 101, 'digest': sha256_bytes(raw), 'size_in_bytes': len(raw),
                    'archive_download_url': 'https://api.github.com/repos/codex-agent-labs/codex-agent/actions/artifacts/101/zip'}
        with mock.patch('runtime_reference_archive.urllib.request.build_opener', return_value=opener):
            stream = _Archive(artifact, 'synthetic-token')
            self.assertEqual(raw[:2], stream.read(2))
            opener.etag = '"different-body"'
            with self.assertRaisesRegex(ValueError, 'range identity'):
                stream.read(2)
            opener.etag = '"immutable-fixture"'
            stream.seek(len(raw) - 2)
            self.assertEqual(raw[-2:], stream.read())
            with self.assertRaisesRegex(ValueError, 'bounded request'):
                stream.read(33 * 1024**2)

    def test_private_upload_byte_reuse_keeps_fresh_authentication_and_provenance_binding(self):
        fixture = resume_fixture.RuntimeResumeCaptureTest()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        from products.restore import verification_session
        with verification_session(), mock.patch.object(product_reuse, 'api_json', return_value=fixture.artifact) as observe, \
                mock.patch.object(product_reuse, 'download_artifact', return_value=fixture.raw) as download:
            arguments = (101, fixture.artifact['digest'], fixture.artifact['name'],
                         fixture.producer, fixture.run, 'synthetic-token')
            first = product_reuse._download_contract_ci_upload(*arguments)
            self.assertEqual(first, product_reuse._download_contract_ci_upload(*arguments))
            self.assertEqual(2, observe.call_count)
            self.assertEqual(1, download.call_count)
            changed = {**fixture.run, 'referenced_workflows': [{'sha': 'f'*40}]}
            product_reuse._download_contract_ci_upload(*arguments[:4], changed, arguments[-1])
            self.assertEqual(2, download.call_count)
            observe.return_value = {**fixture.artifact, 'expired': True}
            with self.assertRaisesRegex(ValueError, 'transport identity'):
                product_reuse._download_contract_ci_upload(*arguments)

    def test_capture_authenticates_both_original_uploads_before_resolving(self):
        fixture = resume_fixture.RuntimeResumeCaptureTest()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        root = fixture.root
        base, handoff = root / 'reference-base', root / 'reference-full'
        for directory in (base, handoff):
            for name, raw in fixture.contents.items():
                target = directory / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw)
        (handoff / 'runtime-state').mkdir()
        (handoff / 'runtime-state/reuse-wave-result.json').write_bytes(b'untrusted phase state')
        capture = root / 'base-transport.json'
        # A genuine source upload may contain a large unrelated body. Its source
        # metadata/job must be authenticated, but that body must never transfer.
        base_raw = archive({**fixture.contents,
            'product-resume-state/unreferenced.bin': b'x' * (4 * 1024 * 1024)})
        base_artifact = {**fixture.artifact, 'created_at': '2026-01-01T01:01:00Z',
            'digest': sha256_bytes(base_raw), 'size_in_bytes': len(base_raw)}
        write_canonical_json(capture, {'artifact': base_artifact})
        delta = root / 'reference-delta'
        stage_reference_handoff(handoff, base, capture, delta, state_wave=1)
        raw = archive({path.relative_to(delta).as_posix(): path.read_bytes()
                       for path in delta.rglob('*') if path.is_file()})
        artifact = {**base_artifact, 'id': 102, 'digest': sha256_bytes(raw),
                    'size_in_bytes': len(raw),
                    'name': f"codex-agent-runtime-wave-1-state-{fixture.producer['tree']}-attempt-3",
                    'archive_download_url': base_artifact['archive_download_url'].replace('/101/', '/102/')}
        jobs = [{**fixture.job, 'name': name, 'started_at': '2026-01-01T01:00:00Z',
                 'completed_at': '2026-01-01T01:02:00Z'} for name in
                ('product-validation / runtime-collect-1', 'product-validation / product-resume')]

        def run_capture(destination, original=base_artifact):
            ranges = RangeOpener({101: base_raw})
            with mock.patch.object(product_reuse, 'api_json', side_effect=[
                    fixture.run, fixture.commit, artifact, fixture.run, fixture.commit, original]), \
                    mock.patch.object(product_reuse, 'paginated_items', side_effect=[[jobs[0]], [jobs[1]]]), \
                    mock.patch.object(product_reuse, 'download_artifact_to_file',
                        side_effect=lambda item, token, path, **kwargs:
                        path.write_bytes(raw if item['id'] == 102 else base_raw)) as downloads, \
                    mock.patch('runtime_reference_archive.urllib.request.build_opener', return_value=ranges):
                result = product_reuse.capture_runtime_resume_upload(
                    fixture.plan_path, destination, artifact_id=102, artifact_sha256=artifact['digest'],
                    trusted_workflow_sha=fixture.pin, state_wave=1, repository_root=root,
                    environ=fixture.environment, token='synthetic-token')
                return result, downloads.call_count, ranges
        destination = root / 'build/reference-capture'
        result, downloads, ranges = run_capture(destination)
        self.assertEqual(1, downloads)  # Only the current delta; no ancestor ZIP.
        self.assertLess(sum(end-start+1 for _, start, end in ranges.requests), len(base_raw) // 2)
        self.assertEqual('qualified-reference-members', result['referenceBase']['verification'])
        self.assertEqual(base_artifact, result['referenceBase']['artifact'])
        self.assertEqual(regular_file_inventory(handoff, allow_empty=True),
                         regular_file_inventory(destination / 'original', allow_empty=True))
        rejected = root / 'build/rejected-reference'
        with self.assertRaisesRegex(ValueError, 'transport identity'):
            run_capture(rejected, {**base_artifact, 'digest': 'sha256:' + 'f'*64})
        self.assertFalse(rejected.exists())

    def test_exact_references_keep_all_original_bytes_and_reject_mutation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            base = root / 'base'
            handoff = root / 'handoff'
            for directory in (base, handoff):
                (directory / 'product-resume-state/v1/objects').mkdir(parents=True)
                (directory / 'product-resume-state/v1/objects/original.zip').write_bytes(b'exact original object')
                (directory / 'product-resume-state/receipt.json').write_bytes(b'original producer receipt')
                (directory / 'product-resume-state/empty.log').write_bytes(b'')
            (handoff / 'runtime-state').mkdir()
            (handoff / 'runtime-state/new-receipt.json').write_bytes(b'new control only')
            capture = root / 'capture.json'
            write_canonical_json(capture, {'artifact': {'id': 101, 'digest': 'sha256:' + 'a'*64}, 'stateWave': 1})
            before = regular_file_inventory(handoff, allow_empty=True)
            delta = root / 'delta'
            value = stage_reference_handoff(handoff, base, capture, delta, state_wave=2)
            self.assertEqual(3, len(value['references']))
            self.assertEqual(before, regular_file_inventory(handoff, allow_empty=True))
            self.assertFalse((delta / 'product-resume-state/v1/objects/original.zip').exists())
            resolved = root / 'resolved'
            snapshot_regular_tree(delta, resolved, allow_empty=True)
            self.assertEqual(before, resolve_reference_handoff(resolved, base, value, state_wave=2))
            self.assertEqual(before, regular_file_inventory(resolved, allow_empty=True))
            self.assertFalse((resolved / REFERENCE_NAME).exists())
            for invalid in ('../escape', '/absolute', 'unexpected/file'):
                altered = copy.deepcopy(value)
                altered['references'][0]['sourcePath'] = invalid
                with self.assertRaises(ValueError):
                    validate_references(altered, 2)
            for wave in (0, 1, 6, True):
                with self.assertRaises(ValueError):
                    validate_references(value, wave)
            duplicate = copy.deepcopy(value)
            duplicate['references'].append(duplicate['references'][0])
            with self.assertRaises(ValueError):
                validate_references(duplicate, 2)
            amplification = copy.deepcopy(value)
            amplification['inventory'][0]['bytes'] = 17 * 1024 * 1024 * 1024
            with self.assertRaisesRegex(ValueError, 'byte bounds'):
                validate_references(amplification, 2)
            (base / 'product-resume-state/receipt.json').write_bytes(b'changed original receipt')
            mutated = root / 'mutated'
            snapshot_regular_tree(delta, mutated, allow_empty=True)
            with self.assertRaisesRegex(ValueError, 'immutable identity'):
                resolve_reference_handoff(mutated, base, value, state_wave=2)
            overlap = root / 'overlap'
            snapshot_regular_tree(delta, overlap, allow_empty=True)
            (overlap / 'product-resume-state').mkdir()
            (overlap / 'product-resume-state/receipt.json').write_bytes(b'original producer receipt')
            with self.assertRaisesRegex(ValueError, 'overlapping'):
                resolve_reference_handoff(overlap, base, value, state_wave=2)


if __name__ == '__main__':
    unittest.main()
