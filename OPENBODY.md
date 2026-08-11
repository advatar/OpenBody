# OpenBody Protocol 0.1.0-draft.1

**Status:** Pre-standardization Working Draft  
**Date:** 2026-08-10

## Abstract

OpenBody is a model-neutral protocol for discovering, querying, composing, simulating, and exchanging uncertainty-aware computational representations of human biological state. It standardizes the layer above health records and sensor data: inferred biological state, model provenance, multi-scale composition, trajectories, counterfactuals, outcomes, calibration, and abstention.

A generic biological model becomes a **Digital Twin** when bound to a specific subject and continuously calibrated with subject-specific evidence.

OpenBody does not replace FHIR, DICOM, IEEE 11073, GA4GH, or clinical judgment. It composes with them.

## 1. Motivation

Today's EHR is primarily event-centered: visits, observations, diagnoses, orders, medications, procedures, and workflows. The integrative model of what is happening inside the person still largely exists in the clinician or an AI system consuming fragments of the record.

OpenBody makes the executable model of the person a first-class interoperable object:

```text
records + sensors -> observations -> BodyState -> trajectories
                                         |
                              specialized body models
                       molecular / cell / organ / system
                                         |
                              counterfactual simulation
                                         |
                              separately authorized action
                                         |
                                observed outcome
                                         |
                                    calibration
                                         +----> BodyState
```

## 2. Normative language

Capitalized **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are normative within this working draft. This draft does not claim standards-body status.

## 3. Non-goals

OpenBody 0.1 does not replace FHIR, DICOM/DICOMweb, IEEE 11073, GA4GH, established biological ontologies, or authorization protocols. It does not define one canonical whole-body model, a universal optimal human state, or diagnosis/prescribing/procedures as primitive protocol powers.

## 4. Architectural invariants

### 4.1 Subject sovereignty
An endpoint MUST identify the represented subject and MUST permit subject-controlled deployment. It MUST NOT assume a hospital, payer, EHR vendor, or model provider permanently owns the complete twin.

### 4.2 Epistemic separation
Implementations MUST distinguish at least `observation`, `inference`, `clinical_interpretation`, `statistical_association`, `causal_estimate`, `mechanistic_simulation`, `prediction`, `counterfactual`, `hypothesis`, and `recommendation`. Changing epistemic class MUST create a new assertion with provenance.

### 4.3 Model neutrality
Models MAY be statistical, machine-learning, foundation, causal, mechanistic, ODE/PDE/stochastic, PK/PD, physiological, neural-operator, cellular, or hybrid. Exact family and version MUST be declared.

### 4.4 Federation
A body representation MAY compose independently developed models. Consumers SHOULD bind to capabilities, biological scope, scale, validation, and version rather than provider identity.

### 4.5 Fail closed
Insufficient evidence, authorization, applicability, calibration, or input coverage MUST produce an explicit `Abstention`, never a fabricated effect.

### 4.6 Simulation is not authority
A counterfactual or recommendation MUST NOT itself authorize disclosure, medication, device actuation, procedures, purchasing, or other consequential action.

### 4.7 Objectives belong to the person
OpenBody MUST NOT define a universal optimal biological state. Goals and trade-offs are external authorized inputs.

### 4.8 Subject and lineage integrity
Subject identity MUST bind state, simulation, outcome, and calibration lineage. A host MUST NOT rebind another subject's trajectory, evidence, expected effect, model receipt, outcome, or calibration by changing only a top-level subject identifier. Every successful simulation and every accepted outcome or calibration MUST preserve a verifiable subject and perturbation lineage.

### 4.9 Advertised enforcement
A host MUST NOT advertise an authorization mechanism that it does not enforce. Discovery metadata MUST distinguish enforced authorization schemes from unsupported or externally unavailable schemes. Possession of an `authority_ref` string MUST NOT itself be treated as proof of authority.

## 5. Seven protocol planes

