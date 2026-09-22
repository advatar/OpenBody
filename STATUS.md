# Status

## In review — post-merge qualification audit of 900b064 — 2026-09-22

Issue: https://github.com/advatar/OpenBody/issues/31
Branch: `fix/intervention-observation-audit` (draft PR, not to be auto-merged).

`900b064` was an intentional preservation commit made during a laptop/worktree
migration. The process defect was not preserving the work. It was merging
preserved-but-unreviewed work into `main` without a distinct review step. The
audit verdict is keep and harden. Because nothing depends on the profile yet,
the hardening goes all the way to a `2.0` revision rather than staying
1.0-compatible.

- [x] Exact disclosure: present content that is not disclosed is rejected
  (`undisclosed_content_present`).
- [x] Non-finite numbers rejected; measurement phases and the patient response
  ordered against the session (`invalid_measurement_phase`, `invalid_interval`);
  zero-length consent window rejected.
- [x] `tools/validate_openbody.py` no longer crashes on non-object JSON; CI
  parses the profile schema.
- [x] Docs carry a claim-to-enforcement table that separates schema, validator
  and intake enforcement from what no payload can prove (a fabricated value, a
  meaningful token, a raw-signal attestation). Example limitations are stated.
- [x] ARCHITECTURE.md: OpenBody hosts the contract. It does not own custody,
  consent or disclosure decisions.
- [x] Neutral synthetic example; adversarial tests.
- [x] `deploy/openbody/CADDY-BLOCK.md` (carried in by the preservation commit,
  unrelated to the profile) removed. It proxied `openbody.invivo.health` to a
  self-hosted landing page that fails TLS. The landing page is hosted by Lovable
  at `openbody.advatar.systems`, and DEPLOYMENT.md now says so.
- [x] Profile revised to `2.0`, since no producer, consumer or published app
  exists: explicit `not_observed` missingness with a reason and a measurement
  origin; UCUM units and ranges per metric and dose dimension; a closed dose
  vocabulary; token identifiers and URI references; neutral evidence kinds with
  a named producer for derived analyses; a required disclosure recipient; one
  entry per metric and phase; subject binding ordered before disclosure;
  `follow_up_offset_seconds` and `heart_breath_synchronization` removed. 1.0 is
  withdrawn and fails conformance.
- [x] `InterventionObservationIntake`: a reference receiver with required
  subject-binding and consent verifiers, and checks for recipient, consent
  window at receipt, and replay/ID reuse.
- [ ] Operator decision outside this repo: `openbody.invivo.health` points at
  the home connection, where Caddy answers without a certificate. No OpenBody
  protocol host is publicly deployed anywhere. Either repurpose the name for a
  `catalogue`-mode host (DEPLOYMENT.md) or retire the record.

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

