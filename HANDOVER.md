# OpenBody PR #5 Handover

## Current checkpoint

- Repository: `advatar/OpenBody`
- Pull request: [#5](https://github.com/advatar/OpenBody/pull/5) — **merged** as `d8d841e`
- Frozen baseline: tag `v0.1.0-draft.1` at `d8d841e`
- Qualified protocol commit: `215f55d`
- State: merged; all 37 review threads resolved; baseline frozen
- Tracker: issue #3; issue #4 is closed as duplicate

## Latest bounded patch

Commit `253b65536050f7f6d65916355f55aaca175775a4` closes the final P1 reported by the local bounded review of `6f422f9d46f1323627dc7340f6370ed5ea9497b8`:

1. Every model cited by an evidence object must individually support every scope on that object at the exact placement; unrelated producers cannot pass through unioned scope coverage.
2. Disjoint per-model attribution in OpenBody 0.1 is represented by separate scoped evidence references, while a single correctly scoped producer remains valid.

The patch tightens the shared placement-aware evidence/producer scope maps rather than adding fixture-specific exceptions. It preserves the previously closed subject, scope, temporal, discoverability, capability/applicability, evidence, request-response, outcome/calibration, and authority invariants.

## Qualification results

Independently re-run against `253b65536050f7f6d65916355f55aaca175775a4`:

- Reference suite: `56 passed`
- Conformance validator: all examples pass
- JSON Schema validation/parsing: pass
- OpenAPI parsing: pass
- MCP profile parsing: pass
- `git diff --check`: pass
- GitHub `validate` CI: pass (run 31458746859, `SUCCESS`)

## Latest bounded patches

`4056647` closed the two P1 findings and one P2 finding that reproduced at `ee4ad24`:

1. **P1-A — read path did not re-substantiate producing models.** The descriptor discoverability/capability/scope/applicability gate was extracted from `_reference_simulate` into `_producing_model_defect` and now runs on the read path too, so both paths share one implementation.
2. **P1-B — simulated results were not bound to the hosted twin.** Candidate and baseline subjects must equal `store.state["subject"]`.
3. **P2-C — evidence could postdate its own claim.** A reference whose `observed_at` follows the scenario's `generated_at` is rejected in both validators.
4. **Aliasing fix.** `from_fixture` deep-copies `fixture["applicability"]` per descriptor.

`215f55d` closed what the bounded review of `4056647` then found — that its own read-path fix was scoped too narrowly, binding only `GET /v1/simulations/{id}` and only for the `simulated` disposition. Four cross-twin disclosures remained, all one root cause, now closed by a single shared `_require_hosted_twin` guard applied uniformly across read paths:

1. **Abstained scenarios were exempt.** `baseline` is a required property on `CounterfactualScenario`, so an abstained foreign scenario disclosed another subject's `BodyState`.
2. **`GET /v1/trajectories/{id}`** disclosed foreign `BodyState`s outright.
3. **`GET /v1/models/{id}` and `GET /v1/models`** disclosed foreign descriptors and their applicable subject.
4. **Last unresolved P2 thread.** `evidence` carried `minItems: 1` for every disposition, so a governed abstention could not be expressed without fabricating an evidence reference and a producing model to satisfy it. The constraint is now conditional on `disposition == "simulated"`, which is what `OPENBODY.md` always said — the schema had been stricter than the spec.

## Qualification results

Against `215f55d`:

- Reference suite: `74 passed` (was 56 at the start of this sequence)
- Every new negative regression fails against the commit it was written for; positive controls pass against both
- Conformance validator, JSON Schema / OpenAPI / MCP profile parsing: pass
- 10 provenance probes and 9 read-path probes: pass
- `git diff --check`: pass

## Final bounded review of `215f55d`: clean

Zero unresolved in-scope P1/P2 findings. Beyond the suite, the following were attacked directly and fail closed: the shared hosted-twin guard on a missing subject key; empty subject sets and stateless trajectories; a mixed store holding one canonical and one foreign descriptor; dodging the new schema conditional by smuggling a counterfactual and receipts under a non-simulated disposition; foreign-subject outcome writes; and coordinate traversal on `GET /v1/state/{coordinate}`. All five canonical read paths and the canonical simulate flow still succeed.

**Confidence caveat, recorded deliberately.** This review was performed by the same agent that wrote `4056647` and `215f55d`, at the owner's direction. Two consecutive rounds each found findings the previous round missed, and both times the miss was one of scope, not of depth: the first pass scoped to the provenance class, the second to a single endpoint and disposition. The pattern to distrust is therefore *which surfaces were considered*, not the rigour applied to those chosen. An independent reviewer should start by enumerating every host path that returns stored, subject-bearing data and every disposition that can carry it, rather than re-deriving the invariants.

## Review-thread sweep: complete

All 21 not-outdated threads are accounted for, each against a named regression:

| Thread | Covering regression |
| --- | --- |
| duplicate trajectory / state ids | `TestTrajectoryLineageClosure` |
| client response vs. request | `test_reference_client_rejects_request_inconsistent_simulation` (4 cases, each confirmed to reject for its own reason) |
| scenario evidence in scope closure | `test_scenario_evidence_cannot_add_unrequested_scope` |
| expired baseline | `test_expired_baseline_abstains` |
| producing-model capability / scope | `test_empty_model_capability_and_scope_fail_closed` |
| full-length digests | `test_short_digest_is_rejected` (schema regex enforces 64/128 hex) |
| per-state validity interval | `test_impossible_state_validity_interval_is_rejected` |
| stored scenario before outcome binding | `test_poisoned_scenario_cannot_extend_outcome_window` |
| recursive evidence placement | `test_nested_cross_subject_undigested_evidence_is_rejected` |
| baseline `state_time` ordering | `test_baseline_cannot_start_after_perturbation` |
| scope-less nested / trajectory producers | `test_scope_less_nested_producer_fails_closed`, `test_scope_less_trajectory_producer_fails_semantic_validation` |
| returned baseline vs. requested state | `test_returned_baseline_must_equal_requested_state` |
| conditional bound-evidence schema | `TestDispositionEvidenceClosure` |
| nested evidence placement provenance | `test_nested_evidence_must_bind_its_exact_producer` plus the three per-producer regressions |
| calibration hosted-twin subject | `test_calibration_rejects_foreign_subject_store_lineage` |
| model applicability boundary | `test_model_applicability_must_match_subject_and_receipt_scopes` |
| hosted-twin binding, read-path re-substantiation, cross-twin reads | `TestHostTrustBoundaryClosure` |
| evidence recency | `test_evidence_cannot_postdate_scenario_generation` (+ nested variant) |

The 16 outdated threads were resolved as superseded rather than individually re-verified; they annotate code that has since been rewritten several times.

## Remaining actions

### 1. InVivo #972 does not conform to the frozen contract

`advatar/Metabolog` (the InVivo checkout; same repo for historical reasons) PR
[#972](https://github.com/advatar/Metabolog/pull/972) "Expose InVivo Twin through OpenBody 0.1" is open and mergeable on
`feat/openbody-adapter`, but it was written against a looser OpenBody and is **not** conformant with
`v0.1.0-draft.1`. This is more than a rebase.

`OpenBodyWireAdapter.scenarioObject` emits neither `applicability` nor `evidence`, both of which are required on
`CounterfactualScenario`, so *every* scenario it produces fails schema validation. `evidenceObject` emits
`content_digest: null` and never emits `subject`, `scopes`, `model_refs`, or `claim_refs` — the four bindings a
simulated scenario requires at every evidence placement.

Closing this needs real provenance plumbing in InVivo, not field padding:

- InVivo must content-digest its health events so `content_digest` is a genuine `sha256:` value.
- InVivo needs a mapping from its internal signals to registered `ob://` coordinates in `registry/coordinates.json`,
  to populate evidence `scopes` and `applicability.scopes`.
- `applicability.scopes` MUST equal all counterfactual output scopes and `applicability.horizon_seconds` MUST equal the
  derived elapsed time; neither can be hard-coded.
- Each evidence `model_refs` entry must individually support every scope on that object at its placement, per the
  per-producer invariant closed in `253b6553`.

The abstention path is closer to conformant, and the conditional-evidence fix in `215f55d` is what makes a governed
abstention expressible with no evidence at all.

### 2. Cross-repository conformance CI

InVivo should emit fixtures into a shared conformance corpus that OpenBody's `tools/validate_openbody.py` validates in
CI on both sides, pinned to `v0.1.0-draft.1`. Without this, drift between the two repos is invisible until integration.

### 3. Body/mind interoperability with OpenMind and BrIAn

`advatar/OpenMind` is the mind-side standard (`spec/omps.md` plus `spec/extensions/om*.md` profiles, JSON Schema, MCP
server); `advatar/BrIAn` is an app implementing it. Two cross-standard questions are unresolved and should be settled
before BrIAn consumes OpenBody:

- **Subject identity.** OpenBody uses `subject:` URIs and binds every object to one canonical twin. OpenMind carries
  its own person identity. One person must resolve to one identity across both standards, or the binding between them
  must be explicit and verifiable.
- **Authority.** The OpenBody reference host abstains on any `authority_ref` because it cannot validate external
  authority. OpenMind already has an authorization and peer-grant model (`AUTHORITY.md`). OpenBody authority should
  delegate to that model rather than introduce a second scheme.

The natural shape is an `OMBODY` extension profile in OpenMind, following the existing `om*.md` convention, defining
the subject-identity binding, how OpenBody claims enter OpenMind's evidence/claim path (per `OMTRANS-0.1`), and
authority delegation.

## Local workspace hygiene

The LandingPage repository is pushed on its `main` branch at `cd361000533d07f28d99456ec51c77fd4140adeb`. OpenBody records it as a submodule in commit `b2b937c847e5892fce5890a0280c3a51f50bdfdb`. The model manifesto and its deliverable assets are committed at `5e174482321f96fb83bcf332312c0f300aa4eb17`.

The local working tree was clean when this handover was updated.
