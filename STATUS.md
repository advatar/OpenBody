# Status

## Active — Specialist composition and durable synthetic twin — issue #13

GitHub issue: https://github.com/advatar/OpenBody/issues/13
Branch: `feat/13-cognitive-health-demo`

- [x] Compose exact specialist outputs only after descriptor, receipt, evidence, scope and horizon validation.
- [x] Add durable reference storage with unchanged canonical JSON/digest semantics.
- [x] Support the exact post-meal-walk fixture and intentional fail-closed negative case.
- [x] Emit a minimized clinical-assertion reference and add restart tests.
  References carry digests, scope, provenance and qualification state only. The
  demo declares no validity window, no evaluated applicability and no calibrated
  uncertainty, so `validate_clinical_reference` refuses it at each gate. Two demo
  coordinates (`ob://human/behavior/activity_tolerance`,
  `ob://human/autonomic/recovery_load`) are not in the registry and are returned
  as explicit projection refusals; registering them is a separate protocol
  decision.

Boundary: synthetic demonstration only. No clinical validation claim, raw personal data disclosure, authority bypass, or production-security claim.

Implementation progress (2026-09-02): the shared event ABI is pinned. The durable reference twin now exposes `/v1/demo/compose`; three exact specialist results produce a schema-valid BodyState, while missing, duplicated, substituted, or tampered receipts produce an abstention. Minimized clinical assertion emission remains open.

## M5 deployment follow-up

- [x] Keep repository schemas and fixtures discoverable in the installed demo image (AdvatarDemo #3).

## Implemented — intervention source-observation profile — 2026-09-21

Issue: https://github.com/advatar/OpenBody/issues/28
Implementation branch: `feat/intervention-observations`.

Adopted from uncommitted working-tree work and landed unchanged apart from a
README link. A therapy app can now disclose a consented record that an
intervention occurred, with selected before/end/follow-up measurements and
derived-analysis references, without that record being admissible as an
OpenBody-derived assertion.

- [x] `openbody.intervention-observation/1.0` closed schema with
  `projection_class` fixed to `source_observation`.
- [x] Validation with stable rejection codes: registry-checked scopes, interval
  ordering, consent window ordering, and a disclosure allowlist that cannot name
  absent content.
- [x] Conformance validator routes documents of this profile to that validator.
- [x] Profile documentation, a bounded example, and 7 tests including the
  negative that a source observation still fails the clinical-assertion boundary.

Boundary preserved: raw ECG/EEG sample arrays are outside the profile, absent
measurements are omitted rather than filled, an `unavailable` dose cannot carry a
value, and changing `projection_class` does not convert an observation into a
derived object. Clinical admission still requires model execution, a receipt, and
an `openbody.clinical-assertion-reference/1.0` projection.

Not done: no host ingestion path for this profile. The replay-safety and
ID-reuse semantics in the profile document are consumer requirements, not
behaviour the reference host implements.

## Implemented — independent deployment handover — 2026-09-21

Issue: https://github.com/advatar/OpenBody/issues/26
Implementation branch: `feat/deployment-handover`.

The repository had no deployment artifacts, and the only observation host factory
required a reachable ProvidEHR deployment with an authorized tenant/EHR. An
external developer could therefore run the bundled demo twin or a catalogue and
nothing else.

- [x] `DEPLOYMENT.md`: modes, prerequisites, proxy boundary, verification, and the
  constraints an operator must design around (no authorization, in-memory state,
  single-tenant by construction, checkout-relative artifact resolution).
- [x] `deploy/openbody/`: Dockerfile, compose file with one service per mode,
  `env.example`, systemd unit, Caddy example, and an `OPENBODY_MODE` entrypoint —
  catalogue hosting previously had no factory of its own.
- [x] `LocalObservationSource`: the admitted-observation path resolving a directory
  of clinical version documents instead of the clinical API. The post-fetch
  verification is extracted and shared, so both resolvers admit exactly the same
  documents; the local one verifies every document at startup rather than on first
  read. It substitutes the transport, not the admission policy.
- [x] `examples/local-observations/`: one runnable synthetic admitted document.
- [x] Fail-closed configuration and an honest operational signal: unknown mode,
  demo twin and non-authoritative source each require an explicit opt-in, and
  `/healthz` names the resolver the process is bound to.
- [x] 33 new unit tests; 212 reference tests and fixture conformance pass on 3.12.
- [x] Verified in a container end to end: build, `observations-local` startup with
  no clinical API, ingest and read of the shipped document, absent subject routes,
  and in-image conformance.

The local source is not a clinical authority and does not make one. Its trust
boundary is the file system, so any deployment handling real clinical data still
resolves through the authorized clinical API. The 0.1 wire contract is unchanged:
the source kind is reported on `/healthz`, outside the protocol surface.

Not done: no persistence layer, so a restart still drops protocol state, and the
reference host still implements no authorization. Both are stated in
`DEPLOYMENT.md` as operator responsibilities rather than silently deferred.

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

## 2026-09-20 — Closed-loop experimental physiology: observation to hypothesis to intervention to evidence

- [ ] Track in GitHub issue #24.
- [ ] Execute the bounded plan in the issue without weakening existing authority, privacy, provenance, or release gates.
- [ ] Add adversarial/negative-control coverage appropriate to this track and record qualification evidence before promotion.

## 2026-09-22 — Whole-person state contract for interoperable executable human models

GitHub issue: #30

- [ ] Inventory existing canonical contracts and baselines before implementation; do not duplicate authority, provenance, state, or evaluation primitives.
- [ ] Implement the bounded architecture and adversarial/negative-control plan recorded in issue #30.
- [ ] Add machine-readable evidence and non-vacuous qualification gates; distinguish implementation, local qualification, CI qualification, and any remaining research/clinical limits.
- [ ] Preserve existing privacy, consent, authority, provenance and release boundaries; do not promote experimental results without preregistered/explicit gates.