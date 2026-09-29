"""Whole-person observation envelopes and deterministic state snapshots (issue #30).

The envelope (`openbody.whole-person-observation/1.0`) carries one source-neutral
observation with exact provenance. The snapshot (`openbody.whole-person-state/1.0`)
is a deterministic longitudinal projection over admitted envelopes.

Boundaries enforced here:

* no source-priority inference: disagreeing current sources stay an unresolved
  conflict and the snapshot selects no value;
* unknown uncertainty stays unknown and is never filled;
* imputed values never count as measurements;
* exact source, time, unit and derivation provenance is copied, not summarised;
* the same admitted inputs, ``as_of``, purpose and revocations always produce the
  same snapshot bytes;
* a snapshot is not a clinical assertion; clinical use still requires the
  existing admission and model-receipt path.
"""

from __future__ import annotations

import copy
import functools
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from .canonical_json import CanonicalDomainError
from .canonical_json import digest as _canonical_digest_v1
from .schema_keywords import schema_vocabulary

ROOT = Path(__file__).resolve().parents[3]
OBSERVATION_SCHEMA_PATH = ROOT / "schemas" / "whole-person-observation.schema.json"
STATE_SCHEMA_PATH = ROOT / "schemas" / "whole-person-state.schema.json"
REGISTRY_PATH = ROOT / "registry" / "coordinates.json"
VALUE_SETS_PATH = ROOT / "registry" / "whole-person-value-sets.json"
NATIVE_VALIDATION_PATH = ROOT / "fixtures" / "whole-person-state" / "v1" / "native-validation.json"
VALUE_SETS_VERSION = "openbody.whole-person-value-sets/1.0"

OBSERVATION_VERSION = "openbody.whole-person-observation/1.0"
STATE_VERSION = "openbody.whole-person-state/1.0"
POLICY_VERSION = "openbody.whole-person-assembly-policy/1.0"

# Envelope time may exceed ingestion time by at most this much before the
# envelope is treated as a clock inconsistency rather than silently accepted.
CLOCK_SKEW_TOLERANCE_SECONDS = 300

# Freshness windows. A candidate older than this at ``as_of`` is stale: it is
# kept with its provenance but cannot support current clinical use.
MAX_AGE_SECONDS: dict[str, int] = {
    "glucose": 3_600,
    "heart_rate": 3_600,
    "heart_rate_variability": 172_800,
    "sleep": 172_800,
    "activity": 172_800,
    "body_temperature": 86_400,
    "meal": 86_400,
    "environment": 86_400,
    "symptom": 604_800,
    "laboratory": 7_776_000,
}

# Explicit unit table. A unit that is not listed is excluded, never guessed.
# Each entry maps an accepted UCUM unit to (factor, offset) into the canonical
# unit: canonical = value * factor + offset.
UNITS: dict[str, dict[str, Any]] = {
    "glucose": {"canonical": "mmol/L", "accept": {"mmol/L": (1.0, 0.0), "mg/dL": (1 / 18.016, 0.0)}},
    "heart_rate": {"canonical": "/min", "accept": {"/min": (1.0, 0.0)}},
    "heart_rate_variability": {"canonical": "ms", "accept": {"ms": (1.0, 0.0), "s": (1000.0, 0.0)}},
    "sleep": {"canonical": "min", "accept": {"min": (1.0, 0.0), "h": (60.0, 0.0)}},
    "activity": {"canonical": "{steps}", "accept": {"{steps}": (1.0, 0.0)}},
    "body_temperature": {
        "canonical": "Cel",
        "accept": {"Cel": (1.0, 0.0), "[degF]": (5 / 9, -32 * 5 / 9)},
    },
    "environment": {"canonical": "ug/m3", "accept": {"ug/m3": (1.0, 0.0)}},
    # Laboratory units are keyed by LOINC code because one domain spans analytes.
    "laboratory:4548-4": {"canonical": "%", "accept": {"%": (1.0, 0.0)}},
    "laboratory:2093-3": {"canonical": "mmol/L", "accept": {"mmol/L": (1.0, 0.0), "mg/dL": (0.02586, 0.0)}},
    "laboratory:2339-0": {"canonical": "mmol/L", "accept": {"mmol/L": (1.0, 0.0), "mg/dL": (1 / 18.016, 0.0)}},
}

NON_MEASUREMENT = {"imputed"}
MODEL_OUTPUT = {"derived", "inferred"}
PURPOSES = {"personal_state", "encounter_context", "research_simulation"}


