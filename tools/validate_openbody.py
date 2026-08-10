#!/usr/bin/env python3
import json
import sys
from datetime import datetime
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schemas" / "openbody.schema.json"
REGISTRY = ROOT / "registry" / "coordinates.json"


def load(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def collect_coordinates(value):
    found = []
    if isinstance(value, dict):
        for k, v in value.items():
            if k in {"coordinate", "scope", "source", "target"} and isinstance(v, str) and v.startswith("ob://"):
                found.append(v)
            found.extend(collect_coordinates(v))
    elif isinstance(value, list):
        for item in value:
            found.extend(collect_coordinates(item))
    return found


def invariant_errors(doc):
    errors = []
    if doc.get("kind") == "CounterfactualScenario":
        disposition = doc.get("disposition")
        receipts = doc.get("model_receipts", [])
        effects = doc.get("expected_effects", [])
        counterfactual = doc.get("counterfactual")
        abstention = doc.get("abstention")
        if disposition == "simulated":
            if not receipts:
                errors.append("simulated scenario MUST carry at least one model receipt")
            if counterfactual is None:
                errors.append("simulated scenario MUST carry a counterfactual trajectory")
            if abstention is not None:
                errors.append("simulated scenario MUST NOT carry abstention")
        else:
            if effects:
                errors.append("non-simulated scenario MUST NOT invent expected effects")
            if counterfactual is not None:
                errors.append("non-simulated scenario MUST NOT carry a counterfactual trajectory")
            if receipts:
                errors.append("non-simulated scenario MUST NOT claim a producing model receipt")
            if disposition == "abstained" and abstention is None:
                errors.append("abstained scenario MUST carry Abstention")
    if doc.get("kind") == "ObservedOutcome":
        started_at = datetime.fromisoformat(doc["started_at"].replace("Z", "+00:00"))
        ended_at = datetime.fromisoformat(doc["ended_at"].replace("Z", "+00:00"))
        if ended_at < started_at:
            errors.append("ObservedOutcome ended_at MUST be >= started_at")
    return errors


def main(paths):
    schema = load(SCHEMA)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    registry = load(REGISTRY)
    known_coordinates = {x["coordinate"] for x in registry["coordinates"]}
    failed = False

    for raw in paths:
        path = Path(raw)
        doc = load(path)
        schema_errors = sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path))
        custom_errors = invariant_errors(doc)
        unknown = sorted({c for c in collect_coordinates(doc) if c not in known_coordinates})
        if schema_errors or custom_errors:
            failed = True
            print(f"FAIL {path}")
            for err in schema_errors:
                loc = "/".join(map(str, err.absolute_path)) or "$"
                print(f"  schema {loc}: {err.message}")
            for err in custom_errors:
                print(f"  invariant: {err}")
        else:
            print(f"PASS {path}")
        for coordinate in unknown:
            print(f"  WARN unregistered coordinate: {coordinate}")

    return 1 if failed else 0


if __name__ == "__main__":
    args = sys.argv[1:] or [str(p) for p in sorted((ROOT / "examples").glob("*.json"))]
    raise SystemExit(main(args))
