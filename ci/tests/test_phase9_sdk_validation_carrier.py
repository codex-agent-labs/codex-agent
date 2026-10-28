"""Bounded carrier controls; fixtures are not hosted or product evidence."""
import ast
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from ci.tests import phase9_sdk_validation as carrier
from products.inventory import canonical_json_bytes, sha256_bytes
from products.receipt import compute_build_key
from products.selection import ALL_INSTANCES, phase_inventory_paths


class SdkCarrierTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        inputs = dict(inventory=[], phaseInputDigest=sha256_bytes(canonical_json_bytes([])),
            versionIdentity='0.8.0', upstreamArtifacts=[], toolchainProfileDigest='sha256:' + '1' * 64,
            flagsDigest='sha256:' + '2' * 64, outputSchemaVersion=1)
        self.plan = dict(schemaVersion=1, product='sdk', component='python', phase='validation',
            target='linux-arm64', productVersion='0.8.0', inputs=inputs,
            buildKey=compute_build_key(product='sdk', component='python', phase='validation',
                                      target='linux-arm64', inputs=inputs))
        self.spec = dict(schemaVersion=1, purpose=carrier.PURPOSE,
            source=dict(commit='a' * 40, tree='b' * 40,
                        bundles=[dict(relativePath='source.bundle', head='a' * 40)]),
            checkpoint=dict(sha256='sha256:' + '0' * 64, retainedKeys=[]),
            hosts={'linux-arm64': dict(files=[dict(relativePath='source.bundle', bytes=1,
                sha256='sha256:' + '3' * 64)], bindings={}, requests={}, paths={}, originals=[],
                plans={'python': self.plan})})

    def select(self, spec=None, expected=None):
        path = self.root / 'selection.json'
        raw = canonical_json_bytes(spec or self.spec); path.write_bytes(raw)
        return carrier.selection(path, expected or sha256_bytes(raw), 'linux-arm64')

    def test_pin_and_missing_key_are_both_required(self):
        self.assertEqual(self.plan, self.select()[1]['plans']['python'])
        with self.assertRaisesRegex(ValueError, 'selection changed'):
            self.select(expected='sha256:' + '9' * 64)
        spec = copy.deepcopy(self.spec)
        spec['checkpoint']['retainedKeys'] = [self.plan['buildKey']]
        with self.assertRaisesRegex(ValueError, 'already-retained'):
            self.select(spec)
        spec = copy.deepcopy(self.spec)
        spec['hosts']['linux-arm64']['plans']['python']['target'] = 'linux-x64'
        with self.assertRaisesRegex(ValueError, 'selected missing'):
            self.select(spec)

    def test_intake_rejects_duplicate_unsafe_and_conflicting_members(self):
        for names in (['source.bundle', 'source.bundle'], ['../source.bundle']):
            spec = copy.deepcopy(self.spec)
            spec['hosts']['linux-arm64']['files'] = [dict(relativePath=n, bytes=1,
                sha256='sha256:' + '3' * 64) for n in names]
            with self.subTest(names=names), self.assertRaises(ValueError):
                self.select(spec)
        spec = copy.deepcopy(self.spec)
        spec['hosts']['linux-arm64']['files'].append(dict(relativePath='z', bytes=2,
            sha256='sha256:' + '3' * 64))
        with self.assertRaisesRegex(ValueError, 'conflicting lengths'):
            self.select(spec)

    def test_rebinding_keeps_original_and_rejects_unbound_absolute_paths(self):
        original = {'repository': '/original/source', 'nested': ['/original/package', '0.8.0']}
        before = copy.deepcopy(original)
        rebound = carrier.rebase(original, {'/original/source': str(self.root / 'source'),
                                           '/original/package': str(self.root / 'inputs/package')})
        self.assertEqual(before, original)
        carrier.confined_request(rebound, self.root)
        with self.assertRaisesRegex(ValueError, 'Unbound original path'):
            carrier.confined_request(original, self.root)
        with self.assertRaises(ValueError):
            carrier.member(self.root, '../outside')

    def test_original_control_bytes_cannot_be_rewritten_after_intake(self):
        (self.root / 'inputs').mkdir()
        p = self.root / 'inputs/receipt.json'
        raw = canonical_json_bytes({'original': True}); p.write_bytes(raw)
        host = {'files': [{'relativePath': 'receipt.json', 'bytes': len(raw), 'sha256': sha256_bytes(raw)}]}
        self.assertEqual({'original': True}, carrier.selected_json(self.root, host, 'inputs/receipt.json'))
        p.write_bytes(canonical_json_bytes({'original': False}))
        with self.assertRaisesRegex(ValueError, 'changed after intake'):
            carrier.selected_json(self.root, host, 'inputs/receipt.json')

    def test_retained_projection_preserves_all_authentication_calls(self):
        source = (carrier.ROOT / 'ci/sdk_native_validation_workflow.py').read_bytes()
        projected = carrier.native_projection(source)
        original, = [n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef)
                     and n.name == '_execute_validation']
        def calls(node):
            return [ast.dump(n, include_attributes=False) for n in ast.walk(node) if isinstance(n, ast.Call)]
        self.assertEqual(calls(original), calls(projected))
        namespace = {}; exec(compile(projected, '<reviewed native projection>', 'exec'), namespace)
        self.assertIn('_execute_validation', namespace)
        with self.assertRaisesRegex(ValueError, 'Exact reviewed'):
            carrier.native_projection(source.replace(b'"Fixed imported-only Gradle consumer;', b'"Changed Gradle consumer;'))

    def test_failed_first_consumer_does_not_block_an_authenticated_runtime_snapshot(self):
        # This is a routing-only unit fixture. The existing ten-pair reader is
        # mocked; neither a product phase nor a hosted qualification is claimed.
        source = self.root / 'source'
        (source / 'ci').mkdir(parents=True)
        original = carrier.ROOT / 'ci/sdk_native_validation_workflow.py'
        (source / 'ci/sdk_native_validation_workflow.py').write_bytes(original.read_bytes())
        tree = 'b' * 40
        retained = source / 'codex-agent-sdk/build/imported-native-wrapper-runtime-stages' / tree
        retained.mkdir(parents=True)
        qualification = source / 'build/phase9-sdk-host-validation' / tree / 'linux-arm64/runtime-reuse-qualification'
        qualification.mkdir(parents=True)
        controller = {'unitFixture': True}
        proof = dict(passed=True, controller=controller, sourceCommit='a' * 40, sourceTree=tree,
            target='linux-arm64', functionSha256='sha256:' + carrier.FUNCTION_SHA,
            excludedTasks=list(carrier.EXCLUDED), qualificationOnly=True)
        (qualification / 'result.json').write_bytes(canonical_json_bytes(proof))
        workflow = SimpleNamespace(__file__=str(original), _inventory=Mock(return_value=[]),
            _runtime_originals=Mock(return_value=[]), consumer_probe=Mock(return_value={'stage': 'unit-fixture'}))
        projected = ast.parse('def _execute_validation(plan, **arguments):\n    return consumer_probe(plan, **arguments)\n')
        arguments = dict(repository_root=source, producer={'commit': 'a' * 40, 'tree': tree},
            predecessor=Mock(), protected_inputs=[], runtime_stages=self.root / 'originals')
        with patch.object(carrier, 'native_projection', return_value=projected):
            result = carrier.native_execute(workflow, self.plan, arguments, self.root,
                self.root / 'result', controller)
        self.assertEqual('unit-fixture', result['stage'])
        workflow.consumer_probe.assert_called_once()
        workflow._runtime_originals.assert_called_once_with(retained, [], arguments['predecessor'])
        self.assertFalse((self.root / 'results').exists())  # No successful sibling raw existed.
        workflow.consumer_probe.reset_mock()
        workflow._runtime_originals.side_effect = ValueError('partial Runtime snapshot')
        with patch.object(carrier, 'native_projection', return_value=projected):
            with self.assertRaisesRegex(ValueError, 'partial Runtime snapshot'):
                carrier.native_execute(workflow, self.plan, arguments, self.root,
                    self.root / 'result', controller)
        workflow.consumer_probe.assert_not_called()

    def test_fixed_helper_binding_rejects_changed_execution_helpers(self):
        original = b'def command():\n    return "fixed"\ndef unrelated():\n    return 1\n'
        carrier.same_definitions(original.replace(b'return 1', b'return 2'), original, ['command'])
        with self.assertRaisesRegex(ValueError, 'dispatcher helper differs'):
            carrier.same_definitions(original.replace(b'"fixed"', b'"injected"'), original, ['command'])

    def test_carrier_and_test_own_zero_of_all_112_product_inputs(self):
        self.assertEqual(112, len(ALL_INSTANCES))
        for path in ('ci/tests/phase9_sdk_validation.py', 'ci/tests/test_phase9_sdk_validation_carrier.py'):
            self.assertFalse([instance for instance in ALL_INSTANCES if phase_inventory_paths([path], instance)])

    def test_election_matches_real_planner_native_cardinality_and_core_none(self):
        # Reuse planner-only fixtures; no signatures, host or product evidence.
        from ci.tests import test_product_plan as fixture
        from products.contract_projection import VerifiedContractProjection, _VERIFIED
        from products.sdk_runtime_content import (VerifiedNativeRuntimeProjection,
            _VERIFIED_NATIVE_RUNTIME, _native_contract_identity)
        from products.receipt import output_inventory_digest
        from products.inventory import load_canonical_json_bytes
        for component in ('python', 'sdk-core'):
            with self.subTest(component=component):
                identity = carrier.PhaseInstanceId('sdk', component, 'validation', 'macos-x64')
                fixture_identity = fixture.PhaseInstanceId(*('sdk', component, 'validation', 'macos-x64'))
                receipts = fixture.upstreams(fixture_identity)
                if component == 'python':
                    package = next(r for r in receipts if r['product'] == 'sdk')
                    original_package = fixture.plan(fixture.PhaseInstanceId('sdk', 'python', 'package', 'desktop'))
                    package.update(inputs=original_package['inputs'], buildKey=original_package['buildKey'])
                value = fixture.verified_projection(fixture_identity)
                contract = VerifiedContractProjection(load_canonical_json_bytes(value._canonical),
                    _VERIFIED, value._coverage)
                originals = {tuple(r[k] for k in ('product', 'component', 'phase', 'target')): {
                    'receipt': r, 'stage': self.root / 'stage', 'receiptPath': self.root / 'receipt'} for r in receipts}
                dependencies = carrier.native_runtime_validation_dependencies(identity)
                proofs = {d.target: VerifiedNativeRuntimeProjection(
                    canonical_json_bytes(originals[(d.product, d.component, d.phase, d.target)]['receipt']),
                    output_inventory_digest(originals[(d.product, d.component, d.phase, d.target)]['receipt']['outputs']),
                    _native_contract_identity(contract, d.target), _VERIFIED_NATIVE_RUNTIME) for d in dependencies}
                native = tuple(proofs[d.target] for d in dependencies) if dependencies else None
                arguments = dict(inventory=[fixture.file_record()], versions=fixture.VERSIONS,
                    upstream_receipts=receipts, toolchain_profile_digest=carrier.NOT_APPLICABLE_TOOLCHAIN_DIGEST,
                    flags_digest=carrier.NOT_APPLICABLE_FLAGS_DIGEST, contract_projection=contract)
                expected = carrier.plan_phase(identity, **arguments, native_runtime_projections=native)
                wrong = native[1:] if native else ()
                with self.assertRaisesRegex(ValueError, 'native Runtime projections'):
                    carrier.plan_phase(identity, **arguments, native_runtime_projections=wrong)
                request = {key: str(self.root / key) for key in ('contractMetadataReceipt', 'contractAttestation',
                    'contractAttestationSignature', 'contractPublicKey', 'contractPayload')}
                for name in ('variantBundles', 'variantAttestations', 'variantAttestationSignatures', 'variantPublicKeys'):
                    request[name] = {d.target: str(self.root / name / d.target) for d in dependencies}
                request['variantPhaseReceipts'] = {d.target: {'validation': str(self.root / d.target)} for d in dependencies}
                request['validationContractEvidence'] = {key: str(self.root / key) for key in
                    ('stageRoot', 'phaseReceipt', 'attestation', 'attestationSignature', 'publicKey')}
                host = {'paths': {'contractStage': 'inputs/contract', 'runtimeStages': 'inputs/runtime'},
                        'plans': {component: expected}}
                spec = {'source': {'commit': 'a' * 40}, 'checkpoint': {'retainedKeys': [r['buildKey'] for r in receipts]}}
                with patch.object(carrier, 'originals', return_value=originals), \
                        patch.object(carrier, 'read', return_value=request), \
                        patch.object(carrier, 'phase_git_inventory', return_value=arguments['inventory']), \
                        patch.object(carrier, 'git_product_versions', return_value=fixture.VERSIONS), \
                        patch('products.contract_projection.verify_contract_component_projection', return_value=contract), \
                        patch('products.sdk_runtime_content.verify_native_runtime_projection',
                            side_effect=lambda **kw: proofs[kw['target']]) as verify:
                    actual, _ = carrier.elect(self.root, spec, host, component, 'macos-x64')
                self.assertEqual(expected, actual)
                self.assertEqual([d.target for d in dependencies], [c.kwargs['target'] for c in verify.call_args_list])
                self.assertEqual(['macos-arm64', 'macos-x64'] if component == 'python' else [],
                                 [d.target for d in dependencies])

    def test_host_failure_precedes_any_intake(self):
        with patch.object(carrier, 'hosted_context', side_effect=ValueError('wrong host')), \
                patch.object(carrier, 'receive') as receive:
            with self.assertRaisesRegex(ValueError, 'wrong host'):
                carrier.prepare(self.root / 'missing.json', 'sha256:' + '0' * 64,
                    'linux-arm64', self.root / 'fresh', self.root / 'storage')
            receive.assert_not_called()

    def test_intake_batches_only_missing_objects_and_keeps_independent_files(self):
        from ci.tests.test_runtime_library_authorization import ImportedLfsTransportTest
        import runtime_phase10_library_caller as transport
        bodies = {sha256_bytes(f'sdk-intake-fixture-{i}'.encode()): f'sdk-intake-fixture-{i}'.encode()
                  for i in range(102)}
        records = [dict(relativePath=f'files/{i}', sha256=digest, bytes=len(raw))
                   for i, (digest, raw) in enumerate(bodies.items())]
        records.append(dict(records[0], relativePath='duplicate'))
        storage = self.root / 'storage'; storage.mkdir()
        first = records[0]['sha256']; (storage / first[7:]).write_bytes(bodies[first])
        requests = []
        def opened(request):
            requests.append(request)
            if request.get_method() == 'POST':
                self.assertEqual(transport._IMPORTED_LFS_ENDPOINT, request.full_url)
                self.assertTrue(request.get_header('Authorization').startswith('Basic '))
                query = json.loads(request.data)
                self.assertEqual('download', query['operation'])
                self.assertLessEqual(len(query['objects']), 100)
                self.assertNotIn(first[7:], [row['oid'] for row in query['objects']])
                rows = [ImportedLfsTransportTest().action(row['oid'], row['size']) for row in query['objects']]
                raw = canonical_json_bytes({'objects': rows})
            else:
                self.assertIsNone(request.get_header('Authorization'))
                digest = request.full_url.split('/media/', 1)[1].split('?', 1)[0]
                raw = bodies['sha256:' + digest]
            return ImportedLfsTransportTest.Response(raw, request.full_url)
        with patch.dict(os.environ, {'GH_TOKEN': 'unit-read-token'}), \
                patch.object(transport, '_imported_lfs_open', side_effect=opened), \
                patch.object(transport.subprocess, 'run', side_effect=AssertionError('No transport subprocess')):
            result = carrier.receive(records, self.root / 'inputs', storage)
        self.assertEqual(2, result['lfsBatchRequests'])
        self.assertEqual(101, result['lfsObjectRequests'])
        self.assertEqual(1, result['reusedCacheObjects'])
        self.assertEqual(0, result['transportSubprocesses'])
        self.assertEqual(sum(len(raw) for digest, raw in bodies.items() if digest != first), result['downloadedBytes'])
        for row in records:
            path = self.root / 'inputs' / row['relativePath']
            self.assertEqual(bodies[row['sha256']], path.read_bytes())
            self.assertEqual(1, path.stat().st_nlink)
            self.assertNotEqual(path.stat().st_ino, (storage / row['sha256'][7:]).stat().st_ino)
        (self.root / 'inputs/duplicate').write_bytes(b'changed independent fixture')
        self.assertEqual(bodies[first], (storage / first[7:]).read_bytes())
        with patch.dict(os.environ, {'GH_TOKEN': 'unit-read-token'}), \
                patch.object(transport, '_imported_lfs_open', side_effect=AssertionError('Cached bytes need no network')):
            result = carrier.receive(records, self.root / 'cached-inputs', storage)
            self.assertEqual(0, result['lfsBatchRequests'])
            self.assertEqual(0, result['downloadedBytes'])
            self.assertEqual(102, result['reusedCacheObjects'])
            (storage / first[7:]).write_bytes(b'x' * len(bodies[first]))
            with self.assertRaisesRegex(ValueError, 'Existing SDK cache object'):
                carrier.receive(records, self.root / 'rejected-inputs', storage)


if __name__ == '__main__':
    unittest.main()
