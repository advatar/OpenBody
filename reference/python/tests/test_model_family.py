from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import inspect
import json
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
import pytest
import httpx

from openbody_ref.host import create_model_execution_host, create_app
from openbody_ref.client import OpenBodyClient
from openbody_ref.model_family import (SCHEMA, ModelEvaluation, ModelExecutionError, ModelRegistration,
    QualificationLease, QualifiedModelRuntime, validate_contract)
from openbody_ref.validation import canonical_digest, parse_timestamp, semantic_validate, validate_definition


def synthetic_model(inputs, parameters):
    """Test arithmetic only. This is not a physiological or clinical model."""
    return ModelEvaluation({"synthetic_shifted_value": inputs["temperature"][0]["quantity"]["value"] + parameters["offset"]},
        {"epistemic": 0.2, "aleatoric": 0.2, "coverage": 0.8, "out_of_distribution": False, "reasons": ["Synthetic software test"]})


ARTIFACT = inspect.getsource(synthetic_model).encode()


@pytest.fixture
def setup():
    version = json.loads((Path(__file__).parent / "fixtures/providehr-kernel-observation.json").read_text())
    row = version["composition"]["context"]["openbody_observation"]
    now = parse_timestamp(row["effective_time"]) + timedelta(seconds=60)
    contract = {"profile": "openbody.model-family-contract.v1", "schema_version": "0.1", "kind": "ModelFamilyContract", "id": "test-contract",
        "model": {"id": "synthetic-offset", "version": "1.0.0", "family": "statistical", "artifact_digest": "sha256:" + hashlib.sha256(ARTIFACT).hexdigest(), "coordinate": "ob://human/whole_body"},
        "context_of_use": ["software_test"], "supported_population": ["synthetic-fixture"], "supported_question": ["software-offset-check"], "prediction_horizon_seconds": [0],
        "required_observations": [{"key": "temperature", "code_system": row["code"]["system"], "code": row["code"]["code"], "unit": row["quantity"]["code"],
                                  "minimum_count": 1, "maximum_age_seconds": 3600, "minimum_value": 0, "maximum_value": 100}],
        "allowed_adaptation": {"parameters": [{"name": "offset", "minimum": -1, "maximum": 1, "default": 0}], "outside_envelope": "dg_review_required"},
        "behavioral_envelope": [{"name": "synthetic_shifted_value", "unit": "Cel", "minimum": 0, "maximum": 101}],
        "uncertainty_contract": {"unknown_input": "propagate_unknown", "out_of_distribution": "abstain"},
        "abstention_rules": SCHEMA["properties"]["abstention_rules"]["const"], "prohibited_uses": ["clinical_decision_support", "research"],
        "dependencies": [{"ref": "test:runtime", "digest": "sha256:" + "1" * 64}],
        "qualification_evidence": [{"ref": "test:software-conformance", "digest": "sha256:" + "2" * 64, "kind": "software"}]}
    request = {"model_id": contract["model"]["id"], "subject": row["subject"], "purpose": "software_test", "population": "synthetic-fixture",
               "question": "software-offset-check", "horizon_seconds": 0, "observations": [row["source"]["clinical_version"]], "adaptation": {}}
    lease = QualificationLease("test:decision", "1", canonical_digest(contract), row["subject"], row["source"]["clinical_version"]["tenant_id"], "software_test", "synthetic-fixture", "software-offset-check", 0,
        contract["model"]["artifact_digest"], (("test:runtime", "sha256:" + "1" * 64),), (("test:software-conformance", "sha256:" + "2" * 64),),
        now - timedelta(seconds=10), now + timedelta(hours=1), "active")

    class Source:
        calls = 0
        unavailable = False
        def resolve(self, locator):
            self.calls += 1
            if self.unavailable:
                raise ValueError("source revoked")
            return deepcopy(row)

    class Authority:
        calls = 0
        current = lease
        def resolve(self, contract_digest, request):
            self.calls += 1
            return self.current

    source = Source(); authority = Authority()
    clock = [now]
    def runtime(evaluate=synthetic_model, override=None):
        return QualifiedModelRuntime(row["subject"], row["source"]["clinical_version"]["tenant_id"], source, authority, [ModelRegistration(override or contract, ARTIFACT, evaluate)], clock=lambda: clock[0])
    return contract, request, row, source, authority, clock, runtime


