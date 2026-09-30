from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[3]
SCHEMA = json.loads((ROOT / "schemas" / "imaging-representation.v1.schema.json").read_text())
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())


class ImagingRepresentationError(ValueError):
    pass


def validate_imaging_representation(value: Any) -> None:
    errors = sorted(VALIDATOR.iter_errors(value), key=lambda e: list(e.absolute_path))
    if errors:
        raise ImagingRepresentationError(errors[0].message)
    # The representation payload is a reference+digest, never an inline latent
    # vector. This keeps whole-person state bounded and preserves immutable blob
    # identity independently of graph projection.
    if any(key in value["payload"] for key in ("values", "bytes", "base64", "data")):
        raise ImagingRepresentationError("representation payload must not inline latent data")


def representation_identity(value: dict[str, Any]) -> tuple[str, str, str]:
    validate_imaging_representation(value)
    return (
        value["source"]["study_ref"],
        value["representation_model"]["model_commitment"],
        value["preprocessing"]["commitment"],
    )


def compatible_for_reuse(value: dict[str, Any], *, allowed_model_commitments: set[str]) -> bool:
    validate_imaging_representation(value)
    if value["domain_applicability"]["status"] != "in_domain":
        return False
    return value["representation_model"]["model_commitment"] in allowed_model_commitments
