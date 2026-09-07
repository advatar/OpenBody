from __future__ import annotations

import copy
from pathlib import Path

import pytest

from openbody_ref.demo_counterfactual import DemoCounterfactualError, simulate


FIXTURE = Path(__file__).resolve().parents[3] / "examples/post-meal-walk.scenario.json"


def request() -> dict:
    return {
        "schema": "openbody.demo-counterfactual-request.v1",
        "subject_ref": "subject:demo-patient-001",
        "generated_at": "2026-09-03T12:35:00Z",
        "body_state_digest": "sha256:" + "a" * 64,
        "intervention": {
            "kind": "post-meal-walk",
            "duration_minutes": 15,
            "intensity": "low",
        },
        "horizon_seconds": 7200,
    }


def test_exact_qualified_fixture_is_replayed_with_receipt() -> None:
    result = simulate(request(), FIXTURE)
    assert result["disposition"] == "simulated"
    assert result["mode"] == "exact_fixture_replay"
    assert result["horizon_seconds"] == 7200
    assert result["generalizable"] is False
    assert result["model_receipts"][0]["model_id"] == "post-meal-walk-personal-difference"
    assert result["fixture_digest"].startswith("sha256:")


def test_unqualified_horizon_fails_closed() -> None:
    value = copy.deepcopy(request())
    value["horizon_seconds"] = 3600
    with pytest.raises(DemoCounterfactualError, match="7,200"):
        simulate(value, FIXTURE)


def test_unqualified_intervention_fails_closed() -> None:
    value = copy.deepcopy(request())
    value["intervention"]["intensity"] = "high"
    with pytest.raises(DemoCounterfactualError, match="outside"):
        simulate(value, FIXTURE)
