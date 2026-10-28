"""Recipe derivation is offline preparation, never native completion authority."""

from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path
import json
import unittest
from unittest.mock import patch

import completed_sdk_reuse as completed
import completed_sdk_reuse as prepare
from products.inventory import canonical_json_bytes, sha256_bytes
from products.receipt import compute_build_key
from products.restore import object_relative_path
from ci.tests import test_completed_sdk_reuse as fixtures


class PrepareSdkCompletionTest(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.CompletedSdkControlsTest()
        fixture.setUp()
        fixture.enable_planned_context()
        self.base = fixture.base
        self.controls = {path.replace('product-resume-state/', 'runtime-state/'): value
                         for path, value in fixture.controls.items()}
        self.request = self.controls['runtime-state/reuse-wave-request.json']
        self.result = self.controls['runtime-state/reuse-wave-result.json']
        self.producer = self.controls['runtime-state/producer.json']
        self.old_receipt = fixture.receipt
        self.old_path = 'runtime-state/original/csharp/phase-receipt.json'
        old = {**fixture.spec['completedPhases'][0], 'receiptPath': self.old_path}
        self.parent_sdk = {'spec': {'schemaVersion': 1}, 'proof': {'held': 'synthetic parent'}}
        fixed = fixtures.ordinary_spec()
        self.policy = {key: deepcopy(fixed[key]) for key in ('parent', 'contractControls', 'contractFiles')}
        self.policy.update(parentProofSha256=sha256_bytes(canonical_json_bytes(self.parent_sdk['proof'])),
            reuseCompletion={**fixed['parent'], 'runId': 1, 'runAttempt': 1})
        self.previous = {'proof': self.parent_sdk['proof'], 'extension': {
            'spec': {'schemaVersion': 4, 'parent': self.policy['parent'], 'completedPhases': [old]},
            'proof': {'controls': {self.old_path: self.old_receipt},
                      'members': [{'bytes': 37}], 'originals': [{'held': 'old original'}]}}}
        self.policy['reuseCompletionProofSha256'] = sha256_bytes(canonical_json_bytes(self.previous['extension']['proof']))
        self.source = {**fixed['source'], 'producer': self.producer, 'jobName': 'product-validation / sdk-collect-9',
                       'inventoryCommit': self.producer['commit'], 'artifactBytes': 1000}
        plan = {key: self.producer[key] for key in ('repository', 'event', 'pullRequest')}
        plan.update(validationCommit=self.producer['commit'], validationTree=self.producer['tree'], remoteBuildAuthorized=True)
        self.controls[completed.SOURCE_PLAN] = json.dumps(plan, indent=2) + '\n'
        receipt = deepcopy(self.old_receipt)
        receipt['component'] = 'python'
        receipt['phase'] = 'package'
        receipt['buildKey'] = compute_build_key(**{key: receipt[key] for key in (*completed.IDENTITY, 'inputs')})
        row = {**{key: receipt[key] for key in completed.IDENTITY}, 'buildKey': receipt['buildKey'],
               'receiptSha256': sha256_bytes(canonical_json_bytes(receipt)),
               'objectSha256': sha256_bytes(b'new object')}
        self.request['availableObjects'].append(row)
        self.result['phases'].append({**row, 'state': 'retained'})
        self.request['phaseAuthorities'].append({**{key: row[key] for key in completed.IDENTITY},
            **{key: receipt['inputs'][key] for key in ('toolchainProfileDigest', 'flagsDigest', 'outputSchemaVersion')}})
        self.controls['held-python/phase-receipt.json'] = receipt
        self.object = {'relativePath': 'runtime-state/original-objects/' + object_relative_path(row['buildKey'], row['receiptSha256']),
                       'bytes': 512, 'sha256': row['objectSha256']}
        self.originals = [{**fixed['originals'][0], **{key: phase[key] for key in completed.IDENTITY}}
                          for phase in (old, row)]
        self.bind()

    def bind(self):
        inventory = [{'relativePath': path, 'bytes': len(fixtures.control_bytes(path, value)),
                      'sha256': sha256_bytes(fixtures.control_bytes(path, value))}
                     for path, value in self.controls.items() if not path.startswith('held-python/')]
        inventory.append(deepcopy(self.object))
        inventory.sort(key=lambda row: row['relativePath'])
        self.references = {'schemaVersion': 1,
            'base': {'artifactId': 1, 'artifactSha256': sha256_bytes(b'base'), 'stateWave': 0},
            'inventory': inventory, 'references': [{**inventory[0], 'sourcePath': inventory[0]['relativePath']}]}
        self.source['referenceControlSha256'] = sha256_bytes(canonical_json_bytes(self.references))

    def run_prepare(self):
        with ExitStack() as stack:
            stack.enter_context(patch.object(completed, '_base', return_value=self.base))
            stack.enter_context(patch.object(completed, '_inventory_revision', return_value=self.producer['commit']))
            current = stack.enter_context(patch.object(completed, 'validate_current'))
            stack.enter_context(patch.object(completed, 'issue_extension', side_effect=AssertionError('must not issue')))
            values = prepare.prepare_collected_extension(self.policy, self.source, self.references,
                self.controls, self.originals, root=Path.cwd(), frozen={}, parent_sdk=self.parent_sdk, previous_sdk=self.previous)
            current.assert_called_once()
            return values

    def test_new_result_inherits_old_object_and_derives_bounded_receipt_hints(self):
        before = canonical_json_bytes([self.policy, self.source, self.references, self.controls, self.originals])
        recipe, controls, report = self.run_prepare()
        self.assertEqual(2, report['selectedSdkPhases'])
        self.assertEqual(1, report['inheritedSdkObjects'])
        self.assertEqual(1, report['newSdkObjectsRequiringQualification'])
        self.assertEqual(len(self.request['availableObjects']), report['retainedPhases'])
        self.assertTrue(report['preparationOnly'])
        self.assertFalse(report['qualificationIssued'])
        self.assertEqual(0, report['networkCalls'] + report['productBodiesRead'] + report['productExecutions'])
        self.assertEqual(self.controls[completed.SOURCE_PLAN], recipe['sourcePlan'])
        self.assertEqual(1, len(recipe['receiptObjects']))
        self.assertEqual(self.controls['held-python/phase-receipt.json'], recipe['receiptObjects'][0]['receipt'])
        self.assertEqual(before, canonical_json_bytes([self.policy, self.source, self.references, self.controls, self.originals]))
        self.controls[self.old_path]['result'] = 'failure'
        self.assertEqual('success', controls[self.old_path]['result'])

    def test_exact_reference_plan_receipt_and_object_substitutions_fail(self):
        for case in ('reference', 'plan-whitespace', 'receipt', 'object', 'object-size', 'result', 'missing-original', 'duplicate-original'):
            self.setUp()
            if case == 'reference': self.source['referenceControlSha256'] = sha256_bytes(b'wrong')
            elif case == 'plan-whitespace': self.controls[completed.SOURCE_PLAN] += ' '
            elif case == 'receipt': self.controls[self.old_path]['productVersion'] = 'forged'
            elif case == 'object': self.object['sha256'] = sha256_bytes(b'wrong'); self.bind()
            elif case == 'object-size': self.object['bytes'] = 512 * 1024**2 + 1; self.bind()
            elif case == 'result': self.result['phases'][-1]['state'] = 'failed'; self.bind()
            elif case == 'missing-original': self.originals.pop()
            else: self.originals.append(deepcopy(self.originals[0]))
            with self.subTest(case=case), self.assertRaises(ValueError): self.run_prepare()

    def test_existing_parent_subject_role_order_and_current_input_gates_stay_mandatory(self):
        for case in ('parent', 'previous', 'role', 'same-run', 'authority'):
            self.setUp()
            if case == 'parent': self.policy['parentProofSha256'] = sha256_bytes(b'wrong')
            elif case == 'previous': self.policy['reuseCompletionProofSha256'] = sha256_bytes(b'wrong')
            elif case == 'role': self.source['jobName'] = 'product-validation / sdk-collect-999'
            elif case == 'same-run': self.policy['reuseCompletion'].update(runId=self.producer['runId'], runAttempt=self.producer['runAttempt'])
            else:
                self.request['phaseAuthorities'][-1]['flagsDigest'] = sha256_bytes(b'wrong')
                self.bind()
            if case == 'authority':
                with patch.object(completed, '_base', return_value=self.base), \
                        patch.object(completed, '_inventory_revision', return_value=self.producer['commit']), \
                        patch.object(completed, 'validate_current', side_effect=ValueError('current authority changed')), \
                        self.assertRaisesRegex(ValueError, 'current authority changed'):
                    prepare.prepare_collected_extension(self.policy, self.source, self.references, self.controls,
                        self.originals, root=Path.cwd(), frozen={}, parent_sdk=self.parent_sdk, previous_sdk=self.previous)
            else:
                with self.subTest(case=case), self.assertRaises(ValueError): self.run_prepare()


if __name__ == '__main__':
    unittest.main()
