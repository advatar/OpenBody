#!/usr/bin/env python3
"""Execute one protocol-0.2 research query from JSON on stdin or a file."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reference" / "python"))

from openbody_ref.longitudinal import QueryError, execute_query  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("request", nargs="?", type=Path, help="JSON request; stdin when omitted")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    try:
        value = json.loads(args.request.read_text() if args.request else sys.stdin.read())
        result = execute_query(value)
    except (OSError, json.JSONDecodeError, QueryError, ValueError) as exc:
        print(f"query rejected: {exc}", file=sys.stderr)
        return 2
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.write_text(rendered)
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
