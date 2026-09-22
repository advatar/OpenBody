from __future__ import annotations

import json
import math
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

from openbody_ref.validation import canonical_digest

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = ROOT / "schemas" / "intervention-observation.schema.json"
REGISTRY_PATH = ROOT / "registry" / "coordinates.json"
SCHEMA_VERSION = "openbody.intervention-observation/2.0"


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


def _first_repeat(keys) -> tuple[str, str] | None:
    counts = Counter(keys)
    return next((key for key, count in counts.items() if count > 1), None)


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
        if measurement["status"] != "observed":
            continue
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

    # One entry per metric and phase: the profile carries selected values, not
    # a series, and a second entry would contradict the first.
    repeated = _first_repeat((m["phase"], m["metric"]) for m in observation["observed_measurements"])
    if repeated:
        _reject("duplicate_measurement", f"More than one {repeated[1]} measurement in phase {repeated[0]}")
    repeated = _first_repeat((d["name"], d["status"]) for d in observation["intervention"]["dose"])
    if repeated:
        _reject("duplicate_dose_dimension", f"More than one {repeated[1]} {repeated[0]} dose dimension")

    if "user_response" in observation:
        recorded_at = _timestamp(observation["user_response"]["recorded_at"], "user_response.recorded_at")
        if recorded_at < start:
            _reject("invalid_interval", "user_response.recorded_at precedes intervention.started_at")

    disclosure = observation["disclosure"]
    authorized_at = _timestamp(disclosure["authorized_at"], "disclosure.authorized_at")
    verified_at = _timestamp(observation["subject_binding"]["verified_at"], "subject_binding.verified_at")
    if verified_at > authorized_at:
        _reject("invalid_subject_binding", "subject_binding.verified_at follows disclosure.authorized_at")
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


ObservationCheck = Callable[[dict[str, Any], datetime], bool]


@dataclass(frozen=True)
class IntakeResult:
    """How a receiver took in a source observation."""

    outcome: str  # "admitted" or "replay"
    observation_id: str
    content_digest: str
    evidence_class: str = "source_observation"


class InterventionObservationIntake:
    """Reference receiver for the requirements the payload cannot enforce.

    A payload only declares its subject binding and consent. This intake refuses
    to accept one until caller-supplied verifiers have checked both, and it
    enforces the consent window at receipt, the named recipient, and the
    replay/ID-reuse rule. It stores source evidence only. Nothing it accepts
    becomes an OpenBody-derived object or a clinical assertion.
    """

    def __init__(
        self,
        *,
        recipient: str,
        verify_subject_binding: ObservationCheck,
        verify_consent: ObservationCheck,
    ):
        self._recipient = recipient
        self._verify_subject_binding = verify_subject_binding
        self._verify_consent = verify_consent
        self._digests: dict[str, str] = {}

    def receive(self, observation: dict[str, Any], *, evaluated_at: datetime) -> IntakeResult:
        if evaluated_at.tzinfo is None:
            _reject("invalid_evaluation_time", "evaluated_at must carry a UTC offset")
        validate_intervention_observation(observation)

        disclosure = observation["disclosure"]
        if disclosure["recipient"] != self._recipient:
            _reject("recipient_mismatch", "The observation was disclosed to a different recipient")
        if _timestamp(disclosure["authorized_at"], "disclosure.authorized_at") > evaluated_at:
            _reject("consent_not_yet_valid", "disclosure.authorized_at is in the future")
        if disclosure.get("expires_at") and _timestamp(disclosure["expires_at"], "disclosure.expires_at") <= evaluated_at:
            _reject("consent_expired", "The disclosure authorization has expired")
        if not _passes(self._verify_subject_binding, observation, evaluated_at):
            _reject("subject_binding_unverified", "The receiver could not verify the subject binding")
        if not _passes(self._verify_consent, observation, evaluated_at):
            _reject("consent_unverified", "The receiver could not verify the consent")

        observation_id = observation["observation_id"]
        digest = canonical_digest(observation)
        known = self._digests.get(observation_id)
        if known is None:
            self._digests[observation_id] = digest
            return IntakeResult("admitted", observation_id, digest)
        if known == digest:
            return IntakeResult("replay", observation_id, digest)
        _reject("observation_id_conflict", f"{observation_id} was already received with different content")


def _passes(check: ObservationCheck, observation: dict[str, Any], evaluated_at: datetime) -> bool:
    # A verifier that errors has not verified anything.
    try:
        return check(observation, evaluated_at) is True
    except Exception:
        return False
