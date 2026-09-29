#!/usr/bin/env python3
"""Build the shared healthcare trace fixture (fixtures/healthcare-trace/v1/trace.json).

The trace has three stages owned by three repositories. The producer output
comes from ProvidEHR's native export (Rust), so building takes two steps:

    python tools/build_healthcare_trace.py inputs
        # writes trace.json with the contract pins and the producer inputs
    (in ProvidEHR crates/ambient-evidence, with trace.json copied in)
    OPENBODY_TRACE_EMIT=/tmp/producer.json cargo test --test openbody_trace -- --ignored emit
    python tools/build_healthcare_trace.py finalize /tmp/producer.json
        # adds producer.expect, the OpenBody snapshot and cases, and the
        # consumer expectations produced by the reference consumer policy

Review the diff: a changed trace is a cross-repository contract change, and
every replaying repository pins the file by SHA-256.
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reference" / "python"))

from openbody_ref.healthcare_trace import (  # noqa: E402
    REVIEW_FLAG,
    TRACE_PATH,
    TRACE_VERSION,
    TraceRefused,
    apply_envelope_ops,
    consume_snapshot,
    contract_pins,
)
from openbody_ref.validation import canonical_digest  # noqa: E402
from openbody_ref.whole_person import assemble_state, envelope_digest, validate_state  # noqa: E402

SUBJECT = "subject:openbody:trace-0001"
AS_OF = "2026-09-20T08:00:00Z"
TENANT = "tenant-trace-1"
PATIENT_REF = "patient-trace-0001"
EXTERNAL_PATIENT = "tc-pat-0001"
CLINICAL_SOURCE = {"system": "takecare", "vendor": "cgm", "version": "leyr-sandbox"}
ADAPTER_ID = "takecare.leyr.ambient-note"


def _connection(unit: str) -> str:
    return f"conn-takecare-{unit}"


def _source_key(unit: str) -> dict:
    return {"clinical_system": CLINICAL_SOURCE["system"], "adapter_id": ADAPTER_ID, "connection_id": _connection(unit)}


def _note(unit: str, note: str, created_at: str, start: str, lines: list[str]) -> dict:
    detail = {
        "id": f"L0_{note}",
        "emr_id": note,
        "patient_id": EXTERNAL_PATIENT,
        "care_unit_id": unit,
        "created_at": created_at,
        "created_by_id": "synthetic-author-1",
        "signed_at": None,
        "signed_by_id": None,
        "template": {"id": None, "emr_id": "synthetic-ambient-note", "name": "Synthetic ambient transcript"},
        "content": {"synthetic_field": "\n".join([f"@start|{start}", *lines])},
    }
    listed = copy.deepcopy(detail)
    listed["content"] = None
    return {"care_unit": unit, "list_record": listed, "detail": detail}


def _encounter(name: str, unit: str, controller: str, note: str, created_at: str, start: str,
               captured_at: str, decided_at: str, lines: list[str], reviews: list[dict],
               consent_withdrawn: bool = False) -> dict:
    return {
        "name": name,
        "binding": {
            "clinical_source": CLINICAL_SOURCE,
            "transport_provider": "leyr",
            "connector_id": "takecare.leyr",
            "connection_id": _connection(unit),
            "tenant_id": TENANT,
            "data_controller": controller,
            "external_patient_id": EXTERNAL_PATIENT,
            "patient_ref": PATIENT_REF,
            "consent_ref": f"urn:providehr:consent:takecare:{note}:ambient",
            "purpose": "ambient_documentation",
            "consent_captured_at": captured_at,
        },
        "read": _note(unit, note, created_at, start, lines),
        "reviewer": {"reviewer_id": "clinician-trace-1", "role": "clinician", "tenant_id": TENANT},
        "decided_at": decided_at,
        "reviews": reviews,
        "consent_withdrawn": consent_withdrawn,
    }


def _accept(concept: str) -> dict:
    return {"concept": concept, "decision": {"decision": "accept"}}


def producer_inputs() -> dict:
    return {
        "upstream": {
            "repository": "advatar/ProvidEHR",
            "base": "PR #689 head f01ee445 (feat/600-ambient-two-adapter-qualification)",
            "takecare_boundary": "merged #599 (1eae39d9), qualified by #601 (f4f52a81); issue #574 closed",
            "adapter": ADAPTER_ID,
            "note": "Synthetic TakeCare-shaped note reads; narrative uses the synthetic ambient line profile documented in crates/ambient-evidence/src/takecare.rs.",
        },
        "tenant_id": TENANT,
        "patient_ref": PATIENT_REF,
        "export_context": {
            "subject": SUBJECT,
            "subject_binding": {
                "status": "verified",
                "binding_ref": "urn:openbody:binding:trace-0001:v1",
                "issuer": "https://invivo.example/identity",
                "revocation_ref": "urn:openbody:binding:trace-0001:revocation",
                "proof_digest": "sha256:" + hashlib.sha256(b"synthetic binding proof trace-0001").hexdigest(),
            },
            "authority_ref": "urn:providehr:grant:takecare:trace-0001:read",
            "clinical_source_version": f"{CLINICAL_SOURCE['system']}/{CLINICAL_SOURCE['version']}",
            "clock_status": "unknown",
            "purpose_map": {"ambient_documentation": "encounter_context"},
            "concept_codes": {
                "dizziness": {"system": "http://snomed.info/sct", "code": "404640003", "display": "Dizziness"},
                "chest-pain": {"system": "http://snomed.info/sct", "code": "29857009", "display": "Chest pain"},
                "dyspnea": {"system": "http://snomed.info/sct", "code": "267036007", "display": "Dyspnea"},
                "headache": {"system": "http://snomed.info/sct", "code": "25064002", "display": "Headache"},
            },
        },
        "sources": [
            {"key": _source_key("unit-ts-a"), "vendor": "cgm", "data_controller": "region-trace-1", "availability": {"availability": "available"}},
            {"key": _source_key("unit-ts-b"), "vendor": "cgm", "data_controller": "region-trace-1", "availability": {"availability": "available"}},
            {"key": _source_key("unit-ts-c"), "vendor": "cgm", "data_controller": "clinic-trace-2", "availability": {"availability": "available"}},
        ],
        "encounters": [
            _encounter(
                "a1", "unit-ts-a", "region-trace-1", "note-a1",
                "2026-09-19T09:40:00Z", "2026-09-19T09:00:00Z", "2026-09-19T08:55:00Z", "2026-09-19T09:50:00Z",
                [
                    "L|00:00:02.000|00:00:04.000|98|What brings you in today?",
                    "P|00:00:05.000|00:00:09.000|96|I have been feeling dizzy since this morning.",
                    "L|00:00:10.000|00:00:12.000|98|Any chest pain?",
                    "P|00:00:13.000|00:00:15.000|95|No chest pain.",
                    "P|00:00:16.000|00:00:20.000|90|I think I have a headache.",
                    "P|00:00:21.000|00:00:24.000|94|My mother had a stroke.",
                    "P|00:00:30.000|00:00:34.000|93|I get shortness of breath on the stairs.",
                    "L|00:00:40.000|00:00:44.000|97|We will check kidney function.",
                ],
                [
                    _accept("dizziness"),
                    _accept("chest-pain"),
                    _accept("headache"),
                    _accept("stroke"),
                    _accept("renal-function-test"),
                    {"concept": "dyspnea", "decision": {"decision": "defer", "reason": "clinician wants to ask again at follow-up"}},
                ],
            ),
            _encounter(
                "a2", "unit-ts-a", "region-trace-1", "note-a2",
                "2026-09-19T15:10:00Z", "2026-09-19T15:00:00Z", "2026-09-19T14:55:00Z", "2026-09-19T15:20:00Z",
                ["P|00:00:05.000|00:00:08.000|95|I still have a headache."],
                [_accept("headache")],
                consent_withdrawn=True,
            ),
            _encounter(
                "b1", "unit-ts-b", "region-trace-1", "note-b1",
                "2026-09-08T10:20:00Z", "2026-09-08T10:00:00Z", "2026-09-08T09:55:00Z", "2026-09-08T10:30:00Z",
                ["P|00:00:05.000|00:00:09.000|94|I get shortness of breath at night."],
                [_accept("dyspnea")],
            ),
            _encounter(
                "c1", "unit-ts-c", "clinic-trace-2", "note-c1",
                "2026-09-19T11:10:00Z", "2026-09-19T11:00:00Z", "2026-09-19T10:55:00Z", "2026-09-19T11:20:00Z",
                ["P|00:00:05.000|00:00:08.000|95|I have a headache."],
                [_accept("headache")],
            ),
        ],
        "availability_after_ingest": [
            {"key": _source_key("unit-ts-c"), "availability": {"availability": "withheld", "reason": "controller policy: sensitive care unit"}},
        ],
        "stale_check": {"now": AS_OF, "max_age_seconds": 604800},
        "cases": [
            {
                "name": "missing_provenance/list-detail-not-reconciled",
                "rule": "The qualified boundary binds the note list record and its detail; a detail that names another note is refused before any ambient step.",
                "encounter": "a1",
                "ops": [{"op": "set", "path": "/read/list_record/emr_id", "value": "note-other"}],
                "expect": {"refused": "boundary_refused"},
            },
            {
                "name": "missing_provenance/wrong-patient",
                "rule": "A detail for another patient is refused by the boundary (patient binding).",
                "encounter": "a1",
                "ops": [
                    {"op": "set", "path": "/read/list_record/patient_id", "value": "tc-pat-9999"},
                    {"op": "set", "path": "/read/detail/patient_id", "value": "tc-pat-9999"},
                ],
                "expect": {"refused": "boundary_refused"},
            },
            {
                "name": "missing_provenance/unqualified-version-field",
                "rule": "An explicit version field has no qualified semantics; the boundary refuses it rather than ignoring it.",
                "encounter": "a1",
                "ops": [{"op": "set", "path": "/read/detail/version", "value": "2"}],
                "expect": {"refused": "boundary_refused"},
            },
            {
                "name": "missing_provenance/not-the-takecare-connector",
                "rule": "The adapter only accepts reads bound to the qualified takecare.leyr connector.",
                "encounter": "a1",
                "ops": [{"op": "set", "path": "/binding/connector_id", "value": "some-other-connector"}],
                "expect": {"refused": "source_mismatch"},
            },
            {
                "name": "missing_provenance/source-digest-changes-with-content",
                "rule": "The record digest is the boundary's original-source digest: a different narrative is a different record version.",
                "encounter": "a2",
                "ops": [{"op": "set", "path": "/read/detail/content/synthetic_field", "value": "@start|2026-09-19T15:00:00Z\nP|00:00:05.000|00:00:08.000|95|I still have a bad headache."}],
                "expect": {"record_digest_differs": True},
            },
        ],
    }


def write(trace: dict) -> None:
    TRACE_PATH.parent.mkdir(parents=True, exist_ok=True)
    TRACE_PATH.write_text(json.dumps(trace, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {TRACE_PATH.relative_to(ROOT)} sha256 {hashlib.sha256(TRACE_PATH.read_bytes()).hexdigest()}")


def build_inputs() -> dict:
    return {
        "trace_version": TRACE_VERSION,
        "description": (
            "Synthetic end-to-end healthcare trace: TakeCare note reads through the qualified ProvidEHR "
            "bounded-read boundary -> ambient extraction and append-only clinician review -> OpenBody "
            "whole-person observation envelopes and state snapshot -> Metabolog temporal state graph. "
            "Not patient data, not a clinical validation claim."
        ),
        "synthetic": True,
        "contract": {
            **contract_pins(),
            "openbody_ref": "advatar/OpenBody PR #44, feat/30-whole-person-state @ 2548ec9",
        },
        "profile": {
            "review_flag": REVIEW_FLAG,
            "hedge_flag": "speaker_hedged",
            "ambient_source_prefix": "urn:providehr:source:",
            "rules": [
                "A ProvidEHR ambient envelope carries quality flag clinician_reviewed; review stays epistemic_status reported (never clinician_validated) and is never uncertainty.",
                "The consumer refuses an ambient candidate without clinician_reviewed (unreviewed_ambient_claim) and never builds state on it.",
                "The consumer re-derives provenance: every listed input has its envelope with the same canonical digest; candidates keep their envelope's source, origin, epistemic status and missingness.",
                "Revoked consent and revoked sources reach OpenBody as host revocations and are recorded as exclusions, never ingested.",
                "A stale-only entry is kept with provenance but produces no current state.",
            ],
        },
        "producer": producer_inputs(),
    }


def _imputed_envelope(parent: dict) -> dict:
    return {
        "schema_version": parent["schema_version"],
        "observation_id": "invivo:gapfill:chest-pain:2026-09-20",
        "subject": parent["subject"],
        "subject_binding": copy.deepcopy(parent["subject_binding"]),
        "scope": ["ob://human/whole_body"],
        "source": {
            "source_id": "urn:openbody:source:model-host:invivo-gapfill",
            "source_kind": "model_host",
            "source_version": "invivo-gapfill/0.1.0",
            "record_ref": "urn:invivo:run:symptom-gapfill:0001",
            "record_digest": "sha256:" + hashlib.sha256(b"synthetic gap-fill run 0001").hexdigest(),
        },
        "origin": "model_transform",
        "epistemic_status": "imputed",
        "context_level": "individual",
        "time": {
            "effective_start": "2026-09-20T07:00:00Z",
            "effective_end": None,
            "ingested_at": "2026-09-20T07:30:00Z",
            "clock": {"status": "synchronized"},
        },
        "measurement": copy.deepcopy(parent["measurement"]),
        "missingness": {"status": "present"},
        "uncertainty": {"status": "unknown"},
        "quality": {"status": "unknown", "flags": []},
        "consent": {
            "consent_ref": "urn:invivo:consent:trace-0001:derived",
            "authority_ref": "urn:invivo:grant:trace-0001:derived",
            "purposes": ["encounter_context"],
            "granted_at": "2026-01-01T00:00:00Z",
            "expires_at": None,
        },
        "derivation": {
            "transform_id": "urn:openbody:transform:symptom-carry-forward",
            "transform_version": "0.1.0",
            "parents": [{"observation_id": parent["observation_id"], "envelope_digest": envelope_digest(parent)}],
        },
    }


def _redigest(snapshot: dict) -> dict:
    snapshot = copy.deepcopy(snapshot)
    snapshot["snapshot_digest"] = canonical_digest({k: v for k, v in snapshot.items() if k != "snapshot_digest"})
    return snapshot


def finalize(producer_output: Path) -> dict:
    trace = json.loads(TRACE_PATH.read_text(encoding="utf-8"))
    emitted = json.loads(producer_output.read_text(encoding="utf-8"))
    trace["producer"]["expect"] = emitted
    envelopes = emitted["envelopes"]
    ctx = trace["producer"]["export_context"]
    revoked = emitted["revoked"]

    def assemble(envs: list[dict], rev: list[str] | None = None) -> dict:
        snap = assemble_state(envs, subject=ctx["subject"], as_of=AS_OF, purpose="encounter_context",
                              revoked=revoked if rev is None else rev)
        validate_state(snap)
        return snap

    snapshot = assemble(envelopes)
    by_concept = {e["measurement"]["code"]["display"]: e for e in envelopes}
    dizziness = next(e for e in envelopes if e["measurement"]["code"]["code"] == "404640003")
    chest = next(e for e in envelopes if e["measurement"]["code"]["code"] == "29857009")
    imputed = _imputed_envelope(chest)
    del by_concept

    unreviewed_ops = [{"op": "set", "observation_id": dizziness["observation_id"], "path": "/quality/flags", "value": []}]
    unreviewed_envelopes = apply_envelope_ops(envelopes, unreviewed_ops)
    unreviewed_snapshot = assemble(unreviewed_envelopes)
    imputed_envelopes = envelopes + [imputed]
    imputed_snapshot = assemble(imputed_envelopes)

    openbody_cases = [
        {
            "name": "revoked_consent",
            "rule": "Withdrawn capture consent is a host revocation; the statement is excluded, not ingested.",
            "expect": {"accepted": snapshot["snapshot_digest"], "exclusions": {
                x["observation_id"]: x["code"] for x in snapshot["exclusions"]}},
        },
        {
            "name": "missing_provenance/record-digest-removed",
            "rule": "An envelope without source.record_digest is structurally invalid.",
            "envelope_ops": [{"op": "remove", "observation_id": dizziness["observation_id"], "path": "/source/record_digest"}],
            "expect": {"rejected": "structural_invalid"},
        },
        {
            "name": "unreviewed_ambient_claim",
            "rule": "The 1.0 assembler cannot see review; it accepts the snapshot and the trace consumer policy refuses the candidate.",
            "envelope_ops": unreviewed_ops,
            "expect": {"accepted": unreviewed_snapshot["snapshot_digest"],
                       "policy": {dizziness["observation_id"]: "refused:unreviewed_ambient_claim"}},
        },
        {
            "name": "imputed_control",
            "rule": "An imputed gap-fill with a digest-bound parent stays a candidate outside basis.",
            "envelope_ops": [{"op": "add", "envelope": imputed}],
            "expect": {"accepted": imputed_snapshot["snapshot_digest"],
                       "policy": {imputed["observation_id"]: "non_measurement"}},
        },
        {
            "name": "imputed_as_observed/envelope-relabelled",
            "rule": "An envelope that says observed but carries a derivation is structurally invalid.",
            "envelope_ops": [{"op": "add", "envelope": {**imputed, "epistemic_status": "observed", "origin": "self_report"}}],
            "expect": {"rejected": "structural_invalid"},
        },
        {
            "name": "imputed_as_observed/snapshot-basis",
            "rule": "A re-digested snapshot that moves the imputed candidate into basis is rejected by validate_state.",
            "envelope_ops": [{"op": "add", "envelope": imputed}],
            "snapshot_ops": [],
            "redigest": True,
            "expect": {"rejected": "imputation_as_measurement"},
        },
        {
            "name": "stale_source",
            "rule": "A symptom older than the 7-day window at as_of is stale_only and blocked.",
            "expect": {"accepted": snapshot["snapshot_digest"]},
        },
    ]
    # Locate the imputed candidate's entry to build the snapshot tamper paths.
    for i, entry in enumerate(imputed_snapshot["entries"]):
        if any(c["observation_id"] == imputed["observation_id"] for c in entry["candidates"]):
            openbody_cases[5]["snapshot_ops"] = [{
                "op": "set", "path": f"/entries/{i}/basis",
                "value": sorted(entry["basis"] + [imputed["observation_id"]]),
            }]
            imputed_entry = i
            imputed_candidate = next(j for j, c in enumerate(entry["candidates"]) if c["observation_id"] == imputed["observation_id"])
            basis_candidate = next(j for j, c in enumerate(entry["candidates"]) if c["observation_id"] == chest["observation_id"])

    stale_ids = [c["observation_id"] for e in snapshot["entries"] for c in e["candidates"] if c["freshness"] == "stale"]

    # Consumer cases: materialized snapshots so a native consumer needs no patch engine.
    tampered_basis = copy.deepcopy(imputed_snapshot)
    tampered_basis["entries"][imputed_entry]["candidates"][imputed_candidate]["epistemic_status"] = "observed"
    tampered_basis["entries"][imputed_entry]["candidates"][imputed_candidate]["origin"] = "self_report"
    tampered_basis["entries"][imputed_entry]["basis"] = sorted(
        tampered_basis["entries"][imputed_entry]["basis"] + [imputed["observation_id"]])
    tampered_basis = _redigest(tampered_basis)

    lost_digest = copy.deepcopy(snapshot)
    for entry in lost_digest["entries"]:
        for candidate in entry["candidates"]:
            if candidate["observation_id"] == dizziness["observation_id"]:
                del candidate["source"]["record_digest"]
    lost_digest = _redigest(lost_digest)

    missingness = copy.deepcopy(snapshot)
    for entry in missingness["entries"]:
        for candidate in entry["candidates"]:
            if candidate["observation_id"] == chest["observation_id"]:
                candidate["missingness"] = "not_measured"
    missingness = _redigest(missingness)

    unpinned = copy.deepcopy(snapshot)
    unpinned["contract"]["observation_schema_digest"] = "sha256:" + "0" * 64
    unpinned = _redigest(unpinned)

    tampered_value = copy.deepcopy(snapshot)
    for entry in tampered_value["entries"]:
        for candidate in entry["candidates"]:
            if candidate["observation_id"] == chest["observation_id"]:
                candidate["value"] = "present"
                candidate["source_value"] = "present"

    consumer_cases = [
        {"name": "control/base-trace", "rule": "The base trace is ingested; see outcomes and states."},
        {"name": "revoked_consent", "rule": "The withdrawn-consent statement is recorded as an exclusion and never becomes evidence."},
        {"name": "stale_source", "rule": "The stale-only entry keeps its evidence but creates no current state.", "stale": stale_ids},
        {"name": "unreviewed_ambient_claim", "rule": "An ambient candidate without clinician_reviewed is refused and no state is built on it.",
         "snapshot": unreviewed_snapshot, "envelopes": unreviewed_envelopes},
        {"name": "missing_provenance/candidate-record-digest-removed", "rule": "A re-digested snapshot whose candidate lost its record digest is refused.",
         "snapshot": lost_digest},
        {"name": "missing_provenance/envelope-not-supplied", "rule": "Every listed input needs its envelope with the same canonical digest.",
         "envelopes": [e for e in envelopes if e["observation_id"] != dizziness["observation_id"]]},
        {"name": "missing_provenance/missingness-altered", "rule": "A candidate's missingness must equal its envelope's.",
         "snapshot": missingness},
        {"name": "imputed_control", "rule": "An imputed candidate is kept as non-measurement evidence and never becomes state.",
         "snapshot": imputed_snapshot, "envelopes": imputed_envelopes},
        {"name": "imputed_as_observed", "rule": "A re-digested snapshot that relabels the imputed candidate as observed and puts it in basis is refused.",
         "snapshot": tampered_basis, "envelopes": imputed_envelopes},
        {"name": "contract_unpinned", "rule": "A snapshot bound to other schema bytes is refused before anything else.",
         "snapshot": unpinned},
        {"name": "snapshot_tampered", "rule": "A value change without a matching snapshot digest is refused.",
         "snapshot": tampered_value},
        {"name": "subject_mismatch", "rule": "The consumer only ingests the subject its custodian bound.",
         "subject": "subject:openbody:someone-else"},
    ]
    pins = contract_pins()
    for case in consumer_cases:
        snap = case.get("snapshot") or snapshot
        envs = case.get("envelopes") or envelopes
        try:
            got = consume_snapshot(snap, envs, subject=case.get("subject", ctx["subject"]), pins=pins)
        except TraceRefused as refusal:
            case["expect"] = {"refused": refusal.code}
        else:
            case["expect"] = {"outcomes": got["outcomes"], "states": got["states"]}
        case.pop("stale", None)

    trace["openbody"] = {
        "as_of": AS_OF,
        "purpose": "encounter_context",
        "envelope_digests": {e["observation_id"]: envelope_digest(e) for e in envelopes},
        "snapshot": snapshot,
        "cases": openbody_cases,
    }
    trace["consumer"] = {
        "repository": "advatar/Metabolog (InVivo)",
        "consumer": "SurrealHealthIndex WholePersonSnapshotConsumer -> OpenBodyStateIndex",
        "subject": ctx["subject"],
        "cases": consumer_cases,
    }
    return trace


def main(argv: list[str]) -> int:
    if argv[:1] == ["inputs"]:
        write(build_inputs())
        return 0
    if argv[:1] == ["finalize"] and len(argv) == 2:
        write(finalize(Path(argv[1])))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