1. **Observation Plane** — source-grounded measurements/events and references to authoritative external formats.
2. **State Plane** — inferred biological state, latent state, evidence, uncertainty, validity, and model versions.
3. **Model Plane** — capabilities, inputs/outputs, scope, scale, applicability, validation, provenance, execution, prohibited uses.
4. **Simulation Plane** — perturbations, baselines, counterfactual trajectories, expected effects, assumptions, uncertainty, abstention.
5. **Evidence & Epistemics Plane** — provenance, assertion class, calibration, applicability, validation, distribution shift.
6. **Authority Plane** — external authorization references controlling access, computation, contribution, and action.
7. **Federation Plane** — model discovery, selection, composition, substitution, dependencies, and coupling.

## 6. Core objects

```text
OpenBodySubject
BodyObservation
BodyState
BodySubsystemState
BodyCoupling
BodyModel
ModelReceipt
EvidenceReference
Uncertainty
BodyTrajectory
Perturbation
CounterfactualScenario
ExpectedEffect
ObservedOutcome
CalibrationEvent
Abstention
AuthorityReference
```

### BodyState

```yaml
BodyState:
  id: uuid
  subject: subject-ref
  generated_at: timestamp
  state_time: timestamp
  valid_until: optional
  subsystems: [BodySubsystemState]
  couplings: [BodyCoupling]
  evidence: [EvidenceReference]
  uncertainty: Uncertainty
  model_receipts: [ModelReceipt]
```

### BodySubsystemState

```yaml
BodySubsystemState:
  coordinate: ob://human/metabolic/glucose_regulation
  scale: Scale
  state_vector: {}
  latent_state: {}
  trend: stable | changing | indeterminate
  uncertainty: Uncertainty
  evidence: [EvidenceReference]
  model_receipt: ModelReceipt
```

Generic numerical direction MUST NOT be interpreted as improving/worsening unless a scoped validated model defines that semantics.

### BodyCoupling

```yaml
BodyCoupling:
  source: OpenBodyCoordinate
  target: OpenBodyCoordinate
  direction: directed | bidirectional
  mechanism_class: neural | circulatory | endocrine | immune | biochemical | mechanical | informational | other
  timescale: DurationRange
  strength: optional
  epistemic_class: mechanistic_simulation | statistical_association | causal_estimate | hypothesis
  uncertainty: Uncertainty
  model_receipt: ModelReceipt
```

### BodyModel

```yaml
BodyModel:
  id: globally-unique-model-id
  version: immutable-version
  family: statistical | machine_learning | foundation | causal | mechanistic | pkpd | physiological | cellular | hybrid
  provider: provider-ref
  scopes: [OpenBodyCoordinate]
  scales: [Scale]
  capabilities: [state_estimation, forecast, counterfactual, explanation, calibration]
  required_inputs: []
  outputs: []
  applicability: Applicability
  validation: ValidationClaim
  prohibited_uses: []
  execution: ExecutionDescriptor
  dependencies: [ModelDependency]
```

### ModelReceipt

Every derived state, trajectory, and simulated effect MUST identify the producing model with model ID, immutable version, family, execution ID/time, input/output digests, and validation reference where available.

Every model producing a successful simulation MUST be discoverable through the Model Plane with the exact model ID, version, and family carried by its receipt. This applies to receipts at scenario and trajectory level and to receipts nested in states, subsystems, and couplings. Its descriptor MUST declare the capability, biological scope, applicability boundary, validation information, execution mode, and prohibited uses relevant to that simulation. The declared applicability subject, scopes, and horizon MUST authorize the represented subject and every output scope and temporal boundary supported by that receipt placement; matching only the descriptor's top-level scope or horizon is insufficient.

Receipt placement determines required producer semantics. A receipt nested in counterfactual trajectory output MUST resolve to a model declaring `counterfactual` capability in addition to any state-estimation role it performs. Every producing receipt placement MUST have at least one biological scope derived from the output it supports. Before success, a host MUST prove that every producing descriptor contains all capabilities and biological scopes required by the receipt's exact placement; scope-less, empty, or incompatible declarations MUST fail closed.

### EvidenceReference

```yaml
EvidenceReference:
  scheme: fhir | dicom | dicomweb | ieee11073 | ga4gh | openbody | uri | other
  canonical_ref: uri-or-id
  content_digest: optional
  observed_at: optional
  source_provenance: Provenance
  authorization_ref: optional
```

### Uncertainty

