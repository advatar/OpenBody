"""Fail-closed evidence-class rules for research-only autonomic resources."""
from __future__ import annotations

ANATOMICAL_CLASSES = frozenset({"anatomical_variability", "anatomical_connectivity", "anatomical_correspondence"})
FORBIDDEN_ANATOMY_PROMOTIONS = frozenset({
    "electrical_recruitment",
    "physiological_target_engagement",
    "hrv_response",
    "resting_heart_rate_response",
    "respiratory_response",
    "clinical_benefit",
    "consumer_auricular_tavns_applicability",
})

def validate_anatomical_correspondence_receipt(receipt: dict) -> list[str]:
    errors: list[str] = []
    if receipt.get("schema_version") != 1:
        errors.append("unsupported_schema_version")
    if receipt.get("evidence_class") != "anatomical_correspondence":
        errors.append("wrong_evidence_class")
    if receipt.get("status") not in {"contracted_not_reproduced", "reproduced"}:
        errors.append("invalid_status")

    reva = receipt.get("reva") or {}
    sckan = receipt.get("sckan") or {}
    mapping = receipt.get("mapping") or {}
    if not reva.get("source_dataset_doi") or not reva.get("subject") or reva.get("side") not in {"left", "right"}:
        errors.append("reva_identity_incomplete")
    if not sckan.get("version") or not sckan.get("graph_sha256"):
        errors.append("sckan_identity_incomplete")

    allowed = set(receipt.get("allowed_claims") or [])
    forbidden = set(receipt.get("forbidden_claims") or [])
    if allowed - ANATOMICAL_CLASSES:
        errors.append("non_anatomical_claim_allowed")
    if not FORBIDDEN_ANATOMY_PROMOTIONS.issubset(forbidden):
        errors.append("promotion_guard_incomplete")

    if receipt.get("status") == "reproduced":
        required = ("branch_identifier", "sckan_identifier", "query", "canonical_result_sha256")
        if not reva.get("artifact_digest"):
            errors.append("reproduced_without_reva_artifact_digest")
        if any(not mapping.get(key) for key in required):
            errors.append("reproduced_without_complete_mapping")
    return errors

def may_promote(source_class: str, target_class: str) -> bool:
    """No implicit promotion from anatomy into functional/clinical evidence."""
    if source_class in ANATOMICAL_CLASSES and target_class in FORBIDDEN_ANATOMY_PROMOTIONS:
        return False
    return source_class == target_class
