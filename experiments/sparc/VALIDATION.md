# SPARC M0 validation

This directory is a research candidate, isolated from the frozen OpenBody protocol/runtime.

## M0 acceptance

1. A SCKAN export is accepted only with explicit schema checks and, when supplied, an exact SHA-256 digest.
2. Native subject/predicate/object, species and evidence fields are returned without inverse/transitive/signal-flow inference.
3. No match is reported as unknown coverage, not a negative biological assertion.
4. Numerical reproduction compares only identically bound model/artifact/input/dataset/species/modality/metric/unit cases.
5. Failed, missing, abstained and invalid outputs cannot become a pass.
6. A numerical pass is never labelled biological or clinical validation.

## Executed checkpoint — 2026-09-20

- 76 offline research tests: `python3 -m unittest discover -s experiments/sparc -p 'test_*.py' -v`.
  Includes existing cases plus release/digest mismatch, bounded extraction attacks,
  malformed export/typed results, unsupported/empty results, species/modality/unit/
  artifact mismatch, failed/missing outputs, NaN/Inf, invalid tolerances and
  machine-checkable receipt consistency. Receipt tests do not rerun real science. Full historical outputs were independently rehashed with `evidence_tools` before compaction; offline tests include corruption of unselected rows.
- Existing `python tools/validate_openbody.py`: two protocol examples and all 11
  clinical-reference admission/rejection fixtures pass.
- `PYTHONPATH=reference/python python -m pytest -q reference/python/tests`: 172 pass.
  Two dependency deprecation warnings (Starlette/httpx and anyio); no test failures.
- All five JSON parse checks from `.github/workflows/conformance.yml` pass.
- Real SCKAN execution: two runs, all five canonical result hashes identical.
  See exact query scope and interpretation in the evidence report. This is not
  biological validation or a reproduction of every historical upstream query.
- Actual ASCENT execution: **NOT TESTED / BLOCKED**; no output/tolerance is invented.

Local Python is 3.14.7. Hosted research CI uses Python 3.13; conformance uses 3.12.
Implementation commit `4795cc0a46253ea9195b899165d2604fee4d7009` passed hosted
SPARC runs [35511918368](https://github.com/advatar/OpenBody/actions/runs/35511918368)
and [35511919989](https://github.com/advatar/OpenBody/actions/runs/35511919989),
and conformance [35511920007](https://github.com/advatar/OpenBody/actions/runs/35511920007).
Machine-readable results are in `evidence/receipts/hosted-ci.json`. Subsequent
report-only commit checks are linked in the final delivery.

## ASCENT provenance and evidence reduction checkpoint

The 364/365 template distinction is authenticated; the former UUIDs are different
studies. Repeated manifest retrieval classifies its API/object size contradiction
as UPSTREAM_METADATA_DEFECT while retaining FAILED verification. The public
13-file Guided Mode deposit and pinned source were inspected without executing
models. There is no authenticated reference output or complete runtime/input
binding. No executable contract, candidate or tolerance was created.

The full SCKAN outputs from both earlier executions pass the external-output
verifier after compaction. Exact queries and frozen hashes remain unchanged.
Full datasets, downloaded API responses and raw output are external. See
[evidence audit](evidence/PR_AUDIT.md) and [ASCENT investigation](evidence/ASCENT_REPRODUCTION.md).

## Remaining gates

Obtain an authorized Guided Mode study export with exact input/potential bytes,
solver/service provenance and published numerical output; then freeze a justified
contract before candidate execution. The metadata size defect requires upstream
correction for a fully passing deposit receipt; it is diagnosed, not waived.
Broader SCKAN and biological/clinical qualification are later milestones. PR #23
remains draft for reviewer acceptance of the explicit BLOCKED scope, without
any implication of completed ASCENT reproduction or consumer readiness.

See [external model admission policy](../../docs/EXTERNAL_MODEL_ADMISSION.md) for
qualification boundaries, compact examples and the committed pre-execution gate.
ASCENT external evidence is tracked separately in [issue #25](https://github.com/advatar/OpenBody/issues/25);
it does not block review of this research infrastructure. No candidate was executed.

Admission milestone verification: **99 research tests**, **172 reference tests**
(two dependency deprecation warnings), **2 protocol examples**, **11 clinical-reference
fixtures**, **5 JSON parsing checks** passed. New tests use synthetic temporary Git
repositories and prove contract-before-callback ordering. No ASCENT execution or
SCKAN query rerun occurred. Final-head hosted CI is linked from PR #23.
