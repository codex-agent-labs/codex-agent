"""Transport controls only; these tests do not stand in for hosted mutation proof."""
import os
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci.tests import phase9_ios_mutation as fixture


class MutationIntakeTest(unittest.TestCase):
    def test_native_original_expectations_and_invalid_selection_fail_before_capture(self):
        from receipt import parse_mapping
        for lane in fixture.NATIVE_PINS:
            expected = fixture.native_expectations(lane)
            self.assertEqual({'os', 'arch', 'image', 'imageVersion'}, set(parse_mapping(expected['runner'])))
            self.assertEqual(fixture.NATIVE_TOOLCHAIN, parse_mapping(expected['toolchain']))
            self.assertNotIn('validationActions', parse_mapping(expected['toolchain']))
        with tempfile.TemporaryDirectory() as temporary, patch.object(fixture, 'qualification_module') as loader:
            path = Path(temporary).resolve() / 'not-created'
            for lanes in ((), ('unknown',), ('ios-native-tests', 'ios-native-tests')):
                with self.assertRaisesRegex(ValueError, 'selection'):
                    fixture.native_inputs(path, token='not-a-real-token', lanes=lanes)
            self.assertFalse(path.exists())
            loader.assert_not_called()

    def test_wrong_hosted_event_never_prepares_or_builds(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            event = root / 'event.json'
            event.write_text(json.dumps({}))
            with patch.dict(os.environ, {'GITHUB_EVENT_PATH': str(event), 'GITHUB_ACTIONS': 'false'}), \
                    patch.object(fixture, 'git', return_value='a'*40), patch.object(fixture, 'prepare') as prepare:
                with self.assertRaisesRegex(ValueError, 'same-repository'):
                    fixture.hosted(root / 'output', root / 'cache')
                prepare.assert_not_called()

    def test_approved_scope_and_zero_product_ownership(self):
        from products.registry import PHASE_INSTANCE_IDS
        from products.selection import phase_inventory_paths
        manifest = fixture.manifest()
        self.assertEqual('development', manifest['trustDomain'])
        self.assertEqual('local', manifest['originalContractProducer']['event'])
        self.assertEqual(12, len(manifest['files']))
        self.assertEqual(11, len({row['sha256'] for row in manifest['files']}))
        paths = ['ci/tests/phase9_ios_mutation.py', 'ci/tests/test_phase9_ios_mutation.py',
            'ci/tests/fixtures/phase9-ios-mutation-transfer.json', '.github/workflows/portable-reuse-proof.yml']
        self.assertTrue(all(not phase_inventory_paths(paths, phase) for phase in PHASE_INSTANCE_IDS))

    def test_exact_cached_or_fetched_object_and_fail_closed_corruption(self):
        raw = b'input bytes\n'
        record = dict(relativePath='contract/input', bytes=len(raw), sha256=fixture.sha256_bytes(raw))
        oid = record['sha256'][7:]
        with tempfile.TemporaryDirectory() as temporary:
            storage = Path(temporary).resolve()
            output = storage / 'objects' / oid[:2] / oid[2:4] / oid
            def fetch(command, **kwargs):
                self.assertEqual(['git', 'lfs', 'smudge', 'contract/input'], command)
                self.assertIn(('oid sha256:' + oid).encode(), kwargs['input'])
                self.assertTrue(kwargs['check'])
                output.parent.mkdir(parents=True)
                output.write_bytes(raw)
            with patch.object(fixture.subprocess, 'run', side_effect=fetch) as downloader:
                self.assertEqual((output, len(raw)), fixture.lfs_object(record, storage, {}, ('git', 'lfs')))
                self.assertEqual((output, 0), fixture.lfs_object(record, storage, {}, ('git', 'lfs')))
                self.assertEqual(1, downloader.call_count)
                output.write_bytes(b'wrong bytes\n')
                with self.assertRaisesRegex(ValueError, 'pinned'):
                    fixture.lfs_object(record, storage, {}, ('git', 'lfs'))
                output.unlink()
                alternate = storage / 'alternate'
                alternate.write_bytes(raw)
                os.symlink(alternate, output)
                with self.assertRaisesRegex(ValueError, 'pinned'):
                    fixture.lfs_object(record, storage, {}, ('git', 'lfs'))
                self.assertEqual(1, downloader.call_count)


if __name__ == '__main__':
    unittest.main()
