"""Shared healthcare trace: ProvidEHR -> OpenBody whole-person state -> Metabolog.

The fixture is produced by the ProvidEHR native export and replayed by all three
repositories. These tests check the OpenBody stage and the reference consumer
policy that Metabolog implements natively.
"""

from __future__ import annotations

import copy
import hashlib
import json

import pytest

from openbody_ref.healthcare_trace import (
    REVIEW_FLAG,
    TRACE_PATH,
    TRACE_VERSION,
    TraceRefused,
    apply_envelope_ops,
    attest_review,
    consume_snapshot,
    contract_pins,
    evaluate_trace,
    map_trace_contribution,
)
from openbody_ref.validation import canonical_digest
from openbody_ref.whole_person import (
    WholePersonStateError,
    assemble_state,
    envelope_digest,
    validate_state,
)
from openbody_ref.whole_person_mapping import MappingRefused


@pytest.fixture(scope="module")
def trace() -> dict:
    return json.loads(TRACE_PATH.read_text(encoding="utf-8"))


def _subject(trace: dict) -> str:
    return trace["producer"]["export_context"]["subject"]


def _envelopes(trace: dict) -> list[dict]:
    return trace["producer"]["expect"]["envelopes"]


def _consume(trace: dict, snapshot: dict | None = None, envelopes: list[dict] | None = None, subject: str | None = None) -> dict:
    return consume_snapshot(
        trace["openbody"]["snapshot"] if snapshot is None else snapshot,
        _envelopes(trace) if envelopes is None else envelopes,
        subject=subject or _subject(trace),
        pins=contract_pins(),
    )


def _redigest(snapshot: dict) -> dict:
    snapshot = copy.deepcopy(snapshot)
    snapshot["snapshot_digest"] = canonical_digest({k: v for k, v in snapshot.items() if k != "snapshot_digest"})
    return snapshot


def _by_code(trace: dict, code: str) -> dict:
    return next(e for e in _envelopes(trace) if e["measurement"]["code"]["code"] == code)


def test_every_trace_check_passes() -> None:
    results = evaluate_trace()
    assert [(r.name, r.failures) for r in results if not r.passed] == []
    assert len(results) >= 20


def test_trace_is_pinned_to_this_contract(trace: dict) -> None:
    assert trace["trace_version"] == TRACE_VERSION
    pins = contract_pins()
    for key, value in pins.items():
        assert trace["contract"][key] == value, key
    assert trace["openbody"]["snapshot"]["contract"]["observation_schema_digest"] == pins["observation_schema_canonical_digest"]
    assert pins["observation_schema_id"] == "https://openbody.dev/schemas/whole-person-observation/1.0"


def test_changed_schema_bytes_fail_the_pin(trace: dict, tmp_path) -> None:
    changed = copy.deepcopy(trace)
    changed["contract"]["observation_schema_file_sha256"] = hashlib.sha256(b"other").hexdigest()
    path = tmp_path / "trace.json"
    path.write_text(json.dumps(changed), encoding="utf-8")
    results = evaluate_trace(path)
    assert len(results) == 1 and not results[0].passed


def test_producer_envelopes_equal_the_reference_mapping(trace: dict) -> None:
    ctx = trace["producer"]["export_context"]
    by_id = {e["observation_id"]: e for e in _envelopes(trace)}
    mapped = 0
    for item in trace["producer"]["expect"]["contributions"]:
        observation_id = f"providehr:fact:{item['record']['fact_id']}"
        context = {**ctx, "subject_role": item["subject_role"], "capture_consent": item["capture_consent"]}
        try:
            envelope = map_trace_contribution(item["record"], context)
        except MappingRefused:
            assert observation_id not in by_id
            continue
        if observation_id in by_id:
            assert by_id[observation_id] == envelope
            mapped += 1
    assert mapped == len(by_id) == 5


