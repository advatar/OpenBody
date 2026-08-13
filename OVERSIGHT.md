# OpenBody Clinical AI Oversight Profile

Status: architecture and protocol-0.2 design record  
Date: 2026-08-13

## Why this exists

OpenBody is designed for a federation of biological models: independently developed models may estimate state, forecast trajectories, simulate perturbations, challenge one another, and contribute to a whole-human representation.

That creates a tempting but unsafe shortcut: treating additional agents, debate, consensus, or an LLM judge as a safety mechanism by themselves.

A 2026 narrative review of 21 peer-reviewed multi-agent clinical AI systems found four recurring oversight functions — verification, validation, consensus/arbitration, and observability — but found that oversight usually produced information rather than control. Only two reviewed systems could prevent a faulty output from reaching the user; none prospectively evaluated its oversight mechanism in live clinical use; and none placed a clinician in the loop while a decision was being formed. The review also found that additional agents do not reliably improve safety, that shared-model errors can be correlated, and that consensus establishes agreement rather than correctness.

OpenBody therefore adopts a stronger rule:

> **Multi-agent intelligence may generate, challenge, or prioritize biological claims. It MUST NOT be treated as the authority that makes those claims safe for clinical action.**

The Society of Organs is a reasoning federation. Safety comes from evidence, explicit standards, model independence, bounded authority, deterministic constraints where possible, fail-closed state, and targeted human judgment.

## 1. Core separation

OpenBody distinguishes five functions that must not be collapsed:

1. **Production** — a model or agent produces a state estimate, prediction, explanation, recommendation, or counterfactual.
2. **Validation** — the system checks whether the inputs, evidence, applicability, calibration, and criteria needed to make the claim are sufficient.
3. **Verification** — the system checks a finished claim against an external standard that exists independently of the producing agent where such a standard exists.
4. **Arbitration** — the system identifies and resolves or escalates disagreement among independently produced claims.
5. **Observability** — the system scores, annotates, monitors, or audits an output without changing whether it is admitted or acted upon.

Observability is useful, but it is not enforcement. Consensus is useful, but it is not truth. Verification can be strong, but only to the extent that the external standard is applicable and current. Validation can prove that a decision rests on admissible evidence without proving that the resulting conclusion is correct.

## 2. Oversight function taxonomy

Protocol 0.2 SHOULD represent oversight function explicitly rather than relying on labels such as `safety_agent`, `judge`, or `verifier`.

```text
OversightFunction
  input_validation
  output_verification
  consensus_or_arbitration
  observability
  longitudinal_monitoring
```

The function says **what is checked**. It does not imply authority.

## 3. Oversight authority taxonomy

The authority carried by an oversight mechanism MUST be represented independently from the function it performs.

```text
OversightAuthority
  observe
  recommend
  block
  require_human
  execute_governed_policy
```

Examples:

- an LLM judge that reports a score is `observability + observe`;
- a contradiction detector that routes an uncertain scenario to a clinician is `input_validation + require_human`;
- a deterministic contraindication check that prevents a simulation from being represented as clinically actionable is `output_verification + block`;
- a reviewed backend policy that safely handles a bounded routine case is `output_verification + execute_governed_policy`.

A name such as `SafetyAgent` MUST NOT imply any authority not explicitly declared and enforced.

## 4. Independence is evidence

A checker can share the same blind spots as the system it checks. OpenBody therefore treats checker independence as a first-class property.

Protocol 0.2 SHOULD define an `OversightReceipt` or equivalent containing at least:

```text
producer
  model_id
  model_version
  model_family
  provider
  execution_id

checker
  mechanism_id
  mechanism_version
  model_id / ruleset_id / verifier_id
  provider

independence_class
verification_standard
oversight_function
oversight_authority
result
input_evidence_refs
output_claim_refs
executed_at
```

Suggested independence classes, from generally stronger to weaker assurance:

