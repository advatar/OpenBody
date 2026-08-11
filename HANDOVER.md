# OpenBody PR #5 Handover

## Current checkpoint

- Repository: `advatar/OpenBody`
- Pull request: [#5](https://github.com/advatar/OpenBody/pull/5)
- Branch: `fix/openbody-0.1-hardening`
- Qualified protocol commit (provenance patch only; see active gate): `253b65536050f7f6d65916355f55aaca175775a4`
- State: draft, open, and unmerged — blocked on two P1 host findings
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

## Final bounded review: NOT clean — two live P1 blockers

The gate is **not** satisfied. A first pass over the patched provenance invariant reported zero findings, but that pass was scoped to the evidence/provenance class and to the invariant classes the reference suite already exercises. Sweeping the 21 not-outdated historical review threads on PR #5 against current HEAD reproduced **two P1 findings at `ee4ad24`**. Both are host trust-boundary gaps, not provenance gaps, and neither is covered by the reference suite.

### P1-A — `GET /v1/simulations/{id}` does not recheck producing-model applicability

`get_simulation` in `reference/python/openbody_ref/host.py:207-213` calls only `semantic_validate(scenario)`. It never consults `store.models`, so it never applies the `producing_model_requirements` capability/scope/applicability gate that `_reference_simulate` applies on the write path.

Reproduction: load the bundled fixture, detach one descriptor's `applicability` from the aliased fixture object, set its `subject` to `subject:other` and its `scopes` to `["ob://human/cardiovascular/heart"]`, then `GET /v1/simulations/scenario-post-meal-walk-001`. The endpoint returns HTTP 200 with `disposition: simulated`. The same mutation on `POST /v1/simulations` correctly abstains with `insufficient_validation`, which confirms the read path is the gap.

### P1-B — the host never binds a simulated result to the hosted twin

`_reference_simulate` in `reference/python/openbody_ref/host.py:66-75` compares the request against `candidate`'s own baseline, but never compares `candidate["subject"]` or the baseline subject with `store.state["subject"]`.

Reproduction: build a fully self-consistent foreign fixture (`subject:other` in the scenario, applicability, every evidence reference, and every trajectory state), load it so the descriptors are foreign too, then graft the canonical hosted twin back as `store.state`. An exact request returns HTTP 200 with `disposition: simulated` and `subject: subject:other`, while `GET /v1/state` still reports `subject:local-demo`. A store whose descriptors remain canonical abstains, so the earlier partial check closes only the mixed-store case, not the self-consistent one.

### Also observed (not a protocol invariant, worth folding into whichever patch lands)

`InMemoryTwinStore.from_fixture` at `reference/python/openbody_ref/store.py:103` assigns `fixture["applicability"]` into every generated descriptor by reference rather than by copy. Every descriptor and the scenario therefore share one mutable object, so mutating a descriptor's applicability silently rewrites the scenario's. This masks descriptor-level mutation tests and should be a `deepcopy`.

### What the first pass did establish

These items were verified and remain sound; they are not in question:

1. **Regressions bite.** Reverting `validation.py` to `6f422f9` while keeping the new tests fails `test_evidence_rejects_unrelated_extra_producer`, `test_disjoint_producers_require_separate_scoped_evidence`, and the tightened `test_state_evidence_must_bind_producer_for_claimed_scope`. The "must continue to pass" guard `test_single_correctly_scoped_producer_remains_valid` passes under both, so the tightening is not over-broad.
2. **Invariant holds at every placement.** Adversarial probes confirm per-producer applicability is enforced at scenario, trajectory, state, and subsystem placements, that an unrelated *extra* producer is rejected even alongside a valid one, and that cross-trajectory provenance leakage (baseline evidence citing a counterfactual-only model) is refused. Positive controls remain valid.
3. **No dual-implementation drift.** The tightened predicate in `reference/python/openbody_ref/validation.py` and `tools/validate_openbody.py` is logically identical, and both validators agree on accept/reject for every probe.
4. **No masked coverage.** The `test_reference_host.py` fixture tweak preserves test intent: each `mismatch` case still rejects for its own request-response reason (`subject`, `perturbation`, `horizon`, `scopes`), not for a provenance error raised earlier in `client.simulate`.
5. **No per-model applicability bypass.** `ModelReceipt` declares no scopes of its own, so producer scope is necessarily placement-derived; the host independently cross-checks each receipt against the discoverable `BodyModel` `scopes` and `applicability` in `_reference_simulate`.
6. **No stale normative text.** The only remaining references to unioned scope coverage are the new prohibitions in `OPENBODY.md` and this document.

## Active gate

Per the standing rule, only the two P1 findings above are the next blockers. Do not widen the patch opportunistically, and do not reopen the closed provenance work.

**Do not merge PR #5, and do not resolve the historical review threads.** 21 of the 37 unresolved threads are not outdated; at least the two above still reproduce, so a blanket resolve would bury live findings. Threads must be resolved individually, each against a verified fix.

Required sequence:

1. Patch P1-A and P1-B, with a regression per finding that fails against `ee4ad24`.
2. Re-run full qualification.
3. Re-sweep the remaining not-outdated threads against the new head, not just the two patched ones.
4. One further bounded review at the same zero-P1/P2 gate.

Only once that gate is genuinely clean:

1. Resolve the historical review threads individually.
2. Merge PR #5.
3. Freeze and tag the OpenBody 0.1 interoperability baseline.
4. Rebase InVivo/Metabolog #972 onto that exact contract.
5. Add cross-repository conformance fixtures and CI.

## Review-thread sweep status

The 16 outdated threads were not individually re-verified. Of the 21 not-outdated threads, the following were checked against current code and are addressed: duplicate trajectory/state IDs (`validation.py:252-257`), client request-response closure (`client.py:75-88`, all four mismatch cases confirmed to reject for their own reason), scenario-level evidence in scope closure (`validation.py:144-145`), expired-baseline abstention (`host.py:76-81`), producing-model capability/scope enforcement (`host.py:114-117`), per-state validity intervals (`validation.py:274`), stored-scenario validation before outcome binding (`store.py:122-125`), recursive evidence placement (`scenario_evidence_bindings`), baseline `state_time` ordering (`validation.py:284`), scope-less nested and trajectory producers (`store.py:30`, `validation.py:271,281`), returned-baseline digest comparison (`client.py:78`), calibration hosted-twin subject binding (`store.py:149-150`), nested-evidence placement provenance (the patched invariant), and conditional bound-evidence schema requirements (the abstention fixture validates).

Not yet re-verified: full-length digest enforcement, and rejection of evidence timestamped after `generated_at`. Both are P2 and should be settled in step 3 above.

## Local workspace hygiene

The LandingPage repository is pushed on its `main` branch at `cd361000533d07f28d99456ec51c77fd4140adeb`. OpenBody records it as a submodule in commit `b2b937c847e5892fce5890a0280c3a51f50bdfdb`. The model manifesto and its deliverable assets are committed at `5e174482321f96fb83bcf332312c0f300aa4eb17`.

The local working tree was clean when this handover was updated.
