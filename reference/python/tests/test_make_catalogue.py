"""The subject-bound to catalogue transform."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))

from make_catalogue import to_catalogue  # noqa: E402

from openbody_ref.host import CATALOGUE_SUBJECT  # noqa: E402


def descriptor(subject: str = "subject:invivo-local", **overrides) -> dict:
    value = {
        "schema_version": "0.1",
        "kind": "BodyModel",
        "id": "invivo-example",
        "version": "0.1.0",
        "family": "statistical",
        "provider": "InVivo",
        "scopes": ["ob://human/metabolic"],
        "capabilities": ["state_estimation"],
        "required_inputs": ["cgm_glucose_series"],
        "outputs": ["state"],
        "applicability": {
            "mode": "shipped",
            "subject": subject,
            "scopes": ["ob://human/metabolic"],
            "horizon_seconds": 86_400,
            "evidence_boundary": "the subject's own observations",
            "generalizable": False,
        },
        "validation": {"status": "evaluated_in_product", "references": []},
        "prohibited_uses": ["clinical decision-making"],
        "execution": {"mode": "on_device"},
        "dependencies": [],
    }
    value.update(overrides)
    return value


def test_the_subject_is_replaced_with_the_catalogue_subject() -> None:
    catalogue = to_catalogue(descriptor())
    assert catalogue["applicability"]["subject"] == CATALOGUE_SUBJECT


def test_nothing_else_about_the_model_changes() -> None:
    source = descriptor()
    catalogue = to_catalogue(source)
    for key in ("id", "version", "family", "scopes", "capabilities",
                "required_inputs", "outputs", "validation", "prohibited_uses"):
        assert catalogue[key] == source[key], key
    # Every applicability member except the subject survives.
    for key, value in source["applicability"].items():
        if key != "subject":
            assert catalogue["applicability"][key] == value, key


def test_the_source_is_not_mutated() -> None:
    source = descriptor()
    to_catalogue(source)
    assert source["applicability"]["subject"] == "subject:invivo-local"


def test_an_already_catalogued_descriptor_passes_through() -> None:
    catalogue = to_catalogue(descriptor(subject=CATALOGUE_SUBJECT))
    assert catalogue["applicability"]["subject"] == CATALOGUE_SUBJECT


def test_a_subject_hidden_elsewhere_is_refused() -> None:
    # The transform is only correct if applicability.subject is the sole carrier.
    # A leak the transform did not know about must stop publication, not ride along.
    leaky = descriptor()
    leaky["dependencies"] = ["twin:subject:invivo-local"]
    with pytest.raises(ValueError, match="carries the source subject"):
        to_catalogue(leaky)


def test_a_subject_in_a_nested_string_is_refused() -> None:
    leaky = descriptor()
    leaky["validation"] = {
        "status": "evaluated_in_product",
        "references": ["cohort of subject:invivo-local"],
    }
    with pytest.raises(ValueError, match="carries the source subject"):
        to_catalogue(leaky)


def test_a_non_descriptor_is_refused() -> None:
    with pytest.raises(ValueError, match="not a BodyModel"):
        to_catalogue({"kind": "BodyState", "id": "x"})


def test_a_descriptor_without_a_subject_is_refused() -> None:
    value = descriptor()
    del value["applicability"]["subject"]
    with pytest.raises(ValueError, match="no applicability.subject"):
        to_catalogue(value)
