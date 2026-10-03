"""Synthetic research harness; not an OpenBody wire profile or clinical qualification.

Offline interpolation is deliberately separate from causal online estimation.
Hidden targets never enter the estimator's input.
"""
import hashlib
import json
import math
import random
from statistics import mean

VERSION = 'openbody.research-robustness/0.1'


def split_guard(train, test, held_out_device=False):
    if not train or not test:
        raise ValueError('empty_split')
    if {r['subject'] for r in train} & {r['subject'] for r in test}:
        raise ValueError('participant_leakage')
    if held_out_device and {r['device'] for r in train} & {r['device'] for r in test}:
        raise ValueError('device_leakage')
    ids = [r['record_ref'] for r in train + test]
    if len(ids) != len(set(ids)):
        raise ValueError('record_leakage')


def validate_series(rows):
    if not rows:
        raise ValueError('empty_series')
    previous = -math.inf
    refs = set()
    for row in rows:
        if row['record_ref'] in refs:
            raise ValueError('duplicate_record')
        refs.add(row['record_ref'])
        t = row['time']
        value = row['value']
        if isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t) or t <= previous:
            raise ValueError('invalid_time')
        previous = t
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)):
            raise ValueError('invalid_value')
        if row['status'] not in {'observed', 'missing', 'non_wear'}:
            raise ValueError('invalid_status')
        if (value is not None) != (row['status'] == 'observed'):
            raise ValueError('value_status_mismatch')
    if len({(r['subject'], r['device'], r['unit']) for r in rows}) != 1:
        raise ValueError('mixed_series')


def reconstruct(rows, method, max_gap):
    """Return new values with explicit imputation lineage; never mutate observations."""
    validate_series(rows)
    if method not in {'causal_hold', 'offline_linear'} or not math.isfinite(max_gap) or max_gap < 0:
        raise ValueError('invalid_method_or_gap')
    observed = [i for i, r in enumerate(rows) if r['status'] == 'observed']
    output = []
    for i, row in enumerate(rows):
        value, status, parents = row['value'], row['status'], [row['record_ref']]
        if value is None:
            left = next((j for j in reversed(observed) if j < i), None)
            right = next((j for j in observed if j > i), None)
            if method == 'causal_hold' and left is not None and row['time'] - rows[left]['time'] <= max_gap:
                value, status, parents = rows[left]['value'], 'imputed', [rows[left]['record_ref']]
            elif method == 'offline_linear' and left is not None and right is not None:
                span = rows[right]['time'] - rows[left]['time']
                if span <= max_gap:
                    fraction = (row['time'] - rows[left]['time']) / span
                    value = rows[left]['value'] + fraction * (rows[right]['value'] - rows[left]['value'])
                    status, parents = 'imputed', [rows[left]['record_ref'], rows[right]['record_ref']]
        output.append(dict(row, value=value, status=status, parents=parents,
                           method=method, uncertainty='unknown', clinical_qualified=False))
    return output


def score(hidden_targets, predictions):
    """Score only withheld observations, reporting coverage separately from error."""
    by_ref = {r['record_ref']: r for r in predictions}
    if len(by_ref) != len(predictions) or not hidden_targets:
        raise ValueError('invalid_evaluation_set')
    errors = []
    for ref, target in hidden_targets.items():
        if not math.isfinite(target) or ref not in by_ref:
            raise ValueError('invalid_target_or_missing_prediction')
        row = by_ref[ref]
        if row['status'] == 'observed':
            raise ValueError('hidden_target_promoted_to_observation')
        if row['value'] is not None:
            if row['status'] != 'imputed' or not row['parents'] or not math.isfinite(row['value']):
                raise ValueError('invalid_imputation')
            errors.append(row['value'] - target)
    return dict(target_count=len(hidden_targets), answered=len(errors),
                coverage=len(errors) / len(hidden_targets),
                mae=mean(abs(e) for e in errors) if errors else None,
                rmse=math.sqrt(mean(e * e for e in errors)) if errors else None)


def synthetic(subject, device, count=80):
    """Arbitrary scalar oscillator, not a physiological simulator."""
    return [dict(subject=subject, device=device, unit='synthetic_unit',
                 record_ref=f'synthetic:{subject}:{device}:{i}', time=float(i),
                 value=10 + math.sin(i / 8), status='observed') for i in range(count)]


def corrupt(rows, scenario, seed=7):
    """Mask targets independently; acquisition shifts affect visible inputs only."""
    rng = random.Random(seed)
    result, targets = [], {}
    for i, row in enumerate(rows):
        hidden = rng.random() < .25 if scenario == 'random_missing' else 20 <= i < 35
        copy = dict(row)
        if hidden:
            targets[row['record_ref']] = row['value']
            copy.update(value=None, status='non_wear' if scenario == 'non_wear' else 'missing')
        elif scenario == 'device_shift':
            copy['value'] += 2.0
        result.append(copy)
    return result, targets


def run():
    train, test = synthetic('train', 'device-a'), synthetic('test', 'device-b')
    split_guard(train, test, held_out_device=True)
    results = []
    for scenario in ['random_missing', 'block_missing', 'non_wear', 'device_shift']:
        inputs, targets = corrupt(test, scenario)
        for method in ['causal_hold', 'offline_linear']:
            results.append(dict(scenario=scenario, method=method,
                                evaluation_mode='online' if method == 'causal_hold' else 'offline',
                                **score(targets, reconstruct(inputs, method, max_gap=8))))
    payload = dict(schema=VERSION, seed=7, evidence='synthetic_only',
                   clinical_qualified=False, results=results)
    payload['result_digest'] = hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()
    return payload


if __name__ == '__main__':
    print(json.dumps(run(), indent=2, sort_keys=True, allow_nan=False))
