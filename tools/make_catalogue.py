#!/usr/bin/env python3
"""Turn subject-bound `BodyModel` descriptors into a publishable catalogue.

A descriptor names the twin it applies to, because OpenBody applicability is
per-subject and a host substantiates receipts against it. That makes descriptors
unpublishable verbatim: `applicability.subject` identifies a person.

A catalogue answers a different question — which models exist and what are they
competent for — which needs no subject at all. This tool performs that transform
explicitly rather than leaving it to a hand edit, and refuses when the assumption
behind it does not hold.

The assumption is that `applicability.subject` is the *only* subject-bearing field
in a `BodyModel`. That is checked, not trusted: if any other value carries the
source subject, the descriptor is rejected rather than published with a leak the
transform did not know about.

Usage:
    python tools/make_catalogue.py --out DIR DESCRIPTOR [DESCRIPTOR ...]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reference" / "python"))

from openbody_ref.host import CATALOGUE_SUBJECT  # noqa: E402
from openbody_ref.validation import semantic_validate  # noqa: E402


def _values(value):
    """Every scalar in a nested structure, with the path that reached it."""
    if isinstance(value, dict):
        for key, nested in value.items():
            for path, scalar in _values(nested):
                yield (f"{key}.{path}" if path else key), scalar
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            for path, scalar in _values(nested):
                yield (f"[{index}].{path}" if path else f"[{index}]"), scalar
    else:
        yield "", value


def to_catalogue(descriptor: dict) -> dict:
    """Rewrite one descriptor into catalogue form, or refuse."""
    if descriptor.get("kind") != "BodyModel":
        raise ValueError(f"{descriptor.get('id')!r} is not a BodyModel descriptor")

    source_subject = descriptor.get("applicability", {}).get("subject")
    if not source_subject:
        raise ValueError(f"{descriptor.get('id')!r} declares no applicability.subject")
    if source_subject == CATALOGUE_SUBJECT:
        return json.loads(json.dumps(descriptor))

    catalogue = json.loads(json.dumps(descriptor))
    catalogue["applicability"]["subject"] = CATALOGUE_SUBJECT

    # The transform is only correct if applicability.subject was the sole carrier.
    # Anything else still holding the source subject would be published as a leak.
    leaks = [
        path
        for path, scalar in _values(catalogue)
        if isinstance(scalar, str) and source_subject in scalar
    ]
    if leaks:
        raise ValueError(
            f"{descriptor['id']!r} carries the source subject outside "
            f"applicability.subject at: {', '.join(sorted(leaks))}"
        )
    return catalogue


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("descriptors", nargs="+", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)

    args.out.mkdir(parents=True, exist_ok=True)
    written = 0
    for path in sorted(args.descriptors):
        descriptor = json.loads(path.read_text())
        catalogue = to_catalogue(descriptor)
        # A catalogue entry must still be a valid BodyModel.
        semantic_validate(catalogue)
        (args.out / path.name).write_text(json.dumps(catalogue, indent=2, sort_keys=True) + "\n")
        written += 1
        print(f"catalogued {path.name}")
    print(f"{written} descriptors written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
