from __future__ import annotations

import json
from copy import deepcopy

import httpx
from fastapi.testclient import TestClient

from openbody_ref.client import OpenBodyClient
from openbody_ref.host import ROOT, create_app
from openbody_ref.validation import validate_definition


def _fixture() -> dict:
    return json.loads((ROOT / "examples" / "post-meal-walk.scenario.json").read_text())


def test_reference_host_serves_valid_state_and_simulation() -> None:
    app = create_app()
    test_client = TestClient(app)
    assert test_client.get("/.well-known/openbody").status_code == 200
    state = test_client.get("/v1/state")
    assert state.status_code == 200
    assert state.json()["kind"] == "BodyState"

    fixture = _fixture()
    scenario = test_client.get(f"/v1/simulations/{fixture['id']}")
    assert scenario.status_code == 200
    assert scenario.json()["disposition"] == "simulated"


def test_reference_client_executes_supported_counterfactual() -> None:
    app = create_app()
    test_client = TestClient(app)

    def handler(request: httpx.Request) -> httpx.Response:
        response = test_client.request(
            request.method,
            request.url.raw_path.decode(),
            content=request.content,
            headers={"content-type": request.headers.get("content-type", "application/json")},
        )
        return httpx.Response(response.status_code, headers=response.headers, content=response.content)

    fixture = _fixture()
    with OpenBodyClient("http://openbody.test", transport=httpx.MockTransport(handler)) as client:
        assert "simulation.execute" in client.capabilities()["capabilities"]
        state = client.state()
        result = client.simulate(state, fixture["perturbation"], horizon_seconds=7_200)
        assert result["kind"] == "CounterfactualScenario"
        assert result["disposition"] == "simulated"
        assert result["subject"] == state["subject"]
        assert result["model_receipts"]


def test_unsupported_counterfactual_abstains_without_effects() -> None:
    fixture = _fixture()
    request = {
        "state": fixture["baseline"]["states"][0],
        "perturbation": fixture["perturbation"] | {"id": "unsupported_experiment"},
        "horizon_seconds": 7_200,
    }
    response = TestClient(create_app()).post("/v1/simulations", json=request)
    assert response.status_code == 200
    result = response.json()
    assert result["kind"] == "Abstention"
    assert result["reason_code"] == "unsupported_perturbation"


def test_simulation_abstains_for_cross_subject_fixture_replay() -> None:
    fixture = _fixture()
    state = deepcopy(fixture["baseline"]["states"][0])
    state["subject"] = "subject:other"
    response = TestClient(create_app()).post(
        "/v1/simulations",
        json={"state": state, "perturbation": fixture["perturbation"], "horizon_seconds": 7_200},
    )
    assert response.status_code == 200
    assert response.json()["reason_code"] == "out_of_distribution"


def test_simulation_abstains_for_unsupported_horizon_and_scope() -> None:
    fixture = _fixture()
    request = {
        "state": fixture["baseline"]["states"][0],
        "perturbation": fixture["perturbation"],
        "horizon_seconds": 1,
    }
    horizon_response = TestClient(create_app()).post("/v1/simulations", json=request)
    assert horizon_response.status_code == 200
    assert horizon_response.json()["reason_code"] == "out_of_distribution"

    request["horizon_seconds"] = 7_200
    request["requested_scopes"] = ["ob://human/cardiovascular/heart"]
    scope_response = TestClient(create_app()).post("/v1/simulations", json=request)
    assert scope_response.status_code == 200
    assert scope_response.json()["reason_code"] == "unsupported_scope"


def test_simulation_rejects_boolean_horizon_and_abstains_for_changed_dates() -> None:
    fixture = _fixture()
    request = {
        "state": fixture["baseline"]["states"][0],
        "perturbation": fixture["perturbation"],
        "horizon_seconds": True,
    }
    assert TestClient(create_app()).post("/v1/simulations", json=request).status_code == 422

    request["horizon_seconds"] = 7_200
    request["perturbation"] = fixture["perturbation"] | {"starts_at": "2099-01-01T00:00:00Z"}
    response = TestClient(create_app()).post("/v1/simulations", json=request)
    assert response.status_code == 200
    assert response.json()["reason_code"] == "unsupported_perturbation"


def test_discovery_does_not_advertise_unenforced_authorization() -> None:
    discovery = TestClient(create_app()).get("/.well-known/openbody").json()
    assert discovery["authorization"]["schemes"] == []


def test_host_rejects_invalid_outcome() -> None:
    client = TestClient(create_app())
    invalid = {
        "schema_version": "0.1",
        "kind": "ObservedOutcome",
        "id": "outcome-invalid",
        "subject": "subject:demo",
        "perturbation_id": "post_meal_walk",
        "started_at": "2026-08-10T12:00:00Z",
        "ended_at": "2026-08-10T11:00:00Z",
        "observed_effects": [],
        "evidence": []
    }
    response = client.post("/v1/outcomes", json=invalid)
    assert response.status_code == 422


def test_host_rejects_offset_chronology_and_cross_subject_outcome() -> None:
    client = TestClient(create_app())
    fixture = _fixture()
    outcome = {
        "schema_version": "0.1",
        "kind": "ObservedOutcome",
        "id": "outcome-offset-invalid",
        "subject": fixture["subject"],
        "perturbation_id": fixture["perturbation"]["id"],
        "started_at": "2026-01-01T10:00:00-10:00",
        "ended_at": "2026-01-01T11:00:00+10:00",
        "observed_effects": [],
        "evidence": [],
    }
    assert client.post("/v1/outcomes", json=outcome).status_code == 422

    outcome["id"] = "outcome-wrong-subject"
    outcome["subject"] = "subject:other"
    outcome["started_at"] = "2026-01-01T10:00:00Z"
    outcome["ended_at"] = "2026-01-01T11:00:00Z"
    assert client.post("/v1/outcomes", json=outcome).status_code == 422


def test_calibration_requires_bound_scenario_and_outcome() -> None:
    calibration = {
        "schema_version": "0.1",
        "kind": "CalibrationEvent",
        "id": "calibration-unbound",
        "scenario_id": "missing-scenario",
        "outcome_id": "missing-outcome",
        "generated_at": "2026-08-10T12:00:00Z",
        "absolute_errors": {},
        "within_predicted_interval": {},
    }
    response = TestClient(create_app()).post("/v1/calibrations", json=calibration)
    assert response.status_code == 422


def test_reference_client_validates_subsystem_response() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"coordinate": "not-an-openbody-coordinate"})

    with OpenBodyClient("http://openbody.test", transport=httpx.MockTransport(handler)) as client:
        try:
            client.subsystem_state("ob://human/metabolic/glucose_regulation")
        except Exception:
            pass
        else:
            raise AssertionError("invalid subsystem response was trusted")


def test_host_exposes_valid_fixture_model() -> None:
    models = TestClient(create_app()).get("/v1/models")
    assert models.status_code == 200
    assert len(models.json()) == 1
    validate_definition("BodyModel", models.json()[0])
