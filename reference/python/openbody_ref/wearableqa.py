from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from .longitudinal import QueryError, execute_query
from .validation import canonical_digest


ADAPTER_VERSION = "openbody-wearableqa-signal-summary/0.2"
SUPPORTED_QUESTION_TYPE = "signal_summary"
_VALUE_PATTERN = re.compile(r"\bis\s+(-?\d+(?:\.\d+)?)\b", re.IGNORECASE)


@dataclass(frozen=True)
class ProjectedItem:
    item_id: str
    user_id: str
    stem: str
    options: tuple[tuple[str, str], ...]
    start: str
    end: str
    metric: str
    statistic: str
    observations: tuple[tuple[str, tuple[tuple[str, float], ...]], ...]


def _semantic(stem: str) -> tuple[str, str]:
    normalized = stem.casefold()
    if "daily heart rate per step" in normalized and "dhrps" in normalized:
        return "dhrps", "mean"
    if "mean nightly sleep duration" in normalized:
        return "sleep_duration", "mean"
    if "median daily step count" in normalized:
        return "steps", "median"
    if "mean daily step count" in normalized:
        return "steps", "mean"
    if "mean resting heart rate" in normalized:
        return "rhr", "mean"
    raise QueryError("signal_summary stem is outside the reviewed semantic allowlist")


def _observations(projected: ProjectedItem) -> list[dict[str, Any]]:
    return [
        {
            "subject": f"wearableqa:{projected.user_id}",
            "timestamp": f"{day}T00:00:00Z",
            "source_id": "wearableqa:raw",
            "values": dict(values),
        }
        for day, values in projected.observations
    ]


def _project_item(item: dict[str, Any], user_histories: dict[str, Any]) -> ProjectedItem:
    item_id = item.get("id")
    user_id = item.get("user_id")
    stem = item.get("stem")
    options = item.get("options")
    if not isinstance(item_id, str) or not item_id:
        raise QueryError("item requires a non-empty id")
    if not isinstance(user_id, str) or user_id not in user_histories:
        raise QueryError("item references an unknown user history")
    if not isinstance(stem, str) or not isinstance(options, dict):
        raise QueryError("item requires a stem and options")
    metric, statistic = _semantic(stem)
    required_metrics = {"rhr", "steps"} if metric == "dhrps" else {metric}
    full_dropped = item.get("full_dropped_metrics", [])
    window_dropped = item.get("window_dropped_metrics", [])
    hidden_metric = item.get("hidden_metric")
    if not isinstance(full_dropped, list) or not isinstance(window_dropped, list):
        raise QueryError("metric visibility controls must be arrays")
    hidden = set(full_dropped) | set(window_dropped)
    if hidden_metric is not None:
        if not isinstance(hidden_metric, str):
            raise QueryError("hidden_metric must be a string")
        hidden.add(hidden_metric)
    if required_metrics.intersection(hidden):
        raise QueryError("required metric is hidden by the benchmark visibility policy")
    window_size = item.get("window_size")
    if isinstance(window_size, bool) or not isinstance(window_size, int) or window_size < 1:
        raise QueryError("window_size must be a positive integer")
    try:
        end = date.fromisoformat(item["end_date"])
    except (KeyError, TypeError, ValueError) as exc:
        raise QueryError("end_date must be an ISO date") from exc
    start = end - timedelta(days=window_size - 1)
    history = user_histories[user_id]
    if not isinstance(history, list):
        raise QueryError("user history must be an array")
    rows = []
    for row in history:
        if not isinstance(row, dict) or not isinstance(row.get("date"), str):
            raise QueryError("history rows require a date")
        try:
            day = date.fromisoformat(row["date"])
        except ValueError as exc:
            raise QueryError("history date must be an ISO date") from exc
        if start <= day <= end:
            values = tuple(sorted((name, row[name]) for name in required_metrics if row.get(name) is not None))
            rows.append((day.isoformat(), values))
    return ProjectedItem(item_id, user_id, stem, tuple(sorted(options.items())), start.isoformat(), end.isoformat(),
                         metric, statistic, tuple(rows))


def _projection_digest(projected: ProjectedItem) -> str:
    return canonical_digest({
        "id": projected.item_id,
        "user_id": projected.user_id,
        "stem": projected.stem,
        "options": dict(projected.options),
        "start": projected.start,
        "end": projected.end,
        "metric": projected.metric,
        "statistic": projected.statistic,
        "observations": [{"date": day, "values": dict(values)} for day, values in projected.observations],
    })


