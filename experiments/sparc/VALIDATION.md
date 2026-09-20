# SPARC M0 validation

This directory is a research candidate, isolated from the frozen OpenBody protocol/runtime.

## M0 acceptance

1. A SCKAN export is accepted only with explicit schema checks and, when supplied, an exact SHA-256 digest.
2. Native subject/predicate/object, species and evidence fields are returned without inverse/transitive/signal-flow inference.
3. No match is reported as unknown coverage, not a negative biological assertion.
4. Numerical reproduction compares only identically bound model/artifact/input/dataset/species/modality/metric/unit cases.
5. Failed, missing, abstained and invalid outputs cannot become a pass.
6. A numerical pass is never labelled biological or clinical validation.

## Still open

Upstream SCKAN authenticity/reuse verification; real export reconciliation; upstream query reproduction; ASCENT artifact execution and reference-output reproduction; full OpenBody conformance; hosted CI; and any read-only Cymba consumer.