def test_schema_and_actual_model_call_preserve_observation_inference_boundary(setup):
    contract, request, row, source, authority, _, factory = setup
    Draft202012Validator.check_schema(SCHEMA)
    validate_contract(contract)
    runtime = factory()
    request["adaptation"] = {"offset": 1}
    state = runtime.execute(request)
    semantic_validate(state)
    assert state["kind"] == "BodyState" and row["kind"] == "Observation"
    assert state["subsystems"][0]["state_vector"] == {"synthetic_shifted_value": 38}
    assert state["uncertainty"]["coverage"] is None
    assert state["uncertainty"]["out_of_distribution"] == "unknown"
    assert state["evidence"][0]["source_provenance"]["normalization"] == row["normalization"]
    assert state["evidence"][0]["content_digest"] == canonical_digest(row)
    assert state["model_receipts"][0]["environment_digest"] == canonical_digest(contract)
    assert source.calls == 2 and authority.calls == 2
    assert runtime.read(state["id"]) == state
    state["subsystems"][0]["state_vector"]["synthetic_shifted_value"] = 999
    assert runtime.read(state["id"])["subsystems"][0]["state_vector"]["synthetic_shifted_value"] == 38


@pytest.mark.parametrize("field", list(SCHEMA["required"]))
def test_all_contract_fields_are_required(setup, field):
    contract = deepcopy(setup[0]); contract.pop(field)
    with pytest.raises(ModelExecutionError): validate_contract(contract)


@pytest.mark.parametrize("field,value", [("subject", "subject:other"), ("purpose", "clinical_decision_support"), ("population", "adult"),
    ("question", "treatment"), ("horizon_seconds", 7200), ("model_id", "unregistered"), ("adaptation", {"offset": 2}), ("adaptation", {"new_weight": 0.1}),
    ("adaptation", {"offset": True}), ("horizon_seconds", True)])
def test_unsupported_requests_never_call_a_model_or_source(setup, field, value):
    _, request, _, source, _, _, factory = setup
    request[field] = value
    def forbidden(*args): pytest.fail("unsupported request reached model")
    with pytest.raises(ModelExecutionError): factory(forbidden).execute(request)
    assert source.calls == 0


@pytest.mark.parametrize("field,value", [("status", "revoked"), ("revision", ""), ("contract_digest", "sha256:" + "f" * 64),
    ("artifact_digest", "sha256:" + "f" * 64), ("subject", "subject:other"), ("population", "adult"), ("purpose", "research"),
    ("question", "other"), ("tenant_id", "other"), ("horizon_seconds", 10), ("dependency_digests", ()), ("evidence_digests", ())])
def test_current_qualification_binds_every_execution_dimension(setup, field, value):
    _, request, _, source, authority, _, factory = setup
    authority.current = replace(authority.current, **{field: value})
    with pytest.raises(ModelExecutionError): factory().execute(request)
    assert source.calls == 0


def test_qualification_expiry_and_revocation_disable_retained_results(setup):
    _, request, _, source, authority, clock, factory = setup
    runtime = factory(); state = runtime.execute(request)
    authority.current = replace(authority.current, status="revoked")
    with pytest.raises(ModelExecutionError): runtime.read(state["id"])
    with pytest.raises(ModelExecutionError): runtime.execute(request)
    authority.current = replace(authority.current, status="active")
    clock[0] = authority.current.valid_until
    with pytest.raises(ModelExecutionError): runtime.read(state["id"])
    with pytest.raises(ModelExecutionError): runtime.execute(request)
    source.unavailable = True
    with pytest.raises(ModelExecutionError): runtime.read(state["id"])


