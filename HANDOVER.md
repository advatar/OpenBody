# OpenBody handover — multi-agent clinical oversight hardening

## Current checkpoint

- Repository: `advatar/OpenBody`
- Branch: `research-mas-oversight-hardening`
- Base: `main`
- Scope: incorporate the 2026 clinical multi-agent oversight literature into the OpenBody vision and architecture without silently changing the frozen 0.1 wire contract.
- Research input: *Oversight mechanisms for multi-agent AI in clinical decision-making: a narrative review of current approaches and gaps* (2026), narrative review of 21 peer-reviewed clinical MAS systems.

## Why this change exists

The research review found that clinical multi-agent oversight is often described more strongly than it is implemented:

- four recurring oversight functions: verification, validation, consensus/arbitration, and observability;
- oversight usually reports rather than prevents;
- only two reviewed systems could block an unsafe output from reaching a user;
- consensus proves agreement, not correctness;
- same-model agents can share correlated failure modes;
- additional agents can increase cost and complexity without increasing safety;
- prospective live-clinical evaluation of oversight remains absent in the reviewed evidence base;
- the literature rarely isolates the checking component through ablation or measures clinically significant harm separately from aggregate accuracy.

OpenBody's Society of Organs therefore needs an explicit assurance architecture. The federation of biological models may generate, challenge, and synthesize claims, but it must not become its own clinical authority.

## Work completed on this branch

### 1. `OVERSIGHT.md`

New architecture/profile document defining:

- explicit separation of production, validation, verification, arbitration, and observability;
- `OversightFunction` design taxonomy;
- `OversightAuthority` design taxonomy;
- first-class checker independence and proposed `IndependenceClass`;
- preference for deterministic/external checks over extra generative intelligence when an external predicate exists;
- rule that consensus is not a completion or authority criterion;
- conflict-triggered escalation rather than universal debate;
- four verification outcomes: `verified`, `unverified`, `invalid`, `unresolvable`;
- harm-weighted evaluation requirements;
- checker ablation / corrupted-output testing requirements;
- Society of Organs + independent assurance plane;
- revised observe-to-learn loop with explicit validation, verification, authorization, and execution verification;
- relationship to ProvidEHR clinical authority;
- protocol-0.2 candidates: `OversightFunction`, `OversightAuthority`, `IndependenceClass`, `OversightReceipt`, `VerificationOutcome`, `DisagreementSet`, and `EscalationRequirement`.

### 2. `MODEL.md`

The manifesto now makes the safety architecture explicit:

- Society of Organs is a reasoning federation, not a clinical authority;
- model diversity and checker independence are first-class;
- observation/evidence is separated from model-derived state;
- counterfactual predictions cannot authorize themselves;
- OpenBody queries can expose disagreement, verification basis, checker independence, and checker authority;
- a new section explains why more agents do not equal more safety;
- selective escalation is preferred over universal debate;
- human involvement is reserved for consent, unresolved uncertainty, conflicting evidence, judgment, and authority rather than routine verification;
- the mature learning loop is now:

```text
Observe
  -> validate evidence
  -> model
  -> detect disagreement
  -> predict
  -> verify constraints
  -> escalate where needed
  -> authorize
  -> intervene
  -> verify execution
  -> measure
  -> recalibrate
  -> learn
```

### 3. `README.md`

The public project principles now include:

- consensus is not truth;
- oversight is not assurance unless its function, authority, standard, and independence are explicit;
- simpler independent checks should be preferred when available;
- attention and compute should concentrate on disagreement and uncertainty;
- the model federation and assurance/authority path are separate structures;
- link to `OVERSIGHT.md`.

## Deliberate non-change: OpenBody 0.1 wire contract

This branch does **not** silently mutate `schemas/openbody.schema.json`, OpenAPI, MCP tools, or the frozen 0.1 protocol object model.

That is deliberate.

The new oversight taxonomy changes contract semantics and deserves a protocol-0.2 design/qualification step. `OVERSIGHT.md` records the candidate types and invariants first so schema/API work can be done explicitly and cross-repository consumers can adapt intentionally.

## Required next OpenBody work

1. Review and merge this architecture/manifesto PR.
2. Open a protocol-0.2 implementation issue for typed oversight receipts and disagreement/escalation objects.
3. Define exact schema semantics for checker independence rather than pretending there is a universal numeric safety ordering.
4. Add conformance fixtures for:
   - same-model consensus that must not be represented as independent verification;
   - `invalid` vs `unresolvable` verification;
   - contradiction-triggered escalation;
   - externally verified claim;
   - observability-only checker that cannot be mistaken for blocking authority.
5. Extend the reference host/client and conformance validator only after those semantics are reviewed.

## Cross-repository requirements for ProvidEHR

No implementation changes should be made in ProvidEHR from this OpenBody branch. Another agent is actively working there.

Downstream issues should cover:

1. **Oversight provenance / independence registry** — distinguish producer from checker, base model family/provider, external standard, oversight function, and actual enforcement authority.
2. **Harm-weighted oversight evaluation** — ablation, deliberate corruption, error overlap, severe-harm recall, false blocks, latency/compute, and clinician-effect measurements.
3. **Clinical action admission** — make explicit that OpenBody consensus/recommendation/observability can never satisfy ProvidEHR authoritative completion by themselves.
4. **Selective escalation integration** — use disagreement/invalid/unresolvable verification as first-class reasons for Clinical Work Graph attention rather than universal multi-agent debate.

## Safety invariants to preserve

- A model or agent may propose; it does not grant clinical authority.
- Consensus among agents is not an external verification standard.
- Observability is not enforcement.
- A same-model judge is not independent simply because it has a different role prompt.
- Missing or unresolvable verification fails closed where verification is required.
- `invalid` and `unresolvable` remain distinguishable.
- External deterministic/formal checks should not be replaced with an LLM judge for convenience.
- Unresolved contradiction, uncertainty, or missing evidence must remain visible.
- Real-world action requires an external governed authority layer.

## Validation note

Changes on this branch are documentation/architecture only. No frozen 0.1 executable artifact has been modified. The existing OpenBody conformance validator therefore remains the qualification path for the executable baseline; protocol-0.2 implementation will require new fixtures/tests before any schema or API changes are accepted.
