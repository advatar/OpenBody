# PR #23 evidence and adversarial audit — 2026-09-20

Baseline: `90d3d3c3412ecebc87ecef5f858fee4b407e1957`, against main
`8c2dff59c6c5e431b99db38e197a659f029e7244`. No history rewrite or merge.

## Before/after

Before: **42 changed files, 33,850 additions, 0 deletions** against main.
After: **44 files changed, 3163 insertions(+)** against the same main.
Net tracked blob payload attributable to the PR: **1216138 → 159901 bytes**.
These byte counts sum changed-file blob size deltas from main, not filesystem
allocation or compressed Git pack size. Historical blobs still exist: deleting
from the tip does not shrink existing clones or remove Git history. A subsequent
squash could omit those historical dumps; no squash/force-push was performed.

Two generated SCKAN dumps accounted for **32,146 added lines** and 1,111,533
bytes. They are replaced by one compact receipt containing both run identities,
counts/digests and at most two selected typed bindings per query. Exact queries,
canonicalization and engine/source pins are unchanged. Both full original runs
were saved externally and verified against compact receipts before removal.
The external-output verifier checks all rows, not just the selected ones.

Removed reconstructable raw DataCite/dataset/file-list responses are replaced by
compact source receipts and the ASCENT identity/reference investigation. The
GitHub release response is reduced to release/asset fields and its original raw
snapshot digest. A reconstructable source-code hash manifest was removed; Git
already versions those files and its stale hashes risked misleading readers.
No upstream archive, database, Docker state, cache, secret or unrelated material
was found in the PR. Runtime caches remain outside the repository.

## File classification

A = source code, queries, workflow and source license; B = tests;
C = small durable provenance metadata, including authored audit/report prose;
D = small canonical evidence/selected regression facts;
E = generated output; F = reconstructable upstream data;
G = cache/runtime state; H = accidental/unrelated material.
Only A–D remain at the tip. Every original and new PR file is listed below.
No G/H files were identified.

