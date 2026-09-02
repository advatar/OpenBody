from __future__ import annotations

import copy

from openbody_ref.demo_composition import (
    EXPECTED_SPECIALISTS,
    REQUEST_SCHEMA,
    _digest,
    compose,
)
from openbody_ref.validation import semantic_validate


def specialist_result(model_id: str) -> dict:
    capability, scope = EXPECTED_SPECIALISTS[model_id]
    output = {
        "score": 0.78,
        "interpretation": "supports",
        "scope": scope,
        "capability": capability,
        "uncertainty": {
            "class": "unqualified_demo_reference",
            "confidence": 0.56,
            "out_of_distribution": False,
        },
    }
    return {
        "schema": "invivo.demo-specialist-execution-result.v1",
        "execution_id": f"exec:{model_id}",
        "model_id": model_id,
        "subject_ref": "subject:demo-patient-001",
        "status": "completed",
        "maturity": "demo_reference",
        "output": output,
        "model_receipt": {
            "model_id": model_id,
            "model_version": "1.0.0-demo",
            "family": "statistical",
            "execution_id": f"exec:{model_id}",
            "executed_at": "2026-09-02T12:35:00Z",
            "input_digest": "sha256:" + "a" * 64,
            "output_digest": _digest(output),
            "environment_digest": "sha256:" + "0" * 64,
            "validation_ref": f"validation:synthetic:{model_id}",
        },
        "prohibited_uses": ["clinical diagnosis", "autonomous treatment"],
    }


def request() -> dict:
    return {
        "schema": REQUEST_SCHEMA,
        "composition_id": "episode1:001",
        "subject_ref": "subject:demo-patient-001",
        "generated_at": "2026-09-02T12:35:00Z",
        "specialist_results": [
            specialist_result(model_id) for model_id in EXPECTED_SPECIALISTS
        ],
    }


def test_three_receipts_compose_a_real_openbody_state() -> None:
    result = compose(request())

    assert result["disposition"] == "composed"
    assert len(result["state"]["subsystems"]) == 3
    assert len(result["state"]["model_receipts"]) == 3
    semantic_validate(result["state"])


def test_missing_recovery_receipt_abstains_without_state() -> None:
    value = request()
    value["specialist_results"] = [
        result
        for result in value["specialist_results"]
        if result["model_id"] != "recovery-gate.v1"
    ]

    result = compose(value)

    assert result["disposition"] == "abstained"
    assert result["state"] is None


def test_tampered_specialist_output_abstains() -> None:
    value = copy.deepcopy(request())
    value["specialist_results"][0]["output"]["score"] = 0.01

    result = compose(value)

    assert result["disposition"] == "abstained"
    assert "tampered" in result["abstention"]["reasons"][0]
