from __future__ import annotations

import copy
import json

import pytest

from openbody_ref.intervention_observation import (
    ROOT,
    InterventionObservationError,
    validate_intervention_observation,
)


def fixture():
    return json.loads(
        (ROOT / "examples" / "cymbathera-intervention-observation.v2.json").read_text(
            encoding="utf-8"
        )
    )


def rejected(value, code):
    with pytest.raises(InterventionObservationError) as caught:
        validate_intervention_observation(value)
    assert caught.value.code == code


def test_example_is_a_valid_source_observation():
    validate_intervention_observation(fixture())


def test_raw_signal_payload_cannot_be_disclosed():
    value = fixture()
    value["evidence"][0]["contains_raw_signal"] = True
    rejected(value, "structural_invalid")


def test_unavailable_dose_cannot_invent_a_value():
    value = fixture()
    value["intervention"]["dose"][1]["value"] = 50
    value["intervention"]["dose"][1]["unit"] = "%"
    rejected(value, "structural_invalid")


def test_unknown_scope_fails_closed():
    value = fixture()
    value["scope"] = ["ob://human/imaginary"]
    rejected(value, "unsupported_scope")


def test_interval_and_consent_window_are_ordered():
    value = fixture()
    value["intervention"]["ended_at"] = "2026-08-30T07:00:00Z"
    rejected(value, "invalid_interval")

    value = fixture()
    value["disclosure"]["expires_at"] = "2026-08-30T07:00:00Z"
    rejected(value, "invalid_consent_window")


def test_disclosure_allowlist_cannot_name_absent_content():
    value = fixture()
    del value["user_response"]
    rejected(value, "disclosed_field_missing")


def test_source_observation_still_fails_clinical_assertion_boundary():
    from openbody_ref.clinical_reference import ClinicalReferenceError, validate_clinical_reference
    from datetime import datetime

    value = fixture()
    with pytest.raises(ClinicalReferenceError) as caught:
        validate_clinical_reference(value, {}, evaluated_at=datetime.now().astimezone())
    assert caught.value.code == "not_openbody_reference"
