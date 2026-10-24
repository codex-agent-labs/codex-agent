"""Control checks only; actual Intel execution is a separate hosted requirement."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci.tests import phase9_native_validation as check


class NativeValidationTest(unittest.TestCase):
    def test_fixed_consumed_inputs_and_zero_product_ownership(self):
        from products.registry import PHASE_INSTANCE_IDS
        from products.selection import phase_inventory_paths
        spec = check.specification()
        self.assertEqual(13, len(spec['files']))
        self.assertEqual({'executor', 'package', 'receipts'},
                         {row['relativePath'].split('/')[0] for row in spec['files']})
        paths = ['ci/tests/phase9_native_validation.py', 'ci/tests/test_phase9_native_validation.py',
            'ci/tests/fixtures/phase9-native-validation-transfer.json',
            'ci/tests/fixtures/phase9-native-validation/settings.gradle',
            'ci/tests/fixtures/phase9-native-validation/codex-agent-runtime-desktop/build.gradle',
            '.github/workflows/portable-reuse-proof.yml']
        self.assertTrue(all(not phase_inventory_paths(paths, phase) for phase in PHASE_INSTANCE_IDS))
        with patch.object(check, 'TRANSFER_SHA256', 'sha256:'+'0'*64):
            with self.assertRaisesRegex(ValueError, 'reviewed original pins'):
                check.specification()

    def test_wrong_event_before_transfer_and_tamper_before_plan(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            event = root / 'event.json'
            event.write_text(json.dumps({}))
            with patch.dict(os.environ, {'GITHUB_EVENT_PATH': str(event), 'GITHUB_ACTIONS': 'false'}), \
                    patch.object(check, 'git', return_value='a'*40), patch.object(check, 'receive') as receive:
                with self.assertRaisesRegex(ValueError, 'same-repository'):
                    check.hosted(root / 'out', root)
                receive.assert_not_called()
                self.assertFalse((root / 'out').exists())
            first = root / check.specification()['files'][0]['relativePath']
            first.parent.mkdir()
            first.write_bytes(b'tampered executor')
            with patch.object(check, 'plan_phase') as plan:
                with self.assertRaisesRegex(ValueError, 'immutable original'):
                    check.prepare(root, 'a'*40)
                plan.assert_not_called()


if __name__ == '__main__':
    unittest.main()
