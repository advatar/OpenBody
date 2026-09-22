# OpenBody intervention source observations

Status: version 2.0 source-observation profile

Schema: `schemas/intervention-observation.schema.json`

Examples: `examples/cymbathera-intervention-observation.v2.json`,
`examples/paced-breathing-intervention-observation.v2.json`

Reference validator and intake: `reference/python/openbody_ref/intervention_observation.py`

## Purpose and boundary

This profile carries a patient-authorized record that an intervention occurred,
the dose facts the source can actually support, selected before/end/follow-up
measurements, references to derived analyses, and an optional patient-reported
response. It supports native therapy apps that disclose selected evidence to a
clinical system such as ProvidEHR.

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

### Five things that must not be confused

| Object | Who asserts it | Contract |
| --- | --- | --- |
| Source observation | The source app or device, with patient authorization | this profile |
| Admitted clinical observation | A clinical source authority, after normalization | `openbody.admitted-observation.v1` |
| Derived physiological state | An OpenBody model execution, with a receipt | `openbody.schema.json` (`BodyState`, `ObservedOutcome`, …) |
| Clinical assertion | A projection of a derived object that passed qualification | `openbody.clinical-assertion-reference/1.0` |
| Clinical record | The EHR | FHIR / openEHR, not OpenBody |

A source observation is the weakest of these. It has not been admitted by a
clinical authority and no model has run on it. Nothing in it is an OpenBody
conclusion.

### Why this contract lives in OpenBody, and where that stops

OpenBody is the neutral layer that every party already pins. The main job of
this profile is a negative one: an intervention record must be structurally
unable to pass as an OpenBody-derived object. That boundary can only be defined
and tested next to the clinical-assertion contract it must fail. The profile is
also the input shape an OpenBody model would read as evidence.

OpenBody **hosts the contract** and a reference intake that shows what a
receiver must check. It does not take custody of the observations, make consent
or disclosure decisions (InVivo), perform clinical intake or record-keeping
(ProvidEHR), or verify identity. The reference host has no ingestion route for
this profile.

## Shape

- **Measurements** are one entry per metric and phase. The phase is `before`,
  `end` or `follow_up`. Each entry is either:
  - `status: "observed"`, with a value, the metric's fixed UCUM unit,
    `observed_at`, a `source_ref` URI, and an `origin` (`consumer_device`,
    `medical_device`, `app_computed` or `patient_reported`); or
  - `status: "not_observed"`, with a `reason` and nothing else.

  A metric that was never part of the record is simply omitted.
- **Units and ranges are fixed per metric and per dose dimension.** For example
  heart rate is `/min` and ≥ 0, EEG relative power is `1` within [0, 1], and step
  count is a non-negative integer of `{steps}`.
- **Dose dimensions** come from a closed vocabulary (`duration`, `frequency`,
  `pulse_width`, `current_amplitude`, `intensity_setting`, `breathing_rate`,
  `repetitions`, `temperature`, `illuminance`). Each dimension appears at most
  once per status, so a planned and an observed duration can sit side by side.
  An `unavailable` dimension carries neither value nor unit.
- **Identifiers** (`observation_id`, `subject`, `intervention_id`,
  `protocol_id`, versions, `app_id`, device) are tokens without whitespace.
  References (`source_ref`, `canonical_ref`, and binding and consent references)
  are URIs.
- **Evidence** items are `device_sample_summary`, `derived_analysis` or
  `patient_report`. A `derived_analysis` must name the (non-OpenBody) software
  that produced it in `produced_by`; other kinds must not.
- **Disclosure** names a purpose, a consent reference, a **recipient**, the
  authorization time, an optional expiry, and the exact sections carried.

## What is enforced, and what is not

| Property | Status | Where |
| --- | --- | --- |
| Closed document. No field outside the schema at any depth. | enforced | schema |
| No raw sample arrays or series. Every number is a scalar; there is at most one entry per metric and phase, and at most 64 entries. | enforced | schema; validator (`duplicate_measurement`) |
| Every number is finite. | enforced | validator |
| Units and ranges fixed per metric and dose dimension. | enforced | schema |
| Missing data is explicit: `not_observed` carries a reason and no value, unit, time, reference or origin; `observed` carries all of them. | enforced | schema |
| A dose with `status: unavailable` carries no value and no unit. Other statuses require both. Each dimension appears once per status. | enforced | schema; validator (`duplicate_dose_dimension`) |
| `projection_class` is `source_observation`, and the document fails `openbody.clinical-assertion-reference/1.0` even if relabelled. | enforced | schema; `validate_clinical_reference` |
| Scopes are registered coordinates. | enforced | validator (`unsupported_scope`) |
| Timestamps are RFC 3339 with an offset. `ended_at >= started_at`. The patient response is recorded at or after the start. | enforced | schema; validator (`invalid_interval`) |
| Observed `before` values are at or before the start, `end` values at or after the start, `follow_up` values at or after the end. | enforced | validator (`invalid_measurement_phase`) |
| The subject binding was verified no later than the disclosure was authorized. | enforced | validator (`invalid_subject_binding`) |
| `expires_at`, if present, is later than `authorized_at`. | enforced | validator (`invalid_consent_window`) |
| `disclosure.fields` names exactly the sections carried. | enforced | validator (`disclosed_field_missing`, `undisclosed_content_present`) |
| No prose in identifiers or references; no free-text interpretation field; closed vocabularies for response, dose, metric and evidence kind; `claim_boundary` fixed to observation. | enforced | schema |
| A derived analysis names its producer. | enforced | schema |
| Identifier tokens carry no meaning (`patient_responded_to_therapy` is a valid token). | not checkable | consumers treat identifiers as opaque |
| An `observed` value was actually measured, not invented. | not checkable from the payload | producer requirement |
| A referenced artifact contains no raw signal. | not checkable | producer attestation (`contains_raw_signal: false`) |
| The subject binding is valid, current and unrevoked. | enforced at intake | `InterventionObservationIntake` via a required verifier |
| The consent is genuine, covers the purpose and subject, and is unrevoked. | enforced at intake | `InterventionObservationIntake` via a required verifier |
| The consent window covers the time of receipt; the recipient is the receiver. | enforced at intake | `InterventionObservationIntake` (`consent_not_yet_valid`, `consent_expired`, `recipient_mismatch`) |
| Identical retries are replays; reusing an ID for different content fails. | enforced at intake | `InterventionObservationIntake` (`observation_id_conflict`) |