def test_review_attestation_is_not_validation_or_uncertainty(trace: dict) -> None:
    for envelope in _envelopes(trace):
        assert REVIEW_FLAG in envelope["quality"]["flags"]
        assert envelope["epistemic_status"] == "reported"
        assert envelope["origin"] == "conversation"
        assert envelope["uncertainty"] == {"status": "unknown"}
        assert "validation" not in envelope
    assert attest_review({"quality": {"flags": ["speaker_hedged"]}})["quality"]["flags"] == [
        "clinician_reviewed",
        "speaker_hedged",
    ]


def test_producer_kept_the_unreviewed_claim_and_refusals(trace: dict) -> None:
    expect = trace["producer"]["expect"]
    assert expect["not_reviewed"] == [{"code": "not_reviewed", "subject": "a1:dyspnea"}]
    codes = sorted(r["code"] for r in expect["refused"])
    assert codes == ["domain_unsupported", "source_withheld", "subject_not_patient"]
    assert expect["sources"]["takecare|takecare.leyr.ambient-note|conn-takecare-unit-ts-c"] == "withheld"


def test_record_digest_is_the_takecare_boundary_digest(trace: dict) -> None:
    admissions = {a["encounter"]: a["admission"] for a in trace["producer"]["expect"]["boundary_admissions"]}
    assert set(admissions) == {"a1", "a2", "b1", "c1"}
    for name, admission in admissions.items():
        assert admission["representation"] == "identified_review_v1"
        assert admission["normalizer_id"] == "providehr.normalizer.takecare-notes"
        if name == "c1":
            continue
        digest = admission["original_source_digest"]
        assert any(
            e["source"]["record_digest"] == f"sha256:{digest}"
            and e["source"]["record_ref"].endswith(f":sha256-{digest}")
            for e in _envelopes(trace)
        ), name


def test_base_snapshot_is_reproducible_and_valid(trace: dict) -> None:
    snapshot = assemble_state(
        list(reversed(_envelopes(trace))),
        subject=_subject(trace),
        as_of=trace["openbody"]["as_of"],
        purpose=trace["openbody"]["purpose"],
        revoked=trace["producer"]["expect"]["revoked"],
    )
    validate_state(snapshot)
    assert snapshot == trace["openbody"]["snapshot"]
    resolutions = {e["key"]["code"]: e["resolution"] for e in snapshot["entries"]}
    assert resolutions == {
        "25064002": "single_source",
        "267036007": "stale_only",
        "29857009": "single_source",
        "404640003": "single_source",
    }
    assert [x["code"] for x in snapshot["exclusions"]] == ["consent_revoked"]
    for entry in snapshot["entries"]:
        assert entry["clinical_use"]["admission_candidate"] is False


def test_consumer_control_outcomes(trace: dict) -> None:
    got = _consume(trace)
    assert sorted(set(got["outcomes"].values())) == ["current", "excluded:consent_revoked", "stale"]
    assert len(got["states"]) == 3
    assert all(not s["admission_candidate"] for s in got["states"])


def test_consumer_refuses_an_unreviewed_ambient_claim(trace: dict) -> None:
    dizziness = _by_code(trace, "404640003")
    envelopes = apply_envelope_ops(
        _envelopes(trace),
        [{"op": "set", "observation_id": dizziness["observation_id"], "path": "/quality/flags", "value": []}],
    )
    snapshot = assemble_state(
        envelopes, subject=_subject(trace), as_of=trace["openbody"]["as_of"],
        purpose="encounter_context", revoked=trace["producer"]["expect"]["revoked"],
    )
    got = _consume(trace, snapshot, envelopes)
    assert got["outcomes"][dizziness["observation_id"]] == "refused:unreviewed_ambient_claim"
    assert not any(dizziness["observation_id"] in s["basis"] for s in got["states"])


