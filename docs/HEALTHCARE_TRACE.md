# Shared healthcare trace (`openbody.healthcare-trace/1.0`)

Status: synthetic cross-repository conformance trace for the whole-person
state contract of [#30](https://github.com/advatar/OpenBody/issues/30) /
PR #44. It is not patient data, not deployed-endpoint evidence and not a
clinical validation claim. The contract itself is still not accepted; that
remains a human decision (see
[Open questions for acceptance](WHOLE_PERSON_STATE.md#open-questions-for-acceptance)).

- Fixture: [`fixtures/healthcare-trace/v1/trace.json`](../fixtures/healthcare-trace/v1/trace.json)
- Reference replay and consumer policy: [`reference/python/openbody_ref/healthcare_trace.py`](../reference/python/openbody_ref/healthcare_trace.py)
- Builder: `python tools/build_healthcare_trace.py inputs|finalize` (two steps, the ProvidEHR producer runs in between)
- Checker: `python tools/check_healthcare_trace.py` (also run by `tools/validate_openbody.py` in conformance CI)
- Tests: `reference/python/tests/test_healthcare_trace.py`

## One trace through the actual runtime boundaries

```text
TakeCare note read (synthetic, qualified shape)          ProvidEHR, Rust
  -> takecare::normalizer::reconcile_detail + TakeCareNormalizer      (#599 boundary, qualified by #601)
  -> AdmittedInboundResource::identified_review  (REVIEW_REQUIRED:narrative, original-source digest)
  -> ambient-evidence TakeCareAmbientNoteAdapter -> pipeline::run (span-verified candidates)
  -> ReviewLedger (append-only clinician review) -> ReviewedClinicalFact
  -> LongitudinalState (source availability, staleness)
  -> openbody::export_state -> whole-person observation envelopes + host revocations
                                                          OpenBody, Python reference
  -> assemble_state / validate_state (unchanged 1.0 assembler)  -> snapshot
                                                          Metabolog, Swift
  -> WholePersonSnapshotConsumer -> OpenBodyStateIndex (temporal state graph)
```

Each repository keeps a byte copy of `trace.json` pinned by SHA-256 and
replays its own stage against it:

| Repository | Stage replayed | Where |
|---|---|---|
| advatar/ProvidEHR | `producer`: TakeCare boundary, ambient pipeline, review, state, export must equal `producer.expect`; also the ProvidEHR records of `consumer-mapping.json` and the canonical-digest interop vectors | `crates/ambient-evidence/tests/openbody_trace.rs` |
| advatar/OpenBody | producer cross-check with the reference mapper, `openbody` snapshot and cases, `consumer` cases with the reference policy | `openbody_ref.healthcare_trace` |
| advatar/Metabolog | `consumer` cases natively, and ingestion into the state graph | `SurrealEmbedded/Tests/SurrealHealthIndexTests/WholePersonSnapshotConsumerTests.swift` |

## Contract pin

`contract` records the schema ids, the SHA-256 of both schema files, the
canonical observation-schema digest that every snapshot carries, the assembly
policy and the mapping version. Replays check the pin first; the Rust and Swift
consumers hard-code the same values.

## Trace profile rules (no schema change)

1. A ProvidEHR ambient envelope carries quality flag `clinician_reviewed`,
   because only facts admitted through the review ledger are exported. It stays
   `conversation` / `reported`: review attests what was said, it is not
   `clinician_validated` and not uncertainty. The 1.0 assembler cannot see
   review, so the consumer enforces it. A typed review field is acceptance
   question 4.
2. The consumer re-derives provenance: each listed input needs its envelope
   with the same canonical digest, and each candidate must keep its envelope's
   source, origin, epistemic status and missingness.
3. Revoked consent and revoked sources reach the assembler as host
   revocations and stay visible as exclusions.
4. A stale-only entry keeps its evidence but creates no current state.
5. Every blocker is kept; nothing becomes an admission candidate by consumption.

## Controls and rejection cases

| Case | ProvidEHR (producer) | OpenBody | Metabolog (consumer) |
|---|---|---|---|
| Control | 5 reviewed envelopes, 3 refusals (family history, plan, withheld source), 1 revocation | 4 entries (3 `single_source`, 1 `stale_only`), 1 exclusion | 5 inputs stored; 3 current state nodes, all with blockers |
| Revoked consent | Withdrawn consent is emitted as a host revocation | `consent_revoked` exclusion | `excluded:consent_revoked`, no evidence |
| Missing provenance | Boundary refuses a list/detail mismatch, another patient, an unqualified `version` field, another connector; a changed note is a different record version | Envelope without `record_digest` is `structural_invalid` | `provenance_lost` (record digest removed, envelope missing), `missingness_altered` |
| Unreviewed ambient claim | Deferred claim never leaves the ledger (`not_reviewed`) | Accepted: 1.0 cannot see review | `refused:unreviewed_ambient_claim`, no state |
| Stale source | Source marked stale still exports | `stale_only`, blocked | `stale`, no state |
| Imputed as observed | Producer only emits `reported` | Relabelled envelope is `structural_invalid`; imputed id in basis is `imputation_as_measurement` | Imputed control is `non_measurement`; relabelled, re-digested snapshot is `imputed_as_observed` |
| Contract / integrity | | | `contract_unpinned`, `snapshot_digest_mismatch`, `subject_mismatch` |

## What this does not show

- The TakeCare note reads are synthetic in the qualified shape; no live
  TakeCare call is made and #574's qualification is reused, not repeated.
- The narrative line profile (`@start` header and
  `role|t0|t1|confidence|text` lines) is a synthetic trace profile, not a
  documented TakeCare template.
- Metabolog's product runtime does not call the consumer yet; the state graph
  is the package-level index. Android parity is separate work.
- Withheld and unavailable ProvidEHR sources emit no envelope under the 1.0
  mapping; the producer reports them in `sources` and `refused`, but OpenBody
  has no place to carry source-level missingness.
