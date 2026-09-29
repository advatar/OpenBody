from __future__ import annotations

import copy
import json
import shutil
import subprocess
import sys

import pytest

from openbody_ref import whole_person
from openbody_ref.whole_person import (
    CORPUS_DIR,
    ROOT,
    WholePersonStateError,
    assemble_state,
    envelope_digest,
    evaluate_conformance_corpus,
    validate_observation,
    validate_state,
)


def corpus_inputs():
    return json.loads((CORPUS_DIR / "inputs.json").read_text(encoding="utf-8"))


def golden():
    return json.loads((CORPUS_DIR / "snapshot.golden.json").read_text(encoding="utf-8"))


def vector_names():
    vectors = json.loads((CORPUS_DIR / "vectors.json").read_text(encoding="utf-8"))
    return ["golden-snapshot"] + [vector["name"] for vector in vectors["vectors"]]


def assemble(envelopes, **overrides):
    inputs = corpus_inputs()
    params = {
        "subject": inputs["subject"],
        "as_of": inputs["as_of"],
        "purpose": inputs["purpose"],
        "revoked": inputs["revoked"],
    }
    params.update(overrides)
    return assemble_state(envelopes, **params)


def by_id(envelopes, observation_id):
    return next(e for e in envelopes if e["observation_id"] == observation_id)


def entry(snapshot, code):
    return next(e for e in snapshot["entries"] if e["key"]["code"] == code)


RESULTS = {result.name: result for result in evaluate_conformance_corpus()}


@pytest.mark.parametrize("name", vector_names())
def test_conformance_vector(name):
    result = RESULTS[name]
    assert result.passed, result.failures


def test_corpus_covers_every_qualification_axis_from_issue_30():
    vectors = json.loads((CORPUS_DIR / "vectors.json").read_text(encoding="utf-8"))["vectors"]
    covers = " ".join(vector["covers"] for vector in vectors)
    for axis in (
        "unit normalization",
        "clock drift",
        "no silent source-priority inference",
        "stale",
        "missingness",
        "revoked source",
        "imputation never masquerades",
        "replay",
        "provenance loss",
        "unknown uncertainty stays unknown",
        "deterministic",
    ):
        assert axis in covers, axis
    domains = {e["measurement"]["domain"] for e in corpus_inputs()["envelopes"]}
    assert {"glucose", "sleep", "heart_rate_variability", "laboratory", "symptom", "meal", "environment"} <= domains
    origins = {e["origin"] for e in corpus_inputs()["envelopes"]}
    assert {"device_sensor", "clinical_record", "laboratory", "self_report", "conversation", "environmental_feed", "model_transform"} <= origins


def test_every_golden_envelope_validates():
    for envelope in corpus_inputs()["envelopes"]:
        validate_observation(envelope)


def test_golden_snapshot_validates_and_matches_assembly():
    snapshot = golden()
    validate_state(snapshot)
    assert assemble(corpus_inputs()["envelopes"]) == snapshot


def test_snapshot_is_deterministic_and_does_not_mutate_inputs():
    envelopes = corpus_inputs()["envelopes"]
    before = copy.deepcopy(envelopes)
    first = assemble(envelopes)
    second = assemble(list(reversed(envelopes)))
    assert first == second
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert envelopes == before


def test_disagreeing_sources_select_no_value_and_are_never_ranked():
    snapshot = assemble(corpus_inputs()["envelopes"])
    heart_rate = entry(snapshot, "8867-4")
    assert heart_rate["resolution"] == "unresolved_conflict"
    assert heart_rate["clinical_use"]["admission_candidate"] is False
    assert "value" not in heart_rate
    assert snapshot["claim_boundary"] == {
        "projection_class": "state_projection",
        "clinical_assertion": False,
        "authority_granted": False,
        "source_priority": "none",
    }


def test_unknown_uncertainty_is_preserved_not_filled():
    snapshot = assemble(corpus_inputs()["envelopes"])
    sleep = entry(snapshot, "93832-4")
    assert sleep["candidates"][0]["uncertainty"] == {"status": "unknown"}
    assert "uncertainty_unknown" in sleep["clinical_use"]["blockers"]


def test_imputed_candidate_is_kept_but_never_in_measurement_basis():
    snapshot = assemble(corpus_inputs()["envelopes"])
    glucose = entry(snapshot, "99504-3")
    imputed = [c for c in glucose["candidates"] if c["epistemic_status"] == "imputed"]
    assert [c["observation_id"] for c in imputed] == ["wp-cgm-imputed-001"]
    assert "wp-cgm-imputed-001" not in glucose["basis"]


