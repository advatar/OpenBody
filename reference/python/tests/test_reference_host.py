from __future__ import annotations

import json
from copy import deepcopy

import httpx
import pytest
from fastapi.testclient import TestClient

from openbody_ref.client import OpenBodyClient
from openbody_ref.host import ROOT, create_app
from openbody_ref.store import InMemoryTwinStore
from openbody_ref.validation import semantic_validate, validate_definition


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
        result = client.simulate(
            state,
            fixture["perturbation"],
            horizon_seconds=7_200,
            requested_scopes=[fixture["perturbation"]["scope"]],
        )
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
        "requested_scopes": [fixture["perturbation"]["scope"]],
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
        json={
            "state": state,
            "perturbation": fixture["perturbation"],
            "horizon_seconds": 7_200,
            "requested_scopes": [fixture["perturbation"]["scope"]],
        },
    )
    assert response.status_code == 200
    assert response.json()["reason_code"] == "out_of_distribution"


def test_simulation_abstains_for_unsupported_horizon_and_scope() -> None:
    fixture = _fixture()
    request = {
        "state": fixture["baseline"]["states"][0],
        "perturbation": fixture["perturbation"],
        "horizon_seconds": 1,
        "requested_scopes": [fixture["perturbation"]["scope"]],
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
        "requested_scopes": [fixture["perturbation"]["scope"]],
    }
    assert TestClient(create_app()).post("/v1/simulations", json=request).status_code == 422

    request["horizon_seconds"] = 7_200
    request["perturbation"] = fixture["perturbation"] | {"starts_at": "2099-01-01T00:00:00Z"}
    response = TestClient(create_app()).post("/v1/simulations", json=request)
    assert response.status_code == 200
    assert response.json()["reason_code"] == "unsupported_perturbation"


def test_simulation_requires_explicit_nonempty_scopes() -> None:
    fixture = _fixture()
    request = {
        "state": fixture["baseline"]["states"][0],
        "perturbation": fixture["perturbation"],
        "horizon_seconds": 7_200,
    }
    assert TestClient(create_app()).post("/v1/simulations", json=request).status_code == 422
    request["requested_scopes"] = []
    assert TestClient(create_app()).post("/v1/simulations", json=request).status_code == 422


def test_fixture_temporal_boundary_must_match_returned_trajectory(tmp_path) -> None:
    fixture = _fixture()
    fixture["applicability"]["horizon_seconds"] = 1
    path = tmp_path / "hostile-scenario.json"
    path.write_text(json.dumps(fixture))
    with pytest.raises(ValueError, match="horizon"):
        InMemoryTwinStore.from_fixture(path)


def test_fixture_registers_receipt_found_only_on_baseline_trajectory(tmp_path) -> None:
    fixture = _fixture()
    receipt = deepcopy(fixture["model_receipts"][0])
    receipt["model_id"] = "baseline-trajectory-only"
    receipt["execution_id"] = "exec-baseline-only"
    fixture["baseline"]["model_receipts"].append(receipt)
    fixture["evidence"][0]["model_refs"].append(receipt["model_id"])
    path = tmp_path / "baseline-receipt-scenario.json"
    path.write_text(json.dumps(fixture))
    client = TestClient(create_app(InMemoryTwinStore.from_fixture(path)))
    model = client.get(f"/v1/models/{receipt['model_id']}")
    assert model.status_code == 200
    assert model.json()["version"] == receipt["model_version"]
    assert model.json()["family"] == receipt["family"]


def test_counterfactual_cannot_contain_unrequested_subsystem_scope() -> None:
    fixture = _fixture()
    subsystem = deepcopy(fixture["counterfactual"]["states"][0]["subsystems"][0])
    subsystem["coordinate"] = "ob://human/cardiovascular/heart"
    fixture["counterfactual"]["states"][0]["subsystems"].append(subsystem)
    with pytest.raises(ValueError, match="output scopes"):
        semantic_validate(fixture)

    store = InMemoryTwinStore.from_fixture(ROOT / "examples" / "post-meal-walk.scenario.json")
    store.scenarios[fixture["id"]] = fixture
    response = TestClient(create_app(store)).post(
        "/v1/simulations",
        json={
            "state": fixture["baseline"]["states"][0],
            "perturbation": fixture["perturbation"],
            "horizon_seconds": 7_200,
            "requested_scopes": [fixture["applicability"]["scopes"][0]],
        },
    )
    assert response.status_code == 200
    assert response.json()["reason_code"] == "insufficient_validation"


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


