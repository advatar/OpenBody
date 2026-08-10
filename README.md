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

## Specification

See [`OPENBODY.md`](OPENBODY.md).

Version: **OpenBody Protocol 0.1.0-draft.1**

Status: **Pre-standardization working draft. Not a clinical standard and not a medical device specification.**
