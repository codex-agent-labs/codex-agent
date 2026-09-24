"""Prepared signing-controller composition with explicit source/signing mocks.

Real private trees, record comparisons and mutation guards are exercised. These
fixtures are not authenticated products, actual CI observations or signatures.
"""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci import runtime_prepared_release as release
from products.inventory import (
    canonical_json_bytes, publish_regular_tree as actual_publish_regular_tree,
    regular_file_inventory, sha256_bytes,
)


class RuntimePreparedReleaseTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='prepared-release-controller-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.trusted, self.candidate = self.root / 'trusted', self.root / 'candidate'
        self.trusted.mkdir()
        self.candidate.mkdir()
        self.plan = self.root / 'impact-plan.json'
        self.plan_raw = canonical_json_bytes({'synthetic': 'original plan'})
        self.plan.write_bytes(self.plan_raw)
        self.output = self.root / 'result'
        self.producer = {'repository': 'codex-agent-labs/codex-agent', 'workflowPath': '.github/workflows/ci.yml',
            'commit': 'a' * 40, 'tree': 'b' * 40, 'event': 'pull_request', 'runId': 71,
            'runAttempt': 2, 'pullRequest': 31}
        self.options = {'target': 'linux-x64', 'expected_build_key': 'sha256:' + 'c' * 64,
            'artifact_id': 701, 'artifact_sha256': 'sha256:' + 'd' * 64, 'state_wave': 4,
            'preparation_artifact_id': 702, 'preparation_artifact_sha256': 'sha256:' + 'e' * 64,
            'trusted_source_sha': 'f' * 40, 'trusted_workflow_sha': '1' * 40,
            'transport_producer': self.producer, 'event_payload': {'number': 31},
            'environment': {'GITHUB_RUN_ID': '71', 'GITHUB_RUN_ATTEMPT': '2'}, 'token': 'synthetic-token'}
        self.change_record = None
        self.change_state = False
        self.late_mutation = None
        self.retained = False
        self.originals = {}
        self.leaf_result = {'synthetic': 'signed leaf result'}
        self.context = self.mock('verify_product_release_context', return_value=(
            self.trusted, self.producer, '2' * 40, {}, 'mocked context authority'))
        self.validate = self.mock('_validate_plan', return_value={'validationCommit': 'a' * 40,
            'remoteBuildAuthorized': True, 'event': 'pull_request'})
        self.consumer = self.mock('_consumer', return_value={'kind': 'ci', 'producer': self.producer})
        self.preparation = self.mock('capture_runtime_signing_preparation', side_effect=self.capture_preparation)
        self.state = self.mock('capture_runtime_resume_upload', side_effect=self.capture_state)
        self.restore = self.mock('restore_prepared_runtime_originals', side_effect=self.restore_originals)
        self.native = self.mock('verify_native_prepared_selection', side_effect=self.native_arguments)
        self.aggregate = self.mock('verify_aggregate_prepared_selection', return_value={})
        self.sign_native = self.mock('attest_runtime_variant_ci', side_effect=self.sign)
        self.sign_aggregate = self.mock('_attest_selected_runtime_aggregate', side_effect=self.sign)

    def mock(self, name, **kwargs):
        return self.enterContext(patch.object(release, name, **kwargs))

    @staticmethod
    def write(path, raw):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)

    def metadata(self):
        target = self.options['target']
        return {'product': 'runtime', 'component': 'runtime-aggregate' if target == 'aggregate' else target,
            'phase': 'metadata', 'target': target, 'state': 'retained',
            'buildKey': self.options['expected_build_key'], 'receiptSha256': 'sha256:' + '3' * 64,
            'objectSha256': 'sha256:' + '4' * 64, 'source': None, 'transportSource': None, 'misses': []}

    def state_original(self, original):
        self.write(original / 'product-resume-inputs/plan/impact-plan.json', self.plan_raw)
        result = canonical_json_bytes({'phases': [self.metadata()]})
        self.write(original / 'product-resume-state/reuse-wave-result.json', result)
        if self.options['state_wave']:
            self.write(original / 'runtime-state/reuse-wave-result.json', result)
        self.write(original / 'product-resume-state/original-receipt.bin', b'original receipt\x00\xff')
        self.write(original / 'product-resume-state/empty-diagnostics.log', b'')

    def capture_preparation(self, plan, destination, **kwargs):
        self.preparation_root = destination
        self.prepared_root = destination / 'original'
        self.state_original(self.prepared_root / 'selected-state-transport/original')
        self.write(self.prepared_root / 'selected-state-transport/capture-transport.json', b'first original observation\n')
        self.selection = {'schemaVersion': 1, 'producer': self.producer, 'target': self.options['target'],
                          'metadata': self.metadata()}
        selection_raw = canonical_json_bytes(self.selection)
        self.write(self.prepared_root / 'selected-inputs/selection.json', selection_raw)
        self.write(self.prepared_root / 'selected-inputs/original-receipt.bin', b'original selected receipt\x00\xff')
        record = {'schemaVersion': 1, 'target': self.options['target'], 'producer': self.producer,
            'expectedBuildKey': self.options['expected_build_key'], 'stateWave': self.options['state_wave'],
            'stateArtifact': {'artifactId': self.options['artifact_id'], 'artifactSha256': self.options['artifact_sha256']},
            'planSha256': sha256_bytes(self.plan_raw), 'selectionSha256': sha256_bytes(selection_raw)}
        if self.change_record:
            self.change_record(record)
        self.write(self.prepared_root / 'preparation.json', canonical_json_bytes(record))
        if self.retained:
            self.write(self.prepared_root / 'release-handoff/original-signature.bin', b'opaque retained signature\n')
        self.write(destination / 'original-upload.zip', b'synthetic preparation ZIP transport seam\n')
        self.write(destination / 'capture-transport.json', canonical_json_bytes({'captureProducer': self.producer}))
        return {'captureProducer': self.producer}

    def capture_state(self, plan, destination, **kwargs):
        self.state_root = destination
        self.state_original(destination / 'original')
        if self.change_state:
            self.write(destination / 'original/product-resume-state/original-receipt.bin', b'different original receipt\n')
        self.write(destination / 'capture-transport.json', b'fresh independent observation\n')
        return {'captureProducer': self.producer}

    def native_arguments(self, root, selection, **kwargs):
        self.assertEqual(self.selection, selection)
        self.assertIs(self.originals, kwargs['originals'])
        return {'runtime_stage_root': root / 'runtime', 'phase_receipts': {},
            'variant_payload': root / 'variant.json', 'contract': {}, 'contract_version': '0.8.0',
            'release_handoffs': (), 'expected_receipt_sha256s': {},
            'expected_contract_receipt_sha256': 'sha256:' + '5' * 64,
            'expected_build_key': self.options['expected_build_key']}

    def restore_originals(self, plan, original, destination, **kwargs):
        self.assertEqual(self.state_root / 'original', original)
        self.assertEqual(self.selection, kwargs['selection'])
        self.write(destination / 'original-receipt.bin', b'original restored receipt\x00\xff')
        return self.originals

    def sign(self, repository, destination, **kwargs):
        self.assertEqual(self.trusted, repository)
        self.assertTrue(self.preparation_root.exists())
        self.assertTrue(self.state_root.exists())
        self.assertFalse(self.output.exists())
        self.write(destination / 'caller.json', b'synthetic leaf result\n')
        if self.late_mutation == 'plan':
            self.plan.write_bytes(b'changed after signing\n')
        elif self.late_mutation == 'preparation':
            self.write(self.prepared_root / 'selected-inputs/original-receipt.bin', b'changed after signing\n')
        elif self.late_mutation == 'state':
            self.write(self.state_root / 'original/product-resume-state/original-receipt.bin', b'changed after signing\n')
        return self.leaf_result

    def invoke(self, **changes):
        self.options.update(changes)
        return release.attest_prepared_runtime_ci(self.trusted, self.candidate, self.plan, self.output, **self.options)

    def test_independent_capture_ids_and_private_lifetime_before_publication(self):
        result = self.invoke()
        self.assertEqual(self.leaf_result, result)
        self.assertEqual(702, self.preparation.call_args.kwargs['artifact_id'])
        self.assertEqual(self.options['preparation_artifact_sha256'], self.preparation.call_args.kwargs['artifact_sha256'])
        self.assertEqual(701, self.state.call_args.kwargs['artifact_id'])
        self.assertEqual(4, self.state.call_args.kwargs['state_wave'])
        self.assertNotIn('sdk_validation_tooling', self.restore.call_args.kwargs)
        self.native.assert_called_once()
        self.aggregate.assert_not_called()
        self.sign_native.assert_called_once()
        self.sign_aggregate.assert_not_called()
        self.assertEqual(b'synthetic leaf result\n', (self.output / 'caller.json').read_bytes())
        self.assertEqual(b'original receipt\x00\xff', (self.output /
            'selected-state-transport/original/product-resume-state/original-receipt.bin').read_bytes())
        self.assertEqual(b'original selected receipt\x00\xff', (self.output /
            'preparation-transport/original/selected-inputs/original-receipt.bin').read_bytes())
        self.assertFalse(self.preparation_root.exists())
        self.assertFalse(self.state_root.exists())
        self.assertEqual(self.plan_raw, self.plan.read_bytes())

    def test_record_field_mismatches_reject_before_signing(self):
        changes = {'target': 'aggregate', 'expectedBuildKey': 'sha256:' + '9' * 64, 'stateWave': 0,
            'producer': {**self.producer, 'runAttempt': 1}, 'planSha256': 'sha256:' + '9' * 64,
            'selectionSha256': 'sha256:' + '9' * 64, 'schemaVersion': 2,
            'stateArtifact': {'artifactId': 99, 'artifactSha256': self.options['artifact_sha256']},
            'extra': 'not permitted'}
        for field, value in changes.items():
            self.change_record = lambda record, field=field, value=value: record.update({field: value})
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.invoke()
            self.sign_native.assert_not_called()
            self.sign_aggregate.assert_not_called()
            self.assertFalse(self.output.exists())

    def test_record_integer_booleans_are_not_equal_integer_authority(self):
        for field in ('schemaVersion', 'stateWave', 'artifactId'):
            self.options.update(state_wave=1, artifact_id=1)
            def mutation(record, field=field):
                if field == 'artifactId':
                    record['stateArtifact'][field] = True
                else:
                    record[field] = True
            self.change_record = mutation
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.invoke()
            self.sign_native.assert_not_called()
            self.assertFalse(self.output.exists())

    def test_aggregate_fresh_and_retained_routes_do_not_rewrite_original_handoff(self):
        for retained in (False, True):
            with self.subTest(retained=retained):
                self.retained = retained
                self.output = self.root / f'aggregate-{retained}'
                self.sign_aggregate.reset_mock()
                handoffs = {}
                if not retained:
                    for target in release.NATIVE_TARGETS:
                        path = self.root / 'variants' / target
                        self.write(path / 'signature.bin', b'original native signature\n')
                        handoffs[target] = path
                self.assertEqual(self.leaf_result, self.invoke(target='aggregate', variant_handoffs=handoffs))
                self.assertEqual(handoffs, self.sign_aggregate.call_args.kwargs['variant_handoffs'])
                expected = self.prepared_root / 'release-handoff' if retained else None
                self.assertEqual(expected, self.sign_aggregate.call_args.kwargs['release_handoff'])
                self.assertIs(self.originals, self.aggregate.call_args.kwargs['originals'])
                self.native.assert_not_called()
                self.sign_native.assert_not_called()
                if retained:
                    self.assertEqual(b'opaque retained signature\n', (self.output /
                        'preparation-transport/original/release-handoff/original-signature.bin').read_bytes())

    def test_reauthenticated_original_state_must_match_preparation_history(self):
        self.change_state = True
        with self.assertRaises(ValueError):
            self.invoke()
        self.restore.assert_not_called()
        self.sign_native.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_late_mutation_and_signing_failure_never_publish(self):
        for mutation in ('plan', 'preparation', 'state'):
            self.plan.write_bytes(self.plan_raw)
            self.late_mutation = mutation
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.invoke()
            self.assertFalse(self.output.exists())
        self.plan.write_bytes(self.plan_raw)
        self.late_mutation = None
        self.sign_native.side_effect = ValueError('signing gate rejected')
        with self.assertRaisesRegex(ValueError, 'signing gate rejected'):
            self.invoke()
        self.assertFalse(self.output.exists())

    def test_changed_verified_result_fails_before_publication(self):
        def mutate_before_copy(source, destination, *, allow_empty, expected_inventory):
            (source / 'caller.json').write_bytes(b'changed after verification\n')
            actual_publish_regular_tree(source, destination, allow_empty=allow_empty,
                                        expected_inventory=expected_inventory)

        with patch.object(release, 'publish_regular_tree', side_effect=mutate_before_copy), \
                self.assertRaisesRegex(ValueError, 'pinned inventory'):
            self.invoke()
        self.assertFalse(self.output.exists())

    def test_no_sdk_replay_entrypoints_and_existing_output_is_immutable(self):
        import product_reuse
        with patch.object(product_reuse, '_verified_product_state', side_effect=AssertionError('SDK replay forbidden')), \
                patch.object(product_reuse, 'materialize_runtime_attestation_inputs', side_effect=AssertionError('SDK replay forbidden')):
            self.invoke()
        before = regular_file_inventory(self.output, allow_empty=True)
        with self.assertRaises(ValueError):
            self.invoke()
        self.assertEqual(before, regular_file_inventory(self.output, allow_empty=True))


if __name__ == '__main__':
    unittest.main()
