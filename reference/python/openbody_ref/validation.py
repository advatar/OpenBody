from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = ROOT / "schemas" / "openbody.schema.json"


def _schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text())


SCHEMA = _schema()
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())


def validate_object(value: dict[str, Any]) -> None:
    VALIDATOR.validate(value)


def validate_definition(name: str, value: Any) -> None:
    wrapper = {
        "$schema": SCHEMA["$schema"],
        "$defs": SCHEMA["$defs"],
        "$ref": f"#/$defs/{name}",
    }
    Draft202012Validator(wrapper, format_checker=FormatChecker()).validate(value)


def parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def canonical_digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def scenario_evidence_bindings(value: dict[str, Any]) -> list[tuple[dict[str, Any], set[str], set[str]]]:
    output_scopes = set(value["applicability"]["scopes"])
    all_model_ids = _receipt_model_ids(value)
    bindings = [(reference, output_scopes, all_model_ids) for reference in value.get("evidence", [])]
    for trajectory_name in ("baseline", "counterfactual"):
        trajectory = value.get(trajectory_name)
        if trajectory is None:
            continue
        trajectory_scopes = {
            subsystem["coordinate"] for state in trajectory["states"] for subsystem in state["subsystems"]
        }
        trajectory_scopes.update(
            coordinate
            for state in trajectory["states"]
            for coupling in state["couplings"]
            for coordinate in (coupling["source"], coupling["target"])
        )
        trajectory_model_ids = _receipt_model_ids(trajectory)
        bindings.extend(
            (reference, trajectory_scopes, trajectory_model_ids) for reference in trajectory.get("evidence", [])
        )
        for state in trajectory["states"]:
            state_scopes = {subsystem["coordinate"] for subsystem in state["subsystems"]}
            state_scopes.update(
                coordinate for coupling in state["couplings"] for coordinate in (coupling["source"], coupling["target"])
            )
            state_model_ids = _receipt_model_ids(state)
            bindings.extend((reference, state_scopes, state_model_ids) for reference in state["evidence"])
            for subsystem in state["subsystems"]:
                bindings.extend(
                    (reference, {subsystem["coordinate"]}, {subsystem["model_receipt"]["model_id"]})
                    for reference in subsystem["evidence"]
                )
    return bindings


def scenario_evidence_references(value: dict[str, Any]) -> list[dict[str, Any]]:
    return [reference for reference, _, _ in scenario_evidence_bindings(value)]


def scenario_horizon_seconds(value: dict[str, Any]) -> int:
    starts_at = parse_timestamp(value["perturbation"]["starts_at"])
    state_times = [parse_timestamp(state["state_time"]) for state in value["counterfactual"]["states"]]
    if state_times != sorted(state_times):
        raise ValueError("counterfactual trajectory states must be time ordered")
    horizon = (state_times[-1] - starts_at).total_seconds()
    if horizon < 1 or not horizon.is_integer():
        raise ValueError("scenario counterfactual horizon must be a positive whole number of seconds")
    return int(horizon)


def counterfactual_output_scopes(value: dict[str, Any]) -> set[str]:
    scopes = {effect["scope"] for effect in value["expected_effects"]}
    for evidence in value["evidence"]:
        scopes.update(evidence.get("scopes", []))
    for state in value["counterfactual"]["states"]:
        scopes.update(subsystem["coordinate"] for subsystem in state["subsystems"])
        for coupling in state["couplings"]:
            scopes.update((coupling["source"], coupling["target"]))
        for evidence in state["evidence"]:
            scopes.update(evidence.get("scopes", []))
        for subsystem in state["subsystems"]:
            for evidence in subsystem["evidence"]:
                scopes.update(evidence.get("scopes", []))
    return scopes


def validate_state_validity(value: dict[str, Any]) -> None:
    valid_until = value.get("valid_until")
    if valid_until is not None and parse_timestamp(valid_until) < parse_timestamp(value["state_time"]):
        raise ValueError("BodyState valid_until precedes state_time")


def _receipt_model_ids(value: Any) -> set[str]:
    if isinstance(value, dict):
        model_ids = {value["model_id"]} if {"model_id", "model_version", "execution_id"}.issubset(value) else set()
        for nested in value.values():
            model_ids.update(_receipt_model_ids(nested))
        return model_ids
    if isinstance(value, list):
        return set().union(*(_receipt_model_ids(nested) for nested in value), set())
    return set()


