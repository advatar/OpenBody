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
        "authorization": {"schemes": []},
    }


def _abstention(reason_code: str, reason: str) -> dict[str, Any]:
    value = json.loads(ABSTENTION_FIXTURE.read_text())
    value["reason_code"] = reason_code
    value["reasons"] = [reason, "No counterfactual effect was generated"]
    semantic_validate(value)
    return value


def _reference_simulate(store: InMemoryTwinStore, request: dict[str, Any]) -> dict[str, Any]:
    allowed_fields = {"state", "perturbation", "horizon_seconds", "requested_scopes", "authority_ref"}
    unexpected_fields = set(request) - allowed_fields
    if unexpected_fields:
        raise ValueError(f"unsupported simulation request fields: {sorted(unexpected_fields)}")
    validate_definition("BodyState", request.get("state"))
    validate_definition("Perturbation", request.get("perturbation"))
    horizon = request.get("horizon_seconds")
    if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon < 1:
        raise ValueError("horizon_seconds must be a positive integer")

    candidate = next(iter(store.scenarios.values()), None)
    if candidate is None:
        return _abstention("model_unavailable", "No reference scenario is available")

    baseline_state = candidate["baseline"]["states"][0]
    if request["state"] != baseline_state:
        return _abstention(
            "out_of_distribution",
            "The deterministic reference provider only supports its exact bundled baseline state and subject",
        )

    requested = request["perturbation"]
    declared = candidate["perturbation"]
    if requested != declared:
        return _abstention(
            "unsupported_perturbation",
            "The deterministic reference provider only supports the exact bundled perturbation",
        )

    model = store.models.get(candidate["model_receipts"][0]["model_id"])
    supported_horizon = model.get("applicability", {}).get("horizon_seconds") if model else None
    if horizon != supported_horizon:
        return _abstention(
            "out_of_distribution",
            f"The deterministic reference provider only supports a {supported_horizon}-second horizon",
        )

    requested_scopes = request.get("requested_scopes", [])
    if not isinstance(requested_scopes, list):
        raise ValueError("requested_scopes must be an array")
    for scope in requested_scopes:
        validate_definition("Coordinate", scope)
    supported_scopes = {effect["scope"] for effect in candidate["expected_effects"]}
    if not set(requested_scopes).issubset(supported_scopes):
        return _abstention("unsupported_scope", "One or more requested output scopes are unsupported")

    if request.get("authority_ref") is not None:
        return _abstention(
            "authorization_required",
            "The reference provider cannot validate external authority references",
        )

    result = copy.deepcopy(candidate)
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
                validate_definition("BodySubsystemState", subsystem)
                return subsystem
        raise HTTPException(status_code=404, detail="OpenBody coordinate not present in current state")

    @app.get("/v1/models")
    def list_models() -> list[dict[str, Any]]:
        models = list(store.models.values())
        for model in models:
            validate_definition("BodyModel", model)
        return models

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

    @app.post("/v1/outcomes", status_code=202)
    def record_outcome(value: dict[str, Any]) -> dict[str, Any]:
        try:
            store.put_outcome(value)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return value

    @app.post("/v1/calibrations", status_code=202)
    def record_calibration(value: dict[str, Any]) -> dict[str, Any]:
        try:
            store.put_calibration(value)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return value

    return app


app = create_app()