def test_host_rejects_outcome_before_bound_perturbation() -> None:
    fixture = _fixture()
    outcome = {
        "schema_version": "0.1",
        "kind": "ObservedOutcome",
        "id": "outcome-before-perturbation",
        "subject": fixture["subject"],
        "perturbation_id": fixture["perturbation"]["id"],
        "started_at": "2000-01-01T00:00:00Z",
        "ended_at": "2000-01-01T01:00:00Z",
        "observed_effects": [fixture["expected_effects"][0]],
        "evidence": [],
    }
    assert TestClient(create_app()).post("/v1/outcomes", json=outcome).status_code == 422


def test_outcome_must_fit_known_scenario_window() -> None:
    fixture = _fixture()
    client = TestClient(create_app())
    outcome = {
        "schema_version": "0.1",
        "kind": "ObservedOutcome",
        "id": "outcome-valid-window",
        "subject": fixture["subject"],
        "perturbation_id": fixture["perturbation"]["id"],
        "started_at": fixture["perturbation"]["starts_at"],
        "ended_at": fixture["perturbation"]["ends_at"],
        "observed_effects": [fixture["expected_effects"][0]],
        "evidence": [],
    }
    assert client.post("/v1/outcomes", json=outcome).status_code == 202

    outcome["id"] = "outcome-arbitrarily-late"
    outcome["started_at"] = "2099-01-01T00:00:00Z"
    outcome["ended_at"] = "2099-01-01T01:00:00Z"
    assert client.post("/v1/outcomes", json=outcome).status_code == 422


def test_calibration_requires_bound_scenario_and_outcome() -> None:
    calibration = {
        "schema_version": "0.1",
        "kind": "CalibrationEvent",
        "id": "calibration-unbound",
        "scenario_id": "missing-scenario",
        "outcome_id": "missing-outcome",
        "generated_at": "2026-08-10T12:00:00Z",
        "absolute_errors": {"postprandial_glucose_excursion_mgdl": 1.0},
        "within_predicted_interval": {"postprandial_glucose_excursion_mgdl": True},
    }
    response = TestClient(create_app()).post("/v1/calibrations", json=calibration)
    assert response.status_code == 422


def test_calibration_requires_matching_prediction_and_outcome_metrics() -> None:
    fixture = _fixture()
    client = TestClient(create_app())
    outcome = {
        "schema_version": "0.1",
        "kind": "ObservedOutcome",
        "id": "outcome-bound",
        "subject": fixture["subject"],
        "perturbation_id": fixture["perturbation"]["id"],
        "started_at": fixture["perturbation"]["starts_at"],
        "ended_at": fixture["perturbation"]["ends_at"],
        "observed_effects": [fixture["expected_effects"][0]],
        "evidence": [],
    }
    assert client.post("/v1/outcomes", json=outcome).status_code == 202
    calibration = {
        "schema_version": "0.1",
        "kind": "CalibrationEvent",
        "id": "calibration-mismatched-metrics",
        "scenario_id": fixture["id"],
        "outcome_id": outcome["id"],
        "generated_at": "2026-08-10T21:00:00Z",
        "absolute_errors": {"unrelated_metric": 1.0},
        "within_predicted_interval": {"different_metric": True},
    }
    assert client.post("/v1/calibrations", json=calibration).status_code == 422

    wrong_scope_outcome = deepcopy(outcome)
    wrong_scope_outcome["id"] = "outcome-wrong-scope"
    wrong_scope_outcome["observed_effects"][0]["scope"] = "ob://human/cardiovascular/heart"
    assert client.post("/v1/outcomes", json=wrong_scope_outcome).status_code == 202
    metric = fixture["expected_effects"][0]["metric"]
    calibration["id"] = "calibration-mismatched-scope"
    calibration["outcome_id"] = wrong_scope_outcome["id"]
    calibration["absolute_errors"] = {metric: 1.0}
    calibration["within_predicted_interval"] = {metric: True}
    assert client.post("/v1/calibrations", json=calibration).status_code == 422