class WholePersonStateError(ValueError):
    """A stable, fail-closed whole-person contract failure."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _reject(code: str, message: str) -> None:
    raise WholePersonStateError(code, message)


def canonical_digest(value: Any) -> str:
    """``openbody.canonical-digest/1`` (docs/CANONICAL_DIGEST_V1.md), failing closed.

    Values outside the specified domain (non-finite numbers, integers beyond
    +/-(2**53 - 1), lone surrogates, non-string keys) are rejected rather than
    digested in a way other languages could not reproduce.
    """

    try:
        return _canonical_digest_v1(value)
    except CanonicalDomainError as error:
        _reject("canonical_domain_violation", f"{error.code}: {error}")
        return ""  # pragma: no cover


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _time(value: str) -> datetime:
    """Parse an RFC 3339 date-time (the schema checks the format first).

    RFC 3339 allows lower-case ``t`` and ``z``; they are accepted as upper case.
    Fractions are compared at microsecond precision, and further digits are
    truncated. Anything the parser cannot read is ``structural_invalid``, never
    an unhandled error.
    """

    try:
        return datetime.fromisoformat(value.upper().replace("Z", "+00:00"))
    except (AttributeError, ValueError) as error:
        _reject("structural_invalid", f"Not an RFC 3339 date-time: {value!r} ({error})")
        raise  # pragma: no cover


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _utc(value: str) -> datetime:
    return _time(value).astimezone(timezone.utc)


def published_native_vocabulary() -> dict[str, Any]:
    """The vocabulary a validator must implement for the v1 schemas (decision 2)."""

    return _load(NATIVE_VALIDATION_PATH)["required_vocabulary"]


def _require_supported_vocabulary(schema: dict[str, Any], format_checker: FormatChecker) -> None:
    """Fail closed when a schema uses a constraint outside the published vocabulary.

    JSON Schema validators ignore unknown keywords, and the Python format checker
    silently accepts formats it has no checker for. Either would weaken the
    contract without any visible error, so both are refused here, as a native
    validator must refuse them.
    """

    published = published_native_vocabulary()
    used = schema_vocabulary(schema)
    unknown = sorted(set(used["keywords"]) - set(published["keywords"]))
    if unknown:
        _reject("schema_vocabulary_unsupported", f"Schema keyword {unknown[0]} is not in the published vocabulary")
    unknown = sorted(set(used["formats"]) - set(published["formats"]))
    if unknown:
        _reject("schema_vocabulary_unsupported", f"Schema format {unknown[0]} is not in the published vocabulary")
    unchecked = sorted(set(used["formats"]) - set(format_checker.checkers))
    if unchecked:
        _reject("schema_vocabulary_unsupported", f"No checker is installed for format {unchecked[0]}")
    unknown = sorted(set(used["refs"]) - set(published["refs"]))
    if unknown:
        _reject("schema_vocabulary_unsupported", f"Schema reference kind {unknown[0]} is not supported")


@functools.lru_cache(maxsize=4)
def _validator(schema_path: Path) -> Draft202012Validator:
    observation_schema = _load(OBSERVATION_SCHEMA_PATH)
    schema = _load(schema_path)
    format_checker = FormatChecker()
    _require_supported_vocabulary(schema, format_checker)
    if schema_path != OBSERVATION_SCHEMA_PATH:
        _require_supported_vocabulary(observation_schema, format_checker)
    registry = Registry().with_resource(
        observation_schema["$id"], Resource.from_contents(observation_schema)
    )
    return Draft202012Validator(schema, registry=registry, format_checker=format_checker)


def _schema_errors(schema_path: Path, value: Any) -> list[str]:
    validator = _validator(schema_path)
    errors = sorted(validator.iter_errors(value), key=lambda error: list(error.absolute_path))
    return [f"{'/'.join(map(str, error.absolute_path)) or '$'}: {error.message}" for error in errors]


def envelope_digest(envelope: dict[str, Any]) -> str:
    return canonical_digest(envelope)


def validate_observation(envelope: dict[str, Any]) -> None:
    """Validate one envelope; raise WholePersonStateError with a stable code."""

    errors = _schema_errors(OBSERVATION_SCHEMA_PATH, envelope)
    if errors:
        _reject("structural_invalid", errors[0])

    registered = {entry["coordinate"] for entry in _load(REGISTRY_PATH)["coordinates"]}
    unknown = sorted(set(envelope["scope"]) - registered)
    if unknown:
        _reject("unsupported_scope", f"Unregistered OpenBody scope: {unknown[0]}")

    present = envelope["missingness"]["status"] == "present"
    if present and envelope["uncertainty"]["status"] == "not_applicable":
        _reject(
            "uncertainty_not_applicable",
            "A present value must state quantified or unknown uncertainty",
        )
    interval = envelope["uncertainty"].get("interval")
    if interval and interval["lower"] > interval["upper"]:
        _reject("invalid_uncertainty", "uncertainty.interval.lower exceeds upper")

    timing = envelope["time"]
    start = _time(timing["effective_start"])
    ingested = _time(timing["ingested_at"])
    if timing["effective_end"] is not None and _time(timing["effective_end"]) < start:
        _reject("clock_inconsistent", "time.effective_end precedes time.effective_start")
    if start - ingested > timedelta(seconds=CLOCK_SKEW_TOLERANCE_SECONDS):
        _reject("clock_inconsistent", "time.effective_start is after ingestion beyond tolerated skew")
    clock = timing["clock"]
    if clock["status"] == "corrected":
        reported = _time(clock["device_reported_start"])
        if reported + timedelta(seconds=clock["correction_seconds"]) != start:
            _reject(
                "clock_inconsistent",
                "device_reported_start + correction_seconds does not equal effective_start",
            )

    consent = envelope["consent"]
    if consent["expires_at"] is not None and _time(consent["expires_at"]) <= _time(consent["granted_at"]):
        _reject("invalid_consent_window", "consent.expires_at is not after consent.granted_at")

    derivation = envelope.get("derivation")
    if derivation and any(parent["observation_id"] == envelope["observation_id"] for parent in derivation["parents"]):
        _reject("derivation_cycle", "An observation cannot derive from itself")


def _normalize(envelope: dict[str, Any]) -> tuple[Any, Any] | None:
    """Return (value, unit) in canonical form, or None when the unit is unrecognized."""

    measurement = envelope["measurement"]
    if envelope["missingness"]["status"] != "present" or measurement["value_type"] != "quantity":
        return measurement["value"], measurement["unit"]
    domain = measurement["domain"]
    table = UNITS.get(f"{domain}:{measurement['code']['code']}") if domain == "laboratory" else UNITS.get(domain)
    if table is None or measurement["unit"] not in table["accept"]:
        return None
    factor, offset = table["accept"][measurement["unit"]]
    return round(measurement["value"] * factor + offset, 4), table["canonical"]


def load_value_sets(path: Path = VALUE_SETS_PATH) -> dict[tuple[str, str], dict[str, Any]]:
    """Per-code categorical value sets (decision 3), checked for internal consistency.

    Returns ``{(system, code): {"domain": str, "dimensions": {name: frozenset(values)}}}``.
    Within one code, a value belongs to exactly one dimension, so the dimension of a
    categorical value is determined by the value set, never guessed.
    """

    document = _load(path)
    if document.get("value_sets_version") != VALUE_SETS_VERSION:
        _reject("value_sets_invalid", f"Unsupported value-set version {document.get('value_sets_version')}")
    value_sets: dict[tuple[str, str], dict[str, Any]] = {}
    for item in document["codes"]:
        key = (item["system"], item["code"])
        if key in value_sets:
            _reject("value_sets_invalid", f"Code {key[0]}|{key[1]} is listed twice")
        dimensions: dict[str, frozenset[str]] = {}
        seen: set[str] = set()
        for name, values in item["dimensions"].items():
            if not values or len(set(values)) != len(values):
                _reject("value_sets_invalid", f"Dimension {name} of {key[1]} is empty or repeats a value")
            if seen & set(values):
                _reject("value_sets_invalid", f"Code {key[1]} shares a value between dimensions")
            seen |= set(values)
            dimensions[name] = frozenset(values)
        if not dimensions:
            _reject("value_sets_invalid", f"Code {key[1]} has no dimension")
        value_sets[key] = {"domain": item["domain"], "dimensions": dimensions}
    return value_sets


@functools.lru_cache(maxsize=1)
def _value_sets() -> dict[tuple[str, str], dict[str, Any]]:
    return load_value_sets()


def value_sets_digest(path: Path = VALUE_SETS_PATH) -> str:
    return canonical_digest(_load(path))


def _categorical_dimension(envelope: dict[str, Any]) -> tuple[bool, str | None]:
    """Return (recognized, dimension) for an envelope under the shared value sets.

    Only a present value can be placed in a dimension. A non-present record of a
    value-set code has no value, so it stays in the dimension-less entry.
    """

    measurement = envelope["measurement"]
    value_set = _value_sets().get((measurement["code"]["system"], measurement["code"]["code"]))
    if envelope["missingness"]["status"] != "present":
        return True, None
    if value_set is None:
        return measurement["value_type"] != "categorical", None
    if measurement["value_type"] != "categorical" or measurement["domain"] != value_set["domain"]:
        return False, None
    matches = [name for name, values in value_set["dimensions"].items() if measurement["value"] in values]
    if len(matches) != 1:
        return False, None
    return True, matches[0]


def _entry_key(envelope: dict[str, Any]) -> tuple[str, str, str, str]:
    measurement = envelope["measurement"]
    dimension = _categorical_dimension(envelope)[1] or ""
    return (measurement["domain"], measurement["code"]["system"], measurement["code"]["code"], dimension)


def _key_tuple(key: dict[str, Any]) -> tuple[str, str, str, str]:
    return (key["domain"], key["system"], key["code"], key.get("dimension", ""))


def _reference_time(envelope: dict[str, Any]) -> datetime:
    timing = envelope["time"]
    return _time(timing["effective_end"] or timing["effective_start"])


def _dedupe(envelopes: Iterable[dict[str, Any]]) -> dict[str, tuple[dict[str, Any], str]]:
    by_id: dict[str, tuple[dict[str, Any], str]] = {}
    for envelope in envelopes:
        validate_observation(envelope)
        digest = envelope_digest(envelope)
        observation_id = envelope["observation_id"]
        if observation_id in by_id:
            if by_id[observation_id][1] != digest:
                _reject(
                    "conflicting_replay",
                    f"Observation {observation_id} was replayed with different content",
                )
            continue
        by_id[observation_id] = (copy.deepcopy(envelope), digest)
    return by_id


def _revocation_code(envelope: dict[str, Any], revoked: set[str]) -> str | None:
    if envelope["source"]["record_ref"] in revoked or envelope["source"]["source_id"] in revoked:
        return "source_revoked"
    if envelope["consent"]["consent_ref"] in revoked or envelope["consent"]["authority_ref"] in revoked:
        return "consent_revoked"
    if envelope["subject_binding"]["revocation_ref"] in revoked or envelope["subject_binding"]["binding_ref"] in revoked:
        return "binding_revoked"
    link = envelope.get("clinical_link")
    if link and (link["clinical_version_ref"] in revoked or link["admitted_observation_id"] in revoked):
        return "source_revoked"
    return None


def _exclusion(
    envelope: dict[str, Any],
    as_of: datetime,
    purpose: str,
    revoked: set[str],
) -> str | None:
    code = _revocation_code(envelope, revoked)
    if code is not None:
        return code
    consent = envelope["consent"]
    if _time(consent["granted_at"]) > as_of:
        return "consent_not_yet_granted"
    if consent["expires_at"] is not None and _time(consent["expires_at"]) <= as_of:
        return "consent_expired"
    if purpose not in consent["purposes"]:
        return "purpose_not_permitted"
    if _time(envelope["time"]["ingested_at"]) > as_of:
        return "not_yet_ingested"
    if _time(envelope["time"]["effective_start"]) > as_of:
        return "effective_after_as_of"
    validation = envelope.get("validation")
    if validation is not None and _time(validation["validated_at"]) > as_of:
        # A receipt dated after as_of did not exist at as_of (decision 8).
        return "validation_after_as_of"
    if _normalize(envelope) is None:
        return "unit_unrecognized"
    if not _categorical_dimension(envelope)[0]:
        return "categorical_value_unrecognized"
    return None


def _resolve_exclusions(
    inputs: dict[str, tuple[dict[str, Any], str]],
    as_of: datetime,
    purpose: str,
    revoked: set[str],
) -> dict[str, str]:
    """Exclusion code per observation id; derivation parents propagate exclusion."""

    excluded: dict[str, str] = {}
    state: dict[str, str] = {}

    def visit(observation_id: str) -> str | None:
        if state.get(observation_id) == "done":
            return excluded.get(observation_id)
        if state.get(observation_id) == "visiting":
            _reject("derivation_cycle", f"Derivation cycle through {observation_id}")
        state[observation_id] = "visiting"
        envelope, _ = inputs[observation_id]
        code = _exclusion(envelope, as_of, purpose, revoked)
        if code is None and "derivation" in envelope:
            for parent in envelope["derivation"]["parents"]:
                parent_id = parent["observation_id"]
                if parent_id not in inputs:
                    code = "derivation_parent_missing"
                    break
                if inputs[parent_id][1] != parent["envelope_digest"]:
                    code = "derivation_parent_digest_mismatch"
                    break
                if inputs[parent_id][0]["subject"] != envelope["subject"]:
                    code = "derivation_parent_subject_mismatch"
                    break
                if visit(parent_id) is not None:
                    code = "derivation_parent_excluded"
                    break
        state[observation_id] = "done"
        if code is not None:
            excluded[observation_id] = code
        return code

    for observation_id in sorted(inputs):
        visit(observation_id)
    return excluded


def _check_source_identity(inputs: dict[str, tuple[dict[str, Any], str]]) -> None:
    """Reject inputs whose source identity or entry key is ambiguous.

    Consumers mint envelopes independently (Metabolog, TwinSuite, ProvidEHR), so
    the assembler must not let an identity disagreement turn into silent
    corroboration, silent version selection or a silently split entry:

    * one ``record_ref`` belongs to exactly one ``source_id``; two emitters that
      claim the same source record under different source identities would
      otherwise count as two agreeing sources (``source_identity_conflict``);
    * one ``record_ref`` names one immutable record, so it carries one
      ``record_digest``; a revised record needs a version-specific
      ``record_ref`` so that the superseded version can be revoked on its own
      (``record_version_conflict``);
    * one coded concept (``system`` + ``code``) lives in exactly one domain;
      otherwise disagreeing values would be assembled into two separate
      entries and never be reported as a conflict (``code_domain_ambiguous``).
    """

    record_sources: dict[str, str] = {}
    record_digests: dict[str, str] = {}
    code_domains: dict[tuple[str, str], str] = {}
    for observation_id in sorted(inputs):
        envelope, _ = inputs[observation_id]
        source = envelope["source"]
        record_ref = source["record_ref"]
        if record_sources.setdefault(record_ref, source["source_id"]) != source["source_id"]:
            _reject(
                "source_identity_conflict",
                f"Source record {record_ref} is claimed by more than one source_id",
            )
        if record_digests.setdefault(record_ref, source["record_digest"]) != source["record_digest"]:
            _reject(
                "record_version_conflict",
                f"Source record {record_ref} appears with more than one record_digest; "
                "use a version-specific record_ref",
            )
        measurement = envelope["measurement"]
        concept = (measurement["code"]["system"], measurement["code"]["code"])
        if code_domains.setdefault(concept, measurement["domain"]) != measurement["domain"]:
            _reject(
                "code_domain_ambiguous",
                f"Code {concept[0]}|{concept[1]} is used in more than one domain",
            )


def _candidate(envelope: dict[str, Any], digest: str, as_of: datetime) -> dict[str, Any]:
    value, unit = _normalize(envelope)  # type: ignore[misc]
    domain = envelope["measurement"]["domain"]
    age = (as_of - _reference_time(envelope)).total_seconds()
    return {
        "observation_id": envelope["observation_id"],
        "envelope_digest": digest,
        "source": copy.deepcopy(envelope["source"]),
        "origin": envelope["origin"],
        "epistemic_status": envelope["epistemic_status"],
        "context_level": envelope["context_level"],
        "effective_start": envelope["time"]["effective_start"],
        "effective_end": envelope["time"]["effective_end"],
        "clock_status": envelope["time"]["clock"]["status"],
        "missingness": envelope["missingness"]["status"],
        "value": value,
        "unit": unit,
        "source_value": envelope["measurement"]["value"],
        "source_unit": envelope["measurement"]["unit"],
        "uncertainty": copy.deepcopy(envelope["uncertainty"]),
        "quality": copy.deepcopy(envelope["quality"]),
        "derivation": copy.deepcopy(envelope.get("derivation")),
        "clinical_link": copy.deepcopy(envelope.get("clinical_link")),
        "validation": copy.deepcopy(envelope.get("validation")),
        "freshness": "current" if age <= MAX_AGE_SECONDS[domain] else "stale",
    }


def _order(candidate: dict[str, Any]) -> tuple[datetime, str]:
    return (_utc(candidate["effective_end"] or candidate["effective_start"]), candidate["observation_id"])


def _independent_units(groups: dict[str, list[dict[str, Any]]]) -> int:
    """Count independent sources among per-source groups (decision 11).

    Two source groups are one unit when any of their candidates share a
    ``record_ref`` or a ``record_digest``: another adapter, connection or emitter
    that reaches the same underlying record is not independent corroboration.
    Distinct ``source_id`` values alone are never enough.
    """

    parent = {source_id: source_id for source_id in groups}

    def find(item: str) -> str:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    owners: dict[tuple[str, str], str] = {}
    for source_id in sorted(groups):
        for candidate in groups[source_id]:
            for marker in (("ref", candidate["source"]["record_ref"]), ("digest", candidate["source"]["record_digest"])):
                other = owners.setdefault(marker, source_id)
                if other != source_id:
                    parent[find(source_id)] = find(other)
    return len({find(source_id) for source_id in groups})


def _entry(key: tuple[str, str, str, str], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = sorted(candidates, key=_order)
    present = [c for c in candidates if c["missingness"] == "present"]
    current = [c for c in present if c["freshness"] == "current"]
    measured = [c for c in current if c["epistemic_status"] not in NON_MEASUREMENT]

    # Latest current measurement per exact source. Sources are never ranked
    # against each other.
    # Candidates from one source that share its latest reference time are all
    # kept: picking one of them by observation_id would be a silent
    # within-source priority (for example a said and a confirmed statement, or
    # two readings a device stamped with the same time). Disagreement among
    # them is a conflict like any other.
    latest: dict[str, list[dict[str, Any]]] = {}
    for candidate in measured:
        source_id = candidate["source"]["source_id"]
        group = latest.get(source_id)
        if group and _order(group[0])[0] == _order(candidate)[0]:
            group.append(candidate)
        else:
            latest[source_id] = [candidate]
    basis = sorted(
        (candidate for group in latest.values() for candidate in group),
        key=lambda c: c["observation_id"],
    )

    if basis:
        values = {json.dumps([c["value"], c["unit"]]) for c in basis}
        if len(values) == 1 and _independent_units(latest) == 1:
            resolution = "single_source"
        elif len(values) == 1:
            resolution = "concordant"
        else:
            resolution = "unresolved_conflict"
    elif any(c["epistemic_status"] in NON_MEASUREMENT for c in current):
        resolution = "imputed_only"
    elif present:
        resolution = "stale_only"
    else:
        resolution = "missing_only"

    blockers: set[str] = set()
    if resolution not in {"single_source", "concordant"}:
        blockers.add(f"resolution_{resolution}")
    for candidate in basis:
        if candidate["uncertainty"]["status"] == "unknown":
            blockers.add("uncertainty_unknown")
        if candidate["quality"]["status"] != "acceptable":
            blockers.add("quality_not_acceptable")
        if candidate["context_level"] != "individual":
            blockers.add("not_individual_measurement")
        if candidate["epistemic_status"] in MODEL_OUTPUT:
            blockers.add("model_output_requires_receipt")
        if candidate["clock_status"] == "unknown":
            blockers.add("clock_unknown")

    entry_key = {"domain": key[0], "system": key[1], "code": key[2]}
    if key[3]:
        entry_key["dimension"] = key[3]
    return {
        "key": entry_key,
        "resolution": resolution,
        "basis": [c["observation_id"] for c in basis],
        "candidates": candidates,
        "clinical_use": {
            "admission_candidate": not blockers,
            "blockers": sorted(blockers),
            "requires": "openbody.clinical-assertion-reference/1.0",
        },
    }


def current_contract() -> dict[str, Any]:
    """The contract pins every v1 snapshot carries and every verifier checks."""

    return {
        "observation_schema_digest": canonical_digest(_load(OBSERVATION_SCHEMA_PATH)),
        "registry_version": _load(REGISTRY_PATH)["registry_version"],
        "value_sets_version": VALUE_SETS_VERSION,
        "value_sets_digest": value_sets_digest(),
    }


def assemble_state(
    envelopes: Iterable[dict[str, Any]],
    *,
    subject: str,
    as_of: str,
    purpose: str,
    revoked: Iterable[str] = (),
) -> dict[str, Any]:
    """Assemble a deterministic whole-person state snapshot.

    ``revoked`` is the host-resolved set of revoked source, record, consent,
    authority and binding references at ``as_of``. It is input, not something
    this function looks up, so the same inputs always yield the same snapshot.
    """

    if purpose not in PURPOSES:
        _reject("purpose_unsupported", f"Unsupported purpose: {purpose}")
    try:
        as_of_time = _time(as_of)
    except (AttributeError, ValueError) as error:
        _reject("structural_invalid", f"as_of is not an RFC 3339 timestamp: {error}")
    if as_of_time.tzinfo is None:
        _reject("structural_invalid", "as_of must carry a UTC offset")

    inputs = _dedupe(envelopes)
    for envelope, _ in inputs.values():
        if envelope["subject"] != subject:
            _reject(
                "subject_mismatch",
                f"Observation {envelope['observation_id']} is bound to another subject",
            )
    _check_source_identity(inputs)
    revoked_set = set(revoked)
    excluded = _resolve_exclusions(inputs, as_of_time, purpose, revoked_set)

    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for observation_id in sorted(inputs):
        if observation_id in excluded:
            continue
        envelope, digest = inputs[observation_id]
        grouped.setdefault(_entry_key(envelope), []).append(_candidate(envelope, digest, as_of_time))

    snapshot: dict[str, Any] = {
        "schema_version": STATE_VERSION,
        "subject": subject,
        "as_of": _iso(as_of_time.astimezone(timezone.utc)),
        "purpose": purpose,
        "policy": {
            "policy_version": POLICY_VERSION,
            "clock_skew_tolerance_seconds": CLOCK_SKEW_TOLERANCE_SECONDS,
            "max_age_seconds": dict(sorted(MAX_AGE_SECONDS.items())),
        },
        "contract": current_contract(),
        "revocations_applied": sorted(revoked_set),
        "subject_bindings": sorted({e["subject_binding"]["binding_ref"] for e, _ in inputs.values()}),
        "inputs": [
            {"observation_id": observation_id, "envelope_digest": inputs[observation_id][1]}
            for observation_id in sorted(inputs)
        ],
        "entries": [_entry(key, grouped[key]) for key in sorted(grouped)],
        "exclusions": [
            {
                "observation_id": observation_id,
                "envelope_digest": inputs[observation_id][1],
                "code": excluded[observation_id],
            }
            for observation_id in sorted(excluded)
        ],
        "claim_boundary": {
            "projection_class": "state_projection",
            "clinical_assertion": False,
            "authority_granted": False,
            "source_priority": "none",
        },
    }
    snapshot["snapshot_digest"] = canonical_digest(snapshot)
    return snapshot


def validate_state(snapshot: dict[str, Any]) -> None:
    """Validate a snapshot's structure and its self-digest."""

    errors = _schema_errors(STATE_SCHEMA_PATH, snapshot)
    if errors:
        _reject("structural_invalid", errors[0])
    body = {k: v for k, v in snapshot.items() if k != "snapshot_digest"}
    if canonical_digest(body) != snapshot["snapshot_digest"]:
        _reject("snapshot_digest_mismatch", "snapshot_digest does not match content")
    if snapshot["contract"] != current_contract():
        _reject(
            "contract_mismatch",
            "Snapshot contract pins (observation schema, registry, value sets) differ from this verifier's",
        )
    as_of = _time(snapshot["as_of"])
    input_digests = {i["observation_id"]: i["envelope_digest"] for i in snapshot["inputs"]}
    for entry in snapshot["entries"]:
        for candidate in entry["candidates"]:
            if input_digests.get(candidate["observation_id"]) != candidate["envelope_digest"]:
                _reject("provenance_lost", f"Candidate {candidate['observation_id']} is not a listed input")
            if candidate["epistemic_status"] in NON_MEASUREMENT and candidate["observation_id"] in entry["basis"]:
                _reject("imputation_as_measurement", "An imputed candidate is part of a measurement basis")
            validation = candidate["validation"]
            if validation is not None and _time(validation["validated_at"]) > as_of:
                _reject(
                    "validation_after_as_of",
                    f"Candidate {candidate['observation_id']} carries a validation dated after as_of",
                )
        if entry["resolution"] == "unresolved_conflict" and entry["clinical_use"]["admission_candidate"]:
            _reject("conflict_admitted", "An unresolved conflict cannot be an admission candidate")
        _check_value_set_placement(entry)
    _check_state_consistency(snapshot)


