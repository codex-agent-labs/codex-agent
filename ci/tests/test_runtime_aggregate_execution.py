"""Composition controls only; mocked admission/producer is not product evidence."""
from contextlib import ExitStack
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import product_reuse as products
import runtime_aggregate_phase
from products import runtime_aggregate
from products.inventory import canonical_json_bytes, load_canonical_json_bytes
from products.registry import NATIVE_TARGETS, PhaseInstanceId


class RuntimeAggregateExecutionTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.state_root = self.root / 'original-state'
        self.state_root.mkdir()
        self.trust_root = self.root / 'original-trust'
        self.trust_root.mkdir()
        self.destination = self.root / 'output'
        self.stage = self.root / 'codex-agent-runtime-desktop/build/product-stage/runtime/runtime-aggregate/metadata'
        self.key = 'sha256:' + 'a' * 64
        self.instance = PhaseInstanceId('runtime', 'runtime-aggregate', 'metadata', 'aggregate')
        self.state = SimpleNamespace(prior_ready_plans={self.instance: {'buildKey': self.key}},
                                     producer={'commit': 'a' * 40}, plan={'event': 'pull_request'},
                                     expected_fixed={'versions': {'runtime-release': '0.2.7'}})
        self.bundles = {}
        for target in NATIVE_TARGETS:
            bundle = self.root / f'{target}.zip'
            self.bundles[target] = bundle
            directory = self.trust_root / target
            directory.mkdir()
            for name in (f'{target}.attestation.json', f'{target}.attestation.sig', 'public-key.pub'):
                (directory / name).write_bytes(b'synthetic detached evidence')

    def prepare(self, _state, _instance, destination, _key, _root):
        destination.mkdir(parents=True)
        (destination / 'original').write_bytes(b'unchanged original')
        return {**{f'codexAgent.{name}': str(destination / 'original') for name in (
            'contractPayload', 'contractMetadataReceipt', 'contractAttestation',
            'contractAttestationSignature', 'contractPublicKey')}, 'codexAgent.contractVersion': '0.2.0'}, {}

    def publication(self, *args, **kwargs):
        from products.receipt import write_output_manifest
        directory = self.stage / 'outputs/maven/jvm'
        directory.mkdir(parents=True)
        (directory / 'fixture.jar').write_bytes(b'composition control only')
        write_output_manifest(self.stage, 'runtime', 'runtime-aggregate', 'metadata', 'aggregate',
                              '0.2.7', {'maven': 'outputs/maven'})
        return SimpleNamespace(returncode=0)

    def produce(self, **kwargs):
        self.arguments = kwargs
        original = load_canonical_json_bytes((self.stage / 'output-manifest.json').read_bytes())['outputs']
        manifest = {'runtimeMavenFiles': [{'path': item['relativePath'].removeprefix('outputs/'),
                                         'bytes': item['bytes'], 'sha256': item['sha256']} for item in original]}
        (kwargs['output_directory'] / 'codex-agent-runtime-0.2.7-manifest.json').write_bytes(canonical_json_bytes(manifest))
        return {'manifest': manifest}

    def policy(self, _root, _commit, destination):
        destination.mkdir()
        (destination / 'keyring').write_bytes(b'original policy')
        return SimpleNamespace(keyring=destination / 'keyring', keys=destination)

    def invoke(self, **changes):
        return products.execute_runtime_aggregate(
            self.root / 'plan', self.state_root, self.state_root, self.destination,
            **{'expected_build_key': self.key, 'variant_trust_root': self.trust_root,
               'repository_root': self.root, 'environ': {}, **changes})

    def mocks(self, stack, *, collect=None, produce=None):
        stack.enter_context(mock.patch.object(products, '_verified_product_state', return_value=self.state))
        stack.enter_context(mock.patch.object(products, '_runtime_worker_checkout'))
        stack.enter_context(mock.patch.object(products, '_runtime_worker_environment', return_value=({}, self.root / 'gradlew')))
        stack.enter_context(mock.patch.object(products.subprocess, 'run', side_effect=self.publication))
        stack.enter_context(mock.patch.object(runtime_aggregate_phase, 'collect_maven_outputs',
            side_effect=lambda *_: ([], load_canonical_json_bytes((self.stage / 'output-manifest.json').read_bytes())['outputs'])))
        stack.enter_context(mock.patch.object(products, '_prepare_runtime_phase', side_effect=self.prepare))
        stack.enter_context(mock.patch.object(products, '_release_trust', side_effect=self.policy))
        stack.enter_context(mock.patch.object(runtime_aggregate_phase, 'collect_inputs',
            side_effect=collect, return_value={'variant_bundles': self.bundles,
                'variant_phase_receipts': {}, 'variant_validation_evidence': {},
                'publication_inputs': {}, 'adapter_evidence': {}, 'adapter_receipts': [], 'adapter_report_files': {}}))
        producer = stack.enter_context(mock.patch.object(runtime_aggregate, 'produce_runtime_aggregate',
                                                         side_effect=produce or self.produce))
        finalizer = stack.enter_context(mock.patch.object(products, 'finalize_phase_object', return_value={'fixture': True}))
        return producer, finalizer

    def test_fixed_existing_producer_receives_release_trust_and_only_payload_inputs(self):
        with ExitStack() as stack:
            producer, finalizer = self.mocks(stack)
            self.assertEqual({'fixture': True}, self.invoke())
        producer.assert_called_once()
        self.assertEqual('release', self.arguments['required_trust_domain'])
        self.assertNotIn('adapter_receipts', self.arguments)
        self.assertNotIn('private_key', self.arguments)
        self.assertEqual(set(NATIVE_TARGETS), set(self.arguments['variant_attestations']))
        self.assertEqual('development', finalizer.call_args.kwargs['trust_domain'])
        self.assertTrue((self.stage / 'output-manifest.json').is_file())

    def test_input_mutation_during_translation_or_production_never_finalizes(self):
        for when in ('translation', 'production'):
            with self.subTest(when=when):
                self.destination = self.root / when
                def mutate(*args, **kwargs):
                    (self.destination / 'inputs/original').write_bytes(b'changed')
                    if when == 'production':
                        return self.produce(**kwargs)
                    return {'variant_bundles': self.bundles, 'variant_phase_receipts': {},
                            'variant_validation_evidence': {}, 'publication_inputs': {},
                            'adapter_evidence': {}, 'adapter_receipts': [], 'adapter_report_files': {}}
                with ExitStack() as stack:
                    _, finalizer = self.mocks(stack, **{'collect' if when == 'translation' else 'produce': mutate})
                    with self.assertRaisesRegex(ValueError, 'inputs changed'):
                        self.invoke()
                    finalizer.assert_not_called()

    def test_coherent_maven_swap_after_original_binding_never_finalizes(self):
        def swapped(**kwargs):
            from products.receipt import write_output_manifest
            (self.stage / 'outputs/maven/jvm/fixture.jar').write_bytes(b'changed but coherently redeclared')
            write_output_manifest(self.stage, 'runtime', 'runtime-aggregate', 'metadata', 'aggregate',
                                  '0.2.7', {'maven': 'outputs/maven'})
            return self.produce(**kwargs)
        with ExitStack() as stack:
            _, finalizer = self.mocks(stack, produce=swapped)
            with self.assertRaisesRegex(ValueError, 'Maven manifest changed'):
                self.invoke()
            finalizer.assert_not_called()

    def test_staged_maven_change_after_manifest_creation_never_finalizes(self):
        def swapped(**kwargs):
            result = self.produce(**kwargs)
            (self.stage / 'outputs/maven/jvm/fixture.jar').write_bytes(b'changed after manifest')
            return result
        with ExitStack() as stack:
            _, finalizer = self.mocks(stack, produce=swapped)
            with self.assertRaisesRegex(ValueError, 'staged bytes changed'):
                self.invoke()
            finalizer.assert_not_called()

    def test_release_policy_change_during_publication_never_reaches_product_verifier(self):
        def changed(*args, **kwargs):
            result = self.publication(*args, **kwargs)
            (self.destination / 'release-policy/keyring').write_bytes(b'changed policy')
            return result
        with ExitStack() as stack:
            producer, finalizer = self.mocks(stack)
            stack.enter_context(mock.patch.object(products.subprocess, 'run', side_effect=changed))
            with self.assertRaisesRegex(ValueError, 'release policy changed'):
                self.invoke()
            producer.assert_not_called()
            finalizer.assert_not_called()

    def test_bytecode_namespace_created_by_publication_is_rejected(self):
        def changed(*args, **kwargs):
            result = self.publication(*args, **kwargs)
            (self.destination / 'python-bytecode').mkdir()
            return result
        with ExitStack() as stack:
            producer, finalizer = self.mocks(stack)
            stack.enter_context(mock.patch.object(products.subprocess, 'run', side_effect=changed))
            with self.assertRaisesRegex(ValueError, 'bytecode namespace'):
                self.invoke()
            producer.assert_not_called()
            finalizer.assert_not_called()

    def test_wrong_election_overlapping_originals_and_extra_trust_fail_closed(self):
        with ExitStack() as stack:
            producer, finalizer = self.mocks(stack)
            with self.assertRaisesRegex(ValueError, 'not ready'):
                self.invoke(expected_build_key='sha256:' + 'b' * 64)
            self.destination = self.trust_root / 'nested'
            with self.assertRaisesRegex(ValueError, 'overlaps'):
                self.invoke()
            self.destination = self.root / 'extra'
            (self.trust_root / 'unexpected').write_bytes(b'extra')
            with self.assertRaisesRegex(ValueError, 'exactly five'):
                self.invoke()
            producer.assert_not_called()
            finalizer.assert_not_called()

    def test_cli_accepts_only_explicit_aggregate_inputs(self):
        with mock.patch.object(products, 'execute_runtime_aggregate') as execute:
            self.assertEqual(0, products.main(['execute-runtime-aggregate', '--plan', 'plan',
                '--discovery-root', 'discovery', '--destination', 'output',
                '--variant-trust-root', 'trust', '--expected-build-key', self.key]))
        self.assertEqual(Path('trust'), execute.call_args.kwargs['variant_trust_root'])


if __name__ == '__main__':
    unittest.main()
