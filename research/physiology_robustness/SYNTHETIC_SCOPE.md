# Synthetic-only implementation scope — 3 October 2026

The owner confirmed that no real cohort is available and authorized synthetic
work. All results remain research diagnostics, with clinical_qualified=false.

## Implemented

1. Missingness and synthetic device-offset benchmark: causal and offline
   baselines, hidden-target isolation, participant/device split guard,
   abstention/error reporting and imputation lineage.
2. Assimilation: scalar random-walk Kalman baseline with declared process and
   measurement variance; irregular-time updates; missing-measurement uncertainty
   growth; explicit unobservable-state abstention; numerical stability check.
3. Reliability gating: fixed quality flags select acceptable channels; unknown,
   absent and corrupted inputs are excluded; no usable channels abstain.
   Ungated fusion provides a comparison under known synthetic corruption.
4. ECG diagnostic evaluation: exact device, firmware, lead, sample rate,
   preprocessing, population and intended-use context; coverage, unusable
   recordings, Brier score and false alerts/person-day. Labels and probabilities
   are synthetic scalars; this is not an ECG classifier or waveform validation.

Run all 16 tests:

```sh
python -m unittest discover -s research/physiology_robustness -v
python research/physiology_robustness/benchmark.py
python research/physiology_robustness/synthetic_models.py
```

Reports: synthetic-report.json and model-diagnostics.json. These reports are
regenerated deterministically with pinned seeds; no runtime performance claims.

## Interpretation and remaining limits

- The scalar model is generic, not a cardiovascular mechanism or ROUKF
  reproduction. The observable flag is supplied by the diagnostic; it is not
  a computed identifiability proof. Real model identifiability needs its own
  observation equations and parameter sensitivity analysis.
- Gating flags are supplied by the corruption generator. Results show the
  behavior of a gate given correct quality flags, not successful quality
  detection. No trained temporal network or neuromorphic implementation exists.
- Nominal Gaussian interval coverage is measured, not assumed to be calibrated.
  Drift during outages intentionally exposes model mismatch.
- ECG context checks compare declared metadata, not hardware attestations.
  Synthetic probabilities/labels cannot establish clinical benefit or actual
  false-alert burden.
- SOTER/StressNet reproduction, learned-model training, physiological model
  composition, production integration, real device power/latency and clinical
  qualification remain outside this bounded implementation.
- Frozen OpenBody contracts and existing runtime are unchanged. Future runtime
  integration must pass existing #18 qualification and authority boundaries.
