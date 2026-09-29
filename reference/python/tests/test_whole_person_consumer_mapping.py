"""Consumer mapping into the whole-person contract (issue #30, PR #44 review).

Proves that representative records from Metabolog/InVivo, ProvidEHR ambient
evidence and the TwinSuite conversational adapter map into
``openbody.whole-person-observation/1.0`` with agreed source identity, time,
uncertainty, consent/revocation and observed/reported/inferred/imputed
distinctions, and that anything 1.0 cannot carry is refused, not approximated.
"""

from __future__ import annotations

import copy
import json

import pytest

from openbody_ref import whole_person
from openbody_ref.schema_keywords import schema_vocabulary
from openbody_ref.validation import canonical_digest
from openbody_ref.whole_person import (
    CORPUS_DIR,
    ROOT,
    WholePersonStateError,
    assemble_state,
    evaluate_conformance_corpus,
    validate_observation,
)
from openbody_ref.whole_person_mapping import (
    MAPPING_VERSION,
    MappingRefused,
    evaluate_consumer_mapping,
    map_metabolog_admitted_observation,
    map_metabolog_epistemic_class,
    map_providehr_contribution,
    map_record,
    map_twinsuite_candidate,
    providehr_revocations,
    providehr_source_id,
)

MAPPING = json.loads((CORPUS_DIR / "consumer-mapping.json").read_text(encoding="utf-8"))
INTEROP = json.loads((CORPUS_DIR / "interop-vectors.json").read_text(encoding="utf-8"))
CONSUMERS = {consumer["consumer"]: consumer for consumer in MAPPING["consumers"]}


def record(consumer, name):
    return next(item for item in CONSUMERS[consumer]["records"] if item["name"] == name)


def mapped(consumer, name):
    return record(consumer, name)["expect"]["envelope"]


def all_envelopes():
    return [
        item["expect"]["envelope"]
        for consumer in MAPPING["consumers"]
        for item in consumer["records"]
        if "envelope" in item["expect"]
    ]


def assemble(envelopes, **overrides):
    params = {
        "subject": MAPPING["subject"],
        "as_of": MAPPING["assembly"]["as_of"],
        "purpose": MAPPING["assembly"]["purpose"],
        "revoked": MAPPING["assembly"]["revoked"],
    }
    params.update(overrides)
    return assemble_state(envelopes, **params)


def entry(snapshot, code):
    return next(e for e in snapshot["entries"] if e["key"]["code"] == code)


MAPPING_RESULTS = {result.name: result for result in evaluate_consumer_mapping()}


@pytest.mark.parametrize("name", sorted(MAPPING_RESULTS))
def test_consumer_mapping_vector(name):
    result = MAPPING_RESULTS[name]
    assert result.passed, result.failures


def test_mapping_corpus_names_each_consumer_upstream_and_field_map():
    assert MAPPING["mapping_version"] == MAPPING_VERSION
    assert set(CONSUMERS) == {"metabolog", "providehr", "twinsuite"}
    for consumer in MAPPING["consumers"]:
        assert consumer["upstream"]["repository"].startswith("advatar/")
        assert consumer["upstream"]["ref"] and consumer["upstream"]["consumed"]
        assert consumer["field_map"], consumer["consumer"]
        for row in consumer["field_map"]:
            assert row["consumer_field"] and row["contract_path"]
        mapped_records = [item for item in consumer["records"] if "envelope" in item["expect"]]
        refused_records = [item for item in consumer["records"] if "refused" in item["expect"]]
        # Every consumer proves both a clean mapping and an explicit refusal.
        assert mapped_records and refused_records, consumer["consumer"]


def test_every_mapped_envelope_validates_and_binds_the_shared_subject():
    for envelope in all_envelopes():
        validate_observation(envelope)
        assert envelope["subject"] == MAPPING["subject"]
        assert envelope["subject_binding"]["status"] == "verified"


def test_mapping_is_deterministic_and_does_not_mutate_records():
    for consumer in MAPPING["consumers"]:
        done = {}
        for item in consumer["records"]:
            before = copy.deepcopy(item)
            try:
                first = map_record(item, done)
                second = map_record(item, done)
            except MappingRefused:
                continue
            assert first == second
            assert canonical_digest(first) == canonical_digest(second)
            assert item == before
            done[item["name"]] = first