def semantic_validate(value: dict[str, Any]) -> None:
    validate_object(value)
    kind = value.get("kind")
    if kind == "CounterfactualScenario":
        disposition = value.get("disposition")
        receipts = value.get("model_receipts", [])
        effects = value.get("expected_effects", [])
        counterfactual = value.get("counterfactual")
        abstention = value.get("abstention")
        if disposition == "simulated":
            if not receipts or counterfactual is None or abstention is not None:
                raise ValueError("simulated scenarios require model receipt + counterfactual and no abstention")
            applicability = value["applicability"]
            if applicability["subject"] != value["subject"]:
                raise ValueError("scenario applicability subject must match scenario subject")
            output_scopes = counterfactual_output_scopes(value)
            if set(applicability["scopes"]) != output_scopes:
                raise ValueError("scenario applicability scopes must equal all counterfactual output scopes")
            if applicability["horizon_seconds"] != scenario_horizon_seconds(value):
                raise ValueError("scenario applicability horizon does not match returned trajectory")
            evidence_bindings = scenario_evidence_bindings(value)
            evidence = [reference for reference, _, _ in evidence_bindings]
            if not evidence:
                raise ValueError("simulated scenarios require actual evidence references")
            for reference in evidence:
                if not all(
                    (
                        reference.get("content_digest"),
                        reference.get("observed_at"),
                        reference.get("scopes"),
                        reference.get("model_refs"),
                        reference.get("claim_refs"),
                    )
                ):
                    raise ValueError("simulated scenario evidence must be digest-addressed and explicitly bound")
            evidence_scopes = {scope for reference in evidence for scope in reference["scopes"]}
            receipt_model_ids = _receipt_model_ids(value)
            evidence_models = {model_id for reference in evidence for model_id in reference["model_refs"]}
            if any(reference["subject"] != value["subject"] for reference in evidence):
                raise ValueError("simulated scenario evidence subject must match scenario subject")
            if any(not set(reference["scopes"]).issubset(scopes) for reference, scopes, _ in evidence_bindings):
                raise ValueError("simulated scenario evidence scopes must match their placement")
            if any(
                not set(reference["model_refs"]).issubset(producer_ids)
                for reference, _, producer_ids in evidence_bindings
            ):
                raise ValueError("simulated scenario evidence must bind its placement producer")
            if any(not set(reference["model_refs"]).issubset(receipt_model_ids) for reference in evidence):
                raise ValueError("simulated scenario evidence references an unknown producing model")
            if any(value["id"] not in reference["claim_refs"] for reference in evidence):
                raise ValueError("simulated scenario evidence is not bound to the scenario claim")
            if not output_scopes.issubset(evidence_scopes):
                raise ValueError("simulated scenario evidence does not cover every output scope")
            if not receipt_model_ids.issubset(evidence_models):
                raise ValueError("simulated scenario evidence does not cover every producing model")
        else:
            if receipts or effects or counterfactual is not None:
                raise ValueError("non-simulated scenarios must not invent effects, receipts, or counterfactual trajectory")
            if disposition == "abstained" and abstention is None:
                raise ValueError("abstained scenarios require abstention details")
        subjects = {
            state["subject"]
            for trajectory_name in ("baseline", "counterfactual")
            if value.get(trajectory_name)
            for state in value[trajectory_name]["states"]
        }
        if subjects != {value["subject"]}:
            raise ValueError("scenario and trajectory subjects must match")
        trajectories = [value["baseline"]]
        if value.get("counterfactual") is not None:
            trajectories.append(value["counterfactual"])
        trajectory_ids = [trajectory["id"] for trajectory in trajectories]
        if len(trajectory_ids) != len(set(trajectory_ids)):
            raise ValueError("scenario trajectory ids must be distinct")
        state_ids = [state["id"] for trajectory in trajectories for state in trajectory["states"]]
        if len(state_ids) != len(set(state_ids)):
            raise ValueError("scenario state ids must be distinct")
        for trajectory in trajectories:
            state_times = [parse_timestamp(state["state_time"]) for state in trajectory["states"]]
            if state_times != sorted(state_times):
                raise ValueError("trajectory states must be time ordered")
            trajectory_scopes = {
                subsystem["coordinate"] for state in trajectory["states"] for subsystem in state["subsystems"]
            }
            trajectory_scopes.update(
                coordinate
                for state in trajectory["states"]
                for coupling in state["couplings"]
                for coordinate in (coupling["source"], coupling["target"])
            )
            if trajectory["model_receipts"] and not trajectory_scopes:
                raise ValueError("producing model receipt placement requires non-empty biological scope")
            for state in trajectory["states"]:
                validate_state_validity(state)
                state_scopes = {subsystem["coordinate"] for subsystem in state["subsystems"]}
                state_scopes.update(
                    coordinate
                    for coupling in state["couplings"]
                    for coordinate in (coupling["source"], coupling["target"])
                )
                if state["model_receipts"] and not state_scopes:
                    raise ValueError("producing model receipt placement requires non-empty biological scope")
        perturbation_start = parse_timestamp(value["perturbation"]["starts_at"])
        if any(parse_timestamp(state["state_time"]) > perturbation_start for state in value["baseline"]["states"]):
            raise ValueError("baseline BodyState begins after perturbation start")
        if any(
            state.get("valid_until") is not None and parse_timestamp(state["valid_until"]) < perturbation_start
            for state in value["baseline"]["states"]
        ):
            raise ValueError("baseline BodyState expired before perturbation start")
        starts_at = parse_timestamp(value["perturbation"]["starts_at"])
        ends_at = value["perturbation"].get("ends_at")
        if ends_at is not None and parse_timestamp(ends_at) < starts_at:
            raise ValueError("perturbation ends_at precedes starts_at")
    if kind == "ObservedOutcome":
        if parse_timestamp(value["ended_at"]) < parse_timestamp(value["started_at"]):
            raise ValueError("outcome ended_at precedes started_at")
    if kind == "BodyState":
        validate_state_validity(value)