def _check_value_set_placement(entry: dict[str, Any]) -> None:
    """A categorical entry's dimension must be what the shared value sets give its values.

    This is the part of candidate placement that a snapshot can show on its own.
    Placement against the source envelopes is ``verify_state_against_inputs``.
    """

    key = entry["key"]
    value_set = _value_sets().get((key["system"], key["code"]))
    dimension = key.get("dimension")
    present = [c for c in entry["candidates"] if c["missingness"] == "present"]
    if value_set is None:
        if dimension is not None:
            _reject("candidate_misplaced", f"Entry {key['code']} has a dimension but the code has no value set")
        return
    if value_set["domain"] != key["domain"]:
        _reject("candidate_misplaced", f"Entry {key['code']} is not in its value-set domain")
    if dimension is None:
        if present:
            _reject("candidate_misplaced", f"Entry {key['code']} holds categorical values without a dimension")
        return
    allowed = value_set["dimensions"].get(dimension)
    if allowed is None:
        _reject("candidate_misplaced", f"Entry {key['code']} names unknown dimension {dimension}")
    for candidate in present:
        if candidate["value"] not in allowed:
            _reject(
                "candidate_misplaced",
                f"Candidate {candidate['observation_id']} value is not in dimension {dimension} of {key['code']}",
            )


