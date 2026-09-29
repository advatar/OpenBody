"""Shared healthcare trace: ProvidEHR -> OpenBody whole-person state -> Metabolog.

``fixtures/healthcare-trace/v1/trace.json`` (``openbody.healthcare-trace/1.0``)
is one synthetic end-to-end trace that three repositories replay:

* **ProvidEHR** (producer, Rust, ``crates/ambient-evidence``) replays the
  ``producer`` stage: TakeCare note reads through the qualified bounded-read
  boundary (#599/#601), ambient extraction, append-only clinician review,
  longitudinal state and the OpenBody export. Its output must equal
  ``producer.expect`` exactly.
* **OpenBody** (this module) replays the ``openbody`` stage: it re-maps every
  exported contribution with the reference ProvidEHR mapper (an independent
  implementation of the same rule), assembles the snapshot with the unchanged
  1.0 assembler, validates it, and checks the OpenBody rejection cases.
* **Metabolog** (consumer, Swift, ``SurrealHealthIndex``) replays the
  ``consumer`` stage: it ingests the snapshot into the temporal state graph.
  :func:`consume_snapshot` is the reference statement of the same consumer
  policy, so the expected outcomes in the fixture are generated here and
  checked natively there.

The contract is pinned by schema id and SHA-256 (``contract``); a replay
against different schema bytes fails before anything else is compared.

Trace profile rules on top of the 1.0 contract and mapping (no schema change):

* A ProvidEHR ambient envelope carries the quality flag ``clinician_reviewed``
  because only reviewed facts leave the review ledger. Review is still
  ``reported``, never ``clinician_validated`` and never uncertainty. The 1.0
  assembler cannot see review, so the consumer enforces it
  (``unreviewed_ambient_claim``). A typed field is acceptance question 4.
* The consumer re-derives provenance from the envelopes it was given: each
  listed input needs its envelope with the same digest, and each candidate's
  source, origin, epistemic status and missingness must equal its envelope
  (``provenance_lost``, ``imputed_as_observed``, ``missingness_altered``).
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from .validation import canonical_digest
from .whole_person import (
    OBSERVATION_SCHEMA_PATH,
    OBSERVATION_VERSION,
    POLICY_VERSION,
    ROOT,
    STATE_SCHEMA_PATH,
    STATE_VERSION,
    ConformanceResult,
    WholePersonStateError,
    _load,
    assemble_state,
    envelope_digest,
    validate_state,
)
from .whole_person_mapping import MAPPING_VERSION, MappingRefused, map_providehr_contribution

TRACE_VERSION = "openbody.healthcare-trace/1.0"
TRACE_DIR = ROOT / "fixtures" / "healthcare-trace" / "v1"
TRACE_PATH = TRACE_DIR / "trace.json"
REVIEW_FLAG = "clinician_reviewed"
HEDGE_FLAG = "speaker_hedged"
AMBIENT_SOURCE_PREFIX = "urn:providehr:source:"
# Producer refusals that happen before the 1.0 mapping is applied.
PRODUCER_REFUSALS = {"source_unregistered", "source_unavailable", "source_withheld", "consent_missing"}


class TraceRefused(ValueError):
    """A snapshot the consumer refuses as a whole, with a stable code."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _refuse(code: str, message: str) -> None:
    raise TraceRefused(code, message)


def contract_pins() -> dict[str, str]:
    """Schema ids and digests of the contract in this checkout."""

    observation = _load(OBSERVATION_SCHEMA_PATH)
    state = _load(STATE_SCHEMA_PATH)
    return {
        "observation_version": OBSERVATION_VERSION,
        "observation_schema_id": observation["$id"],
        "observation_schema_file_sha256": hashlib.sha256(OBSERVATION_SCHEMA_PATH.read_bytes()).hexdigest(),
        "observation_schema_canonical_digest": canonical_digest(observation),
        "state_version": STATE_VERSION,
        "state_schema_id": state["$id"],
        "state_schema_file_sha256": hashlib.sha256(STATE_SCHEMA_PATH.read_bytes()).hexdigest(),
        "policy_version": POLICY_VERSION,
        "mapping_version": MAPPING_VERSION,
    }


def attest_review(envelope: dict[str, Any]) -> dict[str, Any]:
    """Trace profile: a reviewed ambient fact carries ``clinician_reviewed``."""

    envelope = copy.deepcopy(envelope)
    envelope["quality"]["flags"] = sorted(set(envelope["quality"]["flags"]) | {REVIEW_FLAG})
    return envelope


