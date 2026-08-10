from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import timedelta
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


def producing_model_requirements(value: dict[str, Any]) -> dict[tuple[str, str, str], dict[str, set[str]]]:
    requirements: dict[tuple[str, str, str], dict[str, set[str]]] = {}

    def add(receipt: dict[str, Any], capabilities: set[str], scopes: set[str]) -> None:
        key = (receipt["model_id"], receipt["model_version"], receipt["family"])
        requirement = requirements.setdefault(key, {"capabilities": set(), "scopes": set()})
        requirement["capabilities"].update(capabilities)
        requirement["scopes"].update(scopes)
        if receipt.get("validation_ref"):
            requirement.setdefault("validation_refs", set()).add(receipt["validation_ref"])

    for trajectory_name in ("baseline", "counterfactual"):
        trajectory = value[trajectory_name]
        is_counterfactual = trajectory_name == "counterfactual"
        nested_capabilities = {"state_estimation", "counterfactual"} if is_counterfactual else {"state_estimation"}
        trajectory_scopes = set()
        for state in trajectory["states"]:
            state_scopes = {subsystem["coordinate"] for subsystem in state["subsystems"]}
            for coupling in state["couplings"]:
                state_scopes.update((coupling["source"], coupling["target"]))
            trajectory_scopes.update(state_scopes)
            for receipt in state["model_receipts"]:
                add(receipt, nested_capabilities, state_scopes)
            for subsystem in state["subsystems"]:
                add(subsystem["model_receipt"], nested_capabilities, {subsystem["coordinate"]})
            for coupling in state["couplings"]:
                add(coupling["model_receipt"], nested_capabilities, {coupling["source"], coupling["target"]})
        trajectory_capabilities = {"counterfactual"} if is_counterfactual else {"state_estimation"}
        for receipt in trajectory["model_receipts"]:
            add(receipt, trajectory_capabilities, trajectory_scopes)
    scenario_scopes = set(value["applicability"]["scopes"])
    for receipt in value["model_receipts"]:
        add(receipt, {"counterfactual"}, scenario_scopes)
    return requirements


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
            requirements = producing_model_requirements(fixture)
            for (model_id, model_version, family), requirement in requirements.items():
                existing = store.models.get(model_id)
                if existing is not None and (existing["version"], existing["family"]) != (model_version, family):
                    raise ValueError("fixture uses conflicting identities for one model id")
                store.models[model_id] = {
                    "schema_version": "0.1",
                    "kind": "BodyModel",
                    "id": model_id,
                    "version": model_version,
                    "family": family,
                    "provider": "OpenBody deterministic fixture replay",
                    "scopes": sorted(requirement["scopes"]),
                    "capabilities": sorted(requirement["capabilities"]),
                    "required_inputs": ["exact bundled fixture inputs"],
                    "outputs": ["exact bundled fixture outputs"],
                    "applicability": fixture["applicability"],
                    "validation": {"references": sorted(requirement.get("validation_refs", set()))},
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
        scenarios = []
        for scenario in self.scenarios.values():
            if (
                scenario.get("perturbation", {}).get("id") == value["perturbation_id"]
                and scenario.get("subject") == value["subject"]
            ):
                semantic_validate(scenario)
                derived_horizon = scenario_horizon_seconds(scenario)
                if derived_horizon != scenario["applicability"]["horizon_seconds"]:
                    raise ValueError("stored scenario horizon is not trustworthy")
                scenarios.append(scenario)
        if not scenarios:
            raise ValueError("outcome is not bound to a hosted perturbation")
        outcome_start = parse_timestamp(value["started_at"])
        outcome_end = parse_timestamp(value["ended_at"])
        if not any(
            outcome_start >= parse_timestamp(scenario["perturbation"]["starts_at"])
            and outcome_end
            <= parse_timestamp(scenario["perturbation"]["starts_at"])
            + timedelta(seconds=scenario["applicability"]["horizon_seconds"])
            for scenario in scenarios
        ):
            raise ValueError("outcome falls outside its hosted scenario observation window")
        if value["id"] in self.outcomes:
            raise ValueError("outcome id already exists")
        self.outcomes[value["id"]] = value

    def put_calibration(self, value: dict[str, Any]) -> None:
        semantic_validate(value)
        scenario = self.scenarios.get(value["scenario_id"])
        outcome = self.outcomes.get(value["outcome_id"])
        if scenario is None or outcome is None:
            raise ValueError("calibration requires an existing scenario and outcome")
        semantic_validate(scenario)
        if scenario_horizon_seconds(scenario) != scenario["applicability"]["horizon_seconds"]:
            raise ValueError("calibration scenario horizon is not trustworthy")
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
