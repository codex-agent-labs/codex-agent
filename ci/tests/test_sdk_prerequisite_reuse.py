"""Synthetic archive/API composition checks, not SDK execution evidence."""
from argparse import Namespace
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest
from unittest import mock
import zipfile

from ci.tests import test_ci as receipt_fixture

PATH = Path(__file__).resolve().parents[2] / '.github/actions/run-ci-lane/sdk_prerequisite_reuse.py'
SPEC = importlib.util.spec_from_file_location('sdk_prerequisite_reuse_test', PATH)
helper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(helper)


class SdkPrerequisiteReuseTest(unittest.TestCase):
    def test_combined_lookup_is_only_enabled_for_sdk_apple_prerequisites(self):
        root = PATH.parents[3]
        action = (PATH.parent / 'action.yml').read_text()
        workflow = (root / '.github/workflows/apple-runtime-evidence.yml').read_text()
        self.assertEqual(3, workflow.count('sdk-prerequisite-reuse: ${{ inputs.sdkBinaryOnly }}'))
        self.assertIn('default: "false"', action.split('  sdk-prerequisite-reuse:', 1)[1].split('  producer-identities:', 1)[0])
        self.assertIn('--production-destination build/ci/reuse/production', action)
        self.assertIn('COMBINED_COMPLETE: ${{ steps.reuse.outputs.production_discovery_complete }}', action)
        self.assertIn('if [ "$COMBINED_COMPLETE" = true ]; then', action)

    def setUp(self):
        self.fixture = receipt_fixture.ReceiptTest(methodName='runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.addCleanup(self.fixture.tearDown)
        f = self.fixture
        archive = f.root / 'lane.zip'
        with zipfile.ZipFile(archive, 'w') as output:
            for file in f.receipt_root.iterdir():
                output.write(file, file.name)
        self.raw = archive.read_bytes()
        self.toolchain = ['java=25', 'gradle=9.4.1']
        self.artifact = {'id': 77, 'name': f'codex-agent-ci-android-{f.first_tree}',
                         'archive_download_url': 'https://example.invalid/lane.zip',
                         'digest': 'sha256:' + hashlib.sha256(self.raw).hexdigest(),
                         'workflow_run': {'id': 101}}

    def run_lookup(self, plan, *, mutate=None):
        f = self.fixture
        arguments = Namespace(plan=plan, lane='android', destination=f.root / 'full',
            production_destination=f.root / 'production', mode='full', workflow='ci.yml',
            runner=['os=Linux', 'arch=X64'], toolchain=self.toolchain,
            token='token', api_url='https://api.github.invalid')
        legacy = helper._legacy_module()
        with mock.patch.object(helper, '_legacy_module', return_value=legacy), \
                mock.patch.object(legacy, 'candidate_artifacts', return_value=[self.artifact]), \
                mock.patch.object(legacy, 'promoted_artifacts', return_value=[]), \
                mock.patch.object(legacy, 'api_request', return_value=self.raw) as downloaded:
            if mutate is not None:
                original = legacy.restore
                def restore(args):
                    value = original(args)
                    mutate(args)
                    return value
                legacy.restore = restore
            result = helper.restore_both(arguments)
            return result, downloaded.call_count

    def test_authenticate_incompatible_body_once_for_both_categories(self):
        f = self.fixture
        self.toolchain = ['java=17', 'gradle=9.4.1']
        (full, production, witnesses), downloads = self.run_lookup(f.plan_path)
        self.assertFalse(full['reused'])
        self.assertFalse(production['reused'])
        self.assertEqual(1, downloads)
        self.assertEqual(self.artifact['digest'], witnesses[0]['archiveSha256'])
        self.assertEqual('sha256:' + hashlib.sha256((f.receipt_root / 'lane-receipt.json').read_bytes()).hexdigest(),
                         witnesses[0]['receiptSha256'])
        self.assertEqual(101, witnesses[0]['producer']['runId'])

    def test_production_positive_keeps_original_download_and_receipt_gates(self):
        f = self.fixture
        _, plan, _ = f.make_plan('codex-agent-runtime-android/src/test/kotlin/Test.kt',
                               'later test\n', base=f.first_target)
        (full, production, witnesses), downloads = self.run_lookup(plan)
        self.assertFalse(full['reused'])
        self.assertTrue(production['reused'])
        self.assertEqual([], witnesses)
        self.assertEqual(2, downloads)
        self.assertEqual((f.receipt_root / 'lane-receipt.json').read_bytes(),
                         (f.root / 'production/lane-receipt.json').read_bytes())

    def test_full_reuse_still_wins_without_production_lookup(self):
        (full, production, witnesses), downloads = self.run_lookup(self.fixture.plan_path)
        self.assertTrue(full['reused'])
        self.assertFalse(production['reused'])
        self.assertEqual([], witnesses)
        self.assertEqual(1, downloads)

    def test_mismatched_upload_provenance_is_not_cached(self):
        f = self.fixture
        self.toolchain = ['java=17', 'gradle=9.4.1']
        self.artifact['workflow_run']['id'] = 999
        (_, production, witnesses), downloads = self.run_lookup(f.plan_path)
        self.assertFalse(production['reused'])
        self.assertEqual([], witnesses)
        self.assertEqual(2, downloads)

    def test_same_identity_with_corrupt_body_never_reuses(self):
        self.raw += b'changed output'
        (full, production, witnesses), downloads = self.run_lookup(self.fixture.plan_path)
        self.assertFalse(full['reused'])
        self.assertFalse(production['reused'])
        self.assertEqual([], witnesses)
        self.assertEqual(2, downloads)

    def test_plan_mutation_between_modes_aborts(self):
        def mutate(args):
            args.plan.write_bytes(args.plan.read_bytes() + b'\n')
        with self.assertRaisesRegex(ValueError, 'changed during lookup'):
            self.run_lookup(self.fixture.plan_path, mutate=mutate)

    def test_requested_toolchain_mutation_between_modes_aborts(self):
        def mutate(args):
            args.toolchain.append('java=17')
        with self.assertRaisesRegex(ValueError, 'changed during lookup'):
            self.run_lookup(self.fixture.plan_path, mutate=mutate)


if __name__ == '__main__':
    unittest.main()
