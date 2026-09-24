from __future__ import annotations

import copy
from datetime import datetime, timezone

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from openbody_ref.clinical_reference import (
    REFERENCE_SCHEMA_PATH,
    ClinicalReferenceError,
    validate_clinical_reference,
)
from openbody_ref.demo_clinical_reference import (
    DemoReferenceError,
    minimized_clinical_references,
)
from openbody_ref.demo_composition import compose
from openbody_ref.durable_store import DurableTwinStore
from openbody_ref.host import DEFAULT_FIXTURE
from openbody_ref.validation import canonical_digest
from tests.test_demo_composition import request, specialist_result

import json

EVALUATED_AT = datetime(2026, 9, 2, 13, 0, tzinfo=timezone.utc)

BINDING = {
    "status": "verified",
    "binding_ref": "https://identity.example/bindings/demo-patient-001",
    "issuer": "Demo Identity",
    "verified_at": "2026-09-02T12:00:00Z",
    "revocation_ref": "https://identity.example/bindings/demo-patient-001/status",
    "proof_digest": "sha256:" + "b" * 64,
}


def projection():
    return minimized_clinical_references(compose(request()), subject_binding=BINDING)


def reference_schema_validator() -> Draft202012Validator:
    schema = json.loads(REFERENCE_SCHEMA_PATH.read_text(encoding="utf-8"))
    return Draft202012Validator(schema, format_checker=FormatChecker())


def test_projection_is_structurally_valid_and_minimized():
    projected = projection()
    assert projected["references"], "the registered subsystem must project"
    validator = reference_schema_validator()
    for reference in projected["references"]:
        assert not list(validator.iter_errors(reference))
        # Minimized: a reference names and digests the object, and carries no
        # physiological payload.
        assert "state_vector" not in json.dumps(reference)
        assert reference["projection_class"] == "openbody_reference"


def test_unregistered_coordinates_are_refused_not_dropped():
    projected = projection()
    subsystems = compose(request())["state"]["subsystems"]
    projected_scopes = {reference["scope"][0] for reference in projected["references"]}
    refused_scopes = {refusal["coordinate"] for refusal in projected["refusals"]}

    assert projected_scopes | refused_scopes == {item["coordinate"] for item in subsystems}
    assert projected_scopes.isdisjoint(refused_scopes)
    assert refused_scopes == {
        "ob://human/behavior/activity_tolerance",
        "ob://human/autonomic/recovery_load",
    }
    assert all(refusal["reason_code"] == "unsupported_scope" for refusal in projected["refusals"])


def test_reference_digest_matches_the_state_it_names():
    projected = projection()
    state = compose(request())["state"]
    for reference in projected["references"]:
        assert reference["content_digest"] == canonical_digest(state)
        with pytest.raises(ClinicalReferenceError) as caught:
            validate_clinical_reference(reference, state, evaluated_at=EVALUATED_AT)
        # It resolves and matches; it fails on qualification, not on identity.
        assert caught.value.code not in {
            "content_digest_mismatch",
            "object_kind_mismatch",
            "subject_mismatch",
            "unsupported_contract",
            "unsupported_scope",
            "producer_receipt_mismatch",
        }


def test_demo_reference_is_never_clinically_admissible():
    """Three independent gates refuse the demo, and lifting one is not enough."""

    projected = projection()
    state = compose(request())["state"]
    reference = projected["references"][0]

    def refused(candidate) -> str:
        with pytest.raises(ClinicalReferenceError) as caught:
            validate_clinical_reference(candidate, state, evaluated_at=EVALUATED_AT)
        return caught.value.code

    # 1. The demo asserts no validity window.
    assert refused(reference) == "unknown"

    # 2. Grant validity: applicability was never evaluated.
    forced = copy.deepcopy(reference)
    forced["validity"] = {
        "status": "valid",
        "assessed_at": forced["validity"]["assessed_at"],
        "validity_ref": forced["validity"]["validity_ref"],
        "valid_until": "2099-01-01T00:00:00Z",
    }
    assert refused(forced) == "applicability_unknown"

    # 3. Grant applicability too: uncertainty is still unqualified. The demo
    # cannot be talked into the clinical path.
    forced["applicability"]["status"] = "applicable"
    forced["applicability"]["reasons"] = []
    assert refused(forced) == "uncertainty_insufficient"


def test_tampered_state_breaks_the_reference():
    projected = projection()
    tampered = copy.deepcopy(compose(request())["state"])
    tampered["subsystems"][0]["state_vector"]["support_score"] = 0.99

    with pytest.raises(ClinicalReferenceError) as caught:
        validate_clinical_reference(projected["references"][0], tampered, evaluated_at=EVALUATED_AT)
    assert caught.value.code == "content_digest_mismatch"


def test_unverified_binding_is_carried_not_upgraded():
    unverified = dict(BINDING, status="unverified")
    projected = minimized_clinical_references(compose(request()), subject_binding=unverified)
    reference = projected["references"][0]
    assert reference["subject_binding"]["status"] == "unverified"

    state = compose(request())["state"]
    with pytest.raises(ClinicalReferenceError) as caught:
        validate_clinical_reference(reference, state, evaluated_at=EVALUATED_AT)
    assert caught.value.code == "subject_binding_unverified"


def test_an_abstained_composition_projects_nothing():
    incomplete = request()
    incomplete["specialist_results"] = incomplete["specialist_results"][:2]
    result = compose(incomplete)
    assert result["disposition"] == "abstained"

    with pytest.raises(DemoReferenceError):
        minimized_clinical_references(result, subject_binding=BINDING)


def test_tampered_specialist_output_projects_nothing():
    tampered = request()
    tampered["specialist_results"][0]["output"]["score"] = 0.99
    with pytest.raises(DemoReferenceError):
        minimized_clinical_references(compose(tampered), subject_binding=BINDING)


def test_references_survive_a_store_restart(tmp_path):
    path = tmp_path / "twin-store.json"
    store = DurableTwinStore.open(path, DEFAULT_FIXTURE)
    projected_before = minimized_clinical_references(
        {"disposition": "composed", "state": store.state}, subject_binding=BINDING
    )
    assert projected_before["references"]

    reopened = DurableTwinStore.open(path, DEFAULT_FIXTURE)
    assert reopened.snapshot_commitment == store.snapshot_commitment

    projected_after = minimized_clinical_references(
        {"disposition": "composed", "state": reopened.state}, subject_binding=BINDING
    )
    assert projected_after == projected_before