| File | Before | After | Disposition |
|---|---|---|---|
| `.github/workflows/sparc-research.yml` | A | A | Retained/updated |
| `STATUS.md` | C | C | Retained/updated |
| `experiments/sparc/README.md` | C | C | Retained/updated |
| `experiments/sparc/UPSTREAM.md` | C | C | Retained/updated |
| `experiments/sparc/VALIDATION.md` | C | C | Retained/updated |
| `experiments/sparc/__init__.py` | A | A | Retained/updated |
| `experiments/sparc/adapter.py` | A | A | Retained/updated |
| `experiments/sparc/audit_ascent.py` | — | A | Added |
| `experiments/sparc/authenticate.py` | A | A | Retained/updated |
| `experiments/sparc/authenticate_ascent.py` | A | A | Retained/updated |
| `experiments/sparc/benchmark.py` | A | A | Retained/updated |
| `experiments/sparc/evidence/ASCENT_REPRODUCTION.md` | C | C | Retained/updated |
| `experiments/sparc/evidence/AUDIT.md` | C | C | Retained/updated |
| `experiments/sparc/evidence/PR_AUDIT.md` | — | C | Added |
| `experiments/sparc/evidence/SCKAN_REPRODUCTION.md` | C | C | Retained/updated |
| `experiments/sparc/evidence/manifests/ascent-comparison-gate.json` | C | C | Retained/updated |
| `experiments/sparc/evidence/manifests/ascent-datacite.json` | F | — | Removed; raw identity/retrieval retained |
| `experiments/sparc/evidence/manifests/ascent-dataset.json` | F | — | Removed; raw identity/retrieval retained |
| `experiments/sparc/evidence/manifests/ascent-files.json` | F | — | Removed; raw identity/retrieval retained |
| `experiments/sparc/evidence/manifests/sckan-release.json` | F | C | Compact replacement |
| `experiments/sparc/evidence/manifests/tooling-sha256.json` | C | — | Removed; raw identity/retrieval retained |
| `experiments/sparc/evidence/receipts/ascent-artifacts.json` | C | C | Retained/updated |
| `experiments/sparc/evidence/receipts/ascent-environment.json` | C | C | Retained/updated |
| `experiments/sparc/evidence/receipts/ascent-identity.json` | — | C | Added |
| `experiments/sparc/evidence/receipts/ascent-manifest-investigation.json` | — | C | Added |
| `experiments/sparc/evidence/receipts/ascent-reference-search.json` | — | C | Added |
| `experiments/sparc/evidence/receipts/hosted-ci.json` | C | C | Retained/updated |
| `experiments/sparc/evidence/receipts/local-checks.json` | C | C | Retained/updated |
| `experiments/sparc/evidence/receipts/metadata-sources.json` | C | C | Retained/updated |
| `experiments/sparc/evidence/receipts/sckan-artifacts.json` | C | C | Retained/updated |
| `experiments/sparc/evidence/receipts/sckan-queries-first-run.json` | E | — | Removed; raw identity/retrieval retained |
| `experiments/sparc/evidence/receipts/sckan-queries.json` | E | D | Compact replacement |
| `experiments/sparc/evidence/receipts/simple-sckan-diagnostic.json` | C | D | Retained/updated |
| `experiments/sparc/evidence_tools.py` | — | A | Added |
| `experiments/sparc/export.rq` | A | A | Retained/updated |
| `experiments/sparc/queries/LICENSE.upstream` | C | A | Retained/updated |
| `experiments/sparc/queries/bladder-target.rq` | A | A | Retained/updated |
| `experiments/sparc/queries/keast-5-rat.rq` | A | A | Retained/updated |
| `experiments/sparc/queries/keast-5.rq` | A | A | Retained/updated |
| `experiments/sparc/queries/missing-population.rq` | A | A | Retained/updated |
| `experiments/sparc/queries/upstream-apinatomy.rq` | A | A | Retained/updated |
| `experiments/sparc/reproduce_sckan.py` | A | A | Retained/updated |
| `experiments/sparc/sources.json` | C | C | Retained/updated |
| `experiments/sparc/test_evidence.py` | B | B | Retained/updated |
| `experiments/sparc/test_provenance.py` | — | B | Added |
| `experiments/sparc/test_reproduction.py` | B | B | Retained/updated |
| `experiments/sparc/test_sparc.py` | B | B | Retained/updated |
| `experiments/sparc/test_upstream_lock.py` | B | B | Retained/updated |
| `experiments/sparc/upstream-lock.json` | C | C | Retained/updated |

## Fresh adversarial review

This was a fresh local review of the resulting branch, not independent scientific
sign-off. Tests are software evidence only. Findings and fixes:

1. **Wrong UUID attribution.** Our prior lock and the SPARC citation example were
   not independent evidence of Guided Mode identity. Authenticated dataset 365
   and historical ASCENT documentation identify the old UUID as Tutorial. The
   lock correction retains the rejected identity and links primary receipts.
2. **Hash/size inconsistency.** Matching SHA-256 did not justify accepting 4,110
   versus 5,318 bytes. Multiple raw reads, immutable object version, headers and
   self-entry establish the API contradiction. The failed check is preserved.
3. **Overstated environment blocker.** Guided Mode uses pre-solved FEM potentials.
   Missing COMSOL alone does not establish inability to run that path. Exact
   potential provenance and NEURON environment remain required; no software or
   solver substitution was attempted.
4. **Post-hoc/arbitrary tolerance risk.** A generic 1% threshold-search stopping
   rule and warnings about another Portal dataset are not a reproduction
   tolerance. There is no candidate result and no executable contract.
5. **Generated evidence obscured provenance.** Complete result dumps and raw API
   wrappers are removed from the tip. Rerun tools now require external output
   directories. Full-result integrity checking remains available and is tested
   against corrupted unselected rows and independently run on both old dumps.
6. **Premature success persistence.** The SCKAN runner previously wrote successful
   receipts before its final journal check. It now publishes the external output
   after final verification, marks an integrity/comparison failure explicitly,
   and does not print final PASS before the check. No query semantics changed.
