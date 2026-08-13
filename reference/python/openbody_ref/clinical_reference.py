from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from .validation import canonical_digest

ROOT = Path(__file__).resolve().parents[3]
REFERENCE_SCHEMA_PATH = ROOT / "schemas" / "clinical-assertion-reference.schema.json"
OPENBODY_SCHEMA_PATH = ROOT / "schemas" / "openbody.schema.json"
REGISTRY_PATH = ROOT / "registry" / "coordinates.json"
FIXTURE_BUNDLE_PATH = ROOT / "examples" / "clinical-assertion-references.v1.json"


class ClinicalReferenceError(ValueError):
    """A stable, fail-closed clinical-reference admission failure."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class FixtureResult:
    name: str
    expected: str
    actual: str
    expected_error_code: str | None
    actual_error_code: str | None

    @property
    def passed(self) -> bool:
        return self.expected == self.actual and self.expected_error_code == self.actual_error_code


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def merge_patch(target: Any, patch: Any) -> Any:
    """Return RFC 7396 merge-patch output without mutating either input."""

    if not isinstance(patch, dict):
        return copy.deepcopy(patch)
    result = copy.deepcopy(target) if isinstance(target, dict) else {}
    for key, value in patch.items():
        if value is None:
            result.pop(key, None)
        else:
            result[key] = merge_patch(result.get(key), value)
    return result


def expand_fixture_cases(bundle: dict[str, Any]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    base = bundle["base_reference"]
    return [(case, merge_patch(base, case["patch"])) for case in bundle["cases"]]


def _reject(code: str, message: str) -> None:
    raise ClinicalReferenceError(code, message)


def _parse_timestamp(value: str, field: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as error:
        _reject("structural_invalid", f"{field} is not an RFC 3339 timestamp: {error}")


def _validate_structure(reference: dict[str, Any]) -> None:
    schema = _load(REFERENCE_SCHEMA_PATH)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(reference), key=lambda error: list(error.absolute_path))
    if errors:
        error = errors[0]
        location = "/".join(map(str, error.absolute_path)) or "$"
        _reject("structural_invalid", f"{location}: {error.message}")


def _validate_contract(reference: dict[str, Any]) -> None:
    contract = reference["contract"]
    registry = _load(REGISTRY_PATH)
    if (
        contract["openbody_schema_version"] != "0.1"
        or contract["openbody_schema_digest"] != _file_digest(OPENBODY_SCHEMA_PATH)
        or contract["coordinate_registry_version"] != registry["registry_version"]
    ):
        _reject("unsupported_contract", "OpenBody schema or coordinate-registry identity is unsupported")

    registered = {entry["coordinate"] for entry in registry["coordinates"]}
    unknown = sorted(set(reference["scope"]) - registered)
    if unknown:
        _reject("unsupported_scope", f"Unregistered OpenBody scope: {unknown[0]}")


def _validate_subject_binding(reference: dict[str, Any], evaluated_at: datetime) -> None:
    binding = reference["subject_binding"]
    if binding["status"] != "verified":
        _reject(f"subject_binding_{binding['status']}", "Subject binding is not verified")
    if binding.get("expires_at") and _parse_timestamp(binding["expires_at"], "subject_binding.expires_at") < evaluated_at:
        _reject("subject_binding_expired", "Subject-binding receipt has expired")


def _validate_resolved_object(reference: dict[str, Any], resolved_object: dict[str, Any]) -> None:
    if canonical_digest(resolved_object) != reference["content_digest"]:
        _reject("content_digest_mismatch", "Dereferenced OpenBody content does not match its digest")
    if resolved_object.get("kind") != reference["object_kind"]:
        _reject("object_kind_mismatch", "Dereferenced OpenBody object kind does not match the reference")
    if resolved_object.get("schema_version") != reference["contract"]["openbody_schema_version"]:
        _reject("unsupported_contract", "Dereferenced OpenBody object uses a different schema version")
    if "subject" in resolved_object and resolved_object["subject"] != reference["subject"]:
        _reject("subject_mismatch", "Dereferenced OpenBody object belongs to another subject")


def _validate_scope_and_lineage(reference: dict[str, Any], resolved_object: dict[str, Any]) -> None:
    scopes = set(reference["scope"])
    applicability = reference["applicability"]
    if applicability["subject"] != reference["subject"]:
        _reject("subject_mismatch", "Applicability was evaluated for another subject")
    if set(applicability["scopes"]) != scopes:
        _reject("scope_mismatch", "Applicability scopes must exactly match projected scopes")

    evidence = reference["evidence_lineage"]
    if any(item["subject"] != reference["subject"] for item in evidence):
        _reject("evidence_subject_mismatch", "Evidence lineage belongs to another subject")
    if any(not set(item["scopes"]).issubset(scopes) for item in evidence):
        _reject("evidence_scope_mismatch", "Evidence lineage exceeds projected scopes")

    producer = reference["producer"]
    if any(producer["model_id"] not in item["model_refs"] for item in evidence):
        _reject("evidence_model_mismatch", "Evidence lineage does not name the producing model")

    receipts = resolved_object.get("model_receipts", [])
    if receipts and not any(
        receipt.get("model_id") == producer["model_id"]
        and receipt.get("model_version") == producer["model_version"]
        and receipt.get("execution_id") == producer["execution_id"]
        for receipt in receipts
    ):
        _reject("producer_receipt_mismatch", "Producer receipt is not present in the dereferenced object")


def _validate_current_state(reference: dict[str, Any], evaluated_at: datetime) -> None:
    validity = reference["validity"]
    status = validity["status"]
    if status != "valid":
        _reject(status, f"Clinical reference validity is {status}")
    if _parse_timestamp(validity["valid_until"], "validity.valid_until") < evaluated_at:
        _reject("stale", "Clinical reference validity window has elapsed")

    abstention = reference["abstention"]
    if abstention["status"] == "abstained":
        _reject("abstained", "OpenBody explicitly abstained from producing an assertion")

    applicability = reference["applicability"]
    applicability_status = applicability["status"]
    if applicability_status != "applicable":
        code = "out_of_distribution" if applicability_status == "out_of_distribution" else f"applicability_{applicability_status}"
        _reject(code, f"Clinical reference applicability is {applicability_status}")

    uncertainty = reference["uncertainty"]
    if uncertainty["status"] != "known":
        _reject(f"uncertainty_{uncertainty['status']}", "Clinical reference uncertainty is not known")
    if uncertainty["out_of_distribution"]:
        _reject("out_of_distribution", "OpenBody marked the assertion out of distribution")


def validate_clinical_reference(
    reference: dict[str, Any],
    resolved_object: dict[str, Any],
    *,
    evaluated_at: datetime,
) -> None:
    """Validate a reference for clinical admission or raise a stable coded error."""

    if reference.get("projection_class") != "openbody_reference":
        _reject("not_openbody_reference", "Source observations cannot be admitted as derived assertions")
    _validate_structure(reference)
    _validate_contract(reference)
    _validate_subject_binding(reference, evaluated_at)
    _validate_resolved_object(reference, resolved_object)
    _validate_scope_and_lineage(reference, resolved_object)
    _validate_current_state(reference, evaluated_at)


def validate_fixture_bundle(root: Path = ROOT) -> list[FixtureResult]:
    bundle = _load(root / FIXTURE_BUNDLE_PATH.relative_to(ROOT))
    evaluated_at = _parse_timestamp(bundle["evaluated_at"], "evaluated_at")
    results: list[FixtureResult] = []
    for case, reference in expand_fixture_cases(bundle):
        resolved_object = _load(root / case["resolved_object"])
        actual = "accepted"
        actual_error_code = None
        try:
            validate_clinical_reference(reference, resolved_object, evaluated_at=evaluated_at)
        except ClinicalReferenceError as error:
            actual = "rejected"
            actual_error_code = error.code
        results.append(
            FixtureResult(
                name=case["name"],
                expected=case["expected"],
                actual=actual,
                expected_error_code=case.get("error_code"),
                actual_error_code=actual_error_code,
            )
        )
    return results
