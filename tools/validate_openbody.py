#!/usr/bin/env python3
import json
import sys
from datetime import datetime
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schemas" / "openbody.schema.json"
REGISTRY = ROOT / "registry" / "coordinates.json"


def load(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def collect_coordinates(value):
    found = []
    if isinstance(value, dict):
        for k, v in value.items():
            if k in {"coordinate", "scope", "source", "target"} and isinstance(v, str) and v.startswith("ob://"):
                found.append(v)
            found.extend(collect_coordinates(v))
    elif isinstance(value, list):
        for item in value:
            found.extend(collect_coordinates(item))
    return found


def collect_receipt_model_ids(value):
    if isinstance(value, dict):
        found = []
        if {"model_id", "model_version", "execution_id"}.issubset(value):
            found.append(value["model_id"])
        for nested in value.values():
            found.extend(collect_receipt_model_ids(nested))
        return found
    if isinstance(value, list):
        return [model_id for nested in value for model_id in collect_receipt_model_ids(nested)]
    return []


def counterfactual_output_scopes(doc):
    scopes = {effect["scope"] for effect in doc["expected_effects"]}
    for evidence in doc["evidence"]:
        scopes.update(evidence.get("scopes", []))
    for state in doc["counterfactual"]["states"]:
        scopes.update(subsystem["coordinate"] for subsystem in state["subsystems"])
        for coupling in state["couplings"]:
            scopes.update((coupling["source"], coupling["target"]))
        for evidence in state["evidence"]:
            scopes.update(evidence.get("scopes", []))
        for subsystem in state["subsystems"]:
            for evidence in subsystem["evidence"]:
                scopes.update(evidence.get("scopes", []))
    return scopes


def invariant_errors(doc):
    errors = []
    if doc.get("kind") == "CounterfactualScenario":
        disposition = doc.get("disposition")
        receipts = doc.get("model_receipts", [])
        effects = doc.get("expected_effects", [])
        counterfactual = doc.get("counterfactual")
        abstention = doc.get("abstention")
        if disposition == "simulated":
            if not receipts:
                errors.append("simulated scenario MUST carry at least one model receipt")
            if counterfactual is None:
                errors.append("simulated scenario MUST carry a counterfactual trajectory")
            if abstention is not None:
                errors.append("simulated scenario MUST NOT carry abstention")
            if counterfactual is not None:
                starts_at = datetime.fromisoformat(doc["perturbation"]["starts_at"].replace("Z", "+00:00"))
                state_times = [
                    datetime.fromisoformat(state["state_time"].replace("Z", "+00:00"))
                    for state in counterfactual["states"]
                ]
                if state_times != sorted(state_times):
                    errors.append("counterfactual trajectory states MUST be time ordered")
                derived_horizon = (state_times[-1] - starts_at).total_seconds()
                if derived_horizon != doc["applicability"]["horizon_seconds"]:
                    errors.append("simulated scenario applicability horizon MUST match returned trajectory")
                output_scopes = counterfactual_output_scopes(doc)
                if set(doc["applicability"]["scopes"]) != output_scopes:
                    errors.append("simulated scenario applicability scopes MUST match all output scopes")
                evidence = doc["evidence"]
                if not evidence:
                    errors.append("simulated scenario MUST carry actual evidence references")
                else:
                    bound = all(
                        reference.get("content_digest")
                        and reference.get("observed_at")
                        and reference.get("scopes")
                        and reference.get("model_refs")
                        and reference.get("claim_refs")
                        for reference in evidence
                    )
                    if not bound:
                        errors.append("simulated scenario evidence MUST be digest-addressed and explicitly bound")
                    evidence_scopes = {scope for reference in evidence for scope in reference.get("scopes", [])}
                    evidence_models = {model_id for reference in evidence for model_id in reference.get("model_refs", [])}
                    evidence_claims = {claim_id for reference in evidence for claim_id in reference.get("claim_refs", [])}
                    if any(reference.get("subject") != doc["subject"] for reference in evidence):
                        errors.append("simulated scenario evidence subject MUST match scenario subject")
                    if not output_scopes.issubset(evidence_scopes):
                        errors.append("simulated scenario evidence MUST cover all output scopes")
                    if not set(collect_receipt_model_ids(doc)).issubset(evidence_models):
                        errors.append("simulated scenario evidence MUST cover all producing models")
                    if doc["id"] not in evidence_claims:
                        errors.append("simulated scenario evidence MUST bind the scenario claim")
        else:
            if effects:
                errors.append("non-simulated scenario MUST NOT invent expected effects")
            if counterfactual is not None:
                errors.append("non-simulated scenario MUST NOT carry a counterfactual trajectory")
            if receipts:
                errors.append("non-simulated scenario MUST NOT claim a producing model receipt")
            if disposition == "abstained" and abstention is None:
                errors.append("abstained scenario MUST carry Abstention")
        trajectories = [doc["baseline"]]
        if counterfactual is not None:
            trajectories.append(counterfactual)
        trajectory_ids = [trajectory["id"] for trajectory in trajectories]
        if len(trajectory_ids) != len(set(trajectory_ids)):
            errors.append("scenario trajectory IDs MUST be distinct")
        state_ids = [state["id"] for trajectory in trajectories for state in trajectory["states"]]
        if len(state_ids) != len(set(state_ids)):
            errors.append("scenario state IDs MUST be distinct")
        for trajectory in trajectories:
            state_times = [
                datetime.fromisoformat(state["state_time"].replace("Z", "+00:00"))
                for state in trajectory["states"]
            ]
            if state_times != sorted(state_times):
                errors.append("trajectory states MUST be time ordered")
            for state in trajectory["states"]:
                valid_until = state.get("valid_until")
                if valid_until is not None:
                    state_time = datetime.fromisoformat(state["state_time"].replace("Z", "+00:00"))
                    validity_end = datetime.fromisoformat(valid_until.replace("Z", "+00:00"))
                    if validity_end < state_time:
                        errors.append("BodyState valid_until MUST be >= state_time")
        perturbation_start = datetime.fromisoformat(doc["perturbation"]["starts_at"].replace("Z", "+00:00"))
        for state in doc["baseline"]["states"]:
            valid_until = state.get("valid_until")
            if valid_until is not None:
                validity_end = datetime.fromisoformat(valid_until.replace("Z", "+00:00"))
                if validity_end < perturbation_start:
                    errors.append("baseline BodyState validity MUST cover perturbation start")
    if doc.get("kind") == "ObservedOutcome":
        started_at = datetime.fromisoformat(doc["started_at"].replace("Z", "+00:00"))
        ended_at = datetime.fromisoformat(doc["ended_at"].replace("Z", "+00:00"))
        if ended_at < started_at:
            errors.append("ObservedOutcome ended_at MUST be >= started_at")
    if doc.get("kind") == "BodyState" and doc.get("valid_until") is not None:
        state_time = datetime.fromisoformat(doc["state_time"].replace("Z", "+00:00"))
        valid_until = datetime.fromisoformat(doc["valid_until"].replace("Z", "+00:00"))
        if valid_until < state_time:
            errors.append("BodyState valid_until MUST be >= state_time")
    return errors


def main(paths):
    schema = load(SCHEMA)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    registry = load(REGISTRY)
    known_coordinates = {x["coordinate"] for x in registry["coordinates"]}
    failed = False

    for raw in paths:
        path = Path(raw)
        doc = load(path)
        schema_errors = sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path))
        custom_errors = invariant_errors(doc)
        unknown = sorted({c for c in collect_coordinates(doc) if c not in known_coordinates})
        if schema_errors or custom_errors:
            failed = True
            print(f"FAIL {path}")
            for err in schema_errors:
                loc = "/".join(map(str, err.absolute_path)) or "$"
                print(f"  schema {loc}: {err.message}")
            for err in custom_errors:
                print(f"  invariant: {err}")
        else:
            print(f"PASS {path}")
        for coordinate in unknown:
            print(f"  WARN unregistered coordinate: {coordinate}")

    return 1 if failed else 0


if __name__ == "__main__":
    args = sys.argv[1:] or [str(p) for p in sorted((ROOT / "examples").glob("*.json"))]
    raise SystemExit(main(args))
