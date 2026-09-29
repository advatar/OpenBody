#!/usr/bin/env python3
"""Check the whole-person state conformance corpus (issue #30).

Usage:
    python tools/check_whole_person_state.py            # evaluate golden + vectors + consumer mapping
    python tools/check_whole_person_state.py --write-golden
        # regenerate fixtures/whole-person-state/v1/snapshot.golden.json;
        # review the diff: a changed golden snapshot is a contract change.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reference" / "python"))

from openbody_ref.whole_person import evaluate_conformance_corpus, write_golden_snapshot
from openbody_ref.whole_person_mapping import evaluate_consumer_mapping


def main(argv: list[str]) -> int:
    if "--write-golden" in argv:
        snapshot = write_golden_snapshot()
        print(f"wrote snapshot.golden.json {snapshot['snapshot_digest']}")
    failed = False
    results = evaluate_conformance_corpus()
    for result in results:
        if result.passed:
            print(f"PASS whole-person-state vector {result.name}: {result.detail}")
        else:
            failed = True
            print(f"FAIL whole-person-state vector {result.name}: {result.detail}")
            for failure in result.failures:
                print(f"  {failure}")
    print(f"{sum(r.passed for r in results)}/{len(results)} whole-person-state vectors passed")
    mapping = evaluate_consumer_mapping()
    for result in mapping:
        if result.passed:
            print(f"PASS whole-person-state {result.name}: {result.detail}")
        else:
            failed = True
            print(f"FAIL whole-person-state {result.name}: {result.detail}")
            for failure in result.failures:
                print(f"  {failure}")
    print(f"{sum(r.passed for r in mapping)}/{len(mapping)} whole-person-state consumer-mapping checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
