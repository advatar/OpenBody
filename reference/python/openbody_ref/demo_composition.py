from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from .validation import semantic_validate, validate_definition


REQUEST_SCHEMA = "openbody.demo-composition-request.v1"
RESULT_SCHEMA = "openbody.demo-composition-result.v1"
SPECIALIST_RESULT_SCHEMA = "invivo.demo-specialist-execution-result.v1"

EXPECTED_SPECIALISTS = {
    "glucose-logistic.v1": (
        "postprandial-risk-estimation",
        "ob://human/metabolic/glucose_regulation",
    ),
    "careplan-adherence.v1": (
        "careplan-compatibility",
        "ob://human/behavior/activity_tolerance",
    ),
    "recovery-gate.v1": (
        "activity-intensity-bounding",
        "ob://human/autonomic/recovery_load",
    ),
}
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


class DemoCompositionError(ValueError):
    pass


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _abstention(composition_id: str, input_digest: str, reasons: list[str]) -> dict[str, Any]:
    return {
        "schema": RESULT_SCHEMA,
        "composition_id": composition_id,
        "disposition": "abstained",
        "input_digest": input_digest,
        "state": None,
        "abstention": {
            "reason_code": "insufficient_validation",
            "reasons": reasons,
            "safe_next_step": "Do not produce a recommendation; reacquire all three valid specialist receipts.",
        },
    }


def _validate_request(request: dict[str, Any]) -> None:
    expected = {"schema", "composition_id", "subject_ref", "generated_at", "specialist_results"}
    if set(request) != expected:
        raise DemoCompositionError(f"request fields must be exactly {sorted(expected)}")
    if request["schema"] != REQUEST_SCHEMA:
        raise DemoCompositionError("unsupported request schema")
    for field in ("composition_id", "subject_ref", "generated_at"):
        if not isinstance(request[field], str) or not request[field].strip():
            raise DemoCompositionError(f"{field} must be a non-empty string")
    if not request["subject_ref"].startswith("subject:"):
        raise DemoCompositionError("subject_ref must be an opaque subject reference")
    if not isinstance(request["specialist_results"], list):
        raise DemoCompositionError("specialist_results must be an array")


def _validated_subsystem(result: dict[str, Any], subject: str) -> dict[str, Any]:
    expected_result = {
        "schema",
        "execution_id",
        "model_id",
        "subject_ref",
        "status",
        "maturity",
        "output",
        "model_receipt",
        "prohibited_uses",
    }
    if set(result) != expected_result:
        raise DemoCompositionError("specialist result shape is not admitted")
    model_id = result["model_id"]
    if model_id not in EXPECTED_SPECIALISTS:
        raise DemoCompositionError("specialist identity is not admitted")
    if (
        result["schema"] != SPECIALIST_RESULT_SCHEMA
        or result["status"] != "completed"
        or result["maturity"] != "demo_reference"
        or result["subject_ref"] != subject
    ):
        raise DemoCompositionError(f"{model_id} result boundary is invalid")

    capability, scope = EXPECTED_SPECIALISTS[model_id]
    output = result["output"]
    if set(output) != {"score", "interpretation", "scope", "capability", "uncertainty"}:
        raise DemoCompositionError(f"{model_id} output shape is invalid")
    uncertainty = output["uncertainty"]
    if set(uncertainty) != {"class", "confidence", "out_of_distribution"}:
        raise DemoCompositionError(f"{model_id} uncertainty shape is invalid")
    score = output["score"]
    confidence = uncertainty["confidence"]
    if (
        isinstance(score, bool)
        or not isinstance(score, (int, float))
        or not 0 <= score <= 1
        or isinstance(confidence, bool)
        or not isinstance(confidence, (int, float))
        or not 0 <= confidence <= 1
        or output["scope"] != scope
        or output["capability"] != capability
    ):
        raise DemoCompositionError(f"{model_id} output boundary is invalid")

    receipt = result["model_receipt"]
    receipt_fields = {
        "model_id",
        "model_version",
        "family",
        "execution_id",
        "executed_at",
        "input_digest",
        "output_digest",
        "environment_digest",
        "validation_ref",
    }
    if (
        not isinstance(receipt, dict)
        or set(receipt) != receipt_fields
        or receipt["model_id"] != model_id
        or receipt["execution_id"] != result["execution_id"]
        or receipt["family"] != "statistical"
        or receipt["output_digest"] != _digest(output)
        or not all(
            isinstance(receipt[field], str) and DIGEST.fullmatch(receipt[field])
            for field in ("input_digest", "output_digest", "environment_digest")
        )
    ):
        raise DemoCompositionError(f"{model_id} receipt is missing, substituted, or tampered")

    subsystem = {
        "coordinate": scope,
        "organizational_scale": "subsystem",
        "state_vector": {
            "support_score": float(score),
            "confidence": float(confidence),
        },
        "latent_state": {},
        "trend": "indeterminate",
        "uncertainty": {
            "epistemic": round(1.0 - float(confidence), 8),
            "aleatoric": None,
            "coverage": None,
            "interval": None,
            "calibration_ref": None,
            "out_of_distribution": uncertainty["out_of_distribution"],
            "reasons": ["Synthetic demo-reference specialist; not clinically validated"],
        },
        "evidence": [],
        "model_receipt": receipt,
    }
    validate_definition("BodySubsystemState", subsystem)
    return subsystem


def compose(request: dict[str, Any]) -> dict[str, Any]:
    _validate_request(request)
    input_digest = _digest(request["specialist_results"])
    composition_id = request["composition_id"]
    results = request["specialist_results"]
    if len(results) != len(EXPECTED_SPECIALISTS):
        return _abstention(
            composition_id,
            input_digest,
            ["All three specialized model results are required before body-state composition."],
        )

    try:
        subsystems = [_validated_subsystem(result, request["subject_ref"]) for result in results]
        identities = {result["model_id"] for result in results}
        if identities != set(EXPECTED_SPECIALISTS):
            raise DemoCompositionError("specialist result set is incomplete or duplicated")
    except (DemoCompositionError, KeyError, TypeError) as error:
        return _abstention(composition_id, input_digest, [str(error)])

    receipts = [result["model_receipt"] for result in results]
    state = {
        "schema_version": "0.1",
        "kind": "BodyState",
        "id": f"state:{composition_id}",
        "subject": request["subject_ref"],
        "generated_at": request["generated_at"],
        "state_time": request["generated_at"],
        "valid_until": None,
        "subsystems": sorted(subsystems, key=lambda item: item["coordinate"]),
        "couplings": [],
        "evidence": [],
        "uncertainty": {
            "epistemic": max(item["uncertainty"]["epistemic"] for item in subsystems),
            "aleatoric": None,
            "coverage": None,
            "interval": None,
            "calibration_ref": None,
            "out_of_distribution": any(
                item["uncertainty"]["out_of_distribution"] for item in subsystems
            ),
            "reasons": ["Composed from three small synthetic demo-reference models."],
        },
        "model_receipts": sorted(receipts, key=lambda item: item["model_id"]),
    }
    semantic_validate(state)
    return {
        "schema": RESULT_SCHEMA,
        "composition_id": composition_id,
        "disposition": "composed",
        "input_digest": input_digest,
        "state": state,
        "abstention": None,
    }
