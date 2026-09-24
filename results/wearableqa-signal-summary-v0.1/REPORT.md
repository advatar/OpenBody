# WearableQA deterministic signal-summary result

Status: research evaluation only. This is not a clinical-validity result and not a general wearable-reasoning score.

## Result

| Measure | Result |
|---|---:|
| Official questions | 4,084 |
| Answered | 80 |
| Explicit abstentions | 4,004 |
| Missing predictions | 0 |
| Execution errors | 0 |
| Overall coverage | 1.9589% |
| Accuracy on answered questions | 100% (80/80) |
| Full-benchmark accuracy with abstentions incorrect | 1.9589% |
| `signal_summary` coverage | 100% (80/80) |

Only five reviewed deterministic templates in `signal_summary` were eligible: mean RHR, mean steps, median steps, mean sleep duration, and DHRPS composed from independent RHR and step summaries. Every other category abstained.

## Reproducibility

- Raw structured dataset: `sha256:73dedd7290d80b1f0e78f1c51771ef3252a809da66e2484d2cc78cc844c140df`
- Official rendered JSONL: `sha256:de76b40b987bb09cf85475045f6a0cba3c2f53d82eae8c57fb278ee37601c2da`
- Predictions: `sha256:06008732f03f72962f344947f57ac4138e1970fb226e754d222b43e7e17cb49c`
- Run manifest: `sha256:bcfd7ea90f740e1d5c9ef7127f292cc03d8e444d7dee1733a43edd178ab739cd`
- Executed code: `sha256:32f8f86d31ead6eb8b2aedff20e965e422be152e1bbc031c83b0807e329fe070`
- Adapter: `openbody-wearableqa-signal-summary/0.2`
- Query engine: `openbody-longitudinal-query/0.2`
- Seed: none; execution is deterministic.

The adapter is label-blind and creates an immutable projection before execution. The projection excludes ground truth, future observations, cohort data, unrelated metrics, and benchmark-hidden metrics. Predictions and the licensed dataset are not vendored; use the documented commands to reproduce their digests.

## Interpretation

This establishes that the deterministic query path can perfectly execute the narrow arithmetic subset under the published dataset. It does not test natural-language reasoning, physiological interpretation, free response, unsafe advice, external-device transfer, or clinical utility. New categories require independently reviewed task-specific semantics rather than reuse based on similar names.
