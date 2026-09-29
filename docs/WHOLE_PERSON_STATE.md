# Whole-person observation envelope and state snapshot

Status: version 1.0 source-neutral contract with a local conformance corpus.
The owner accepted the observation/projection architecture and the ownership
boundaries on 2026-09-29, on condition that the v1 correctness items in
[Owner decisions](#owner-decisions-2026-09-29) are met. Those corrections are
implemented here. The corrected v1 baseline is frozen by
[`fixtures/whole-person-state/v1/frozen-manifest.json`](../fixtures/whole-person-state/v1/frozen-manifest.json).
Additive 1.1 work is tracked in [#47](https://github.com/advatar/OpenBody/issues/47).
This profile is not part of the frozen OpenBody 0.1 core schema; it is an
additive profile.

Tracking issues: [#30](https://github.com/advatar/OpenBody/issues/30) (contract),
[#46](https://github.com/advatar/OpenBody/issues/46) (v1 corrections),
[#47](https://github.com/advatar/OpenBody/issues/47) (1.1).

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
- Canonical digest (normative): [`docs/CANONICAL_DIGEST_V1.md`](CANONICAL_DIGEST_V1.md)
  (`openbody.canonical-digest/1`), with cross-language vectors
  [`fixtures/whole-person-state/v1/canonical-digest-vectors.json`](../fixtures/whole-person-state/v1/canonical-digest-vectors.json)
  and the reference implementation `openbody_ref.canonical_json`
- Native validation vocabulary (normative):
  [`fixtures/whole-person-state/v1/native-validation.json`](../fixtures/whole-person-state/v1/native-validation.json)
  (`openbody.whole-person-native-validation/1.0`)
- Categorical value sets (owned by OpenBody):
  [`registry/whole-person-value-sets.json`](../registry/whole-person-value-sets.json)
  (`openbody.whole-person-value-sets/1.0`)
- Frozen v1 manifest: [`fixtures/whole-person-state/v1/frozen-manifest.json`](../fixtures/whole-person-state/v1/frozen-manifest.json)

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
| Snapshot is deterministic | Inputs are de-duplicated by id and digest, sorted, and assembled against an explicit `as_of`, `purpose` and the host-resolved revocations. `snapshot_digest` covers the whole snapshot. Neither input order nor an identical replay changes it; a replay with different content is rejected. `contract` pins the observation schema digest, the registry version and the value sets (`value_sets_version`, `value_sets_digest`); `validate_state` rejects a snapshot whose pins differ from the verifier's (`contract_mismatch`). |
| Clinical assertions still need their receipt path | `clinical_use.admission_candidate` only says that no blocker applies; `requires` names `openbody.clinical-assertion-reference/1.0`. Model outputs are blocked with `model_output_requires_receipt`. |

Exclusions (kept in `exclusions` with the input digest):
- a revoked source, record, clinical version, consent, authority or subject binding;
- consent not yet granted or expired;
- purpose not permitted;
- not yet ingested, or effective after `as_of`;
- a validation receipt dated after `as_of` (`validation_after_as_of`);
- an unrecognized unit (never guessed);
- a categorical value that is not in its code's value set
  (`categorical_value_unrecognized`, never guessed);
- derivation parents that are missing, digest-mismatched, bound to another
  subject, or themselves excluded.

**Categorical value sets (decision 3).** OpenBody owns one value set per code
in `registry/whole-person-value-sets.json`. A code's value set is split into
dimensions, for example `presence` (`present`, `absent`) and `severity`
(`mild`, `moderate`, `severe`). No value belongs to two dimensions of the same
code, so the dimension of a present categorical value is determined, not
inferred. Entries of categorical values carry `key.dimension`. A presence
statement and a severity statement about one code are in different entries,
never compared, and neither equivalent nor contradictory. Within one
dimension, disagreement is an ordinary conflict. A present measurement of a
listed code must be categorical, in the listed domain, with a listed value
(exact match); otherwise it is excluded. A non-present record of a listed code
has no value and stays in the dimension-less entry.

**Independence (decision 11).** `source_id` is the conflict unit, and it is not
enough on its own for corroboration. Per-source groups that share a
`record_ref` or a `record_digest` form one independence unit. `concordant`
needs at least two independent units that agree; agreement within one unit is
`single_source`. One `record_ref` under two `source_id`s is still rejected
(`source_identity_conflict`). A disagreeing mirror is still a conflict and is
never silently merged.

**Placement and present use (decisions 8 and 10).** A snapshot on its own
cannot show which code a candidate came from, because v1 candidates do not
repeat the code.
- `verify_state_against_inputs(snapshot, envelopes)` resolves every listed input
  to its envelope by digest (`provenance_lost`). It checks that each candidate
  sits under its own envelope's key, including the dimension
  (`candidate_misplaced`), and that it equals what its envelope derives
  (`candidate_mismatch`). It then re-assembles the snapshot from the inputs
  (`state_not_reproducible`).
- `present_use(snapshot, envelopes, current_revoked)` applies the *current*
  revocation set before a historical snapshot is used now. Revoked candidates
  and their derived descendants are reported (`derivation_parent_revoked`), and
  `require_present_use` fails with `revoked_since_snapshot`. Present use does not
  re-date consent windows, purposes or freshness: those were judged at `as_of`.
  The current revocation set cannot establish what was authorized at an earlier
  time. Historical replay at an earlier `as_of` shows what the evidence says,
  not what was authorized then. That needs versioned, time-aware revocation
  evidence (#47).

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

`validate_state` also checks internal consistency:
- every `basis` id is a candidate of its entry;
- each entry's `resolution`, `basis`, candidate order and `clinical_use` equal
  what this policy derives from its candidates (`state_inconsistent`
  otherwise);
- every input is accounted for exactly once, as a candidate or an exclusion;
- a categorical entry's `dimension` is the one its values belong to
  (`candidate_misplaced`);
- no candidate carries a validation dated after `as_of`
  (`validation_after_as_of`).

Date-times are RFC 3339. Lower-case `t`/`z` are accepted, and instants are
compared at microsecond precision. An unreadable time is `structural_invalid`,
never an unhandled error.

Blockers: `resolution_*` (conflict, stale_only, imputed_only, missing_only),
`uncertainty_unknown`, `quality_not_acceptable`, `not_individual_measurement`,
`model_output_requires_receipt`, `clock_unknown`.

Clock drift: `effective_start` may exceed `ingested_at` by at most 300 s; a
`corrected` clock must satisfy `device_reported_start + correction_seconds =
effective_start`; an `unknown` clock blocks clinical use.

## Source mapping

The terminology in this table and in the consumer-mapping fixture is
**synthetic and unreviewed** (decision 12). Producers own their
source-to-contract tables. OpenBody owns the contract vocabulary (domains,
units, value sets) and the mapping requirements.

| Source | origin | epistemic_status | domain / code | Notes |
|---|---|---|---|---|
| CGM | device_sensor | observed | glucose / LOINC 99504-3 | mmol/L or mg/dL; 1 h freshness |
| Sleep (wearable) | device_sensor | observed | sleep / LOINC 93832-4 | min or h |
| HRV (wearable) | device_sensor | observed | heart_rate_variability / LOINC 80404-7 | ms or s |
| Heart rate / non-wear | device_sensor | observed | heart_rate / LOINC 8867-4 | `missingness.status = non_wear` carries no value |
| Symptoms (app diary) | self_report | reported | symptom / SNOMED CT | categorical, uncertainty unknown |
| Meals (conversation, TwinSuite) | conversation | reported | meal / text (categorical `meal-category` only via an extractor, value set `meal_category`) | candidate observation only |
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

- Implemented and locally qualified: schemas, the reference assembler, 1 golden
  snapshot and 95 adversarial/conformance vectors:
  - 52 original;
  - 12 added in the PR #44 consumer review: source identity, record versions,
    code/domain ambiguity, same-time ties, state consistency;
  - 31 added for the owner's v1 corrections (#46): value sets and dimensions,
    validation after `as_of`, present use under current revocation, placement
    against envelopes, independence.

  The vectors cover EHR, wearable, lab, behavior and environment inputs; unit
  normalization; clock drift; conflicting sources; stale values;
  missingness/non-wear; revocation; imputed-vs-observed; replay; provenance
  loss; and state tampering.
- Cross-language vectors: 46 positive, 17 negative and 3 corpus canonical-digest
  vectors, and 50 native-validation cases (40 observation, 10 state). Python
  reproduces all of them. Swift/Kotlin (Metabolog) and Rust (ProvidEHR) have
  not reproduced them yet; that is tracked in those repositories.
- CI: the corpus runs inside `tools/validate_openbody.py`.
- Not qualified here (other repositories): InVivo native consumer
  (Metabolog #1129/#1144), TwinSuite conversational adapter (#144), ProvidEHR
  encounter context integration (#600). The corpus is synthetic; it is not
  real-cohort physiology, patient/consent binding evidence, or deployed
  endpoint qualification. The reference host does not mount this profile.

## Consumer mapping

Mapping version `openbody.whole-person-consumer-mapping/1.0`. The owner accepted
its ownership boundaries with the corrections in
[Owner decisions](#owner-decisions-2026-09-29). Its terminology tables remain
synthetic and unreviewed (`terminology` in the fixture; the checker fails on an
unlabelled table). The rules below
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
- **Source identity.** `source_id` is the consumer's own conflict unit, scoped
  explicitly by tenant and data controller wherever the producer is
  multi-tenant. `record_ref` names one immutable version of the *underlying*
  record (`:rev:` or `::v`) and never names the adapter or connection that
  fetched it. One record belongs to one source and has one digest; the
  assembler enforces this. Another adapter or connection that reaches the same
  record is not independent corroboration (decision 11).
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
  `concept_unmapped`, `purpose_unmapped`, `model_family_contract_required`,
  `source_scope_missing`). The record stays in its custodian.

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
| `SourceKey` (`clinical_system`, `adapter_id`, `connection_id`) + `tenant_id` + `data_controller` | `source.source_id` | `urn:providehr:source:<tenant>:<controller>:<system>:<adapter>:<connection>`, each part percent-encoded. It is the same conflict unit as `LongitudinalState`, scoped explicitly. Without tenant and controller the record is refused (`source_scope_missing`) |
| `source_record_type`, `source_record_id`, `source_version` | `source.record_ref` | `urn:providehr:record:<tenant>:<controller>:<system>:<type>:<id>:<version>`: the underlying record version, independent of adapter and connection. Revoking it excludes all of its facts |
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
| `transport_provider`, normalizer, spans | (not carried) | Stay in ProvidEHR and are reachable through `record_ref`; `tenant_id` and `data_controller` are carried in `source_id` and `record_ref` |

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
  presence (`present`) for SNOMED 404640003. Under OpenBody's value sets
  (decision 3) these are two entries, `presence` and `severity`, each
  `single_source`, and they are never compared. Before the decision, this was
  one `unresolved_conflict` entry.
- The admitted body temperature is `stale_only` at the shared `as_of`.
- The superseded TwinSuite revision is excluded with `source_revoked`, and its
  correction is the basis.

### Interoperability vectors (`interop-vectors.json`)

- **Canonical digests.** Derivation parents, clinical links and snapshots are
  bound by `openbody.canonical-digest/1`. Its normative, language-independent
  definition is [`CANONICAL_DIGEST_V1.md`](CANONICAL_DIGEST_V1.md); the Python
  `json` form is only the historical reference that the spec reproduces. The
  vectors in `canonical-digest-vectors.json` are the conformance bar for Swift,
  Kotlin, Rust and Python. The earlier vectors here still hold. Swift
  `JSONSerialization` (InVivo `wireData`) writes `37` and `\/` by default and
  loses the integer/float distinction, so a native digest needs its own
  canonicalizer.
- **Native validation.** InVivo's fail-closed validator (#1131) supports the
  vocabulary of the admitted-observation profile only. The whole-person
  observation schema also uses `allOf`, `anyOf`, `if`/`then`/`else`, `not`,
  `uniqueItems`, `exclusiveMinimum`/`exclusiveMaximum` and `format: uri`. The
  state schema uses `uniqueItems`, `format: uri` and an external `$ref`. The
  inventory is recomputed in tests, so any change to it is visible. The
  complete vocabulary a native validator must implement, with its semantics and
  cases, is `native-validation.json` (decision 2).

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

These questions were decided by the owner on 2026-09-29. See
[Owner decisions](#owner-decisions-2026-09-29). They are kept here as they
were asked:

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

## Owner decisions (2026-09-29)

Decided by the accountable project owner (Johan Sellstrom, @advatar). The owner
accepts the observation/projection architecture and the ownership boundaries,
on condition that the correctness requirements below are met. Items marked
**v1** are implemented and frozen in the corrected v1 baseline (#46). Items
marked **1.1** are additive and tracked in
[#47](https://github.com/advatar/OpenBody/issues/47).

1. **Canonical digests (v1).** Keep the pinned v1 algorithm. It now has a
   language-independent specification, not "whatever Python `json.dumps`
   does": [`CANONICAL_DIGEST_V1.md`](CANONICAL_DIGEST_V1.md)
   (`openbody.canonical-digest/1`). Cross-language vectors
   (`canonical-digest-vectors.json`) must be reproduced identically by Swift,
   Kotlin, Rust and Python. Python is implemented from the spec
   (`openbody_ref.canonical_json`) and verified. Values outside the specified
   domain (non-finite numbers, integers beyond +-(2^53 - 1), lone surrogates,
   duplicate keys) fail closed. Any algorithm change needs a new version and a
   migration (spec section 8).
2. **Native validation (v1).** The contract identity is not weakened, and there
   is no flattened subset. `native-validation.json` publishes the exact
   vocabulary a native validator must implement (keywords, formats, reference
   kinds, patterns, semantics), with 50 cases. Unsupported constraints must
   fail closed. The Python reference applies the same rule
   (`schema_vocabulary_unsupported`), including for a format it has no checker
   for. The Metabolog lane implements the native validator.
3. **Categorical values (v1).** OpenBody owns the shared per-code value sets
   (`registry/whole-person-value-sets.json`). Presence and severity are
   separate dimensions. They are never equivalent, and never contradictory just
   because they share a symptom code. Implemented in the assembler
   (`key.dimension`, `categorical_value_unrecognized`), the value-set
   definitions and the vectors.
4. **Clinician review (1.1).** A typed review receipt in 1.1, separate from
   epistemic status. A reviewed statement stays `reported` unless the
   clinical-validation path says otherwise. v1 is unchanged: review is not
   `clinician_validated`.
5. **User confirmation (1.1).** A typed confirmation in 1.1. The current
   `quality.flags: ["user_confirmed"]` flag is kept for v1 compatibility.
   Confirmation confers no clinical authority.
6. **Domains.** Domains are added incrementally, and only with a real consumer
   mapping and conformance cases. Unsupported domains stay explicit refusals
   (`domain_unsupported`). Candidates are tracked in #47.
7. **Uncertainty (1.1).** Distinct representations go in a versioned
   extension. Epistemic, aleatoric and coverage fractions are never converted
   into SDs, intervals or confidence. v1 keeps its explicit refusal
   (`uncertainty_not_representable`).
8. **Time and revocation (v1 + documented).** A validation dated after the
   snapshot `as_of` is rejected: it is excluded at assembly and rejected by
   `validate_state` (`validation_after_as_of`). Current revocation constrains
   present use of historical snapshots (`present_use`,
   `require_present_use`, `revoked_since_snapshot`). Historical replay needs
   versioned, time-aware revocation evidence. The current set cannot establish
   historical authorization (#47).
9. **Conversion tolerance (v1 policy).** Conflict behaviour stays conservative
   now: concordance is exact after unit conversion and rounding to 4 decimals.
   Any future tolerance must be explicit, per-analyte, versioned and justified.
   There is no universal epsilon.
10. **Candidate keys (v1 + 1.1).** Each candidate's placement is validated
    against its source envelope now (`verify_state_against_inputs`:
    `candidate_misplaced`, `candidate_mismatch`, `state_not_reproducible`). An
    explicit code/key on candidates in 1.1 will not replace that check.
11. **Source identity (v1).** The current ProvidEHR `SourceKey` is accepted only
    with explicit tenant and data-controller scoping (`source_scope_missing`
    otherwise). Independence rule: another adapter or connection to the same
    underlying record (the same `record_ref` or `record_digest`) does not count
    as independent corroboration. Implemented in the mapper and the assembler,
    with vectors.
12. **Terminology (v1 labels).** OpenBody owns the contract vocabulary and the
    mapping requirements. Producers own their source-to-contract mappings.
    Synthetic tables stay labelled synthetic until they are reviewed
    (`terminology` in `consumer-mapping.json`; the checker enforces the label).

### Changes to existing vectors and fixtures required by these decisions

| Artifact | Change | Decision |
|---|---|---|
| `snapshot.golden.json` | `contract` adds `value_sets_version` and `value_sets_digest`. The fatigue entry key adds `dimension: severity`. `snapshot_digest` changes accordingly. No candidate, basis, resolution or blocker changed. | 3 |
| `vectors.json` `concordant-second-source` | The added second CGM now carries its own `record_digest`. The old vector copied `wp-cgm-001`'s digest, which under the independence rule is the same underlying record (that case is now the separate vector `independence-shared-record-digest-not-corroboration`). Expected result unchanged: `concordant`. | 11 |
| `consumer-mapping.json` ProvidEHR records | Records carry `tenant_id` and `data_controller`. The expected `source_id` and `record_ref` are tenant/controller-scoped. The new record `ambient-symptom-unscoped-source` is refused. | 11 |
| `consumer-mapping.json` cross-consumer result | Dizziness is two `single_source` entries (presence, severity) instead of one `unresolved_conflict` entry. The `meal-category` entry carries `dimension: meal_category`. The snapshot digest changes. | 3 |
| `consumer-mapping.json` `terminology` | Added labels; all tables are `synthetic_unreviewed`. | 12 |
| `interop-vectors.json` | Adds `normative` pointers, and the digest rule text references the spec. All earlier vectors still hold. | 1, 2 |
| `test_whole_person_consumer_mapping.py` | `..._symptom_value_vocabulary_is_an_open_conflict` becomes `..._presence_and_severity_are_separate_dimensions` (stronger assertions). The SourceKey tests use scoped keys and also assert the unscoped refusal. | 3, 11 |

Schemas: the observation schema is unchanged (its canonical digest is still
`sha256:7071eb62…99881d`). The state schema (still `openbody.whole-person-state/1.0`,
corrected before the freeze) adds the optional `key.dimension`, the exclusion
codes `validation_after_as_of` and `categorical_value_unrecognized`, and the
`contract.value_sets_*` pins. It uses no new keyword. Downstream byte copies
pinned to a pre-freeze PR #44 revision (the healthcare trace in PR #45, the
ProvidEHR and Metabolog replays) must re-pin to the frozen manifest.

