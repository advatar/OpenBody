# OpenBody

**An open protocol for executable human biological models.**

OpenBody is a model-neutral protocol for discovering, querying, composing, simulating, and exchanging uncertainty-aware computational representations of human biological state.

OpenBody is **not** a replacement for FHIR, DICOM, IEEE 11073, GA4GH, or other domain standards. Those standards remain authoritative for healthcare records, imaging, device communication, genomics, and related data. OpenBody sits above them and standardizes the missing computational layer: biological state, model provenance, cross-system coupling, trajectories, counterfactual simulation, outcomes, calibration, abstention, and the evidence needed to understand why a model should or should not be trusted.

The long-term objective is a patient-controlled, continuously calibrated digital twin that can be read by authorized AI systems, clinicians, hospitals, researchers, and specialist biological models without requiring any one institution or vendor to own the complete human model.

## Core loop

```text
Observation
  -> Evidence validation
  -> BodyState
  -> Trajectory / CounterfactualScenario
  -> Disagreement + uncertainty detection
  -> External verification where available
  -> Separately authorized action
  -> Verified execution
  -> ObservedOutcome
  -> Calibration
  -> BodyState
```

The additional assurance steps are deliberate. A simulation, recommendation, agent consensus, or successful model call is not proof that a real-world clinical action is safe or authorized.

## First principles

1. **The individual is the subject, not the institution.**
2. **Observation is not inference.** Observations, states, interpretations, predictions, counterfactuals, recommendations, and actions are distinct objects.
3. **No model without provenance.** Every derived state or simulation identifies the exact model/version/family that produced it.
4. **Uncertainty is data.** Epistemic and aleatoric uncertainty, coverage, applicability, and abstention are first-class.
5. **Model-neutral federation.** Different laboratories may provide competing cardiac, metabolic, genomic, cellular, or whole-body models behind common capability contracts.
6. **Multi-scale by construction.** Molecular, cellular, tissue, organ, subsystem, and whole-body models may coexist and compose.
7. **Existing standards remain authoritative for their domains.** OpenBody references them instead of inventing replacement payload formats.
8. **Simulation does not imply authority.** A model may simulate or propose; authorization to disclose data or cause a real-world intervention belongs to a separate authority layer.
9. **Fail closed.** Unsupported, stale, out-of-distribution, insufficiently calibrated, unauthorized, invalidly verified, or unresolvable requests produce explicit abstention or escalation rather than fabricated certainty.
10. **Objectives belong to the person.** The protocol does not define a universal "optimal human." Goals and acceptable trade-offs are external, authorized inputs.
11. **Consensus is not truth.** Agreement among agents or models may trigger routing or reduce uncertainty, but it is not by itself verification, authority, or permission to act.
12. **Oversight is not assurance unless it can be characterized.** A checker must declare what it checks, what authority it has, what independent standard it uses where applicable, and how independent it is from the system it checks.
13. **Prefer simpler external checks when they exist.** Deterministic constraints, authoritative standards, exact evidence/version checks, policy predicates, and formal invariants are generally stronger control primitives than asking another generative model to agree.
14. **Spend attention on disagreement.** Additional compute and human review should concentrate on contradiction, missing evidence, invalid/unresolvable verification, uncertainty, and consequential decisions rather than universal debate.

## Society of Organs + assurance plane

OpenBody's model federation is intentionally not a hierarchy in which the highest-level AI becomes the safety authority.

```text
specialist biological models
          |
          v
whole-body synthesis
          |
          v
candidate state / trajectory / counterfactual
          |
          +--> evidence validation
          +--> contradiction & uncertainty detection
          +--> external verification / deterministic constraints
          |
          v
separate authority boundary
          |
          v
real-world action
```

The model federation provides biological intelligence. The assurance and authority path determines what can safely become consequential action.

See [`OVERSIGHT.md`](OVERSIGHT.md) for the clinical multi-agent oversight profile and the protocol-0.2 design candidates derived from the 2026 literature on clinical AI oversight.

## Executable 0.1 artifacts

- [`OPENBODY.md`](OPENBODY.md) — normative protocol draft.
- [`schemas/openbody.schema.json`](schemas/openbody.schema.json) — JSON Schema 2020-12 definitions for the core state/model/simulation/outcome objects.
- [`schemas/clinical-assertion-reference.schema.json`](schemas/clinical-assertion-reference.schema.json) — fail-closed consumer projection contract for model-derived clinical references.
- [`registry/coordinates.json`](registry/coordinates.json) — initial machine-readable `ob://` biological coordinate registry.
- [`openapi/openbody.openapi.json`](openapi/openbody.openapi.json) — OpenAPI 3.1 HTTP profile.
- [`profiles/mcp/tools.json`](profiles/mcp/tools.json) — agent/MCP semantic capability profile.
- [`examples/post-meal-walk.scenario.json`](examples/post-meal-walk.scenario.json) — first end-to-end simulated scenario, aligned with the InVivo personal CGM/walking model.
- [`examples/insufficient-evidence.abstention.json`](examples/insufficient-evidence.abstention.json) — fail-closed response example.
- [`examples/clinical-assertion-references.v1.json`](examples/clinical-assertion-references.v1.json) — executable admission/rejection fixtures for clinical consumers.
- [`docs/CLINICAL_ASSERTION_REFERENCES.md`](docs/CLINICAL_ASSERTION_REFERENCES.md) — projection, subject-binding, uncertainty, applicability, and retraction semantics.
- [`tools/validate_openbody.py`](tools/validate_openbody.py) — schema + protocol-invariant conformance validator.
- [`OVERSIGHT.md`](OVERSIGHT.md) — clinical multi-agent oversight architecture and protocol-0.2 design record.

## Validate locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
PYTHONPATH=reference/python python tools/validate_openbody.py
```

CI runs the same conformance path on every pull request and push to `main`.

The validator currently enforces structural JSON Schema conformance plus semantic invariants that JSON Schema alone should not silently encode, including:

- a `simulated` scenario must contain a counterfactual trajectory and model receipt;
- a non-simulated scenario must not invent expected effects or claim a producing model receipt;
- an explicit `abstained` scenario must contain an `Abstention`;
- an `ObservedOutcome` cannot end before it starts;
- OpenBody coordinates referenced by fixtures are checked against the registry and unknown coordinates are reported.
- clinical assertion references verify schema/registry identity, content digest, subject binding, scope, producer/evidence lineage, applicability, uncertainty, abstention, and current validity using stable rejection codes.

## Status

Version: **OpenBody Protocol 0.1.0-draft.1**

Status: **Pre-standardization working draft. Not a clinical standard and not a medical device specification.**

The 0.1 wire contract remains intentionally stable on this branch. The new oversight taxonomy is recorded as an architecture/profile layer and protocol-0.2 candidate rather than silently changing the frozen 0.1 schema.