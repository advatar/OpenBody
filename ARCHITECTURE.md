# Advatar twin architecture: layer boundary decision

Status: decided. This record is the single authoritative statement of the boundary between InVivo,
OpenBody, OpenMind, BrIAn, and ProvidEHR. It lives in OpenBody because OpenBody is the neutral layer
every party already pins.

`InVivo/PROPOSAL.md` and `OpenMind/docs/health-super-app-plan.md` MUST reference this record rather than
restate it. Three drifting copies of the boundary is the failure this record exists to end: the OpenMind
health plan predates OpenBody and independently described physiological representation, subject identity,
and provenance, which is how the conflict arose.

## Layer ownership

| Layer | Owns | Does not own |
| --- | --- | --- |
| InVivo | The canonical biological Twin, raw observation custody, consent, disclosure decisions | The wire contract; governed memory |
| OpenBody | Physiological computation: state, models, simulation, outcome, calibration, abstention | Medical records; authority; memory |
| OpenMind | Governed memory, projection policy, redaction, retrieval, continuity | Physiological representation; a second `BodyState` |
| BrIAn | The reasoning and conversational interface | Policy enforcement; physiological inference |
| ProvidEHR | Clinical evidence, attestation, orders, workflow, authoritative write-back | Twin state; counterfactual computation |

The OpenMind health-event envelope (`advatar.health-event/0.1`) is a **projection envelope**, not a
physiological schema. No inferred physiology may be re-encoded in an OpenMind-specific payload.

## BrIAn has two legitimate paths

- **BrIAn → OpenBody** directly, for live state, model discovery, and simulation.
- **BrIAn → OpenMind**, for historical meaning, goals, preferences, reviewed conclusions, and continuity.

BrIAn may combine both. Neither replaces the other, and BrIAn does not become a second policy engine.

## Projection classes

For `health.*` domains the envelope payload carries exactly one of:

- `projectionClass: "source_observation"` — a user-approved summary with no corresponding OpenBody
  assertion yet. Carries `sourceReference` and `contentDigest`.
- `projectionClass: "openbody_reference"` — a governed reference to an OpenBody object. Carries
  `objectKind`, `canonicalRef`, `contentDigest`, `epistemicClass`, and the contract identity below.

OpenMind stores the governed reference plus a minimal human-readable projection. It never maintains a
second `BodyState`.

The envelope's scalar `provenance.confidence` is narrowed to **projection or extraction confidence only**.
It MUST NOT stand in for OpenBody's epistemic uncertainty, aleatoric uncertainty, coverage, applicability,
or out-of-distribution status. Those are structurally richer and live only in OpenBody objects.

`subjectId: "local-user"` is retired from all cross-system traffic. It may remain an internal fixture value.

## Contract identity is the schema version, not the release tag

A projection MUST identify the contract by `schema_version` (`"0.1"`) and, where stronger binding is needed,
a digest over the normative artifacts (`OPENBODY.md`, `schemas/openbody.schema.json`,
`openapi/openbody.openapi.json`, `profiles/mcp/tools.json`, `registry/coordinates.json`).

It MUST NOT identify the contract solely by git tag. Tags increment for reasons that are not protocol
changes: `v0.1.0-draft.2` carries a clean artifact tree and a larger coordinate registry, while its
schema, OpenAPI, and MCP profile are byte-identical to `draft.1`. A projection asserting
`openBodyVersion: "0.1.0-draft.2"` would therefore imply a semantic change that did not occur. Where a
projection needs to record which coordinates were registered when it was written, it carries the
`registry_version` alongside `schema_version` — not the tag. Release tags pin checkouts; they do not
describe contracts.

## Identity is a binding graph, never string equality

Independently revocable, verifiable edges:

```
OpenMind person  ←→ BrIAn Twin identity
OpenMind person  ←→ OpenBody subject
InVivo Twin      ←→ OpenBody subject
OpenBody subject ←→ ProvidEHR patient
```

Each edge records both namespaces and identifiers, issuer, assurance method, allowed purposes, issue and
expiry times, a revocation reference, and a digest or signature. "Same person" means a verified path
through this graph. A runtime proves only the path a given operation needs.