def test_source_identity_is_one_to_one_with_each_consumers_conflict_unit():
    # ProvidEHR keys its longitudinal state by SourceKey; the envelope uses the same unit.
    a = {"clinical_system": "ehr-a", "adapter_id": "fhir-style", "connection_id": "conn-1"}
    b = dict(a, adapter_id="legacy-journal")
    c = dict(a, connection_id="conn-2")
    ids = {providehr_source_id(key) for key in (a, b, c)}
    assert len(ids) == 3
    # Every mapped record_ref is version-specific and names exactly one source.
    by_ref = {}
    for envelope in all_envelopes():
        by_ref.setdefault(envelope["source"]["record_ref"], set()).add(envelope["source"]["source_id"])
    assert all(len(sources) == 1 for sources in by_ref.values())
    timeline = mapped("metabolog", "timeline-glucose-meter-healthkit")
    assert ":rev:" in timeline["source"]["record_ref"]
    assert ":rev:" in mapped("twinsuite", "conversation-said")["source"]["record_ref"]


def test_observed_reported_inferred_and_clinical_distinctions_survive_mapping():
    statuses = {
        (consumer, item["name"]): (item["expect"]["envelope"]["origin"], item["expect"]["envelope"]["epistemic_status"])
        for consumer, data in CONSUMERS.items()
        for item in data["records"]
        if "envelope" in item["expect"]
    }
    assert statuses[("metabolog", "timeline-glucose-meter-healthkit")] == ("device_sensor", "observed")
    # A value the person typed in is reported, even if a meter produced it.
    assert statuses[("metabolog", "timeline-glucose-typed-by-person")] == ("self_report", "reported")
    assert statuses[("metabolog", "admitted-body-temperature")] == ("clinical_record", "imported")
    assert statuses[("providehr", "ambient-symptom-present")] == ("conversation", "reported")
    assert statuses[("twinsuite", "conversation-said")] == ("conversation", "reported")
    assert statuses[("twinsuite", "conversation-confirmed")] == ("conversation", "reported")
    assert statuses[("twinsuite", "conversation-inferred")] == ("model_transform", "inferred")
    # No statement, confirmation or review becomes a measurement or a clinician validation.
    for (consumer, _), (origin, status) in statuses.items():
        if origin in {"conversation", "self_report"}:
            assert status == "reported"
        assert status != "clinician_validated"


def test_said_and_confirmed_stay_distinct_without_ranking():
    said = mapped("twinsuite", "conversation-said")
    confirmed = mapped("twinsuite", "conversation-confirmed")
    assert canonical_digest(said) != canonical_digest(confirmed)
    assert confirmed["quality"]["flags"] == ["user_confirmed"]
    assert said["quality"]["flags"] == []
    meal = entry(assemble(all_envelopes()), "meal-description")
    # Same source and time: both kept, neither silently preferred.
    assert meal["basis"] == sorted([said["observation_id"], confirmed["observation_id"]])
    assert meal["resolution"] == "single_source"


def test_inferred_candidate_is_digest_bound_to_what_was_said():
    inferred = mapped("twinsuite", "conversation-inferred")
    said = mapped("twinsuite", "conversation-said")
    assert inferred["derivation"]["parents"] == [
        {"observation_id": said["observation_id"], "envelope_digest": canonical_digest(said)}
    ]
    snapshot = assemble(all_envelopes())
    assert "model_output_requires_receipt" in entry(snapshot, "meal-category")["clinical_use"]["blockers"]
    # Revoking the utterance excludes the inference that depends on it.
    revoked = assemble(all_envelopes(), revoked=MAPPING["assembly"]["revoked"] + [said["source"]["record_ref"]])
    exclusions = {item["observation_id"]: item["code"] for item in revoked["exclusions"]}
    assert exclusions[said["observation_id"]] == "source_revoked"
    assert exclusions[inferred["observation_id"]] == "derivation_parent_excluded"
    item = record("twinsuite", "conversation-inferred")
    with pytest.raises(MappingRefused) as refused:
        map_twinsuite_candidate(item["record"], item["context"], None)
    assert refused.value.code == "derivation_parent_missing"


def test_reported_and_observed_disagreement_is_a_conflict_not_a_ranking():
    glucose = entry(assemble(all_envelopes()), "41653-7")
    assert glucose["resolution"] == "unresolved_conflict"
    assert glucose["clinical_use"]["admission_candidate"] is False


