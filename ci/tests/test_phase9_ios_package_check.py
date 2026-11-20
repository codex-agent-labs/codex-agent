"""Control/custody checks, not genuine hosted or product acceptance."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci.tests import phase9_ios_package_check as check


class PackageCheckTest(unittest.TestCase):
    def test_pinned_originals_and_zero_product_ownership(self):
        from products.registry import PHASE_INSTANCE_IDS
        from products.selection import phase_inventory_paths
        value = check.specification()
        self.assertEqual(303, len(value['files']))
        self.assertEqual(187, len({row['sha256'] for row in value['files']}))
        self.assertEqual('sha256:8d0b18df5a6b074b3e53e67c1dc5f4555fec542ac9f877a4aff134445bdc867e',
                         value['packageReceiptSha256'])
        paths = ['ci/tests/phase9_ios_package_check.py', 'ci/tests/test_phase9_ios_package_check.py',
            'ci/tests/fixtures/phase9-ios-package-transfer.json', '.github/workflows/portable-reuse-proof.yml']
        self.assertTrue(all(not phase_inventory_paths(paths, phase) for phase in PHASE_INSTANCE_IDS))
        with patch.object(check, 'TRANSFER_SHA256', 'sha256:'+'0'*64):
            with self.assertRaisesRegex(ValueError, 'reviewed original pins'):
                check.specification()

    def test_wrong_event_rejected_before_transfer(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            event = root / 'event.json'
            event.write_text(json.dumps({}))
            with patch.dict(os.environ, {'GITHUB_EVENT_PATH': str(event), 'GITHUB_ACTIONS': 'false'}), \
                    patch.object(check.mutation, 'git', return_value='a'*40), \
                    patch.object(check, 'receive') as receive:
                with self.assertRaisesRegex(ValueError, 'same-repository'):
                    check.hosted(root / 'out', root, root / 'java')
                receive.assert_not_called()
                self.assertFalse((root / 'out').exists())

    def test_unique_acquisition_and_independent_custody(self):
        raw = b'one exact original\n'
        digest = check.sha256_bytes(raw)
        rows = [dict(relativePath=name, bytes=len(raw), sha256=digest)
                for name in ('binary/file', 'package/file')]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            cache = root / 'cache'
            cache.mkdir()
            original = cache / 'original'
            original.write_bytes(raw)
            with patch.object(check.mutation, 'lfs_object', return_value=(original, 0)) as acquire:
                result = check.receive(rows, root / 'inputs', cache)
            self.assertEqual(1, acquire.call_count)
            self.assertEqual(0, result['downloadedBytes'])
            original.write_bytes(b'changed cache')
            self.assertEqual(raw, (root / 'inputs/binary/file').read_bytes())
            (root / 'inputs/binary/file').write_bytes(b'changed sibling')
            self.assertEqual(raw, (root / 'inputs/package/file').read_bytes())
            self.assertEqual(1, (root / 'inputs/package/file').stat().st_nlink)
            with self.assertRaises(FileExistsError):
                check.receive(rows, root / 'inputs', cache)


if __name__ == '__main__':
    unittest.main()
