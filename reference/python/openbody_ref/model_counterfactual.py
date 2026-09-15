"""Qualified simulations; no intervention execution authority is created here."""
from copy import deepcopy
import json
from types import SimpleNamespace
from uuid import uuid4

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from .model_family import (PROFILE, SCHEMA, CounterfactualEvaluation, ModelEvaluation,
                           QualifiedModelRuntime, finite, require)
from .model_forecast import build_forecast, forecast_output, unknown_uncertainty, validate_forecast
from .validation import SCHEMA as CORE_SCHEMA, canonical_digest, semantic_validate

COUNTERFACTUAL_VALIDATOR = Draft202012Validator(
    SCHEMA["$defs"]["CounterfactualResult"], format_checker=FormatChecker(),
    registry=Registry().with_resources([(schema["$id"], Resource.from_contents(schema)) for schema in (CORE_SCHEMA, SCHEMA)]),
)


def validate_perturbation_request(contract, requested):
    permitted = next((row for row in contract["counterfactual"]["perturbations"] if row["id"] == requested["id"]), None)
    require(permitted is not None, "unsupported_perturbation", "Perturbation is not covered by model qualification")
    bounds = {row["name"]: row for row in permitted["parameters"]}
    require(set(requested["parameters"]) == set(bounds), "unsupported_perturbation", "Perturbation parameters differ from the qualified envelope")
    require(all(finite(value) and bounds[name]["minimum"] <= value <= bounds[name]["maximum"]
                for name, value in requested["parameters"].items()), "unsupported_perturbation", "Perturbation dose exceeds the qualified envelope")
    return permitted


def execution_perturbation(contract, requested, origin):
    permitted = validate_perturbation_request(contract, requested)
    return {"id": permitted["id"], "class": permitted["class"], "scope": permitted["scope"],
            "parameters": deepcopy(requested["parameters"]), "starts_at": origin.isoformat().replace("+00:00", "Z")}


def counterfactual_output(value):
    result = deepcopy(value)
    result["scenario"].pop("model_receipts")
    return result


def _bind_scenario(forecast, scenario_id):
    for state in forecast["trajectory"]["states"]:
        for evidence in state["evidence"] + state["subsystems"][0]["evidence"]:
            if scenario_id not in evidence["claim_refs"]:
                evidence["claim_refs"].append(scenario_id)
    forecast["trajectory"]["model_receipts"][0]["output_digest"] = canonical_digest(forecast_output(forecast))


def _validate_uncertainty(contract, metrics, uncertainty):
    QualifiedModelRuntime._validate_evaluation(SimpleNamespace(contract=contract), ModelEvaluation(metrics, uncertainty))


