# External scientific resources and executable models

This research policy complements OpenBody's epistemic separation and fail-closed
abstention rules (OPENBODY.md §4). It does not add a runtime admission authority
or change the frozen protocol. SCKAN is a knowledge resource, not a physiological
model. ASCENT is an executable-model candidate, not an admitted model.

## Reuse the model-family boundary

[PR #19](https://github.com/advatar/OpenBody/pull/19) is **unmerged** at this audit.
Its [model-family profile](https://github.com/advatar/OpenBody/blob/bb3c689802e9284a29c200e42b8a01b96fa0680f/docs/MODEL_FAMILY_CONTRACTS.md)
and schema/runtime already separate artifact registration, evidence classes,
context of use and current qualification. PR #23 does not copy that implementation
or claim it is installed on main. Integration must use that profile when available.

| Research evidence or requirement | Existing model-family boundary in PR #19 |
|---|---|
| Source/version, artifact integrity, input/output identity | Exact registered artifact; receipt input/output digests; evidence references |
| Runtime, solver, dataset and upstream status | Contract dependencies and reviewed evidence commitments; digest alone is not authentication |
| Species, anatomy, population/sample, modality, device, parameters | Model identity, population/question/context of use, bounded parameters and dependencies; scientific review must bind the complete context |
| Reproduction status and scientific evidence class | Research qualification evidence, never an automatic qualification lease |
| Uncertainty and limitations | Uncertainty policy, behavioral envelope, abstention and prohibited uses |
| Model and person/context qualification | Current authority lease binds exact contract/artifact, purpose, population, tenant/subject, question and horizon |
| Staleness/revocation | Fresh authority/dependency/source checks before and after execution and on retained reads |

A research receipt cannot mint a `QualificationLease`. A resource manifest is
not a model-family contract. No SPARC code registers a model, publishes a clinical
reference, mutates a Twin or grants intervention authority. Existing clinical
reference admission remains unchanged. Cross-system durable revocation remains
an explicit limitation of the existing architecture, not solved here.

## Evidence stages are independent claims

These are policy vocabulary, **not** a second runtime state machine. Each claim
needs its own scope, evidence and uncertainty; they are not one promotion score.

| Claim | Required evidence; no implied promotion |
|---|---|
| DISCOVERED | Citable source exists |
| IDENTIFIED | Exact deposit/version/study identity established |
| ARTIFACT_AUTHENTICATED | Independent upstream provenance plus matching bytes/digest/size within stated scope |
| EXECUTABLE | Demonstrated execution with bound inputs and environment |
| REPRODUCTION_CONTRACTED | Valid reference/comparison specification committed before candidate invocation |
| REPRODUCED | Candidate compared against that specification, or explicitly scoped historical repeated-query evidence |
| MODEL_QUALIFIED | Separate current scientific/governance decision for an exact model and purpose |
| CONTEXT_QUALIFIED | Separate current applicability/authority for the person/population/context |

Unknown is UNKNOWN; absence is not a negative scientific finding. Failed integrity
checks stay FAILED even alongside successful identity checks. Operational outcomes
PASS, FAIL, BLOCKED and INCOMPARABLE are distinct. BLOCKED describes unavailable
prerequisites; INCOMPARABLE describes nonmatching identities/representations.
Neither is a numerical failure or success. Claims may become stale or revoked;
historical receipts retain their dates and do not assert current authority.

A DOI is identity evidence, not execution evidence. A matching hash is integrity
evidence, not scientific validity. Publication, a trusted repository, a number
from a simulation, or a paper's word “validated” cannot establish admission.
Execution is not reproduction; reproduction is not biological validation;
biological validation is not clinical validity; clinical validity does not imply
transferability to a different person or context.

Anatomical connectivity, functional connectivity, electrical recruitment,
physiological target engagement and clinical benefit remain separate evidence
classes. Implanted cervical, implanted abdominal, branch-specific, transcutaneous
cervical and transcutaneous auricular VNS are distinct modalities. Species,
population, anatomy, electrode geometry and stimulation parameters stay bound;
unknown sex/sample information stays unknown. No implanted-to-auricular transfer
or Cymba qualification follows from these examples.

## Pre-execution reproduction specification

The generic contract must bind source identity/version/status, artifact and input
digests, model version, runtime/container and solver identity, species,
population/sample, anatomy, modality, device/electrode, parameters, metric/unit,
authenticated reference output/digest, comparison method, predeclared tolerance
and its primary justification, provenance references and expected failure states.
Unknown required execution information blocks a contract. Scientifically irrelevant
fields need an explicit `not applicable: <reason>`, never an invented default.
The exact upstream expected value belongs in the reference artifact.

`experiments/sparc/contract.py` is a small research invocation gate, not a model
qualification service. It supports **exact byte equality only**, with zero
tolerance. Numerical tolerances and structured canonicalization require a future
reviewed extension and primary evidence; the older `benchmark.compare` and
`reproduction_outcome` functions are diagnostic comparison helpers, not evidence
of predeclaration or authority to execute/promote a model.

The gate loads a full commit ID reachable from HEAD, verifies that the regular
contract file is unchanged, validates its bindings, and checks input/reference
bytes and the trusted adapter's actual environment identity **before** invoking
its callback. Missing/invalid/uncommitted contracts return BLOCKED without calling
the candidate. Changed inputs/environment return INCOMPARABLE without execution.
Execution errors are FAIL; missing output is BLOCKED. A receipt binds the contract
commit/hash and output hash. Synthetic temporary-Git tests establish call ordering
and tampering rejection; no ASCENT contract or candidate is supplied.

The loader/adapter must independently authenticate source artifacts and attest the
actual runtime and executable bytes. Passing a claimed environment dictionary is
not authentication. This gate is not a sandbox and cannot prove that an operator
never ran the model elsewhere. Git ordering makes invocation through this gate
auditable; timestamps supplied by a caller are not accepted as ordering proof.
A complete execution receipt additionally needs actual command, runtime versions,
start/end times, warnings and logs from the adapter. Do not label a bare synthetic
gate test as a real model reproduction.

## Frozen examples

[Compact examples](../experiments/sparc/examples/admission.json) point to original
receipts rather than duplicate data. Tests tie their claims to those receipts.

SCKAN `sckan-2026-06-23` remains a prerelease: artifact authentication PASS,
bounded query execution PASS, repeated canonical results PASS. This is historical
bounded repeated-query reproduction, **not** a retrospectively contracted ASCENT-
style numerical comparison. The five frozen queries include an empty UNKNOWN
result. Evidence class is anatomical/connectivity knowledge; no biological,
clinical, model-family or Cymba/auricular qualification is established.

ASCENT Guided Mode dataset 364 v1 / ASCENT 1.2.1 has bounded identity/artifact
evidence. Root manifest size verification remains FAILED (upstream metadata
defect), and Tutorial dataset 365 is INCOMPARABLE, not an equivalent study.
Execution identity is incomplete; reference output and reproduction contract are
ABSENT; reproduction is BLOCKED, with no candidate executed. No validity or
qualification follows. The completed investigation is sufficient for this
research-infrastructure PR; obtaining external resources is [issue #25](https://github.com/advatar/OpenBody/issues/25).
Future sequence: authoritative bundle → commit contract → candidate execution →
comparison → separate model and context qualification decisions.
