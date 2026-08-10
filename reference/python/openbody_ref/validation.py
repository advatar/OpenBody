from __future__ import annotations

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
        starts_at = parse_timestamp(value["perturbation"]["starts_at"])
        ends_at = value["perturbation"].get("ends_at")
        if ends_at is not None and parse_timestamp(ends_at) < starts_at:
            raise ValueError("perturbation ends_at precedes starts_at")
    if kind == "ObservedOutcome":
        if parse_timestamp(value["ended_at"]) < parse_timestamp(value["started_at"]):
            raise ValueError("outcome ended_at precedes started_at")
