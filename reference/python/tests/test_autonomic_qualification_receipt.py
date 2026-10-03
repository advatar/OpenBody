import copy
import json
from pathlib import Path

from openbody_ref.autonomic_evidence import validate_autonomic_qualification_receipt

ROOT = Path(__file__).resolve().parents[3]
PATH = ROOT / "research" / "sparc" / "cymba-autonomic-receipt.example.v1.json"

def load():
    return json.loads(PATH.read_text())

def test_compact_sckan_receipt_is_valid():
    assert validate_autonomic_qualification_receipt(load()) == []

def test_receipt_carries_no_patient_or_model_output_payload():
    receipt = load()
    forbidden = {"patient", "subject_id", "raw_data", "model_output", "ecg", "healthkit"}
    assert forbidden.isdisjoint(receipt)

def test_blocked_resource_cannot_be_claim_usable():
    receipt = load()
    receipt["qualification_state"] = "reproduction_blocked"
    receipt["usable_for_claims"] = True
    assert "blocked_marked_usable_for_claims" in validate_autonomic_qualification_receipt(receipt)

def test_revoked_receipt_cannot_be_usable():
    receipt = load()
    receipt["qualification_state"] = "revoked"
    receipt["usable"] = True
    assert "revoked_or_stale_marked_usable" in validate_autonomic_qualification_receipt(receipt)

def test_scope_is_mandatory():
    receipt = load()
    receipt["scope"]["modality"] = ""
    assert "scope_incomplete" in validate_autonomic_qualification_receipt(receipt)

def test_evidence_class_cannot_be_omitted():
    receipt = load()
    receipt.pop("evidence_class")
    assert "unknown_evidence_class" in validate_autonomic_qualification_receipt(receipt)