7. **Collapsed comparator states.** A failed candidate previously overwrote an
   INCOMPARABLE result, and could override a missing-reference BLOCKED result.
   Both states now retain precedence; focused regression tests cover both.
8. **No fresh upstream authority in offline tests.** Lock/receipt equality tests
   are explicitly consistency checks. Public HTTPS retrieval and versioned
   artifact hashes supply the provenance; selected facts do not authenticate a
   full run by themselves. Source/API drift is not silently committed by tools.
9. **No new scientific inference.** Native SCKAN query text/hashes are unchanged.
   Anatomy, function, recruitment, target engagement and clinical benefit remain
   separate; no species or modality transfer, clinical assertion or Cymba work.
10. **Scope/security/reproducibility.** Reviewed staged paths, sizes and content
    for archives, runtime state, credentials and personal machine paths. The
    deterministic offline suite has no dependency downloads or live services.
    Local path examples are generic temp directories, not private user paths.

## Previous review gate (superseded by the admission milestone below)

The investigation and cleanup can be reviewed on their evidence, but this is
not ASCENT reproduction completion. PR stays draft. A reviewer must explicitly
accept the bounded SCKAN success plus documented ASCENT BLOCKED scope, or require
the authorized Guided Mode study export, complete runtime/input/potential lineage
and published numerical output before progressing the milestone. That output is
needed to commit a defensible contract before any candidate execution.

## External admission milestone review — 2026-09-20

Starting head `15ff70ee41c59c6d11f6132507a8f66205fde948`; main's only intervening
change is issue #24 planning in STATUS, preserved by merge. PR #19 was inspected
at `bb3c689802e9284a29c200e42b8a01b96fa0680f`: model-family docs/schema/runtime
already supply qualification and context admission. They remain unmerged;
PR #23 documents that boundary rather than installing a competing authority.

Additional files are narrowly classified:
- A source: `experiments/sparc/contract.py`, committed pre-invocation exact-byte gate.
- B tests: `experiments/sparc/test_contract.py`, synthetic Git ordering/failure tests and receipt-linked examples.
- C metadata: `experiments/sparc/examples/admission.json`, compact non-authoritative claim examples.
- C policy: `docs/EXTERNAL_MODEL_ADMISSION.md`, evidence/qualification mapping and trust boundary.
Existing A–D classifications above remain; no generated dumps or runtime caches added.

Fresh adversarial review findings and fixes:
- The numerical helper's old README wording implied tolerance predeclaration
  that it does not enforce. Corrected it and documented diagnostics versus the
  sole new candidate invocation gate. A comparison helper never grants admission.
- A new fixture initially treated the missing-population receipt as REPRODUCED;
  its actual label is VERIFIED with UNKNOWN coverage. Tests now retain that exact
  distinction and verify the repeated digest, without changing historical evidence.
- Merely accepting an environment claim did not bind actual input/model bytes.
  The gate now checks both artifact and input digests before invocation; the
  trusted adapter still must attest that it executes those bytes in that runtime.
- Tests reject changed/staged/symlink/duplicate-key contracts, nonancestor commits,
  unknown/missing context, arbitrary/NaN tolerance, mismatched artifacts/inputs/runtime,
  missing/wrong reference and the actual incomplete ASCENT gate. Failure states
  remain distinct. Synthetic PASS is not scientific evidence.
- Historical SCKAN reproduction is not relabeled as a newly precontracted run.
  No upstream authentication was re-inferred from the lock, no queries expanded,
  no ASCENT candidate invoked, and no size failure or UUID difference waived.
- PR #19 is explicitly identified as pending. No model-family/runtime/protocol code
  was copied or changed. No patient/context authority is synthesized by examples.

This is a fresh local adversarial review, not independent scientific approval.
External human review is still required before merge. ASCENT's external resource
gate is now issue #25 and is not itself a blocker to reviewing this bounded PR.
Readiness requires green final-head CI; neither marking ready nor passing tests
constitutes approval, biological validation or a merge authorization.
