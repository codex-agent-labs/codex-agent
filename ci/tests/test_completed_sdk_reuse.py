"""Incremental control invariants; synthetic controls grant no native authority."""

from copy import deepcopy
from pathlib import Path
from contextlib import ExitStack
import tempfile
import unittest
from unittest.mock import patch

import completed_sdk_reuse as completed
from products.inventory import canonical_json_bytes, sha256_bytes
from products.receipt import compute_build_key
from reuse_qualification import QualificationIncompatible
from ci.tests.test_products import phase_receipt


class CompletedSdkControlsTest(unittest.TestCase):
    def setUp(self):
        def record(receipt):
            return {**{field: receipt[field] for field in completed.IDENTITY},
                'buildKey': receipt['buildKey'], 'receiptSha256': sha256_bytes(canonical_json_bytes(receipt)),
                'objectSha256': sha256_bytes(b'synthetic object'), 'state': 'retained'}
        def authority(receipt):
            return {**{field: receipt[field] for field in completed.IDENTITY},
                **{field: receipt['inputs'][field] for field in
                   ('toolchainProfileDigest', 'flagsDigest', 'outputSchemaVersion')}}
        contract = phase_receipt()
        self.receipt = {**deepcopy(contract), 'product': 'sdk', 'component': 'csharp', 'target': 'desktop'}
        self.receipt['buildKey'] = compute_build_key(**{field: self.receipt[field] for field in
            (*completed.IDENTITY, 'inputs')})
        frozen, phase = record(contract), record(self.receipt)
        request = {'repository': contract['producer']['repository'], 'pullRequest': 31,
                   'versions': {'sdk': '0.2.0'}, 'catalogs': [], 'phaseAuthorities': [authority(contract)]}
        self.base = {'request': deepcopy(request), 'expectedResult': {'phases': [frozen]}}
        prefix = 'product-resume-state/'
        producer = {**contract['producer'], 'runId': 8}
        request.update(repositoryRevision=producer['commit'], availableObjects=[frozen, phase])
        request['phaseAuthorities'].append(authority(self.receipt))
        self.receipt_path = prefix + 'original/csharp/phase-receipt.json'
        self.controls = {prefix + 'reuse-wave-request.json': request, prefix + 'producer.json': producer,
            prefix + 'reuse-wave-result.json': {'phases': [frozen, phase],
                                               'matrices': {'contract': [], 'runtime': [], 'sdk': []}},
            self.receipt_path: self.receipt}
        self.spec = {'completedPhases': [{**{field: phase[field] for field in
            (*completed.IDENTITY, *completed.OBJECT)}, 'receiptPath': self.receipt_path}],
            'stateRoot': prefix.rstrip('/'), 'source': {'producer': producer}}
        self.bind_controls()

    def bind_controls(self):
        self.spec['controls'] = [{'relativePath': path, 'bytes': len(canonical_json_bytes(value)),
            'sha256': sha256_bytes(canonical_json_bytes(value))} for path, value in sorted(self.controls.items())]

    def test_native_javascript_capture_and_replay_keep_only_exact_controls(self):
        import reuse_qualification as native
        import sdk_ios_binary_recovery as recovery
        from products.restore import PHASE_SHARD_NAME
        receipt = deepcopy(self.receipt)
        receipt.update(component='javascript', phase='package', target='node')
        receipt['buildKey'] = compute_build_key(**{field: receipt[field] for field in (*completed.IDENTITY, 'inputs')})
        record = {**{field: receipt[field] for field in completed.IDENTITY}, 'buildKey': receipt['buildKey'],
                  'receiptSha256': sha256_bytes(canonical_json_bytes(receipt)),
                  'objectSha256': sha256_bytes(b'synthetic object')}
        spec = {'request': self.base['request'], 'expectedResult': {'phases': [record]}}
        cap = native.CompletedFrozenReuse(spec, [receipt], native._COMPLETED_FROZEN,
            revision=receipt['producer']['commit'], sdk={'extension': {
                'spec': {'completedPhases': [record]}, 'proof': {}}})
        artifact = {'id': 71, 'name': 'synthetic-original', 'digest': record['objectSha256']}
        consumer = {**receipt['producer'], 'runId': receipt['producer']['runId'] + 1}
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            root = Path(temporary).resolve()
            observed = stack.enter_context(patch.object(native.CompletedFrozenReuse, 'observe_extended_sdk',
                return_value=({}, artifact, [])))
            stack.enter_context(patch.object(recovery.products, 'api_json', return_value={}))
            stack.enter_context(patch.object(recovery, '_require_prior', return_value=(7, 1)))
            stack.enter_context(patch.object(recovery.products, '_runtime_prior_workflow_sha', return_value='a' * 40))
            records = recovery.capture_completed_javascript(root, root, completed_frozen=cap,
                producer=consumer, token='synthetic')
            capture = root / 'prior-failed-sdk-javascript'
            def replay(authority):
                return recovery.replay_prior_javascript_package(capture, root,
                    plan={'repository': receipt['producer']['repository']}, consumer_producer=consumer,
                    trusted_workflow_sha='a' * 40, token='synthetic', environ={}, completed_frozen=authority)
            self.assertEqual(records, replay(cap))
            self.assertEqual(2, observed.call_count)
            self.assertFalse((root / records[0]['objectPath']).exists())
            shard = capture / 'javascript/package/node/original/shard'
            self.assertEqual({PHASE_SHARD_NAME, 'phase-receipt.json'}, {p.name for p in shard.iterdir()})
            with patch.object(recovery, '_capture_javascript_package', side_effect=ValueError('ordinary whole upload required')):
                with self.assertRaisesRegex(ValueError, 'whole upload required'):
                    replay(None)
            with self.assertRaisesRegex(ValueError, 'concrete native authority'):
                replay(object())
            (shard / 'phase-receipt.json').write_bytes(canonical_json_bytes({**receipt, 'productVersion': 'changed'}))
            with self.assertRaises(ValueError):
                replay(cap)

    def test_incremental_schema_and_parent_subject_are_fixed_before_inheritance(self):
        import json
        spec = json.loads((Path(__file__).parent / 'data/sdk-completed-resume.json').read_bytes())
        completed._spec(spec)
        proof = {key: {} for key in ('parentProof', 'controls', 'source', 'originals', 'members',
                                     'contractSource', 'contractFiles')}
        proof.update(schemaVersion=2, kind='completed-sdk-reuse', issuerCommit='a' * 40,
                     specSha256=sha256_bytes(canonical_json_bytes(spec)))
        with patch('reuse_qualification._validate_completed_sdk') as inherit:
            with self.assertRaisesRegex(ValueError, 'approved native issuer or parent'):
                completed.validate_extension(spec, proof, {'signer_commit': 'a' * 40},
                    root=Path.cwd(), revision='a' * 40, frozen={}, token='synthetic')
            inherit.assert_not_called()
        altered = deepcopy(spec)
        altered['source']['artifactBytes'] = completed.LIMIT + 1
        with self.assertRaisesRegex(ValueError, 'bounded original upload'):
            completed._spec(altered)

    def test_native_parent_commit_is_fetched_only_when_missing_and_exactly_pinned(self):
        import reuse_qualification as native
        from types import SimpleNamespace
        commit, tree = 'a' * 40, 'b' * 40
        with patch.object(native.subprocess, 'run', return_value=SimpleNamespace(returncode=0)), \
                patch('product_reuse.api_json') as observe, patch('sdk_handoff._ensure_pinned_git_commit') as fetch:
            native._ensure_native_issuer_commit(Path.cwd(), commit, 'synthetic')
            observe.assert_not_called()
            fetch.assert_not_called()
        with patch.object(native.subprocess, 'run', return_value=SimpleNamespace(returncode=128)), \
                patch('product_reuse.api_json', return_value={'sha': commit, 'tree': {'sha': tree}}) as observe, \
                patch('sdk_handoff._ensure_pinned_git_commit') as fetch:
            native._ensure_native_issuer_commit(Path.cwd(), commit, 'synthetic')
            fetch.assert_called_once_with(Path.cwd(), commit, tree, 'synthetic')
            fetch.reset_mock()
            observe.return_value['sha'] = 'c' * 40
            with self.assertRaisesRegex(ValueError, 'authenticated pin'):
                native._ensure_native_issuer_commit(Path.cwd(), commit, 'synthetic')
            fetch.assert_not_called()

    def validate(self):
        return completed.validate_controls(self.spec, self.controls, self.base)

    def test_exact_controls_preserve_native_base_and_reject_changed_receipts_or_scope(self):
        request, phases, receipts = self.validate()
        self.assertEqual([self.receipt], receipts)
        self.assertEqual('csharp', phases[0]['component'])
        self.assertEqual(2, len(request['availableObjects']))
        saved = deepcopy(self.controls)
        mutations = (
            lambda: self.controls[self.receipt_path].update(productVersion='9.0.0'),
            lambda: self.controls['product-resume-state/reuse-wave-result.json']['phases'][0].update(
                objectSha256=sha256_bytes(b'changed native predecessor')),
            lambda: self.controls['product-resume-state/reuse-wave-request.json'].update(catalogs=[{}]),
            lambda: self.controls['product-resume-state/producer.json'].update(runId=9),
        )
        for mutate in mutations:
            self.controls = deepcopy(saved)
            mutate()
            # Even re-binding bytes cannot change the fixed semantic identities.
            self.bind_controls()
            with self.assertRaises(ValueError):
                self.validate()
        self.controls = deepcopy(saved)
        self.bind_controls()
        self.controls[self.receipt_path]['productVersion'] = '9.0.0'
        with self.assertRaisesRegex(ValueError, 'differs from its approved original'):
            self.validate()

    def test_current_owning_inputs_and_authorities_still_gate_native_completion(self):
        request, phases, receipts = self.validate()
        expected = request['phaseAuthorities'][-1]
        with patch('products.inventory.tree_entries', return_value=[('owned', ('100644', 'same'))]) as trees, \
                patch('products.selection.phase_inventory_paths', return_value=['owned']), \
                patch('product_reuse._authorities', return_value=([expected], None)) as authorities:
            arguments = dict(root=Path('/synthetic'), revision='b' * 40, original_revision='a' * 40)
            completed.validate_current(request, phases, receipts, **arguments)
            authorities.return_value = ([{**expected, 'outputSchemaVersion': 2}], None)
            with self.assertRaisesRegex(QualificationIncompatible, 'current authority changed'):
                completed.validate_current(request, phases, receipts, **arguments)
            authorities.return_value = [expected], None
            trees.side_effect = [[('owned', ('100644', 'before'))], [('owned', ('100644', 'after'))]]
            with self.assertRaisesRegex(QualificationIncompatible, 'owning inputs changed'):
                completed.validate_current(request, phases, receipts, **arguments)


if __name__ == '__main__':
    unittest.main()
