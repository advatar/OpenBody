# OpenBody intervention source observations

Status: version 1.0 source-observation profile

Schema: `schemas/intervention-observation.schema.json`

Examples: `examples/cymbathera-intervention-observation.v1.json`,
`examples/paced-breathing-intervention-observation.v1.json`

## Purpose and boundary

This profile carries a patient-authorized record that an intervention occurred,
the dose facts the source can actually support, selected before/end/follow-up
measurements, derived-analysis references, and an optional patient-reported
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

OpenBody **hosts the contract**. It does not take custody of the observations,
make consent or disclosure decisions (InVivo), perform clinical intake or
record-keeping (ProvidEHR), or verify identity. The reference host has no
ingestion route for this profile.

## What is enforced, and what is not

`validate_intervention_observation` (reference/python) and
`tools/validate_openbody.py` enforce the rows marked *enforced*. Everything else
is a producer or consumer requirement, and this repository does not check it.

| Property | Status | Where |
| --- | --- | --- |
| Closed document. No field outside the schema at any depth. | enforced | schema `additionalProperties: false` |
| No raw sample arrays are carried. Every number is a scalar, and the metric vocabulary has no voltage or sample metric. | enforced | schema |
| Every number is finite (no NaN or ±Infinity). | enforced | validator |
| `projection_class` is `source_observation`, and the document fails `openbody.clinical-assertion-reference/1.0` even if relabelled. | enforced | schema; `validate_clinical_reference` |
| A dose with `status: unavailable` carries no `value` and no `unit`. Other statuses require both. | enforced | schema |
| Scopes are registered coordinates. | enforced | validator (`unsupported_scope`) |
| Timestamps are RFC 3339 with an offset. `ended_at >= started_at`. | enforced | schema format; validator (`invalid_interval`) |
| `before` is observed at or before the start. `end` is observed at or after the start. `follow_up` is observed at or after the end. The patient response is recorded at or after the start. | enforced | validator (`invalid_measurement_phase`, `invalid_interval`) |
| `disclosure.expires_at`, if present, is later than `authorized_at`. | enforced | validator (`invalid_consent_window`) |
| `disclosure.fields` names exactly the top-level sections carried. It names nothing absent or empty, and nothing carried is left undisclosed. | enforced | validator (`disclosed_field_missing`, `undisclosed_content_present`) |
| `claim_boundary` is fixed to `observation` with no causal, diagnostic or treatment claim. There is no free-text interpretation field, and `user_response.felt` is a closed vocabulary. | enforced (structure only) | schema |
| `follow_up_offset_seconds` matches `observed_at - ended_at`. | not checked | producer label |
| Units match their metric. | not checked | free text in 1.0 |
| Identifier strings (`observation_id`, `intervention_id`, `protocol_id`, dose `name`, device, `source_ref`, `canonical_ref`) carry no claims. | not checkable | opaque, bounded producer labels |
| Missing measurements were omitted, not filled in. | not checkable from the payload | producer requirement |
| The subject binding is valid, current and unrevoked. | not checked | consumer requirement |
| The consent exists, covers this purpose, subject and recipient, and is current and unrevoked. | not checked | consumer requirement |
| Replay-safe retries; ID reuse with different content fails. | not implemented here | consumer requirement |
| A referenced artifact contains no raw signal. | not checkable | producer attestation |

### The disclosure allowlist is a declaration

`disclosure.fields` must match what is carried, so a payload cannot present
undisclosed content as disclosed. It does not produce a minimized projection.
Minimization happens before this document is built: omit a section to withhold
it. The allowlist works at section granularity only; it has no nested paths.

## Producer requirements

- **Missingness.** Absent measurements are omitted, never filled with demo,
  zero, or inferred values. A measured zero (for example `step_count: 0`) is a
  legitimate value. The profile cannot tell a measured zero from a fabricated
  one, so it relies on this rule being followed. In 1.0, omission is the only
  way to say "not observed".
- **Raw signal.** `contains_raw_signal: false` is the producer's attestation
  that the referenced artifact is not a raw signal. Raw ECG/EEG stays under
  custody elsewhere (for example InVivo). The validator cannot resolve a
  `canonical_ref`, so a reference that actually names raw data breaks this
  attestation without being detected. This profile never carries the samples
  themselves.
- **Identifiers are labels.** Do not put findings, effects, diagnoses or
  recommendations in identifier strings. The schema bounds their length but
  cannot read their meaning.

## Consumer requirements

A receiving system must do the following. None of it is implemented or checked
in this repository.

- **Subject binding.** `subject_binding.status: "verified"` is the producer's
  declaration. The receiver independently verifies the binding (OAuth/SMART
  grant or equivalent) against its issuer and revocation reference, and rejects
  cross-patient disclosure. The validator checks only that the fields are
  present and well-formed.
- **Consent.** `consent_ref` is a reference. The receiver resolves it, then
  checks purpose, subject, recipient, scope, expiry and revocation at the time
  of receipt. The validator checks only presence, URI form and window ordering.
  The profile has no recipient or audience field.
- **Storage.** Store the payload as patient-reported/source evidence with
  provenance and audit, not as clinician-verified fact.
- **Replay and ID reuse.** A retry with the same `observation_id` and identical
  canonical content is replay-safe. Reusing an ID for different content fails
  closed.
- **Model use.** A model host may use the source observation as evidence. Any
  resulting `BodyState`, `ObservedOutcome`, or other derived object needs its own
  model receipt, uncertainty, applicability, validity, and
  `openbody.clinical-assertion-reference/1.0` projection before ProvidEHR
  clinical admission. The source observation itself must continue to fail that
  assertion schema.

## Derived-analysis references

`evidence` items of kind `vagus_analysis` or `eeg_derived_features` point at
analyses computed by the source application's own software. Those analyses are
derived, not observed. `claim_boundary.epistemic_class: "observation"` describes
this document, not the referenced artifact. Resolving a reference does not make
its content OpenBody-derived. An evidence item cannot carry a conclusion, a
finding, or its own epistemic class; it carries only a reference, a digest, and
a time.

## About the examples

Both examples are synthetic. Their subjects, bindings, consent references and
digests are placeholders.

The Cymbathera example shows the shape a real therapy app would send. It does
not show:

- a treatment effect. Heart rate 71 → 65 beats/min before and after one session
  is two observations, not a response to stimulation.
- target engagement. An HRV value is not evidence of vagal activation.
- a mechanism. `cymbathera.transcutaneous-vagus-stimulation` is the product's
  identifier, not a claim that taVNS was delivered or reached its target.
  Intensity is `unavailable` because the source cannot report it.
- clinical-grade measurement. HealthKit references are consumer-device data.
- efficacy. `felt: better` is a patient report.

The paced-breathing example is product-neutral. It shows a planned and a
patient-reported dose, an unavailable dimension, a legitimate measured zero,
and an omitted optional section that is correspondingly not disclosed.

## Known limits of 1.0 and candidates for 1.1

These are additive and would be `1.1`. None changes what a valid 1.0 document
means.

- Explicit missingness: an `availability` status on measurements
  (`observed`/`not_observed`/`unavailable`), as `openbody.admitted-observation.v1`
  already does with explicit nulls.
- Metric/unit binding via UCUM.
- Neutral evidence kinds in place of product-derived `vagus_analysis` and the
  `heart_breath_synchronization` metric, kept as deprecated aliases.
- An explicit recipient/audience on `disclosure`.