def build_counterfactual(runtime, model, request, inputs, parameters, evaluation, lease, origin, perturbation):
    require(isinstance(evaluation, CounterfactualEvaluation), "invalid_output", "Counterfactual model returned another result type")
    now = runtime._clock().isoformat().replace("+00:00", "Z")
    control = build_forecast(runtime, model, request, inputs, parameters, evaluation.control, lease, origin, generated_at=now)
    intervention = build_forecast(runtime, model, request, inputs, parameters, evaluation.intervention, lease, origin, generated_at=now)
    require(evaluation.control.points[0].evaluation == evaluation.intervention.points[0].evaluation,
            "invalid_output", "Control and intervention must share the state before perturbation")
    require([point.offset_seconds for point in evaluation.control.points] == [point.offset_seconds for point in evaluation.intervention.points],
            "invalid_output", "Control and intervention must use the same time points")
    metrics = control["trajectory"]["states"][0]["subsystems"][0]["state_vector"]
    _validate_uncertainty(model.contract, metrics, evaluation.uncertainty)
    effect_bounds = {row["name"]: row for row in model.contract["counterfactual"]["effect_bounds"]}
    require(set(evaluation.effect_uncertainty) == set(effect_bounds), "invalid_output", "Every effect needs its declared uncertainty")
    for uncertainty in evaluation.effect_uncertainty.values():
        _validate_uncertainty(model.contract, metrics, uncertainty)
    require(type(evaluation.assumptions) in (tuple, list) and len(evaluation.assumptions) <= 64 and
            all(isinstance(item, str) and 0 < len(item) <= 2048 for item in evaluation.assumptions),
            "invalid_output", "Counterfactual assumptions exceed their bounds")
    unknown = any(runtime._unknown(value) for value in [evaluation.uncertainty, *evaluation.effect_uncertainty.values(),
        control["trajectory"]["uncertainty"], intervention["trajectory"]["uncertainty"]])
    identity = "model-counterfactual:" + str(uuid4())
    for forecast in (control, intervention):
        _bind_scenario(forecast, identity)
    baseline_state = deepcopy(control["trajectory"]["states"][0])
    baseline = {"id": identity + ":baseline", "trajectory_kind": "expected", "generated_at": now,
                "states": [baseline_state], "uncertainty": deepcopy(baseline_state["uncertainty"]),
                "assumptions": ["Model-estimated state at perturbation start"],
                "model_receipts": deepcopy(baseline_state["model_receipts"])}
    predicted = deepcopy(intervention["trajectory"])
    predicted["trajectory_kind"] = "intervention"
    control_final = control["trajectory"]["states"][-1]["subsystems"][0]["state_vector"]
    intervention_final = predicted["states"][-1]["subsystems"][0]["state_vector"]
    effects = []
    for metric, bounds in effect_bounds.items():
        delta = intervention_final[metric] - control_final[metric]
        require(finite(delta) and bounds["minimum"] <= delta <= bounds["maximum"], "invalid_output", "Counterfactual effect exceeds its qualified bounds")
        uncertainty = evaluation.effect_uncertainty[metric]
        effects.append({"scope": model.contract["model"]["coordinate"], "metric": metric, "delta": delta,
                        "epistemic_class": "counterfactual", "uncertainty": unknown_uncertainty(uncertainty) if unknown else deepcopy(uncertainty)})
    scenario = {"schema_version": "0.1", "kind": "CounterfactualScenario", "id": identity, "subject": request["subject"],
                "generated_at": now, "baseline": baseline, "perturbation": deepcopy(perturbation), "counterfactual": predicted,
                "disposition": "simulated", "applicability": {"mode": "qualified_model_family_counterfactual", "subject": request["subject"],
                    "scopes": [model.contract["model"]["coordinate"]], "horizon_seconds": request["horizon_seconds"],
                    "evidence_boundary": "Qualification for " + request["purpose"] + ": " + canonical_digest(model.contract), "generalizable": False},
                "evidence": deepcopy(baseline_state["evidence"]), "expected_effects": effects,
                "assumptions": list(evaluation.assumptions), "uncertainty": unknown_uncertainty(evaluation.uncertainty) if unknown else deepcopy(evaluation.uncertainty),
                "model_receipts": []}
    result = {"profile": PROFILE, "schema_version": "0.1", "kind": "ModelCounterfactual", "id": identity,
              "subject": request["subject"], "generated_at": now, "forecast_origin": control["forecast_origin"],
              "horizon_seconds": request["horizon_seconds"], "contract_digest": canonical_digest(model.contract),
              "request_digest": canonical_digest(request), "qualification_valid_until": control["qualification_valid_until"],
              "execution_context": deepcopy(control["execution_context"]),
              "scenario": scenario, "comparison_forecast": control}
    receipt = deepcopy(control["trajectory"]["model_receipts"][0])
    receipt["execution_id"] = identity
    receipt["output_digest"] = canonical_digest(counterfactual_output(result))
    scenario["model_receipts"] = [receipt]
    validate_counterfactual(result, model.contract, request["subject"], request=request)
    return result