**OpenBody 0.1 cannot verify these bindings, and implementers must not assume it does.** In the frozen
contract, `subject` is a bare string; there is no field carrying a binding proof. OpenBody enforces that
every object and every read path is bound to *one consistent* subject — it cannot establish that the
subject denotes the person the caller means. Binding verification lives strictly above OpenBody, in InVivo
and in OMBODY. Any future in-band binding proof is a **protocol** 0.2 concern, distinct from the
coordinate registry's own version, which has already moved to 0.2 without changing protocol semantics.

## Authority

Authority stays external to OpenBody objects. An `authority_ref` is a reference to a grant; possession of
the string is never proof of authority. Grants come from several issuers — SMART/OAuth for ProvidEHR, InVivo
consent for local processing, a scoped grant for an OpenBody query, clinician approval for consequential
clinical workflow, and OpenMind peer grants. OpenMind is one issuer among several, not the authority.
InVivo decides which issuers it trusts and verifies every receipt itself.

## Retraction must propagate, so a digest alone is insufficient

A digest proves what was asserted, not that the assertion is still valid. When an OpenBody object is
retracted or invalidated — for example a calibration reveals the producing model was misapplied — any
OpenMind claim promoted from it, and any BrIAn context derived from that claim, is now downstream of a
withdrawn assertion.

Therefore an `openbody_reference` projection MUST retain both the content digest **and** a validity pointer
that can be re-resolved against the producing host. Claim promotion MUST record that pointer, and
promotion of a retracted assertion into durable memory MUST fail closed. Retraction propagation is a
first-class requirement of OMBODY-0.1, not a later refinement.

The executable projection contract, current-validity rules, and shared consumer fixture matrix are
defined in [`docs/CLINICAL_ASSERTION_REFERENCES.md`](docs/CLINICAL_ASSERTION_REFERENCES.md),
[`schemas/clinical-assertion-reference.schema.json`](schemas/clinical-assertion-reference.schema.json),
and [`examples/clinical-assertion-references.v1.json`](examples/clinical-assertion-references.v1.json).

## OMBODY-0.1 scope

OMBODY specifies the OpenMind-facing bridge, not body semantics. It references OpenBody's schema and copies
nothing: no `BodyState`, `Uncertainty`, or simulation structures. It covers supported OpenBody versions,
reference projection, subject-binding requirements, peer-grant scopes, authority-reference exchange,
epistemic-class preservation, minimum retained provenance and digests, claim-promotion restrictions,
retraction and revocation propagation, context-package redaction, and BrIAn discovery conventions.

OMBODY follows a working OpenBody projection, so its fixtures reference real conformant InVivo objects
rather than hypothetical ones.

## Sequencing

Bottom-up. Starting at the scenario encoder is backwards because nearly every required field depends on the
layers beneath it.

1. Canonical `HealthEvent` serialization and genuine SHA-256 digests.
2. Explicit `HealthEvent`/body-system → registered `ob://` coordinate mappings.
3. **Stand up cross-repository conformance CI here, not at the end.** From this point every layer is
   validated against the frozen `tools/validate_openbody.py` as it lands. Deferring the harness to the end
   leaves steps 4–11 unverified against the real validator until the last moment.
4. Evidence claim and producer bindings.
5. Subject-binding input.
6. Exact scope-closure derivation.
7. Exact normalized horizon derivation.
8. Placement-specific model references.
9. Conformant `BodyState`.
10. Conformant abstention.
11. Conformant simulated scenario.
12. Outcomes and calibration.

Then OMBODY-0.1, then BrIAn as a client of both paths.

## Deployment modes and tenancy

**One isolated logical authority per user, never one physical host per user.** Requiring
an iPhone plus an always-on Mac would be a deployment accident, not an architectural
requirement. Any client implementing the authenticated contracts qualifies — macOS, web,
Android, another agent — which is why digest canonicalisation is specified
implementation-independently and pinned by a cross-language golden vector.

| Mode | Always-on personal hardware | Capabilities |
| --- | --- | --- |
| Managed | no | full remote access and synchronisation |
| Self-hosted | yes, user-selected host | full control and availability |
| Device-only | no | private local use; no reliable remote access while offline |

