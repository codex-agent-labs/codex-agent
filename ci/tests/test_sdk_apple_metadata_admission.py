"""Real metadata planning/content, with signature/native handoff explicitly mocked.

These tests prove composition and lifetime rejection, not Git or hosted trust.
"""

from contextlib import contextmanager, ExitStack
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

from ci.products import sdk_apple_metadata_admission as admission
from ci.products.inventory import canonical_json_bytes, sha256_bytes
from ci.products.plan import plan_phase, NOT_APPLICABLE_FLAGS_DIGEST, NOT_APPLICABLE_TOOLCHAIN_DIGEST
from ci.products.receipt import write_output_manifest
from ci.products.registry import PhaseInstanceId
from ci.tests import test_sdk_apple_metadata as content_fixture
from ci.tests.product_chain_support import write_receipt


class AppleMetadataAdmissionTest(unittest.TestCase):
    def setUp(self):
        self.f = content_fixture.AppleMetadataTest(methodName='runTest')
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.root = self.f.root
        self.producer = dict(repository='owner/repository', workflowPath='.github/workflows/product-validation.yml',
            commit='a' * 40, tree='b' * 40, event='pull_request', runId=91, runAttempt=2, pullRequest=31)
        self.package_path = self.root / 'package-receipt.json'
        self.package = write_receipt(self.package_path, product='sdk', component='sdk-ios', phase='package', target='ios',
            version=self.f.version, version_identity=self.f.version, upstream=[], outputs=self.f.manifest['outputs'],
            context={'producer': self.producer})
        self.package_raw = self.package_path.read_bytes()
        self.receipts, self.paths, self.values, self.records = {}, {}, {}, []
        self.evidence = self.root / 'evidence'
        self.evidence.mkdir()
        (self.evidence / 'opaque-retained-originals').write_bytes(b'full gate mocked only at handoff boundary')
        for index, target in enumerate(admission._TARGETS):
            stage = self.root / ('validation-' + target)
            content = stage / admission._VALIDATION_PATH
            content.parent.mkdir(parents=True)
            content.write_bytes(canonical_json_bytes(self.f.contents[target]))
            manifest = write_output_manifest(stage, 'sdk', 'sdk-ios', 'validation', target, self.f.version,
                                             {'apple-validation-content': admission._VALIDATION_PATH})
            path = self.root / (target + '-receipt.json')
            receipt = write_receipt(path, product='sdk', component='sdk-ios', phase='validation', target=target,
                version=self.f.version, version_identity=self.f.version, upstream=[], outputs=manifest['outputs'],
                context={'producer': {**self.producer, 'runId': 92 + index, 'commit': str(index + 2) * 40}})
            raw = path.read_bytes()
            self.paths[target], self.receipts[target] = path, receipt
            self.values[target] = {'receiptBytes': raw, 'receipt': deepcopy(receipt), 'stage': stage,
                'package': {'stage': self.f.stage, 'receipt': deepcopy(self.package), 'receiptBytes': self.package_raw}}
            digest = sha256_bytes(raw)
            self.records.append({'receiptSha256': digest, 'target': target,
                                 'evidenceRoot': 'originals/' + digest.removeprefix('sha256:')})
            entry = self.evidence / self.records[-1]['evidenceRoot']
            entry.mkdir(parents=True)
            (entry / 'opaque-original').write_bytes(b'full signed entry mocked by explicit handoff boundary')
        self.records.sort(key=lambda row: row['receiptSha256'])
        self.policy = {name: str(self.root / name) for name in (
            'plan', 'attestationPublicKey', 'keyring', 'keysDirectory', 'toolingEvidence',
            'toolingPublicKey', 'javaExecutable', 'toolingKeyring', 'toolingKeysDirectory')}
        self.policy.update(attestationTrustDomain='development', toolingTrustDomain='release')
        self.arguments = dict(repository=self.root, validation_receipts=self.paths, evidence_root=self.evidence,
                              evidence_records=self.records, policy_revision='c' * 40, policy=self.policy)
        self.events, self.exit_mutation = [], None
        self.inventory = [{'relativePath': 'ci/products/sdk_apple_metadata.py', 'bytes': 1, 'sha256': sha256_bytes(b'x')}]
        self.versions = {'contract': '0.8.0', 'runtime-release': '0.8.0',
                         'runtime-compatibility': '0.8.0', 'sdk': self.f.version}
        planned = self.planned()
        self.stage = self.root / 'metadata-stage'
        content = self.stage / admission.OUTPUT_PATH
        content.parent.mkdir(parents=True)
        content.write_bytes(canonical_json_bytes(admission.apple_metadata_content(**self.f.arguments)))
        manifest = write_output_manifest(self.stage, 'sdk', 'sdk-ios', 'metadata', 'ios', self.f.version,
                                         {admission.OUTPUT_KIND: admission.OUTPUT_PATH})
        self.metadata_path = self.root / 'metadata-receipt.json'
        self.metadata = write_receipt(self.metadata_path, product='sdk', component='sdk-ios', phase='metadata', target='ios',
            version=self.f.version, version_identity=self.f.version, upstream=[], outputs=manifest['outputs'],
            context={'producer': self.producer, 'plan_factory': lambda *_: planned})

    def planned(self):
        return plan_phase(PhaseInstanceId('sdk', 'sdk-ios', 'metadata', 'ios'), inventory=self.inventory,
            versions=self.versions, upstream_receipts=[self.receipts[target] for target in admission._TARGETS],
            toolchain_profile_digest=NOT_APPLICABLE_TOOLCHAIN_DIGEST,
            flags_digest=NOT_APPLICABLE_FLAGS_DIGEST, output_schema_version=1)

    @contextmanager
    def handoff(self, root, **kwargs):
        target = kwargs['target']
        expected = next(row for row in self.records if row['target'] == target)
        self.assertEqual(self.evidence / expected['evidenceRoot'], root)
        self.assertEqual(expected['receiptSha256'], kwargs['expected_receipt_sha256'])
        self.assertEqual(self.root, kwargs['repository_root'])
        self.assertEqual('c' * 40, kwargs['policy_revision'])
        self.assertEqual('release', kwargs['required_trust_domain'])
        self.events.append('enter:' + target)
        try:
            yield self.values[target]
        finally:
            self.events.append('exit:' + target)
            if self.exit_mutation:
                self.exit_mutation(target)

    @contextmanager
    def boundaries(self):
        with ExitStack() as stack:
            stack.enter_context(patch.object(admission, 'rebase_sdk_apple_validation_records',
                                             side_effect=lambda records, *_: deepcopy(records)))
            stack.enter_context(patch.object(admission, 'verified_apple_validation_handoff', side_effect=self.handoff))
            stack.enter_context(patch.object(admission, 'run_git', side_effect=lambda _, __, ref:
                                             self.producer['tree' if ref.endswith('^{tree}') else 'commit']))
            stack.enter_context(patch.object(admission, 'git_product_versions', return_value=self.versions))
            stack.enter_context(patch.object(admission, 'phase_git_inventory', return_value=self.inventory))
            yield

    def verify(self):
        return admission.verify_sdk_apple_metadata_admission(metadata_stage=self.stage,
            metadata_receipt=self.metadata_path, **self.arguments)

    def test_real_plan_and_content_accept_mixed_validation_producers_after_both_clean_exits(self):
        with self.boundaries():
            receipt, raw = self.verify()
        self.assertEqual(self.metadata, receipt)
        self.assertEqual(self.metadata_path.read_bytes(), raw)
        self.assertEqual(['enter:ios-arm64', 'enter:ios-simulator-arm64',
                          'exit:ios-simulator-arm64', 'exit:ios-arm64'], self.events)

    def test_shared_inputs_context_holds_both_gates_and_exact_original_paths(self):
        with self.boundaries(), admission.verified_sdk_apple_metadata_inputs(**self.arguments) as inputs:
            self.assertEqual(['enter:ios-arm64', 'enter:ios-simulator-arm64'], self.events)
            self.assertEqual(self.f.stage, inputs['package_stage'])
            self.assertEqual(self.package_raw, inputs['package_receipt_bytes'])
            self.assertEqual(self.receipts, inputs['validation_receipts'])
            self.assertEqual(admission.apple_metadata_content(**self.f.arguments), inputs['content'])
            for target, path in inputs['validation_contents'].items():
                self.assertEqual(canonical_json_bytes(self.f.contents[target]), path.read_bytes())

    def test_missing_target_record_or_wrong_handoff_receipt_rejects(self):
        with self.boundaries():
            with self.assertRaises(ValueError):
                with admission.verified_sdk_apple_metadata_inputs(**{**self.arguments,
                        'validation_receipts': {'ios-arm64': self.paths['ios-arm64']}}):
                    self.fail('missing target yielded')
            saved = deepcopy(self.records)
            self.records.pop()
            with self.assertRaises(ValueError):
                self.verify()
            self.records[:] = saved
            self.values['ios-arm64']['receiptBytes'] += b'changed'
            with self.assertRaisesRegex(ValueError, 'handoff receipt'):
                self.verify()

    def test_different_original_package_receipt_even_same_outputs_rejects(self):
        package = self.values['ios-simulator-arm64']['package']
        package['receipt']['producer']['runId'] += 1
        package['receiptBytes'] = canonical_json_bytes(package['receipt'])
        with self.boundaries(), self.assertRaisesRegex(ValueError, 'package'):
            self.verify()

    def test_receipt_only_gate_requires_exact_singleton_projection_inventory(self):
        raw = self.metadata_path.read_bytes()
        with self.boundaries():
            self.assertEqual((self.metadata, raw), admission.verify_sdk_apple_metadata_receipt_admission(
                metadata_receipt_bytes=raw, **self.arguments))
        for field, value in (('kind', 'binding-evidence'), ('relativePath', 'outputs/evidence/other.json'),
                             ('bytes', self.metadata['outputs'][0]['bytes'] + 1),
                             ('sha256', sha256_bytes(b'changed'))):
            receipt = deepcopy(self.metadata)
            receipt['outputs'][0][field] = value
            with self.subTest(field=field), self.boundaries(), self.assertRaises(ValueError):
                admission.verify_sdk_apple_metadata_receipt_admission(
                    metadata_receipt_bytes=canonical_json_bytes(receipt), **self.arguments)

    def test_private_projection_mutation_during_caller_use_rejects_on_exit(self):
        with self.boundaries(), self.assertRaisesRegex(ValueError, 'private package or validation'):
            with admission.verified_sdk_apple_metadata_inputs(**self.arguments) as inputs:
                inputs['validation_contents']['ios-arm64'].write_bytes(b'changed')

    def test_real_replan_rejects_inventory_or_upstream_changes(self):
        for mutate in ('inventory', 'upstream'):
            before_inventory, before_receipts = deepcopy(self.inventory), deepcopy(self.receipts)
            with self.subTest(mutate=mutate):
                if mutate == 'inventory':
                    self.inventory[0]['sha256'] = sha256_bytes(b'y')
                else:
                    # Real planner binds upstream build keys/outputs, not their run IDs.
                    receipt = deepcopy(self.receipts['ios-arm64'])
                    receipt['outputs'][0]['sha256'] = sha256_bytes(b'changed')
                    self.receipts['ios-arm64'] = receipt
                    changed = self.planned()
                    self.assertNotEqual(self.metadata['inputs'], changed['inputs'])
                    self.receipts = before_receipts
                    continue
                with self.boundaries(), self.assertRaisesRegex(ValueError, 'inputs/build key'):
                    self.verify()
            self.inventory[:] = before_inventory

    def test_context_exit_failure_or_late_package_mutation_never_returns(self):
        for mutation in ('exit', 'package', 'metadata', 'carrier', 'policy'):
            def mutate(target):
                if target != 'ios-arm64':
                    return
                if mutation == 'exit':
                    raise ValueError('full original replay exit rejected')
                if mutation == 'package':
                    self.values['ios-simulator-arm64']['package']['receipt']['producer']['runId'] += 1
                elif mutation == 'metadata':
                    (self.stage / admission.OUTPUT_PATH).write_bytes(b'changed')
                elif mutation == 'carrier':
                    (self.evidence / self.records[0]['evidenceRoot'] / 'late-file').write_bytes(b'changed')
                else:
                    self.policy['plan'] += '-changed'
            before_values, before_policy = deepcopy(self.values), deepcopy(self.policy)
            original = (self.stage / admission.OUTPUT_PATH).read_bytes()
            self.exit_mutation = mutate
            with self.subTest(mutation=mutation), self.boundaries(), self.assertRaises(ValueError):
                self.verify()
            self.values, self.policy = before_values, before_policy
            self.arguments['policy'] = self.policy
            (self.stage / admission.OUTPUT_PATH).write_bytes(original)
            (self.evidence / self.records[0]['evidenceRoot'] / 'late-file').unlink(missing_ok=True)
        self.exit_mutation = None


if __name__ == '__main__':
    unittest.main()