def _summary(
    user_id: str,
    observations: list[dict[str, Any]],
    metric: str,
    start: str,
    end: str,
) -> dict[str, Any]:
    return execute_query({
        "subject": f"wearableqa:{user_id}",
        "operation": "summary",
        "observations": observations,
        "parameters": {
            "metric": metric,
            "start": f"{start}T00:00:00Z",
            "end": f"{end}T23:59:59Z",
            "minimum_samples": 1,
        },
    })


def _option_value(options: Any, target: float) -> str:
    if not isinstance(options, dict) or set(options) != set("ABCDEFGHIJ"):
        raise QueryError("signal_summary requires exactly options A through J")
    candidates: list[tuple[float, str]] = []
    for letter, text in options.items():
        if not isinstance(text, str):
            raise QueryError("option text must be a string")
        match = _VALUE_PATTERN.search(text)
        if match:
            option_value = float(match.group(1))
            if math.isclose(option_value, target, rel_tol=0, abs_tol=1e-12):
                candidates.append((0.0, letter))
    if not candidates:
        raise QueryError("no option exactly matches the rounded computed value")
    candidates.sort()
    if len(candidates) > 1 and math.isclose(candidates[0][0], candidates[1][0], rel_tol=0, abs_tol=1e-12):
        raise QueryError("numeric options are tied at the computed value")
    return candidates[0][1]


def _benchmark_round(metric: str, statistic: str, value: float) -> float:
    if not math.isfinite(value):
        raise QueryError("composed result is non-finite")
    if metric == "steps":
        return float(round(value / 100) * 100)
    if metric in {"sleep_duration", "dhrps"}:
        return round(value, 1)
    if metric == "rhr" and statistic == "mean":
        return float(round(value))
    raise QueryError("no reviewed benchmark rounding rule exists")


def answer_item(item: dict[str, Any], user_histories: dict[str, Any]) -> dict[str, Any]:
    """Answer one reviewed deterministic item, otherwise explicitly abstain."""
    item_id = item.get("id")
    if not isinstance(item_id, str) or not item_id:
        raise QueryError("item requires a non-empty id")
    if item.get("question_type") != SUPPORTED_QUESTION_TYPE:
        return {"id": item_id, "abstain": True, "reason": "unsupported_question_type",
                "provenance": {"adapter": ADAPTER_VERSION}}
    try:
        projected = _project_item(item, user_histories)
    except QueryError as exc:
        return {"id": item_id, "abstain": True, "reason": str(exc),
                "provenance": {"adapter": ADAPTER_VERSION}}
    observations = _observations(projected)
    metric, statistic = projected.metric, projected.statistic

    receipts = []
    if metric == "dhrps":
        rhr = _summary(projected.user_id, observations, "rhr", projected.start, projected.end)
        steps = _summary(projected.user_id, observations, "steps", projected.start, projected.end)
        receipts.extend((rhr, steps))
        if rhr["disposition"] != "computed" or steps["disposition"] != "computed" or steps["result"]["mean"] == 0:
            return {"id": item_id, "abstain": True, "reason": "insufficient_data",
                    "provenance": {"adapter": ADAPTER_VERSION}}
        value = rhr["result"]["mean"] / steps["result"]["mean"] * 1000
    else:
        receipt = _summary(projected.user_id, observations, metric, projected.start, projected.end)
        receipts.append(receipt)
        if receipt["disposition"] != "computed":
            return {"id": item_id, "abstain": True, "reason": receipt["reason_code"],
                    "provenance": {"adapter": ADAPTER_VERSION}}
        value = receipt["result"][statistic]

    rounded_value = _benchmark_round(metric, statistic, value)
    answer = _option_value(dict(projected.options), rounded_value)
    return {
        "id": item_id,
        "answer": answer,
        "provenance": {
            "adapter": ADAPTER_VERSION,
            "semantic": metric if metric == "dhrps" else f"{statistic}:{metric}",
            "computed_value": value,
            "rounded_value": rounded_value,
            "projection_digest": _projection_digest(projected),
            "query_digests": [receipt["provenance"]["query_digest"] for receipt in receipts],
        },
    }


def answer_dataset(raw: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(raw, dict) or not isinstance(raw.get("mcqs"), list):
        raise QueryError("raw WearableQA data requires an mcqs array")
    histories = raw.get("user_histories")
    if not isinstance(histories, dict):
        raise QueryError("raw WearableQA data requires user_histories")
    results = []
    for item in raw["mcqs"]:
        try:
            results.append(answer_item(item, histories))
        except QueryError as exc:
            item_id = item.get("id") if isinstance(item, dict) else None
            if not isinstance(item_id, str) or not item_id:
                raise
            results.append({"id": item_id, "error": True, "reason": str(exc),
                            "provenance": {"adapter": ADAPTER_VERSION}})
    return results
