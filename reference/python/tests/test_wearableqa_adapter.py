from __future__ import annotations

from openbody_ref.wearableqa import answer_dataset, answer_item


def _history() -> dict:
    return {"user_1": [
        {"date": "2026-01-01", "rhr": 60, "steps": 1000, "sleep_duration": 7},
        {"date": "2026-01-02", "rhr": 62, "steps": 2000, "sleep_duration": 8},
        {"date": "2026-01-03", "rhr": 64, "steps": 3000, "sleep_duration": 9},
    ]}


def _item(stem: str, values: list[float]) -> dict:
    return {
        "id": "q1",
        "user_id": "user_1",
        "question_type": "signal_summary",
        "stem": stem,
        "end_date": "2026-01-03",
        "window_size": 3,
        "options": {letter: f"computed value is {value}" for letter, value in zip("ABCDEFGHIJ", values, strict=True)},
    }


def test_adapter_answers_reviewed_summary_without_ground_truth() -> None:
    item = _item("What is their mean resting heart rate (RHR)?", [1, 2, 3, 4, 5, 62, 70, 80, 90, 100])
    item["gt_letter"] = "A"  # Deliberately wrong: the adapter must not read the label.
    result = answer_item(item, _history())
    assert result["answer"] == "F"
    assert result["provenance"]["semantic"] == "mean:rhr"
    assert len(result["provenance"]["query_digests"]) == 1


def test_projection_excludes_future_history_ground_truth_and_unrelated_metrics() -> None:
    item = _item("What is their mean resting heart rate (RHR)?", [1, 2, 3, 4, 5, 62, 70, 80, 90, 100])
    baseline = answer_item(dict(item, gt_letter="A"), _history())
    changed = _history()
    changed["user_1"].append({"date": "2027-01-01", "rhr": 999, "secret": 123})
    repeated = answer_item(dict(item, gt_letter="J", cohort_reference={"answer": "J"}), changed)
    assert repeated["answer"] == baseline["answer"]
    assert repeated["provenance"]["projection_digest"] == baseline["provenance"]["projection_digest"]


def test_hidden_required_metric_forces_abstention() -> None:
    item = _item("What is their mean resting heart rate (RHR)?", [1, 2, 3, 4, 5, 62, 70, 80, 90, 100])
    item["full_dropped_metrics"] = ["rhr"]
    result = answer_item(item, _history())
    assert result["abstain"] is True
    assert "hidden" in result["reason"]

    for field, value in (("hidden_metric", "rhr"), ("window_dropped_metrics", ["rhr"])):
        visible = _item("What is their mean resting heart rate (RHR)?", [1, 2, 3, 4, 5, 62, 70, 80, 90, 100])
        visible[field] = value
        result = answer_item(visible, _history())
        assert result["abstain"] is True
        assert "hidden" in result["reason"]


def test_adapter_supports_composed_dhrps_and_abstains_elsewhere() -> None:
    item = _item(
        "Mean Daily Heart Rate per Step (DHRPS), computed as mean daily HR divided by mean daily steps",
        [1, 2, 3, 4, 5, 31, 40, 50, 60, 70],
    )
    result = answer_item(item, _history())
    assert result["answer"] == "F"
    assert len(result["provenance"]["query_digests"]) == 2

    item["question_type"] = "recovery_time"
    assert answer_item(item, _history())["abstain"] is True


def test_dataset_preserves_one_prediction_per_item() -> None:
    supported = _item("What is their median daily step count?", [1, 2, 3, 4, 5, 2000, 7, 8, 9, 10])
    unsupported = dict(supported, id="q2", question_type="health_recommendation")
    results = answer_dataset({"mcqs": [supported, unsupported], "user_histories": _history()})
    assert [result["id"] for result in results] == ["q1", "q2"]
    assert results[1]["reason"] == "unsupported_question_type"
