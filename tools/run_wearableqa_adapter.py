#!/usr/bin/env python3
"""Run the reviewed deterministic adapter against structured WearableQA data."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reference" / "python"))

from openbody_ref.longitudinal import QueryError  # noqa: E402
from openbody_ref.wearableqa import ADAPTER_VERSION, answer_dataset  # noqa: E402


def _code_digest() -> str:
    hasher = hashlib.sha256()
    for path in (
        ROOT / "reference" / "python" / "openbody_ref" / "longitudinal.py",
        ROOT / "reference" / "python" / "openbody_ref" / "wearableqa.py",
        Path(__file__).resolve(),
    ):
        hasher.update(path.relative_to(ROOT).as_posix().encode())
        hasher.update(b"\0")
        hasher.update(path.read_bytes())
        hasher.update(b"\0")
    return "sha256:" + hasher.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, required=True, help="WearableQA_raw.json")
    parser.add_argument("--out", type=Path, required=True, help="prediction JSONL")
    parser.add_argument("--manifest-out", type=Path, required=True)
    args = parser.parse_args()
    try:
        raw = json.loads(args.raw.read_text())
        predictions = answer_dataset(raw)
        args.out.write_text("".join(json.dumps(value, sort_keys=True, allow_nan=False) + "\n"
                                    for value in predictions))
        code_digest = _code_digest()
        args.manifest_out.write_text(json.dumps({
            "system": "OpenBody deterministic longitudinal query layer",
            "revision": code_digest,
            "code_digest": code_digest,
            "prompt_tool_policy": "structured signal_summary allowlist; no generative model",
            "seed": None,
            "adapter_version": ADAPTER_VERSION,
            "raw_dataset_digest": "sha256:" + hashlib.sha256(args.raw.read_bytes()).hexdigest(),
        }, indent=2, sort_keys=True, allow_nan=False) + "\n")
    except (OSError, json.JSONDecodeError, QueryError, ValueError) as exc:
        print(f"adapter rejected input: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