def test_simulated_scenario_requires_applicability_boundary_and_distinct_ids() -> None:
    fixture = _fixture()
    fixture["applicability"] = {}
    with pytest.raises(Exception):
        semantic_validate(fixture)

    fixture = _fixture()
    fixture["counterfactual"]["id"] = fixture["baseline"]["id"]
    with pytest.raises(ValueError, match="trajectory ids"):
        semantic_validate(fixture)


def test_simulated_scenario_requires_bound_actual_evidence() -> None:
    fixture = _fixture()
    fixture["evidence"] = []
    fixture["applicability"]["evidence_boundary"] = "none"
    for trajectory_name in ("baseline", "counterfactual"):
        for state in fixture[trajectory_name]["states"]:
            state["evidence"] = []
            for subsystem in state["subsystems"]:
                subsystem["evidence"] = []
    with pytest.raises(Exception):
        semantic_validate(fixture)

    store = InMemoryTwinStore.from_fixture(ROOT / "examples" / "post-meal-walk.scenario.json")
    store.scenarios[fixture["id"]] = fixture
    response = TestClient(create_app(store)).post(
        "/v1/simulations",
        json={
            "state": fixture["baseline"]["states"][0],
            "perturbation": fixture["perturbation"],
            "horizon_seconds": 7_200,
            "requested_scopes": fixture["applicability"]["scopes"],
        },
    )
    assert response.status_code == 200
    assert response.json()["reason_code"] == "insufficient_evidence"


@pytest.mark.parametrize("mismatch", ["subject", "perturbation", "horizon", "scopes"])
def test_reference_client_rejects_request_inconsistent_simulation(mismatch: str) -> None:
    fixture = _fixture()
    response_value = deepcopy(fixture)
    requested_scope = fixture["applicability"]["scopes"][0]
    if mismatch == "subject":
        response_value["subject"] = "subject:other"
        response_value["applicability"]["subject"] = "subject:other"
        response_value["evidence"][0]["subject"] = "subject:other"
        for trajectory_name in ("baseline", "counterfactual"):
            for state in response_value[trajectory_name]["states"]:
                state["subject"] = "subject:other"
    elif mismatch == "perturbation":
        response_value["perturbation"]["id"] = "different-perturbation"
    elif mismatch == "horizon":
        response_value["applicability"]["horizon_seconds"] = 1
        response_value["counterfactual"]["states"][-1]["state_time"] = "2026-08-10T18:05:01Z"
    else:
        broader_scope = "ob://human/cardiovascular/heart"
        subsystem = deepcopy(response_value["counterfactual"]["states"][0]["subsystems"][0])
        subsystem["coordinate"] = broader_scope
        response_value["counterfactual"]["states"][0]["subsystems"].append(subsystem)
        effect = deepcopy(response_value["expected_effects"][0])
        effect["scope"] = broader_scope
        response_value["expected_effects"].append(effect)
        response_value["applicability"]["scopes"].append(broader_scope)
        response_value["evidence"][0]["scopes"].append(broader_scope)

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=response_value)

    with OpenBodyClient("http://openbody.test", transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="response"):
            client.simulate(
                fixture["baseline"]["states"][0],
                fixture["perturbation"],
                horizon_seconds=7_200,
                requested_scopes=[requested_scope],
            )


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
    assert {model["id"] for model in models.json()} == {
        "post-meal-walk-personal-difference",
        "twin-state-metabolic",
    }
    for model in models.json():
        validate_definition("BodyModel", model)
