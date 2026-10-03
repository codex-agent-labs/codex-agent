"""Reference custody is byte reuse, never receipt or provenance admission."""
import copy
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


class RuntimeReferenceTransportTest(unittest.TestCase):
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
        base_artifact = {**fixture.artifact, 'created_at': '2026-01-01T01:01:00Z'}
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
            with mock.patch.object(product_reuse, 'api_json', side_effect=[
                    fixture.run, fixture.commit, artifact, fixture.run, fixture.commit, original]), \
                    mock.patch.object(product_reuse, 'paginated_items', side_effect=[[jobs[0]], [jobs[1]]]), \
                    mock.patch.object(product_reuse, 'download_artifact_to_file',
                        side_effect=lambda item, token, path, **kwargs:
                        path.write_bytes(raw if item['id'] == 102 else fixture.raw)) as downloads:
                result = product_reuse.capture_runtime_resume_upload(
                    fixture.plan_path, destination, artifact_id=102, artifact_sha256=artifact['digest'],
                    trusted_workflow_sha=fixture.pin, state_wave=1, repository_root=root,
                    environ=fixture.environment, token='synthetic-token')
                return result, downloads.call_count
        destination = root / 'build/reference-capture'
        result, downloads = run_capture(destination)
        self.assertEqual(2, downloads)
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
