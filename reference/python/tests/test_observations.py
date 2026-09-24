from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from openbody_ref.client import OpenBodyClient
from openbody_ref.host import ROOT, create_app, create_observation_host_from_env
from openbody_ref.observation import SCHEMA, ObservationError, ProvidEHRObservationSource, validate_locator, validate_observation
from openbody_ref.store import InMemoryTwinStore
from openbody_ref.validation import validate_definition


FIXTURE = Path(__file__).parent / "fixtures" / "providehr-kernel-observation.json"


@pytest.fixture
def version():
    return json.loads(FIXTURE.read_text())


def observation(version):
    return version["composition"]["context"]["openbody_observation"]


def test_profile_schema_is_valid():
    Draft202012Validator.check_schema(SCHEMA)


def locator(version):
    return observation(version)["source"]["clinical_version"]


def resolver(version, handler=None):
    reference = locator(version)
    return ProvidEHRObservationSource(
        "https://providehr.test", "synthetic-token", reference["tenant_id"], reference["ehr_id"],
        transport=httpx.MockTransport(handler or (lambda _: httpx.Response(200, json=version))),
    )


def host(version, source=None):
    store = InMemoryTwinStore(state={"subject": observation(version)["subject"]})
    return TestClient(create_app(store=store, observation_source=source or resolver(version), observations_only=True)), store


def test_producer_projection_round_trips_through_source_host_store_and_client(version):
    calls = []

    def source_handler(request):
        calls.append(request)
        assert request.headers["authorization"] == "Bearer synthetic-token"
        ref = locator(version)
        assert request.url.path == f"/v1/ehr/{ref['ehr_id']}/composition/{ref['composition_uid']}/version/{ref['version_uid']}"
        return httpx.Response(200, json=version)

    api, store = host(version, resolver(version, source_handler))

    def host_handler(request):
        response = api.request(request.method, request.url.raw_path.decode(), content=request.content,
                               headers={"content-type": "application/json"})
        return httpx.Response(response.status_code, content=response.content, headers=response.headers)

    with OpenBodyClient("http://openbody.test", transport=httpx.MockTransport(host_handler)) as client:
        assert client.capabilities()["capabilities"] == ["observations.ingest", "observations.read"]
        value = client.ingest_observation(locator(version))
        assert value == observation(version)
        assert value["quantity"]["value"] == pytest.approx(37)
        assert value["quantity"]["code"] == "Cel"
        assert value["normalization"]["source"]["quantity"]["value"] == 98.6
        assert value["uncertainty"]["coverage"] is None
        assert value["uncertainty"]["out_of_distribution"] == "unknown"
        assert "resourceType" not in json.dumps(value)
        assert client.ingest_observation(locator(version)) == value
        assert client.observation(value["id"], subject=value["subject"]) == value
        assert len(calls) == 3  # Replay and read both require source access.
        value["quantity"]["value"] = 100
        assert store.observation(value["id"])["quantity"]["value"] == 37


@pytest.mark.parametrize("extra", [{"quantity": {"value": 37}}, {"status": "normalized"}, {"source_url": "https://attacker.test"}])
def test_caller_cannot_submit_facts_status_or_origin(version, extra):
    def unexpected(_):
        pytest.fail("invalid locator reached source")
    api, store = host(version, resolver(version, unexpected))
    for value in [observation(version), locator(version) | extra]:
        response = api.post("/v1/observations", json=value)
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "invalid_source_locator"
    assert not store.observations


@pytest.mark.parametrize("field,value", [
    ("tenant_id", "other-tenant"), ("ehr_id", "other-ehr"),
])
def test_source_scope_cannot_be_selected_by_caller(version, field, value):
    def unexpected(_):
        pytest.fail("cross-scope locator reached source")
    api, store = host(version, resolver(version, unexpected))
    response = api.post("/v1/observations", json=locator(version) | {field: value})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "source_scope_mismatch"
    assert not store.observations


