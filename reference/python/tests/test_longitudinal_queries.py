from __future__ import annotations

import pytest

from openbody_ref.longitudinal import QueryError, execute_query


def _observations() -> list[dict]:
    return [
        {
            "subject": "subject:local-demo",
            "timestamp": f"2026-01-{day:02d}T00:00:00Z",
            "source_id": "healthkit:watch",
            "quality": 0.9,
            "values": {"rhr": 50 + day, "steps": 1000 * day},
        }
        for day in range(1, 8)
    ]


def _request(operation: str, **parameters: object) -> dict:
    return {
        "subject": "subject:local-demo",
        "operation": operation,
        "observations": _observations(),
        "parameters": {"metric": "rhr", **parameters},
    }


def test_summary_and_trend_are_deterministic_and_digest_bound() -> None:
    summary = execute_query(_request("summary"))
    trend = execute_query(_request("trend"))
    assert summary["disposition"] == "computed"
    assert summary["result"]["mean"] == 54.0
    assert trend["result"]["slope_per_day"] == pytest.approx(1.0)
    assert trend["result"]["direction"] == "increasing"
    assert summary["provenance"]["source_ids"] == ["healthkit:watch"]
    assert summary["provenance"]["observation_digest"].startswith("sha256:")
    assert execute_query(_request("summary")) == summary


def test_lagged_correlation_uses_paired_samples() -> None:
    result = execute_query(_request("lagged_correlation", other_metric="steps", max_lag=2))
    assert result["disposition"] == "computed"
    assert result["result"]["pearson_r"] == pytest.approx(1.0)
    assert result["result"]["lag_days"] == 0
    assert result["result"]["pair_count"] == 7


def test_excursions_use_a_baseline_outside_target_window() -> None:
    request = _request(
        "excursions",
        start="2026-01-07T00:00:00Z",
        end="2026-01-07T00:00:00Z",
        baseline_start="2026-01-01T00:00:00Z",
        baseline_end="2026-01-05T00:00:00Z",
        threshold_mad=1.0,
        minimum_samples=1,
    )
    result = execute_query(request)
    assert result["disposition"] == "computed"
    assert result["result"]["excursion_count"] == 1


def test_recovery_returns_first_consecutive_in_range_sample() -> None:
    observations = _observations()
    observations.extend(
        [
            {"subject": "subject:local-demo", "timestamp": "2026-01-08T00:00:00Z",
             "source_id": "healthkit:watch", "values": {"rhr": 70}},
            {"subject": "subject:local-demo", "timestamp": "2026-01-09T00:00:00Z",
             "source_id": "healthkit:watch", "values": {"rhr": 54}},
            {"subject": "subject:local-demo", "timestamp": "2026-01-10T00:00:00Z",
             "source_id": "healthkit:watch", "values": {"rhr": 53}},
        ]
    )
    request = _request(
        "recovery",
        event_time="2026-01-08T00:00:00Z",
        start="2026-01-08T00:00:00Z",
        end="2026-01-10T00:00:00Z",
        baseline_start="2026-01-01T00:00:00Z",
        baseline_end="2026-01-07T00:00:00Z",
        tolerance=1.0,
        consecutive_samples=2,
    )
    request["observations"] = observations
    result = execute_query(request)
    assert result["disposition"] == "computed"
    assert result["result"]["recovered_at"] == "2026-01-09T00:00:00Z"
    assert result["result"]["recovery_seconds"] == 86_400


def test_insufficient_data_abstains_and_malformed_data_is_rejected() -> None:
    request = _request("summary", minimum_samples=99)
    result = execute_query(request)
    assert result["disposition"] == "abstained"
    assert result["reason_code"] == "insufficient_data"

    hostile = _request("summary")
    hostile["observations"][0]["values"]["rhr"] = float("nan")
    with pytest.raises(QueryError, match="finite"):
        execute_query(hostile)

    cross_subject = _request("summary")
    cross_subject["observations"][0]["subject"] = "subject:other"
    with pytest.raises(QueryError, match="subject"):
        execute_query(cross_subject)

    competing_sources = _request("summary")
    duplicate = dict(competing_sources["observations"][0])
    duplicate["source_id"] = "manual:override"
    competing_sources["observations"].append(duplicate)
    with pytest.raises(QueryError, match="competing sources"):
        execute_query(competing_sources)

    unknown_parameter = _request("trend", clinical_interpretation=True)
    with pytest.raises(QueryError, match="unsupported parameters"):
        execute_query(unknown_parameter)


def test_minimum_quality_filters_before_computation() -> None:
    request = _request("summary", minimum_quality=0.95)
    result = execute_query(request)
    assert result["disposition"] == "abstained"
    assert result["provenance"]["sample_count"] == 0
