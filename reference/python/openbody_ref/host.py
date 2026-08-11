from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException

from .store import InMemoryTwinStore, producing_model_requirements
from .validation import parse_timestamp, scenario_evidence_references, scenario_horizon_seconds, semantic_validate, validate_definition

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


def _producing_model_defect(store: InMemoryTwinStore, candidate: dict[str, Any]) -> tuple[str, str] | None:
    """Substantiate every producing receipt against its discoverable descriptor.

    Stored scenarios are an untrusted protocol boundary, so this runs on both the
    execute and read paths rather than only when a simulation is generated.
    """
    try:
        requirements = producing_model_requirements(candidate)
    except ValueError:
        return ("insufficient_validation", "A producing model receipt has no biological scope")
    declared_horizon = candidate["applicability"]["horizon_seconds"]
    producing_models = []
    for (model_id, model_version, family), requirement in requirements.items():
        model = store.models.get(model_id)
        if (
            model is None
            or model["version"] != model_version
            or model["family"] != family
        ):
            return ("model_unavailable", "A producing model receipt is not discoverable")
        if not requirement["capabilities"].issubset(set(model["capabilities"])):
            return ("insufficient_validation", "A producing model lacks its required capability")
        if not requirement["scopes"].issubset(set(model["scopes"])):
            return ("unsupported_scope", "A producing model does not support its receipt scopes")
        model_applicability = model.get("applicability", {})
        if (
            model_applicability.get("subject") != candidate["subject"]
            or not requirement["scopes"].issubset(set(model_applicability.get("scopes", [])))
        ):
            return (
                "insufficient_validation",
                "A producing model applicability boundary does not match its subject and receipt scopes",
            )
        producing_models.append(model)
    if not producing_models or any(
        model.get("applicability", {}).get("horizon_seconds") != declared_horizon for model in producing_models
    ):
        return ("insufficient_validation", "Producing model applicability does not match the scenario")
    return None


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
    requested_scopes = request.get("requested_scopes")
    if not isinstance(requested_scopes, list) or not requested_scopes:
        raise ValueError("requested_scopes must be a non-empty array")
    for scope in requested_scopes:
        validate_definition("Coordinate", scope)
    if len(requested_scopes) != len(set(requested_scopes)):
        raise ValueError("requested_scopes must not contain duplicates")
    requested = request["perturbation"]
    if request.get("authority_ref") is not None or requested.get("authority_ref") is not None:
        return _abstention(
            "authorization_required",
            "The reference provider cannot validate external authority references",
        )

    candidate = next(iter(store.scenarios.values()), None)
    if candidate is None:
        return _abstention("model_unavailable", "No reference scenario is available")

    baseline_state = candidate["baseline"]["states"][0]
    hosted_subject = store.state["subject"]
    if candidate["subject"] != hosted_subject or baseline_state["subject"] != hosted_subject:
        return _abstention(
            "out_of_distribution",
            "The stored scenario does not represent the hosted twin",
        )
    if request["state"] != baseline_state:
        return _abstention(
            "out_of_distribution",
            "The deterministic reference provider only supports its exact bundled baseline state and subject",
        )
    valid_until = baseline_state.get("valid_until")
    perturbation_start = parse_timestamp(candidate["perturbation"]["starts_at"])
    if parse_timestamp(baseline_state["state_time"]) > perturbation_start or (
        valid_until is not None and parse_timestamp(valid_until) < perturbation_start
    ):
        return _abstention("stale_evidence", "The baseline BodyState does not cover perturbation start")

    declared = candidate["perturbation"]
    if requested != declared:
        return _abstention(
            "unsupported_perturbation",
            "The deterministic reference provider only supports the exact bundled perturbation",
        )

    evidence = scenario_evidence_references(candidate)
    evidence_binding_fields = ("content_digest", "observed_at", "subject", "scopes", "model_refs", "claim_refs")
    if not evidence or any(not all(reference.get(field) for field in evidence_binding_fields) for reference in evidence):
        return _abstention("insufficient_evidence", "The stored scenario lacks bound, digest-addressed evidence")
    try:
        semantic_validate(candidate)
    except Exception as exc:
        reason_code = "insufficient_evidence" if "evidence" in str(exc).lower() else "insufficient_validation"
        return _abstention(reason_code, "The stored scenario does not prove its declared applicability boundary")
    declared_horizon = candidate["applicability"]["horizon_seconds"]
    derived_horizon = scenario_horizon_seconds(candidate)
    defect = _producing_model_defect(store, candidate)
    if defect is not None:
        return _abstention(*defect)
    if declared_horizon != derived_horizon:
        return _abstention("insufficient_validation", "Declared and returned trajectory horizons do not match")
    if horizon != declared_horizon:
        return _abstention(
            "out_of_distribution",
            f"The deterministic reference provider only supports a {declared_horizon}-second horizon",
        )

    supported_scopes = set(candidate["applicability"]["scopes"])
    if set(requested_scopes) != supported_scopes:
        return _abstention("unsupported_scope", "Requested output scopes must exactly match the provider boundary")

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
        try:
            semantic_validate(scenario)
            if scenario.get("disposition") == "simulated":
                if scenario["subject"] != store.state["subject"]:
                    raise ValueError("stored scenario does not represent the hosted twin")
                defect = _producing_model_defect(store, scenario)
                if defect is not None:
                    raise ValueError(defect[1])
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
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