def test_exact_provenance_is_copied_into_candidates():
    envelopes = corpus_inputs()["envelopes"]
    snapshot = assemble(envelopes)
    for item in snapshot["entries"]:
        for candidate in item["candidates"]:
            source = by_id(envelopes, candidate["observation_id"])
            assert candidate["source"] == source["source"]
            assert candidate["envelope_digest"] == envelope_digest(source)
            assert candidate["source_value"] == source["measurement"]["value"]
            assert candidate["source_unit"] == source["measurement"]["unit"]
            assert candidate["derivation"] == source.get("derivation")
            assert candidate["clinical_link"] == source.get("clinical_link")


def test_clinical_link_is_a_reference_not_a_copied_record():
    envelopes = corpus_inputs()["envelopes"]
    hba1c = by_id(envelopes, "wp-lab-hba1c-001")
    assert set(hba1c["clinical_link"]) == {
        "profile",
        "admitted_observation_id",
        "clinical_version_ref",
        "content_digest",
    }
    assert entry(assemble(envelopes), "4548-4")["clinical_use"]["requires"] == (
        "openbody.clinical-assertion-reference/1.0"
    )


def test_stale_boundary_is_inclusive_of_max_age():
    envelopes = corpus_inputs()["envelopes"]
    # wp-cgm-001 is at 07:55:00Z; glucose max age is one hour.
    at_limit = entry(assemble(envelopes, as_of="2026-09-20T08:55:00Z"), "99504-3")
    past_limit = entry(assemble(envelopes, as_of="2026-09-20T08:55:01Z"), "99504-3")
    assert at_limit["resolution"] == "single_source"
    assert at_limit["basis"] == ["wp-cgm-001"]
    # Only the (still current) imputed gap-fill remains; it never becomes the basis.
    assert past_limit["resolution"] == "imputed_only"
    assert past_limit["basis"] == []


def test_as_of_without_offset_is_rejected():
    with pytest.raises(WholePersonStateError) as caught:
        assemble(corpus_inputs()["envelopes"], as_of="2026-09-20T08:00:00")
    assert caught.value.code == "structural_invalid"


def test_corpus_detects_a_regression_that_counts_imputation_as_measurement(monkeypatch):
    monkeypatch.setattr(whole_person, "NON_MEASUREMENT", set())
    failed = {r.name for r in evaluate_conformance_corpus() if not r.passed}
    assert "golden-snapshot" in failed
    assert "imputed-only-entry" in failed


def test_corpus_detects_a_regression_that_ranks_sources(monkeypatch):
    original = whole_person._entry

    def ranked(key, candidates):
        result = original(key, candidates)
        if result["resolution"] == "unresolved_conflict":
            result["resolution"] = "single_source"
            result["basis"] = result["basis"][-1:]
        return result

    monkeypatch.setattr(whole_person, "_entry", ranked)
    failed = {r.name for r in evaluate_conformance_corpus() if not r.passed}
    assert {"golden-snapshot", "conflict-second-cgm-disagrees", "conflict-clinician-validated-does-not-win"} <= failed


def test_corpus_checker_is_not_vacuous(tmp_path):
    corpus = tmp_path / "v1"
    shutil.copytree(CORPUS_DIR, corpus)
    vectors = json.loads((corpus / "vectors.json").read_text(encoding="utf-8"))
    for vector in vectors["vectors"]:
        if vector["name"] == "revoked-source":
            vector["expect"]["exclusions"] = {}
        if vector["name"] == "clock-correction-mismatch":
            vector["expect"]["error_code"] = "structural_invalid"
    (corpus / "vectors.json").write_text(json.dumps(vectors), encoding="utf-8")
    snapshot = json.loads((corpus / "snapshot.golden.json").read_text(encoding="utf-8"))
    snapshot["entries"][0]["candidates"][0]["value"] = 99.0
    (corpus / "snapshot.golden.json").write_text(json.dumps(snapshot), encoding="utf-8")
    failed = {r.name for r in evaluate_conformance_corpus(corpus) if not r.passed}
    assert {"golden-snapshot", "revoked-source", "clock-correction-mismatch"} <= failed


def test_cli_check_passes():
    completed = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "check_whole_person_state.py")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "whole-person-state vectors passed" in completed.stdout