"Enforced at intake" means the reference intake refuses to accept without it.
The intake does not implement the verification itself: it requires the receiver
to supply `verify_subject_binding` and `verify_consent`. These have no defaults,
and a verifier that errors or returns anything but `True` counts as a refusal.
The intake keeps its replay record in memory; a production receiver persists it.

### The disclosure allowlist is a declaration

`disclosure.fields` must match what is carried, so a payload cannot present
undisclosed content as disclosed. It does not produce a minimized projection.
Minimization happens before this document is built: omit a section to withhold
it. The allowlist works at section granularity only; it has no nested paths.

## Producer requirements

- **Missingness.** Report a value you expected but do not have as
  `not_observed` with a reason. Never fill it with a demo, zero or inferred
  value. A measured zero (for example `step_count: 0`) is a legitimate
  observation. The profile cannot tell a measured zero from a fabricated one;
  it gives you an honest way to say "no value" and relies on you to use it.
- **Origin.** Use `consumer_device` for wearables and phones, and
  `app_computed` for values your software derives (for example HRV computed
  from beat intervals). Reserve `medical_device` for regulated measurement
  devices.
- **Raw signal.** `contains_raw_signal: false` is your attestation that the
  referenced artifact is not a raw signal. Raw ECG/EEG stays under custody
  elsewhere (for example InVivo). The validator cannot resolve a reference, so a
  reference that actually names raw data breaks this attestation without being
  detected.
- **Identifiers are labels.** The token pattern stops prose, not meaning. Do not
  encode findings, effects, diagnoses or recommendations in identifiers.

## Receiver requirements

Use `InterventionObservationIntake`, or do what it does:

- verify the subject binding against its issuer and revocation reference (for
  example the OAuth/SMART grant), and reject cross-patient disclosure;
- resolve the consent and check purpose, subject, scope and revocation;
- check the recipient and the consent window at the time of receipt;
- treat identical retries as replays and conflicting reuse of an ID as an
  error;
- store the payload as patient-reported/source evidence with provenance and
  audit, not as clinician-verified fact.

A model host may use the source observation as evidence. Any resulting
`BodyState`, `ObservedOutcome`, or other derived object needs its own model
receipt, uncertainty, applicability, validity, and
`openbody.clinical-assertion-reference/1.0` projection before ProvidEHR clinical
admission. The source observation itself must continue to fail that assertion
schema.

## Derived-analysis references

A `derived_analysis` evidence item points at an analysis computed by the named
`produced_by` software, not by OpenBody. That analysis is derived, not observed.
`claim_boundary.epistemic_class: "observation"` describes this document, not the
referenced artifact. Resolving a reference does not make its content
OpenBody-derived. An evidence item cannot carry a conclusion, a finding or its
own epistemic class; it carries only a reference, a digest, a time and a
producer.

## About the examples

Both examples are synthetic. Their subjects, bindings, consent references and
digests are placeholders.

The Cymbathera example shows the shape a real therapy app would send. It does
not show:

- a treatment effect. Heart rate 71 → 65 /min before and after one session is
  two observations, not a response to stimulation.
- target engagement. An HRV value is not evidence of vagal activation.
- a mechanism. `cymbathera.transcutaneous-vagus-stimulation` is the product's
  identifier, not a claim that taVNS was delivered or reached its target.
  `intensity_setting` is `unavailable` because the source cannot report it.
- clinical-grade measurement. The values are `consumer_device` data.
- efficacy. `felt: better` is a patient report.

The paced-breathing example is product-neutral. It shows a planned and a
patient-reported dose, an unavailable dimension, a legitimate measured zero, a
`not_observed` value, and an omitted optional section that is correspondingly
not disclosed.

## Version history

- **2.0**: explicit missingness and origin; UCUM units and ranges bound per
  metric and dose dimension; a closed dose vocabulary; token identifiers and URI
  references; neutral evidence kinds with a named producer for derived
  analyses; a required recipient; one entry per metric and phase; subject
  binding ordered before disclosure; `follow_up_offset_seconds` removed (it is
  derivable from the times); the product-specific
  `heart_breath_synchronization` metric removed; a reference intake.
- **1.0**: withdrawn before any producer or consumer existed. The conformance
  validator rejects 1.0 documents.