```text
formal_or_deterministic_constraint
external_authoritative_standard
independent_non_llm_model
independent_model_family
same_family_independent_model
same_model_different_execution
same_model_different_prompt_or_role
self_reflection
```

This ordering is not a universal safety ranking; applicability and validation still matter. It exists to prevent a same-model debate from being described as independent verification.

## 5. External standards before extra intelligence

Where a machine-checkable criterion exists, OpenBody SHOULD prefer it over another generative model.

Examples include:

- schema and type constraints;
- subject and lineage integrity;
- exact evidence-version binding;
- temporal consistency;
- terminology validity;
- applicability boundaries;
- dose or device limits supplied by an authoritative source;
- contraindication rules supplied by an authoritative source;
- consent and authorization predicates;
- policy-version validity;
- provenance completeness;
- replay/idempotency constraints;
- formally verified invariants.

The safest supervisor for a generative model is frequently not another generative model.

## 6. Consensus is not a completion criterion

OpenBody MUST NOT treat the number of agreeing agents, a majority vote, or a confidence-weighted synthesis as proof that a clinical claim is correct.

Consensus MAY:

- raise or lower epistemic uncertainty;
- trigger deeper verification;
- select which hypothesis to investigate next;
- trigger conflict-specific routing;
- inform a human reviewer.

Consensus MUST NOT by itself:

- authorize a real-world intervention;
- suppress a contradictory claim;
- convert a recommendation into a verified clinical fact;
- convert an uncertain simulation into an authoritative conclusion;
- satisfy a required external verification standard.

A whole-body coordinator is therefore a synthesizer, not an authority root.

## 7. Conflict-triggered escalation

OpenBody SHOULD favor selective oversight over universal debate.

A host or federation SHOULD spend additional compute and human attention where one or more of the following is present:

- independent models disagree materially;
- evidence is contradictory;
- a required input is missing or stale;
- the subject is outside model applicability;
- uncertainty exceeds a declared bound;
- an external standard cannot be resolved;
- a policy or model version has expired or changed;
- a proposed perturbation has consequential clinical implications;
- a predicted effect depends on a disputed coupling or causal claim.

When verified evidence agrees and the applicable policy explicitly permits compression, routine agreement MAY be hidden from primary attention. Unresolved disagreement, uncertainty, missing evidence, invalid verification, or unresolvable verification MUST remain explicit.

## 8. Verification outcomes

`ARCHITECTURE.md` already records that attestation verification must distinguish four outcomes. The same distinction SHOULD apply to oversight checks generally:

```text
verified       authenticated/checkable evidence establishes the required predicate
unverified     the required evidence or check was not provided
invalid        evidence/check was provided and failed
unresolvable   the check could not complete, e.g. dependency unavailable
```

`invalid` and `unresolvable` both fail closed, but they are not equivalent. The first is evidence that the supplied basis failed; the second is evidence that the system could not determine the answer.

## 9. Harm-weighted evaluation

OpenBody implementations MUST NOT use aggregate accuracy as the only evidence for a safety-critical oversight mechanism.

Oversight evaluation SHOULD report at least:

- severe-harm recall / missed-harm rate;
- false-block rate;
- unresolved contradiction rate;
- unsupported-claim rate;
- error overlap between producer and checker;
- latency and compute cost;
- performance with the checker present;
- performance with the checker removed;
- deliberately corrupted-output detection where appropriate;
- out-of-distribution behavior;
- subgroup/equity behavior where clinically relevant.

For clinical deployments, prospective evaluation SHOULD additionally measure:

- clinician correction rate;
- automation-bias effects;
- decision changes caused by oversight;
- escalation timing;
- workload removed or added;
- clinically significant near misses and harms.

## 10. Ablation is required evidence

A multi-agent system that performs better than a single model has not demonstrated that its oversight mechanism caused the improvement.

For any oversight mechanism used to justify a safety claim, evaluation SHOULD isolate the checker through ablation or an equivalent causal design.

At minimum, evaluation artifacts SHOULD make it possible to answer:

