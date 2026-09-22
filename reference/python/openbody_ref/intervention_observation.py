from __future__ import annotations

import json
import math
from functools import lru_cache
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


@lru_cache(maxsize=1)
def _schema_validator() -> Draft202012Validator:
    return Draft202012Validator(_load(SCHEMA_PATH), format_checker=FormatChecker())


@lru_cache(maxsize=1)
def _registered_scopes() -> frozenset[str]:
    return frozenset(entry["coordinate"] for entry in _load(REGISTRY_PATH)["coordinates"])


def _reject(code: str, message: str) -> None:
    raise InterventionObservationError(code, message)


def _timestamp(value: str, field: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as error:
        _reject("structural_invalid", f"{field} is not an RFC 3339 timestamp: {error}")


def _non_finite_path(value: Any, path: str = "") -> str | None:
    if isinstance(value, float) and not math.isfinite(value):
        return path or "$"
    if isinstance(value, dict):
        children = ((f"{path}/{key}".lstrip("/"), child) for key, child in value.items())
    elif isinstance(value, list):
        children = ((f"{path}/{index}".lstrip("/"), child) for index, child in enumerate(value))
    else:
        return None
    for child_path, child in children:
        found = _non_finite_path(child, child_path)
        if found:
            return found
    return None


def validate_intervention_observation(observation: dict[str, Any]) -> None:
    non_finite = _non_finite_path(observation)
    if non_finite:
        _reject("structural_invalid", f"{non_finite}: numbers must be finite")

    errors = sorted(_schema_validator().iter_errors(observation), key=lambda error: list(error.absolute_path))
    if errors:
        error = errors[0]
        location = "/".join(map(str, error.absolute_path)) or "$"
        _reject("structural_invalid", f"{location}: {error.message}")

    unknown = sorted(set(observation["scope"]) - _registered_scopes())
    if unknown:
        _reject("unsupported_scope", f"Unregistered OpenBody scope: {unknown[0]}")

    start = _timestamp(observation["intervention"]["started_at"], "intervention.started_at")
    end = _timestamp(observation["intervention"]["ended_at"], "intervention.ended_at")
    if end < start:
        _reject("invalid_interval", "intervention.ended_at precedes intervention.started_at")

    for measurement in observation["observed_measurements"]:
        observed_at = _timestamp(measurement["observed_at"], "observed_measurements.observed_at")
        phase = measurement["phase"]
        if (
            (phase == "before" and observed_at > start)
            or (phase == "end" and observed_at < start)
            or (phase == "follow_up" and observed_at < end)
        ):
            _reject(
                "invalid_measurement_phase",
                f"A {phase} measurement observed at {measurement['observed_at']} contradicts the session interval",
            )

    if "user_response" in observation:
        recorded_at = _timestamp(observation["user_response"]["recorded_at"], "user_response.recorded_at")
        if recorded_at < start:
            _reject("invalid_interval", "user_response.recorded_at precedes intervention.started_at")

    disclosure = observation["disclosure"]
    authorized_at = _timestamp(disclosure["authorized_at"], "disclosure.authorized_at")
    if disclosure.get("expires_at") and _timestamp(disclosure["expires_at"], "disclosure.expires_at") <= authorized_at:
        _reject("invalid_consent_window", "disclosure.expires_at does not follow disclosure.authorized_at")

    # The allowlist is exact: it names every section the payload carries and
    # nothing it does not. Declaring less than is carried would present
    # undisclosed content as disclosed.
    disclosed = set(disclosure["fields"])
    present = {"intervention"}
    present.update(
        field for field in ("observed_measurements", "evidence") if observation[field]
    )
    if "user_response" in observation:
        present.add("user_response")
    for field in sorted(disclosed - present):
        _reject("disclosed_field_missing", f"{field} is disclosed but absent or empty")
    for field in sorted(present - disclosed):
        _reject("undisclosed_content_present", f"{field} is carried but not disclosed")
