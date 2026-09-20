# SPARC research adapter (M0)

Research-only integration candidate for OpenBody. It follows the 2026 SPARC review's separation of machine-computable autonomic connectivity (SCKAN) from executable computational modeling (o2S2PARC/ASCENT).

The SCKAN reader is deliberately literal and fail-closed: it verifies a pinned local export when a digest is supplied, preserves native triples and evidence, performs exact filtering, and treats missing coverage as unknown. It does not invent inverse/transitive connectivity or convert anatomical relations into signal flow.

The numerical comparator is the first gate for an ASCENT reproduction. It refuses comparisons unless model, artifact, inputs, dataset version, species, stimulation modality, metric and unit agree. A pass means only that a candidate number is within a predeclared tolerance of a reference number.

## Boundaries

No changes to OpenBody protocol/runtime, no patient data, no Twin writes, no clinical assertions, no stimulation control, and no dosing recommendations. Implanted cervical VNS evidence is not silently transferred to consumer auricular stimulation.

## Run

    python3 -m unittest discover -s experiments/sparc -p 'test_*.py' -v

## Next gate

Pin and authenticate an actual SCKAN release/export, reproduce selected upstream connectivity queries, then freeze independently sourced ASCENT reference outputs and tolerances before running the first real numerical reproduction.