def _check_state_consistency(snapshot: dict[str, Any]) -> None:
    """Every entry must be exactly what policy 1.0 derives from its candidates.

    A re-digested snapshot can otherwise claim a basis that is not a candidate,
    an admission candidate that still has blockers, or drop a blocker, and
    downstream consumers would have no way to tell. Every input must also be
    accounted for exactly once, as a candidate or as an exclusion.
    """

    inputs = {item["observation_id"]: item["envelope_digest"] for item in snapshot["inputs"]}
    if len(inputs) != len(snapshot["inputs"]):
        _reject("state_inconsistent", "An input is listed more than once")
    accounted: dict[str, str] = {}
    keys: set[tuple[str, str, str, str]] = set()
    for entry in snapshot["entries"]:
        key = _key_tuple(entry["key"])
        if key in keys:
            _reject("state_inconsistent", f"Entry key {key} appears more than once")
        keys.add(key)
        for candidate in entry["candidates"]:
            if candidate["observation_id"] in accounted:
                _reject("state_inconsistent", f"Input {candidate['observation_id']} is accounted for twice")
            accounted[candidate["observation_id"]] = "candidate"
        candidate_ids = {candidate["observation_id"] for candidate in entry["candidates"]}
        stray = [observation_id for observation_id in entry["basis"] if observation_id not in candidate_ids]
        if stray:
            _reject("provenance_lost", f"Basis {stray[0]} is not a candidate of its entry")
        expected = _entry(key, entry["candidates"])
        for field in ("resolution", "basis", "candidates", "clinical_use"):
            if expected[field] != entry[field]:
                _reject(
                    "state_inconsistent",
                    f"Entry {key[2]} {field} is not what the assembly policy derives from its candidates",
                )
    for exclusion in snapshot["exclusions"]:
        observation_id = exclusion["observation_id"]
        if inputs.get(observation_id) != exclusion["envelope_digest"]:
            _reject("provenance_lost", f"Exclusion {observation_id} is not a listed input")
        if observation_id in accounted:
            _reject("state_inconsistent", f"Input {observation_id} is accounted for twice")
        accounted[observation_id] = "excluded"
    missing = sorted(set(inputs) - set(accounted))
    if missing:
        _reject("state_inconsistent", f"Input {missing[0]} is neither a candidate nor an exclusion")