@pytest.mark.parametrize("kind", ["source", "qualification", "revision", "source_content"])
def test_changes_during_actual_execution_prevent_a_result(setup, kind):
    _, request, row, source, authority, _, factory = setup
    def mutate(inputs, parameters):
        if kind == "source": source.unavailable = True
        elif kind == "source_content": row["uncertainty"]["coverage"] = 0.7
        elif kind == "revision": authority.current = replace(authority.current, revision="2")
        else: authority.current = replace(authority.current, status="revoked")
        return synthetic_model(inputs, parameters)
    with pytest.raises(ModelExecutionError): factory(mutate).execute(request)


def test_host_tenant_cannot_be_selected_by_a_source_locator(setup):
    _, request, _, source, _, _, factory = setup
    runtime = factory()
    request["observations"][0] = dict(request["observations"][0], tenant_id="foreign-tenant")
    with pytest.raises(ModelExecutionError, match="hosted tenant"): runtime.execute(request)
    assert source.calls == 0


def test_quantified_model_uncertainty_is_preserved_only_with_known_inputs(setup):
    _, request, row, _, _, _, factory = setup
    row["uncertainty"].update(epistemic=0.1, aleatoric=0.1, coverage=0.9, out_of_distribution=False)
    state = factory().execute(request)
    assert state["uncertainty"]["coverage"] == 0.8
    assert state["uncertainty"]["out_of_distribution"] is False


@pytest.mark.parametrize("mutation", ["bool", "nan_interval", "reversed_interval", "ood"])
def test_invalid_model_uncertainty_is_rejected_before_projection(setup, mutation):
    def invalid(inputs, parameters):
        value = synthetic_model(inputs, parameters)
        if mutation == "bool": value.uncertainty["coverage"] = True
        elif mutation == "nan_interval": value.uncertainty["interval"] = {"lower": 0, "point": float("nan"), "upper": 1}
        elif mutation == "reversed_interval": value.uncertainty["interval"] = {"lower": 1, "point": 0.5, "upper": 0}
        else: value.uncertainty["out_of_distribution"] = 1
        return value
    with pytest.raises(ModelExecutionError): setup[-1](invalid).execute(setup[1])


@pytest.mark.parametrize("case", ["stale", "future", "duplicate", "wrong_unit", "wrong_subject", "unknown", "changed_version", "extra_body"])
def test_required_observation_admission_and_uncertainty_fail_closed(setup, case):
    contract, request, row, _, authority, clock, factory = setup
    if case in ("stale", "future"):
        row["effective_time"] = (clock[0] + timedelta(seconds=-7200 if case == "stale" else 1)).isoformat()
        row["normalization"]["source"]["effective_time"] = row["effective_time"]
    elif case == "duplicate": request["observations"] *= 2
    elif case == "wrong_unit":
        row["quantity"]["code"] = "mg"; row["normalization"]["quantity"]["code"] = "mg"
    elif case == "wrong_subject": row["subject"] = "subject:other"
    elif case == "unknown":
        contract["uncertainty_contract"]["unknown_input"] = "abstain"
        authority.current = replace(authority.current, contract_digest=canonical_digest(contract))
    elif case == "changed_version": request["observations"][0] = dict(request["observations"][0], version_uid="other::1::1")
    elif case == "extra_body": request["observations"][0] = dict(request["observations"][0], quantity=37)
    with pytest.raises(ModelExecutionError): factory().execute(request)


@pytest.mark.parametrize("value", [True, float("nan"), float("inf"), 102, -1, "37"])
def test_model_output_must_stay_in_qualified_behavioral_envelope(setup, value):
    def invalid(inputs, parameters):
        valid = synthetic_model(inputs, parameters)
        return ModelEvaluation({"synthetic_shifted_value": value}, valid.uncertainty)
    with pytest.raises(ModelExecutionError): setup[-1](invalid).execute(setup[1])


