## Current native DG model qualification (2026-09-16)

Branch `feat/18-model-family-contract`, issues #18/#20 and draft PR #19; paired
native DG source `b68b410` on `feat/7-bounded-execution` / DG PR #8. The real
`DgQualificationAuthority` now connects the actual execution/read HTTP host to
fresh native DG qualification backed by current EUWallet inputs. Pinned command,
key/policies, subject and exact model/evidence bindings are trusted host settings.
Every declared dependency/evidence descriptor must appear in native frozen review;
missing or changed review commitments refuse. Fresh audit references are retained
without turning qualification into a provider-effect authorization.

Local verification: **423 tests pass**, including 31 wire/host verifier tests and
**eight actual DG/wallet/SurrealDB/HTTP composition cases**. Valid synthetic model
execution preserves unknown uncertainty; revoked reviewer/operator/subject status,
withdrawn consent, revoked evidence, missing wallet inputs and omitted review
dependencies disable execution and retained reads. Consent withdrawal during the
model call suppresses the result. Core and clinical-reference conformance pass.
Hosted CI is skipped. See [configuration and reproduction](docs/DG_MODEL_QUALIFICATION.md).

Synthetic arithmetic/public test keys establish software enforcement only.
Production issuer enrollment, independent patient linkage, native physiological
model/source integration, qualified model composition, clinical efficacy and full
G3/G4/G7/G8/G17 remain open. Earlier checkpoints below retain their original scope;
statements that no native DG qualification adapter exists are superseded here.

Tracking current DG authority migration: https://github.com/advatar/OpenBody/issues/20

Documentation cleanup is complete on this feature branch: current DG resolution,
EUWallet and credential inputs replace the retired gateway terminology.
Validation: scoped reference scan and git diff --check pass; no runtime change.

## Active — current DG authority architecture (2026-09-15)

Remove the superseded external capability gateway throughout this repository.
EUWallet and verifiable credentials provide inputs; DG resolves current authority
for each exact action and context, verified immediately before effect.
Use local unit tests and skip hosted CI. Track implementation and remaining
production composition honestly; capability discovery never grants permission.

# Status

## Active — G3/G4 model-family execution boundary — 2026-09-15

Issue: https://github.com/advatar/OpenBody/issues/18
Branch: `feat/18-model-family-contract`; native consumers remain on
Metabolog `feat/1129-openbody-twin-protocol` / issues #1129 and #1130.

Qualified counterfactual execution is now implemented in the reference runtime.
Contracts pin perturbation class/scope, numeric dose/timing and effect bounds;
explicit counterfactual callables produce matched control/intervention forecasts.
The runtime derives same-horizon effects and returns a ModelCounterfactual with
a frozen-core scenario plus explicit no-intervention comparison. Sources,
qualification, unknown uncertainty, context, receipts and time remain bound and
revalidated. No action authority is emitted. Local tests: 328 total, including
42 new counterfactual cases, plus core/clinical-reference conformance. Hosted CI
for this addition remains pending; native physiological/clinical qualification
and model/source integration are not established by these synthetic tests.

Forecast implementation is now added: explicit positive-horizon registrations,
a separately typed ModelForecast envelope around frozen-core BodyTrajectory,
ordered bounded points, source/qualification rechecks, uncertainty propagation,
full trajectory/request receipts and matching host/client verification. Current
state registration remains horizon zero. Qualification expiry stays separate from
predicted physiological time; no authority is extended to reach a future point.

Local verification passes 286 reference tests (45 new forecast cases), frozen
core and clinical-reference fixtures. Forecast tests execute only deterministic
synthetic arithmetic. This does not qualify the native post-meal model, establish
CGM/walking source lineage, provide a production DG authority or native qualified counterfactual integration. Hosted conformance `34916946185` passes at functional
forecast head `5859a4672304df094160c8e2075615661444e10e`.

Add a versioned model-family contract alongside the frozen core schema, then
apply it to an actual model call in the reference host: current qualification
and dependencies, admitted source resolution, context/population/question/horizon,
required observations, uncertainty, output bounds and adaptation. Recheck source
and qualification after execution so revocation cannot leave a reusable result.
Out-of-envelope adaptation creates a DG review candidate, never activation.
The reference executor supports state estimation, forecasts and counterfactuals;
native runtime composition remains follow-up work, not implied completion.

The host must receive a trusted qualification resolver and verified model
registration from deployment configuration. Client-supplied descriptors,
qualification labels and observation bodies cannot authorize execution. Synthetic
tests prove software behavior only; a production DG authority adapter and governed
physiological/clinical qualification evidence are still required.

