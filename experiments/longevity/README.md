# Longevity research track — M0

**Implemented research infrastructure, not an official benchmark reproduction, an aging clock, or a clinical integration.** Nothing here writes a Twin state, clinical assertion, treatment recommendation, or production model registry. The frozen OpenBody 0.1 contracts and existing branches are unchanged.

## What runs now

Python 3.11+ standard-library code provides a label-blind JSONL adapter, per-task scoring, same-case model comparisons, a signed-permit loopback inference client, a longitudinal split validator, and two bounded research tools. Ed25519 permit verification uses `/usr/bin/openssl` with Ed25519 support. The tests generate ephemeral keys and a mock local model server; they do not load a real checkpoint, contact a paid API, or contain released benchmark rows.

```bash
python3 -m unittest discover -s experiments/longevity -p 'test_*.py' -v
python3 experiments/longevity/longevity.py --help
```

There is no `pip install`, upstream-code execution, plugin discovery, model download, automatic approval, or default signing key. The added CI workflow pins its checkout action and runs only this stdlib suite. It does not harden unrelated existing repository workflows or attest the runner image/OpenSSL binary.

## Verified external resources

The [Cell paper](https://doi.org/10.1016/j.cell.2026.08.026), published 17 September 2026, describes [LongevityBench](https://longevitybenchmarks.org/), specialist models and an agentic research system. The source catalog is `catalog.json`; it records what was inspected on 19 September 2026, not permission to execute it.

The [released dataset](https://huggingface.co/datasets/insilicomedicine/longebench) has 17 benchmark tasks, five domains, 25,457 benchmark rows, and a 728-row `mini` configuration. Mini has different task IDs; this adapter maps both sets explicitly. The `extra` configuration is rejected rather than silently pooled into the benchmark. Tasks retain separate units; no average of years, months, days and percent is presented as a meaningful leaderboard score.

The dataset is **CC-BY-NC-4.0**. Qwen-derived Longevity model cards report **CC-BY-ND-4.0**, while the two Liquid models use **lfm1.0**. These are different restrictions: noncommercial data terms are not the same as no-derivatives model terms. The [9B model card](https://huggingface.co/insilicomedicine/longevity-llm) describes commercial serving as distributed with attribution while restricting redistribution of modified versions. Do not infer clearance for our commercial evaluation, tuning, quantization or redistribution. Appropriate rights review is required. No model is admitted in the catalog; model revisions and weight hashes remain null rather than invented.

The dataset's recorded revision is `40bc2f97b699bca29256c568a824212811091cd9`. The [published LFS pointer](https://huggingface.co/datasets/insilicomedicine/longebench/commit/40bc2f97b699bca29256c568a824212811091cd9) identifies `mini/eval-00000-of-00001.parquet`, 6,920,300 bytes, SHA-256 `544e0bf2975b04cf1d2be6654b4baccbe04db3cf4f167d80c81e25a9fc3fe72c`. This is a published digest, not an independently verified local download or publisher signature. The parquet was not downloaded here. Parquet-to-JSONL conversion is not implemented; it belongs in an independently reviewed environment, with converter/runtime provenance and input/output hashes recorded. Merely hashing an arbitrary JSONL file does not establish its descent from the published parquet.

[Longevity Claw](https://github.com/Insilico-org/longeclaw) is a reference, not an imported dependency. Its tools, clock coefficients, model supply chain and data licenses have not been audited here.

## Evaluation procedure

1. Resolve dataset rights, authenticated artifact provenance, converter/runtime pins and original-file integrity. Export the selected public configuration to JSONL in that reviewed environment. Keep the original three chat messages per row. Preserve the export hash and conversion record. Do not use patient records.
2. Prepare blinded requests in a new directory. The raw file SHA is its ordinary byte hash; the review reference is a declaration, not proof of rights. The adapter validates known task metadata, projects only system/user content, strips the assistant reference and metadata, and rejects unknown shapes and duplicated prompts.

```bash
python3 experiments/longevity/longevity.py prepare mini.jsonl \
  --sha256 "$RAW_JSONL_SHA256" --config mini \
  --rights-review "$APPROVED_RIGHTS_REVIEW" --out prepared-mini
python3 experiments/longevity/longevity.py hash-json prepared-mini/requests.json
python3 experiments/longevity/longevity.py hash-json prepared-mini/gold.json
```

Freeze both printed digests independently before running models. They hash this module's sorted, compact UTF-8 JSON encoding, **not JCS and not the pretty-printed file bytes**. Gold stays outside model inputs. For a genuine blind deployment, also isolate gold from the serving process's filesystem and access rights; this client is not an OS sandbox.

3. Independently review the local serving environment. Pin the actual checkpoint revision, all weight/config/tokenizer files, runtime and dependencies in a serving manifest. An authorized reviewer signs a permit scoped to the exact blinded bundle, model/revision, serving-manifest digest, endpoint, case budget and validity interval. Use `permit.example.json` only as a deliberately invalid template. A signing key must be enrolled independently; generating a key is not approval. Sign the exact permit file bytes, without later reformatting:

```bash
openssl pkeyutl -sign -rawin -inkey reviewer-private.pem -in permit.json -out permit.sig
python3 experiments/longevity/longevity.py run prepared-mini/requests.json \
  permit.json permit.sig reviewer-public.pem \
  --key-sha256 "$INDEPENDENT_TRUST_ROOT_PEM_SHA256" --out specialist-run.json
```

The endpoint must be `http://127.0.0.1:PORT/v1/chat/completions`. No redirects or proxy environment are used. The client rejects remote URLs, expired permits, model-name mismatches, extra tool calls and truncated generations. It rechecks the permit before each request and before accepting an answer. Run a separately approved baseline under its own permit to produce `baseline-run.json`.

**Trust limits:** The signature authenticates a maintainer's authorization, not publisher authenticity, license truth, or live serving identity. Revision and manifest hashes are signed declarations, not remote attestation; a server echoing a model name does not prove which weights it used. Data classification is declared, not a PHI detector. Configure the serving process's own egress, storage and telemetry separately; loopback alone cannot prevent it from forwarding prompts. There is no key-revocation service, hardware attestation, total spend cap, resumable execution or process isolation in M0. Do not admit sensitive data or use this permit as clinical authority.

4. Score and compare against the independently frozen gold hash:

```bash
python3 experiments/longevity/longevity.py score prepared-mini/gold.json specialist-run.json \
  --gold-sha256 "$FROZEN_GOLD_CANONICAL_SHA256" --out specialist-score.json
python3 experiments/longevity/longevity.py compare prepared-mini/gold.json \
  baseline-run.json specialist-run.json --gold-sha256 "$FROZEN_GOLD_CANONICAL_SHA256" \
  --out paired-comparison.json
```

The scorer counts answers, explicit abstentions, failures, invalid outputs and missing predictions separately. Classification accuracy includes every case in its denominator. Regression's full-coverage MAE is null when any case is unanswered; selective MAE is separately labeled. Comparisons require the same frozen cases and report per-task deltas only at full coverage. No aggregate winner, statistical superiority, biological validity, or clinical promotion follows.

**Scorer parity is still open.** `strict-final-answer-v1` accepts bare class tokens or finite bare numbers, optionally after a thinking terminator. It is not the authors' verified output parser. Official row formatting, all labels, task semantics, aggregation and published score reproduction must be checked against the real dataset and official evaluator. The test fixtures validate our code, not that external compatibility. `official_reproduction` remains false even when task counts match.

## Longitudinal physiology is a separate study

`check-split rows.json` enforces one prospective subject/cohort-disjoint design: train, validation and test must all exist; no subject or cohort crosses splits; each `last_observation <= anchor < outcome_time`; each earlier split's outcomes precede the next split's anchors. Timestamps require timezones. Rows contain `subject_id`, `cohort_id`, `split`, `last_observation`, `anchor`, and `outcome_time`. This is not the only valid study design and does not implement within-person personalized validation.

A later study must pre-register actual physiological targets, eligibility, missingness handling, deterministic/statistical baselines, uncertainty/calibration and clinically meaningful endpoints. Chronological-age questions and lifespan tasks in LongevityBench are not validation of InVivo biological-age inference or human healthspan benefit. A mini subset used for debugging is development data; overlapping full-benchmark rows cannot be relabeled independent holdout evidence. Assess published model-training overlap and reserve an independent longitudinal cohort.

## Research tools and integration boundary

`tools plan.json reports.json --out receipts.json` accepts at most six exact `{ "tool": ..., "report": ... }` steps. Reports is an object mapping local report names to scorecards. Only `inspect_coverage` and `propose_followup` are enabled. Receipts bind the report digest; follow-ups remain inert proposals. Shell, downloads, arbitrary tools, aging clocks, target-ranking, prescribing and publishing into the Twin are not implemented or allowed. This is a bounded dispatcher for a future Kline planner, **not a complete autonomous agent or a Longevity Claw port**.

Integration should reuse existing work rather than invent another authority layer:

- [OpenBody PR #15](https://github.com/advatar/OpenBody/pull/15): separately reviewed deterministic longitudinal baseline; not copied, expanded or merged here.
- [OpenBody PR #19](https://github.com/advatar/OpenBody/pull/19): qualified model-family execution remains the future admission boundary; research receipts here cannot bypass it.
- Kline's existing research/evaluation workflow can propose approved comparisons through this tool boundary after a reviewed adapter is implemented. No Kline wiring was changed here.
- InVivo/Metabolog receives no native model, personal-data route, age estimate or UI change from this PR. ProvidEHR clinical assertion and action authority remain separate and unchanged.

## Next gates

M1: rights and artifact provenance; reviewed converter; real mini schema and official-scorer parity. M2: pinned serving manifests and approved keys; paired base/specialist/frontier experiments, latency/resource measurements and uncertainty analysis. M3: independent longitudinal study plus existing model-family qualification before any InVivo consumer integration. Scientific tools need individual data/model provenance and qualification before agent access. No phase is marked complete by passing these software tests.
