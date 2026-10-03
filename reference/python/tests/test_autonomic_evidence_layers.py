import json
from pathlib import Path

from openbody_ref.autonomic_evidence import validate_evidence_claim

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = json.loads((ROOT / "research" / "sparc" / "autonomic-evidence-conformance.v1.json").read_text())["fixtures"]

def by_id(value):
    return next(item for item in FIXTURES if item["id"] == value)

def test_same_class_same_scope_is_admissible():
    record = by_id("reva-sckan-anatomy")
    assert validate_evidence_claim(record, "anatomical_connectivity",
                                   target_species="human", target_modality="anatomy_only") == []

def test_anatomy_cannot_become_recruitment_or_benefit():
    record = by_id("reva-sckan-anatomy")
    assert "evidence_class_promotion" in validate_evidence_claim(record, "simulated_recruitment")
    assert "evidence_class_promotion" in validate_evidence_claim(record, "clinical_benefit")

def test_simulation_cannot_become_measured_target_engagement():
    record = by_id("ascent-simulated-recruitment")
    assert "evidence_class_promotion" in validate_evidence_claim(record, "measured_target_engagement")

def test_rat_target_engagement_cannot_become_human_evidence():
    record = by_id("rat-implanted-vns-adenosine")
    errors = validate_evidence_claim(record, "measured_target_engagement", target_species="human")
    assert "species_transfer" in errors

def test_implanted_vns_cannot_silently_become_auricular_tavns():
    record = by_id("rat-implanted-vns-adenosine")
    errors = validate_evidence_claim(record, "measured_target_engagement",
                                     target_species="rat", target_modality="auricular_tavns")
    assert "modality_transfer" in errors

def test_clinical_benefit_does_not_transfer_modalities():
    record = by_id("human-clinical-benefit-placeholder")
    errors = validate_evidence_claim(record, "clinical_benefit",
                                     target_species="human", target_modality="auricular_tavns")
    assert "modality_transfer" in errors

def test_missing_provenance_fails_closed():
    record = dict(by_id("reva-sckan-anatomy"))
    record["provenance"] = ""
    assert "missing_provenance" in validate_evidence_claim(record, "anatomical_connectivity")