1. What happens with the checker enabled?
2. What happens with the checker removed?
3. What happens when the worker is deliberately wrong or corrupted?
4. What errors are shared by worker and checker?
5. What happens when the checker disagrees?
6. What does the mechanism cost in time and compute?

## 11. Society of Organs + independent assurance plane

The OpenBody model federation SHOULD be understood as two orthogonal structures.

```text
                         Whole-body coordinator
                                  |
               +------------------+------------------+
               |                  |                  |
          cardiovascular       metabolic           renal
              model              model              model
               |                  |                  |
               +-------- candidate claims ----------+
                                  |
                        state integration layer
                                  |
               +------------------+------------------+
               |                  |                  |
        evidence validation   contradiction      uncertainty
                               detection          modeling
               |                  |                  |
               +------------------+------------------+
                                  |
                         assurance plane
                                  |
                 standards / policies / proofs
                                  |
                         authority boundary
                                  |
                        real-world action
```

The horizontal federation provides biological intelligence. The vertical assurance path determines what can safely cross into consequential action.

No organ model, coordinator, debate panel, or LLM judge becomes the clinical authority simply because it sits above other models.

## 12. Revised learning loop

The original manifesto loop is strengthened as follows:

```text
Observe
  -> Validate evidence
  -> Estimate state
  -> Detect disagreement / uncertainty
  -> Predict / simulate
  -> Verify applicable external constraints
  -> Escalate where necessary
  -> Authorize
  -> Intervene
  -> Verify execution
  -> Measure
  -> Compare predicted vs observed
  -> Recalibrate
  -> Learn
```

The distinction between `Authorize` and `Intervene` is deliberate. A simulation or recommendation cannot authorize itself.

The distinction between `Intervene` and `Verify execution` is equally deliberate. An intended action and an action that actually occurred are different facts.

## 13. Relationship to ProvidEHR

OpenBody owns computational biological state and simulation. It does not become the clinical action authority.

For deployments with ProvidEHR:

- OpenBody exposes evidence-bound state, trajectories, model receipts, disagreement, uncertainty, abstention, and oversight receipts;
- ProvidEHR owns clinical evidence/attestation, workflow authority, policy-controlled actions, authoritative write-back, action receipts, and reopening;
- a ProvidEHR action MAY consume an OpenBody claim, but MUST independently enforce the authority and policy required for that action;
- an OpenBody consensus or recommendation MUST NOT be accepted as a ProvidEHR completion receipt;
- a corrected/retracted OpenBody claim MUST be capable of invalidating downstream derived context and reopening affected work where the clinical runtime has bound an action to that premise.

This separation allows OpenBody to remain model-neutral and portable while allowing clinical runtimes to apply jurisdiction-, institution-, profession-, and patient-specific authority.

## 14. Protocol 0.2 candidates

The following are candidates for typed 0.2 objects rather than silent extensions of the frozen 0.1 schema:

```text
OversightFunction
OversightAuthority
IndependenceClass
OversightReceipt
VerificationOutcome
DisagreementSet
EscalationRequirement
```

A future schema revision SHOULD allow state, trajectory, expected-effect, recommendation, and counterfactual claims to reference applicable oversight receipts without making oversight mandatory for purely non-clinical/research computation.

The protocol MUST preserve the distinction between:

- the producer's provenance;
- the checker/verifier's provenance;
- the external standard or policy checked;
- the authority empowered to act on the result.

## 15. Research posture

OpenBody does not claim that multi-agent oversight has been shown to reduce patient harm. Current peer-reviewed evidence is largely retrospective, simulated, or benchmark-based.

A production deployment SHOULD advance authority progressively:

```text
retrospective evaluation
  -> silent/shadow mode
  -> prospective advisory mode
  -> targeted escalation/blocking
  -> narrowly governed autonomous handling
```

Each increase in authority should require evidence appropriate to the risk and intended use.

The purpose of this profile is therefore not to claim solved clinical AI safety. It is to prevent the protocol from confusing more agents, more debate, or more observability with actual assurance.