# Physiological robustness research lane

This additive research harness preserves the frozen whole-person v1 contract.
It is not a new observation format, production model, or clinical qualification.
Raw custody remains in InVivo. No patient data is included.

## Run

```sh
python -m unittest discover -s research/physiology_robustness -v
python research/physiology_robustness/benchmark.py
```

The standard-library harness uses an explicitly synthetic scalar oscillator.
It separates held-out participants and devices; masks targets before estimation;
tests random missingness, contiguous outages, non-wear and a synthetic device
offset; and reports coverage separately from MAE/RMSE. Offline interpolation may
use future observations; causal hold may not. Neither fills beyond its declared
gap bound. Imputed values retain parent references, unknown uncertainty and an
explicit non-clinical status. Original inputs remain unchanged.

The device offset is an artificial robustness probe, not measured device-domain
transfer. The split guard protects declared subject/device/record identities;
it cannot verify dataset identities or detect undisclosed duplicate waveforms.
Result hashing is local report integrity, not the normative OpenBody digest.

## Ordered next experiments

1. **Missingness/device shift:** bind a licensed public cohort's immutable
   version/digests and participant/device inventory. Freeze training-only
   preprocessing and a participant-disjoint/device-held-out split before model
   selection. Add a compact temporal baseline and an independently reproducible
   SOTER adapter only after verifying code, weights and reuse terms. Test real
   irregular timestamps, modality dropout and calibrated selective prediction.
   Report per-subject error, coverage and intervals; no superiority claim from
   these synthetic fixtures.
2. **Executable model updates:** reuse #18/#24 and the existing model-family
   boundary. A bounded synthetic assimilation test must expose noise assumptions,
   uncertainty, observability/identifiability and stability. Unidentifiable
   parameters abstain; missing measurements widen uncertainty. Invasive-pressure
   evidence does not qualify wearable contractility inference.
3. **Reliability-gated fusion:** compare a small conventional temporal model with
   motion/quality gating under modality dropout and corrupted inputs. Fit quality
   rules on training data only. WESAD participant-held-out evaluation is an initial
   reproduction, not free-living stress validation. Hardware latency/energy must
   be measured on the intended device and include preprocessing.
4. **ECG qualification:** reuse #18 and sensor metadata #66. Pin device, firmware,
   lead, sample rate, preprocessing, population and intended use. Evaluate
   calibration, unusable recordings, abstention and false alerts per person-day
   against independently adjudicated labels. Keep AF detection separate from
   forecasts, structural disease and clinical outcome claims. Unknown context
   blocks qualification. Real device recordings and clinical labels are required.

## Sources

- [SOTER preprint, 15 September 2026](https://arxiv.org/abs/2609.16804)
- [Cardiovascular digital twin, 10 September 2026](https://doi.org/10.1002/cnm.70209)
- [StressNet, 19 September 2026](https://doi.org/10.1038/s41598-026-71273-z)
- [Wearable AI-ECG review, 30 September 2026](https://doi.org/10.1093/ehjdh/ztag155)

These motivate experiments; this implementation does not reproduce their results.
