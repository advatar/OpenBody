from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .validation import parse_timestamp, scenario_horizon_seconds, semantic_validate


def collect_model_receipts(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        receipts = []
        if {"model_id", "model_version", "execution_id"}.issubset(value):
            receipts.append(value)
        for nested in value.values():
            receipts.extend(collect_model_receipts(nested))
        return receipts
    if isinstance(value, list):
        return [receipt for nested in value for receipt in collect_model_receipts(nested)]
    return []


@dataclass
class InMemoryTwinStore:
    state: dict[str, Any]
    models: dict[str, dict[str, Any]] = field(default_factory=dict)
    trajectories: dict[str, dict[str, Any]] = field(default_factory=dict)
    scenarios: dict[str, dict[str, Any]] = field(default_factory=dict)
    outcomes: dict[str, dict[str, Any]] = field(default_factory=dict)
    calibrations: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def from_fixture(cls, path: Path) -> "InMemoryTwinStore":
        fixture = json.loads(path.read_text())
        state = fixture["baseline"]["states"][0] if fixture.get("kind") == "CounterfactualScenario" else fixture
        semantic_validate(state)
        store = cls(state=state)
        if fixture.get("kind") == "CounterfactualScenario":
            semantic_validate(fixture)
            declared_horizon = fixture["applicability"]["horizon_seconds"]
            if declared_horizon != scenario_horizon_seconds(fixture):
                raise ValueError("fixture applicability horizon does not match returned trajectory")
            store.scenarios[fixture["id"]] = fixture
            store.trajectories[fixture["baseline"]["id"]] = fixture["baseline"]
            if fixture.get("counterfactual"):
                store.trajectories[fixture["counterfactual"]["id"]] = fixture["counterfactual"]
            receipt_capabilities: dict[tuple[str, str], set[str]] = {}
            receipt_values: dict[tuple[str, str], dict[str, Any]] = {}
            trajectories = [fixture["baseline"], fixture["counterfactual"]]
            for trajectory in trajectories:
                for receipt in collect_model_receipts(trajectory["states"]):
                    key = (receipt["model_id"], receipt["model_version"])
                    receipt_values[key] = receipt
                    receipt_capabilities.setdefault(key, set()).add("state_estimation")
            simulation_receipts = fixture["model_receipts"] + fixture["counterfactual"]["model_receipts"]
            for receipt in collect_model_receipts(simulation_receipts):
                key = (receipt["model_id"], receipt["model_version"])
                receipt_values[key] = receipt
                receipt_capabilities.setdefault(key, set()).add("counterfactual")

            state_scopes = {subsystem["coordinate"] for state in fixture["baseline"]["states"] for subsystem in state["subsystems"]}
            simulation_scopes = set(fixture["applicability"]["scopes"])
            for (model_id, model_version), capabilities in receipt_capabilities.items():
                existing = store.models.get(model_id)
                if existing is not None and existing["version"] != model_version:
                    raise ValueError("fixture uses multiple versions of one model id")
                receipt = receipt_values[(model_id, model_version)]
                scopes = set()
                if "state_estimation" in capabilities:
                    scopes.update(state_scopes)
                if "counterfactual" in capabilities:
                    scopes.update(simulation_scopes)
                store.models[model_id] = {
                    "schema_version": "0.1",
                    "kind": "BodyModel",
                    "id": model_id,
                    "version": model_version,
                    "family": receipt["family"],
                    "provider": "OpenBody deterministic fixture replay",
                    "scopes": sorted(scopes),
                    "capabilities": sorted(capabilities),
                    "required_inputs": ["exact bundled fixture inputs"],
                    "outputs": ["exact bundled fixture outputs"],
                    "applicability": fixture["applicability"],
                    "validation": {"reference": receipt.get("validation_ref")},
                    "prohibited_uses": ["clinical decision-making", "generalization beyond the bundled fixture"],
                    "execution": {"mode": "fixture_replay"},
                    "dependencies": [],
                }
                semantic_validate(store.models[model_id])
        return store

    def put_outcome(self, value: dict[str, Any]) -> None:
        semantic_validate(value)
        if value["subject"] != self.state["subject"]:
            raise ValueError("outcome subject does not match hosted twin")
        scenarios = [
            scenario
            for scenario in self.scenarios.values()
            if scenario["perturbation"]["id"] == value["perturbation_id"]
            and scenario["subject"] == value["subject"]
        ]
        if not scenarios:
            raise ValueError("outcome is not bound to a hosted perturbation")
        outcome_start = parse_timestamp(value["started_at"])
        if not any(outcome_start >= parse_timestamp(scenario["perturbation"]["starts_at"]) for scenario in scenarios):
            raise ValueError("outcome predates its hosted perturbation instance")
        if value["id"] in self.outcomes:
            raise ValueError("outcome id already exists")
        self.outcomes[value["id"]] = value

    def put_calibration(self, value: dict[str, Any]) -> None:
        semantic_validate(value)
        scenario = self.scenarios.get(value["scenario_id"])
        outcome = self.outcomes.get(value["outcome_id"])
        if scenario is None or outcome is None:
            raise ValueError("calibration requires an existing scenario and outcome")
        if scenario["subject"] != outcome["subject"]:
            raise ValueError("calibration subject binding does not match")
        if scenario["perturbation"]["id"] != outcome["perturbation_id"]:
            raise ValueError("calibration perturbation binding does not match")
        absolute_error_metrics = set(value["absolute_errors"])
        interval_metrics = set(value["within_predicted_interval"])
        if not absolute_error_metrics or absolute_error_metrics != interval_metrics:
            raise ValueError("calibration metric maps must be non-empty and use identical keys")
        for metric in absolute_error_metrics:
            predicted_scopes = {effect["scope"] for effect in scenario["expected_effects"] if effect["metric"] == metric}
            observed_scopes = {effect["scope"] for effect in outcome["observed_effects"] if effect["metric"] == metric}
            if len(predicted_scopes) != 1 or predicted_scopes != observed_scopes:
                raise ValueError("calibration metric and scope must match exactly in prediction and outcome")
        if value["id"] in self.calibrations:
            raise ValueError("calibration id already exists")
        self.calibrations[value["id"]] = value
