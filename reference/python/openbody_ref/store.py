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
        return store

    def put_outcome(self, value: dict[str, Any]) -> None:
        semantic_validate(value)
        self.outcomes[value["id"]] = value

    def put_calibration(self, value: dict[str, Any]) -> None:
        semantic_validate(value)
        self.calibrations[value["id"]] = value
