# OpenBody PR #5 Handover

## Current checkpoint

- Repository: `advatar/OpenBody`
- Pull request: [#5](https://github.com/advatar/OpenBody/pull/5)
- Branch: `fix/openbody-0.1-hardening`
- Qualified protocol commit: `4056647` (provenance patch `253b6553`, host trust boundary `4056647`)
- State: draft, open, and unmerged — awaiting one final bounded review of `4056647`
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

## Latest bounded patch: host trust boundary

Commit `4056647` closes the two P1 findings and one P2 finding that reproduced at `ee4ad24` when the not-outdated historical review threads were swept:

1. **P1-A — read path did not re-substantiate producing models.** The descriptor discoverability/capability/scope/applicability gate is extracted from `_reference_simulate` into `_producing_model_defect` and now runs on `GET /v1/simulations/{id}` as well, so the two paths share one implementation instead of the read path having none. The read path fails closed with 422 rather than surfacing an unhandled validation error.
2. **P1-B — simulated results were not bound to the hosted twin.** The candidate and baseline subjects must now equal `store.state["subject"]` on both the execute and read paths, so a self-consistent foreign store can no longer be served as successful.
3. **P2-C — evidence could postdate its own claim.** A reference whose `observed_at` follows the scenario's `generated_at` is now rejected in both the reference validator and `tools/validate_openbody.py`.
4. **Aliasing fix.** `from_fixture` now deep-copies `fixture["applicability"]` into each generated descriptor instead of sharing one mutable object.

`OPENBODY.md` records the hosted-twin binding, the read-path re-substantiation duty, and the evidence recency and full-digest requirements as normative.

## Qualification results

Against `4056647`:

- Reference suite: `66 passed` (was 56; nine new regressions plus the two lineage regressions)
- Every new regression fails against `ee4ad24`; the substantiated-read positive control passes against both
- Conformance validator: all examples pass
- JSON Schema / OpenAPI / MCP profile parsing: pass
- Provenance probes from the earlier pass: all 10 still pass, so the patched per-producer invariant did not regress
- `git diff --check`: pass

## Review-thread sweep: complete

All 21 not-outdated threads are now accounted for, each against a named regression rather than by inspection:

| Thread | Covering regression |
| --- | --- |
| duplicate trajectory / state ids | `TestTrajectoryLineageClosure` (new) |
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
| conditional bound-evidence schema | abstention fixture validates with no evidence |
| nested evidence placement provenance | `test_nested_evidence_must_bind_its_exact_producer` and the three per-producer regressions |
| calibration hosted-twin subject | `test_calibration_rejects_foreign_subject_store_lineage` |
| model applicability boundary | `test_model_applicability_must_match_subject_and_receipt_scopes` |
| hosted-twin binding, read-path re-substantiation | `TestHostTrustBoundaryClosure` (new) |
| evidence recency | `test_evidence_cannot_postdate_scenario_generation` (+ nested variant) |

The 16 outdated threads were not individually re-verified; they predate several rewrites of the files they annotate.

## Active gate

One further bounded adversarial review must verify `4056647` at the same acceptance criterion: **0 unresolved in-scope P1/P2 findings** across the established OpenBody 0.1 invariant classes, without expanding into performance, deployment hardening, future protocol features, or unrelated security concerns.

Reviewers should note that the two P1s closed here were both host trust-boundary gaps reachable only through a custom store, and that `create_app()` accepts custom stores by design. That boundary and both HTTP read paths deserve explicit attention; the earlier pass missed them by scoping to the provenance class and to the classes the suite already exercised.

**Do not merge PR #5 and do not resolve the historical review threads until that review is clean.** When it is, resolve the threads individually against the mapping above rather than in bulk, then:

1. Merge PR #5.
2. Freeze and tag the OpenBody 0.1 interoperability baseline.
3. Rebase InVivo/Metabolog #972 onto that exact contract.
4. Add cross-repository conformance fixtures and CI.

## Local workspace hygiene

The LandingPage repository is pushed on its `main` branch at `cd361000533d07f28d99456ec51c77fd4140adeb`. OpenBody records it as a submodule in commit `b2b937c847e5892fce5890a0280c3a51f50bdfdb`. The model manifesto and its deliverable assets are committed at `5e174482321f96fb83bcf332312c0f300aa4eb17`.

The local working tree was clean when this handover was updated.
