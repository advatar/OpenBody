#!/usr/bin/env python3
"""Check the shared healthcare trace (fixtures/healthcare-trace/v1/trace.json).

Usage:
    python tools/check_healthcare_trace.py

Rebuilding the fixture is tools/build_healthcare_trace.py (two steps, with the
ProvidEHR producer in between). Replaying repositories pin the file by SHA-256.
"""

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reference" / "python"))

from openbody_ref.healthcare_trace import TRACE_PATH, evaluate_trace  # noqa: E402


def main() -> int:
    failed = False
    results = evaluate_trace()
    for result in results:
        if result.passed:
            print(f"PASS {result.name}: {result.detail}")
        else:
            failed = True
            print(f"FAIL {result.name}: {result.detail}")
            for failure in result.failures:
                print(f"  {failure}")
    print(f"{sum(r.passed for r in results)}/{len(results)} healthcare-trace checks passed")
    print(f"trace sha256 {hashlib.sha256(TRACE_PATH.read_bytes()).hexdigest()}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