def map_trace_contribution(record: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """The 1.0 ProvidEHR mapping plus the trace profile review attestation."""

    return attest_review(map_providehr_contribution(record, context))


# ---------------------------------------------------------------------------
# Consumer policy (reference for the Metabolog native consumer)
# ---------------------------------------------------------------------------


def _is_ambient(candidate: dict[str, Any]) -> bool:
    return candidate["source"]["source_id"].startswith(AMBIENT_SOURCE_PREFIX) and candidate["origin"] == "conversation"


def consume_snapshot(
    snapshot: dict[str, Any],
    envelopes: list[dict[str, Any]],
    *,
    subject: str,
    pins: dict[str, str],
) -> dict[str, Any]:
    """Reference consumer policy. Raises :class:`TraceRefused` for a snapshot
    that must not be ingested at all; otherwise returns per-observation
    outcomes and the state nodes a temporal graph may create."""

    if (
        snapshot.get("schema_version") != pins["state_version"]
        or snapshot.get("contract", {}).get("observation_schema_digest") != pins["observation_schema_canonical_digest"]
        or snapshot.get("policy", {}).get("policy_version") != pins["policy_version"]
    ):
        _refuse("contract_unpinned", "Snapshot is not bound to the pinned contract")
    body = {k: v for k, v in snapshot.items() if k != "snapshot_digest"}
    if canonical_digest(body) != snapshot.get("snapshot_digest"):
        _refuse("snapshot_digest_mismatch", "snapshot_digest does not match content")
    if snapshot["subject"] != subject:
        _refuse("subject_mismatch", "Snapshot is bound to another subject")

    by_id: dict[str, dict[str, Any]] = {}
    for envelope in envelopes:
        by_id[envelope["observation_id"]] = envelope
    inputs = {item["observation_id"]: item["envelope_digest"] for item in snapshot["inputs"]}
    for observation_id, digest in inputs.items():
        envelope = by_id.get(observation_id)
        if envelope is None or envelope_digest(envelope) != digest:
            _refuse("provenance_lost", f"Input {observation_id} has no matching envelope")
        if envelope["subject"] != subject:
            _refuse("subject_mismatch", f"Input {observation_id} is bound to another subject")

    seen: list[str] = []
    outcomes: dict[str, str] = {}
    for exclusion in snapshot["exclusions"]:
        observation_id = exclusion["observation_id"]
        if inputs.get(observation_id) != exclusion["envelope_digest"]:
            _refuse("provenance_lost", f"Exclusion {observation_id} is not a listed input")
        seen.append(observation_id)
        outcomes[observation_id] = f"excluded:{exclusion['code']}"

    states: list[dict[str, Any]] = []
    for entry in snapshot["entries"]:
        entry_outcomes: dict[str, str] = {}
        for candidate in entry["candidates"]:
            observation_id = candidate["observation_id"]
            if inputs.get(observation_id) != candidate["envelope_digest"]:
                _refuse("provenance_lost", f"Candidate {observation_id} is not a listed input")
            envelope = by_id[observation_id]
            if candidate.get("source") != envelope["source"]:
                _refuse("provenance_lost", f"Candidate {observation_id} source differs from its envelope")
            if (
                candidate["epistemic_status"] != envelope["epistemic_status"]
                or candidate["origin"] != envelope["origin"]
                or (candidate["epistemic_status"] == "imputed" and observation_id in entry["basis"])
            ):
                _refuse("imputed_as_observed", f"Candidate {observation_id} does not keep its envelope's epistemic status")
            if candidate["missingness"] != envelope["missingness"]["status"]:
                _refuse("missingness_altered", f"Candidate {observation_id} missingness differs from its envelope")
            seen.append(observation_id)
            if _is_ambient(candidate) and REVIEW_FLAG not in candidate["quality"]["flags"]:
                outcome = "refused:unreviewed_ambient_claim"
            elif candidate["epistemic_status"] == "imputed":
                outcome = "non_measurement"
            elif candidate["epistemic_status"] in {"derived", "inferred"}:
                outcome = "model_output"
            elif candidate["missingness"] != "present":
                outcome = f"missing:{candidate['missingness']}"
            elif candidate["freshness"] == "stale":
                outcome = "stale"
            elif observation_id in entry["basis"]:
                outcome = "conflict" if entry["resolution"] == "unresolved_conflict" else "current"
            else:
                outcome = "superseded"
            entry_outcomes[observation_id] = outcome
        outcomes.update(entry_outcomes)
        basis_outcomes = [entry_outcomes[b] for b in entry["basis"]]
        if basis_outcomes and all(o in {"current", "conflict"} for o in basis_outcomes):
            states.append(
                {
                    "key": entry["key"],
                    "resolution": entry["resolution"],
                    "basis": entry["basis"],
                    "blockers": entry["clinical_use"]["blockers"],
                    "admission_candidate": entry["clinical_use"]["admission_candidate"],
                }
            )
    if sorted(seen) != sorted(inputs):
        _refuse("provenance_lost", "Inputs are not accounted for exactly once")
    return {
        "snapshot_digest": snapshot["snapshot_digest"],
        "outcomes": dict(sorted(outcomes.items())),
        "states": states,
    }


# ---------------------------------------------------------------------------
# Trace replay
# ---------------------------------------------------------------------------


def apply_pointer_op(document: Any, op: dict[str, Any]) -> None:
    """``set`` or ``remove`` one JSON-pointer path in place."""

    parts: list[Any] = [p.replace("~1", "/").replace("~0", "~") for p in op["path"].split("/")[1:]]
    target = document
    for part in parts[:-1]:
        target = target[int(part)] if isinstance(target, list) else target[part]
    last = int(parts[-1]) if isinstance(target, list) else parts[-1]
    if op["op"] == "remove":
        del target[last]
    else:
        target[last] = copy.deepcopy(op["value"])


def apply_envelope_ops(envelopes: list[dict[str, Any]], ops: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """``set`` / ``remove`` a JSON-pointer path in a named envelope, or ``add`` one."""

    result = copy.deepcopy(envelopes)
    for op in ops:
        if op["op"] == "add":
            result.append(copy.deepcopy(op["envelope"]))
            continue
        apply_pointer_op(next(e for e in result if e["observation_id"] == op["observation_id"]), op)
    return result


def base_envelopes(trace: dict[str, Any]) -> list[dict[str, Any]]:
    return trace["producer"]["expect"]["envelopes"]


def _assemble(trace: dict[str, Any], envelopes: list[dict[str, Any]], revoked: list[str] | None = None) -> dict[str, Any]:
    stage = trace["openbody"]
    return assemble_state(
        envelopes,
        subject=trace["producer"]["export_context"]["subject"],
        as_of=stage["as_of"],
        purpose=stage["purpose"],
        revoked=trace["producer"]["expect"]["revoked"] if revoked is None else revoked,
    )


def _consumer_inputs(trace: dict[str, Any], case: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    snapshot = case.get("snapshot") or trace["openbody"]["snapshot"]
    envelopes = case.get("envelopes")
    return snapshot, base_envelopes(trace) if envelopes is None else envelopes


def evaluate_trace(path: Path = TRACE_PATH) -> list[ConformanceResult]:
    trace = json.loads(path.read_text(encoding="utf-8"))
    results: list[ConformanceResult] = []

    failures: list[str] = []
    if trace.get("trace_version") != TRACE_VERSION:
        failures.append(f"trace_version {trace.get('trace_version')} != {TRACE_VERSION}")
    pins = contract_pins()
    for key, value in pins.items():
        if trace["contract"].get(key) != value:
            failures.append(f"contract pin {key} differs: fixture {trace['contract'].get(key)} vs checkout {value}")
    results.append(ConformanceResult("healthcare-trace contract-pin", failures, pins["observation_schema_file_sha256"][:16]))
    if failures:
        return results

    producer = trace["producer"]["expect"]
    failures = []
    mapped = 0
    for item in producer["contributions"]:
        context = {**trace["producer"]["export_context"], "subject_role": item["subject_role"], "capture_consent": item["capture_consent"]}
        observation_id = f"providehr:fact:{item['record']['fact_id']}"
        producer_side = [r for r in producer["refused"] if r["subject"] == observation_id and r["code"] in PRODUCER_REFUSALS]
        if producer_side:
            # Refused before mapping (source availability or missing consent):
            # it must not be exported either.
            if any(e["observation_id"] == observation_id for e in producer["envelopes"]):
                failures.append(f"{observation_id}: refused ({producer_side[0]['code']}) but exported")
            continue
        try:
            envelope = map_trace_contribution(item["record"], context)
        except MappingRefused as refusal:
            expected = {"subject": observation_id, "code": refusal.code}
            if expected not in producer["refused"]:
                failures.append(f"{observation_id}: reference refused {refusal.code}, producer did not")
            continue
        except WholePersonStateError as error:
            failures.append(f"{observation_id}: producer envelope invalid ({error.code}): {error}")
            continue
        mapped += 1
        match = [e for e in producer["envelopes"] if e["observation_id"] == observation_id]
        if match != [envelope]:
            failures.append(f"{observation_id}: producer envelope differs from the reference mapping")
    if mapped != len(producer["envelopes"]):
        failures.append(f"reference mapped {mapped} envelopes, producer exported {len(producer['envelopes'])}")
    if any(REVIEW_FLAG not in e["quality"]["flags"] for e in producer["envelopes"]):
        failures.append("an exported envelope lacks the review attestation")
    if any((e["origin"], e["epistemic_status"]) != ("conversation", "reported") for e in producer["envelopes"]):
        failures.append("the producer exported something other than conversation/reported")
    results.append(ConformanceResult("healthcare-trace producer-cross-check", failures, f"{mapped} envelopes"))

    stage = trace["openbody"]
    failures = []
    try:
        snapshot = _assemble(trace, base_envelopes(trace))
        validate_state(snapshot)
    except WholePersonStateError as error:
        failures.append(f"base trace rejected: {error.code}: {error}")
        snapshot = None
    if snapshot is not None and snapshot != stage["snapshot"]:
        failures.append("assembled snapshot differs from the fixture snapshot")
    results.append(ConformanceResult("healthcare-trace openbody-snapshot", failures, stage["snapshot"]["snapshot_digest"]))

    for case in stage["cases"]:
        failures = []
        envelopes = apply_envelope_ops(base_envelopes(trace), case.get("envelope_ops", []))
        detail = ""
        try:
            got = _assemble(trace, envelopes, case.get("revoked"))
            if "snapshot_ops" in case:
                for op in case["snapshot_ops"]:
                    apply_pointer_op(got, op)
                if case.get("redigest"):
                    body = {k: v for k, v in got.items() if k != "snapshot_digest"}
                    got["snapshot_digest"] = canonical_digest(body)
            validate_state(got)
        except WholePersonStateError as error:
            detail = f"rejected ({error.code})"
            if case["expect"].get("rejected") != error.code:
                failures.append(f"expected {case['expect']}, got {detail}")
        else:
            detail = f"accepted {got['snapshot_digest']}"
            if case["expect"].get("accepted") != got["snapshot_digest"]:
                failures.append(f"expected {case['expect']}, got {detail}")
            for observation_id, code in case["expect"].get("exclusions", {}).items():
                found = {x["observation_id"]: x["code"] for x in got["exclusions"]}.get(observation_id)
                if found != code:
                    failures.append(f"{observation_id}: expected exclusion {code}, got {found}")
            for observation_id, want in case["expect"].get("policy", {}).items():
                outcome = consume_snapshot(
                    got, envelopes, subject=trace["producer"]["export_context"]["subject"], pins=pins
                )["outcomes"].get(observation_id)
                if outcome != want:
                    failures.append(f"{observation_id}: expected consumer outcome {want}, got {outcome}")
        results.append(ConformanceResult(f"healthcare-trace openbody-case {case['name']}", failures, detail))

    consumer = trace["consumer"]
    subject = trace["producer"]["export_context"]["subject"]
    for case in consumer["cases"]:
        failures = []
        snapshot, envelopes = _consumer_inputs(trace, case)
        try:
            got = consume_snapshot(snapshot, envelopes, subject=case.get("subject", subject), pins=pins)
        except TraceRefused as refusal:
            detail = f"refused ({refusal.code})"
            if case["expect"].get("refused") != refusal.code:
                failures.append(f"expected {case['expect']}, got {detail}")
        else:
            detail = f"accepted, {len(got['states'])} states"
            if "refused" in case["expect"]:
                failures.append(f"expected {case['expect']}, got {detail}")
            if case["expect"].get("outcomes") is not None and got["outcomes"] != case["expect"]["outcomes"]:
                failures.append(f"outcomes differ: expected {case['expect']['outcomes']}, got {got['outcomes']}")
            if case["expect"].get("states") is not None and got["states"] != case["expect"]["states"]:
                failures.append("state nodes differ from the fixture")
        results.append(ConformanceResult(f"healthcare-trace consumer-case {case['name']}", failures, detail))
    return results
