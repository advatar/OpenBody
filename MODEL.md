---
title: "From Electronic Health Records to Executable Human Models"
subtitle: "A manifesto for a continuously observed, computationally modeled human body"
lang: en
---

![Clinical records and measurements converge into an executable whole-human model, which branches into predicted trajectories and possible interventions.](assets/model/executable-human-hero.png)

<div class="page-break"></div>

For decades, healthcare has been built around the medical record.

The electronic health record is essentially a history of what happened: consultations, laboratory results, images, diagnoses, prescriptions, and procedures. It organizes information so that clinicians can understand a patient and decide what to do next.

But the most important model of the patient is not actually in the EHR.

**It exists in the clinician.**

A physician takes fragments of information, combines them with medical knowledge and experience, constructs a mental model of what is happening inside the body, considers possible explanations and interventions, and makes a decision. The EHR records the evidence and conclusions and coordinates the resulting workflow.

I believe this architecture is about to change fundamentally.

## The health record will no longer be the center

The central computational object of future healthcare will not be the electronic health record.

> **It will be an executable model of the human being.**

Human biology can increasingly be represented as a hierarchy of interacting systems: genome, epigenome, proteins, metabolites, cells, tissues, organs, physiological systems, and, ultimately, the whole organism.

These systems are constantly communicating through biochemical, neural, endocrine, immune, circulatory, and physical processes. Health and disease emerge from their interactions.

Trying to represent all of this with a single monolithic AI model is unlikely to be the right architecture.

Instead, imagine the human body represented by a society of specialized biological models.

A cardiovascular model understands electrophysiology, hemodynamics, vascular biology, and cardiac mechanics. A metabolic model understands glucose regulation, insulin dynamics, hepatic metabolism, and energy balance. Kidney, liver, immune, endocrine, neurological, musculoskeletal, and gastrointestinal systems have their own specialized models.

Below them are increasingly detailed molecular and cellular models. Above them is a whole-body model capable of reasoning about how these systems interact.

![A hierarchy of biological models, from molecular and cellular layers through specialized organ systems to a coordinated whole-body model.](assets/model/society-of-organs.svg)

It is less like one artificial neural network and more like a **Society of Organs**.

But there is a crucial safety condition:

> **The Society of Organs is a federation of biological intelligence, not a clinical authority.**

Several models agreeing with one another does not make them correct. A coordinating model sitting above other models does not become an objective supervisor merely because it has the final word. And asking one generative model to judge another does not create an independent safety standard if both share the same blind spots.

The federation should therefore produce, challenge, and refine hypotheses while an independent assurance path determines what may safely cross into consequential action.

## A federation of biological intelligence

No single hospital, technology company, or research institution needs to build all of these models.

Specialized laboratories could develop competing models for individual biological systems, much as specialized AI laboratories develop foundation models today.

An individual might use the best available cardiovascular model from one research group, a metabolic model from another, and a genomic interpretation model from a third. Better models could replace older ones as science advances, without replacing the entire system.

The computational representation of the individual therefore becomes a federation of biological models.

> **A biological model is not yet a digital twin.** It becomes a digital twin when it is continuously calibrated against a particular human being.

Model diversity is useful for another reason: independence. When two models genuinely differ in training data, mechanism, architecture, provider, or epistemic basis, disagreement between them is informative. When several agents are merely different prompts around the same underlying model, apparent diversity can conceal correlated error.

Future computational medicine should therefore record not only which models contributed to a conclusion, but how independent they are from one another and what external standard, if any, was used to check their work.

## From occasional measurements to continuous observation

Historically, medicine has observed the body intermittently.

A blood test provides a snapshot. A consultation captures a moment. An ECG records a few seconds or minutes. An MRI provides an image at one point in time.

That is changing.

Wearable ECG, continuous glucose monitoring, blood pressure, sleep, movement, temperature, EEG, imaging, and laboratory measurements are steadily increasing the resolution with which we can observe human physiology. Genomics, proteomics, and metabolomics add deeper biological layers. Over time, continuous or near-continuous molecular sensing could extend this much further.

Every new observation can update the state of the digital twin.

![Continuous observations update a living state estimate with evidence, uncertainty, provenance, and predicted trajectories.](assets/model/continuous-calibration.svg)

The result is fundamentally different from an electronic health record.