def _inputs_by_id(snapshot: dict[str, Any], envelopes: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Resolve every listed snapshot input to its envelope, bound by digest."""

    supplied = _dedupe(envelopes)
    resolved: dict[str, dict[str, Any]] = {}
    for item in snapshot["inputs"]:
        found = supplied.get(item["observation_id"])
        if found is None:
            _reject("provenance_lost", f"Input {item['observation_id']} has no supplied envelope")
        if found[1] != item["envelope_digest"]:
            _reject("provenance_lost", f"Input {item['observation_id']} envelope digest does not match the snapshot")
        resolved[item["observation_id"]] = found[0]
    return resolved


def verify_state_against_inputs(snapshot: dict[str, Any], envelopes: Iterable[dict[str, Any]]) -> None:
    """Validate a snapshot against the envelopes it lists (decision 10).

    v1 candidates do not repeat their measurement code, so a snapshot on its own
    cannot show that a candidate sits under the right key. Given the input
    envelopes, this checks:

    * every listed input has an envelope with that exact digest (``provenance_lost``);
    * each candidate sits under the key (domain, system, code and value-set
      dimension) of its own envelope (``candidate_misplaced``);
    * each candidate equals what the policy derives from its envelope at
      ``as_of`` (``candidate_mismatch``);
    * the whole snapshot is exactly what the assembler produces from these
      envelopes, ``as_of``, purpose and revocations (``state_not_reproducible``).

    An explicit key on candidates in 1.1 (#47) will not replace this check.
    """

    validate_state(snapshot)
    by_id = _inputs_by_id(snapshot, envelopes)
    as_of = _time(snapshot["as_of"])
    for entry in snapshot["entries"]:
        key = _key_tuple(entry["key"])
        for candidate in entry["candidates"]:
            envelope = by_id[candidate["observation_id"]]
            if _entry_key(envelope) != key:
                _reject(
                    "candidate_misplaced",
                    f"Candidate {candidate['observation_id']} is filed under {key[2]} "
                    f"but its envelope is {_entry_key(envelope)[2]}",
                )
            if _candidate(envelope, candidate["envelope_digest"], as_of) != candidate:
                _reject(
                    "candidate_mismatch",
                    f"Candidate {candidate['observation_id']} differs from what its envelope derives",
                )
    rebuilt = assemble_state(
        list(by_id.values()),
        subject=snapshot["subject"],
        as_of=snapshot["as_of"],
        purpose=snapshot["purpose"],
        revoked=snapshot["revocations_applied"],
    )
    if rebuilt != snapshot:
        _reject("state_not_reproducible", "The snapshot is not what these inputs assemble to")


def present_use(
    snapshot: dict[str, Any],
    envelopes: Iterable[dict[str, Any]],
    current_revoked: Iterable[str],
) -> dict[str, Any]:
    """Apply the *current* revocation set to a snapshot before present use (decision 8).

    A snapshot records the revocations resolved at its ``as_of``. A revocation
    that arrives later still constrains any present use of that historical
    snapshot. This returns every candidate whose source, record, clinical version,
    consent, authority or subject binding is revoked now, together with every
    candidate derived from one of them, and the entries whose ``basis`` they
    touch. It does not re-date the snapshot. The current set cannot establish
    what was authorized at an earlier time; that needs time-aware revocation
    evidence (#47).
    """

    verify_state_against_inputs(snapshot, envelopes)
    by_id = _inputs_by_id(snapshot, envelopes)
    revoked = set(current_revoked)
    codes: dict[str, str] = {}

    def revocation(observation_id: str, trail: tuple[str, ...]) -> str | None:
        if observation_id in codes:
            return codes[observation_id]
        envelope = by_id.get(observation_id)
        if envelope is None or observation_id in trail:
            return None
        # Only revocation applies here; time, consent window and purpose were
        # judged at as_of and are not re-dated.
        code = _revocation_code(envelope, revoked)
        if code is None:
            for parent in envelope.get("derivation", {}).get("parents", []):
                if revocation(parent["observation_id"], trail + (observation_id,)) is not None:
                    code = "derivation_parent_revoked"
                    break
        if code is not None:
            codes[observation_id] = code
        return code

    candidate_ids = [c["observation_id"] for e in snapshot["entries"] for c in e["candidates"]]
    for observation_id in sorted(candidate_ids):
        revocation(observation_id, ())
    affected = {observation_id: codes[observation_id] for observation_id in sorted(candidate_ids) if observation_id in codes}
    entries = [
        entry["key"]
        for entry in snapshot["entries"]
        if any(candidate["observation_id"] in affected for candidate in entry["candidates"])
    ]
    basis_affected = [
        entry["key"]
        for entry in snapshot["entries"]
        if any(observation_id in affected for observation_id in entry["basis"])
    ]
    return {
        "usable": not affected,
        "affected": affected,
        "entries_affected": entries,
        "basis_affected": basis_affected,
    }


def require_present_use(
    snapshot: dict[str, Any],
    envelopes: Iterable[dict[str, Any]],
    current_revoked: Iterable[str],
) -> None:
    """Raise ``revoked_since_snapshot`` unless no candidate is revoked now."""

    report = present_use(snapshot, envelopes, current_revoked)
    if not report["usable"]:
        first = next(iter(report["affected"]))
        _reject(
            "revoked_since_snapshot",
            f"Candidate {first} is revoked now ({report['affected'][first]}); the snapshot cannot be used as is",
        )


# ---------------------------------------------------------------------------
# Shared conformance corpus (fixtures/whole-person-state/v1)
# ---------------------------------------------------------------------------

CORPUS_DIR = ROOT / "fixtures" / "whole-person-state" / "v1"
CORPUS_INPUTS_PATH = CORPUS_DIR / "inputs.json"
CORPUS_GOLDEN_PATH = CORPUS_DIR / "snapshot.golden.json"
CORPUS_VECTORS_PATH = CORPUS_DIR / "vectors.json"


class ConformanceResult:
    """Outcome of one corpus vector; ``failures`` is empty when it passed."""

    def __init__(self, name: str, failures: list[str], detail: str):
        self.name = name
        self.failures = failures
        self.detail = detail

    @property
    def passed(self) -> bool:
        return not self.failures


def _merge_patch(target: Any, patch: Any) -> Any:
    from .clinical_reference import merge_patch

    return merge_patch(target, patch)


def _pointer_parts(pointer: str) -> list[str]:
    if not pointer.startswith("/"):
        raise ValueError(f"JSON pointer must start with '/': {pointer}")
    return [part.replace("~1", "/").replace("~0", "~") for part in pointer[1:].split("/")]


def _pointer_apply(document: Any, operation: dict[str, Any]) -> None:
    parts = _pointer_parts(operation["path"])
    parent = document
    for part in parts[:-1]:
        parent = parent[int(part)] if isinstance(parent, list) else parent[part]
    last = parts[-1]
    if operation["op"] == "set":
        if isinstance(parent, list):
            parent[int(last)] = copy.deepcopy(operation["value"])
        else:
            parent[last] = copy.deepcopy(operation["value"])
    elif operation["op"] == "remove":
        if isinstance(parent, list):
            del parent[int(last)]
        else:
            del parent[last]
    else:
        raise ValueError(f"Unsupported state operation: {operation['op']}")


def _rebind_parent_digests(envelopes: list[dict[str, Any]]) -> None:
    """Recompute derivation parent digests so a patch does not cascade by accident."""

    by_id = {envelope["observation_id"]: envelope for envelope in envelopes}
    done: set[str] = set()

    def visit(envelope: dict[str, Any], trail: tuple[str, ...]) -> None:
        observation_id = envelope["observation_id"]
        if observation_id in done or observation_id in trail:
            return
        for parent in envelope.get("derivation", {}).get("parents", []):
            parent_envelope = by_id.get(parent["observation_id"])
            if parent_envelope is not None:
                visit(parent_envelope, trail + (observation_id,))
                parent["envelope_digest"] = envelope_digest(parent_envelope)
        done.add(observation_id)

    for envelope in envelopes:
        visit(envelope, ())


def _apply_input_operations(
    envelopes: list[dict[str, Any]], operations: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    envelopes = copy.deepcopy(envelopes)

    def find(observation_id: str) -> int:
        for index, envelope in enumerate(envelopes):
            if envelope["observation_id"] == observation_id:
                return index
        raise ValueError(f"Vector references unknown observation {observation_id}")

    for operation in operations:
        kind = operation["op"]
        if kind == "patch":
            index = find(operation["observation_id"])
            envelopes[index] = _merge_patch(envelopes[index], operation["patch"])
        elif kind in {"set", "unset"}:
            # JSON-pointer edits inside one envelope; unlike merge-patch they can
            # set an explicit null.
            _pointer_apply(
                envelopes[find(operation["observation_id"])],
                {"op": "set" if kind == "set" else "remove", "path": operation["path"], "value": operation.get("value")},
            )
        elif kind == "remove":
            del envelopes[find(operation["observation_id"])]
        elif kind == "add":
            base = envelopes[find(operation["from"])]
            envelopes.append(_merge_patch(base, operation["patch"]))
        elif kind == "duplicate":
            envelopes.append(copy.deepcopy(envelopes[find(operation["observation_id"])]))
        elif kind == "reverse":
            envelopes.reverse()
        else:
            raise ValueError(f"Unsupported input operation: {kind}")
    return envelopes


def _check_accepted(
    snapshot: dict[str, Any], expect: dict[str, Any], golden: dict[str, Any]
) -> list[str]:
    failures: list[str] = []
    try:
        validate_state(snapshot)
    except WholePersonStateError as error:
        failures.append(f"assembled snapshot fails validate_state: {error.code}")
    if "snapshot_equals_golden" in expect:
        equal = snapshot == golden
        if equal != expect["snapshot_equals_golden"]:
            failures.append(f"snapshot_equals_golden expected {expect['snapshot_equals_golden']}, got {equal}")
    actual_exclusions = {item["observation_id"]: item["code"] for item in snapshot["exclusions"]}
    if "exclusions" in expect and actual_exclusions != expect["exclusions"]:
        failures.append(f"exclusions expected {expect['exclusions']}, got {actual_exclusions}")
    for observation_id, code in expect.get("exclusions_include", {}).items():
        if actual_exclusions.get(observation_id) != code:
            failures.append(f"exclusion {observation_id} expected {code}, got {actual_exclusions.get(observation_id)}")
    for expected in expect.get("entries", []):
        # An entry is named by its code, plus its value-set dimension when a code
        # has more than one entry (decision 3).
        matches = [
            entry
            for entry in snapshot["entries"]
            if entry["key"]["code"] == expected["code"]
            and ("dimension" not in expected or entry["key"].get("dimension") == expected["dimension"])
        ]
        if len(matches) > 1:
            failures.append(f"entry {expected['code']} is ambiguous; the vector must name its dimension")
            continue
        entry = matches[0] if matches else None
        if "dimension" in expected and entry is not None and entry["key"].get("dimension") != expected["dimension"]:
            entry = None
        if entry is None:
            if not expected.get("absent"):
                failures.append(f"entry {expected['code']} missing")
            continue
        if expected.get("absent"):
            failures.append(f"entry {expected['code']} present but expected absent")
            continue
        for field in ("resolution", "basis"):
            if field in expected and entry[field] != expected[field]:
                failures.append(f"entry {expected['code']} {field} expected {expected[field]}, got {entry[field]}")
        if "admission_candidate" in expected and (
            entry["clinical_use"]["admission_candidate"] != expected["admission_candidate"]
        ):
            failures.append(
                f"entry {expected['code']} admission_candidate expected {expected['admission_candidate']}"
            )
        missing = sorted(set(expected.get("blockers_include", [])) - set(entry["clinical_use"]["blockers"]))
        if missing:
            failures.append(f"entry {expected['code']} missing blockers {missing}")
        if "blockers" in expected and entry["clinical_use"]["blockers"] != expected["blockers"]:
            failures.append(
                f"entry {expected['code']} blockers expected {expected['blockers']}, got {entry['clinical_use']['blockers']}"
            )
        candidates = {candidate["observation_id"]: candidate for candidate in entry["candidates"]}
        for observation_id, fields in expected.get("candidates", {}).items():
            candidate = candidates.get(observation_id)
            if candidate is None:
                failures.append(f"entry {expected['code']} lacks candidate {observation_id}")
                continue
            for field, value in fields.items():
                if candidate.get(field) != value:
                    failures.append(
                        f"candidate {observation_id} {field} expected {value!r}, got {candidate.get(field)!r}"
                    )
    return failures


def evaluate_conformance_corpus(corpus_dir: Path = CORPUS_DIR) -> list[ConformanceResult]:
    """Evaluate the golden snapshot and every adversarial vector in the corpus."""

    inputs = _load(corpus_dir / CORPUS_INPUTS_PATH.name)
    golden = _load(corpus_dir / CORPUS_GOLDEN_PATH.name)
    vectors = _load(corpus_dir / CORPUS_VECTORS_PATH.name)
    results: list[ConformanceResult] = []

    def assemble(envelopes: list[dict[str, Any]], params: dict[str, Any]) -> dict[str, Any]:
        return assemble_state(
            envelopes,
            subject=params.get("subject", inputs["subject"]),
            as_of=params.get("as_of", inputs["as_of"]),
            purpose=params.get("purpose", inputs["purpose"]),
            revoked=params.get("revoked", inputs["revoked"]),
        )

    failures: list[str] = []
    try:
        for envelope in inputs["envelopes"]:
            validate_observation(envelope)
        assembled = assemble(inputs["envelopes"], {})
        validate_state(golden)
        if assembled != golden:
            failures.append("assembled snapshot differs from snapshot.golden.json")
    except WholePersonStateError as error:
        failures.append(f"golden inputs rejected: {error.code}: {error}")
    results.append(ConformanceResult("golden-snapshot", failures, golden.get("snapshot_digest", "")))

    if (corpus_dir / FROZEN_MANIFEST_PATH.name).is_file():
        results.append(
            ConformanceResult(
                "frozen-v1-manifest",
                frozen_manifest_failures(corpus_dir / FROZEN_MANIFEST_PATH.name),
                _load(corpus_dir / FROZEN_MANIFEST_PATH.name)["manifest_id"],
            )
        )

    def golden_variant(vector: dict[str, Any]) -> dict[str, Any]:
        snapshot = copy.deepcopy(golden)
        for operation in vector.get("operations", []):
            _pointer_apply(snapshot, operation)
        if vector.get("redigest"):
            snapshot.pop("snapshot_digest", None)
            snapshot["snapshot_digest"] = canonical_digest(snapshot)
        return snapshot

    def expect_code(expect: dict[str, Any], actual_code: str | None) -> list[str]:
        detail = f"rejected ({actual_code})" if actual_code else "accepted"
        if expect["outcome"] == "rejected" and actual_code != expect["error_code"]:
            return [f"expected rejected/{expect['error_code']}, got {detail}"]
        if expect["outcome"] == "accepted" and actual_code is not None:
            return [f"expected accepted, got {detail}"]
        return []

    for vector in vectors["vectors"]:
        expect = vector["expect"]
        failures = []
        detail = ""
        if vector.get("target") == "state_with_inputs":
            # Decision 10: placement of each candidate against its source envelope.
            snapshot = golden_variant(vector)
            envelopes = _apply_input_operations(inputs["envelopes"], vector.get("input_operations", []))
            actual_code = None
            try:
                verify_state_against_inputs(snapshot, envelopes)
            except WholePersonStateError as error:
                actual_code = error.code
            detail = f"rejected ({actual_code})" if actual_code else "accepted"
            results.append(ConformanceResult(vector["name"], expect_code(expect, actual_code), detail))
            continue
        if vector.get("target") == "present_use":
            # Decision 8: current revocations constrain present use of a historical snapshot.
            snapshot = golden_variant(vector)
            current = vector["params"]["current_revoked"]
            actual_code = None
            report: dict[str, Any] = {"affected": {}}
            try:
                report = present_use(snapshot, inputs["envelopes"], current)
                require_present_use(snapshot, inputs["envelopes"], current)
            except WholePersonStateError as error:
                actual_code = error.code
            detail = f"rejected ({actual_code})" if actual_code else "accepted"
            failures = expect_code(expect, actual_code)
            if "affected" in expect and report["affected"] != expect["affected"]:
                failures.append(f"affected expected {expect['affected']}, got {report['affected']}")
            if "affected_count" in expect and len(report["affected"]) != expect["affected_count"]:
                failures.append(f"affected_count expected {expect['affected_count']}, got {len(report['affected'])}")
            results.append(ConformanceResult(vector["name"], failures, detail))
            continue
        if vector.get("target") == "state":
            snapshot = copy.deepcopy(golden)
            for operation in vector["operations"]:
                _pointer_apply(snapshot, operation)
            if vector.get("redigest"):
                snapshot.pop("snapshot_digest", None)
                snapshot["snapshot_digest"] = canonical_digest(snapshot)
            actual_code = None
            try:
                validate_state(snapshot)
            except WholePersonStateError as error:
                actual_code = error.code
            detail = f"rejected ({actual_code})" if actual_code else "accepted"
            if expect["outcome"] == "rejected" and actual_code != expect["error_code"]:
                failures.append(f"expected rejected/{expect['error_code']}, got {detail}")
            if expect["outcome"] == "accepted" and actual_code is not None:
                failures.append(f"expected accepted, got {detail}")
            results.append(ConformanceResult(vector["name"], failures, detail))
            continue

        envelopes = _apply_input_operations(inputs["envelopes"], vector.get("operations", []))
        if vector.get("rebind_parent_digests", True):
            _rebind_parent_digests(envelopes)
        try:
            snapshot = assemble(envelopes, vector.get("params", {}))
        except WholePersonStateError as error:
            detail = f"rejected ({error.code})"
            if expect["outcome"] != "rejected" or error.code != expect["error_code"]:
                failures.append(f"expected {expect['outcome']}/{expect.get('error_code')}, got {detail}")
        else:
            detail = "accepted"
            if expect["outcome"] != "accepted":
                failures.append(f"expected rejected/{expect.get('error_code')}, got accepted")
            else:
                failures.extend(_check_accepted(snapshot, expect, golden))
        results.append(ConformanceResult(vector["name"], failures, detail))
    return results


FROZEN_MANIFEST_PATH = CORPUS_DIR / "frozen-manifest.json"


def frozen_manifest_failures(manifest_path: Path = FROZEN_MANIFEST_PATH) -> list[str]:
    """Check the frozen v1 baseline: every pinned artifact still has its SHA-256.

    A change to any pinned file is a new contract version (additive 1.1 or 2.0,
    tracked in #47), never an edit of v1. Regenerating a golden file does not
    unfreeze it.
    """

    import hashlib

    manifest = _load(manifest_path)
    failures: list[str] = []
    for item in manifest["files"]:
        path = ROOT / item["path"]
        if not path.is_file():
            failures.append(f"{item['path']} is missing")
            continue
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != item["sha256"]:
            failures.append(f"{item['path']} changed after the v1 freeze (sha256 {actual})")
    versions = manifest["versions"]
    expected = {
        "observation": OBSERVATION_VERSION,
        "state": STATE_VERSION,
        "assembly_policy": POLICY_VERSION,
        "value_sets": VALUE_SETS_VERSION,
    }
    for key, value in expected.items():
        if versions.get(key) != value:
            failures.append(f"manifest version {key} is {versions.get(key)}, the implementation is {value}")
    if manifest["observation_schema_canonical_digest"] != current_contract()["observation_schema_digest"]:
        failures.append("observation schema canonical digest differs from the manifest")
    return failures


def write_golden_snapshot(corpus_dir: Path = CORPUS_DIR) -> dict[str, Any]:
    """Regenerate snapshot.golden.json from inputs.json (review the diff before committing)."""

    inputs = _load(corpus_dir / CORPUS_INPUTS_PATH.name)
    snapshot = assemble_state(
        inputs["envelopes"],
        subject=inputs["subject"],
        as_of=inputs["as_of"],
        purpose=inputs["purpose"],
        revoked=inputs["revoked"],
    )
    (corpus_dir / CORPUS_GOLDEN_PATH.name).write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return snapshot
