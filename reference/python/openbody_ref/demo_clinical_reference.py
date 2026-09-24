"""Minimized clinical-assertion references for the demo composition.

A composed demo `BodyState` is not clinical evidence. What a clinical receiver
may be handed is a *reference*: digests, scope, provenance and an explicit
qualification state, with no physiological values in it. This module projects
one reference to the composed `BodyState` per registered coordinate, and
refuses to project anything it cannot name honestly.

Two properties matter more than convenience here:

* a subsystem whose coordinate is not in the OpenBody registry cannot be
  projected at all, and the refusal is returned rather than dropped;
* the synthetic demo has no calibrated uncertainty and no evaluated
  applicability, so every reference it emits declares that. Such a reference is
  well-formed and still fails `validate_clinical_reference`, which is the
  intended outcome: the demo cannot be admitted as clinical evidence.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .clinical_reference import OPENBODY_SCHEMA_PATH, REGISTRY_PATH, _file_digest
from .validation import canonical_digest

REFERENCE_SCHEMA = "openbody.clinical-assertion-reference/1.0"
CANONICAL_REF_BASE = "https://demo.openbody.dev/objects"
RECEIPT_REF_BASE = "https://demo.openbody.dev/receipts"


class DemoReferenceError(ValueError):
    """The composition cannot be projected as a clinical reference at all."""


def _registered_coordinates() -> set[str]:
    registry = json.loads(Path(REGISTRY_PATH).read_text(encoding="utf-8"))
    return {entry["coordinate"] for entry in registry["coordinates"]}


def _registry_version() -> str:
    return json.loads(Path(REGISTRY_PATH).read_text(encoding="utf-8"))["registry_version"]


def _contract() -> dict[str, Any]:
    return {
        "openbody_schema_version": "0.1",
        "openbody_schema_digest": _file_digest(OPENBODY_SCHEMA_PATH),
        "coordinate_registry_version": _registry_version(),
    }


def _reference(state: dict[str, Any], subsystem: dict[str, Any], binding: dict[str, Any]) -> dict[str, Any]:
    receipt = subsystem["model_receipt"]
    coordinate = subsystem["coordinate"]
    subject = state["subject"]
    model_id = receipt["model_id"]
    return {
        "schema_version": REFERENCE_SCHEMA,
        "projection_class": "openbody_reference",
        "reference_id": f"clinical-ref:{state['id']}:{model_id}",
        # The reference names the composed state, narrowed to the one
        # coordinate this producer is responsible for.
        "object_kind": "BodyState",
        "canonical_ref": f"{CANONICAL_REF_BASE}/{state['id']}",
        "content_digest": canonical_digest(state),
        "subject": subject,
        "subject_binding": binding,
        "scope": [coordinate],
        "contract": _contract(),
        "producer": {
            "model_id": model_id,
            "model_version": receipt["model_version"],
            "family": receipt["family"],
            "execution_id": receipt["execution_id"],
            "executed_at": receipt["executed_at"],
            "input_digest": receipt["input_digest"],
            "output_digest": receipt["output_digest"],
            "receipt_ref": f"{RECEIPT_REF_BASE}/{receipt['execution_id']}",
        },
        "evidence_lineage": [
            {
                "canonical_ref": f"local://demo/specialist/{model_id}/{receipt['execution_id']}",
                "content_digest": receipt["output_digest"],
                "model_refs": [model_id],
                "observed_at": receipt["executed_at"],
                "scopes": [coordinate],
                "subject": subject,
            }
        ],
        "epistemic_class": "statistical_association",
        # The demo evaluates no applicability and calibrates no uncertainty.
        # Saying so is what keeps it out of the clinical path.
        "applicability": {
            "status": "unknown",
            "subject": subject,
            "scopes": [coordinate],
            "evaluated_at": state["generated_at"],
            "reasons": ["Demo-reference composition evaluates no applicability envelope."],
        },
        "uncertainty": {
            "status": "insufficient",
            "reasons": [
                "Synthetic demo specialist reports confidence only; aleatoric, coverage and calibration are unestablished."
            ],
        },
        "validity": {
            "status": "unknown",
            "assessed_at": state["generated_at"],
            "validity_ref": f"{CANONICAL_REF_BASE}/{state['id']}/validity",
        },
        "abstention": {"status": "not_abstained"},
        "summary": (
            f"Synthetic demo-reference support score for {coordinate}. "
            "Not clinically validated and not admissible as clinical evidence."
        ),
    }


def minimized_clinical_references(
    result: dict[str, Any], *, subject_binding: dict[str, Any]
) -> dict[str, Any]:
    """Project a composition result as minimized references plus explicit refusals.

    The caller supplies `subject_binding`; OpenBody does not verify identity and
    never invents a binding.
    """

    if result.get("disposition") == "abstained":
        raise DemoReferenceError("An abstained composition has no object to project")
    state = result.get("state")
    if not isinstance(state, dict) or state.get("kind") != "BodyState":
        raise DemoReferenceError("Only a composed BodyState can be projected")

    registered = _registered_coordinates()
    references: list[dict[str, Any]] = []
    refusals: list[dict[str, Any]] = []
    for subsystem in state["subsystems"]:
        coordinate = subsystem["coordinate"]
        if coordinate not in registered:
            refusals.append(
                {
                    "coordinate": coordinate,
                    "reason_code": "unsupported_scope",
                    "reason": "Coordinate is not in the OpenBody registry and cannot be projected.",
                }
            )
            continue
        references.append(_reference(state, subsystem, subject_binding))
    return {"references": references, "refusals": refusals}
