"""Test-only model publisher for the live ProvidEHR consumer verifier.

No production authority, physiological model, or known COSMIC uncertainty is
asserted. The real worker source remains unchanged. A distinct synthetic source
exists only to exercise positive clinical-publication transport and revocation.
"""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import inspect
from uuid import uuid4

from openbody_ref.model_family import (SCHEMA, CounterfactualEvaluation, CounterfactualModelRegistration,
    ForecastEvaluation, ForecastPoint, ModelEvaluation, QualificationLease, QualifiedModelRuntime)
from openbody_ref.model_clinical_reference import QualifiedClinicalReferencePublisher, VerifiedSubjectBinding
from openbody_ref.observation import validate_observation
from openbody_ref.validation import canonical_digest


def software_counterfactual(inputs, parameters, perturbation, horizon):
    """Arithmetic test only; the synthetic difference is not a treatment effect."""
    value = inputs["temperature"][0]["quantity"]["value"]
    uncertainty = {"epistemic": 0.2, "aleatoric": 0.2, "coverage": 0.8,
                   "out_of_distribution": False, "reasons": ["Synthetic software transport test"]}
    initial = ForecastPoint(0, ModelEvaluation({"synthetic_value": value}, uncertainty))
    final = ForecastPoint(horizon, ModelEvaluation({"synthetic_value": value + 1}, uncertainty))
    control = ForecastEvaluation((initial, final), uncertainty, ("No physiological dynamics are asserted",))
    intervention = replace(control, points=(initial, ForecastPoint(horizon,
        ModelEvaluation({"synthetic_value": value + 1 - perturbation["parameters"]["dose"]}, uncertainty))))
    return CounterfactualEvaluation(control, intervention, {"synthetic_value": uncertainty}, uncertainty,
        ("Test-only arithmetic, synthetic authority and identity; no clinical efficacy claim",))


def prepare_publication(configuration, observation, clinical_source):
    subject = observation["subject"]
    locator = configuration["admitted"]
    artifact = inspect.getsource(software_counterfactual).encode()
    now = datetime.now(timezone.utc)
    contract = {"profile": "openbody.model-family-contract.v1", "schema_version": "0.1", "kind": "ModelFamilyContract", "id": "live-transport-test",
        "model": {"id": "synthetic-publication-check", "version": "1.0.0", "family": "statistical", "artifact_digest": "sha256:" + hashlib.sha256(artifact).hexdigest(), "coordinate": "ob://human/whole_body"},
        "context_of_use": ["clinical_decision_support"], "supported_population": ["synthetic-fixture"],
        "supported_question": ["software-publication-check"], "prediction_horizon_seconds": [600],
        "required_observations": [{"key": "temperature", "code_system": observation["code"]["system"], "code": observation["code"]["code"],
            "unit": observation["quantity"]["code"], "minimum_count": 1, "maximum_age_seconds": 365 * 86400, "minimum_value": 0, "maximum_value": 100}],
        "allowed_adaptation": {"parameters": [], "outside_envelope": "dg_review_required"},
        "behavioral_envelope": [{"name": "synthetic_value", "unit": "Cel", "minimum": 0, "maximum": 101}],
        "uncertainty_contract": {"unknown_input": "propagate_unknown", "out_of_distribution": "abstain"},
        "abstention_rules": SCHEMA["properties"]["abstention_rules"]["const"], "prohibited_uses": ["autonomous_treatment"],
        "dependencies": [{"ref": "test:runtime", "digest": "sha256:" + "1" * 64}],
        "qualification_evidence": [{"ref": "test:synthetic-clinical-policy", "digest": "sha256:" + "2" * 64, "kind": "clinical"}],
        "counterfactual": {"start_timing": "execution_time", "perturbations": [{"id": "test-dose", "class": "research",
            "scope": "ob://human/whole_body", "parameters": [{"name": "dose", "unit": "test_unit", "minimum": 0, "maximum": 1}]}],
            "effect_bounds": [{"name": "synthetic_value", "minimum": -1, "maximum": 0}]}}
    request = {"model_id": contract["model"]["id"], "subject": subject, "purpose": "clinical_decision_support",
        "population": "synthetic-fixture", "question": "software-publication-check", "horizon_seconds": 600,
        "observations": [deepcopy(locator)], "adaptation": {}, "perturbation": {"id": "test-dose", "parameters": {"dose": 1}}}
    lease = QualificationLease("test:qualification", "1", canonical_digest(contract), subject, locator["tenant_id"],
        request["purpose"], request["population"], request["question"], request["horizon_seconds"], contract["model"]["artifact_digest"],
        (("test:runtime", "sha256:" + "1" * 64),), (("test:synthetic-clinical-policy", "sha256:" + "2" * 64),),
        now - timedelta(seconds=10), now + timedelta(minutes=5), "active")

    class Authority:
        current = lease
        def resolve(self, contract_digest, request): return self.current

    class Identity:
        current = VerifiedSubjectBinding(subject, locator["tenant_id"], locator["ehr_id"], "test:identity", "synthetic-only-identity",
            "sha256:" + "3" * 64, "test:identity-revocation", now - timedelta(seconds=10), now + timedelta(minutes=10), "verified")
        def resolve(self, subject, tenant_id, ehr_id): return self.current

    # Distinct test source and clinical version; the real worker observation is
    # never edited, replaced or reported as having quantified uncertainty.
    synthetic = deepcopy(observation)
    uid = str(uuid4())
    version = dict(locator, composition_uid=uid, version_uid=f"{uid}::synthetic-test::1")
    synthetic["id"] = "urn:openbody:observation:" + version["version_uid"]
    synthetic["source"].update(clinical_version=version, system="synthetic-test-only", resource_ref="Observation/synthetic-known-input",
        resource_digest=canonical_digest({"kind": "SyntheticTestSource", "id": uid}), resource_version="test-1", parent=None)
    synthetic["normalization"]["source"]["source_id"] = synthetic["source"]["resource_ref"]
    synthetic["uncertainty"] = {"epistemic": 0.1, "aleatoric": 0.1, "coverage": 0.9, "out_of_distribution": False,
                               "reasons": ["Separate synthetic known-input fixture; not a COSMIC measurement"]}
    validate_observation(synthetic, subject=subject)

    class Sources:
        fixture = synthetic
        def resolve(self, requested):
            if requested == version:
                return deepcopy(self.fixture)
            return clinical_source.resolve(requested)

    sources, authority, identity = Sources(), Authority(), Identity()
    runtime = QualifiedModelRuntime(subject, locator["tenant_id"], sources, authority,
        [CounterfactualModelRegistration(contract, artifact, software_counterfactual)])
    publisher = QualifiedClinicalReferencePublisher(runtime, identity, configuration["publisher_url"])
    fixture_request = dict(deepcopy(request), observations=[version])
    return runtime, publisher, request, fixture_request, authority, identity, sources
