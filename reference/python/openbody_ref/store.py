from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .validation import semantic_validate


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
            store.scenarios[fixture["id"]] = fixture
            store.trajectories[fixture["baseline"]["id"]] = fixture["baseline"]
            if fixture.get("counterfactual"):
                store.trajectories[fixture["counterfactual"]["id"]] = fixture["counterfactual"]
            receipt = fixture["model_receipts"][0]
            store.models[receipt["model_id"]] = {
                "schema_version": "0.1",
                "kind": "BodyModel",
                "id": receipt["model_id"],
                "version": receipt["model_version"],
                "family": receipt["family"],
                "provider": "OpenBody deterministic fixture replay",
                "scopes": sorted({effect["scope"] for effect in fixture["expected_effects"]}),
                "capabilities": ["counterfactual"],
                "required_inputs": ["exact bundled baseline BodyState"],
                "outputs": ["exact bundled CounterfactualScenario"],
                "applicability": {"scenario_id": fixture["id"], "horizon_seconds": 7200},
                "validation": {"reference": receipt.get("validation_ref")},
                "prohibited_uses": ["clinical decision-making", "generalization beyond the bundled fixture"],
                "execution": {"mode": "fixture_replay"},
                "dependencies": [],
            }
            semantic_validate(store.models[receipt["model_id"]])
        return store

    def put_outcome(self, value: dict[str, Any]) -> None:
        semantic_validate(value)
        if value["subject"] != self.state["subject"]:
            raise ValueError("outcome subject does not match hosted twin")
        if not any(
            scenario["perturbation"]["id"] == value["perturbation_id"]
            and scenario["subject"] == value["subject"]
            for scenario in self.scenarios.values()
        ):
            raise ValueError("outcome is not bound to a hosted perturbation")
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
        if value["id"] in self.calibrations:
            raise ValueError("calibration id already exists")
        self.calibrations[value["id"]] = value