def test_cross_consumer_symptom_value_vocabulary_is_an_open_conflict():
    # InVivo records severity, ProvidEHR records presence for the same SNOMED code.
    # Without an agreed value set per code this is (correctly) never merged.
    dizziness = entry(assemble(all_envelopes()), "404640003")
    assert dizziness["resolution"] == "unresolved_conflict"
    values = {c["value"] for c in dizziness["candidates"]}
    assert values == {"moderate", "present"}


def test_negation_and_hedging_never_become_uncertainty():
    negated = mapped("providehr", "ambient-symptom-negated")
    hedged = mapped("providehr", "ambient-symptom-hedged")
    assert negated["measurement"]["value"] == "absent"
    assert hedged["quality"]["flags"] == ["speaker_hedged"]
    for envelope in (negated, hedged):
        assert envelope["uncertainty"] == {"status": "unknown"}


def test_admitted_observation_is_linked_by_reference_with_invivo_identity_rules():
    item = record("metabolog", "admitted-body-temperature")
    example = json.loads(
        (ROOT / "examples" / "local-observations" / "synthetic-body-temperature.v1.json").read_text(encoding="utf-8")
    )["composition"]["context"]["openbody_observation"]
    assert item["record"] == example
    envelope = item["expect"]["envelope"]
    version_uid = example["source"]["clinical_version"]["version_uid"]
    # InVivo (#1131) accepts an admitted id only as urn:openbody:observation:<version_uid>.
    assert example["id"] == f"urn:openbody:observation:{version_uid}"
    assert envelope["clinical_link"] == {
        "profile": "openbody.admitted-observation.v1",
        "admitted_observation_id": example["id"],
        "clinical_version_ref": example["id"],
        "content_digest": INTEROP["canonical_digest"]["admitted_observation_example"]["content_digest"],
    }
    assert envelope["source"]["record_digest"] == example["source"]["resource_digest"]
    assert envelope["subject"] != example["subject"]
    # Revoking the admitted clinical version excludes the linked envelope.
    snapshot = assemble(all_envelopes(), revoked=[example["id"]])
    assert {x["observation_id"]: x["code"] for x in snapshot["exclusions"]}[envelope["observation_id"]] == "source_revoked"


def test_admitted_numeric_uncertainty_is_refused_not_dropped():
    item = record("metabolog", "admitted-body-temperature")
    admitted = copy.deepcopy(item["record"])
    admitted["uncertainty"]["epistemic"] = 0.2
    with pytest.raises(MappingRefused) as refused:
        map_metabolog_admitted_observation(admitted, item["context"])
    assert refused.value.code == "uncertainty_not_representable"


@pytest.mark.parametrize(
    ("epistemic_class", "origin", "expected"),
    [
        ("observed", "device_sensor", "observed"),
        ("observed", "self_report", "reported"),
        ("observed", "conversation", "reported"),
        ("derived", "model_transform", "derived"),
        ("statistical_inference", "model_transform", "inferred"),
    ],
)
def test_metabolog_epistemic_classes_map_by_origin(epistemic_class, origin, expected):
    assert map_metabolog_epistemic_class(epistemic_class, origin) == expected


@pytest.mark.parametrize(
    ("epistemic_class", "code"),
    [("mechanistic_inference", "model_family_contract_required"), ("guess", "epistemic_class_unmapped")],
)
def test_metabolog_model_classes_are_refused(epistemic_class, code):
    with pytest.raises(MappingRefused) as refused:
        map_metabolog_epistemic_class(epistemic_class, "model_transform")
    assert refused.value.code == code


def test_providehr_revocation_and_consent_withdrawal_become_host_revocations():
    key = {"clinical_system": "ehr-a", "adapter_id": "fhir-style", "connection_id": "conn-1"}
    other = dict(key, connection_id="conn-2")
    sources = [
        {"key": key, "availability": {"availability": "revoked", "reason": "grant withdrawn"}},
        {"key": other, "availability": {"availability": "stale", "last_recorded_at": "2026-01-01T00:00:00Z"}},
    ]
    consents = [
        {"consent_ref": "urn:providehr:consent:enc-1:ambient", "withdrawn": True},
        {"consent_ref": "urn:providehr:consent:enc-2:ambient", "withdrawn": False},
    ]
    assert providehr_revocations(sources, consents) == sorted(
        [providehr_source_id(key), "urn:providehr:consent:enc-1:ambient"]
    )
    # A withdrawn capture consent excludes every fact captured under it.
    ambient = [mapped("providehr", n) for n in ("ambient-symptom-present", "ambient-symptom-negated")]
    snapshot = assemble(ambient, revoked=["urn:providehr:consent:enc-1:ambient"])
    assert {x["code"] for x in snapshot["exclusions"]} == {"consent_revoked"}
    assert snapshot["entries"] == []


