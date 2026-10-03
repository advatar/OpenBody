import copy
import unittest
from benchmark import corrupt, reconstruct, run, score, split_guard, synthetic


class RobustnessTests(unittest.TestCase):
    def test_participant_and_device_leakage(self):
        a = synthetic('a', 'one')
        with self.assertRaisesRegex(ValueError, 'participant_leakage'):
            split_guard(a, synthetic('a', 'two'))
        with self.assertRaisesRegex(ValueError, 'device_leakage'):
            split_guard(a, synthetic('b', 'one'), True)

    def test_sources_immutable_and_imputations_explicit(self):
        rows, targets = corrupt(synthetic('a', 'one'), 'random_missing')
        before = copy.deepcopy(rows)
        predictions = reconstruct(rows, 'causal_hold', 8)
        self.assertEqual(rows, before)
        for r in predictions:
            if r['record_ref'] in targets and r['value'] is not None:
                self.assertEqual(r['status'], 'imputed')
                self.assertEqual(r['uncertainty'], 'unknown')
                self.assertFalse(r['clinical_qualified'])
                self.assertTrue(r['parents'])

    def test_causal_estimator_never_uses_future(self):
        rows, _ = corrupt(synthetic('a', 'one'), 'block_missing')
        first = reconstruct(rows, 'causal_hold', 100)
        rows[35]['value'] = 99999
        second = reconstruct(rows, 'causal_hold', 100)
        self.assertEqual(first[:35], second[:35])

    def test_long_gap_abstention_and_coverage(self):
        rows, targets = corrupt(synthetic('a', 'one'), 'block_missing')
        online = score(targets, reconstruct(rows, 'causal_hold', 8))
        offline = score(targets, reconstruct(rows, 'offline_linear', 8))
        self.assertLess(online['coverage'], 1)
        self.assertEqual(offline['coverage'], 0)
        self.assertIsNone(offline['mae'])

    def test_hidden_observation_promotion_rejected(self):
        rows = synthetic('a', 'one')
        with self.assertRaisesRegex(ValueError, 'promoted'):
            score({rows[0]['record_ref']: rows[0]['value']}, reconstruct(rows, 'causal_hold', 8))

    def test_nonfinite_and_mixed_device_rejected(self):
        rows = synthetic('a', 'one')
        rows[0]['value'] = float('nan')
        with self.assertRaises(ValueError):
            reconstruct(rows, 'causal_hold', 8)
        rows = synthetic('a', 'one')
        rows[1]['device'] = 'two'
        with self.assertRaisesRegex(ValueError, 'mixed_series'):
            reconstruct(rows, 'causal_hold', 8)

    def test_shift_degrades_without_hiding_abstention(self):
        report = run()['results']
        by_key = {(r['scenario'], r['method']): r for r in report}
        self.assertGreater(by_key['device_shift', 'causal_hold']['mae'],
                           by_key['block_missing', 'causal_hold']['mae'])
        self.assertEqual(run(), run())


if __name__ == '__main__':
    unittest.main()
