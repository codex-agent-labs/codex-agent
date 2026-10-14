"""Incremental control invariants; synthetic controls grant no native authority."""

from copy import deepcopy
from pathlib import Path
from contextlib import ExitStack
import tempfile
import os
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
        proof.update(schemaVersion=spec['schemaVersion'], kind='completed-sdk-reuse', issuerCommit='a' * 40,
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

    def test_native_csharp_and_ios_package_controls_route_without_body_or_gate_replay(self):
        import reuse_qualification as native
        import sdk_ios_binary_recovery as recovery
        for component, phase, target in (('csharp', 'binary', 'desktop'), ('sdk-ios', 'package', 'ios')):
            receipt = deepcopy(self.receipt)
            receipt.update(component=component, phase=phase, target=target)
            receipt['buildKey'] = compute_build_key(**{field: receipt[field] for field in (*completed.IDENTITY, 'inputs')})
            record = {**{field: receipt[field] for field in completed.IDENTITY}, 'buildKey': receipt['buildKey'],
                'receiptSha256': sha256_bytes(canonical_json_bytes(receipt)), 'objectSha256': sha256_bytes(b'object')}
            cap = native.CompletedFrozenReuse({'request': self.base['request'], 'expectedResult': {'phases': [record]}},
                [receipt], native._COMPLETED_FROZEN, revision=receipt['producer']['commit'],
                sdk={'extension': {'spec': {'schemaVersion': 3, 'completedPhases': [record]}, 'proof': {}}})
            consumer = {**receipt['producer'], 'runId': receipt['producer']['runId'] + 1}
            artifact = {'id': 71, 'name': 'synthetic-original', 'digest': sha256_bytes(b'original')}
            plan = {'repository': receipt['producer']['repository'], 'remoteBuildAuthorized': True,
                    'pullRequest': receipt['producer']['pullRequest']}
            with self.subTest(component=component), tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
                root = Path(temporary).resolve()
                plan_path = root / 'plan.json'
                plan_path.write_bytes(canonical_json_bytes(plan))
                stack.enter_context(patch.object(native.CompletedFrozenReuse, 'observe_extended_sdk', return_value=({}, artifact, [])))
                stack.enter_context(patch.object(recovery.products, 'api_json', return_value={}))
                stack.enter_context(patch.object(recovery, '_require_prior', return_value=(7, 1)))
                stack.enter_context(patch.object(recovery.products, '_runtime_prior_workflow_sha', return_value='a' * 40))
                stack.enter_context(patch.object(recovery.products, '_validate_plan', return_value=plan))
                stack.enter_context(patch.object(recovery.products, '_contract_ci_upload_metadata', return_value=artifact))
                stack.enter_context(patch.object(recovery, 'locate_original_apple_upload', return_value={
                    'artifact_id': 71, 'artifact_sha256': artifact['digest']}))
                stack.enter_context(patch.object(recovery, '_capture_ios_original', side_effect=AssertionError('body/gate replay')))
                stack.enter_context(patch.object(recovery, '_capture_javascript_package', side_effect=AssertionError('body replay')))
                records = recovery.capture_completed_javascript(root, root, completed_frozen=cap, producer=consumer, token='synthetic')
                self.assertEqual(1, len(records))
                self.assertFalse((root / records[0]['objectPath']).exists())
                folder = 'prior-failed-sdk-ios-package' if component == 'sdk-ios' else 'prior-failed-sdk-csharp'
                def replay(authority):
                    options = dict(plan=plan, consumer_producer=consumer, trusted_workflow_sha='a' * 40,
                                   token='synthetic', environ={}, completed_frozen=authority, phase=phase)
                    if component == 'sdk-ios':
                        return recovery.replay_prior_ios_binary(root / folder, root,
                            plan_path=plan_path, repository_root=root, **options)
                    return recovery.replay_prior_javascript_package(root / folder, root, component=component, **options)
                self.assertEqual(records, replay(cap))
                if component == 'sdk-ios':
                    # Exercise the shared worker-entry replay, not only its leaf helper.
                    plan.update(event='pull_request', validationCommit=receipt['producer']['commit'])
                    plan_path.write_bytes(canonical_json_bytes(plan))
                    (root / 'producer.json').write_bytes(canonical_json_bytes(consumer))
                    instance = recovery.products._identity(receipt)
                    request = {'requested': [recovery.products._identity_record(instance)],
                               'sdkRuntimeSource': None}
                    actual_replay = recovery.replay_prior_ios_binary

                    class ReplayedControls(Exception):
                        pass

                    def replayed(*args, **kwargs):
                        self.assertEqual(records, actual_replay(*args, **kwargs))
                        raise ReplayedControls  # Stop before unrelated Contract/planner fixtures.

                    with ExitStack() as shared:
                        shared.enter_context(patch.object(native.CompletedFrozenReuse, 'check_request'))
                        shared.enter_context(patch.object(recovery.products, '_consumer',
                            return_value={'kind': 'ci', 'producer': consumer}))
                        shared.enter_context(patch.object(recovery.products, '_relocated_wave_control', return_value=request))
                        shared.enter_context(patch.object(recovery.products, '_requested', return_value=(instance,)))
                        shared.enter_context(patch.object(recovery.products, '_versions',
                            return_value={'sdk': '0.2.0', 'runtime-release': '0.2.0'}))
                        shared.enter_context(patch.object(recovery.products, 'sdk_runtime_source', return_value=None))
                        shared.enter_context(patch.object(recovery.products, '_dependency_closure', return_value=(instance,)))
                        shared.enter_context(patch.object(recovery.products, '_authorities', return_value=([], None)))
                        shared.enter_context(patch.object(recovery, 'replay_prior_ios_binary', side_effect=replayed))
                        with self.assertRaises(ReplayedControls):
                            recovery.products._verified_product_state(plan_path, root, root, root,
                                {'GITHUB_TOKEN': 'synthetic'}, None, sdk_original_workflow_sha='a' * 40,
                                completed_frozen=cap)
                    inputs = root / 'inputs'
                    inputs.mkdir()
                    (inputs / 'same-plan.json').write_bytes(plan_path.read_bytes())
                    published = root / 'published'
                    report = recovery.products._publish_runtime_original_reference_handoff(
                        inputs, root, published, completed_frozen=cap)
                    self.assertEqual([], report['sources'])
                    self.assertTrue((published / 'runtime-original-references.json').exists())
                    self.assertFalse((published / 'product-resume-state' / records[0]['objectPath']).exists())
                with self.assertRaisesRegex(AssertionError, 'body'):
                    replay(None)
                with self.assertRaisesRegex(ValueError, 'concrete native authority'):
                    replay(object())
                shard = root / folder / f'{component}/{phase}/{target}/original/shard'
                (shard / 'phase-receipt.json').write_bytes(canonical_json_bytes({**receipt, 'productVersion': 'changed'}))
                with self.assertRaises(ValueError):
                    replay(cap)

    def test_independent_native_captures_overlap_but_any_observation_failure_aborts(self):
        import threading
        import reuse_qualification as native
        import sdk_ios_binary_recovery as recovery
        receipts, records = [], []
        for phase in ('package', 'validation', 'metadata'):
            receipt = deepcopy(self.receipt)
            receipt.update(component='javascript', phase=phase, target='node')
            receipt['buildKey'] = compute_build_key(**{field: receipt[field] for field in (*completed.IDENTITY, 'inputs')})
            receipts.append(receipt)
            records.append({**{field: receipt[field] for field in completed.IDENTITY}, 'buildKey': receipt['buildKey'],
                'receiptSha256': sha256_bytes(canonical_json_bytes(receipt)), 'objectSha256': sha256_bytes(b'object')})
        cap = native.CompletedFrozenReuse({'request': self.base['request'], 'expectedResult': {'phases': records}},
            receipts, native._COMPLETED_FROZEN, revision=receipt['producer']['commit'],
            sdk={'extension': {'spec': {'schemaVersion': 3, 'completedPhases': records}, 'proof': {}}})
        barrier = threading.Barrier(3)
        seen = recovery.products._CI_OBSERVATIONS.get()
        def observe(record, **kwargs):
            self.assertIsNotNone(recovery.products._CI_OBSERVATIONS.get())
            barrier.wait(timeout=5)  # A serial implementation cannot reach all three participants.
            return {}, {'id': 71}, []
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            with patch.object(native.CompletedFrozenReuse, 'observe_extended_sdk', side_effect=observe):
                result = recovery.capture_completed_javascript(root / 'success', root,
                    completed_frozen=cap, producer={}, token='synthetic')
            self.assertEqual([row['phase'] for row in records], [row['phase'] for row in result])
            self.assertTrue(all(not (root / row['objectPath']).exists() for row in result))
            self.assertIs(seen, recovery.products._CI_OBSERVATIONS.get())
            def failed(record, **kwargs):
                if record['phase'] == 'validation':
                    raise ValueError('original provenance changed')
                return {}, {'id': 71}, []
            with patch.object(native.CompletedFrozenReuse, 'observe_extended_sdk', side_effect=failed), \
                    self.assertRaisesRegex(ValueError, 'original provenance changed'):
                recovery.capture_completed_javascript(root / 'failure', root,
                    completed_frozen=cap, producer={}, token='synthetic')
            self.assertIs(seen, recovery.products._CI_OBSERVATIONS.get())

    def test_large_native_package_member_is_bound_to_its_original_only_in_v3(self):
        import json
        import reuse_qualification as native
        from products.restore import object_relative_path
        spec = json.loads((Path(__file__).parent / 'data/sdk-completed-resume.json').read_bytes())
        phase = {**spec['completedPhases'][0], 'component': 'sdk-ios', 'phase': 'package', 'target': 'ios'}
        spec['completedPhases'] = [phase]
        spec['originals'] = [{**spec['originals'][0], **{key: phase[key] for key in completed.IDENTITY}}]
        spec['schemaVersion'] = 3
        parent = {'schemaVersion': 1}
        spec['parentProofSha256'] = sha256_bytes(canonical_json_bytes(parent))
        member = {'relativePath': 'shard/' + object_relative_path(phase['buildKey'], phase['receiptSha256']),
                  'bytes': 3_631_000_000, 'sha256': phase['objectSha256']}
        proof = {'schemaVersion': 3, 'kind': 'completed-sdk-reuse', 'issuerCommit': 'a' * 40,
            'specSha256': sha256_bytes(canonical_json_bytes(spec)), 'parentProof': parent,
            'controls': {}, 'source': {'source': 1}, 'originals': [{'original': 1}],
            'members': [member], 'contractSource': {'source': 1}, 'contractFiles': {}}
        available = {**phase, 'objectPath': 'unused-for-original-package.zip'}
        with ExitStack() as stack:
            stack.enter_context(patch.object(native, '_validate_completed_sdk', return_value={}))
            stack.enter_context(patch.object(completed, '_base', return_value={}))
            stack.enter_context(patch.object(completed, 'validate_controls', return_value=(
                {'availableObjects': [available]}, [phase], [phase])))
            stack.enter_context(patch.object(completed, 'validate_current'))
            stack.enter_context(patch.object(completed, '_inventory_revision', return_value='a' * 40))
            stack.enter_context(patch.object(completed, 'observe_source', return_value=({}, [], {'source': 1})))
            stack.enter_context(patch.object(completed, 'observe_original', return_value=({}, [], {'original': 1})))
            stack.enter_context(patch.object(completed, '_contract_files'))
            def validate(value):
                return completed.validate_extension(spec, value, {'signer_commit': 'a' * 40},
                    root=Path.cwd(), revision='a' * 40, frozen={}, token='synthetic')
            self.assertEqual(spec, validate(proof)['extension']['spec'])
            for altered in ({**member, 'bytes': 0}, {**member, 'bytes': 8 * 1024**3 + 1},
                            {**member, 'relativePath': 'another/' + member['relativePath']},
                            {**member, 'sha256': sha256_bytes(b'wrong')}):
                with self.subTest(altered=altered), self.assertRaises(ValueError):
                    validate({**proof, 'members': [altered]})
            with self.assertRaises(ValueError):
                validate({**proof, 'originals': [{'original': 2}]})
            spec['schemaVersion'] = 2
            with self.assertRaisesRegex(ValueError, 'consumed object'):
                validate({**proof, 'schemaVersion': 2, 'specSha256': sha256_bytes(canonical_json_bytes(spec))})

    def test_consumption_fetches_only_native_package_member_from_its_original_upload(self):
        for component, phase, target in (('sdk-ios', 'package', 'ios'),
                ('javascript', 'package', 'node'), ('csharp', 'binary', 'desktop')):
            with self.subTest(component=component):
                self.check_consumption_from_original(component, phase, target)

    def check_consumption_from_original(self, component, phase_name, target_name):
        import io
        import zipfile
        import reuse_qualification as native
        from contextlib import contextmanager
        from products.restore import object_relative_path
        receipt = deepcopy(self.receipt)
        receipt.update(component=component, phase=phase_name, target=target_name)
        receipt['buildKey'] = compute_build_key(**{field: receipt[field] for field in (*completed.IDENTITY, 'inputs')})
        body = b'only the requested package object'
        phase = {**{field: receipt[field] for field in completed.IDENTITY}, 'buildKey': receipt['buildKey'],
            'receiptSha256': sha256_bytes(canonical_json_bytes(receipt)), 'objectSha256': sha256_bytes(body)}
        name = 'shard/' + object_relative_path(phase['buildKey'], phase['receiptSha256'])
        member = {'relativePath': name, 'bytes': len(body), 'sha256': phase['objectSha256']}
        cap = native.CompletedFrozenReuse({'request': self.base['request'], 'expectedResult': {'phases': [phase]}},
            [receipt], native._COMPLETED_FROZEN, revision=receipt['producer']['commit'],
            sdk={'extension': {'spec': {'schemaVersion': 3, 'completedPhases': [phase]}, 'proof': {'members': [member]}}})
        original = {'id': 71}
        raw = io.BytesIO()
        with zipfile.ZipFile(raw, 'w') as archive:
            archive.writestr(name, body)
            archive.writestr('unrelated-evidence', b'never copied')
        @contextmanager
        def opened(artifact, token, **bounds):
            self.assertEqual(original, artifact)
            self.assertEqual({'max_bytes': 32 * 1024**3} if component == 'sdk-ios' else {}, bounds)
            with zipfile.ZipFile(raw) as archive:
                yield archive, None
        with tempfile.TemporaryDirectory() as temporary, \
                patch.object(native.CompletedFrozenReuse, 'check_consumer'), \
                patch.object(native.CompletedFrozenReuse, 'observe_extended_sdk', return_value=({'id': 999}, original, [])) as provenance, \
                patch('runtime_reference_archive.open_reference_archive', side_effect=opened) as fetch:
            target = Path(temporary).resolve() / 'object.zip'
            cap.capture_object(phase, target, plan={}, producer={}, trusted_workflow_sha='a' * 40, token='synthetic')
            self.assertEqual(body, target.read_bytes())
            self.assertEqual([target], list(target.parent.iterdir()))
            import hydrated_evidence
            with patch.dict(os.environ, {'CODEX_AGENT_HYDRATED_EVIDENCE': str(target.parent / 'cache')}), \
                    patch.object(hydrated_evidence, 'hosted_records', wraps=hydrated_evidence.hosted_records) as hosted:
                options = dict(plan={}, producer={}, trusted_workflow_sha='a' * 40, token='synthetic')
                cap.capture_object(phase, target.parent / 'cache-miss.zip', **options)
                self.assertEqual('save', hosted.call_args.args[0])
                self.assertEqual({'already_compressed': component == 'sdk-ios'}, hosted.call_args.kwargs)
                self.assertEqual(2, fetch.call_count)
                cap.capture_object(phase, target.parent / 'cache-hit.zip', **options)
                self.assertEqual(body, (target.parent / 'cache-hit.zip').read_bytes())
                self.assertEqual(2, fetch.call_count)
                self.assertEqual(3, provenance.call_count)
                provenance.side_effect = ValueError('original source changed')
                with self.assertRaisesRegex(ValueError, 'original source changed'):
                    cap.capture_object(phase, target.parent / 'wrong-source.zip', **options)
                self.assertFalse((target.parent / 'wrong-source.zip').exists())
                provenance.side_effect = None
                hydrated_evidence.blob(member).write_bytes(b'x' * len(body))
                with self.assertRaises(ValueError):
                    cap.capture_object(phase, target.parent / 'corrupt.zip', **options)
                self.assertEqual(2, fetch.call_count)  # Corruption cannot fall back and hide a failure.

    def test_v3_issuer_verifies_original_package_member_without_embedding_or_downloading_outer_upload(self):
        for component, phase, target in (('sdk-ios', 'package', 'ios'),
                ('javascript', 'package', 'node'), ('csharp', 'binary', 'desktop')):
            with self.subTest(component=component):
                self.setUp()
                self.check_v3_issuer_original_member(component, phase, target)

    def check_v3_issuer_original_member(self, component, phase_name, target):
        import io, json, zipfile
        from contextlib import contextmanager
        from types import SimpleNamespace
        import reuse_qualification as native
        import product_reuse as products
        from ci.tests.test_sdk_worker_collection import SdkWorkerCollectionTest
        fixture = SdkWorkerCollectionTest()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        _, _, shard, verified, _ = fixture.shard(phase_name, component=component, target=target)
        receipt = verified['receipt']
        del self.controls[self.receipt_path]
        folder = 'prior-failed-sdk-ios-package' if component == 'sdk-ios' else 'prior-failed-sdk'
        self.receipt_path = (f'product-resume-state/{folder}/{component}/{phase_name}/{target}/'
                            'original/shard/phase-receipt.json')
        phase = {**{key: receipt[key] for key in completed.IDENTITY},
            **{key: verified[key] for key in completed.OBJECT}, 'receiptPath': self.receipt_path}
        prefix = 'product-resume-state/'
        request = self.controls[prefix + 'reuse-wave-request.json']
        request['availableObjects'][-1] = {**phase, 'objectPath': 'deferred-package.zip'}
        request['phaseAuthorities'][-1] = {**{key: phase[key] for key in completed.IDENTITY},
            **{key: receipt['inputs'][key] for key in ('toolchainProfileDigest', 'flagsDigest', 'outputSchemaVersion')}}
        self.controls[prefix + 'reuse-wave-result.json']['phases'][-1] = {**phase, 'state': 'retained'}
        self.controls[self.receipt_path] = receipt
        self.spec['completedPhases'] = [phase]
        self.bind_controls()
        spec = json.loads((Path(__file__).parent / 'data/sdk-completed-resume.json').read_bytes())
        spec.update(schemaVersion=3, completedPhases=[phase], controls=self.spec['controls'])
        spec['source']['producer'] = self.controls[prefix + 'producer.json']
        spec['originals'] = [{**spec['originals'][0], **{key: phase[key] for key in completed.IDENTITY}}]
        parent = {'schemaVersion': 1}
        spec['parentProofSha256'] = sha256_bytes(canonical_json_bytes(parent))
        def zipped(files):
            raw = io.BytesIO()
            with zipfile.ZipFile(raw, 'w') as archive:
                for name, value in files.items(): archive.writestr(name, value)
            return raw.getvalue()
        source_files = {name: canonical_json_bytes(value) for name, value in self.controls.items()}
        package = component == 'sdk-ios'
        if package:
            del source_files[self.receipt_path]  # Ordinary P exports retain this only by reference.
        producer_row = next(row for row in spec['controls'] if row['relativePath'] == prefix + 'producer.json')
        alias = {**producer_row, 'relativePath': prefix + 'retained-producer.json'}
        source_prefix = self.receipt_path.removesuffix('/shard/phase-receipt.json')
        receipt_row = next(row for row in spec['controls'] if row['relativePath'] == self.receipt_path)
        source_files['runtime-original-references.json'] = canonical_json_bytes({
            'schemaVersion': 3, 'inventory': sorted([*spec['controls'], alias], key=lambda row: row['relativePath']),
            'sources': ([{'relativePath': source_prefix, 'kind': 'sdk-package', 'receipt': receipt,
                **{key: spec['originals'][0][key] for key in ('artifactId', 'artifactSha256')}}] if package else []),
            'references': sorted([{**alias, 'source': None, 'sourcePath': producer_row['relativePath']}] +
                ([{**receipt_row, 'source': source_prefix, 'sourcePath': 'shard/phase-receipt.json'}] if package else []),
                key=lambda row: row['relativePath'])})
        source = zipped(source_files)
        contract = zipped({row['relativePath']: b'{}' for row in spec['contractFiles']})
        for item, raw in ((spec['source'], source), (spec['contractControls'], contract)):
            item.update(artifactBytes=len(raw), artifactSha256=sha256_bytes(raw))
        name = 'shard/' + verified['objectPath']
        body = (shard / verified['objectPath']).read_bytes()
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            stack.enter_context(patch.object(native, '_fetch_completed_sdk', return_value={'proof': parent}))
            stack.enter_context(patch.object(completed, '_base', return_value=self.base))
            stack.enter_context(patch.object(completed, 'validate_current'))
            stack.enter_context(patch.object(completed, '_inventory_revision', return_value='a' * 40))
            stack.enter_context(patch.object(completed, '_contract_files'))
            stack.enter_context(patch.object(completed, 'observe_source', side_effect=lambda item, token, **kw:
                ({'name': 'controls'}, [{'run': {}}], {'source': item['artifactId']})))
            stack.enter_context(patch.object(completed, 'observe_original', return_value=({'id': 71}, [], {'original': 71})))
            def download(identifier, digest, artifact_name, producer, run, token, *, destination, max_bytes):
                raw = source if identifier == spec['source']['artifactId'] else contract
                self.assertEqual((sha256_bytes(raw), len(raw)), (digest, max_bytes))
                destination.write_bytes(raw)
            downloads = stack.enter_context(patch.object(products, '_download_contract_ci_upload', side_effect=download))
            for tampered in (False, True):
                @contextmanager
                def opened(artifact, token, **bounds):
                    self.assertEqual({'id': 71}, artifact)
                    self.assertEqual({'max_bytes': 32 * 1024**3} if package else {}, bounds)
                    with zipfile.ZipFile(io.BytesIO(zipped({name: b'x' * len(body) if tampered else body}))) as archive:
                        yield archive, SimpleNamespace(transferred=len(body))
                work = Path(temporary).resolve() / str(tampered)
                work.mkdir()
                with patch('runtime_reference_archive.open_reference_archive', opened):
                    if tampered:
                        with self.assertRaisesRegex(ValueError, 'immutable digest'):
                            completed.issue_extension(spec, work, root=fixture.repository, revision='a' * 40, frozen={}, token='synthetic')
                        self.assertFalse((work / 'completion.json').exists())
                    else:
                        report = completed.issue_extension(spec, work, root=fixture.repository, revision='a' * 40, frozen={}, token='synthetic')
                        result = json.loads((work / 'completion.json').read_bytes())
                        self.assertEqual(3, result['schemaVersion'])
                        self.assertEqual([{'relativePath': name, 'bytes': len(body), 'sha256': phase['objectSha256']}], result['members'])
                        self.assertEqual(len(source) + len(contract), report['downloadedOriginalBytes'])
                        self.assertEqual(len(body), report['originalMemberRangeBytes'])
                        self.assertEqual(0, report['productPhasesExecuted'])
                        self.assertEqual(2, downloads.call_count)

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
                patch('products.selection.phase_inventory_paths',
                      side_effect=lambda paths, instance: ['owned'] if 'owned' in paths else []), \
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