@pytest.mark.parametrize(
    ("name", "mutate", "code"),
    [
        ("contract", lambda s: s["contract"].__setitem__("observation_schema_digest", "sha256:" + "0" * 64), "contract_unpinned"),
        ("policy", lambda s: s["policy"].__setitem__("policy_version", "openbody.whole-person-assembly-policy/0.9"), "contract_unpinned"),
        ("record-digest", lambda s: s["entries"][0]["candidates"][0]["source"].pop("record_digest"), "provenance_lost"),
        ("missingness", lambda s: s["entries"][0]["candidates"][0].__setitem__("missingness", "withheld"), "missingness_altered"),
        ("relabel", lambda s: s["entries"][0]["candidates"][0].__setitem__("epistemic_status", "observed"), "imputed_as_observed"),
        ("dropped-exclusion", lambda s: s.__setitem__("exclusions", []), "provenance_lost"),
    ],
)
def test_consumer_refuses_re_digested_tampering(trace: dict, name: str, mutate, code: str) -> None:
    snapshot = copy.deepcopy(trace["openbody"]["snapshot"])
    mutate(snapshot)
    with pytest.raises(TraceRefused) as refused:
        _consume(trace, _redigest(snapshot))
    assert refused.value.code == code, name


def test_consumer_refuses_digest_mismatch_and_other_subject(trace: dict) -> None:
    snapshot = copy.deepcopy(trace["openbody"]["snapshot"])
    snapshot["as_of"] = "2026-09-21T08:00:00Z"
    with pytest.raises(TraceRefused) as refused:
        _consume(trace, snapshot)
    assert refused.value.code == "snapshot_digest_mismatch"
    with pytest.raises(TraceRefused) as refused:
        _consume(trace, subject="subject:openbody:someone-else")
    assert refused.value.code == "subject_mismatch"


def test_consumer_requires_every_envelope(trace: dict) -> None:
    for envelope in _envelopes(trace):
        remaining = [e for e in _envelopes(trace) if e is not envelope]
        with pytest.raises(TraceRefused) as refused:
            _consume(trace, envelopes=remaining)
        assert refused.value.code == "provenance_lost"
    changed = copy.deepcopy(_envelopes(trace))
    changed[0]["time"]["ingested_at"] = "2026-09-19T23:59:00Z"
    assert envelope_digest(changed[0]) != envelope_digest(_envelopes(trace)[0])
    with pytest.raises(TraceRefused):
        _consume(trace, envelopes=changed)


def test_openbody_rejects_missing_provenance_and_imputed_as_observed(trace: dict) -> None:
    dizziness = _by_code(trace, "404640003")
    envelopes = apply_envelope_ops(
        _envelopes(trace), [{"op": "remove", "observation_id": dizziness["observation_id"], "path": "/source/record_digest"}]
    )
    with pytest.raises(WholePersonStateError) as rejected:
        assemble_state(envelopes, subject=_subject(trace), as_of=trace["openbody"]["as_of"], purpose="encounter_context")
    assert rejected.value.code == "structural_invalid"
    case = next(c for c in trace["openbody"]["cases"] if c["name"] == "imputed_as_observed/envelope-relabelled")
    envelopes = apply_envelope_ops(_envelopes(trace), case["envelope_ops"])
    with pytest.raises(WholePersonStateError) as rejected:
        assemble_state(envelopes, subject=_subject(trace), as_of=trace["openbody"]["as_of"], purpose="encounter_context")
    assert rejected.value.code == "structural_invalid"


def test_consumer_cases_cover_every_requested_rejection(trace: dict) -> None:
    names = {c["name"].split("/")[0] for c in trace["consumer"]["cases"]}
    assert {"control", "revoked_consent", "missing_provenance", "unreviewed_ambient_claim", "stale_source", "imputed_as_observed"} <= names
    openbody_names = {c["name"].split("/")[0] for c in trace["openbody"]["cases"]}
    assert {"revoked_consent", "missing_provenance", "unreviewed_ambient_claim", "stale_source", "imputed_as_observed"} <= openbody_names
    producer_names = {c["name"].split("/")[0] for c in trace["producer"]["cases"]}
    assert "missing_provenance" in producer_names
