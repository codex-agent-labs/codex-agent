"""Retain existing carrier receipts without another product-object read."""
from copy import deepcopy
from pathlib import Path
import json
import os
import sys
import unittest
from unittest.mock import patch

import completed_sdk_reuse as completed
from products.inventory import canonical_json_bytes, regular_file_inventory, sha256_bytes
from ci.tests.test_collector_controls import CollectorControlsTest


class CollectorReceiptPublicationTest(unittest.TestCase):
    def setUp(self):
        self.fixture = CollectorControlsTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.result = self.fixture.controls['runtime-state/reuse-wave-result.json']
        self.receipt = self.fixture.controls['runtime-state/original/csharp/phase-receipt.json']
        self.phase = next(row for row in self.result['phases'] if row['product'] == 'sdk')
        self.carrier = {'objects': [{**self.phase, 'receipt': self.receipt,
                                    'receiptBytes': canonical_json_bytes(self.receipt)}]}

    def write(self, destination):
        import products.restore as restore
        with patch.object(restore, 'verify_object', side_effect=AssertionError('no new body verification')), \
                patch.object(restore, 'restore_object', side_effect=AssertionError('no product restoration')):
            completed.write_collector_receipts(self.carrier, self.result, destination)

    def test_verified_receipts_feed_existing_control_export_without_product_objects(self):
        handoff = self.root / 'handoff'
        before = canonical_json_bytes(self.result)
        self.write(handoff / 'runtime-state' / completed.COLLECTOR_RECEIPTS)
        for path, value in self.fixture.controls.items():
            if path.endswith('phase-receipt.json'): continue
            target = handoff / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(value.encode() if path == completed.SOURCE_PLAN else canonical_json_bytes(value))
        refs = deepcopy(self.fixture.references)
        refs['inventory'] = regular_file_inventory(handoff)
        refs['references'] = [{**refs['inventory'][0], 'sourcePath': refs['inventory'][0]['relativePath']}]
        raw = canonical_json_bytes(refs)
        source = {**self.fixture.source, 'referenceControlSha256': sha256_bytes(raw)}
        controls = completed.collected_control_inputs(handoff, refs)
        files = completed.prepare_collector_controls(source, raw, controls)
        self.assertEqual({'collector-controls.json', 'runtime-references.json'}, files.keys())
        self.assertEqual(5, len(controls))
        name = 'runtime-state/' + completed.COLLECTOR_RECEIPTS + '/' + self.phase['receiptSha256'][7:] + '.json'
        self.assertEqual(canonical_json_bytes(self.receipt), (handoff / name).read_bytes())
        self.assertEqual(self.receipt, controls[name])
        self.assertEqual(before, canonical_json_bytes(self.result))
        self.assertFalse(list(handoff.rglob('*.zip')))

    def test_receipt_substitution_duplicate_or_missing_scope_never_publishes(self):
        for case in ('missing', 'duplicate', 'receipt', 'raw', 'object', 'extra'):
            with self.subTest(case=case):
                old = self.carrier
                self.carrier = deepcopy(old)
                if case == 'missing': self.carrier['objects'].clear()
                elif case == 'duplicate': self.carrier['objects'] *= 2
                elif case == 'receipt': self.carrier['objects'][0]['receipt']['productVersion'] = '0.0.1'
                elif case == 'raw': self.carrier['objects'][0]['receiptBytes'] += b' '
                elif case == 'object': self.carrier['objects'][0]['objectSha256'] = sha256_bytes(b'changed')
                elif case == 'extra': self.carrier['objects'][0]['component'] = 'python'
                destination = self.root / case
                with self.assertRaises(ValueError): self.write(destination)
                self.assertFalse(destination.exists())
                self.carrier = old

    def test_reference_inventory_and_exact_receipt_scope_are_checked_before_export(self):
        handoff = self.root / 'handoff'
        self.write(handoff / 'runtime-state' / completed.COLLECTOR_RECEIPTS)
        for path, value in self.fixture.controls.items():
            if path.endswith('phase-receipt.json'): continue
            target = handoff / path; target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(value.encode() if path == completed.SOURCE_PLAN else canonical_json_bytes(value))
        refs = {'inventory': regular_file_inventory(handoff)}
        for case in ('missing', 'changed', 'symlink'):
            with self.subTest(case=case):
                local = deepcopy(refs)
                receipt = next(row for row in local['inventory'] if '/collector-receipts/' in row['relativePath'])
                target = handoff / receipt['relativePath']
                original = target.read_bytes()
                if case == 'missing': local['inventory'].remove(receipt)
                elif case == 'changed': target.write_bytes(original + b' ')
                else:
                    target.unlink(); target.symlink_to(self.root / 'unavailable-product-object')
                with self.assertRaises(ValueError): completed.collected_control_inputs(handoff, local)
                if case == 'symlink': target.unlink()
                target.write_bytes(original)

    def test_post_upload_cli_publishes_only_small_controls_and_explicit_name(self):
        import reuse
        handoff = self.root / 'handoff'
        self.write(handoff / 'runtime-state' / completed.COLLECTOR_RECEIPTS)
        for path, value in self.fixture.controls.items():
            if path.endswith('phase-receipt.json'): continue
            target = handoff / path; target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(value.encode() if path == completed.SOURCE_PLAN else canonical_json_bytes(value))
        refs = deepcopy(self.fixture.references)
        refs['inventory'] = regular_file_inventory(handoff)
        refs['references'] = [{**refs['inventory'][0], 'sourcePath': refs['inventory'][0]['relativePath']}]
        reference = self.root / 'reference.json'; reference.write_bytes(canonical_json_bytes(refs))
        destination = self.root / 'publication'
        output = self.root / 'github-output'
        self.fixture.job.update(status='in_progress', conclusion=None)
        args = ['collector-controls', '--handoff', str(handoff), '--reference-path', str(reference),
            '--destination', str(destination), '--github-output', str(output), '--wave', '9',
            '--artifact-id', '700', '--artifact-sha256', self.fixture.source['artifactSha256'],
            '--workflow-sha', self.fixture.pin]
        environment = {'GITHUB_RUN_ID': str(self.fixture.producer['runId']),
            'GITHUB_RUN_ATTEMPT': str(self.fixture.producer['runAttempt']), 'GITHUB_TOKEN': 'synthetic'}
        with patch.object(sys, 'argv', args), patch.dict(os.environ, environment), \
                patch.object(reuse, 'api_request', side_effect=lambda url, token: json.dumps(self.fixture.api(url, token)).encode()):
            completed._publish_main()
        files = {path.name: path.read_bytes() for path in destination.iterdir()}
        self.assertEqual({'collector-controls.json', 'runtime-references.json'}, files.keys())
        envelope = json.loads(files['collector-controls.json'])
        self.assertEqual(700, envelope['source']['artifactId'])
        self.assertEqual(801, envelope['source']['jobId'])
        self.assertEqual(self.fixture.producer, envelope['source']['producer'])
        self.assertEqual('artifact_name=' + completed.collector_control_artifact_name(envelope['source']) + '\n' +
            'source=' + canonical_json_bytes(envelope['source']).decode().rstrip('\n') + '\n', output.read_text())
        self.assertFalse(any(url.endswith('/zip') for url in self.fixture.urls))
        self.assertFalse(self.fixture.downloads)
        # Retained state from a different run cannot become current transport.
        with patch.object(reuse, 'api_request', side_effect=AssertionError('reject before HTTP')):
            with self.assertRaisesRegex(ValueError, 'current workflow run or earlier attempt'):
                completed.publish_current_collector_controls(handoff, reference, self.root / 'retry',
                    wave=9, artifact_id=700, artifact_sha256=self.fixture.source['artifactSha256'],
                    workflow_sha=self.fixture.pin, token='synthetic',
                    environ={**environment, 'GITHUB_RUN_ID': str(self.fixture.producer['runId'] + 1)})


