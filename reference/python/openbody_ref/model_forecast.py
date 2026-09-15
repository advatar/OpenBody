"""Bounded forecast construction and verification using frozen core trajectories."""
from copy import deepcopy
from datetime import timedelta
import json
from types import SimpleNamespace
from uuid import uuid4

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from .model_family import (PROFILE, SCHEMA, ForecastEvaluation, ForecastPoint,
                           ModelEvaluation, require)
from .validation import SCHEMA as CORE_SCHEMA, canonical_digest, parse_timestamp

FORECAST_VALIDATOR = Draft202012Validator(
    SCHEMA["$defs"]["ForecastResult"], format_checker=FormatChecker(),
    registry=Registry().with_resource(CORE_SCHEMA["$id"], Resource.from_contents(CORE_SCHEMA)),
)
MAX_FORECAST_STATE_BYTES = 8 * 1024 * 1024


def forecast_output(value):
    """Digest all forecast times and nested states, excluding the aggregate receipt."""
    trajectory = value["trajectory"]
    return {"forecast_origin": value["forecast_origin"], "horizon_seconds": value["horizon_seconds"],
            "request_digest": value["request_digest"], "qualification_valid_until": value["qualification_valid_until"],
            "execution_context": value["execution_context"],
            "states": trajectory["states"], "uncertainty": trajectory["uncertainty"],
            "assumptions": trajectory["assumptions"]}


def unknown_uncertainty(value):
    return {"epistemic": None, "aleatoric": None, "coverage": None, "out_of_distribution": "unknown",
            "reasons": value["reasons"] + ["Forecast evidence or point uncertainty is unknown; aggregate uncertainty is not quantified"]}


def build_forecast(runtime, model, request, inputs, parameters, evaluation, lease, origin, *, generated_at=None):
    require(isinstance(evaluation, ForecastEvaluation), "invalid_output", "Forecast model returned another result type")
    require(type(evaluation.points) in (tuple, list) and 2 <= len(evaluation.points) <= 512,
            "invalid_output", "A forecast requires 2 to 512 bounded time points")
    offsets = []
    for point in evaluation.points:
        require(isinstance(point, ForecastPoint) and type(point.offset_seconds) is int, "invalid_output", "Invalid forecast point")
        offsets.append(point.offset_seconds)
        runtime._validate_evaluation(model, point.evaluation)
    require(offsets[0] == 0 and offsets[-1] == request["horizon_seconds"] and
            all(left < right for left, right in zip(offsets, offsets[1:])),
            "invalid_output", "Forecast points must increase from zero to the exact qualified horizon")
    runtime._validate_evaluation(model, ModelEvaluation(evaluation.points[0].evaluation.metrics, evaluation.uncertainty))
    require(type(evaluation.assumptions) in (tuple, list) and len(evaluation.assumptions) <= 64 and
            all(isinstance(item, str) and 0 < len(item) <= 2048 for item in evaluation.assumptions),
            "invalid_output", "Forecast assumptions exceed the output boundary")
    now = generated_at or runtime._clock().isoformat().replace("+00:00", "Z")
    states, state_bytes = [], 0
    for point in evaluation.points:
        state = runtime._state(model, request, inputs, parameters, point.evaluation, lease,
                               state_time=(origin + timedelta(seconds=point.offset_seconds)).isoformat().replace("+00:00", "Z"),
                               generated_at=now)
        state_bytes += len(json.dumps(state, allow_nan=False).encode())
        require(state_bytes <= MAX_FORECAST_STATE_BYTES, "invalid_output", "Forecast states exceed their aggregate size bound")
        states.append(state)
    uncertainty = deepcopy(evaluation.uncertainty)
    if any(runtime._unknown(state["uncertainty"]) for state in states):
        uncertainty = unknown_uncertainty(uncertainty)
    identity = "model-forecast:" + str(uuid4())
    result = {"profile": PROFILE, "schema_version": "0.1", "kind": "ModelForecast", "id": identity,
              "subject": request["subject"], "generated_at": now, "forecast_origin": origin.isoformat().replace("+00:00", "Z"),
              "horizon_seconds": request["horizon_seconds"], "contract_digest": canonical_digest(model.contract),
              "request_digest": canonical_digest(request),
              "execution_context": {key: request[key] for key in ("purpose", "population", "question")},
              "qualification_valid_until": lease.valid_until.isoformat().replace("+00:00", "Z"),
              "trajectory": {"id": identity, "trajectory_kind": "predicted", "generated_at": now, "states": states,
                             "uncertainty": uncertainty, "assumptions": list(evaluation.assumptions), "model_receipts": []}}
    receipt = deepcopy(states[0]["model_receipts"][0])
    receipt["execution_id"] = identity
    receipt["output_digest"] = canonical_digest(forecast_output(result))
    result["trajectory"]["model_receipts"] = [receipt]
    validate_forecast(result, model.contract, request["subject"], request=request)
    return result