| Electronic health record | Human digital twin |
|---|---|
| Records that a glucose measurement of 145 mg/dL occurred yesterday | Maintains an evolving estimate of the person’s metabolic state |
| Organizes observations and conclusions | Connects observations, models, uncertainty, and provenance |
| Primarily describes what happened | Estimates what is happening now and what may happen next |

The difference is between **recording the past** and **maintaining an evolving model of the present**.

That evolving model must also distinguish what is observed from what is inferred. A laboratory result, ECG trace, or genomic variant is evidence. A state estimate derived from those measurements is a claim made by a model. The model may be wrong even when the evidence is perfectly authentic.

This distinction becomes more important, not less, as the twin becomes more capable.

## Healthcare becomes counterfactual

Once we have sufficiently capable models, the questions medicine can ask begin to change.

Today, one of the central questions is:

> **What disease does this person have?**

That remains important. But it becomes part of a larger set of questions:

1. What state is this biological system currently in?
2. What mechanisms best explain that state?
3. Where is it likely to go from here?
4. What would happen if we intervened?
5. What would happen under intervention A instead of B?
6. What sequence of interventions has the greatest probability of moving this system toward a healthier state?

![A current biological state branches into multiple simulated interventions, predicted outcomes, and an evidence-informed choice.](assets/model/counterfactual-medicine.svg)

This is a shift from predominantly diagnostic medicine toward increasingly predictive and counterfactual medicine.

Diagnosis does not disappear. But it becomes one useful representation derived from a richer underlying model rather than the organizing principle of the entire architecture.

Counterfactual medicine also creates a new obligation: a prediction must not be allowed to authorize itself. A model may estimate what might happen after a drug, procedure, behavioral change, device intervention, or molecular perturbation. That estimate is still only a modeled claim. Real-world clinical authority belongs to a separate system of consent, professional responsibility, policy, evidence, and governed action.

## The patient carries the model

There is a useful, although imperfect, analogy with modern automobiles.

Cars no longer rely entirely on a mechanic inferring their internal condition from symptoms. They continuously measure themselves, maintain internal state, detect abnormalities, and expose standardized diagnostic interfaces.

Owners can handle simple maintenance themselves. Specialists and service centers intervene when expensive equipment or expertise is required.

Human beings are, of course, incomparably more complex than cars. Biology is probabilistic, adaptive, and only partially understood.

But the architectural principle is powerful:

> **The individual should carry the continuously updated computational representation of themselves.**

When someone arrives at a hospital, the healthcare system should not have to reconstruct that person from years of fragmented records.

With the individual’s authorization, it should be able to query their computational model.

## OpenBody: an interface to the computational human

I call this interface **OpenBody**.

OpenBody is not another electronic health-record format.

FHIR describes healthcare information. DICOM describes medical imaging. Other standards describe measurements, genomic information, and specific forms of clinical data.

OpenBody sits above them.

It describes the current computational state of a human being: the evidence supporting that state, the models that produced it, their uncertainty, dependencies between biological systems, predicted trajectories, executable counterfactuals, and the outcomes of previous interventions.

It could become an interoperability layer connecting people, biological digital twins, AI systems, healthcare providers, researchers, and medical devices.

![OpenBody connects the individual’s digital twin with models, care providers, researchers, devices, and AI systems through an interoperable interface.](assets/model/openbody-interoperability.svg)

A hospital receiving a patient should eventually be able—with appropriate authorization—to ask:

- What is currently known about this person’s cardiovascular state?
- What evidence supports that assessment?
- Which models produced it?
- How uncertain are those conclusions?
- What has materially changed during the last 24 hours?
- Which interventions have already been simulated?
- Which interventions were actually performed?
- How did the observed response compare with the predicted response?
- Which conclusions are direct observations, statistical associations, causal estimates, or mechanistic simulations?
- Which models disagree, and on what exact claim?
- Was a claim verified against an external standard, merely supported by model consensus, or only observed by a judging system?
- How independent was the checker from the model it checked?
- What is the checker allowed to do when it finds a problem?
- Which questions cannot currently be answered safely?

That final question matters enormously.

> A trustworthy digital twin must represent not only what it believes, but **what it does not know—and why**.

And a trustworthy clinical AI system must represent not only that something was “checked,” but **what was checked, against what, by whom or what, with what independence, and with what authority to prevent harm**.

## More agents do not equal more safety

Clinical AI is moving rapidly toward multi-agent systems: specialist agents, coordinators, judges, verifiers, debate panels, and monitoring agents. The intuition is attractive. Medicine itself is collaborative, so a computational multidisciplinary team appears more robust than a single model.

