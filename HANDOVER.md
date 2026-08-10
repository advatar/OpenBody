# OpenBody PR #5 Handover

## Current checkpoint

- Repository: `advatar/OpenBody`
- Pull request: [#5](https://github.com/advatar/OpenBody/pull/5)
- Branch: `fix/openbody-0.1-hardening`
- Qualified protocol commit: `6f422f9d46f1323627dc7340f6370ed5ea9497b8`
- State: draft, open, and unmerged
- Tracker: issue #3; issue #4 is closed as duplicate

## Latest bounded patch

Commit `6f422f9d46f1323627dc7340f6370ed5ea9497b8` closes the two P1 findings reported by the bounded review of `b5e986680f0a7f627ae418ed5ec1d967e61d5b2d`:

1. State and other nested evidence now binds claimed scopes to models that produce those scopes at the exact placement, rather than any producer in the object subtree.
2. Producing model descriptors must declare applicability subject, scopes, and horizon compatible with the scenario and exact receipt placement.

The patch extends the shared placement-aware evidence/producer scope maps and full model-applicability checks rather than adding fixture-specific exceptions. It preserves the previously closed subject, scope, temporal, discoverability, capability, evidence, request-response, outcome/calibration, and authority invariants.

## Qualification results

- Reference suite: `53 passed`
- Conformance validator: all examples pass
- JSON Schema validation/parsing: pass
- OpenAPI parsing: pass
- MCP profile parsing: pass
- `git diff --check`: pass
- GitHub `validate` CI: pass

## Active gate

A single final bounded adversarial Codex review must now verify qualified protocol commit `6f422f9d46f1323627dc7340f6370ed5ea9497b8`.

Acceptance criterion: **0 unresolved in-scope P1/P2 findings** across the established OpenBody 0.1 invariant classes. The review must not expand into performance, deployment hardening, future protocol features, or unrelated security concerns.

Do not merge PR #5 or resolve historical review threads until this gate is clean. If the review reports another in-scope P1/P2, treat only that finding as the next blocker and do not widen the patch opportunistically.

If the review returns zero unresolved in-scope P1/P2 findings:

1. Resolve the historical review threads.
2. Merge PR #5.
3. Freeze and tag the OpenBody 0.1 interoperability baseline.
4. Rebase InVivo/Metabolog #972 onto that exact contract.
5. Add cross-repository conformance fixtures and CI.

## Local workspace hygiene

The LandingPage repository is pushed on its `main` branch at `cd361000533d07f28d99456ec51c77fd4140adeb`. OpenBody records it as a submodule in commit `b2b937c847e5892fce5890a0280c3a51f50bdfdb`. The model manifesto and its deliverable assets are committed at `5e174482321f96fb83bcf332312c0f300aa4eb17`.

The local working tree was clean when this handover was updated.
