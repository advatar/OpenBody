# OpenBody intervention source observations

Status: version 1.0 source-observation profile

Schema: `schemas/intervention-observation.schema.json`

Example: `examples/cymbathera-intervention-observation.v1.json`

## Purpose and boundary

This profile carries a patient-authorized record that an intervention occurred,
the dose facts the source can actually support, selected before/end/follow-up
measurements, derived-analysis references, and optional patient-reported response.
It supports native therapy apps that disclose selected evidence to a clinical
system such as ProvidEHR.

It is deliberately not a core `BodyState` and not a clinical assertion:

```text
HealthKit/device/app observations
        -> intervention source observation
        -> authorized clinical intake and provenance

source observation -> OpenBody model execution
                   -> derived OpenBody object
                   -> clinical assertion reference
                   -> ProvidEHR clinical admission/review
```

The first path records what was observed. The second path is required before a
physiology conclusion may be presented as OpenBody-derived clinical evidence.
Changing `projection_class` does not convert one into the other.

FHIR, openEHR, IEEE 11073, and the originating health store remain authoritative
for their domains. This profile is a bounded computational/evidence handoff and
does not redefine those standards or authorize write-back into a legal record.

## Required safety properties

- `subject_binding.status` is `verified`; the receiver independently verifies
  the OAuth/SMART or equivalent grant and rejects cross-patient disclosure.
- disclosure names a purpose, consent receipt, authorization time, and an exact
  field allowlist.
- absent measurements are omitted. They are never filled with demo, zero, or
  inferred values.
- every evidence item contains a digest and `contains_raw_signal: false`.
  Raw ECG and EEG voltage/sample arrays are outside this profile.
- dose dimensions say whether a value was planned, observed, patient reported,
  or unavailable. `unavailable` cannot carry a numeric value.
- the claim boundary is structurally fixed to observation, with no causal,
  diagnostic, or treatment-recommendation claim.

## Consumer behavior

A clinical receiver stores this payload as patient-reported/source evidence with
provenance and audit, not as clinician-verified fact. Retries with the same
`observation_id` and identical canonical content are replay-safe; reuse of an ID
for different content fails closed.

A model host may use the source observation as evidence for an OpenBody model.
Any resulting `BodyState`, `ObservedOutcome`, or other derived object needs its
own model receipt, uncertainty, applicability, validity, and
`openbody.clinical-assertion-reference/1.0` projection before ProvidEHR clinical
admission. The source observation itself must continue to fail that assertion
schema.