```yaml
Uncertainty:
  epistemic: 0.0..1.0
  aleatoric: 0.0..1.0
  coverage: 0.0..1.0
  interval: optional
  calibration_ref: optional
  out_of_distribution: true | false | unknown
  reasons: []
```

Unknown uncertainty MUST NOT be represented as zero uncertainty.

### BodyTrajectory
A time-ordered state path with kind `observed | expected | reference | predicted | intervention`, horizon, assumptions, uncertainty, and model receipts.

### Perturbation
A proposed modeled change, not permission to perform it. Classes include behavior, nutrition, sleep, exercise, environment, medication, supplement, device, procedure, molecular, genetic, cellular, and research.

### CounterfactualScenario
Contains subject, baseline, perturbation, counterfactual trajectory, expected effects, assumptions, applicability, evidence, receipts, uncertainty, and disposition. Disposition includes `simulated`, `abstained`, `authorization_required`, and `clinician_review_required`.

### ObservedOutcome / CalibrationEvent
An outcome binds observations to the exact intervention instance. Calibration compares prediction and outcome. Calibration MUST NOT silently retrain or mutate a production model; learned updates require a new version and provenance.

An accepted `ObservedOutcome` MUST bind to the represented subject and to a known perturbation instance for that subject. Its normalized interval MUST begin no earlier than the exact perturbation start and end no later than the linked scenario counterfactual horizon boundary. An accepted `CalibrationEvent` MUST reference a known, compatible scenario/outcome pair whose subject and perturbation lineage agree, and both subjects MUST equal the host's canonical twin subject. Because stored objects are an untrusted protocol boundary, a host MUST revalidate the scenario, independently derive its horizon, validate the outcome, and re-prove their temporal and lineage compatibility when accepting calibration, even if both objects were validated when inserted. Its metric maps MUST be non-empty, use identical keys, and refer only to metrics present in both the prediction and observed outcome. A host MUST reject unbound, cross-subject, cross-twin, temporally unrelated, metrically incompatible, or conflicting outcome and calibration writes.

### Abstention
Abstention is a successful protocol response, not a transport error. Reasons include insufficient/stale evidence, unsupported scope/perturbation, out-of-distribution input, insufficient validation, authorization required, clinician review required, model unavailable, and invalid input.

### AuthorityReference
An opaque reference to external authorization such as OAuth/OIDC, capabilities, Mandamus, or future systems. OpenBody objects MUST NOT embed reusable credentials or secrets.

A host that advertises no enforced authorization scheme MUST fail closed when any authority reference is non-null, including both transport-level request authority and authority embedded in a perturbation. An opaque reference is never self-authenticating.

RFC 3339 timestamps represent temporal instants. Implementations MUST parse and compare normalized instants and MUST NOT infer chronology from lexicographic string ordering.

For every `BodyState`, a non-null `valid_until` MUST be no earlier than `state_time`. Every baseline state used for simulation MUST satisfy `state_time <= perturbation.starts_at` after RFC 3339 instant normalization and, when `valid_until` is non-null, `perturbation.starts_at <= valid_until`. A baseline outside that interval is stale and MUST NOT support successful simulation.

Cryptographic digests MUST use algorithm-specific hexadecimal lengths: SHA-256 requires exactly 64 hexadecimal digits and SHA-512 requires exactly 128 hexadecimal digits.

## 7. OpenBody Coordinates

Coordinates address **biological scope**, not storage location:

```text
ob://<species>/<path>[?<qualifiers>]
```

Examples:

```text
ob://human/cardiovascular/heart
ob://human/cardiovascular/heart/left_ventricle
ob://human/neural/autonomic/vagus
ob://human/endocrine/pancreas/beta_cell
ob://human/metabolic/glucose_regulation
ob://human/molecular/protein/PCSK9
ob://human/genome/GRCh38/chr1
```

Coordinates MUST be extensible through registries/profiles. External ontology identifiers MAY be aliases. Consumers MUST tolerate unknown coordinates and SHOULD discover definitions.

## 8. Multi-scale semantics

Models SHOULD declare organizational scale (`molecular`, `organelle`, `cellular`, `tissue`, `organ`, `subsystem`, `whole_body`) and temporal range. Cross-scale adapters SHOULD declare transformations, information loss, uncertainty propagation, and calibration. Outputs at one scale MUST NOT be assumed interchangeable with inputs at another.

