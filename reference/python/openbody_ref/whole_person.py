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
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from .validation import canonical_digest

ROOT = Path(__file__).resolve().parents[3]
OBSERVATION_SCHEMA_PATH = ROOT / "schemas" / "whole-person-observation.schema.json"
STATE_SCHEMA_PATH = ROOT / "schemas" / "whole-person-state.schema.json"
REGISTRY_PATH = ROOT / "registry" / "coordinates.json"

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


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _utc(value: str) -> datetime:
    return _time(value).astimezone(timezone.utc)


def _schema_errors(schema_path: Path, value: Any) -> list[str]:
    observation_schema = _load(OBSERVATION_SCHEMA_PATH)
    registry = Registry().with_resource(
        observation_schema["$id"], Resource.from_contents(observation_schema)
    )
    validator = Draft202012Validator(
        _load(schema_path), registry=registry, format_checker=FormatChecker()
    )
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


def _exclusion(
    envelope: dict[str, Any],
    as_of: datetime,
    purpose: str,
    revoked: set[str],
) -> str | None:
    if envelope["source"]["record_ref"] in revoked or envelope["source"]["source_id"] in revoked:
        return "source_revoked"
    if envelope["consent"]["consent_ref"] in revoked or envelope["consent"]["authority_ref"] in revoked:
        return "consent_revoked"
    if envelope["subject_binding"]["revocation_ref"] in revoked or envelope["subject_binding"]["binding_ref"] in revoked:
        return "binding_revoked"
    link = envelope.get("clinical_link")
    if link and (link["clinical_version_ref"] in revoked or link["admitted_observation_id"] in revoked):
        return "source_revoked"
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
    if _normalize(envelope) is None:
        return "unit_unrecognized"
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


def _entry(key: tuple[str, str, str], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = sorted(candidates, key=_order)
    present = [c for c in candidates if c["missingness"] == "present"]
    current = [c for c in present if c["freshness"] == "current"]
    measured = [c for c in current if c["epistemic_status"] not in NON_MEASUREMENT]

    # Latest current measurement per exact source. Sources are never ranked
    # against each other.
    latest: dict[str, dict[str, Any]] = {}
    for candidate in measured:
        latest[candidate["source"]["source_id"]] = candidate
    basis = sorted(latest.values(), key=lambda c: c["observation_id"])

    if basis:
        values = {json.dumps([c["value"], c["unit"]]) for c in basis}
        if len(basis) == 1:
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

    return {
        "key": {"domain": key[0], "system": key[1], "code": key[2]},
        "resolution": resolution,
        "basis": [c["observation_id"] for c in basis],
        "candidates": candidates,
        "clinical_use": {
            "admission_candidate": not blockers,
            "blockers": sorted(blockers),
            "requires": "openbody.clinical-assertion-reference/1.0",
        },
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
    revoked_set = set(revoked)
    excluded = _resolve_exclusions(inputs, as_of_time, purpose, revoked_set)

    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for observation_id in sorted(inputs):
        if observation_id in excluded:
            continue
        envelope, digest = inputs[observation_id]
        measurement = envelope["measurement"]
        key = (measurement["domain"], measurement["code"]["system"], measurement["code"]["code"])
        grouped.setdefault(key, []).append(_candidate(envelope, digest, as_of_time))

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
        "contract": {
            "observation_schema_digest": canonical_digest(_load(OBSERVATION_SCHEMA_PATH)),
            "registry_version": _load(REGISTRY_PATH)["registry_version"],
        },
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
    input_digests = {i["observation_id"]: i["envelope_digest"] for i in snapshot["inputs"]}
    for entry in snapshot["entries"]:
        for candidate in entry["candidates"]:
            if input_digests.get(candidate["observation_id"]) != candidate["envelope_digest"]:
                _reject("provenance_lost", f"Candidate {candidate['observation_id']} is not a listed input")
            if candidate["epistemic_status"] in NON_MEASUREMENT and candidate["observation_id"] in entry["basis"]:
                _reject("imputation_as_measurement", "An imputed candidate is part of a measurement basis")
        if entry["resolution"] == "unresolved_conflict" and entry["clinical_use"]["admission_candidate"]:
            _reject("conflict_admitted", "An unresolved conflict cannot be an admission candidate")


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
    if "exclusions" in expect:
        actual = {item["observation_id"]: item["code"] for item in snapshot["exclusions"]}
        if actual != expect["exclusions"]:
            failures.append(f"exclusions expected {expect['exclusions']}, got {actual}")
    entries = {entry["key"]["code"]: entry for entry in snapshot["entries"]}
    for expected in expect.get("entries", []):
        entry = entries.get(expected["code"])
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

    for vector in vectors["vectors"]:
        expect = vector["expect"]
        failures = []
        detail = ""
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
