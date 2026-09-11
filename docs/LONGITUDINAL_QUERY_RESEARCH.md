# Deterministic longitudinal query research candidate

Status: protocol-0.2 research implementation. Not part of the frozen OpenBody 0.1 wire contract.

Research inputs:

- [WearableQA](https://arxiv.org/abs/2609.05405), Lee et al., 2026.
- [WearableQA reference dataset](https://github.com/facebookresearch/WearableQA), CC BY-NC 4.0.

## Purpose

An LLM should not be responsible for both calculating facts from a long physiological record and interpreting those facts. The research implementation separates the two:

```text
source observations
    -> deterministic longitudinal query
    -> digest-bound typed result or abstention
    -> separately governed physiological/clinical interpretation
```

`reference/python/openbody_ref/longitudinal.py` implements the deterministic boundary. It is intentionally not mounted in the reference host and is not advertised in the 0.1 OpenAPI or MCP profiles.

For research use, execute a request without changing the wire contract:

```bash
python tools/query_longitudinal.py query.json
```

## Implemented operations

| Operation | Output | Fail-closed conditions |
|---|---|---|
| `summary` | count, mean, median, range, population standard deviation | insufficient samples |
| `trend` | least-squares slope per day, direction, time span | insufficient samples or no temporal span |
| `lagged_correlation` | strongest Pearson correlation and signed day lag | insufficient paired samples or zero variance |
| `excursions` | robust baseline median/MAD and threshold-crossing observations | missing/degenerate baseline |
| `recovery` | first sustained return to an explicit baseline tolerance | missing baseline or recovery not observed |

Every computed or abstained result includes:

- exact subject binding;
- algorithm/version identity;
- SHA-256 digest of the query and observation set;
- source identifiers declared by the input observations;
- unique sample count used by the computation;
- explicit disposition and reason code.

Malformed timestamps, non-finite values or results, unsupported fields or parameters, invalid quality thresholds, duplicate timestamps from competing sources and cross-subject observations are rejected rather than converted into plausible-looking results. Missing quality is unknown rather than perfect: it cannot pass a positive minimum-quality threshold. Excursion and recovery baselines must be explicit and must end before the evaluation window or event.

## WearableQA integration

`tools/evaluate_wearableqa.py` scores externally generated prediction JSONL without invoking a model. It reports:

- full accuracy, selective accuracy and coverage;
- abstention count;
- data versus health reasoning;
- single- versus cross-signal reasoning;
- per-category results;
- dataset and prediction digests.

The scorer reports missing predictions and execution errors separately from explicit abstentions, requires a run manifest, and warns that multiple-choice accuracy is not clinical validity. This prevents runner failures or an apparently strong selective score from hiding very low coverage.

### Dataset preflight

The official structured release was inspected at content digest `sha256:73dedd7290d80b1f0e78f1c51771ef3252a809da66e2484d2cc78cc844c140df`:

- 4,084 questions from 200 users;
- 2,724 data-reasoning and 1,360 health-reasoning questions;
- 2,402 cross-signal and 1,682 single-signal questions;
- 3,154 population-grounded and 930 literature-grounded questions.

Compatibility is deliberately narrower than category-name similarity suggests:

| WearableQA category | Current compatibility | Required before support |
|---|---|---|
| `signal_summary` | Supported by the narrow adapter for five allowlisted templates | Independent review of visibility, rounding and insufficient-data rules |
| `excursion_count` | Mathematical primitive is close | Exact first/second-half partition, missingness and option semantics |
| `signed_correlation` | Not supported | Benchmark uses Spearman plus categorical stability rules; the generic engine now exposes a Spearman mode but does not implement those rules |
| `trend_shape` | Not supported | Ten-class shape detection rather than a linear slope |
| `recovery_time` | Not supported | Detection of the largest multi-day event and benchmark-specific recovery classification |

The first narrow adapter is implemented in `openbody_ref.wearableqa`. It answers only the structured `signal_summary` category using an explicit semantic allowlist: mean RHR, mean/median steps, mean sleep duration and DHRPS composed from separate RHR and step summaries. Before execution it creates an immutable visibility projection containing only the requested date window and metrics; ground truth, future history, cohort data and unrelated or hidden metrics cannot reach the query layer. Unsupported categories become explicit abstentions. Run it and score the resulting predictions with:

```bash
python tools/run_wearableqa_adapter.py --raw WearableQA_raw.json --out predictions.jsonl --manifest-out manifest.json
python tools/evaluate_wearableqa.py --dataset WearableQA.jsonl --predictions predictions.jsonl --manifest manifest.json
```

The dataset is not vendored because it is large, distributed via Git LFS, and licensed CC BY-NC 4.0. Users supply their own authorized copy to the scorer.

## Qualification gates before a host/API proposal

1. Define a typed, versioned observation/query/result schema and review it independently.
2. Add unit-aware coordinates; raw metric names are not an interoperability contract.
3. Define sampling cadence, aggregation and duplicate-resolution semantics.
4. Add property tests for timezone offsets, missingness, irregular sampling and adversarial numeric inputs.
5. Independently review the narrow `signal_summary` adapter, then add categories only when their benchmark semantics match versioned query operations exactly.
6. Compare end-to-end assistants with and without tool use at matched coverage.
7. Add free-response, unsupported-question and clinically unsafe-advice tests; multiple choice alone is insufficient.
8. Only then propose an additive protocol-0.2 HTTP/MCP surface.

No model result produced by this module is a diagnosis, recommendation, causal estimate or counterfactual simulation.