def test_proposals_never_activate_new_adaptation_or_change_contract(setup):
    contract, request, _, _, _, _, factory = setup
    runtime = factory(); request["adaptation"] = {"offset": 2}
    candidate = runtime.adaptation_candidate(request)
    Draft202012Validator(SCHEMA["$defs"]["AdaptationCandidate"]).validate(candidate)
    assert candidate["status"] == "dg_review_required" and candidate["activated"] is False
    assert candidate["contract_digest"] == canonical_digest(contract)
    assert runtime.contracts() == [contract]
    with pytest.raises(ModelExecutionError): runtime.execute(request)


def test_registration_requires_exact_loaded_artifact_and_evidence_class(setup):
    contract, _, row, source, authority, _, factory = setup
    with pytest.raises(ModelExecutionError):
        QualifiedModelRuntime(row["subject"], row["source"]["clinical_version"]["tenant_id"], source, authority, [ModelRegistration(contract, b"another artifact", synthetic_model)])
    invalid = deepcopy(contract); invalid["context_of_use"] = ["clinical_decision_support"]; invalid["prohibited_uses"] = ["autonomous_treatment"]
    with pytest.raises(ModelExecutionError): validate_contract(invalid)
    invalid = deepcopy(contract); invalid["prediction_horizon_seconds"] = [7200]
    with pytest.raises(ModelExecutionError): factory(override=invalid)


def test_reference_http_execution_discovery_and_revoked_read(setup):
    contract, request, row, _, authority, _, factory = setup
    api = TestClient(create_model_execution_host(factory()))
    caps = api.get("/v1/capabilities").json()
    assert "model-executions.execute" in caps["capabilities"]
    assert api.get("/v1/model-families").json() == [contract]
    response = api.post("/v1/model-executions", json=request)
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    state = response.json(); semantic_validate(state)
    assert api.get("/v1/model-executions/" + state["id"]).json() == state
    authority.current = replace(authority.current, status="revoked")
    blocked = api.get("/v1/model-executions/" + state["id"])
    validate_definition("Abstention", blocked.json())
    assert blocked.headers["openbody-execution-reason"] == "unqualified"
    assert blocked.json()["kind"] != "Observation"
    assert TestClient(create_app(discovery_only=True)).post("/v1/model-executions", json=request).status_code == 404
    with pytest.raises(ValueError): create_model_execution_host(None)


def test_real_client_round_trip_and_cross_type_producer_value_rejection(setup):
    contract, request, row, _, authority, _, factory = setup
    api = TestClient(create_model_execution_host(factory()))
    def handle(request):
        response = api.request(request.method, request.url.raw_path.decode(), content=request.content,
                               headers={"content-type": "application/json"})
        return httpx.Response(response.status_code, content=response.content, headers=response.headers)
    with OpenBodyClient("http://model.test", httpx.MockTransport(handle)) as client:
        assert client.model_families() == [contract]
        state = client.execute_model(request, contract=contract)
        assert client.model_execution(state["id"], subject=row["subject"], contract=contract) == state
        authority.current = replace(authority.current, status="revoked")
        assert client.model_execution(state["id"], subject=row["subject"], contract=contract)["kind"] == "Abstention"
    for case in ("observation", "subject", "producer", "value", "contract"):
        changed = deepcopy(state)
        if case == "observation": changed = row
        elif case == "subject": changed["subject"] = "subject:other"
        elif case == "producer": changed["model_receipts"][0]["model_version"] = "unqualified"
        elif case == "value": changed["subsystems"][0]["state_vector"]["synthetic_shifted_value"] = 99
        else: changed["model_receipts"][0]["environment_digest"] = "sha256:" + "f" * 64
        with OpenBodyClient("http://model.test", httpx.MockTransport(lambda request: httpx.Response(200, json=changed))) as client:
            with pytest.raises(Exception): client.execute_model(request, contract=contract)
