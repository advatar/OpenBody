from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = ROOT / "schemas" / "intervention-observation.schema.json"
REGISTRY_PATH = ROOT / "registry" / "coordinates.json"


class InterventionObservationError(ValueError):
    """A stable, fail-closed source-observation validation failure."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _reject(code: str, message: str) -> None:
    raise InterventionObservationError(code, message)


def _timestamp(value: str, field: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as error:
        _reject("structural_invalid", f"{field} is not an RFC 3339 timestamp: {error}")


def validate_intervention_observation(observation: dict[str, Any]) -> None:
    schema = _load(SCHEMA_PATH)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(observation), key=lambda error: list(error.absolute_path))
    if errors:
        error = errors[0]
        location = "/".join(map(str, error.absolute_path)) or "$"
        _reject("structural_invalid", f"{location}: {error.message}")

    registered = {entry["coordinate"] for entry in _load(REGISTRY_PATH)["coordinates"]}
    unknown = sorted(set(observation["scope"]) - registered)
    if unknown:
        _reject("unsupported_scope", f"Unregistered OpenBody scope: {unknown[0]}")

    start = _timestamp(observation["intervention"]["started_at"], "intervention.started_at")
    end = _timestamp(observation["intervention"]["ended_at"], "intervention.ended_at")
    if end < start:
        _reject("invalid_interval", "intervention.ended_at precedes intervention.started_at")

    disclosure = observation["disclosure"]
    authorized_at = _timestamp(disclosure["authorized_at"], "disclosure.authorized_at")
    if disclosure.get("expires_at") and _timestamp(disclosure["expires_at"], "disclosure.expires_at") < authorized_at:
        _reject("invalid_consent_window", "disclosure.expires_at precedes disclosure.authorized_at")

    disclosed = set(disclosure["fields"])
    if "user_response" in disclosed and "user_response" not in observation:
        _reject("disclosed_field_missing", "user_response is disclosed but absent")
    if "evidence" in disclosed and not observation["evidence"]:
        _reject("disclosed_field_missing", "evidence is disclosed but empty")
    if "observed_measurements" in disclosed and not observation["observed_measurements"]:
        _reject("disclosed_field_missing", "observed_measurements is disclosed but empty")
