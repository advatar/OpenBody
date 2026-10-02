import copy
import json
from pathlib import Path

from openbody_ref.autonomic_evidence import may_promote, validate_anatomical_correspondence_receipt

ROOT = Path(__file__).resolve().parents[3]
RECEIPT = ROOT / "research" / "sparc" / "reva-sckan-f007-right.v1.json"

def load():
    return json.loads(RECEIPT.read_text())

def test_preflight_contract_is_valid_but_not_reproduced():
    receipt = load()
    assert receipt["status"] == "contracted_not_reproduced"
    assert validate_anatomical_correspondence_receipt(receipt) == []

def test_cannot_mark_reproduced_without_artifact_and_mapping():
    receipt = load()
    receipt["status"] = "reproduced"
    errors = validate_anatomical_correspondence_receipt(receipt)
    assert "reproduced_without_reva_artifact_digest" in errors
    assert "reproduced_without_complete_mapping" in errors

def test_anatomy_cannot_promote_to_physiology_or_benefit():
    for target in load()["forbidden_claims"]:
        assert not may_promote("anatomical_correspondence", target)

def test_non_anatomical_allowed_claim_fails_closed():
    receipt = copy.deepcopy(load())
    receipt["allowed_claims"].append("clinical_benefit")
    assert "non_anatomical_claim_allowed" in validate_anatomical_correspondence_receipt(receipt)

def test_selected_subject_and_side_are_explicit():
    reva = load()["reva"]
    assert reva["source_dataset_doi"] == "10.26275/DP8R-BB7W"
    assert reva["subject"] == "f007"
    assert reva["side"] == "right"
