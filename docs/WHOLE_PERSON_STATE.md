# Whole-person observation envelope and state snapshot

Status: version 1.0 source-neutral contract with a local conformance corpus.
Not part of the frozen OpenBody 0.1 core schema (additive profile).

Tracking issue: [#30](https://github.com/advatar/OpenBody/issues/30).

- Envelope schema: [`schemas/whole-person-observation.schema.json`](../schemas/whole-person-observation.schema.json) (`openbody.whole-person-observation/1.0`)
- Snapshot schema: [`schemas/whole-person-state.schema.json`](../schemas/whole-person-state.schema.json) (`openbody.whole-person-state/1.0`)
- Reference assembler/validator: [`reference/python/openbody_ref/whole_person.py`](../reference/python/openbody_ref/whole_person.py)
- Conformance corpus: [`fixtures/whole-person-state/v1/`](../fixtures/whole-person-state/v1/) (`inputs.json`, `snapshot.golden.json`, `vectors.json`)
- Checker: `python tools/check_whole_person_state.py` (also run by `tools/validate_openbody.py` in conformance CI)
- Consumer mapping: [`reference/python/openbody_ref/whole_person_mapping.py`](../reference/python/openbody_ref/whole_person_mapping.py),
  [`fixtures/whole-person-state/v1/consumer-mapping.json`](../fixtures/whole-person-state/v1/consumer-mapping.json)
  (`openbody.whole-person-consumer-mapping/1.0`) and
  [`fixtures/whole-person-state/v1/interop-vectors.json`](../fixtures/whole-person-state/v1/interop-vectors.json);
  see [Consumer mapping](#consumer-mapping)

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

Within one source, every measured candidate at that source's latest reference
time is kept in `basis`; they are never tie-broken by `observation_id`. If
they disagree the entry is `unresolved_conflict`; if they agree and come from
one source it stays `single_source`.

Source identity and entry keys must be unambiguous across all inputs, or the
whole assembly is rejected (consumers mint envelopes independently, so these
disagreements must not become silent corroboration, version choice or a split
entry):

| Rejection | Rule |
|---|---|
| `source_identity_conflict` | One `source.record_ref` belongs to exactly one `source.source_id`. |
| `record_version_conflict` | One `source.record_ref` carries one `record_digest`; a revised record needs a version-specific `record_ref` so the superseded version can be revoked alone. |
| `code_domain_ambiguous` | One coded concept (`system` + `code`) is used in exactly one `domain`. |

`validate_state` also checks internal consistency: every `basis` id is a
candidate of its entry, each entry's `resolution`, `basis`, candidate order and
`clinical_use` equal what this policy derives from its candidates
(`state_inconsistent` otherwise), and every input is accounted for exactly once
as a candidate or an exclusion.

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
  snapshot + 64 adversarial/conformance vectors (52 original + 12 added in the
  PR #44 consumer review: source identity, record versions, code/domain
  ambiguity, same-time ties, state consistency) covering EHR, wearable, lab,
  behavior and environment inputs; unit normalization; clock drift; conflicting
  sources; stale values; missingness/non-wear; revocation; imputed-vs-observed;
  replay; provenance loss; state tampering.
- CI: the corpus runs inside `tools/validate_openbody.py`.
- Not qualified here (other repositories): InVivo native consumer
  (Metabolog #1129/#1144), TwinSuite conversational adapter (#144), ProvidEHR
  encounter context integration (#600). The corpus is synthetic; it is not
  real-cohort physiology, patient/consent binding evidence, or deployed
  endpoint qualification. The reference host does not mount this profile.

## Consumer mapping

Mapping version `openbody.whole-person-consumer-mapping/1.0`. It is a reviewed
proposal, not an accepted contract (see
[Open questions for acceptance](#open-questions-for-acceptance)). The rules below
are executable in `openbody_ref.whole_person_mapping`; each consumer's
representative records, their expected envelopes or refusal codes, and one
cross-consumer snapshot are frozen in `consumer-mapping.json` and checked by
`tools/check_whole_person_state.py`, `tools/validate_openbody.py` and
`reference/python/tests/test_whole_person_consumer_mapping.py`. Consumers
implement the same rules natively and use the fixture as their shared vectors.

Upstream versions read for this mapping:

| Consumer | Upstream consumed | Records mapped |
|---|---|---|
| Metabolog / InVivo (#1129, #1144) | `advatar/Metabolog` main `ec586aeb`, containing merged #1131 (`167f52b3`) and #1145 (`204c3348`) | `HealthTimelineEntryRecord`, the `openbody.admitted-observation.v1` document behind `OpenBodyAdmittedObservation`, `OpenBodyStateRecord`, `OpenBodyEpistemicClass`, Cymbathera quality |
| ProvidEHR ambient evidence (#600) | PR #689 head `f01ee445` (`crates/ambient-evidence`, open) | `longitudinal::Contribution` with `SourceKey`, `SourceAvailability`, `CaptureConsent` |
| TwinSuite conversational adapter (#144) | Issue #144 acceptance criteria; TwinSuite main `9bd339a3` has no conversation-timeline code yet | A said / confirmed / inferred conversation candidate held in InVivo custody |

### Rules shared by every consumer

- **Subject.** Consumers never put their own patient identifier in `subject`.
  The custodian supplies the pseudonymous subject and a verified
  `subject_binding`. A ProvidEHR `ehr_id`, an InVivo `subjectID` and a TwinSuite
  user are never treated as equal by inference.
- **Source identity.** `source_id` is the consumer's own conflict unit, and
  `record_ref` names one immutable record version (`:rev:` or `::v`). One
  record belongs to one source and has one digest; the assembler enforces this.
  The custodian that holds the raw record mints its `record_ref`. When TwinSuite
  statements are held in InVivo custody, InVivo is the only emitter, so the same
  utterance is never emitted twice under two sources.
- **Time.** `effective_start` is when the event happened (sample, clinical,
  spoken time), and `ingested_at` is when the custodian took it in. The clock is
  `synchronized` only when the producing clock is known to be. Typed-in or
  spoken times are `unknown`, which blocks clinical use.
- **Uncertainty.** Uncertainty is `quantified` only with a method and an SD or
  interval in the source unit. Model `confidence`, Cymbathera quality-derived
  confidence, ASR confidence, speaker hedging and user confirmation are never
  uncertainty. Numbers that 1.0 cannot express (the admitted-observation
  epistemic/aleatoric/coverage fractions) are refused, not dropped.
- **Consent and revocation.** Consent and authority references come from the
  custodian. Withdrawal, a revoked source, a revoked clinical version and a
  superseded record revision all reach the assembler as host-resolved
  `revoked` references. A correction is a new record version plus revocation of
  the old one, never an in-place replacement.
- **Epistemic status.** A device-provenanced sample is `observed`. A person's
  typed-in, diary or spoken value is `reported`, even when a meter produced the
  number. User confirmation is still `reported` (flag `user_confirmed`), and so
  is a clinician-reviewed ambient statement: review attests what was said, and
  1.0 only allows a validation receipt on `clinician_validated`. Extractor or
  model output is `inferred`/`derived` with digest-bound parents, and a gap-fill
  is `imputed`. Admitted EHR records are `imported` with a `clinical_link`.
- **Refusal over approximation.** When a record has no 1.0 domain, is about
  someone other than the subject, is historical or planned, or has an uncertainty
  that 1.0 cannot represent, the mapper refuses it with a stable code
  (`domain_unsupported`, `subject_not_patient`, `speaker_not_subject`,
  `temporality_unsupported`, `uncertainty_not_representable`,
  `concept_unmapped`, `purpose_unmapped`, `model_family_contract_required`). The
  record stays in its custodian.

### Metabolog / InVivo

| Consumer field | Contract path | Rule |
|---|---|---|
| `HealthTimelineEntryRecord.id` + `updatedAt` | `observation_id`, `source.record_ref` | Revision-specific `urn:invivo:timeline:<id>:rev:<updatedAt>`, because the SwiftData record is mutable |
| Canonical export of the revision | `source.record_digest` | `canonical_digest` (see interop vectors) |
| `source` (for example `health-intake`) | (not identity) | An intake channel. `source_id`, `source_kind` and `device` come from HealthKit/device provenance |
| `kind` + `payload.manualReading` | `origin`, `epistemic_status` | Manual → `self_report`/`reported`; device sample → `device_sensor`/`observed` |
| `kind` | `measurement.domain` + `code` | Explicit concept table. Glucometer glucose is LOINC 41653-7 in `glucose`. `ketone`, `lipidPanel`, `medicine`, `supplement`, `bioScan`, `autonomic` are refused |
| `timestamp` / `createdAt` | `time.effective_start` / `time.ingested_at` | `effective_end` null |
| `value`, `unit` / symptom severity | `measurement.value`, `unit` / categorical value | UCUM |
| (none) | `uncertainty` | `unknown` |
| Admitted `id` (`urn:openbody:observation:<version_uid>`) | `clinical_link.admitted_observation_id`, `clinical_version_ref`, `source.record_ref` | Already the immutable clinical version; revoking it excludes the envelope |
| Admitted document | `clinical_link.content_digest` | `canonical_digest` of the admitted-observation.v1 JSON |
| Admitted `source.resource_digest` | `source.record_digest` | |
| Admitted `uncertainty` | `uncertainty` | All null → `unknown`; any number → refused |
| `OpenBodyEpistemicClass` `observed` / `derived` / `statistical_inference` | `observed` or `reported` (by origin) / `derived` / `inferred` | Parents must be envelopes bound by digest |
| `mechanistic_inference`, `OpenBodyStateRecord` | (refused) | Model state and simulation belong to the model-family contract (#18/#19); their evidence observations map one by one |
| Cymbathera quality `qualified` / `limited` / `unknown` | `quality.status` `acceptable` / `degraded` / `unknown` | The derived `confidence` (1 / 0.5 / nil) is not uncertainty |

### ProvidEHR ambient evidence

| Consumer field | Contract path | Rule |
|---|---|---|
| `SourceKey` (`clinical_system`, `adapter_id`, `connection_id`) | `source.source_id` | `urn:providehr:source:<system>:<adapter>:<connection>`, the same conflict unit as `LongitudinalState` |
| `source_record_type`, `source_record_id`, `source_version` | `source.record_ref` | Version-specific source record. Revoking it excludes all of its facts |
| `source_sha256` | `source.record_digest` | `sha256:<hex>` |
| `fact_id` | `observation_id` | `providehr:fact:<fact_id>` |
| `clinical_time` / `recorded_at` | `time.effective_start` / `time.ingested_at` | |
| `kind` `symptom` + local concept | `symptom` + agreed SNOMED CT code | Lexicon concepts are local identifiers, so an explicit code table is required. Problems, medications, plans and composite blood pressure are refused |
| `assertion` `present` / `negated` | categorical value `present` / `absent` | |
| `temporality` | (current only) | Historical and planned statements are refused |
| `uncertain` | `quality.flags: ["speaker_hedged"]` | Never uncertainty |
| `speaker_role`, `reviewer_id` | `origin: conversation`, `epistemic_status: reported` | The review receipt remains reachable through `record_ref` |
| `Subject::FamilyMember` / `Unknown` | (refused) | `subject_not_patient` |
| `CaptureConsent` | `consent` | `ambient_documentation` → `encounter_context`, `captured_at` → `granted_at`, `expires_at` null |
| `withdrawn`, `SourceAvailability::Revoked` | host `revoked` | `consent_ref` / `source_id`. `Unavailable`/`Withheld` emit nothing; `Stale` still maps and the assembler judges freshness |
| `transport_provider`, normalizer, `data_controller`, `tenant_id`, spans | (not carried) | Stay in ProvidEHR and are reachable through `record_ref` |

### TwinSuite conversational adapter

| Candidate | Contract | Rule |
|---|---|---|
| `said` by the subject | `conversation` / `reported` | `record_ref` `urn:invivo:conversation:<utterance>:rev:<n>` (custody in InVivo) |
| `confirmed` by the subject | `conversation` / `reported`, flag `user_confirmed` | Its digest differs from `said`. Same source and time, so both stay in `basis` and neither is preferred |
| `inferred` by an extractor | `model_transform` / `inferred`, `derivation` → said envelope | Blocked with `model_output_requires_receipt`. Revoking the utterance excludes it (`derivation_parent_excluded`) |
| Other or ambiguous speaker | (refused) | `speaker_not_subject` |
| Correction (revision n+1) | new `record_ref` | The host revokes revision n |
| `medication`, `exercise` | (refused) | No 1.0 domain |

### Cross-consumer result (frozen in `consumer-mapping.json`)

- The HealthKit meter glucose (observed) and the typed-in glucose (reported)
  for LOINC 41653-7 disagree after unit normalization, so the entry is
  `unresolved_conflict`. Observed values are not ranked above reported ones.
- InVivo's dizziness diary records severity (`moderate`) and ProvidEHR records
  presence (`present`) for SNOMED 404640003, so the entry is
  `unresolved_conflict`. This is correct fail-closed behavior, and it shows that
  consumers need an agreed value set per code (question 3).
- The admitted body temperature is `stale_only` at the shared `as_of`.
- The superseded TwinSuite revision is excluded with `source_revoked`, and its
  correction is the basis.

### Interoperability vectors (`interop-vectors.json`)

- **Canonical digests.** Derivation parents, clinical links and snapshots are
  bound by `canonical_digest`, which is Python `json` over the parsed value.
  The vectors pin three cases: an integral float keeps `.0` (`37.0` ≠ `37`),
  `/` and non-ASCII are unescaped, and keys are sorted recursively. Swift
  `JSONSerialization` (InVivo `wireData`) writes `37` and `\/` by default, so a
  native digest over the admitted example would not match without its own
  canonicalizer.
- **Native validation.** InVivo's fail-closed validator (#1131) supports the
  vocabulary of the admitted-observation profile only. The whole-person
  observation schema also uses `allOf`, `anyOf`, `if`/`then`/`else`, `not`,
  `uniqueItems`, `exclusiveMinimum`/`exclusiveMaximum` and `format: uri`. The
  state schema uses `uniqueItems`, `format: uri` and an external `$ref`. The
  inventory is recomputed in tests, so any change to it is visible.

### Relationship to the model-family contract (#18/#19)

This profile carries observations and their deterministic projection. It
deliberately does not carry model state (`OpenBodyStateRecord`,
`PhysiologicalState`), forecasts, counterfactuals, mechanistic inference or
model confidence. Those need the model-family execution and qualification
contract (OpenBody #18/#19, open), which is a separate dependency: Metabolog
#1129 needs both profiles. A whole-person snapshot can be a model input, and a
model output returns here only as a `derived`/`inferred`/`imputed` envelope
with digest-bound parents, blocked from clinical use until a receipt exists.

### Open questions for acceptance

Acceptance is a human decision. This review does not mark the contract
accepted. The questions to decide are:

1. **Canonical digest.** Keep Python-`json` canonicalization, including the
   `37.0` vs `37` distinction, as normative? Or version a digest algorithm (for
   example RFC 8785 JCS) before Swift, Kotlin and Rust emitters bind parents
   and clinical links?
2. **Native validation.** Should InVivo extend its validator to the
   whole-person vocabulary (conditionals, `uniqueItems`, `format: uri`, external
   `$ref`)? Or should OpenBody publish a flattened, native-subset profile of the
   same 1.0 contract?
3. **Categorical value sets.** Who owns the per-code value sets (presence vs
   severity for symptoms) so that cross-consumer statements are comparable
   rather than always in conflict?
4. **Reviewed statements.** Should 1.0 stay as it is, where a
   clinician-reviewed ambient statement is `reported` and the review receipt is
   reachable only through `record_ref`? Or should a 1.1 envelope add a review or
   confirmation receipt that does not claim clinician validation?
5. **Confirmation.** Is `quality.flags: ["user_confirmed"]` an acceptable 1.0
   carrier for TwinSuite's said/confirmed distinction, or does it need a typed
   field in 1.1?
6. **Domain coverage.** Should 1.1 add domains for blood pressure (a composite
   value), ketones, medication and exercise? Today they are refused.
7. **Admitted uncertainty.** Is refusing admitted observations with numeric
   epistemic/aleatoric/coverage fractions right, or should 1.1 carry them next
   to SD/interval uncertainty?
8. **Revocation timing.** Revocations are a host-resolved set with no effective
   time. Is that enough for replay at an earlier `as_of`? Relatedly,
   `validation.validated_at` later than `as_of` is not checked.
9. **Conversion tolerance.** Concordance is exact after unit conversion and
   rounding to 4 decimals, so equal values in mg/dL and mmol/L can conflict. Is
   a per-analyte tolerance wanted, or is fail-closed preferred?
10. **Candidate key.** Snapshot candidates do not repeat their measurement code,
    so a consumer needs the envelope to check that a candidate sits under the
    right key. Should the key be added in 1.1?
11. **ProvidEHR source unit.** Is `SourceKey` (system, adapter, connection) the
    agreed conflict unit, with transport provider, normalizer and controller
    left in ProvidEHR?
12. **Terminology ownership.** The code tables for InVivo kinds, ProvidEHR
    lexicon concepts and TwinSuite kinds are synthetic here. Who owns them?
