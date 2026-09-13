"""Auxiliary lane routing with real receipt/action/hash gates, not CI observation.

Only the impact projection authority is mocked; originals are actual small lane
receipt trees and remain unchanged by aggregation.
"""

from argparse import Namespace
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from ci import receipt


class AuxiliaryToolingReceiptTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='auxiliary-tooling-receipt-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.plan_path = self.root / 'plan/impact-plan.json'
        self.receipts = self.root / 'receipts'
        self.output = self.root / 'validation-receipt.json'
        self.plan = {'schemaVersion': 1, 'repository': 'codex-agent-labs/codex-agent',
            'event': 'pull_request', 'pullRequest': 31, 'baseCommit': 'a' * 40,
            'headCommit': 'b' * 40, 'validationCommit': 'c' * 40, 'validationTree': 'd' * 40,
            'lanes': {lane: {'build': False, 'test': False, 'metadata': False} for lane in receipt.LANES}}
        self.plan['lanes']['android']['test'] = True
        receipt.write_json(self.plan_path, self.plan)
        projection = patch.object(receipt, 'validate_legacy_lane_projection')
        projection.start()
        self.addCleanup(projection.stop)
        self.lane('android', 'test')

    def lane(self, name, actions='build,test', *, reissued=False):
        for filename in receipt.INPUT_NAMES.values():
            path = self.plan_path.parent / 'inventories' / name / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((name + ':' + filename + '\n').encode())
        root = self.receipts / name
        root.mkdir(parents=True, exist_ok=True)
        (root / 'product.bin').write_bytes(b'original fixture product\n')
        evidence = []
        if reissued:
            (root / 'transport-provenance.json').write_bytes(b'{}\n')
            evidence.append('transport-provenance.json=transport-provenance')
        receipt.create_receipt(Namespace(plan=self.plan_path, lane=name, output=root,
            workflow_path='.github/workflows/ci.yml', artifact_name=f'codex-agent-ci-{name}-' + 'd' * 40,
            run_id=17, run_attempt=2, runner=['os=Linux', 'arch=X64'],
            toolchain=['java=17', 'validationActions=' + actions],
            artifact=['product.bin=release-tooling' if name == 'contracts' else 'product.bin=binary'],
            evidence=evidence))
        return root

    def aggregate(self, **options):
        arguments = Namespace(plan=self.plan_path, receipts=self.receipts, output=self.output, **options)
        receipt.aggregate(arguments)
        return json.loads(self.output.read_bytes())

    def inventory(self):
        return {path.relative_to(self.root).as_posix(): path.read_bytes()
                for parent in (self.plan_path.parent, self.receipts)
                for path in parent.rglob('*') if path.is_file()}

    def test_original_auxiliary_build_and_test_is_verified_but_not_a_validation_lane(self):
        auxiliary = self.lane('contracts')
        before = self.inventory()
        with patch.object(receipt, 'validate_receipt', wraps=receipt.validate_receipt) as verify:
            result = self.aggregate(auxiliary_contracts=True)
        self.assertEqual({'android'}, set(result['lanes']))
        self.assertEqual('passed', result['result'])
        self.assertEqual(17, result['lanes']['android']['runId'])
        self.assertEqual(before, self.inventory())
        self.assertIn(auxiliary / 'lane-receipt.json', [call.args[0] for call in verify.call_args_list])
        original = receipt.validate_receipt(auxiliary / 'lane-receipt.json', self.plan_path, auxiliary)
        self.assertEqual(frozenset({'build', 'test'}), receipt.parse_validation_actions(original['toolchain']))

    def test_default_exact_lane_set_is_unchanged_and_missing_auxiliary_rejects(self):
        self.assertEqual({'android'}, set(self.aggregate()['lanes']))
        self.output.unlink()
        with self.assertRaises(ValueError):
            self.aggregate(auxiliary_contracts=True)
        self.assertFalse(self.output.exists())
        self.lane('contracts')
        with self.assertRaises(ValueError):
            self.aggregate()
        self.assertFalse(self.output.exists())

    def test_auxiliary_flag_rejects_already_required_contracts(self):
        self.plan['lanes']['contracts']['build'] = True
        receipt.write_json(self.plan_path, self.plan)
        self.lane('contracts')
        with self.assertRaises(ValueError):
            self.aggregate(auxiliary_contracts=True)
        self.assertFalse(self.output.exists())
        self.assertEqual({'android', 'contracts'}, set(self.aggregate()['lanes']))

    def test_unexpected_other_lane_and_duplicate_contracts_are_not_hidden(self):
        auxiliary = self.lane('contracts')
        extra = self.lane('portable')
        before = self.inventory()
        with self.assertRaises(ValueError):
            self.aggregate(auxiliary_contracts=True)
        self.assertEqual(before, self.inventory())
        self.assertFalse(self.output.exists())
        extra.rename(self.root / 'unused-portable')
        shutil.copytree(auxiliary, self.receipts / 'duplicate-contracts')
        with self.assertRaisesRegex(ValueError, 'Duplicate receipt'):
            self.aggregate(auxiliary_contracts=True)
        self.assertFalse(self.output.exists())

    def test_auxiliary_requires_real_action_coverage_and_original_not_reissued_receipt(self):
        auxiliary = self.lane('contracts')
        path = auxiliary / 'lane-receipt.json'
        original = receipt.read_json(path)
        for actions in ('build', 'test', 'metadata', 'build,metadata', 'test,build', ''):
            with self.subTest(actions=actions):
                changed = {**original, 'toolchain': {**original['toolchain'], 'validationActions': actions}}
                receipt.write_json(path, changed)
                before = self.inventory()
                with self.assertRaises(ValueError):
                    self.aggregate(auxiliary_contracts=True)
                self.assertEqual(before, self.inventory())
                self.assertFalse(self.output.exists())
        self.lane('contracts', reissued=True)
        # The reissued marker is honestly declared and hashed: only the new
        # original-source rule, not a broken file inventory, must reject it.
        receipt.validate_receipt(path, self.plan_path, auxiliary)
        with self.assertRaises(ValueError):
            self.aggregate(auxiliary_contracts=True)
        self.assertFalse(self.output.exists())

    def test_auxiliary_integrity_and_cli_flag_remain_strict(self):
        auxiliary = self.lane('contracts')
        (auxiliary / 'product.bin').write_bytes(b'tampered product')
        with self.assertRaisesRegex(ValueError, 'integrity-mismatched'):
            self.aggregate(auxiliary_contracts=True)
        self.assertFalse(self.output.exists())
        args = ['aggregate', '--plan', str(self.plan_path), '--receipts', str(self.receipts), '--output', str(self.output)]
        self.assertFalse(receipt.parser().parse_args(args).auxiliary_contracts)
        self.assertTrue(receipt.parser().parse_args([*args, '--auxiliary-contracts']).auxiliary_contracts)


if __name__ == '__main__':
    unittest.main()