Reconciled branches after fetching/pruning main: `feat/16-admitted-observations`
was merged and its remote branch deleted. Older executable/reference-host work is
already represented on main; longitudinal query, adaptive state and cognitive
health demo work remain separate and are not silently merged into this boundary.

Implementation checkpoint: the additive contract, bounded current-state executor,
explicit reference HTTP host and client are implemented. Exact artifact identity,
host tenant/subject, current qualification context/evidence/dependency lease,
source admission/recency/uncertainty, output bounds and adaptation are enforced.
Source and qualification are checked again after the actual model call and on
retained-result reads. Unknown measurement uncertainty stays unknown. Out-of-
envelope adaptation produces an inert DG-review candidate without activation.

Hosted conformance `34914384357` passes at functional source
`6b0f7f496e9bfa3769b9fe83bd6b238f331e197b`, draft PR #19. The implementation
remains on its feature branch while native model integration and trusted
qualification resolution continue. It has not been merged or released.

Local verification passes all 241 reference tests (69 new model-family cases),
core protocol fixtures and clinical-reference conformance, plus diff checks.
Tests execute a bounded synthetic arithmetic callable with a fixture authority;
they do not establish physiological or clinical qualification. Production DG
qualification, native model call-site wiring, multi-model composition and durable cross-repository revocation remain open.
See `docs/MODEL_FAMILY_CONTRACTS.md` for exact trust and digest boundaries.

## Implemented — G2 admitted clinical observation bridge; joint release pending — 2026-09-14

Issue: https://github.com/advatar/OpenBody/issues/16
Implementation branch: `feat/16-admitted-observations`, PR #17. The PR records
its merge state; joint release also requires ProvidEHR PR #519.
The initial repository sync fetched all remotes and pulled main at `2a9a398`.
Other unmerged work exists on `feat/longitudinal-query-wearableqa` and
`feat/13-cognitive-health-demo`; neither is evidence that G2 is complete.

Authoritative producer tracking: advatar/ProvidEHR#524. Ingestion will resolve
the existing authorized versioned-composition API and require its stored typed
projection; clients cannot submit their own normalization status or values.

Initial source audit: the 0.1 reference host had no observation ingestion
capability and the core schema had no Observation definition. Clinical assertion
references already represent separately typed model-derived evidence.

- [x] Define a versioned admitted-observation profile carrying exact source,
  canonical code/value/unit/time, patient binding, normalization rule lineage
  and uncertainty, with no inferred authority or certainty.
- [x] Enforce the profile in the reference host/store/client ingestion and read
  paths, including idempotency and rejection of cross-patient/conflicting input.
- [x] Wire ProvidEHR's actual admitted-fact producer and verify its output through
  the OpenBody host. Dependency: advatar/ProvidEHR#523 / PR #519.
- [x] Verify the separate model-derived assertion return path and negative tests
  proving observation, inference, simulation and clinical assertion stay distinct.
- [x] Run conformance and producer/consumer tests and record exact version bindings.
- [ ] Complete joint G2 release after ProvidEHR required checks and merge.

The full PRODUCTION.md program (G1–G18) and integrated closure scenario remain
unfinished. A schema or isolated adapter alone does not close this gate. The
stable core 0.1 contract must not be silently redefined by this profile.

Implementation checkpoint: the typed profile, source resolver, host/store/client
paths, and explicit observation-only startup are implemented. The worker writes
the source-bound projection before its atomic clinical commit. The consumer
requires the authorized immutable version and re-resolves it on every read.
Unknown uncertainty stays unknown; rejected admissions cannot be promoted.

Local evidence: 172 reference tests (48 new bridge tests) and the existing
protocol/clinical-assertion fixture conformance pass. The committed kernel
fixture was generated by the real Rust projector; it is not worker execution
evidence. A separate live worker/API -> OpenBody HTTP verifier is implemented
for ProvidEHR CI and remains pending execution on pinned revisions.

The initial reverse-path audit found that ProvidEHR currently compares the
OpenBody subject string directly with an EHR id. That does not compose with
OpenBody's required `subject:` identifier convention for normal UUID EHRs.
Correcting and testing this production binding remains part of G2, alongside
required CI and the integrated assertion return path. See
[profile and operational boundaries](docs/ADMITTED_OBSERVATIONS.md).

