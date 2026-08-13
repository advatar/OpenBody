# OpenBody clinical assertion references

Status: version 1.0 consumer projection contract

Schema: `schemas/clinical-assertion-reference.schema.json`

Fixtures: `examples/clinical-assertion-references.v1.json`

Tracking: https://github.com/advatar/OpenBody/issues/6

## Purpose

Clinical systems need to refer to model-derived physiology without copying it
into a generic observation or treating a scalar confidence as biological
certainty. The clinical assertion reference is a projection of identity,
lineage, applicability, uncertainty, epistemic class, and current validity. It
does not create a second `BodyState` and it is not a clinical attestation.

The reference is intentionally different from a source observation:

```text
raw observation -> InVivo custody -> OpenBody model -> OpenBody object
                                                   -> clinical assertion reference
                                                   -> ProvidEHR policy/workflow
```

`projection_class` is always `openbody_reference`. A source observation uses a
different consumer-owned type and fails this schema. `BodyObservation` is also
excluded from `object_kind` so the type boundary cannot be bypassed by changing
only the projection-class label.

## Immutable reference identity

The following fields identify what was originally produced and do not change:

- `reference_id`;
- `object_kind` and `canonical_ref`;
- `content_digest` of the dereferenced OpenBody object;
- `subject` and the binding receipt used at projection time;
- contract schema/registry identity;
- model/execution receipt;
- evidence lineage and epistemic class.

Canonical object digests use UTF-8 JSON with recursively sorted object keys,
no insignificant whitespace, array order preserved, and non-ASCII characters
unescaped. This matches `openbody_ref.validation.canonical_digest`.

## Re-resolved validity

`validity.validity_ref` is mandatory and mutable when dereferenced. A digest
proves which bytes were asserted; it does not prove those bytes remain valid.
Consumers must resolve the pointer before admission and periodically while a
reference influences active clinical work.

- `valid`: eligible for further domain-policy evaluation when every other gate
  passes.
- `stale`: retain provenance, do not admit as current evidence.
- `retracted`: block admission and reopen downstream work where policy used the
  assertion; preserve `retraction_ref` and time.
- `superseded`: do not silently substitute. Resolve `superseded_by`, validate it
  as a new reference, and record the transition.
- `invalid` or `unknown`: quarantine/fail closed.

Retraction and supersession never mutate the immutable content digest.

## Subject binding

OpenBody 0.1 enforces a single consistent subject but cannot prove that the
subject denotes the patient a clinical caller means. `subject_binding` is an
external receipt reference. Clinical admission requires `verified`; an
`unverified`, `invalid`, or `unresolvable` binding fails closed. Possession of a
binding URI is not proof: the consumer verifies its digest, issuer, expiry, and
revocation endpoint under platform identity policy.

## Applicability, uncertainty, OOD, and abstention

Clinical admission requires all of:

- applicability status `applicable` for exactly the referenced subject and
  every projected scope;
- uncertainty status `known` with epistemic, aleatoric, coverage, calibration,
  interval, OOD, and reasons preserved;
- `out_of_distribution == false`;
- validity status `valid` and no expired `valid_until`;
- abstention status `not_abstained`;
- a matching dereferenced object digest and supported contract/registry.

`unknown`, `insufficient`, `contradictory`, `inapplicable`, and
`out_of_distribution` are distinct states. None may be represented as a
confident fact. An `Abstention` is a valid OpenBody response but inadmissible as
a physiological assertion.

The scalar confidence used by a presentation or extraction layer is not part
of this contract and must not replace any field above.

## Consumer reactions

Triage preserves the reference and its explicit state. It does not reinterpret
OpenBody uncertainty and does not call OpenBody on the offline deterministic
urgency path.

ProvidEHR verifies the reference, subject binding, digest, registry, current
validity, and domain policy. It owns any CarePlan obligation, completion,
reopening, clinician attention, and audit receipt caused by the evidence.

Neither OpenBody nor this reference authorizes diagnosis, treatment, workflow
completion, clinician attestation, or legal-record write-back.

## Fixture bundle

The fixture bundle uses RFC 7396 merge patches over one complete base
reference. Each case names the resolved OpenBody example, the expected
admission result, and a stable error code. It covers:

- applicable/known/valid;
- unknown or insufficient;
- contradictory;
- inapplicable and OOD;
- abstained;
- stale;
- retracted;
- superseded;
- digest mismatch;
- unresolved subject binding;
- a source observation that must not decode as an OpenBody reference.

`openbody_ref.clinical_reference` is the reference expander and validator.
Triage and ProvidEHR should consume the bundle directly rather than copy its
examples into independently drifting test data.
