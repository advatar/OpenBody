from __future__ import annotations

import json
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from openbody_ref.client import OpenBodyClient
from openbody_ref.host import ROOT, create_app


def test_reference_host_serves_valid_state_and_simulation() -> None:
    app = create_app()
    test_client = TestClient(app)
    assert test_client.get("/.well-known/openbody").status_code == 200
    state = test_client.get("/v1/state")
    assert state.status_code == 200
    assert state.json()["kind"] == "BodyState"

    fixture = json.loads((ROOT / "examples" / "post-meal-walk.scenario.json").read_text())
    scenario_id = fixture["id"]
    scenario = test_client.get(f"/v1/simulations/{scenario_id}")
    assert scenario.status_code == 200
    assert scenario.json()["disposition"] == "simulated"


def test_reference_client_validates_server_objects() -> None:
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    # ASGITransport is async-only in httpx 0.28, so exercise the sync client with MockTransport.
    test_client = TestClient(app)

    def handler(request: httpx.Request) -> httpx.Response:
        response = test_client.request(request.method, request.url.raw_path.decode(), content=request.content)
        return httpx.Response(response.status_code, headers=response.headers, content=response.content)

    with OpenBodyClient("http://openbody.test", transport=httpx.MockTransport(handler)) as client:
        assert "state.read" in client.capabilities()["capabilities"]
        assert client.state()["kind"] == "BodyState"


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
