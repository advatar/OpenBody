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
