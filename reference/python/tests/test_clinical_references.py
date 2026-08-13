from __future__ import annotations

import copy
import json
from datetime import datetime

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from openbody_ref.clinical_reference import (
    FIXTURE_BUNDLE_PATH,
    REFERENCE_SCHEMA_PATH,
    ROOT,
    ClinicalReferenceError,
    expand_fixture_cases,
    merge_patch,
    validate_clinical_reference,
    validate_fixture_bundle,
)


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def fixtures():
    bundle = load(FIXTURE_BUNDLE_PATH)
    return bundle, {case["name"]: (case, reference) for case, reference in expand_fixture_cases(bundle)}


def assert_rejected(reference, resolved_object, code):
    with pytest.raises(ClinicalReferenceError) as caught:
        validate_clinical_reference(
            reference,
            resolved_object,
            evaluated_at=datetime.fromisoformat("2026-08-13T12:00:00+00:00"),
        )
    assert caught.value.code == code


def test_fixture_bundle_matches_every_expected_admission_result():
    results = validate_fixture_bundle()
    assert len(results) == 11
    assert all(result.passed for result in results), results


def test_merge_patch_is_rfc_7396_and_does_not_mutate_base():
    base = {"a": {"b": 1, "c": 2}, "keep": [1, 2]}
    snapshot = copy.deepcopy(base)
    assert merge_patch(base, {"a": {"b": None, "d": 3}, "keep": [4]}) == {
        "a": {"c": 2, "d": 3},
        "keep": [4],
    }
    assert base == snapshot


def test_every_openbody_projection_is_structurally_valid():
    bundle, cases = fixtures()
    schema = load(REFERENCE_SCHEMA_PATH)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    for name, (_, reference) in cases.items():
        if name == "source-observation-is-not-derived-assertion":
            continue
        assert list(validator.iter_errors(reference)) == [], name
    assert bundle["schema_version"] == "openbody.clinical-assertion-reference-fixtures/1.0"


def test_unknown_uncertainty_cannot_smuggle_numeric_certainty():
    _, cases = fixtures()
    _, reference = cases["unknown-insufficient"]
    assert reference["uncertainty"] == {
        "reasons": ["Uncertainty cannot be estimated from available evidence."],
        "status": "unknown",
    }
    resolved_object = load(ROOT / "examples/post-meal-walk.scenario.json")
    assert_rejected(reference, resolved_object, "applicability_insufficient")


@pytest.mark.parametrize(
    ("name", "code"),
    [
        ("positive-applicable-known-valid", None),
        ("contradictory", "applicability_contradictory"),
        ("inapplicable-out-of-distribution", "out_of_distribution"),
        ("abstained", "abstained"),
        ("stale", "stale"),
        ("retracted", "retracted"),
        ("superseded", "superseded"),
        ("digest-mismatch", "content_digest_mismatch"),
        ("unresolved-subject", "subject_binding_unresolvable"),
        ("source-observation-is-not-derived-assertion", "not_openbody_reference"),
    ],
)
def test_named_boundary_cases(name, code):
    _, cases = fixtures()
    case, reference = cases[name]
    resolved_object = load(ROOT / case["resolved_object"])
    if code is None:
        validate_clinical_reference(
            reference,
            resolved_object,
            evaluated_at=datetime.fromisoformat("2026-08-13T12:00:00+00:00"),
        )
    else:
        assert_rejected(reference, resolved_object, code)


@pytest.mark.parametrize(
    ("patch", "code"),
    [
        ({"subject": "subject:someone-else"}, "subject_mismatch"),
        ({"scope": ["ob://human/cardiovascular"]}, "scope_mismatch"),
        (
            {"evidence_lineage": [{
                "canonical_ref": "local://cgm/meal-response-set-001",
                "content_digest": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "model_refs": ["another-model"],
                "observed_at": "2026-08-09T18:00:00Z",
                "scopes": ["ob://human/metabolic/glucose_regulation"],
                "subject": "subject:local-demo",
            }]},
            "evidence_model_mismatch",
        ),
    ],
)
def test_subject_scope_and_lineage_tampering_fail_closed(patch, code):
    bundle, _ = fixtures()
    reference = merge_patch(bundle["base_reference"], patch)
    resolved_object = load(ROOT / "examples/post-meal-walk.scenario.json")
    assert_rejected(reference, resolved_object, code)


def test_retraction_and_supersession_require_resolvable_pointers():
    bundle, _ = fixtures()
    resolved_object = load(ROOT / "examples/post-meal-walk.scenario.json")
    retracted = merge_patch(
        bundle["base_reference"],
        {"validity": {"status": "retracted", "valid_until": None}},
    )
    superseded = merge_patch(
        bundle["base_reference"],
        {"validity": {"status": "superseded", "valid_until": None}},
    )
    assert_rejected(retracted, resolved_object, "structural_invalid")
    assert_rejected(superseded, resolved_object, "structural_invalid")
