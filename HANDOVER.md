# OpenBody PR #5 Handover

## Current checkpoint

- Repository: `advatar/OpenBody`
- Pull request: [#5](https://github.com/advatar/OpenBody/pull/5)
- Branch: `fix/openbody-0.1-hardening`
- Qualified protocol commit: `253b65536050f7f6d65916355f55aaca175775a4`
- State: draft, open, and unmerged
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

## Final bounded review: clean

The final bounded adversarial review of qualified protocol commit `253b65536050f7f6d65916355f55aaca175775a4` is complete and reports **0 unresolved in-scope P1/P2 findings** across the established OpenBody 0.1 invariant classes.

Verification performed beyond re-running the suite:

1. **Regressions bite.** Reverting `validation.py` to `6f422f9` while keeping the new tests fails `test_evidence_rejects_unrelated_extra_producer`, `test_disjoint_producers_require_separate_scoped_evidence`, and the tightened `test_state_evidence_must_bind_producer_for_claimed_scope`. The "must continue to pass" guard `test_single_correctly_scoped_producer_remains_valid` passes under both, so the tightening is not over-broad.
2. **Invariant holds at every placement.** Adversarial probes confirm per-producer applicability is enforced at scenario, trajectory, state, and subsystem placements, that an unrelated *extra* producer is rejected even alongside a valid one, and that cross-trajectory provenance leakage (baseline evidence citing a counterfactual-only model) is refused. Positive controls remain valid.
3. **No dual-implementation drift.** The tightened predicate in `reference/python/openbody_ref/validation.py` and `tools/validate_openbody.py` is logically identical, and both validators agree on accept/reject for every probe.
4. **No masked coverage.** The `test_reference_host.py` fixture tweak preserves test intent: each `mismatch` case still rejects for its own request-response reason (`subject`, `perturbation`, `horizon`, `scopes`), not for a provenance error raised earlier in `client.simulate`.
5. **No per-model applicability bypass.** `ModelReceipt` declares no scopes of its own, so producer scope is necessarily placement-derived; the host independently cross-checks each receipt against the discoverable `BodyModel` `scopes` and `applicability` in `_reference_simulate`.
6. **No stale normative text.** The only remaining references to unioned scope coverage are the new prohibitions in `OPENBODY.md` and this document.

## Remaining actions — pending owner authorization

The gate is clean, so the following are unblocked. They are outward-facing and have not been performed:

1. Resolve the historical review threads.
2. Merge PR #5.
3. Freeze and tag the OpenBody 0.1 interoperability baseline.
4. Rebase InVivo/Metabolog #972 onto that exact contract.
5. Add cross-repository conformance fixtures and CI.

## Local workspace hygiene

The LandingPage repository is pushed on its `main` branch at `cd361000533d07f28d99456ec51c77fd4140adeb`. OpenBody records it as a submodule in commit `b2b937c847e5892fce5890a0280c3a51f50bdfdb`. The model manifesto and its deliverable assets are committed at `5e174482321f96fb83bcf332312c0f300aa4eb17`.

The local working tree was clean when this handover was updated.
