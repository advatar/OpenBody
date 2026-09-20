# SPARC research adapter (M0)

Research-only integration candidate for OpenBody. It follows the 2026 SPARC review's separation of machine-computable autonomic connectivity (SCKAN) from executable computational modeling (o2S2PARC/ASCENT).

The SCKAN reader is deliberately literal and fail-closed: it verifies a pinned local export when a digest is supplied, preserves native triples and evidence, performs exact filtering, and treats missing coverage as unknown. It does not invent inverse/transitive connectivity or convert anatomical relations into signal flow.

The numerical comparator is the first gate for an ASCENT reproduction. It refuses comparisons unless model, artifact, inputs, dataset version, species, stimulation modality, metric and unit agree. A pass means only that a candidate number is within a predeclared tolerance of a reference number.

## Boundaries

No changes to OpenBody protocol/runtime, no patient data, no Twin writes, no clinical assertions, no stimulation control, and no dosing recommendations. Implanted cervical VNS evidence is not silently transferred to consumer auricular stimulation.

## Run

    python3 -m unittest discover -s experiments/sparc -p 'test_*.py' -v

## Actual checkpoint — 2026-09-20

- **VERIFIED:** pinned SCKAN prerelease metadata and both large artifact digests.
- **REPRODUCED:** native upstream ApiNATOMY query and three bounded native query
  variants, with repeat-stable typed results; deliberately missing coverage is UNKNOWN.
- **BLOCKED:** ASCENT numerical reproduction. Dataset metadata/configuration were
  retrieved; the deposit's study UUID differs from the lock, one metadata size
  check fails, reference outputs/solver identities are absent, and no licensed
  local or authorized browser execution environment is available.
- **NOT TESTED:** biological/clinical validity, broader Simple SCKAN competency
  reproduction, consumer integration and modality transfer.

See [SCKAN evidence](evidence/SCKAN_REPRODUCTION.md),
[ASCENT evidence](evidence/ASCENT_REPRODUCTION.md),
[audit](evidence/AUDIT.md) and [validation record](VALIDATION.md).
The original literal-edge adapter remains; typed SPARQL results are preserved
separately rather than flattened into asserted anatomical edges. This is not a
complete ontology transformation or model qualification.
