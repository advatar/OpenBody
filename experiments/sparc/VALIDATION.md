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

- 54 offline research tests: `python3 -m unittest discover -s experiments/sparc -p 'test_*.py' -v`.
  Includes existing cases plus release/digest mismatch, bounded extraction attacks,
  malformed export/typed results, unsupported/empty results, species/modality/unit/
  artifact mismatch, failed/missing outputs, NaN/Inf, invalid tolerances and
  machine-checkable receipt consistency. Receipt tests do not rerun real science.
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
Initial CI repair is green; final revision checks are linked in the delivery.

## Remaining gates

Resolve ASCENT study identity and the manifest metadata discrepancy; obtain exact
reference outputs, configuration and published solver versions; predeclare a
justified comparator; obtain compatible licensed local or authorized o²S²PARC
execution; execute the candidate. Broader upstream Simple SCKAN query coverage
and complete OWL-expression handling remain open. Biological/clinical model
qualification and any read-only Cymba consumer are outside this milestone.