But collaboration and oversight are not the same thing.

A second agent can perform at least four different jobs:

- validate whether the first agent has sound evidence and inputs;
- verify an output against an external standard;
- arbitrate disagreement among agents;
- observe and score another agent without controlling it.

These functions provide very different kinds of assurance. A consensus vote proves only that models agree. A judge that reports a score improves visibility but may not prevent anything. Verification against an applicable external standard can be stronger, but only where such a standard exists and is current for the patient in question.

The strongest clinical architecture will therefore not be the one with the most agents. It will be the one that uses the **simplest independent check that can actually establish the required predicate**, and escalates when that check cannot resolve the question.

Sometimes the best overseer of an AI system will be another model. Often it will instead be a deterministic rule, exact evidence-version check, clinical policy, terminology constraint, consent predicate, formal invariant, or other mechanism simpler than the model it constrains.

This leads to an important design principle:

> **Use intelligence to generate hypotheses. Use independent evidence and constraints to decide what can safely pass.**

## Disagreement is where attention belongs

Universal debate among many models is expensive and can amplify shared errors. A better pattern is selective escalation.

When independent models agree, the evidence is complete, applicability is valid, and an external policy permits routine handling, the system should be able to compress that agreement without forcing a human to inspect every step.

When models disagree, evidence is stale or missing, verification fails, the standard cannot be resolved, or the consequence is clinically significant, the system should spend more compute and more human attention there.

The goal is not to remove clinicians from care. It is to remove clinicians from **mechanically verifying routine computational work** while making the exceptional cases more visible and better supported.

## This does not remove the clinician

The digital twin does not replace clinical expertise.

It changes where clinical reasoning begins.

Instead of spending much of the clinical encounter reconstructing the patient from a fragmented historical record, the clinician can begin with a continuously calibrated computational representation of the person.

The physician can inspect it, challenge it, interrogate its evidence, test alternative hypotheses, add observations, and independently interpret its conclusions.

Clinical expertise becomes more powerful because the starting point is richer.

But human involvement should also become more selective. A clinician should not have to verify every claim, citation, or intermediate computation produced by the system. That would simply move administrative burden from operating the EHR to operating the AI.

The better model is human oversight at the points where consent, unresolved uncertainty, conflicting evidence, professional judgment, or clinical authority genuinely require it.

And the relationship should work in both directions.

Every intervention becomes an experiment from which the model can learn.

The system predicts a response. Independent checks validate the evidence and applicable constraints. A person or governed clinical runtime authorizes the action where required. The intervention occurs. Execution is verified. The body responds. New observations arrive. Prediction and reality are compared. The model is recalibrated.

![The learning loop: observe, model, predict, intervene, measure, and learn.](assets/model/learning-loop.svg)

The mature loop is therefore richer than the original diagram:

> **Observe → validate evidence → model → detect disagreement → predict → verify constraints → escalate where needed → authorize → intervene → verify execution → measure → recalibrate → learn.**

## Safety should come from structure, not confidence theater

A clinical system should never ask a user to trust a number merely because several agents agree or because a judge reports high confidence.

The useful questions are structural:

- What exact evidence was used?
- Is it current and applicable?
- Which model and immutable version produced the claim?
- What independent mechanism checked it?
- Did the checker share the same model family or failure mode?
- Was the claim checked against an external standard or merely compared with another model?
- Could the checker block or escalate, or did it only annotate?
- What clinically significant errors does the oversight mechanism actually detect?
- What happens when the checker cannot resolve the question?
- Who remains accountable for the real-world action?

That is the difference between **observability** and **assurance**.

## Beyond the EHR

The EHR will not simply disappear. Records, provenance, consent, auditability, and clinical documentation will remain essential.

But their role changes.

The future EHR becomes less like a medical filing cabinet and more like a runtime for the human digital twin.

- **The medical record** becomes the evidence.
- **The digital twin** becomes the model.
- **AI** becomes the reasoning interface.
- **Independent assurance** determines what computational claims may safely pass.
- **Clinical authority** remains separate from simulation and model consensus.
- **OpenBody** becomes the interoperability layer.

And healthcare evolves from episodically documenting disease toward continuously understanding, predicting, maintaining, and restoring the state of the human organism.

That is the transition I believe lies ahead:

> **From electronic health records to executable human models.**
