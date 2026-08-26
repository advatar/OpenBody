# PersonalAdaptiveState research candidate

Status: protocol-0.2 research candidate. Not part of the frozen OpenBody 0.1 wire contract.

Tracking issue: #10. EHM research dependency: `advatar/Metabolog#1092`.

## Motivation

`BodyState` represents current modeled biological state. It is not the right object for a compact latent representation of how a particular person's physiology responds over time.

If the EHM personalization benchmark demonstrates utility, OpenBody should represent that distinction explicitly:

```text
Observation / Evidence
        -> BodyState
        + PersonalAdaptiveState
        + producing model
        -> Trajectory / Counterfactual
        -> ObservedOutcome
        -> Calibration
        -> explicit adaptive-state update
```

The protocol should standardize the semantics and provenance of personal adaptive state without requiring a particular learning algorithm.

## Candidate semantics

A future `PersonalAdaptiveState` object should bind at minimum:

- exact subject identity;
- producing/updating model identifier, version and family;
- algorithm family and update-policy version;
- supported OpenBody coordinates and applicability domain;
- evidence/time-range lineage used to create or update the state;
- creation and last-update timestamps;
- state dimensionality/size metadata;
- uncertainty/calibration metadata relevant to state-conditioned predictions;
- prior-state digest and resulting-state digest;
- storage/privacy/exportability policy;
- explicit lifecycle operation (`create`, `update`, `reset`, `fork`, `merge`) where applicable.

Opaque state payloads may remain implementation-specific or device-local. A digest/provenance envelope can be portable even when the learned state itself is not.

## Invariants

1. Adaptive state is model-derived, not an observation.
2. Adaptive state cannot assert that a laboratory or sensor measurement occurred.
3. Subject binding is strict; another subject's state cannot condition inference.
4. State applicability is bounded by model/version, coordinate scope and evidence lineage.
5. Stale, unsupported or unresolvable state can force abstention.
6. State transitions are explicit and hash-linked when persistence is claimed.
7. Reset, fork and merge are never implicit.
8. Adaptive state grants no disclosure, clinical or intervention authority.
9. Model consensus is not validation of adaptive-state correctness.
10. Prospective calibration/performance evidence remains separate from the state object itself.

## Why this remains research-only

A compact state is not automatically useful, stable, interpretable or privacy preserving. Metabolog #1092 must first show prospective held-out-person benefit, and subsequent work must test harmful drift, inversion/membership leakage and cross-subject isolation.

Only after those semantics are reviewed should #11 add conformance fixtures and issue #8 integrate the object with the broader protocol-0.2 oversight model.
