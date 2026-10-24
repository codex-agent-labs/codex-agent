"""Old native locators narrow discovery; every invocation still observes afresh."""

from copy import deepcopy
from threading import Barrier, Lock
import unittest
from unittest.mock import patch

import completed_sdk_reuse as completed
import product_reuse as products
from products.inventory import canonical_json_bytes
from ci.tests.test_products import phase_receipt


class CompletionOriginalObservationsTest(unittest.TestCase):
    def setUp(self):
        self.receipts = []
        for component, target in (('cpp', 'linux-x64'), ('cpp', 'linux-arm64'),
                ('cpp', 'macos-arm64'), ('cpp', 'macos-x64'), ('cpp', 'windows-x64'),
                ('python', 'linux-x64'), ('python', 'linux-arm64'), ('python', 'macos-arm64')):
            self.receipts.append({**deepcopy(phase_receipt()), 'product': 'sdk',
                                  'component': component, 'phase': 'validation', 'target': target})
        self.originals = {completed._identity(row): {'artifactId': i + 100}
                          for i, row in enumerate(self.receipts)}
        self.qualified = {completed._identity(row): ({'bytes': 10}, {'job': {'id': i + 200}})
                          for i, row in enumerate(self.receipts[:6])}

    def test_parallel_mixed_observation_binds_old_locators_keeps_order_and_fresh_batch(self):
        snapshots, batches, calls = [], [], []
        guard, barrier = Lock(), Barrier(4)
        active, peak = 0, 0

        def prime(rows, token):
            self.assertEqual('synthetic', token)
            self.assertEqual([{'receipt': row, 'artifactId': self.originals[completed._identity(row)]['artifactId']}
                              for row in self.receipts], rows)
            batch = products._CI_OBSERVATIONS.get()
            self.assertIsNotNone(batch)
            batches.append(batch)

        def observe(original, receipt, token, **kwargs):
            nonlocal active, peak
            instance = completed._identity(receipt)
            self.assertIs(products._CI_OBSERVATIONS.get(), batches[-1])
            self.assertEqual({'native_locator': self.qualified[instance][1]} if instance in self.qualified else {}, kwargs)
            self.assertEqual(self.originals[instance], original)
            with guard:
                active += 1
                peak = max(peak, active)
                calls.append(instance)
            try:
                barrier.wait(timeout=5)
                return {'id': original['artifactId']}, [], {'identity': instance}
            finally:
                with guard:
                    active -= 1

        before = canonical_json_bytes([self.receipts, list(self.originals.values()), [list(row) for row in self.qualified.values()]])
        with patch.object(products, '_prime_runtime_artifact_metadata', side_effect=prime), \
                patch.object(completed, 'observe_original', side_effect=observe), \
                patch.object(products, '_download_contract_ci_upload', side_effect=AssertionError('body forbidden')):
            for _ in range(2):
                snapshots.append(completed._observe_incremental_originals(self.originals, self.receipts,
                                                                         self.qualified, 'synthetic'))
                self.assertIsNone(products._CI_OBSERVATIONS.get())
        self.assertEqual(4, peak)
        self.assertEqual(16, len(calls))
        self.assertIsNot(batches[0], batches[1])
        self.assertEqual(snapshots[0], snapshots[1])
        self.assertEqual(list(range(100, 108)), [row[0]['id'] for row in snapshots[0]])
        self.assertEqual(before, canonical_json_bytes([self.receipts, list(self.originals.values()), [list(row) for row in self.qualified.values()]]))

    def test_failure_exits_batch_and_retry_reobserves_every_original(self):
        batch_objects, seen = [], []
        def prime(rows, token):
            batch_objects.append(products._CI_OBSERVATIONS.get())
        def observe(original, receipt, token, **kwargs):
            seen.append(original['artifactId'])
            if original['artifactId'] == 104:
                raise ValueError('fresh original expired')
            return original, [], {}
        with patch.object(products, '_prime_runtime_artifact_metadata', side_effect=prime), \
                patch.object(completed, 'observe_original', side_effect=observe) as observed:
            for _ in range(2):
                seen.clear()
                with self.assertRaisesRegex(ValueError, 'fresh original expired'):
                    completed._observe_incremental_originals(self.originals, self.receipts, self.qualified, 'synthetic')
                self.assertEqual(list(range(100, 108)), sorted(seen))
                self.assertIsNone(products._CI_OBSERVATIONS.get())
            self.assertEqual(16, observed.call_count)
            self.assertIsNot(batch_objects[0], batch_objects[1])


if __name__ == '__main__':
    unittest.main()