def test_providehr_unmapped_purpose_is_refused():
    item = record("providehr", "ambient-symptom-present")
    context = copy.deepcopy(item["context"])
    context["capture_consent"]["purpose"] = "marketing"
    with pytest.raises(MappingRefused) as refused:
        map_providehr_contribution(item["record"], context)
    assert refused.value.code == "purpose_unmapped"


def test_correction_revokes_the_superseded_revision_only():
    snapshot = assemble(all_envelopes())
    old = mapped("twinsuite", "conversation-correction-superseded")
    new = mapped("twinsuite", "conversation-correction-current")
    assert {x["observation_id"]: x["code"] for x in snapshot["exclusions"]} == {old["observation_id"]: "source_revoked"}
    assert entry(snapshot, "symptom-description")["basis"] == [new["observation_id"]]


def test_two_consumers_emitting_one_record_under_different_sources_is_rejected():
    said = mapped("twinsuite", "conversation-said")
    duplicate = copy.deepcopy(said)
    duplicate["observation_id"] = "invivo:conversation:utt-0042"
    duplicate["source"]["source_id"] = "urn:invivo:source:conversation:twin-app"
    with pytest.raises(WholePersonStateError) as caught:
        assemble(all_envelopes() + [duplicate])
    assert caught.value.code == "source_identity_conflict"


@pytest.mark.parametrize("vector", INTEROP["canonical_digest"]["vectors"], ids=lambda v: v["name"])
def test_canonical_digest_vectors(vector):
    value = json.loads(vector["wire"])
    assert json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) == vector["canonical"]
    assert canonical_digest(value) == vector["digest"]


def test_integral_float_and_integer_wire_forms_digest_differently():
    vectors = {v["name"]: v for v in INTEROP["canonical_digest"]["vectors"]}
    assert vectors["integral-float-keeps-fraction"]["digest"] != vectors["integer-stays-integer"]["digest"]


def test_native_validator_inventory_matches_the_schemas():
    native = INTEROP["native_validation"]
    supported = set(native["supported_keywords"])
    for name, expected in native["schemas"].items():
        vocab = schema_vocabulary(json.loads((ROOT / "schemas" / f"{name}.schema.json").read_text(encoding="utf-8")))
        assert {k: expected[k] for k in ("keywords", "formats", "refs")} == vocab, name
        assert expected["unsupported_keywords"] == sorted(set(vocab["keywords"]) - supported)
        assert expected["unsupported_formats"] == sorted(set(vocab["formats"]) - set(native["supported_formats"]))
        assert expected["unsupported_refs"] == sorted(set(vocab["refs"]) - set(native["supported_refs"]))
    # The profile InVivo already consumes fits its validator; the whole-person schemas do not yet.
    admitted = native["schemas"]["admitted-observation"]
    assert not (admitted["unsupported_keywords"] or admitted["unsupported_formats"] or admitted["unsupported_refs"])
    assert native["schemas"]["whole-person-observation"]["unsupported_keywords"]


def test_corpus_detects_disabled_identity_and_consistency_checks(monkeypatch):
    monkeypatch.setattr(whole_person, "_check_source_identity", lambda inputs: None)
    monkeypatch.setattr(whole_person, "_check_state_consistency", lambda snapshot: None)
    failed = {r.name for r in evaluate_conformance_corpus() if not r.passed}
    assert {
        "identity-record-claimed-by-two-sources",
        "identity-record-revised-under-same-ref",
        "identity-code-in-two-domains",
        "state-admission-despite-blockers",
        "state-blocker-dropped",
        "state-conflict-relabelled-concordant",
        "state-input-unaccounted",
    } <= failed


def test_mapping_corpus_detects_a_mapper_regression(monkeypatch):
    from openbody_ref import whole_person_mapping

    original = whole_person_mapping.map_twinsuite_candidate

    def promote(candidate, context, parent=None):
        envelope = original(candidate, context, parent)
        if candidate["assertion"] == "confirmed":
            envelope = copy.deepcopy(envelope)
            envelope["quality"]["flags"] = []
        return envelope

    monkeypatch.setitem(whole_person_mapping.MAPPERS, "twinsuite.candidate", promote)
    failed = {r.name for r in whole_person_mapping.evaluate_consumer_mapping() if not r.passed}
    assert "consumer-mapping twinsuite/conversation-confirmed" in failed