## 9. Discovery

HTTPS deployments SHOULD expose `GET /.well-known/openbody` containing protocol versions, base URL, capabilities, and supported authorization schemes. Discovery MUST NOT contain credentials.

## 10. HTTP profile

```text
GET  /v1/capabilities
GET  /v1/state
GET  /v1/state/{coordinate}
GET  /v1/evidence/{id}
GET  /v1/models
GET  /v1/models/{id}
GET  /v1/trajectories/{id}
POST /v1/query
POST /v1/simulations
POST /v1/outcomes
POST /v1/calibrations
```

Transport profiles MAY map the same semantics to MCP, A2A, local IPC, or future transports.

## 11. Agent profile

```text
openbody.get_state
openbody.get_subsystem_state
openbody.explain_state
openbody.get_evidence
openbody.get_uncertainty
openbody.list_models
openbody.describe_model
openbody.simulate
openbody.compare_scenarios
openbody.record_outcome
openbody.compare_prediction_to_outcome
openbody.prepare_clinician_packet
```

The base profile intentionally does not define `diagnose`, `prescribe`, or `perform_procedure` as primitive powers.

## 12. Simulation contract

A request MUST identify subject/twin, state/reference, perturbation, horizon, a non-empty set of requested outputs/scopes, and authority when required. Success MUST bind to the exact requested state, declared model capability, represented subject, requested biological scopes, temporal horizon, and applicable evidence boundary. A client MUST compare the returned baseline to the complete requested `BodyState` using canonical semantic content, not merely subject identity; any changed state vector, subsystem, uncertainty, evidence, receipt, or additional baseline state invalidates the response. Success MUST include baseline and counterfactual trajectories, exact model receipts, assumptions, expected effects, uncertainty, evidence, and applicability. Successful output scopes MUST equal the explicitly requested scopes across expected effects and every nested counterfactual state, subsystem, coupling, and scoped evidence reference; omitted or empty `requested_scopes` is invalid. Contradictory broader output MUST fail closed rather than be silently filtered. `requested_scopes` and horizon MUST NOT be silently ignored.

The declared simulation horizon MUST equal the normalized elapsed time from perturbation start to the returned counterfactual boundary and MUST agree with the producing model applicability declaration. A hard-coded or transport-default horizon is not proof of temporal applicability.

A successful simulated scenario MUST recursively validate every `EvidenceReference` at scenario, trajectory, state, subsystem, and other normative evidence placements. Each reference MUST be digest-addressed, timestamped, and explicitly bound to the represented subject, applicable claimed scopes, producing model, and scenario claim. A digest MUST carry its algorithm's full length, and no reference may be observed after the scenario's own generation instant; evidence that postdates the claim it substantiates is not evidence. For nested evidence, every referenced model MUST be a producer responsible for that exact placement and MUST individually support every scope listed on that evidence object; applicability MUST NOT be inferred from the union of unrelated producer scopes. OpenBody 0.1 expresses disjoint per-model attribution as separate evidence references, each containing only the scopes supported by all of its `model_refs`. A valid model elsewhere in the scenario cannot substitute for local provenance. Subject identity MUST be carried in a normative evidence field and MUST NOT be inferred from arbitrary provenance content. Evidence scopes at every placement participate in scope closure and MUST NOT broaden requested, applicable, output, or model-supported scopes. A free-form evidence-boundary label or empty evidence array is not evidence. If those bindings cannot be proven, the provider MUST abstain.

A consumer receiving a successful simulation MUST validate it against the originating request, including subject, perturbation semantics, horizon, and complete output-scope closure. Internal schema validity alone MUST NOT cause a request-inconsistent response to be trusted.

A host MUST bind every successful simulation it serves to its own canonical twin: a stored scenario whose subject differs from the host's represented subject MUST NOT be returned as successful, however internally self-consistent that scenario and its descriptors are. Because stored scenarios are an untrusted protocol boundary, a host MUST re-substantiate producing-model discoverability, capability, biological scope, and applicability before returning a stored successful simulation on a read path, not only when the simulation is generated. A read that cannot re-prove those bindings MUST fail closed.

