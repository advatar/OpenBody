#!/usr/bin/env python3
"""Score WearableQA predictions with explicit abstention and coverage reporting.

The scorer never invokes a model and never treats multiple-choice accuracy as
clinical validity. It consumes the official rendered JSONL and a prediction JSONL:

    {"id": "...", "answer": "A"}
    {"id": "...", "abstain": true, "reason": "insufficient context"}

Results are stratified by the two benchmark axes that matter most to OpenBody:
data versus health reasoning and single- versus cross-signal reasoning.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


LETTERS = frozenset("ABCDEFGHIJ")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    values = []
    with path.open() as source:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON") from exc
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: expected an object")
            values.append(value)
    return values


def _digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            hasher.update(block)
    return "sha256:" + hasher.hexdigest()


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _metrics(rows: Iterable[tuple[dict[str, Any], dict[str, Any] | None]]) -> dict[str, Any]:
    total = answered = correct = 0
    for item, prediction in rows:
        total += 1
        if prediction is None or prediction.get("abstain") is True:
            continue
        answered += 1
        correct += prediction["answer"] == item["answer"]
    return {
        "total": total,
        "answered": answered,
        "abstained": total - answered,
        "coverage": _rate(answered, total),
        "accuracy_on_answered": _rate(correct, answered),
        "accuracy_with_abstentions_incorrect": _rate(correct, total),
        "correct": correct,
    }


def evaluate(dataset_path: Path, predictions_path: Path) -> dict[str, Any]:
    dataset = _read_jsonl(dataset_path)
    predictions = _read_jsonl(predictions_path)
    required = {"id", "answer", "reasoning_group", "signal", "category"}
    ids: set[str] = set()
    for item in dataset:
        if not required.issubset(item):
            raise ValueError("dataset item lacks required WearableQA fields")
        if item["id"] in ids:
            raise ValueError(f"duplicate dataset id: {item['id']}")
        ids.add(item["id"])
        if not isinstance(item["answer"], str) or item["answer"] not in LETTERS:
            raise ValueError(f"invalid ground-truth answer for {item['id']}")

    by_id: dict[str, dict[str, Any]] = {}
    for prediction in predictions:
        prediction_id = prediction.get("id")
        if prediction_id not in ids:
            raise ValueError(f"prediction references unknown id: {prediction_id}")
        if prediction_id in by_id:
            raise ValueError(f"duplicate prediction id: {prediction_id}")
        allowed = {"id", "answer", "abstain", "reason", "provenance"}
        if set(prediction) - allowed:
            raise ValueError(f"prediction {prediction_id} contains unsupported fields")
        abstain = prediction.get("abstain") is True
        answer = prediction.get("answer")
        has_answer = isinstance(answer, str) and answer in LETTERS
        if abstain == has_answer:
            raise ValueError(f"prediction {prediction_id} must contain exactly one of answer or abstain=true")
        if not abstain and not has_answer:
            raise ValueError(f"prediction {prediction_id} has an invalid answer")
        by_id[prediction_id] = prediction

    paired = [(item, by_id.get(item["id"])) for item in dataset]
    groups: dict[str, dict[str, list[tuple[dict[str, Any], dict[str, Any] | None]]]] = {
        axis: defaultdict(list) for axis in ("reasoning_group", "signal", "category")
    }
    for item, prediction in paired:
        for axis in groups:
            groups[axis][item[axis]].append((item, prediction))

    return {
        "benchmark": "WearableQA",
        "status": "research_evaluation_only",
        "dataset_digest": _digest(dataset_path),
        "predictions_digest": _digest(predictions_path),
        "overall": _metrics(paired),
        "by_axis": {
            axis: {name: _metrics(rows) for name, rows in sorted(values.items())}
            for axis, values in groups.items()
        },
        "warnings": [
            "Multiple-choice accuracy is not clinical validity.",
            "Missing predictions are counted as abstentions.",
            "Compare systems at matched coverage; selective accuracy alone is insufficient.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = evaluate(args.dataset, args.predictions)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.write_text(rendered)
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
