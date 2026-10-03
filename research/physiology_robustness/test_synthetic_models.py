import unittest
from synthetic_models import ScalarFilter, fuse, ecg_metrics, ECG_FIELDS, run


class SyntheticModelTests(unittest.TestCase):
    def test_missing_measurements_widen_uncertainty(self):
        f = ScalarFilter()
        first = f.update(0, 1)
        second = f.update(10, None)
        self.assertGreater(second['variance'], first['variance'])
        self.assertEqual(first['value'], second['value'])

    def test_unobservable_abstains(self):
        self.assertIsNone(ScalarFilter().update(0, 8, observable=False)['value'])

    def test_long_run_stability(self):
        f = ScalarFilter()
        for i in range(10000):
            r = f.update(i, 3)
            self.assertGreaterEqual(r['variance'], 0)
        self.assertAlmostEqual(r['value'], 3)

    def test_invalid_noise_and_time(self):
        for q, r in [(-1, 1), (1, 0), (float('nan'), 1)]:
            with self.assertRaises(ValueError):
                ScalarFilter(q, r)
        f = ScalarFilter()
        f.update(1, 1)
        with self.assertRaises(ValueError):
            f.update(1, 2)

    def test_gate_abstains_for_unknown_or_absent_inputs(self):
        for value in [None, 12]:
            r = fuse([dict(ref='x', value=value, quality='unknown')])
            self.assertEqual(r['status'], 'abstained')
            self.assertEqual(r['parents'], [])

    def test_corrupted_channel_has_no_influence(self):
        good = dict(ref='good', value=2, quality='acceptable')
        for bad in [10, 1000]:
            r = fuse([good, dict(ref='bad', value=bad, quality='corrupted')])
            self.assertEqual(r['value'], 2)
            self.assertEqual(r['parents'], ['good'])

    def test_every_ecg_context_field_is_pinned(self):
        ctx = {k: 'known' for k in ECG_FIELDS}
        rows = [dict(label=0, probability=.9, usable=True)]
        for k in ECG_FIELDS:
            for changed, code in [(None, 'context_unknown'), ('other', 'context_mismatch')]:
                with self.assertRaisesRegex(ValueError, code):
                    ecg_metrics(dict(ctx, **{k: changed}), ctx, rows, 1)

    def test_ecg_abstention_denominator_and_false_alerts(self):
        ctx = {k: 'known' for k in ECG_FIELDS}
        rows = [dict(label=0, probability=.9, usable=True),
                dict(label=1, probability=.9, usable=False)]
        r = ecg_metrics(ctx, ctx, rows, 2)
        self.assertEqual(r['coverage'], .5)
        self.assertEqual(r['false_alerts_per_person_day'], .5)
        self.assertFalse(r['clinical_qualified'])

    def test_reproducibility_and_gating_diagnostic(self):
        self.assertEqual(run(), run())
        self.assertLess(run()['fusion']['gated_mae'], run()['fusion']['ungated_mae'])
        self.assertFalse(run()['clinical_qualified'])


if __name__ == '__main__':
    unittest.main()