Injected or persisted store contents are an untrusted protocol boundary. Before a stored scenario can authorize model claims, simulation output, outcome windows, or calibration lineage, the host MUST semantically validate it and independently recompute its normalized temporal horizon. Unvalidated final timestamps MUST NOT establish an observation window.

A model MUST abstain when perturbation, dose, biological scope, temporal horizon, subject context, or evidence falls outside its declared boundary. The response MUST state whether its epistemic basis is statistical association, causal estimate, mechanistic simulation, hybrid inference, or another registered class.

## 13. Society of Organs federation

```text
WholeBodyCoordinator
  +-- CardiovascularModel
  +-- MetabolicModel
  +-- NeuralModel
  +-- EndocrineModel
  +-- ImmuneModel
  +-- RenalModel
  +-- HepaticModel
  +-- PulmonaryModel
  +-- GastrointestinalModel
  +-- MusculoskeletalModel
  +-- cross-system BodyCouplings
  +-- molecular / cellular / tissue submodels
```

This is a capability graph, not a mandatory anatomy taxonomy. Narrow pathway/receptor/cell/organ models MAY participate. Composition MUST preserve each contributing model's provenance, uncertainty, and epistemic class.

## 14. Existing-standard mappings

| Domain | Existing layer | OpenBody role |
|---|---|---|
| Clinical/EHR exchange | HL7 FHIR | evidence/reference, clinical context, workflows |
| Imaging | DICOM/DICOMweb | image/evidence references and model inputs |
| Personal devices | IEEE 11073 where applicable | observations and device provenance |
| Genomics | GA4GH standards | genomic evidence, knowledge references, federated analysis |
| Terminology | established ontologies | coordinate aliases and semantic identifiers |
| Identity/authorization | OAuth/OIDC/capabilities/delegation | external authority reference |

## 15. Security, privacy, and authority

Inferred state and counterfactual predictions may reveal information absent from any individual source record. Implementations MUST support least-privilege disclosure and SHOULD support biological-scope authorization, purpose limitation, audit, revocation/supersession, and local/on-device execution.

Installing or discovering a model MUST NOT grant it access to the twin. Access MUST be separately authorized.

## 16. Validation and promotion

`ValidationClaim` SHOULD declare study design, cohort, sample size, endpoints, calibration, subgroup performance, external validation, distribution limits, and intended/prohibited uses.

OpenBody MUST distinguish biological plausibility, retrospective association, emulated causal evidence, prospective N-of-1 evidence, prospective cohort evidence, interventional trial evidence, and external replication. Predictive accuracy alone MUST NOT promote an assertion to a stronger epistemic class.

## 17. Versioning

Protocol objects MUST include schema/version information. Model versions MUST be immutable identifiers. Breaking protocol changes require a new protocol version. Coordinate/profile registries evolve independently.

## 18. Minimal conformance

**Core Reader:** subject, state, subsystem state, evidence, uncertainty, model receipt, coordinate, abstention.

**Simulation Provider:** Core Reader plus model discovery, perturbation, baseline/counterfactual trajectories, expected effects, fail-closed abstention.

**Twin Host:** Simulation Provider plus subject-specific evidence binding, provenance retention, calibration/outcomes, and external authority enforcement.

## 19. Relationship to OpenMind and authority systems

```text
OpenMind  -> who the person is, remembers, values, prefers, intends
OpenBody  -> biological state, models, trajectories, simulations, outcomes
Authority -> what an AI or other actor may actually do
```

These layers MAY be deployed independently.

## 20. Open questions for 0.2

1. Coordinate registry governance and ontology mappings.
2. Canonical JSON Schema/CBOR and content-addressing rules.
3. Model capability negotiation and dependency resolution.
4. Cross-scale coupling and uncertainty propagation.
5. Privacy-preserving/federated simulation and confidential-compute receipts.
6. Model attestation, signatures, reproducibility, and supply-chain provenance.
7. Clinical-action profile and regulator-facing validation levels.
8. Streaming state updates for ECG/EEG/CGM and molecular sensors.
9. FHIR/DICOM/GA4GH implementation guides.
10. MCP/A2A agent and Mandamus authority profiles.

## 21. Design doctrine

> **The record is evidence. The twin is the model. Simulation is computation. Authority is separate. Outcomes recalibrate the model.**
