"""Bounded synthetic diagnostics, deliberately disconnected from clinical runtime."""
import json
import math
import random
from statistics import mean


def finite(value, lower=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or (lower is not None and value < lower):
        raise ValueError('invalid_number')
    return value


class ScalarFilter:
    """Random-walk Kalman baseline: declared Q/R, no physiological meaning."""
    def __init__(self, process_variance=.01, measurement_variance=.04):
        self.q = finite(process_variance, 0)
        self.r = finite(measurement_variance, 1e-12)
        self.x, self.p, self.time = 0., 1., None

    def update(self, time, measurement, observable=True):
        finite(time)
        if self.time is not None and time <= self.time:
            raise ValueError('nonmonotonic_time')
        if measurement is not None:
            finite(measurement)
        dt = 0 if self.time is None else time - self.time
        self.p += self.q * dt
        self.time = time
        if measurement is not None and observable:
            gain = self.p / (self.p + self.r)
            self.x += gain * (measurement - self.x)
            self.p *= 1 - gain
        return dict(value=self.x if observable else None, variance=self.p,
                    status='inferred' if observable else 'abstained',
                    clinical_qualified=False)


def fuse(channels, gated=True):
    """Fixed externally declared quality flags; no learned gating claim."""
    selected = []
    for channel in channels:
        if channel['value'] is not None:
            finite(channel['value'])
        if channel['quality'] not in {'acceptable', 'corrupted', 'unknown'}:
            raise ValueError('invalid_quality')
        if channel['value'] is not None and (not gated or channel['quality'] == 'acceptable'):
            selected.append(channel)
    return dict(value=mean(c['value'] for c in selected) if selected else None,
                parents=[c['ref'] for c in selected],
                status='inferred' if selected else 'abstained',
                uncertainty='unknown', clinical_qualified=False)


ECG_FIELDS = ('device', 'firmware', 'lead', 'sample_rate', 'preprocessing', 'population', 'intended_use')


def ecg_metrics(context, expected, rows, person_days, threshold=.5):
    """Qualification *diagnostic*: synthetic labels never qualify a clinical model."""
    finite(person_days, 1e-12)
    finite(threshold, 0)
    if threshold > 1 or not rows:
        raise ValueError('invalid_threshold_or_empty_rows')
    if any(not context.get(k) or not expected.get(k) for k in ECG_FIELDS):
        raise ValueError('context_unknown')
    if any(context[k] != expected[k] for k in ECG_FIELDS):
        raise ValueError('context_mismatch')
    answered, false_alerts, correct, brier = 0, 0, 0, []
    for row in rows:
        if type(row['label']) is not int or row['label'] not in (0, 1):
            raise ValueError('invalid_label')
        probability = row['probability']
        if probability is not None:
            finite(probability, 0)
            if probability > 1:
                raise ValueError('invalid_probability')
        if not row['usable'] or probability is None:
            continue
        answered += 1
        positive = probability >= threshold
        false_alerts += positive and row['label'] == 0
        correct += positive == bool(row['label'])
        brier.append((probability - row['label']) ** 2)
    return dict(coverage=answered / len(rows), unusable=sum(not r['usable'] for r in rows),
                false_alerts_per_person_day=false_alerts / person_days,
                brier=mean(brier) if brier else None,
                accuracy_on_answered=correct / answered if answered else None,
                clinical_qualified=False, evidence='synthetic_only')


def run(seed=17):
    rng = random.Random(seed)
    f = ScalarFilter()
    errors, covered = [], []
    for i in range(200):
        truth = .02 * i
        estimate = f.update(float(i), None if 60 <= i < 90 else truth + rng.gauss(0, .2))
        errors.append(abs(estimate['value'] - truth))
        covered.append(abs(estimate['value'] - truth) <= 1.96 * math.sqrt(estimate['variance']))
    ungated, gated = [], []
    for i in range(100):
        truth = math.sin(i / 10)
        channels = [dict(ref=f'a:{i}', value=truth + rng.gauss(0, .05), quality='acceptable'),
                    dict(ref=f'b:{i}', value=truth + 4, quality='corrupted')]
        ungated.append(abs(fuse(channels, False)['value'] - truth))
        gated.append(abs(fuse(channels)['value'] - truth))
    context = dict(zip(ECG_FIELDS, ['synthetic-device', '1', 'I', 250, 'none', 'synthetic', 'AF_detection_diagnostic']))
    rows = [dict(label=i % 2, probability=.8 if i % 2 else .2, usable=i % 5 != 0) for i in range(100)]
    rows[2]['probability'] = .9
    return dict(seed=seed, evidence='synthetic_only', clinical_qualified=False,
                assimilation=dict(mae=mean(errors), nominal_interval_coverage=mean(covered),
                                  note='Coverage diagnostic only; missing-gap drift violates random-walk assumptions.'),
                fusion=dict(ungated_mae=mean(ungated), gated_mae=mean(gated),
                            note='Quality flags are known from the synthetic corruption generator.'),
                ecg=ecg_metrics(context, context, rows, 10))


if __name__ == '__main__':
    print(json.dumps(run(), indent=2, sort_keys=True, allow_nan=False))