Follow-up (advatar/ProvidEHR#525): the live verifier now includes a synthetic
model-reference return through the authorized runtime, with replay and
subject/type/expiry negatives. It rebases the existing test scenario to the
synthetic EHR and test clock; it does not claim to execute a model on the new
observation. ProvidEHR is adding the shared subject mapping, exact workforce
scopes and read-time reference validation. The 172 Python tests still pass;
this expanded integration remains pending at the pinned producer/consumer pair.

Verified bidirectional execution (2026-09-14): ProvidEHR run `34902892696`
passes at producer `9199f30c599029c32a64e9c95ffc43e760ecfb83` and this consumer's
functional revision `228de15f5676dcad6eb6a3d747c9ecfe5d2c87b3`. One actual live
integration test ran: worker -> ClinicalStore -> enforced API -> OpenBody HTTP
ingestion/read/replay, followed by the separately typed synthetic model-reference
return. Physician admission, nurse denial, patient/type/expiry rejection,
read/replay rejection of corrupted durable records, and unchanged original
clinical compositions all pass. This remains synthetic/in-memory execution
evidence; it does not qualify model physiology or a live vendor deployment.

OpenBody CI run `34902726178` and all 172 local reference tests pass. PR #17 is
ready for merge after the tracking update's checks. G2's joint release remains
open until ProvidEHR PR #519's remaining release/policy gates are resolved.
G3/G4 consumption and model qualification are tracked by Metabolog#1129.


G3/G4 next execution step (2026-09-15, issue #18): connect retained qualified
model executions to the existing clinical assertion reference profile. An
explicit host-configured publisher will require clinical-purpose qualification,
current independently verified tenant/EHR subject binding, exact source and
qualification rechecks, and known supported uncertainty before returning an
admission packet. State inference and counterfactual simulation stay distinct.
Software/research outputs cannot be relabeled as clinical; forecasts without a
compatible standalone clinical object profile must abstain. Verify actual model
call -> retained result -> publisher HTTP -> clinical-reference validation, with
revocation, expiry, binding, source changes and type negatives. This is not a
production DG/identity adapter or a native app integration claim.

Counterfactual revision `42b4b37` passed hosted CI `34919089702` (328 local
reference tests plus core and clinical-reference conformance).

Clinical publication implemented (2026-09-15): explicit
`QualifiedClinicalReferencePublisher` and opt-in reference/object GET routes
consume actual retained state/counterfactual executions. Publication requires the
original clinical-purpose lease and current exact independent subject binding;
software/research purposes and unknown uncertainty abstain. Source, dependency,
qualification and binding changes prevent return; identical reads retain a
stable immutable reference ID. Counterfactual receipts still reference the
complete control/intervention execution. No clinical action is submitted.

Validation: 383 reference tests pass locally, including 55 new actual-call/HTTP
publication and negative tests. Core and clinical-reference conformance pass.
Hosted checks are pending the commit. Production DG/identity adapters, native
callers, admission of these new packets through ProvidEHR, and downstream
transitive use-time revalidation remain open.

G3/G17 live integration follow-up (ProvidEHR#527, OpenBody#18): extend the
actual worker/API verifier to execute the qualified counterfactual runtime and
clinical publisher. Preserve the real worker observation's unknown uncertainty
and prove it cannot become a clinically admitted result. A separate explicitly
synthetic known-input observation will test positive runtime publication, actual
ProvidEHR admission/replay/read and issuer revocation. That positive fixture is
not evidence of qualified COSMIC measurement uncertainty. The gateway's fixed
trusted issuer must re-resolve all current uses and leave historical records
intact after denial.

Live verifier update implemented: the actual qualified counterfactual runtime and
authenticated publisher now serve the fixed issuer expected by ProvidEHR#527.
The real worker observation retains unknown uncertainty and cannot be published
clinically. A distinct synthetic known-input source exercises positive runtime
publication, admission/replay/state/simulation/A2UI reads and current issuer
qualification/dependency/identity/source revocation. All 384 local reference
tests and conformance pass. A local actual Python publisher -> real Rust clinical
admission crate + production HTTP resolver smoke passes, including revocation
denial. Full worker/gateway integration is pending ProvidEHR's updated CI pin;
this local smoke does not substitute for that gateway test or clinical evidence.

Verified full live integration (2026-09-15): ProvidEHR `ed4df64` with OpenBody
`38e8cb1` passed `34921269684`. The actual COSMIC worker -> admitted clinical
source API -> qualified counterfactual runtime preserves unknown uncertainty and
refuses clinical publication. A distinct synthetic known-input observation
passes actual model/publisher -> enforced gateway admission/replay/read/A2UI;
qualification, dependency, identity and source changes deny further use while
historical records and original clinical compositions remain intact. This
replaces the earlier fixture-only model-reference return with actual callable
execution evidence. It still does not establish clinical efficacy, qualified
COSMIC uncertainty, native callers, production DG/identity or full G17 graph
propagation. The publisher/known-source authorities in this verifier are
explicitly synthetic, test-only configuration.
