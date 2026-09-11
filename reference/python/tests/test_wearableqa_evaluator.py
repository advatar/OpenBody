from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("evaluate_wearableqa", ROOT / "tools" / "evaluate_wearableqa.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def _write_jsonl(path: Path, values: list[dict]) -> None:
    path.write_text("".join(json.dumps(value) + "\n" for value in values))


def _manifest(path: Path) -> Path:
    path.write_text(json.dumps({"system": "test", "revision": "1", "prompt_tool_policy": "none",
                                "seed": None, "adapter_version": "test/1"}))
    return path


def test_evaluator_reports_cross_signal_and_abstention_metrics(tmp_path: Path) -> None:
    dataset = [
        {"id": "q1", "answer": "A", "reasoning_group": "data", "signal": "single", "category": "trend"},
        {"id": "q2", "answer": "B", "reasoning_group": "health", "signal": "cross", "category": "risk"},
        {"id": "q3", "answer": "C", "reasoning_group": "data", "signal": "cross", "category": "coupling"},
    ]
    predictions = [
        {"id": "q1", "answer": "A", "provenance": {"query_digest": "sha256:test"}},
        {"id": "q2", "abstain": True, "reason": "unsupported clinical interpretation"},
        {"id": "q3", "answer": "D"},
    ]
    dataset_path, predictions_path = tmp_path / "dataset.jsonl", tmp_path / "predictions.jsonl"
    _write_jsonl(dataset_path, dataset)
    _write_jsonl(predictions_path, predictions)
    report = MODULE.evaluate(dataset_path, predictions_path, _manifest(tmp_path / "manifest.json"))
    assert report["overall"]["coverage"] == pytest.approx(2 / 3)
    assert report["overall"]["accuracy_on_answered"] == 0.5
    assert report["by_axis"]["signal"]["cross"]["coverage"] == 0.5
    assert report["overall"]["abstained"] == 1
    assert report["overall"]["missing_predictions"] == 0
    assert report["overall"]["execution_errors"] == 0
    assert report["dataset_digest"].startswith("sha256:")


def test_evaluator_rejects_unknown_and_ambiguous_predictions(tmp_path: Path) -> None:
    dataset_path, predictions_path = tmp_path / "dataset.jsonl", tmp_path / "predictions.jsonl"
    _write_jsonl(dataset_path, [
        {"id": "q1", "answer": "A", "reasoning_group": "data", "signal": "single", "category": "trend"}
    ])
    _write_jsonl(predictions_path, [{"id": "unknown", "answer": "A"}])
    with pytest.raises(ValueError, match="unknown id"):
        MODULE.evaluate(dataset_path, predictions_path, _manifest(tmp_path / "manifest.json"))

    _write_jsonl(predictions_path, [{"id": "q1", "answer": "A", "abstain": True}])
    with pytest.raises(ValueError, match="exactly one"):
        MODULE.evaluate(dataset_path, predictions_path, _manifest(tmp_path / "manifest.json"))


def test_evaluator_separates_missing_from_explicit_abstention(tmp_path: Path) -> None:
    dataset_path, predictions_path = tmp_path / "dataset.jsonl", tmp_path / "predictions.jsonl"
    _write_jsonl(dataset_path, [
        {"id": "q1", "answer": "A", "reasoning_group": "data", "signal": "single", "category": "trend"},
        {"id": "q2", "answer": "B", "reasoning_group": "data", "signal": "single", "category": "trend"},
    ])
    _write_jsonl(predictions_path, [{"id": "q1", "error": True, "reason": "runner failed"}])
    report = MODULE.evaluate(dataset_path, predictions_path, _manifest(tmp_path / "manifest.json"))
    assert report["overall"]["abstained"] == 0
    assert report["overall"]["missing_predictions"] == 1
    assert report["overall"]["execution_errors"] == 1