class CollectorAdvancePublicationTest(unittest.TestCase):
    def test_cli_choice_reaches_the_shared_advancer(self):
        import sdk_workflow as workflow
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            original = root / 'input'
            for name in ('product-resume-inputs', 'product-resume-state', 'runtime-state'):
                (original / name).mkdir(parents=True)
            for enabled in (False, True):
                with self.subTest(enabled=enabled):
                    def advance(*args, **kwargs):
                        self.assertIs(enabled, kwargs['checkpoint_controls'])
                        self.assertEqual('native-package', kwargs['sdk_family'])
                        args[4].mkdir(parents=True)
                        return {'matrices': {'sdk': []}}
                    with patch.object(workflow.product_reuse, 'collect_runtime_workers', return_value={'rows': []}), \
                            patch.object(workflow.product_reuse, 'advance_products', side_effect=advance) as called:
                        self.assertEqual(0, workflow.main(['collect', '--family', 'native-package',
                            '--input-root', str(original), '--destination', str(root / str(enabled)),
                            '--repository-root', str(root), '--wave', '4', '--trusted-workflow-sha', 'c' * 40,
                            '--github-output', str(root / 'output')]
                            + (['--checkpoint-controls'] if enabled else [])))
                        called.assert_called_once()

    def test_real_native_continuation_retains_receipt_from_its_existing_carrier(self):
        self._advance_with_controls(True)

    def test_default_native_continuation_does_not_project_receipt_controls(self):
        self._advance_with_controls(False)

    def _advance_with_controls(self, enabled):
        from ci.tests import test_product_native_continuation as fixture
        actual = fixture.adapter.advance_products
        writer = completed.write_collector_receipts
        calls = []

        def retain(carrier, result, destination):
            self.assertEqual(1, sum(row['product'] == 'sdk' for row in carrier['objects']))
            writer(carrier, result, destination)
            row = next(row for row in carrier['objects'] if row['product'] == 'sdk')
            self.assertEqual(row['receiptBytes'], (destination / (row['receiptSha256'][7:] + '.json')).read_bytes())
            calls.append(destination)

        def advance(*args, **kwargs):
            # The original integration fixture drives a successful package into
            # its real next validation plan. Only that collector uses this scope.
            if args[3]:
                kwargs['sdk_family'] = 'native-package'
                if enabled: kwargs['checkpoint_controls'] = True
            result = actual(*args, **kwargs)
            self.assertEqual(bool(enabled and args[3]), (args[4] / completed.COLLECTOR_RECEIPTS).exists())
            return result

        with patch.object(fixture.adapter, 'advance_products', side_effect=advance), \
                patch.object(completed, 'write_collector_receipts', side_effect=retain):
            existing = fixture.NativeContinuationTest('test_original_objects_reach_package_then_host_plan_without_product_processes')
            existing.test_original_objects_reach_package_then_host_plan_without_product_processes()
        self.assertEqual(int(enabled), len(calls))


if __name__ == '__main__':
    unittest.main()
