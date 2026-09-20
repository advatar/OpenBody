# PR and qualification audit

Starting local workspace HEAD/main: `8c2dff59c6c5e431b99db38e197a659f029e7244`.
Starting PR #23 remote head: `49d8d9526cd1aeed377530dfd8e4c9bbd39e40b7`.
Main was already an ancestor. No rebase, force-push, merge or parallel PR was
needed. A linked worktree checked out the existing `research/sparc-m0` branch;
the user's original uncommitted work remains untouched.

Read the complete 12-file starting PR diff and inherited `advatar/AGENTS.md`.
User instructions override that file's normal merge/delete-branch policy and
new-issue default: keep existing issue #22 and draft PR #23, do not merge.
The older issue's 47-test claim did not match this starting tree (19 tests).
Current execution counts are recorded separately in VALIDATION.md.

Inspected `OPENBODY.md` Model/Evidence planes and simulation receipt requirements,
`docs/CLINICAL_ASSERTION_REFERENCES.md`, `reference/python/openbody_ref/clinical_reference.py`,
reference validation and conformance workflow. Model identity, exact version,
family, applicability, source/subject binding and epistemic class remain stable
runtime requirements. Research result receipts do not satisfy those requirements
or enter the registry, clinical-reference bridge, runtime, Twin or Cymba.
Only research files, its dedicated workflow and an additive STATUS.md entry change.

PR #23 was draft with no comments/reviews at audit time. Its SPARC workflow was
already active and running, rather than absent. Runs 35510888026 and 35510887209
failed in **Post Set up Python**, after tests, because `cache: pip` requested
saving a nonexistent pip cache. The standard-library suite installs nothing.
The fix removes that single unnecessary setting; no permissions or event
expansion is needed. `pull_request` and branch-scoped `push` path filters already
cover this PR. Both events can therefore produce runs for one push. YAML parsed
and action pins executed successfully on hosted runners. Repository Actions is
enabled (`allowed_actions: all`); SPARC workflow state is active.

No dependency downloads were added to the synthetic suite. Large real runs remain
manual local commands; no unneeded manual-dispatch workflow or credentials were
introduced. Initial fixed CI: SPARC runs 35511225017 / 35511227872 and conformance
35511227869 all succeeded. Final pushed-revision CI is reported in the handoff.
