# Whole-person observation envelope and state snapshot

Status: version 1.0 source-neutral contract with a local conformance corpus.
Not part of the frozen OpenBody 0.1 core schema (additive profile).

Tracking issue: [#30](https://github.com/advatar/OpenBody/issues/30).

- Envelope schema: [`schemas/whole-person-observation.schema.json`](../schemas/whole-person-observation.schema.json) (`openbody.whole-person-observation/1.0`)
- Snapshot schema: [`schemas/whole-person-state.schema.json`](../schemas/whole-person-state.schema.json) (`openbody.whole-person-state/1.0`)
- Reference assembler/validator: [`reference/python/openbody_ref/whole_person.py`](../reference/python/openbody_ref/whole_person.py)
- Conformance corpus: [`fixtures/whole-person-state/v1/`](../fixtures/whole-person-state/v1/) (`inputs.json`, `snapshot.golden.json`, `vectors.json`)
- Checker: `python tools/check_whole_person_state.py` (also run by `tools/validate_openbody.py` in conformance CI)

## Boundary

```text
InVivo raw custody / consent  --->  whole-person observation envelope (reference, digest, provenance)
ProvidEHR admitted observation --->  envelope.clinical_link (reference only, never a copy)
                                           |
                                           v
                          whole-person state snapshot (deterministic projection)
                                           |
                     clinical use still requires the existing path:
                     OpenBody model execution -> clinical assertion reference -> ProvidEHR admission/review
```

- InVivo (repository Metabolog) owns raw observation custody, consent and disclosure.
  ProvidEHR owns clinical evidence, workflow and write-back. OpenBody owns this
  neutral, reference-oriented contract. The snapshot is not a medical record,
  not a `BodyState`, and not a clinical assertion
  (`claim_boundary.clinical_assertion = false`, `authority_granted = false`).
- `origin` (where the value came from) is orthogonal to `epistemic_status`
  (observed, reported, imported, derived, inferred, imputed, clinician_validated).
  Import or a signature alone is not validation: `clinician_validated` requires a
  receipt on the existing admission path, `reported` is only possible for
  self-report/conversation origins, and a `model_transform` origin can only be
  derived, inferred or imputed (with derivation parents bound by envelope digest).
- `context_level` separates individual physiology from household/community
  context (for example air quality), which never counts as a personal measurement.

## Assembly rules (`openbody.whole-person-assembly-policy/1.0`)

| Acceptance criterion (issue #30) | Enforcement |
|---|---|
| No silent source-priority inference | Latest current measurement per exact `source_id`; if sources disagree the entry is `unresolved_conflict`, no value is selected and it cannot be an admission candidate. A clinician-validated record does not win a conflict either. `claim_boundary.source_priority = "none"`. |
| Unknown uncertainty stays unknown | A present value must declare `quantified` (with method and SD/interval) or `unknown`; `unknown` cannot carry numbers and blocks clinical use (`uncertainty_unknown`). Uncertainty is copied unchanged, in `source_unit`. |
| Imputation never masquerades as measurement | `imputed` requires derivation parents, is kept as a candidate but never enters `basis`; an entry with only imputed current values is `imputed_only`. `validate_state` rejects an imputed id in `basis`. |
| Exact provenance survives state assembly | Every candidate copies source (id, kind, version, device, record ref/digest), times, clock status, source value/unit, uncertainty, quality, derivation, clinical link and validation, bound to the input `envelope_digest`; `validate_state` rejects candidates that are not listed inputs. |
| Snapshot is deterministic | Inputs are de-duplicated by id+digest, sorted, and assembled against explicit `as_of`, `purpose` and host-resolved revocations; `snapshot_digest` covers the whole snapshot. Input order and identical replay do not change it; a replay with different content is rejected. |
| Clinical assertions still need their receipt path | `clinical_use.admission_candidate` only says that no blocker applies; `requires` names `openbody.clinical-assertion-reference/1.0`. Model outputs are blocked with `model_output_requires_receipt`. |

Exclusions (kept in `exclusions` with the input digest): revoked source, record,
clinical version, consent, authority or subject binding; consent not yet granted
or expired; purpose not permitted; not yet ingested or effective after `as_of`;
unrecognized unit (never guessed); and derivation parents that are missing,
digest-mismatched, bound to another subject, or themselves excluded.

A later non-wear or missing record from the same source does not erase an
earlier current measurement; both stay visible as candidates.

Blockers: `resolution_*` (conflict, stale_only, imputed_only, missing_only),
`uncertainty_unknown`, `quality_not_acceptable`, `not_individual_measurement`,
`model_output_requires_receipt`, `clock_unknown`.

Clock drift: `effective_start` may exceed `ingested_at` by at most 300 s; a
`corrected` clock must satisfy `device_reported_start + correction_seconds =
effective_start`; an `unknown` clock blocks clinical use.

## Source mapping

| Source | origin | epistemic_status | domain / code | Notes |
|---|---|---|---|---|
| CGM | device_sensor | observed | glucose / LOINC 99504-3 | mmol/L or mg/dL; 1 h freshness |
| Sleep (wearable) | device_sensor | observed | sleep / LOINC 93832-4 | min or h |
| HRV (wearable) | device_sensor | observed | heart_rate_variability / LOINC 80404-7 | ms or s |
| Heart rate / non-wear | device_sensor | observed | heart_rate / LOINC 8867-4 | `missingness.status = non_wear` carries no value |
| Symptoms (app diary) | self_report | reported | symptom / SNOMED CT | categorical, uncertainty unknown |
| Meals (conversation, TwinSuite) | conversation | reported | meal / text | candidate observation only |
| Labs (LIS) | laboratory | observed / clinician_validated | laboratory / LOINC | units keyed by LOINC code |
| Clinical record (ProvidEHR) | clinical_record | imported | any | `clinical_link` to `openbody.admitted-observation.v1` required |
| Environment | environmental_feed | observed | environment | `context_level` household/community |
| Model output | model_transform | derived / inferred / imputed | any | transform id/version + parent digests |

## Reuse / gap matrix

| Existing contract | Reused | Gap closed here |
|---|---|---|
| `openbody.admitted-observation.v1` (ProvidEHR clinical projection) | Referenced by `clinical_link` (id, version ref, content digest); not copied | Non-clinical sources (wearable, self-report, conversation, environment) and a longitudinal view across them |
| `openbody.intervention-observation/1.0` | Subject binding, revocation references, missingness and claim-boundary patterns | Generic per-measurement envelope; intervention events stay in their own profile |
| Core `BodyState` (0.1, frozen) | Coordinate registry (`scope`), fail-closed style | Snapshot is explicitly not a BodyState: no modeled state, no confidence |
| `openbody.clinical-assertion-reference/1.0` | Remains the only path to clinical use | Snapshot names it as required rather than duplicating it |
| `PersonalAdaptiveState` (research) | Not used | Snapshot is an input for #24 simulation/counterfactual research, not adaptive state |
| Deterministic longitudinal query (research) | Same determinism/abstention philosophy | Multi-source, multi-epistemic state rather than single-series queries |

## Qualification status

- Implemented and locally qualified: schemas, reference assembler, 1 golden
  snapshot + 52 adversarial/conformance vectors covering EHR, wearable, lab,
  behavior and environment inputs; unit normalization; clock drift; conflicting
  sources; stale values; missingness/non-wear; revocation; imputed-vs-observed;
  replay; provenance loss; state tampering.
- CI: the corpus runs inside `tools/validate_openbody.py`.
- Not qualified here (other repositories): InVivo native consumer
  (Metabolog #1129/#1144), TwinSuite conversational adapter (#144), ProvidEHR
  encounter context integration (#600). The corpus is synthetic; it is not
  real-cohort physiology, patient/consent binding evidence, or deployed
  endpoint qualification. The reference host does not mount this profile.
