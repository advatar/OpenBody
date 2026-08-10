from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException

from .store import InMemoryTwinStore
from .validation import semantic_validate, validate_definition

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FIXTURE = ROOT / "examples" / "post-meal-walk.scenario.json"
ABSTENTION_FIXTURE = ROOT / "examples" / "insufficient-evidence.abstention.json"


def _capabilities() -> dict[str, Any]:
    return {
        "protocol": "openbody",
        "versions": ["0.1"],
        "capabilities": [
            "state.read",
            "models.discover",
            "simulation.execute",
            "simulation.read",
            "outcomes.write",
            "calibrations.write",
        ],
        "authorization": {"schemes": ["oauth2", "oidc", "mandamus"]},
    }


def _reference_simulate(store: InMemoryTwinStore, request: dict[str, Any]) -> dict[str, Any]:
    validate_definition("BodyState", request.get("state"))
    validate_definition("Perturbation", request.get("perturbation"))
    horizon = request.get("horizon_seconds")
    if not isinstance(horizon, int) or horizon < 1:
        raise ValueError("horizon_seconds must be a positive integer")

    candidate = next(iter(store.scenarios.values()), None)
    if candidate is None:
        return json.loads(ABSTENTION_FIXTURE.read_text())

    requested = request["perturbation"]
    declared = candidate["perturbation"]
    same_capability = (
        requested.get("id") == declared.get("id")
        and requested.get("class") == declared.get("class")
        and requested.get("scope") == declared.get("scope")
        and requested.get("parameters") == declared.get("parameters")
    )
    if not same_capability:
        return json.loads(ABSTENTION_FIXTURE.read_text())

    result = copy.deepcopy(candidate)
    result["baseline"] = copy.deepcopy(request["state"] and candidate["baseline"])
    result["baseline"]["states"][0] = copy.deepcopy(request["state"])
    result["subject"] = request["state"]["subject"]
    result["perturbation"] = copy.deepcopy(requested)
    semantic_validate(result)
    return result


def create_app(store: InMemoryTwinStore | None = None) -> FastAPI:
    store = store or InMemoryTwinStore.from_fixture(DEFAULT_FIXTURE)
    app = FastAPI(title="OpenBody Reference Host", version="0.1.0-draft.1")

    @app.get("/.well-known/openbody")
    def well_known() -> dict[str, Any]:
        return _capabilities() | {"base_url": "/v1"}

    @app.get("/v1/capabilities")
    def capabilities() -> dict[str, Any]:
        return _capabilities()

    @app.get("/v1/state")
    def get_state() -> dict[str, Any]:
        semantic_validate(store.state)
        return store.state

    @app.get("/v1/state/{coordinate:path}")
    def get_subsystem_state(coordinate: str) -> dict[str, Any]:
        normalized = coordinate if coordinate.startswith("ob://") else f"ob://{coordinate}"
        for subsystem in store.state.get("subsystems", []):
            if subsystem.get("coordinate") == normalized:
                return subsystem
        raise HTTPException(status_code=404, detail="OpenBody coordinate not present in current state")

    @app.get("/v1/models")
    def list_models() -> list[dict[str, Any]]:
        return list(store.models.values())

    @app.get("/v1/models/{model_id}")
    def get_model(model_id: str) -> dict[str, Any]:
        model = store.models.get(model_id)
        if model is None:
            raise HTTPException(status_code=404, detail="model not found")
        semantic_validate(model)
        return model

    @app.get("/v1/trajectories/{trajectory_id}")
    def get_trajectory(trajectory_id: str) -> dict[str, Any]:
        trajectory = store.trajectories.get(trajectory_id)
        if trajectory is None:
            raise HTTPException(status_code=404, detail="trajectory not found")
        validate_definition("BodyTrajectory", trajectory)
        return trajectory

    @app.post("/v1/simulations")
    def simulate(request: dict[str, Any]) -> dict[str, Any]:
        try:
            result = _reference_simulate(store, request)
            semantic_validate(result)
            return result
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/v1/simulations/{scenario_id}")
    def get_simulation(scenario_id: str) -> dict[str, Any]:
        scenario = store.scenarios.get(scenario_id)
        if scenario is None:
            raise HTTPException(status_code=404, detail="scenario not found")
        semantic_validate(scenario)
        return scenario

    @app.post("/v1/outcomes", status_code=201)
    def record_outcome(value: dict[str, Any]) -> dict[str, Any]:
        try:
            store.put_outcome(value)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return value

    @app.post("/v1/calibrations", status_code=201)
    def record_calibration(value: dict[str, Any]) -> dict[str, Any]:
        try:
            store.put_calibration(value)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return value

    return app


app = create_app()
