import pytest

from openbody_ref.imaging_representation import (
    ImagingRepresentationError, compatible_for_reuse, representation_identity, validate_imaging_representation,
)


def fixture(model="a", domain="in_domain"):
    h=lambda c: "sha256:"+c*64
    return {
        "profile":"openbody.imaging-representation.v1","id":f"repr:{model}","subject":"subject:synthetic",
        "source":{"study_ref":"dicom:study:1","series_refs":["dicom:series:1"]},
        "modality":"CT","anatomy":["chest"],"acquired_at":"2026-01-01T00:00:00Z",
        "representation_model":{"model_id":"percival-like","model_version":model,"model_commitment":h(model)},
        "preprocessing":{"pipeline_id":"ct-prep","pipeline_version":"1","commitment":h("b")},
        "payload":{"kind":"embedding","dimensions":[1024],"content_digest":h("c"),"object_ref":"object:latent:1"},
        "execution_evidence":"receipt:1","evidence_maturity":"exploratory_human",
        "domain_applicability":{"status":domain,"population_refs":["population:synthetic"]},
        "derived_at":"2026-01-02T00:00:00Z","provenance":["source:study:1"],
        "privacy":{"export_policy":"local_only"},
    }


def test_valid_representation_is_model_and_pipeline_bound():
    v=fixture()
    validate_imaging_representation(v)
    assert representation_identity(v)[0]=="dicom:study:1"


def test_two_model_versions_are_distinct_immutable_identities():
    assert representation_identity(fixture("a")) != representation_identity(fixture("d"))


def test_out_of_domain_representation_is_not_reusable():
    v=fixture(domain="out_of_domain")
    assert not compatible_for_reuse(v,allowed_model_commitments={v["representation_model"]["model_commitment"]})


def test_reuse_requires_exact_qualified_model_commitment():
    v=fixture()
    assert not compatible_for_reuse(v,allowed_model_commitments={"sha256:"+"f"*64})
    assert compatible_for_reuse(v,allowed_model_commitments={v["representation_model"]["model_commitment"]})


def test_inline_embedding_is_rejected():
    v=fixture()
    v["payload"]["values"]=[0.1,0.2]
    with pytest.raises(ImagingRepresentationError):
        validate_imaging_representation(v)
