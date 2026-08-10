# OpenBody PR #5 Handover

## Current checkpoint

- Repository: `advatar/OpenBody`
- Pull request: [#5](https://github.com/advatar/OpenBody/pull/5)
- Branch: `fix/openbody-0.1-hardening`
- Qualified protocol commit: `2dc83ffb3a26a490d0af668c44f524386139ce10`
- State: draft, open, and unmerged
- Tracker: issue #3; issue #4 is closed as duplicate

## Latest bounded patch

Commit `2dc83ffb3a26a490d0af668c44f524386139ce10` closes the five findings reported against `51d367568978682ac16ca78084efd89b1ccc9187`:

1. Recursively validates evidence subject, placement scope, digest, model, and claim bindings.
2. Requires normalized baseline temporal coverage of perturbation start.
3. Rejects scope-less or incorrectly scoped nested producing models.
4. Makes `OpenBodyClient.simulate()` bind the returned baseline to the exact requested state using canonical semantic content.
5. Revalidates stored scenario/outcome semantics, horizon, window, subject, perturbation, metric, and scope lineage when accepting calibration.

The implementation consolidates these checks into shared evidence, producer, temporal, request-response, and calibration invariant machinery where practical. Normative text, the reference runtime/client, fixture, validator, and adversarial regressions are aligned.

## Qualification results

- Reference suite: `48 passed`
- Conformance validator: all examples pass
- JSON Schema validation/parsing: pass
- OpenAPI parsing: pass
- MCP profile parsing: pass
- `git diff --check`: pass
- GitHub `validate` CI: pass

## Active gate

A single final bounded adversarial Codex review was requested at:

https://github.com/advatar/OpenBody/pull/5#issuecomment-5243057463

Acceptance criterion: **0 unresolved in-scope P1/P2 findings** across the established OpenBody 0.1 invariant classes. The review must not expand into performance, deployment hardening, future protocol features, or unrelated security concerns.

Do not merge PR #5 or resolve historical review threads until this gate is clean. If the review reports another in-scope P1/P2, treat only that finding as the next blocker and do not widen the patch opportunistically.

If the review returns zero unresolved in-scope P1/P2 findings:

1. Resolve the historical review threads.
2. Merge PR #5.
3. Freeze and tag the OpenBody 0.1 interoperability baseline.
4. Rebase InVivo/Metabolog #972 onto that exact contract.
5. Add cross-repository conformance fixtures and CI.

## Local workspace hygiene

The following unrelated local work remains intentionally untouched and outside PR #5:

- staged: `.gitmodules`, `LandingPage`
- untracked: `MODEL.md`, `assets/`, `output/`, `tmp/`

`HANDOVER.md` is currently a local handover artifact and is not part of the protocol patch commit.