@pytest.mark.parametrize("field,value", [
    ("ehr_id", "../other"), ("ehr_id", "%2e%2e"), ("ehr_id", "x?secret"),
    ("composition_uid", "other"), ("version_uid", "bad"), ("version_uid", "x::y::0"),
    ("version_uid", "x::y::" + "9" * 5000),
])
def test_locator_rejects_noncanonical_identifiers(version, field, value):
    with pytest.raises(ObservationError, match="locator|version|identifiers"):
        validate_locator(locator(version) | {field: value})


@pytest.mark.parametrize("path,value", [
    (("ehr_id",), "other-ehr"),
    (("version_uid",), "other-version"),
    (("composition", "template_id"), "providehr.fhir_admission_review.v1"),
    (("composition", "context", "tenant_id"), "other-tenant"),
    (("composition", "context", "upstream_version"), "other-source-version"),
    (("composition", "context", "external_source_system"), "other-vendor"),
    (("composition", "context", "semantic_admission", "result", "status"), "review_required"),
    (("composition", "context", "source_evidence", "payload_hash"), "sha256:" + "0" * 64),
    (("composition", "content", "observation", "value"), 100),
    (("composition", "content", "observation", "patient_external_id"), "other-patient"),
    (("composition", "context", "openbody_observation", "source", "clinical_version", "tenant_id"), "other-tenant"),
])
def test_source_response_must_match_immutable_version_admission_and_content(version, path, value):
    tampered = deepcopy(version)
    node = tampered
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    source = resolver(version, lambda _: httpx.Response(200, json=tampered))
    api, store = host(version, source)
    assert api.post("/v1/observations", json=locator(version)).status_code == 422
    assert not store.observations


@pytest.mark.parametrize("status", ["partially_normalized", "review_required", "rejected"])
def test_even_self_consistent_projection_cannot_promote_an_unadmitted_source(version, status):
    observation(version)["normalization"]["status"] = status
    version["composition"]["context"]["semantic_admission"]["result"]["status"] = status
    api, store = host(version)
    assert api.post("/v1/observations", json=locator(version)).status_code == 422
    assert not store.observations


@pytest.mark.parametrize("number", [float("nan"), float("inf"), -float("inf"), 10**400])
def test_nonfinite_or_unrepresentable_values_are_rejected(version, number):
    value = observation(version)
    value["quantity"]["value"] = value["normalization"]["quantity"]["value"] = number
    with pytest.raises(ObservationError):
        validate_observation(value)


def test_unknown_time_and_uncertainty_remain_unknown(version):
    value = observation(version)
    value["effective_time"] = value["normalization"]["source"]["effective_time"] = None
    validate_observation(value)
    assert value["effective_time"] is None
    assert value["uncertainty"]["aleatoric"] is None


def test_contained_observation_preserves_parent_and_rejects_cross_patient(version):
    value = observation(version)
    parent = {"resource_ref": "DiagnosticReport/report", "payload_hash": "a" * 64,
              "path": "/contained/0", "subject_reference": "Patient/synthetic-1"}
    value["source"]["parent"] = parent
    version["composition"]["context"]["source_evidence"]["parent"] = deepcopy(parent)
    assert resolver(version).resolve(locator(version))["source"]["parent"] == parent
    parent["subject_reference"] = "Patient/another"
    with pytest.raises(ObservationError):
        validate_observation(value)


def test_source_timeout_and_malformed_json_are_sanitized(version):
    def timeout(request):
        raise httpx.ReadTimeout("synthetic-token must not escape", request=request)
    for handler in [timeout, lambda _: httpx.Response(200, text="not JSON")]:
        api, _ = host(version, resolver(version, handler))
        response = api.post("/v1/observations", json=locator(version))
        assert response.status_code == 503
        assert "synthetic-token" not in response.text


