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


def control_bytes(path, value):
    return value.encode('utf-8') if path == completed.SOURCE_PLAN else canonical_json_bytes(value)


def ordinary_spec():
    """Keep legacy intake regressions independent of the current issuer role."""
    import json
    spec = json.loads((Path(__file__).parent / 'data/sdk-completed-resume.json').read_bytes())
    for field in ('sourcePlan', 'reuseCompletion', 'reuseCompletionProofSha256', 'receiptObjects'):
        spec.pop(field, None)
    spec['stateRoot'] = 'product-resume-state'
    spec['source'].pop('referenceControlSha256', None)
    spec['source'].update(jobName='product-validation / product-resume',
                          artifactBytes=min(spec['source']['artifactBytes'], completed.LIMIT))
    spec['controls'] = [row for row in spec['controls'] if row['relativePath'] != completed.SOURCE_PLAN]
    return spec


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
        self.spec['controls'] = [{'relativePath': path, 'bytes': len(control_bytes(path, value)),
            'sha256': sha256_bytes(control_bytes(path, value))} for path, value in sorted(self.controls.items())]

    def test_native_sdk_capture_and_replay_keep_only_exact_controls(self):
        from sdk_phase import COMPACT_REPLAY_INSTANCES
        for instance in COMPACT_REPLAY_INSTANCES:
            component, phase, target = instance.component, instance.phase, instance.target
            with self.subTest(component=component, target=target):
                self._check_native_capture_and_replay(component, phase, target)

    def _check_native_capture_and_replay(self, component, phase, target):
        import reuse_qualification as native
        import sdk_ios_binary_recovery as recovery
        from products.restore import PHASE_SHARD_NAME
        receipt = deepcopy(self.receipt)
        receipt.update(component=component, phase=phase, target=target)
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
            from sdk_phase import completed_recovery_folder
            capture = root / completed_recovery_folder(recovery._javascript_instance(phase, component, target))
            def replay(authority):
                return recovery.replay_prior_javascript_package(capture, root,
                    plan={'repository': receipt['producer']['repository']}, consumer_producer=consumer,
                    trusted_workflow_sha='a' * 40, token='synthetic', environ={}, completed_frozen=authority,
                    phase=phase, component=component, target=target)
            with patch.object(recovery.products, '_runtime_prior_workflow_sha', return_value=None), \
                    patch.object(recovery, '_require_prior', side_effect=AssertionError('legacy failed-run gate')):
                self.assertEqual(records, replay(cap))
            self.assertEqual(2, observed.call_count)
            self.assertFalse((root / records[0]['objectPath']).exists())
            shard = capture / f'{component}/{phase}/{target}/original/shard'
            self.assertEqual({PHASE_SHARD_NAME, 'phase-receipt.json'}, {p.name for p in shard.iterdir()})
            with patch.object(recovery, '_capture_javascript_package', side_effect=ValueError('ordinary whole upload required')):
                with self.assertRaisesRegex(ValueError, 'exact native authority' if component in {'sdk-ios', 'sdk-core', 'sdk-android'} else 'whole upload required'):
                    replay(None)
            with self.assertRaisesRegex(ValueError, 'concrete native authority'):
                replay(object())
            (shard / 'phase-receipt.json').write_bytes(canonical_json_bytes({**receipt, 'productVersion': 'changed'}))
            with self.assertRaises(ValueError):
                replay(cap)

    def test_incremental_schema_and_parent_subject_are_fixed_before_inheritance(self):
        import json
        actual = json.loads((Path(__file__).parent / 'data/sdk-completed-resume.json').read_bytes())
        completed._spec(actual)
        spec = ordinary_spec()
        completed._spec(spec)
        planned = deepcopy(spec)
        planned['source']['jobName'] = 'product-validation / plan'
        completed._spec(planned)
        planned['source']['jobName'] = 'product-validation / unrelated'
        with self.assertRaisesRegex(ValueError, 'successful resume contract'):
            completed._spec(planned)
        proof = {key: {} for key in ('parentProof', 'controls', 'source', 'originals', 'members',
                                     'contractSource', 'contractFiles')}
        proof.update(schemaVersion=spec['schemaVersion'], kind='completed-sdk-reuse', issuerCommit='a' * 40,
                     specSha256=sha256_bytes(canonical_json_bytes(spec)))
        with patch('reuse_qualification._validate_completed_sdk') as inherit:
            with self.assertRaisesRegex(ValueError, 'approved native issuer or parent'):
                completed.validate_extension(spec, proof, {'signer_commit': 'a' * 40},
                    root=Path.cwd(), revision='a' * 40, frozen={}, token='synthetic')
            inherit.assert_not_called()

    def test_collected_inventory_acquires_only_exact_native_commit_and_tree(self):
        spec = ordinary_spec()
        with patch('sdk_handoff._ensure_pinned_git_commit') as acquire, \
                patch('products.inventory.run_git', return_value=spec['source']['producer']['tree']):
            self.assertEqual(spec['source']['inventoryCommit'],
                             completed._inventory_revision(spec, Path.cwd(), token='synthetic'))
            acquire.assert_called_once_with(Path.cwd(), spec['source']['inventoryCommit'],
                                            spec['source']['producer']['tree'], 'synthetic')
        with patch('sdk_handoff._ensure_pinned_git_commit', side_effect=ValueError('wrong tree')), \
                patch('products.inventory.run_git') as git:
            with self.assertRaisesRegex(ValueError, 'wrong tree'):
                completed._inventory_revision(spec, Path.cwd(), token='synthetic')
            git.assert_not_called()
        altered = deepcopy(spec)
        altered['source']['artifactBytes'] = completed.LIMIT + 1
        with self.assertRaisesRegex(ValueError, 'bounded original upload'):
            completed._spec(altered)

    def test_future_completion_pins_both_fixed_state_roles_and_upload_windows(self):
        import json
        import product_reuse
        spec = ordinary_spec()
        for role, prefix in (('product-validation / product-resume', 'codex-agent-product-resume-'),
                             ('product-validation / plan', 'codex-agent-planned-product-resume-'),
                             ('product-validation / sdk-collect-1', 'codex-agent-sdk-wave-1-state-'),
                             ('product-validation / sdk-collect-9', 'codex-agent-sdk-wave-9-state-'),
                             ('product-validation / sdk-collect-10', 'codex-agent-sdk-wave-10-state-'),
                             (completed._CORE_COLLECTOR, 'codex-agent-sdk-wave-11-state-'),
                             (completed._CORE_PACKAGE_COLLECTOR, 'codex-agent-sdk-wave-12-state-'),
                             ('product-validation / sdk-core-validation-wave / sdk-collect-13', 'codex-agent-sdk-wave-13-state-'),
                             ('product-validation / sdk-core-metadata-wave / sdk-collect-14', 'codex-agent-sdk-wave-14-state-'),
                             ('product-validation / sdk-android-binary-result / sdk-collect-15', 'codex-agent-sdk-wave-15-state-'),
                             ('product-validation / sdk-android-package-result / sdk-collect-16', 'codex-agent-sdk-wave-16-state-'),
                             ('product-validation / sdk-android-validation-result / sdk-collect-17', 'codex-agent-sdk-wave-17-state-'),
                             ('product-validation / sdk-android-metadata-result / sdk-collect-18', 'codex-agent-sdk-wave-18-state-')):
            source = {**spec['source'], 'jobName': role}
            job = dict(id=source['jobId'], name=role, status='completed', conclusion='success',
                       started_at='2026-01-01T01:00:00Z', completed_at='2026-01-01T01:02:00Z')
            suffix = f"-attempt-{source['producer']['runAttempt']}" if role in completed._COLLECTED_WAVES else ''
            artifact = dict(id=source['artifactId'], name=prefix + source['producer']['tree'] + suffix,
                            size_in_bytes=source['artifactBytes'], created_at='2026-01-01T01:01:00Z')
            with self.subTest(role=role), patch.object(product_reuse, '_observe_ci_producer_jobs',
                    return_value=[{'run': {'id': source['producer']['runId']}, 'jobs': [job]}]) as observe, \
                    patch.object(product_reuse, '_contract_ci_upload_metadata', return_value=artifact) as metadata:
                result = completed.observe_source(source, 'synthetic')
                self.assertEqual(artifact, result[0])
                self.assertEqual({'source': role}, observe.call_args.kwargs['jobs_by_phase'])
                child = {
                    completed._CORE_COLLECTOR: 'sdk-core-binary-validation',
                    completed._CORE_PACKAGE_COLLECTOR: 'sdk-core-package-validation',
                    'product-validation / sdk-core-validation-wave / sdk-collect-13': 'sdk-core-validation',
                    'product-validation / sdk-core-metadata-wave / sdk-collect-14': 'sdk-core-metadata-validation',
                    'product-validation / sdk-android-binary-result / sdk-collect-15': 'sdk-android-binary-validation',
                    'product-validation / sdk-android-package-result / sdk-collect-16': 'sdk-android-package-validation',
                    'product-validation / sdk-android-validation-result / sdk-collect-17': 'sdk-android-validation',
                    'product-validation / sdk-android-metadata-result / sdk-collect-18': 'sdk-android-metadata-validation',
                }.get(role)
                if child is not None:
                    self.assertEqual({'source': {'path': f'.github/workflows/{child}.yml',
                        'sha': source['workflowSha']}}, observe.call_args.kwargs['trusted_workflows_by_phase'])
                    self.assertNotIn('trusted_workflow_sha', observe.call_args.kwargs)
                else:
                    self.assertEqual(source['workflowSha'], observe.call_args.kwargs['trusted_workflow_sha'])
                self.assertEqual(artifact['name'], metadata.call_args.args[2])
                self.assertNotIn('native_job_ids_by_phase', observe.call_args.kwargs)
                self.assertEqual(result, completed.observe_source(source, 'synthetic', native_locator=result[2]))
                self.assertEqual({'source': source['jobId']}, observe.call_args.kwargs['native_job_ids_by_phase'])
                altered = deepcopy(result[2])
                altered['job']['completed_at'] = '2026-01-01T01:03:00Z'
                with self.assertRaisesRegex(ValueError, 'authenticated native locator'):
                    completed.observe_source(source, 'synthetic', native_locator=altered)
                altered['job']['id'] += 1
                observe.reset_mock()
                with self.assertRaisesRegex(ValueError, 'independently pinned job'):
                    completed.observe_source(source, 'synthetic', native_locator=altered)
                observe.assert_not_called()
                with self.assertRaisesRegex(ValueError, 'approved successful job'):
                    completed.observe_source({**source, 'jobId': source['jobId'] + 1}, 'synthetic')
                metadata.return_value = {**artifact, 'created_at': '2026-01-01T01:03:00Z'}
                with self.assertRaisesRegex(ValueError, 'job-attempt window'):
                    completed.observe_source(source, 'synthetic')
                for unsupported in ('product-validation / unrelated', 'product-validation / sdk-collect-13',
                                    'product-validation / sdk-android-binary-result / sdk-collect-16'):
                    observe.reset_mock()
                    with self.assertRaisesRegex(ValueError, 'fixed native state producer'):
                        completed.observe_source({**source, 'jobName': unsupported}, 'synthetic')
                    observe.assert_not_called()

    def test_collected_source_requires_exact_plan_manifest_role_root_and_bounded_controls(self):
        import json
        spec = ordinary_spec()
        for invalid in (None, {}, {**spec, 'source': []}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                completed._spec(invalid)
        spec['stateRoot'] = 'runtime-state'
        spec['source'].update(jobName='product-validation / sdk-collect-9',
            artifactBytes=6_500_000_000, referenceControlSha256='sha256:' + 'a' * 64)
        producer = spec['source']['producer']
        plan = {key: producer[key] for key in ('repository', 'event', 'pullRequest')}
        plan.update(validationCommit=producer['commit'], validationTree=producer['tree'], remoteBuildAuthorized=True)
        spec['sourcePlan'] = json.dumps(plan, indent=2) + '\n'
        raw = spec['sourcePlan'].encode('utf-8')
        self.assertNotEqual(canonical_json_bytes(plan), raw)
        spec['controls'].append({'relativePath': 'product-resume-inputs/plan/impact-plan.json',
                                'bytes': len(raw), 'sha256': sha256_bytes(raw)})
        completed._spec(spec)
        metadata = deepcopy(spec)
        metadata['source']['jobName'] = 'product-validation / sdk-collect-10'
        completed._spec(metadata)
        from products.restore import object_relative_path
        phase = metadata['completedPhases'][0]
        obj = {'relativePath': 'runtime-state/original-objects/' + object_relative_path(
            phase['buildKey'], phase['receiptSha256']), 'bytes': 12, 'sha256': phase['objectSha256']}
        phase['receiptPath'] = obj['relativePath'] + '/phase-receipt.json'
        metadata['receiptObjects'] = [obj]
        completed._spec(metadata)
        core = deepcopy(metadata)
        core['source']['jobName'] = completed._CORE_COLLECTOR
        completed._spec(core)
        for job in ('product-validation / sdk-collect-11',
                    'product-validation / sdk-core-package-wave / sdk-collect-11'):
            core['source']['jobName'] = job
            with self.assertRaises(ValueError): completed._spec(core)
        for mutate in (
                lambda value: value['receiptObjects'].append(deepcopy(obj)),
                lambda value: value['receiptObjects'][0].update(bytes=completed.LIMIT + 1),
                lambda value: value['receiptObjects'][0].update(sha256='sha256:' + '0' * 64),
                lambda value: value['receiptObjects'][0].update(relativePath='runtime-state/unrelated.zip'),
                lambda value: value['completedPhases'][0].update(receiptPath='runtime-state/other.json')):
            changed = deepcopy(metadata)
            mutate(changed)
            with self.assertRaises(ValueError): completed._spec(changed)
        reuse = {**deepcopy(spec), 'reuseCompletion': deepcopy(spec['parent']),
                 'reuseCompletionProofSha256': 'sha256:' + 'b' * 64}
        completed._spec(reuse)
        for change in (lambda value: value.pop('reuseCompletionProofSha256'),
                       lambda value: value.update(reuseCompletionProofSha256='unqualified'),
                       lambda value: value['reuseCompletion'].update(runId=producer['runId'],
                                                                     runAttempt=producer['runAttempt'])):
            altered = deepcopy(reuse)
            change(altered)
            with self.assertRaises(ValueError): completed._spec(altered)
        for change in (
            lambda value: value['source'].pop('referenceControlSha256'),
            lambda value: value['source'].update(referenceControlSha256='unqualified'),
            lambda value: value['source'].update(jobName='product-validation / sdk-collect-11'),
            lambda value: value.update(stateRoot='product-resume-state'),
            lambda value: value.update(schemaVersion=2),
            lambda value: value.update(sourcePlan=plan),
            lambda value: value.update(sourcePlan=json.dumps({**plan, 'validationCommit': 'f' * 40})),
            lambda value: value.update(sourcePlan=json.dumps({**plan, 'remoteBuildAuthorized': False})),
            lambda value: value.update(sourcePlan=canonical_json_bytes(plan).decode()),
            lambda value: value['controls'].pop(),
            lambda value: value['source'].update(artifactBytes=16 * 1024**3 + 1),
            lambda value: value['contractControls'].update(artifactBytes=completed.LIMIT + 1),
        ):
            altered = deepcopy(spec)
            change(altered)
            with self.subTest(altered=change), self.assertRaises(ValueError):
                completed._spec(altered)

    def test_native_original_locator_requires_independent_pin_and_exact_fresh_record(self):
        import product_reuse
        receipt = deepcopy(self.receipt)
        receipt['producer']['workflowPath'] = '.github/workflows/ci.yml'
        original = {'jobId': 71, 'workflowSha': 'a' * 40, 'artifactId': 72, 'artifactSha256': 'sha256:' + 'b' * 64}
        job = {'id': 71, 'name': 'product-validation / sdk-csharp-binary-desktop',
               'started_at': '2026-01-01T01:00:00Z', 'completed_at': '2026-01-01T01:02:00Z'}
        artifact = {'id': 72, 'created_at': '2026-01-01T01:01:00Z'}
        with patch.object(product_reuse, '_observe_ci_producer_jobs',
                return_value=[{'run': {}, 'jobs': [job]}]) as observe, \
                patch.object(product_reuse, '_contract_ci_upload_metadata', return_value=artifact):
            result = completed.observe_original(original, receipt, 'synthetic')
            self.assertNotIn('native_job_ids_by_phase', observe.call_args.kwargs)
            self.assertEqual(result, completed.observe_original(original, receipt, 'synthetic', native_locator=result[2]))
            self.assertEqual({'original': 71}, observe.call_args.kwargs['native_job_ids_by_phase'])
            altered = deepcopy(result[2])
            altered['artifact']['created_at'] = '2026-01-01T01:01:01Z'
            with self.assertRaisesRegex(ValueError, 'authenticated native locator'):
                completed.observe_original(original, receipt, 'synthetic', native_locator=altered)
            altered['job']['id'] += 1
            observe.reset_mock()
            with self.assertRaisesRegex(ValueError, 'independently pinned job'):
                completed.observe_original(original, receipt, 'synthetic', native_locator=altered)
            observe.assert_not_called()

    def test_core_original_requires_exact_nested_child_and_matrix_key(self):
        from products.registry import SDK_FACADE_TARGETS
        cases = [(phase, 'common') for phase in ('binary', 'package', 'metadata')]
        cases.extend(('validation', target) for target in SDK_FACADE_TARGETS)
        for phase, target in cases:
            with self.subTest(phase=phase, target=target):
                self.check_core_original(phase, target)

    def check_core_original(self, phase, target):
        import product_reuse
        receipt = deepcopy(self.receipt)
        receipt.update(component='sdk-core', phase=phase, target=target)
        receipt['producer']['workflowPath'] = '.github/workflows/ci.yml'
        receipt['buildKey'] = compute_build_key(**{field: receipt[field] for field in (*completed.IDENTITY, 'inputs')})
        original = {'jobId': 71, 'workflowSha': 'a' * 40, 'artifactId': 72,
                    'artifactSha256': 'sha256:' + 'b' * 64}
        name = f'product-validation / sdk-core-{phase}-wave / sdk-core-{phase}-{target}'
        job = {'id': 71, 'name': name + ' (' + receipt['buildKey'] + ', ...',
               'started_at': '2026-01-01T01:00:00Z', 'completed_at': '2026-01-01T01:02:00Z'}
        artifact = {'id': 72, 'created_at': '2026-01-01T01:01:00Z'}
        with patch.object(product_reuse, '_observe_ci_producer_jobs',
                return_value=[{'run': {}, 'jobs': [job]}]) as observe, \
                patch.object(product_reuse, '_contract_ci_upload_metadata', return_value=artifact) as metadata:
            completed.observe_original(original, receipt, 'synthetic')
            self.assertEqual({'upload_limit': 32 * 1024**3} if phase == 'metadata' else {},
                             metadata.call_args.kwargs)
            self.assertEqual({'original': name}, observe.call_args.kwargs['jobs_by_phase'])
            self.assertEqual({'original': receipt['buildKey']}, observe.call_args.kwargs['build_keys_by_phase'])
            child = 'sdk-core-validation' if phase == 'validation' else f'sdk-core-{phase}-validation'
            self.assertEqual({'original': {'path': f'.github/workflows/{child}.yml',
                'sha': original['workflowSha']}}, observe.call_args.kwargs['trusted_workflows_by_phase'])
            self.assertNotIn('trusted_workflow_sha', observe.call_args.kwargs)
            for invalid in (f'product-validation / sdk-core-{phase}-{target}', name + ' (sha256:' + '0' * 64 + ', ...'):
                job['name'] = invalid
                with self.assertRaises(ValueError): completed.observe_original(original, receipt, 'synthetic')

    def test_native_job_selection_cannot_run_before_subject_authentication(self):
        import reuse_qualification as native
        pins = {'artifactId': 1, 'artifactSha256': 'sha256:' + 'a' * 64, 'runId': 2,
                'runAttempt': 1, 'signerCommit': 'b' * 40, 'sourceCommit': 'c' * 40}
        with patch.object(native, '_fetch_qualification_archive',
                return_value=({}, {'completion.json': b'{}', 'bundle.jsonl': b'{}'})), \
                patch.object(native, '_authenticate_native_subject', side_effect=ValueError('bad signature')), \
                patch.object(native, '_validate_completed_sdk') as validate:
            with self.assertRaisesRegex(ValueError, 'bad signature'):
                native._fetch_completed_sdk(Path('unused'), pins, root=Path.cwd(),
                    revision='d' * 40, frozen={}, token='synthetic')
            validate.assert_not_called()

    def test_native_csharp_and_ios_controls_route_without_body_or_gate_replay(self):
        import reuse_qualification as native
        import sdk_ios_binary_recovery as recovery
        for component, phase, target in (('csharp', 'binary', 'desktop'), ('sdk-ios', 'binary', 'ios'), ('sdk-ios', 'package', 'ios')):
            receipt = deepcopy(self.receipt)
            receipt.update(component=component, phase=phase, target=target)
            receipt['buildKey'] = compute_build_key(**{field: receipt[field] for field in (*completed.IDENTITY, 'inputs')})
            record = {**{field: receipt[field] for field in completed.IDENTITY}, 'buildKey': receipt['buildKey'],
                'receiptSha256': sha256_bytes(canonical_json_bytes(receipt)), 'objectSha256': sha256_bytes(b'object')}
            cap = native.CompletedFrozenReuse({'request': self.base['request'], 'expectedResult': {'phases': [record]}},
                [receipt], native._COMPLETED_FROZEN, revision=receipt['producer']['commit'],
                sdk={'spec': {'completedPhase': record},
                     'extension': {'spec': {'schemaVersion': 3, 'completedPhases': [record]}, 'proof': {}}})
            consumer = {**receipt['producer'], 'runId': receipt['producer']['runId'] + 1}
            artifact = {'id': 71, 'name': 'synthetic-original', 'digest': sha256_bytes(b'original')}
            plan = {'repository': receipt['producer']['repository'], 'event': 'pull_request', 'remoteBuildAuthorized': True,
                    'pullRequest': receipt['producer']['pullRequest']}
            with self.subTest(component=component), tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
                root = Path(temporary).resolve()
                plan_path = root / 'plan.json'
                plan_path.write_bytes(canonical_json_bytes(plan))
                stack.enter_context(patch.object(native.CompletedFrozenReuse, 'observe_extended_sdk', return_value=({}, artifact, [])))
                stack.enter_context(patch.object(native.CompletedFrozenReuse, 'observe_sdk', return_value=({}, artifact, [])))
                stack.enter_context(patch.object(recovery.products, 'api_json', return_value={}))
                stack.enter_context(patch.object(recovery, '_require_prior', return_value=(7, 1)))
                stack.enter_context(patch.object(recovery.products, '_runtime_prior_workflow_sha', return_value='a' * 40))
                stack.enter_context(patch.object(recovery.products, '_validate_plan', return_value=plan))
                stack.enter_context(patch.object(recovery.products, '_contract_ci_upload_metadata', return_value=artifact))
                stack.enter_context(patch.object(recovery, 'locate_original_apple_upload', return_value={
                    'artifact_id': 71, 'artifact_sha256': artifact['digest']}))
                stack.enter_context(patch.object(recovery, '_capture_ios_original', side_effect=AssertionError('body/gate replay')))
                stack.enter_context(patch.object(recovery, '_capture_javascript_package', side_effect=AssertionError('body replay')))
                if component == 'sdk-ios' and phase == 'binary':
                    records = recovery.capture_completed_ios_binary(root / 'prior-failed-sdk', root,
                        completed_frozen=cap, plan=plan, producer=consumer, token='synthetic')
                else:
                    records = recovery.capture_completed_javascript(root, root, completed_frozen=cap, producer=consumer, token='synthetic')
                self.assertEqual(1, len(records))
                self.assertFalse((root / records[0]['objectPath']).exists())
                folder = ('prior-failed-sdk' if phase == 'binary' else 'prior-failed-sdk-ios-package') if component == 'sdk-ios' else 'prior-failed-sdk-csharp'
                def replay(authority):
                    options = dict(plan=plan, consumer_producer=consumer, trusted_workflow_sha='a' * 40,
                                   token='synthetic', environ={}, completed_frozen=authority, phase=phase)
                    if component == 'sdk-ios':
                        return recovery.replay_prior_ios_binary(root / folder, root,
                            plan_path=plan_path, repository_root=root, **options)
                    return recovery.replay_prior_javascript_package(root / folder, root, component=component, **options)
                with patch.object(recovery, '_require_prior', side_effect=AssertionError('legacy lookup')), \
                        patch.object(recovery, 'locate_original_apple_upload', side_effect=AssertionError('legacy locator')):
                    self.assertEqual(records, replay(cap))
                    observation = 'observe_sdk' if component == 'sdk-ios' and phase == 'binary' else 'observe_extended_sdk'
                    with patch.object(native.CompletedFrozenReuse, observation,
                                      return_value=({}, {**artifact, 'digest': 'sha256:' + 'f' * 64}, [])):
                        with self.assertRaisesRegex(ValueError, 'Completed SDK controls'):
                            replay(cap)
                    def late_mutation(*args, **kwargs):
                        consumer['runAttempt'] += 1
                        return {}, artifact, []
                    try:
                        with patch.object(native.CompletedFrozenReuse, observation, side_effect=late_mutation):
                            with self.assertRaisesRegex(ValueError, 'Completed SDK controls'):
                                replay(cap)
                    finally:
                        consumer['runAttempt'] -= 1
                    if component == 'sdk-ios':
                        old_event = plan['event']
                        try:
                            plan['event'] = 'merge_group'
                            plan_path.write_bytes(canonical_json_bytes(plan))
                            with self.assertRaisesRegex(ValueError, 'current consumer'):
                                replay(cap)
                        finally:
                            plan['event'] = old_event
                            plan_path.write_bytes(canonical_json_bytes(plan))
                if component == 'sdk-ios' and phase == 'package':
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

    def test_full_state_overlaps_only_native_sdk_reads_and_propagates_failures(self):
        import threading
        import reuse_qualification as native
        import sdk_ios_binary_recovery as recovery
        products = recovery.products
        instances = tuple(sorted(completed.PhaseInstanceId('sdk', 'javascript', phase, 'node')
                                 for phase in ('package', 'validation', 'metadata')))
        rows = [{**products._identity_record(instance), 'buildKey': 'sha256:' + 'a' * 64,
                 'receiptSha256': 'sha256:' + 'b' * 64, 'objectSha256': 'sha256:' + 'c' * 64}
                for instance in instances]
        cap = native.CompletedFrozenReuse({'request': self.base['request'], 'expectedResult': {'phases': rows}},
            [], native._COMPLETED_FROZEN, revision='a' * 40, sdk={
                'spec': {'completedPhase': {'product': 'sdk', 'component': 'sdk-ios', 'phase': 'binary', 'target': 'ios'}},
                'extension': {'spec': {'completedPhases': rows}, 'proof': {}}})
        producer = self.receipt['producer']
        plan = {'remoteBuildAuthorized': True, 'event': 'pull_request', 'validationCommit': producer['commit']}
        request = {'requested': [products._identity_record(i) for i in instances], 'sdkRuntimeSource': None,
                   'availableObjects': [{**row, 'objectPath': row['phase'] + '.zip'} for row in rows]}
        class AfterReplay(Exception): pass
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            root = Path(temporary).resolve()
            (root / 'producer.json').write_bytes(canonical_json_bytes(producer))
            for phase in ('package', 'validation', 'metadata'):
                (root / ('prior-failed-sdk-javascript' + ('' if phase == 'package' else '-' + phase))).mkdir()
            stack.enter_context(patch.object(native.CompletedFrozenReuse, 'check_request'))
            stack.enter_context(patch.object(products, '_validate_plan', return_value=plan))
            stack.enter_context(patch.object(products, '_consumer', return_value={'kind': 'ci', 'producer': producer}))
            stack.enter_context(patch.object(products, '_relocated_wave_control', return_value=request))
            stack.enter_context(patch.object(products, '_requested', return_value=instances))
            stack.enter_context(patch.object(products, '_versions', return_value={'sdk': '0.2.0', 'runtime-release': '0.2.0'}))
            stack.enter_context(patch.object(products, 'sdk_runtime_source', return_value=None))
            stack.enter_context(patch.object(products, '_dependency_closure', side_effect=lambda selected, **_:
                () if selected[0].product == 'contract' else instances))
            stack.enter_context(patch.object(products, '_authorities', return_value=([], None)))
            after = stack.enter_context(patch.object(products, '_capture_completed_contract_handoff', side_effect=AfterReplay))
            barrier = threading.Barrier(3)
            seen = []
            def replay(*args, phase='package', **kwargs):
                self.assertIsNotNone(products._CI_OBSERVATIONS.get())
                if kwargs.get('completed_frozen') is not None: barrier.wait(timeout=5)
                seen.append(phase)
                return [next(row for row in request['availableObjects'] if row['phase'] == phase)]
            def run(authority):
                products._verified_product_state(root / 'plan.json', root, root, root,
                    {'GITHUB_TOKEN': 'synthetic'}, None, sdk_original_workflow_sha='a' * 40, completed_frozen=authority)
            with patch.object(recovery, 'replay_prior_javascript_package', side_effect=replay):
                with self.assertRaises(AfterReplay): run(cap)
                self.assertEqual({'package', 'validation', 'metadata'}, set(seen))
                seen.clear()
                with patch('products.restore.bounded_verify', side_effect=AssertionError('ordinary parallel recovery')):
                    with self.assertRaises(AfterReplay): run(None)
                self.assertEqual(['package', 'validation', 'metadata'], seen)
            after.reset_mock()
            with patch.object(recovery, 'replay_prior_javascript_package', side_effect=ValueError('changed original')):
                with self.assertRaisesRegex(ValueError, 'changed original'): run(cap)
            after.assert_not_called()

    def test_large_native_package_member_is_bound_to_its_original_only_in_v3(self):
        import json
        import reuse_qualification as native
        from products.restore import object_relative_path
        spec = ordinary_spec()
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
            inventory = stack.enter_context(patch.object(completed, '_inventory_revision', return_value='a' * 40))
            observed_source = stack.enter_context(patch.object(completed, 'observe_source', return_value=({}, [], {'source': 1})))
            stack.enter_context(patch.object(completed, 'observe_original', return_value=({}, [], {'original': 1})))
            stack.enter_context(patch.object(completed, '_contract_files'))
            def validate(value):
                return completed.validate_extension(spec, value, {'signer_commit': 'a' * 40},
                    root=Path.cwd(), revision='a' * 40, frozen={}, token='synthetic')
            self.assertEqual(spec, validate(proof)['extension']['spec'])
            inventory.assert_called_once_with(spec, Path.cwd(), token='synthetic')
            inventory.reset_mock()
            observed_source.side_effect = ValueError('source no longer successful')
            with self.assertRaisesRegex(ValueError, 'source no longer successful'):
                validate(proof)
            inventory.assert_not_called()
            observed_source.side_effect = None
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
                ('javascript', 'package', 'node'), ('csharp', 'binary', 'desktop'),
                ('sdk-core', 'metadata', 'common')):
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
            self.assertEqual({'max_bytes': 32 * 1024**3, 'max_members': 65_536}
                             if (component, phase_name) == ('sdk-core', 'metadata') else
                             {'max_bytes': 32 * 1024**3} if component == 'sdk-ios' else {}, bounds)
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
                ('javascript', 'package', 'node'), ('csharp', 'binary', 'desktop'),
                ('sdk-core', 'metadata', 'common')):
            with self.subTest(component=component):
                self.setUp()
                self.check_v3_issuer_original_member(component, phase, target)

    def test_collected_issuer_reads_only_pinned_controls_and_rejects_failed_state_before_objects(self):
        for component, phase, target, wave in (('javascript', 'package', 'node', 1),
                ('csharp', 'binary', 'desktop', 19),
                ('sdk-ios', 'package', 'ios', 5),
                ('sdk-ios', 'package', 'ios', 9),
                ('sdk-ios', 'validation', 'ios-arm64', 9), ('sdk-ios', 'metadata', 'ios', 10),
                ('sdk-core', 'binary', 'common', 11), ('sdk-core', 'package', 'common', 12),
                ('sdk-core', 'metadata', 'common', 14),
                ('sdk-android', 'binary', 'android', 15), ('sdk-android', 'package', 'android', 16),
                ('sdk-android', 'validation', 'android', 17), ('sdk-android', 'metadata', 'android', 18)):
            with self.subTest(phase=phase):
                self.setUp()
                self.check_v3_issuer_original_member(component, phase, target, collected=True, collected_wave=wave)

    def test_large_package_receipt_object_keeps_exact_identity_and_dedicated_replay(self):
        from products.restore import object_relative_path
        from sdk_phase import COMPACT_REPLAY_INSTANCES
        self.assertNotIn(completed.IOS_PACKAGE, COMPACT_REPLAY_INSTANCES)
        self.assertEqual(5, completed._COLLECTED_WAVES['product-validation / sdk-collect-5'])
        phase = deepcopy(self.spec['completedPhases'][0])
        phase.update(product='sdk', component='sdk-ios', phase='package', target='ios')
        path = 'runtime-state/original-objects/' + object_relative_path(phase['buildKey'], phase['receiptSha256'])
        phase['receiptPath'] = path + '/phase-receipt.json'
        obj = {'relativePath': path, 'bytes': 8 * 1024**3, 'sha256': phase['objectSha256']}
        spec = {'stateRoot': 'runtime-state', 'completedPhases': [phase], 'receiptObjects': [obj]}
        self.assertEqual({phase['receiptPath']: (obj, phase)}, completed._receipt_objects(spec))
        for change in (lambda: obj.update(bytes=8 * 1024**3 + 1),
                       lambda: phase.update(phase='validation'),
                       lambda: obj.update(sha256='sha256:' + '0' * 64)):
            before_phase, before_object = deepcopy(phase), deepcopy(obj)
            change()
            with self.assertRaises(ValueError): completed._receipt_objects(spec)
            phase.clear(); phase.update(before_phase)
            obj.clear(); obj.update(before_object)

    def test_collected_issuer_reuses_native_object_without_any_object_transfer(self):
        self.check_v3_issuer_original_member('sdk-ios', 'package', 'ios', collected=True, reused=True)
        for phase, wave in (('binary', 15), ('package', 16), ('validation', 17), ('metadata', 18)):
            self.setUp()
            self.check_v3_issuer_original_member('sdk-android', phase, 'android',
                collected=True, collected_wave=wave, reused=True)

    def test_android_maven_object_bound_is_scoped_not_a_json_limit_change(self):
        from products.registry import PhaseInstanceId
        from products.restore import object_relative_path
        for phase in ('binary', 'package'):
            selected = deepcopy(self.spec['completedPhases'][0])
            selected.update(product='sdk', component='sdk-android', phase=phase, target='android')
            path = 'runtime-state/original-objects/' + object_relative_path(selected['buildKey'], selected['receiptSha256'])
            selected['receiptPath'] = path + '/phase-receipt.json'
            obj = {'relativePath': path, 'bytes': 512 * 1024 * 1024, 'sha256': selected['objectSha256']}
            spec = {'stateRoot': 'runtime-state', 'completedPhases': [selected], 'receiptObjects': [obj]}
            self.assertEqual({selected['receiptPath']: (obj, selected)}, completed._receipt_objects(spec))
            obj['bytes'] += 1
            with self.assertRaises(ValueError):
                completed._receipt_objects(spec)
            obj['bytes'] -= 1
            for field, value in (('phase', 'validation'), ('target', 'common'), ('component', 'sdk-core')):
                original = selected[field]
                selected[field] = value
                with self.assertRaises(ValueError):
                    completed._receipt_objects(spec)
                selected[field] = original
        self.assertEqual(16 * 1024 * 1024, completed.LIMIT)
        self.assertEqual(completed.LIMIT, completed._object_limit(
            PhaseInstanceId('sdk', 'sdk-android', 'metadata', 'android')))

    def test_reused_members_require_exact_native_subject_parent_and_original_identity(self):
        parent = {'schemaVersion': 1}
        phase = self.spec['completedPhases'][0]
        member = {'relativePath': 'synthetic member', 'bytes': 8, 'sha256': phase['objectSha256']}
        spec = {'parent': {'artifactId': 7}, 'parentProofSha256': sha256_bytes(canonical_json_bytes(parent))}
        prior = {'proof': parent, 'extension': {'spec': {'schemaVersion': 3, 'parent': spec['parent'],
            'completedPhases': [deepcopy(phase)]}, 'proof': {'members': [member],
            'originals': [{'original': 71}], 'controls': deepcopy(self.controls)}}}
        spec['reuseCompletionProofSha256'] = sha256_bytes(canonical_json_bytes(prior['extension']['proof']))
        self.assertEqual({completed._identity(phase): (member, {'original': 71})},
            completed._qualified_members(spec, prior, [phase], [self.receipt]))
        for case in ('subject', 'parent', 'base', 'object', 'receipt', 'dropped', 'omitted-member', 'no-native'):
            candidate, pins, selected = deepcopy(prior), deepcopy(spec), [phase]
            if case == 'subject': pins['reuseCompletionProofSha256'] = sha256_bytes(b'wrong subject')
            elif case == 'parent': candidate['extension']['spec']['parent'] = {'artifactId': 8}
            elif case == 'base': candidate['proof'] = {'schemaVersion': 2}
            elif case == 'object': candidate['extension']['spec']['completedPhases'][0]['objectSha256'] = sha256_bytes(b'other')
            elif case == 'receipt': candidate['extension']['proof']['controls'][self.receipt_path]['productVersion'] = '9.0.0'
            elif case == 'dropped': selected = []
            elif case == 'omitted-member': candidate['extension']['proof']['members'] = []
            elif case == 'no-native': candidate.pop('extension')
            if case not in ('subject', 'no-native'):
                pins['reuseCompletionProofSha256'] = sha256_bytes(canonical_json_bytes(candidate['extension']['proof']))
            with self.subTest(case=case), self.assertRaises(ValueError):
                completed._qualified_members(pins, candidate, selected, [self.receipt])

    def check_v3_issuer_original_member(self, component, phase_name, target, *, collected=False, reused=False,
                                      collected_wave=9):
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
        embedded = collected and (phase_name == 'metadata' or component == 'sdk-core' or collected_wave == 5)
        if embedded:
            source_object = 'runtime-state/original-objects/' + verified['objectPath']
            self.receipt_path = source_object + '/phase-receipt.json'
        if collected and phase_name == 'validation':
            self.receipt_path = self.receipt_path.replace('product-resume-state/', 'runtime-state/', 1)
        phase = {**{key: receipt[key] for key in completed.IDENTITY},
            **{key: verified[key] for key in completed.OBJECT}, 'receiptPath': self.receipt_path}
        prefix = 'runtime-state/' if collected else 'product-resume-state/'
        if collected:
            for name in ('reuse-wave-request.json', 'reuse-wave-result.json', 'producer.json'):
                self.controls[prefix + name] = self.controls.pop('product-resume-state/' + name)
        request = self.controls[prefix + 'reuse-wave-request.json']
        request['availableObjects'][-1] = {**phase, 'objectPath': 'deferred-package.zip'}
        request['phaseAuthorities'][-1] = {**{key: phase[key] for key in completed.IDENTITY},
            **{key: receipt['inputs'][key] for key in ('toolchainProfileDigest', 'flagsDigest', 'outputSchemaVersion')}}
        self.controls[prefix + 'reuse-wave-result.json']['phases'][-1] = {**phase, 'state': 'retained'}
        self.controls[self.receipt_path] = receipt
        if collected:
            producer = self.controls[prefix + 'producer.json']
            plan = {key: producer[key] for key in ('repository', 'event', 'pullRequest')}
            plan.update(validationCommit=producer['commit'], validationTree=producer['tree'], remoteBuildAuthorized=True)
            plan_text = json.dumps(plan, indent=2) + '\n'
            self.controls[completed.SOURCE_PLAN] = plan_text
        self.spec['completedPhases'] = [phase]
        self.bind_controls()
        spec = ordinary_spec()
        spec.update(schemaVersion=3, completedPhases=[phase], controls=self.spec['controls'])
        spec['source']['producer'] = self.controls[prefix + 'producer.json']
        if collected:
            spec.update(stateRoot='runtime-state', sourcePlan=plan_text)
            spec['source'].update(jobName=next(job for job, wave in completed._COLLECTED_WAVES.items()
                                              if wave == collected_wave),
                                  referenceControlSha256='sha256:' + 'a' * 64)
        if embedded:
            spec['receiptObjects'] = [{'relativePath': source_object,
                'bytes': (shard / verified['objectPath']).stat().st_size, 'sha256': verified['objectSha256']}]
        spec['originals'] = [{**spec['originals'][0], **{key: phase[key] for key in completed.IDENTITY}}]
        parent = {'schemaVersion': 1}
        spec['parentProofSha256'] = sha256_bytes(canonical_json_bytes(parent))
        def zipped(files):
            raw = io.BytesIO()
            with zipfile.ZipFile(raw, 'w') as archive:
                for name, value in files.items(): archive.writestr(name, value)
            return raw.getvalue()
        source_files = {name: control_bytes(name, value) for name, value in self.controls.items()}
        package = component == 'sdk-ios' and phase_name == 'package'
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
        if collected:
            spec['source']['artifactBytes'] = 6_500_000_000
        name = 'shard/' + verified['objectPath']
        body = (shard / verified['objectPath']).read_bytes()
        previous = None
        if reused:
            spec['reuseCompletion'] = {'artifactId': 8, 'artifactSha256': 'sha256:' + 'c' * 64,
                'runId': 2, 'runAttempt': 1, 'signerCommit': 'b' * 40, 'sourceCommit': 'b' * 40}
            previous = {'proof': parent, 'extension': {'spec': {'schemaVersion': 3,
                'parent': spec['parent'], 'completedPhases': [phase]}, 'proof': {
                'controls': deepcopy(self.controls), 'originals': [{'original': 71}],
                'members': [{'relativePath': name, 'bytes': len(body), 'sha256': phase['objectSha256']}]}}}
            spec['reuseCompletionProofSha256'] = sha256_bytes(canonical_json_bytes(previous['extension']['proof']))
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            def native_completion(destination, pins, **arguments):
                if reused and pins == spec['reuseCompletion']:
                    self.assertEqual('previous', destination.name)
                    return previous
                self.assertEqual(spec['parent'], pins)
                return {'proof': parent}
            fetched = stack.enter_context(patch.object(native, '_fetch_completed_sdk', side_effect=native_completion))
            stack.enter_context(patch.object(completed, '_base', return_value=self.base))
            stack.enter_context(patch.object(completed, 'validate_current'))
            stack.enter_context(patch.object(completed, '_inventory_revision', return_value='a' * 40))
            stack.enter_context(patch.object(completed, '_contract_files'))
            stack.enter_context(patch.object(completed, 'observe_source', side_effect=lambda item, token, **kw:
                ({'name': 'controls'}, [{'run': {}}], {'source': item['artifactId']})))
            observe_original = stack.enter_context(patch.object(completed, 'observe_original',
                return_value=({'id': 71}, [], {'original': 71})))
            if collected:
                ensure_commit = stack.enter_context(patch('sdk_handoff._ensure_observed_sdk_commit'))
                validate_plan = stack.enter_context(patch.object(products, '_validate_plan', return_value=plan))
                def capture(actual_plan, raw_plan, producer, base, destination, *, trusted_workflow_sha, token, wanted):
                    self.assertEqual((plan, plan_text.encode('utf-8'), spec['source']['producer']),
                                     (actual_plan, raw_plan, producer))
                    self.assertEqual({'artifactId': spec['source']['artifactId'],
                        'artifactSha256': spec['source']['artifactSha256'], 'stateWave': 0, 'sdkStateWave': collected_wave,
                        'referenceControlSha256': spec['source']['referenceControlSha256'],
                        'runAttempt': producer['runAttempt']}, base)
                    expected = {row['relativePath']: row for row in spec['controls']
                                if not embedded or row['relativePath'] != self.receipt_path}
                    expected.update({row['relativePath']: row for row in spec.get('receiptObjects', [])})
                    self.assertEqual(expected, wanted)
                    self.assertEqual(spec['source']['workflowSha'], trusted_workflow_sha)
                    for path, value in self.controls.items():
                        if embedded and path == self.receipt_path:
                            target = destination / source_object
                            target.parent.mkdir(parents=True, exist_ok=True)
                            target.write_bytes(body)
                            continue
                        target = destination / path
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(control_bytes(path, value))
                    return {'artifact': {'name': 'controls'}, 'rangeBytes': 600,
                            'referenceBase': {'originalReferenceSources': [{'rangeBytes': 100}]}}
                capture_controls = stack.enter_context(patch.object(products, '_capture_runtime_reference_members',
                    side_effect=capture))
            def download(identifier, digest, artifact_name, producer, run, token, *, destination, max_bytes):
                raw = source if identifier == spec['source']['artifactId'] else contract
                self.assertEqual((sha256_bytes(raw), len(raw)), (digest, max_bytes))
                destination.write_bytes(raw)
            downloads = stack.enter_context(patch.object(products, '_download_contract_ci_upload', side_effect=download))
            for tampered in ((False,) if reused else (False, True)):
                @contextmanager
                def opened(artifact, token, **bounds):
                    self.assertFalse(reused, 'Native-qualified objects must not be downloaded again')
                    self.assertEqual({'id': 71}, artifact)
                    self.assertEqual({'max_bytes': 32 * 1024**3, 'max_members': 65_536}
                                     if (component, phase_name) == ('sdk-core', 'metadata') else
                                     {'max_bytes': 32 * 1024**3} if package else {}, bounds)
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
                        self.assertEqual(len(contract) + (0 if collected else len(source)), report['downloadedOriginalBytes'])
                        self.assertEqual(700 if collected else 0, report['sourceControlRangeBytes'])
                        self.assertEqual(0 if reused else len(body), report['originalMemberRangeBytes'])
                        self.assertEqual(len(body) if reused else 0, report['reusedObjectBytes'])
                        self.assertEqual(0 if reused else len(body), report['verifiedObjectBytes'])
                        self.assertEqual(0, report['productPhasesExecuted'])
                        self.assertEqual(1 if collected else 2, downloads.call_count)
                        if collected:
                            ensure_commit.assert_called_once_with(fixture.repository, spec['source']['producer'], 'synthetic')
                            self.assertEqual(spec['source']['producer']['commit'],
                                             validate_plan.call_args.kwargs['expected_revision'])
                            self.assertEqual(1, capture_controls.call_count)
            if reused:
                for case in ('native-signature', 'locator'):
                    work = Path(temporary).resolve() / case
                    work.mkdir()
                    observe_original.reset_mock()
                    downloads.reset_mock()
                    def rejected(destination, pins, **arguments):
                        if pins == spec['reuseCompletion'] and case == 'native-signature':
                            raise ValueError('bad native signature')
                        return native_completion(destination, pins, **arguments)
                    fetched.side_effect = rejected
                    if case == 'locator': observe_original.return_value = {'id': 71}, [], {'original': 72}
                    with patch('runtime_reference_archive.open_reference_archive', side_effect=AssertionError('body read')), \
                            self.assertRaisesRegex(ValueError, 'native signature|freshly observed original locator'):
                        completed.issue_extension(spec, work, root=fixture.repository,
                            revision='a' * 40, frozen={}, token='synthetic')
                    if case == 'native-signature': observe_original.assert_not_called()
                    downloads.assert_not_called()
                    self.assertFalse((work / 'completion.json').exists())
                fetched.side_effect = native_completion
                observe_original.return_value = {'id': 71}, [], {'original': 71}
            if collected:
                original_plan_text = self.controls[completed.SOURCE_PLAN]
                self.controls[completed.SOURCE_PLAN] += '\n'
                observe_original.reset_mock()
                downloads.reset_mock()
                work = Path(temporary).resolve() / 'changed-plan-bytes'
                work.mkdir()
                with patch('runtime_reference_archive.open_reference_archive', side_effect=AssertionError('body read')):
                    with self.assertRaisesRegex(ValueError, 'exact original bytes'):
                        completed.issue_extension(spec, work, root=fixture.repository,
                            revision='a' * 40, frozen={}, token='synthetic')
                observe_original.assert_not_called()
                downloads.assert_not_called()
                self.assertFalse((work / 'completion.json').exists())
                self.controls[completed.SOURCE_PLAN] = original_plan_text
                self.controls[prefix + 'reuse-wave-result.json']['phases'][-1]['state'] = 'failed'
                self.bind_controls()
                spec['controls'] = self.spec['controls']
                observe_original.reset_mock()
                downloads.reset_mock()
                work = Path(temporary).resolve() / 'failed-state'
                work.mkdir()
                with patch('runtime_reference_archive.open_reference_archive', side_effect=AssertionError('body read')):
                    with self.assertRaisesRegex(ValueError, 'successful original scope'):
                        completed.issue_extension(spec, work, root=fixture.repository,
                            revision='a' * 40, frozen={}, token='synthetic')
                observe_original.assert_not_called()
                downloads.assert_not_called()
                self.assertFalse((work / 'completion.json').exists())

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
            lambda: self.controls['product-resume-state/reuse-wave-result.json']['phases'][-1].update(state='failed'),
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