def validate_forecast(value, contract, subject, *, request=None):
    from .client import OpenBodyClient
    from .model_family import QualifiedModelRuntime
    FORECAST_VALIDATOR.validate(value)
    require(value["subject"] == subject and value["contract_digest"] == canonical_digest(contract),
            "invalid_output", "Forecast subject or contract differs from request")
    require(type(value["horizon_seconds"]) is int and value["horizon_seconds"] > 0 and
            value["horizon_seconds"] in contract["prediction_horizon_seconds"],
            "invalid_output", "Forecast horizon exceeds the model contract")
    require(all(value["execution_context"][key] in contract[allowed] for key, allowed in
                (("purpose", "context_of_use"), ("population", "supported_population"), ("question", "supported_question"))),
            "invalid_output", "Forecast execution context exceeds qualification")
    if request is not None:
        require(value["request_digest"] == canonical_digest(request) and value["horizon_seconds"] == request["horizon_seconds"],
                "invalid_output", "Forecast does not bind the exact execution request")
        require(all(value["execution_context"][key] == request[key] for key in value["execution_context"]),
                "invalid_output", "Forecast context differs from request")
    trajectory = value["trajectory"]
    require(trajectory["id"] == value["id"] and trajectory["trajectory_kind"] == "predicted" and
            trajectory["generated_at"] == value["generated_at"] and 2 <= len(trajectory["states"]) <= 512 and
            len(trajectory["model_receipts"]) == 1, "invalid_output", "Forecast trajectory exceeds its boundary")
    origin = parse_timestamp(value["forecast_origin"])
    generated = parse_timestamp(value["generated_at"])
    require(origin <= generated, "invalid_output", "Forecast origin is after execution")
    require(generated < parse_timestamp(value["qualification_valid_until"]), "invalid_output", "Forecast qualification had expired at execution")
    times = [parse_timestamp(state["state_time"]) for state in trajectory["states"]]
    require(generated < times[-1], "invalid_output", "Execution finished after the forecast horizon")
    require(len(json.dumps(trajectory["states"], allow_nan=False).encode()) <= MAX_FORECAST_STATE_BYTES + 1024,
            "invalid_output", "Forecast states exceed their aggregate size bound")
    require(times[0] == origin and times[-1] == origin + timedelta(seconds=value["horizon_seconds"]) and
            all(a < b for a, b in zip(times, times[1:])) and
            all((time - origin).total_seconds().is_integer() for time in times),
            "invalid_output", "Forecast time points do not match its exact horizon")
    require(len({state["id"] for state in trajectory["states"]}) == len(times), "invalid_output", "Forecast contains replayed states")
    for state in trajectory["states"]:
        OpenBodyClient._checked_model_state(state, contract, subject)
        QualifiedModelRuntime._validate_evaluation(SimpleNamespace(contract=contract),
            ModelEvaluation(state["subsystems"][0]["state_vector"], state["uncertainty"]))
        require(state["generated_at"] == value["generated_at"], "invalid_output", "Forecast state execution time differs")
        require("valid_until" not in state, "invalid_output", "Forecast qualification expiry must remain separate from physiological time")
    first = trajectory["states"][0]
    aggregate = trajectory["model_receipts"][0]
    expected = deepcopy(first["model_receipts"][0])
    expected["execution_id"] = value["id"]
    expected["output_digest"] = canonical_digest(forecast_output(value))
    require(aggregate == expected, "invalid_output", "Forecast receipt does not bind its complete trajectory")
    # Every point must describe the same execution inputs and qualification;
    # output-specific IDs/digests and claim references may legitimately differ.
    common_keys = ("input_digest", "environment_digest", "validation_ref", "executed_at")
    evidence_inputs = None
    for state in trajectory["states"]:
        receipt = state["model_receipts"][0]
        require(all(receipt[key] == aggregate[key] for key in common_keys), "invalid_output", "Forecast points differ in inputs or qualification")
        sources = [{key: item for key, item in evidence.items() if key != "claim_refs"} for evidence in state["evidence"]]
        require(evidence_inputs is None or sources == evidence_inputs, "invalid_output", "Forecast points differ in source evidence")
        evidence_inputs = sources
    # Reuse the finite numeric / OOD checks for the aggregate uncertainty.
    QualifiedModelRuntime._validate_evaluation(SimpleNamespace(contract=contract),
        ModelEvaluation(first["subsystems"][0]["state_vector"], trajectory["uncertainty"]))
    if any(QualifiedModelRuntime._unknown(state["uncertainty"]) for state in trajectory["states"]):
        u = trajectory["uncertainty"]
        require(all(u[key] is None for key in ("epistemic", "aleatoric", "coverage")) and u["out_of_distribution"] == "unknown",
                "invalid_output", "Forecast aggregate quantifies unknown point uncertainty")
    require(len(trajectory["assumptions"]) <= 64 and all(0 < len(item) <= 2048 for item in trajectory["assumptions"]),
            "invalid_output", "Forecast assumptions exceed their bounds")
    return value
