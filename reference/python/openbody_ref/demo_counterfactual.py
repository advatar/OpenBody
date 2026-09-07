from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

REQUEST_SCHEMA = "openbody.demo-counterfactual-request.v1"
RESULT_SCHEMA = "openbody.demo-counterfactual-result.v1"
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


class DemoCounterfactualError(ValueError):
    pass


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def simulate(request: dict[str, Any], fixture_path: Path) -> dict[str, Any]:
    fields = {
        "schema", "subject_ref", "generated_at", "body_state_digest",
        "intervention", "horizon_seconds",
    }
    if set(request) != fields or request.get("schema") != REQUEST_SCHEMA:
        raise DemoCounterfactualError(
            f"counterfactual fields must be exactly {sorted(fields)}"
        )
    if not isinstance(request.get("subject_ref"), str) or not request["subject_ref"].startswith("subject:"):
        raise DemoCounterfactualError("subject_ref must be opaque")
    if not isinstance(request.get("generated_at"), str) or not request["generated_at"]:
        raise DemoCounterfactualError("generated_at is required")
    if not isinstance(request.get("body_state_digest"), str) or not DIGEST.fullmatch(request["body_state_digest"]):
        raise DemoCounterfactualError("body_state_digest must be canonical")
    if request.get("horizon_seconds") != 7200:
        raise DemoCounterfactualError("only the qualified 7,200-second horizon is admitted")
    intervention = request.get("intervention")
    if intervention != {
        "kind": "post-meal-walk",
        "duration_minutes": 15,
        "intensity": "low",
    }:
        raise DemoCounterfactualError("intervention is outside the qualified demo boundary")

    scenario = json.loads(fixture_path.read_text())
    applicability = scenario["applicability"]
    if (
        scenario.get("disposition") != "simulated"
        or applicability.get("mode") != "exact_fixture_replay"
        or applicability.get("horizon_seconds") != 7200
        or applicability.get("generalizable") is not False
    ):
        raise DemoCounterfactualError("bundled counterfactual fixture is not qualified")
    fixture_digest = "sha256:" + hashlib.sha256(
        _canonical_bytes(scenario)
    ).hexdigest()
    return {
        "schema": RESULT_SCHEMA,
        "disposition": "simulated",
        "mode": "exact_fixture_replay",
        "subject_ref": request["subject_ref"],
        "generated_at": request["generated_at"],
        "body_state_digest": request["body_state_digest"],
        "horizon_seconds": 7200,
        "intervention": intervention,
        "expected_effects": scenario["expected_effects"],
        "uncertainty": scenario["uncertainty"],
        "model_receipts": scenario["model_receipts"],
        "evidence_boundary": applicability["evidence_boundary"],
        "generalizable": False,
        "fixture_digest": fixture_digest,
    }
