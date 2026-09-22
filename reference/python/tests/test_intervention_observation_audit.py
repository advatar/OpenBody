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
    validate_intervention_observation,
)

EXAMPLES = [
    "cymbathera-intervention-observation.v1.json",
    "paced-breathing-intervention-observation.v1.json",
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
    value = example("paced-breathing-intervention-observation.v1.json")
    assert value["observed_measurements"][1]["value"] == 0
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
        (("intervention", "intervention_id"), "HRV improved because of stimulation"),
        (("intervention", "protocol_id"), "recommended stimulation: 25 Hz daily"),
        (("intervention", "dose", 0, "name"), "effective dose"),
        (("intervention", "device", "model"), "diagnosis: autonomic dysfunction"),
    ],
)
def test_identifier_strings_are_not_semantically_checked(path, text):
    # Documented limit: identifiers are opaque producer labels. Wording in them
    # is not a claim the profile carries, and consumers must not read it as one.
    value = example()
    at(value, path[:-1])[path[-1]] = text
    validate_intervention_observation(value)
