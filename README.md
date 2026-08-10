# OpenBody

**An open protocol for executable human biological models.**

OpenBody is a model-neutral protocol for discovering, querying, composing, simulating, and exchanging uncertainty-aware computational representations of human biological state.

OpenBody is **not** a replacement for FHIR, DICOM, IEEE 11073, GA4GH, or other domain standards. Those standards remain authoritative for healthcare records, imaging, device communication, genomics, and related data. OpenBody sits above them and standardizes the missing computational layer: biological state, model provenance, cross-system coupling, trajectories, counterfactual simulation, outcomes, calibration, and abstention.

The long-term objective is a patient-controlled, continuously calibrated digital twin that can be read by authorized AI systems, clinicians, hospitals, researchers, and specialist biological models without requiring any one institution or vendor to own the complete human model.

## Core loop

```text
Observation -> BodyState -> Trajectory -> Perturbation
                                      -> CounterfactualScenario
                                      -> Intervention / real-world action
                                      -> ObservedOutcome
                                      -> Calibration
                                      -> BodyState
```

## First principles

1. **The individual is the subject, not the institution.**
2. **Observation is not inference.** Observations, states, interpretations, predictions, counterfactuals, recommendations, and actions are distinct objects.
3. **No model without provenance.** Every derived state or simulation identifies the exact model/version/family that produced it.
4. **Uncertainty is data.** Epistemic and aleatoric uncertainty, coverage, applicability, and abstention are first-class.
5. **Model-neutral federation.** Different laboratories may provide competing cardiac, metabolic, genomic, cellular, or whole-body models behind common capability contracts.
6. **Multi-scale by construction.** Molecular, cellular, tissue, organ, subsystem, and whole-body models may coexist and compose.
7. **Existing standards remain authoritative for their domains.** OpenBody references them instead of inventing replacement payload formats.
8. **Simulation does not imply authority.** A model may simulate or propose; authorization to disclose data or cause a real-world intervention belongs to a separate authority layer.
9. **Fail closed.** Unsupported, stale, out-of-distribution, insufficiently calibrated, or unauthorized requests produce explicit abstention rather than fabricated results.
10. **Objectives belong to the person.** The protocol does not define a universal "optimal human." Goals and acceptable trade-offs are external, authorized inputs.

## Executable 0.1 artifacts

- [`OPENBODY.md`](OPENBODY.md) — normative protocol draft.
- [`schemas/openbody.schema.json`](schemas/openbody.schema.json) — JSON Schema 2020-12 definitions for the core state/model/simulation/outcome objects.
- [`registry/coordinates.json`](registry/coordinates.json) — initial machine-readable `ob://` biological coordinate registry.
- [`openapi/openbody.openapi.json`](openapi/openbody.openapi.json) — OpenAPI 3.1 HTTP profile.
- [`profiles/mcp/tools.json`](profiles/mcp/tools.json) — agent/MCP semantic capability profile.
- [`examples/post-meal-walk.scenario.json`](examples/post-meal-walk.scenario.json) — first end-to-end simulated scenario, aligned with the InVivo personal CGM/walking model.
- [`examples/insufficient-evidence.abstention.json`](examples/insufficient-evidence.abstention.json) — fail-closed response example.
- [`tools/validate_openbody.py`](tools/validate_openbody.py) — schema + protocol-invariant conformance validator.

## Validate locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
python tools/validate_openbody.py
```

CI runs the same conformance path on every pull request and push to `main`.

The validator currently enforces structural JSON Schema conformance plus semantic invariants that JSON Schema alone should not silently encode, including:

- a `simulated` scenario must contain a counterfactual trajectory and model receipt;
- a non-simulated scenario must not invent expected effects or claim a producing model receipt;
- an explicit `abstained` scenario must contain an `Abstention`;
- an `ObservedOutcome` cannot end before it starts;
- OpenBody coordinates referenced by fixtures are checked against the registry and unknown coordinates are reported.

## Status

Version: **OpenBody Protocol 0.1.0-draft.1**

Status: **Pre-standardization working draft. Not a clinical standard and not a medical device specification.**