def validate_counterfactual(value, contract, subject, *, request=None):
    COUNTERFACTUAL_VALIDATOR.validate(value)
    require("counterfactual" in contract, "invalid_output", "A forecast contract cannot qualify a counterfactual")
    require(value["subject"] == subject and value["contract_digest"] == canonical_digest(contract), "invalid_output", "Counterfactual subject or contract differs")
    require(len(json.dumps(value, allow_nan=False).encode()) <= 12 * 1024 * 1024, "invalid_output", "Counterfactual output exceeds its size bound")
    control = value["comparison_forecast"]
    validate_forecast(control, contract, subject, request=request)
    header = ("subject", "generated_at", "forecast_origin", "horizon_seconds", "contract_digest", "request_digest", "qualification_valid_until", "execution_context")
    require(all(value[key] == control[key] for key in header), "invalid_output", "Counterfactual and comparison execution bindings differ")
    scenario = value["scenario"]
    semantic_validate(scenario)
    require(scenario["id"] == value["id"] and scenario["subject"] == subject and scenario["generated_at"] == value["generated_at"] and
            scenario["disposition"] == "simulated" and "abstention" not in scenario, "invalid_output", "Counterfactual scenario differs from execution")
    perturbation = scenario["perturbation"]
    require(set(perturbation) == {"id", "class", "scope", "parameters", "starts_at"} and perturbation["starts_at"] == value["forecast_origin"],
            "invalid_output", "Simulation cannot carry action authority or unqualified timing")
    selected = {"id": perturbation["id"], "parameters": perturbation["parameters"]}
    permitted = validate_perturbation_request(contract, selected)
    require(perturbation["class"] == permitted["class"] and perturbation["scope"] == permitted["scope"], "invalid_output", "Perturbation scope or class differs from qualification")
    if request is not None:
        require(request["perturbation"] == selected, "invalid_output", "Returned perturbation differs from request")
    predicted = scenario["counterfactual"]
    require(predicted["trajectory_kind"] == "intervention", "invalid_output", "Counterfactual trajectory must be an intervention projection")
    arm = {key: deepcopy(item) for key, item in control.items() if key != "trajectory"}
    arm["id"] = predicted["id"]
    arm["trajectory"] = deepcopy(predicted)
    arm["trajectory"]["trajectory_kind"] = "predicted"
    validate_forecast(arm, contract, subject, request=request)
    control_states, intervention_states = control["trajectory"]["states"], predicted["states"]
    require(control["id"] != predicted["id"] and not ({state["id"] for state in control_states} & {state["id"] for state in intervention_states}),
            "invalid_output", "Control and intervention must have distinct execution identities")
    require([state["state_time"] for state in control_states] == [state["state_time"] for state in intervention_states],
            "invalid_output", "Control and intervention time grids differ")
    first = control_states[0]
    def source_fields(state):
        return [{key: item for key, item in evidence.items() if key != "claim_refs"} for evidence in state["evidence"]]
    require(source_fields(first) == source_fields(intervention_states[0]), "invalid_output", "Control and intervention source evidence differs")
    require(first["subsystems"][0]["state_vector"] == intervention_states[0]["subsystems"][0]["state_vector"] and
            first["uncertainty"] == intervention_states[0]["uncertainty"], "invalid_output", "Initial states differ before perturbation")
    baseline = scenario["baseline"]
    require(baseline["states"] == [first] and baseline["trajectory_kind"] == "expected" and baseline["generated_at"] == value["generated_at"] and
            baseline["model_receipts"] == first["model_receipts"] and baseline["uncertainty"] == first["uncertainty"],
            "invalid_output", "Scenario baseline is not the shared initial estimate")
    bounds = {row["name"]: row for row in contract["counterfactual"]["effect_bounds"]}
    effects = scenario["expected_effects"]
    require(len(effects) == len(bounds) and {row["metric"] for row in effects} == set(bounds), "invalid_output", "Scenario effects differ from the qualified metrics")
    metrics = first["subsystems"][0]["state_vector"]
    unknown = any(QualifiedModelRuntime._unknown(u) for u in [control["trajectory"]["uncertainty"], predicted["uncertainty"],
        scenario["uncertainty"], *[effect["uncertainty"] for effect in effects]])
    for effect in effects:
        metric = effect["metric"]
        delta = intervention_states[-1]["subsystems"][0]["state_vector"][metric] - control_states[-1]["subsystems"][0]["state_vector"][metric]
        require(effect["scope"] == contract["model"]["coordinate"] and effect["epistemic_class"] == "counterfactual" and
                finite(effect["delta"]) and effect["delta"] == delta and bounds[metric]["minimum"] <= delta <= bounds[metric]["maximum"],
                "invalid_output", "Counterfactual effect is not the bounded same-horizon difference")
        _validate_uncertainty(contract, metrics, effect["uncertainty"])
    _validate_uncertainty(contract, metrics, scenario["uncertainty"])
    if unknown:
        require(all(all(u[key] is None for key in ("epistemic", "aleatoric", "coverage")) and u["out_of_distribution"] == "unknown"
                    for u in [scenario["uncertainty"], *[effect["uncertainty"] for effect in effects]]), "invalid_output", "Counterfactual quantifies unknown uncertainty")
    require(scenario["evidence"] == first["evidence"] and scenario["applicability"] == {
        "mode": "qualified_model_family_counterfactual", "subject": subject, "scopes": [contract["model"]["coordinate"]],
        "horizon_seconds": value["horizon_seconds"], "evidence_boundary": "Qualification for " + value["execution_context"]["purpose"] + ": " + canonical_digest(contract), "generalizable": False},
        "invalid_output", "Scenario applicability or evidence exceeds its qualification")
    require(len(scenario["assumptions"]) <= 64 and all(0 < len(item) <= 2048 for item in scenario["assumptions"]), "invalid_output", "Scenario assumptions exceed their bounds")
    expected = deepcopy(control["trajectory"]["model_receipts"][0])
    expected["execution_id"] = value["id"]
    expected["output_digest"] = canonical_digest(counterfactual_output(value))
    require(scenario["model_receipts"] == [expected], "invalid_output", "Counterfactual receipt does not bind the complete comparison")
    for key in ("input_digest", "environment_digest", "validation_ref", "executed_at"):
        require(predicted["model_receipts"][0][key] == expected[key], "invalid_output", "Intervention and control qualification or inputs differ")
    return value
