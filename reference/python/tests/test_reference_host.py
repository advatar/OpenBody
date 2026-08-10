from __future__ import annotations

import json

import httpx
from fastapi.testclient import TestClient

from openbody_ref.client import OpenBodyClient
from openbody_ref.host import ROOT, create_app


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
    assert result["reason_code"] == "insufficient_evidence"


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
