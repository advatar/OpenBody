"""Adversarial tests from the post-merge audit of the intervention profile.

Each test pins one row of the claim-to-enforcement table in
docs/INTERVENTION_OBSERVATIONS.md: either a guarantee the validator enforces,
or a limit the documentation must not overstate.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from datetime import datetime, timezone

import pytest

from openbody_ref.clinical_reference import ClinicalReferenceError, validate_clinical_reference
from openbody_ref.intervention_observation import (
    ROOT,
    InterventionObservationError,
    InterventionObservationIntake,
    validate_intervention_observation,
)

EXAMPLES = [
    "cymbathera-intervention-observation.v2.json",
    "paced-breathing-intervention-observation.v2.json",
]

SMUGGLE_KEYS = [
    "samples", "values", "waveform", "ecg", "eeg", "signal", "voltage",
    "data", "payload", "attachment", "blob", "base64", "raw", "extensions",
]


def example(name: str = EXAMPLES[0]) -> dict:
    return json.loads((ROOT / "examples" / name).read_text(encoding="utf-8"))


def rejected(value, code):
    with pytest.raises(InterventionObservationError) as caught:
        validate_intervention_observation(value)
    assert caught.value.code == code, str(caught.value)


def object_paths(value, path=()):
    """Every JSON object location in a document, as a key/index path."""
    if isinstance(value, dict):
        yield path
        for key, child in value.items():
            yield from object_paths(child, path + (key,))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from object_paths(child, path + (index,))


def at(value, path):
    for step in path:
        value = value[step]
    return value


@pytest.mark.parametrize("name", EXAMPLES)
def test_examples_are_valid(name):
    validate_intervention_observation(example(name))


# Raw signal carriage -------------------------------------------------------


@pytest.mark.parametrize("key", SMUGGLE_KEYS)
def test_no_object_anywhere_accepts_an_extra_payload_field(key):
    base = example()
    paths = list(object_paths(base))
    assert len(paths) > 10
    for path in paths:
        value = copy.deepcopy(base)
        at(value, path)[key] = [0.12, 0.15, 0.11, 0.09]
        rejected(value, "structural_invalid")


def test_numeric_fields_accept_scalars_only():
    value = example()
    value["observed_measurements"][0]["value"] = [71, 72, 70]
    rejected(value, "structural_invalid")
    value = example()
    value["intervention"]["dose"][0]["value"] = {"samples": [1, 2]}
    rejected(value, "structural_invalid")


def test_evidence_must_attest_no_raw_signal():
    value = example()
    value["evidence"][0]["contains_raw_signal"] = True
    rejected(value, "structural_invalid")
    value = example()
    del value["evidence"][0]["contains_raw_signal"]
    rejected(value, "structural_invalid")


def test_reference_strings_are_bounded_not_content_checked():
    # A reference may name raw evidence held elsewhere; the profile bounds the
    # string but does not inspect it. This pins the documented limit.
    value = example()
    value["evidence"][0]["canonical_ref"] = "x" * 501
    rejected(value, "structural_invalid")
    value = example()
    value["evidence"][0]["canonical_ref"] = "invivo://raw/ecg/session-001"
    validate_intervention_observation(value)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_numbers_are_rejected(bad):
    value = example()
    value["observed_measurements"][0]["value"] = bad
    rejected(value, "structural_invalid")
    value = example()
    value["intervention"]["dose"][0]["value"] = bad
    rejected(value, "structural_invalid")


# Missingness ---------------------------------------------------------------


def test_measured_zero_is_legitimate():
    value = example("paced-breathing-intervention-observation.v2.json")
    assert value["observed_measurements"][2]["value"] == 0
    validate_intervention_observation(value)


def test_missing_measurement_cannot_be_null_or_empty():
    value = example()
    value["observed_measurements"][0]["value"] = None
    rejected(value, "structural_invalid")
    value = example()
    del value["observed_measurements"][0]["value"]
    rejected(value, "structural_invalid")


def test_no_measurements_at_all_is_representable_by_omission():
    value = example()
    value["observed_measurements"] = []
    value["disclosure"]["fields"].remove("observed_measurements")
    validate_intervention_observation(value)


# Dose availability ---------------------------------------------------------


@pytest.mark.parametrize(
    "extra",
    [
        {"value": 0},
        {"value": 50, "unit": "%"},
        {"unit": "mA"},
        {"range": [1, 2]},
        {"derived_dose": 3},
        {"estimated_value": 1},
        {"dose": {"value": 1}},
    ],
)
def test_unavailable_dose_cannot_carry_a_value(extra):
    value = example()
    value["intervention"]["dose"][1].update(extra)
    rejected(value, "structural_invalid")


@pytest.mark.parametrize("status", ["planned", "observed", "patient_reported"])
def test_available_dose_requires_value_and_unit(status):
    value = example()
    value["intervention"]["dose"][1]["status"] = status
    rejected(value, "structural_invalid")


# Projection class and the clinical-assertion boundary ----------------------


@pytest.mark.parametrize("projection_class", ["openbody_reference", "derived", "clinical_assertion", None])
def test_projection_class_cannot_be_mutated(projection_class):
    value = example()
    value["projection_class"] = projection_class
    rejected(value, "structural_invalid")


@pytest.mark.parametrize("name", EXAMPLES)
def test_source_observation_is_never_admitted_as_clinical_assertion(name):
    now = datetime.now(timezone.utc)
    original = example(name)
    with pytest.raises(ClinicalReferenceError) as caught:
        validate_clinical_reference(original, {}, evaluated_at=now)
    assert caught.value.code == "not_openbody_reference"

    # Relabelling it, even with itself as the resolved object, fails the
    # assertion schema rather than reaching digest or model checks.
    relabelled = copy.deepcopy(original)
    relabelled["projection_class"] = "openbody_reference"
    for resolved in ({}, relabelled):
        with pytest.raises(ClinicalReferenceError) as caught:
            validate_clinical_reference(relabelled, resolved, evaluated_at=now)
        assert caught.value.code == "structural_invalid"


def test_conformance_validator_routes_and_fails_closed(tmp_path):
    cases = {
        "relabelled.json": dict(example(), projection_class="openbody_reference"),
        "unversioned.json": {k: v for k, v in example().items() if k != "schema_version"},
    }
    for name, doc in cases.items():
        (tmp_path / name).write_text(json.dumps(doc), encoding="utf-8")
    (tmp_path / "array.json").write_text("[]", encoding="utf-8")
    paths = [tmp_path / name for name in [*cases, "array.json"]]
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "validate_openbody.py"), *map(str, paths)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "Traceback" not in result.stderr, result.stderr
    for path in paths:
        assert f"FAIL {path}" in result.stdout, path


# Disclosure allowlist ------------------------------------------------------


@pytest.mark.parametrize(
    "remove",
    ["intervention", "observed_measurements", "evidence", "user_response"],
)
def test_carried_content_must_be_disclosed(remove):
    value = example()
    value["disclosure"]["fields"].remove(remove)
    rejected(value, "undisclosed_content_present")


@pytest.mark.parametrize(
    "mutate",
    [
        lambda v: v.pop("user_response"),
        lambda v: v.__setitem__("evidence", []),
        lambda v: v.__setitem__("observed_measurements", []),
    ],
)
def test_disclosure_cannot_name_absent_content(mutate):
    value = example()
    mutate(value)
    rejected(value, "disclosed_field_missing")


@pytest.mark.parametrize(
    "field",
    [
        "subject",
        "subject_binding",
        "/intervention/dose",
        "intervention/dose",
        "intervention.dose",
        "observed_measurements/0",
        "",
        "*",
        "Intervention",
    ],
)
def test_disclosure_names_only_top_level_sections(field):
    value = example()
    value["disclosure"]["fields"].append(field)
    rejected(value, "structural_invalid")


def test_duplicate_disclosure_entries_are_rejected():
    value = example()
    value["disclosure"]["fields"].append("evidence")
    rejected(value, "structural_invalid")


# Consent and subject binding: declarations, not verification ---------------


def test_consent_is_a_reference_not_a_verification():
    # Any well-formed URI is accepted: nothing resolves, authenticates, or
    # checks the currency or revocation of the consent it names.
    value = example()
    value["disclosure"]["consent_ref"] = "urn:uuid:00000000-0000-0000-0000-000000000000"
    validate_intervention_observation(value)
    value["disclosure"]["consent_ref"] = "not a uri"
    rejected(value, "structural_invalid")


@pytest.mark.parametrize("expires_at", ["2026-08-30T07:00:00Z", "2026-08-30T08:30:00Z"])
def test_consent_window_must_have_positive_length(expires_at):
    value = example()
    value["disclosure"]["expires_at"] = expires_at
    rejected(value, "invalid_consent_window")


def test_subject_binding_status_is_a_declaration():
    value = example()
    value["subject_binding"]["status"] = "asserted"
    rejected(value, "structural_invalid")
    # A placeholder proof is accepted: the validator does not verify the binding.
    value = example()
    value["subject_binding"]["proof_digest"] = "sha256:" + "0" * 64
    validate_intervention_observation(value)


# Timing --------------------------------------------------------------------


@pytest.mark.parametrize(
    "path,bad",
    [
        (("intervention", "started_at"), "yesterday"),
        (("intervention", "started_at"), "2026-08-30T08:01:00"),
        (("intervention", "ended_at"), "2026-08-30"),
        (("disclosure", "authorized_at"), "2026-13-01T00:00:00Z"),
        (("observed_measurements", 0, "observed_at"), "08:00:30Z"),
    ],
)
def test_malformed_timestamps_are_rejected(path, bad):
    value = example()
    at(value, path[:-1])[path[-1]] = bad
    rejected(value, "structural_invalid")


def test_session_interval_is_ordered():
    value = example()
    value["intervention"]["ended_at"] = "2026-08-30T07:00:00Z"
    rejected(value, "invalid_interval")


@pytest.mark.parametrize(
    "index,observed_at",
    [
        (0, "2026-08-30T08:05:00Z"),  # before, observed after start
        (1, "2026-08-30T07:59:00Z"),  # end, observed before start
        (2, "2026-08-30T08:05:00Z"),  # follow_up, observed before end
    ],
)
def test_measurement_phase_agrees_with_session(index, observed_at):
    value = example()
    value["observed_measurements"][index]["observed_at"] = observed_at
    rejected(value, "invalid_measurement_phase")


def test_response_cannot_precede_session():
    value = example()
    value["user_response"]["recorded_at"] = "2026-08-30T07:00:00Z"
    rejected(value, "invalid_interval")


# Derived analyses and claims -----------------------------------------------


def test_evidence_reference_cannot_carry_its_own_epistemic_class():
    for key, claim in [
        ("epistemic_class", "inferred"),
        ("conclusion", "vagal target engaged"),
        ("finding", "HRV improved because of stimulation"),
    ]:
        value = example()
        value["evidence"][0][key] = claim
        rejected(value, "structural_invalid")


@pytest.mark.parametrize(
    "path,key",
    [
        ((), "interpretation"),
        ((), "effect"),
        (("user_response",), "note"),
        (("claim_boundary",), "summary"),
        (("intervention",), "recommendation"),
    ],
)
def test_no_free_text_claim_field_exists(path, key):
    value = example()
    at(value, path)[key] = "patient responded to therapy"
    rejected(value, "structural_invalid")


@pytest.mark.parametrize("field", ["causal_claim", "diagnosis", "treatment_recommendation"])
def test_claim_boundary_flags_are_fixed(field):
    value = example()
    value["claim_boundary"][field] = True
    rejected(value, "structural_invalid")


def test_response_is_a_closed_vocabulary():
    value = example()
    value["user_response"]["felt"] = "responded to therapy"
    rejected(value, "structural_invalid")


@pytest.mark.parametrize(
    "path,text",
    [
        (("observation_id",), "HRV improved because of stimulation"),
        (("intervention", "intervention_id"), "patient responded to therapy"),
        (("intervention", "protocol_id"), "recommended stimulation: 25 Hz daily"),
        (("intervention", "device", "model"), "diagnosis: autonomic dysfunction"),
        (("source", "app_version"), "effective dose"),
        (("observed_measurements", 0, "source_ref"), "healthkit://hr because of stimulation"),
        (("evidence", 0, "canonical_ref"), "vagal target engaged"),
    ],
)
def test_identifiers_and_references_cannot_carry_prose(path, text):
    value = example()
    at(value, path[:-1])[path[-1]] = text
    rejected(value, "structural_invalid")


@pytest.mark.parametrize("name", ["effective_dose", "effective dose", "dose", "intensity"])
def test_dose_dimensions_are_a_closed_vocabulary(name):
    value = example()
    value["intervention"]["dose"][0]["name"] = name
    rejected(value, "structural_invalid")


def test_identifier_tokens_are_still_not_read_for_meaning():
    # Documented limit: a token forbids prose, not meaning. Consumers must treat
    # identifiers as opaque.
    value = example()
    value["intervention"]["intervention_id"] = "patient_responded_to_therapy"
    validate_intervention_observation(value)


# Version 2.0 structure -------------------------------------------------------


def test_version_1_documents_fail_closed():
    value = example()
    value["schema_version"] = "openbody.intervention-observation/1.0"
    rejected(value, "structural_invalid")


def test_follow_up_offset_is_derived_not_declared():
    value = example()
    value["observed_measurements"][2]["follow_up_offset_seconds"] = 900
    rejected(value, "structural_invalid")


@pytest.mark.parametrize("field", ["value", "unit", "observed_at", "source_ref", "origin"])
def test_not_observed_measurement_carries_nothing_observed(field):
    value = example()
    not_observed = value["observed_measurements"][3]
    assert not_observed["status"] == "not_observed"
    not_observed[field] = value["observed_measurements"][0][field]
    rejected(value, "structural_invalid")


def test_not_observed_measurement_needs_a_reason_and_observed_forbids_one():
    value = example()
    del value["observed_measurements"][3]["reason"]
    rejected(value, "structural_invalid")
    value = example()
    value["observed_measurements"][0]["reason"] = "no_sample"
    rejected(value, "structural_invalid")


@pytest.mark.parametrize("field", ["observed_at", "source_ref", "origin", "unit"])
def test_observed_measurement_needs_its_provenance(field):
    value = example()
    del value["observed_measurements"][0][field]
    rejected(value, "structural_invalid")


@pytest.mark.parametrize(
    "metric,unit,number",
    [
        ("heart_rate", "beats/min", 70),
        ("heart_rate", "/min", -1),
        ("hrv_sdnn", "s", 0.05),
        ("step_count", "{steps}", 1.5),
        ("eeg_alpha_relative_power", "1", 1.2),
        ("eeg_alpha_relative_power", "%", 0.3),
    ],
)
def test_measurement_unit_and_range_are_bound_to_metric(metric, unit, number):
    value = example()
    value["observed_measurements"][0].update(metric=metric, unit=unit, value=number)
    rejected(value, "structural_invalid")


@pytest.mark.parametrize(
    "name,unit,number",
    [("duration", "min", 7), ("duration", "s", -1), ("intensity_setting", "1", 1.5), ("repetitions", "{count}", 2.5)],
)
def test_dose_unit_and_range_are_bound_to_dimension(name, unit, number):
    value = example()
    value["intervention"]["dose"][0].update(name=name, unit=unit, value=number)
    rejected(value, "structural_invalid")


def test_a_series_cannot_be_carried_as_repeated_measurements():
    value = example()
    first = value["observed_measurements"][0]
    value["observed_measurements"] = [dict(first, value=70 + i % 5) for i in range(40)]
    rejected(value, "duplicate_measurement")
    value["observed_measurements"] = [dict(first, value=70 + i % 5) for i in range(65)]
    rejected(value, "structural_invalid")


def test_contradictory_measurements_are_rejected():
    value = example()
    value["observed_measurements"].append(
        {"phase": "before", "metric": "heart_rate", "status": "not_observed", "reason": "no_sample"}
    )
    rejected(value, "duplicate_measurement")


def test_dose_dimension_appears_once_per_status():
    value = example()
    value["intervention"]["dose"].append(dict(value["intervention"]["dose"][0], value=300))
    rejected(value, "duplicate_dose_dimension")
    # Planned and observed values of one dimension may both be carried.
    value = example()
    value["intervention"]["dose"].append(dict(value["intervention"]["dose"][0], status="planned", value=600))
    validate_intervention_observation(value)


def test_derived_analysis_must_name_its_producer():
    value = example()
    del value["evidence"][0]["produced_by"]
    rejected(value, "structural_invalid")
    value = example()
    value["evidence"][0]["kind"] = "patient_report"
    rejected(value, "structural_invalid")


@pytest.mark.parametrize("kind", ["vagus_analysis", "eeg_derived_features", "other", "openbody_state"])
def test_evidence_kinds_are_neutral_and_closed(kind):
    value = example()
    value["evidence"][0]["kind"] = kind
    rejected(value, "structural_invalid")


def test_disclosure_names_a_recipient():
    value = example()
    del value["disclosure"]["recipient"]
    rejected(value, "structural_invalid")


def test_subject_binding_precedes_disclosure():
    value = example()
    value["subject_binding"]["verified_at"] = "2026-08-30T09:00:00Z"
    rejected(value, "invalid_subject_binding")


# Reference intake: what the payload cannot enforce -------------------------

RECIPIENT = "https://providehr.example/intake"
RECEIVED_AT = datetime(2026, 8, 30, 9, 0, tzinfo=timezone.utc)


def accept(observation, evaluated_at):
    return True


def intake(**overrides):
    options = dict(recipient=RECIPIENT, verify_subject_binding=accept, verify_consent=accept)
    options.update(overrides)
    return InterventionObservationIntake(**options)


def refused(receiver, value, code, evaluated_at=RECEIVED_AT):
    with pytest.raises(InterventionObservationError) as caught:
        receiver.receive(value, evaluated_at=evaluated_at)
    assert caught.value.code == code, str(caught.value)


def test_intake_requires_both_verifiers():
    with pytest.raises(TypeError):
        InterventionObservationIntake(recipient=RECIPIENT, verify_consent=accept)
    with pytest.raises(TypeError):
        InterventionObservationIntake(recipient=RECIPIENT, verify_subject_binding=accept)


def test_intake_admits_then_treats_identical_retry_as_replay():
    receiver = intake()
    first = receiver.receive(example(), evaluated_at=RECEIVED_AT)
    assert (first.outcome, first.evidence_class) == ("admitted", "source_observation")
    again = receiver.receive(example(), evaluated_at=RECEIVED_AT)
    assert again.outcome == "replay"
    assert again.content_digest == first.content_digest


def test_intake_rejects_id_reuse_with_different_content():
    receiver = intake()
    receiver.receive(example(), evaluated_at=RECEIVED_AT)
    changed = example()
    changed["observed_measurements"][0]["value"] = 72
    refused(receiver, changed, "observation_id_conflict")


@pytest.mark.parametrize(
    "overrides,code",
    [
        ({"verify_subject_binding": lambda o, t: False}, "subject_binding_unverified"),
        ({"verify_subject_binding": lambda o, t: "yes"}, "subject_binding_unverified"),
        ({"verify_subject_binding": lambda o, t: 1 / 0}, "subject_binding_unverified"),
        ({"verify_consent": lambda o, t: False}, "consent_unverified"),
        ({"verify_consent": lambda o, t: None}, "consent_unverified"),
        ({"recipient": "https://someone-else.example/intake"}, "recipient_mismatch"),
    ],
)
def test_intake_fails_closed_without_verification(overrides, code):
    refused(intake(**overrides), example(), code)


def test_intake_enforces_the_consent_window_at_receipt():
    refused(intake(), example(), "consent_not_yet_valid", datetime(2026, 8, 30, 8, 29, tzinfo=timezone.utc))
    value = example()
    value["disclosure"]["expires_at"] = "2026-08-30T08:45:00Z"
    refused(intake(), value, "consent_expired")


def test_intake_requires_an_aware_evaluation_time():
    refused(intake(), example(), "invalid_evaluation_time", datetime(2026, 8, 30, 9, 0))


def test_intake_validates_before_verifying():
    calls = []
    receiver = intake(verify_subject_binding=lambda o, t: calls.append(o) or True)
    value = example()
    value["projection_class"] = "openbody_reference"
    refused(receiver, value, "structural_invalid")
    assert calls == []