@pytest.mark.parametrize("status", [401, 403, 404, 500, 302])
def test_unavailable_or_denied_source_never_serves_cached_observation(version, status):
    response_status = 200
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(response_status, json=version, headers={"location": "https://attacker.test"})

    api, store = host(version, resolver(version, handler))
    assert api.post("/v1/observations", json=locator(version)).status_code == 200
    response_status = status
    response = api.get(f"/v1/observations/{observation(version)['id']}")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "source_unavailable"
    assert "synthetic-token" not in response.text
    assert len(calls) == 2  # No redirect was followed.
    assert len(store.observations) == 1  # Historical evidence is retained.


def test_immutable_conflict_and_read_tamper_rejected(version):
    api, store = host(version)
    value = observation(version)
    assert api.post("/v1/observations", json=locator(version)).status_code == 200
    changed = deepcopy(value)
    changed["uncertainty"]["reasons"] = ["A different source result"]
    with pytest.raises(ObservationError) as error:
        store.put_observation(changed)
    assert error.value.code == "observation_conflict"
    store.observations[value["id"]] = changed
    response = api.get(f"/v1/observations/{value['id']}")
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "source_changed"
    store.observations[value["id"]]["subject"] = "subject:another"
    assert api.get(f"/v1/observations/{value['id']}").status_code == 422


def test_observation_never_validates_as_model_state_simulation_or_clinical_assertion(version):
    value = observation(version)
    for definition in ["BodyState", "BodyTrajectory", "CounterfactualScenario", "Abstention"]:
        with pytest.raises(Exception):
            validate_definition(definition, value)
    assertion_schema = json.loads((ROOT / "schemas" / "clinical-assertion-reference.schema.json").read_text())
    assert not Draft202012Validator(assertion_schema).is_valid(value)
    assert "Observation" not in assertion_schema["properties"]["object_kind"]["enum"]
    for kind in ["BodyState", "CounterfactualScenario", "ClinicalAssertion"]:
        with pytest.raises(ObservationError):
            validate_observation(value | {"kind": kind})


def test_observation_only_host_exposes_no_demo_body_state(version):
    api, _ = host(version)
    for method, path in [("GET", "/v1/state"), ("GET", "/v1/trajectories/x"), ("POST", "/v1/simulations"), ("POST", "/v1/outcomes"), ("POST", "/v1/calibrations")]:
        assert api.request(method, path, json={}).status_code == 404
    assert api.get("/v1/observations/profile").json()["profile"] == observation(version)["profile"]
    assert api.get("/v1/observations/unknown").status_code == 404
    assert TestClient(create_app()).post("/v1/observations", json=locator(version)).status_code == 404
    catalogue = TestClient(create_app(discovery_only=True, observation_source=resolver(version)))
    assert catalogue.post("/v1/observations", json=locator(version)).status_code == 404
    assert "observations.ingest" not in catalogue.get("/v1/capabilities").json()["capabilities"]
    with pytest.raises(ValueError):
        create_app(observations_only=True)


@pytest.mark.parametrize("origin", ["http://clinical.example", "https://user:secret@clinical.example", "https://clinical.example?token=secret", "file:///tmp/records"])
def test_source_origin_is_operator_bound_and_protects_credentials(origin):
    with pytest.raises(ValueError):
        ProvidEHRObservationSource(origin, "token", "tenant", "ehr")


def test_factory_requires_explicit_configuration_and_does_not_load_demo(monkeypatch, tmp_path, version):
    names = ["URL", "TOKEN_FILE", "TENANT", "EHR"]
    for name in names:
        monkeypatch.delenv(f"OPENBODY_SOURCE_{name}", raising=False)
    with pytest.raises(ValueError):
        create_observation_host_from_env()
    token = tmp_path / "token"
    token.write_text("synthetic-token")
    values = ["https://providehr.test", str(token), locator(version)["tenant_id"], locator(version)["ehr_id"]]
    for name, value in zip(names, values):
        monkeypatch.setenv(f"OPENBODY_SOURCE_{name}", value)
    with TestClient(create_observation_host_from_env()) as api:
        assert api.get("/v1/state").status_code == 404
        assert api.get("/healthz").json()["models"] == 0
    token.write_text("x" * 8193)
    with pytest.raises(ValueError):
        create_observation_host_from_env()