Device-only is **not a degraded twin**. The whole loop — state, scenario, outcome,
calibration — runs with no server, and every object it produces is conformant. What it
loses is remote model discovery and federation, not correctness.

### The catalogue and the subject APIs deploy on different schedules

A `BodyModel` descriptor's only subject-bearing field is `applicability.subject`, which is
why a public catalogue can be forced to `CATALOGUE_SUBJECT` and carry no personal data at
all. So the model catalogue is shared, multi-tenant, and deployable immediately.

Subject APIs are not, because **the reference host is single-tenant by construction**.
`store.state["subject"]` is the hosted twin, and every read path binds to it: a stored
object for another subject is refused. Managed multi-tenancy therefore has two honest
routes.

1. **One lightweight instance per user behind a shared gateway.** Preserves the
   single-tenant invariant exactly as implemented. Isolation is process- and
   store-level, which is the strongest form available without new code.
2. **A tenancy layer** provisioning isolated namespaces, keys, backups, and runtime
   contexts, where the bound subject becomes the *authenticated* subject per request.
   This weakens a guarantee currently enforced structurally, and is only safe if the
   subject binding is proven on every request rather than configured once at startup.

Route 1 is the default until route 2's per-request binding exists. A shared process whose
hosted subject is configured rather than authenticated would turn a structural guarantee
into a deployment assumption.

Note that a host being multi-tenant across *projects* — several services, one operator —
is a different isolation problem from being multi-tenant across *users*. The two must not
be conflated when assessing whether an existing host is suitable.

## Protocol 0.2 requirements

Recorded here because each is a concession `draft.2` makes knowingly, and a concession
nobody wrote down becomes a permanent design.

**Type `applicability`.** It is `{"type": "object"}` today, which is why InVivo can carry
`evidence_requirements` inside it without a schema change. That buys schema-legality at
the cost of contract validation: nothing checks the shape of a requirement, so two
providers could express the same bar differently and both validate. `SimulationApplicability`
should become the typed schema for model applicability too, with evidence requirements as
named members.

**Define verification outcomes explicitly.** Attestation verification has at least four
distinguishable results, and collapsing them is unsafe:

| Outcome | Meaning | Admissible |
| --- | --- | --- |
| `verified` | an authenticated artefact establishes the attestation | yes |
| `unverified` | no attestation artefact was presented | no |
| `invalid` | an artefact was presented and failed authentication | no, and it is a finding |
| `unresolvable` | verification could not complete, e.g. a registry timeout | no, but it is transient |

A transient registry outage must not be indistinguishable from a bad signature. Both
refuse admission, but `invalid` is evidence of a problem with the evidence while
`unresolvable` is evidence of a problem with the check. A provider that reports them
identically cannot tell a forged report from an unreachable directory.

**Name the authentication axis correctly.** Whether an attestation is authenticated is
independent of who asserted it: a laboratory's cryptographic signature is necessarily
asserted by that laboratory and is authenticated. The distinction that matters is
authenticated evidence versus an unverified label, never self-assertion versus
third-party assertion.

## Tag policy

A tag is never moved, and artifact removal is never described as a protocol change.

- **`v0.1.0-draft.1`** (`d8d841e`) is immutable. It accidentally contains ignored Python bytecode
  under `__pycache__`, untracked in `e039385`; this does not affect any normative artifact.
- **`v0.1.0-draft.2`** (`5ae6398`) is the current baseline. Coordinate registry `0.2` grows coverage
  from 21 to 61 coordinates, additively: every `draft.1` document remains valid, and all five InVivo
  conformance fixtures validate unchanged. Schema, OpenAPI, and MCP profile are byte-identical to
  `draft.1`, so no normative protocol semantics changed.

Registry growth is deliberately *not* a semantic version bump of the protocol. `OPENBODY.md` sanctions
coordinate extension through registries, and a consumer that tolerates unknown coordinates — which the
spec requires — is unaffected by additions. What a new tag buys is a nameable pin for consumers who
need the new coordinates to be *registered*, since a cross-repository gate should fail on an
unregistered coordinate rather than warn.
