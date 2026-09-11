from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from .validation import canonical_digest, parse_timestamp


ALGORITHM_VERSION = "openbody-longitudinal-query/0.1"
SUPPORTED_OPERATIONS = frozenset({"summary", "trend", "lagged_correlation", "excursions", "recovery"})


class QueryError(ValueError):
    """Malformed requests are rejected; insufficient data produces an abstention."""


@dataclass(frozen=True)
class Point:
    timestamp: datetime
    value: float
    source_id: str


def _finite_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise QueryError(f"{field} must be a finite number")
    return float(value)


def _timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise QueryError(f"{field} must be an RFC 3339 timestamp")
    try:
        result = parse_timestamp(value)
    except Exception as exc:
        raise QueryError(f"{field} must be an RFC 3339 timestamp") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise QueryError(f"{field} must include an offset")
    return result.astimezone(timezone.utc)


def _validate_request(request: dict[str, Any]) -> None:
    allowed = {"subject", "operation", "observations", "parameters"}
    if not isinstance(request, dict) or set(request) - allowed:
        raise QueryError("query contains unsupported fields")
    if not isinstance(request.get("subject"), str) or not request["subject"]:
        raise QueryError("subject must be a non-empty string")
    if request.get("operation") not in SUPPORTED_OPERATIONS:
        raise QueryError("unsupported longitudinal operation")
    if not isinstance(request.get("observations"), list):
        raise QueryError("observations must be an array")
    if not isinstance(request.get("parameters", {}), dict):
        raise QueryError("parameters must be an object")


def _points(request: dict[str, Any], metric: str, minimum_quality: float = 0.0) -> list[Point]:
    subject = request["subject"]
    points: list[Point] = []
    seen: set[datetime] = set()
    for index, observation in enumerate(request["observations"]):
        if not isinstance(observation, dict):
            raise QueryError("every observation must be an object")
        allowed = {"subject", "timestamp", "values", "source_id", "quality"}
        if set(observation) - allowed:
            raise QueryError("observation contains unsupported fields")
        if observation.get("subject") != subject:
            raise QueryError("observation subject does not match query subject")
        timestamp = _timestamp(observation.get("timestamp"), f"observations[{index}].timestamp")
        source_id = observation.get("source_id")
        if not isinstance(source_id, str) or not source_id:
            raise QueryError("every observation requires a non-empty source_id")
        values = observation.get("values")
        if not isinstance(values, dict):
            raise QueryError("every observation requires a values object")
        if metric not in values or values[metric] is None:
            continue
        quality = observation.get("quality", 1.0)
        quality = _finite_number(quality, "observation quality")
        if quality < 0 or quality > 1:
            raise QueryError("observation quality must be between 0 and 1")
        value = _finite_number(values[metric], f"observation value for {metric}")
        if quality < minimum_quality:
            continue
        if timestamp in seen:
            raise QueryError("duplicate timestamp for metric; resolve competing sources before querying")
        seen.add(timestamp)
        points.append(Point(timestamp, value, source_id))
    return sorted(points, key=lambda point: (point.timestamp, point.source_id))


def _window(points: Iterable[Point], start: datetime | None, end: datetime | None) -> list[Point]:
    return [p for p in points if (start is None or p.timestamp >= start) and (end is None or p.timestamp <= end)]


def _bounds(parameters: dict[str, Any], prefix: str = "") -> tuple[datetime | None, datetime | None]:
    start_key, end_key = f"{prefix}start", f"{prefix}end"
    start = _timestamp(parameters[start_key], start_key) if parameters.get(start_key) is not None else None
    end = _timestamp(parameters[end_key], end_key) if parameters.get(end_key) is not None else None
    if start is not None and end is not None and start > end:
        raise QueryError(f"{start_key} must not be after {end_key}")
    return start, end


def _median_absolute_deviation(values: list[float]) -> float:
    median = statistics.median(values)
    return statistics.median(abs(value - median) for value in values)


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3:
        return None
    mean_x, mean_y = statistics.fmean(xs), statistics.fmean(ys)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    denominator = math.sqrt(sum((x - mean_x) ** 2 for x in xs) * sum((y - mean_y) ** 2 for y in ys))
    return numerator / denominator if denominator else None


def _abstention(request: dict[str, Any], reason_code: str, reason: str, sample_count: int = 0) -> dict[str, Any]:
    return {
        "kind": "LongitudinalQueryResult",
        "version": "0.1",
        "subject": request["subject"],
        "operation": request["operation"],
        "disposition": "abstained",
        "reason_code": reason_code,
        "reason": reason,
        "result": None,
        "provenance": _provenance(request, sample_count),
    }


def _provenance(request: dict[str, Any], sample_count: int) -> dict[str, Any]:
    source_ids = sorted({o.get("source_id") for o in request["observations"] if o.get("source_id")})
    return {
        "algorithm": ALGORITHM_VERSION,
        "query_digest": canonical_digest(request),
        "observation_digest": canonical_digest(request["observations"]),
        "source_ids": source_ids,
        "sample_count": sample_count,
    }


def _computed(request: dict[str, Any], result: dict[str, Any], sample_count: int) -> dict[str, Any]:
    return {
        "kind": "LongitudinalQueryResult",
        "version": "0.1",
        "subject": request["subject"],
        "operation": request["operation"],
        "disposition": "computed",
        "reason_code": None,
        "reason": None,
        "result": result,
        "provenance": _provenance(request, sample_count),
    }


def _unique_sample_count(*point_sets: Iterable[Point]) -> int:
    return len({(point.timestamp, point.source_id) for points in point_sets for point in points})


def execute_query(request: dict[str, Any]) -> dict[str, Any]:
    """Execute a deterministic query without attaching clinical meaning to it."""
    _validate_request(request)
    parameters = request.get("parameters", {})
    operation = request["operation"]
    common_parameters = {"metric", "minimum_samples", "minimum_quality", "start", "end"}
    operation_parameters = {
        "summary": set(),
        "trend": set(),
        "lagged_correlation": {"other_metric", "max_lag"},
        "excursions": {"baseline_start", "baseline_end", "threshold_mad"},
        "recovery": {"baseline_start", "baseline_end", "event_time", "tolerance", "consecutive_samples"},
    }
    unexpected = set(parameters) - common_parameters - operation_parameters[operation]
    if unexpected:
        raise QueryError(f"unsupported parameters for {operation}: {sorted(unexpected)}")
    metric = parameters.get("metric")
    if not isinstance(metric, str) or not metric:
        raise QueryError("parameters.metric must be a non-empty string")
    minimum = parameters.get("minimum_samples", 3)
    if isinstance(minimum, bool) or not isinstance(minimum, int) or minimum < 1:
        raise QueryError("minimum_samples must be a positive integer")
    minimum_quality = _finite_number(parameters.get("minimum_quality", 0.0), "minimum_quality")
    if minimum_quality < 0 or minimum_quality > 1:
        raise QueryError("minimum_quality must be between 0 and 1")

    if operation == "lagged_correlation":
        other_metric = parameters.get("other_metric")
        if not isinstance(other_metric, str) or not other_metric or other_metric == metric:
            raise QueryError("lagged_correlation requires a distinct other_metric")
        max_lag = parameters.get("max_lag", 0)
        if isinstance(max_lag, bool) or not isinstance(max_lag, int) or max_lag < 0 or max_lag > 30:
            raise QueryError("max_lag must be an integer from 0 to 30")
        start, end = _bounds(parameters)
        first = {p.timestamp: p for p in _window(_points(request, metric, minimum_quality), start, end)}
        second = {p.timestamp: p for p in _window(_points(request, other_metric, minimum_quality), start, end)}
        candidates: list[tuple[float, int, int]] = []
        day = 86_400
        for lag in range(-max_lag, max_lag + 1):
            xs, ys = [], []
            for timestamp, point in first.items():
                shifted = datetime.fromtimestamp(timestamp.timestamp() + lag * day, tz=timezone.utc)
                match = second.get(shifted)
                if match is not None:
                    xs.append(point.value)
                    ys.append(match.value)
            correlation = _pearson(xs, ys)
            if correlation is not None and len(xs) >= minimum:
                candidates.append((correlation, lag, len(xs)))
        if not candidates:
            return _abstention(request, "insufficient_data", "No lag has enough paired, varying samples")
        correlation, lag, count = max(candidates, key=lambda item: (abs(item[0]), -abs(item[1]), -item[1]))
        return _computed(request, {"metric": metric, "other_metric": other_metric, "lag_days": lag,
                                   "pearson_r": correlation, "pair_count": count}, count)

    points = _points(request, metric, minimum_quality)
    start, end = _bounds(parameters)
    selected = _window(points, start, end)
    if len(selected) < minimum:
        return _abstention(request, "insufficient_data", "Too few observations in the requested window", len(selected))
    values = [point.value for point in selected]

    if operation == "summary":
        result = {"metric": metric, "count": len(values), "mean": statistics.fmean(values),
                  "median": statistics.median(values), "minimum": min(values), "maximum": max(values),
                  "standard_deviation": statistics.pstdev(values)}
        return _computed(request, result, len(values))

    if operation == "trend":
        origin = selected[0].timestamp
        xs = [(point.timestamp - origin).total_seconds() / 86_400 for point in selected]
        mean_x, mean_y = statistics.fmean(xs), statistics.fmean(values)
        denominator = sum((x - mean_x) ** 2 for x in xs)
        if denominator == 0:
            return _abstention(request, "insufficient_temporal_span", "Trend requires distinct timestamps", len(values))
        slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, values, strict=True)) / denominator
        return _computed(request, {"metric": metric, "slope_per_day": slope,
                                   "direction": "increasing" if slope > 0 else "decreasing" if slope < 0 else "stable",
                                   "span_days": max(xs) - min(xs)}, len(values))

    if operation == "excursions":
        baseline_start, baseline_end = _bounds(parameters, "baseline_")
        baseline = _window(points, baseline_start, baseline_end)
        if len(baseline) < minimum:
            return _abstention(request, "insufficient_baseline", "Too few baseline observations", len(baseline))
        threshold = _finite_number(parameters.get("threshold_mad", 3.0), "threshold_mad")
        if threshold <= 0:
            raise QueryError("threshold_mad must be positive")
        baseline_values = [point.value for point in baseline]
        center = statistics.median(baseline_values)
        mad = _median_absolute_deviation(baseline_values)
        if mad == 0:
            return _abstention(request, "degenerate_baseline", "Baseline median absolute deviation is zero", len(baseline))
        scale = 1.4826 * mad
        excursions = [{"timestamp": point.timestamp.isoformat().replace("+00:00", "Z"), "value": point.value,
                       "robust_z": (point.value - center) / scale}
                      for point in selected if abs(point.value - center) / scale >= threshold]
        return _computed(request, {"metric": metric, "baseline_median": center, "baseline_mad": mad,
                                   "threshold_mad": threshold, "excursion_count": len(excursions),
                                   "excursions": excursions}, _unique_sample_count(selected, baseline))

    if operation == "recovery":
        event_time = _timestamp(parameters.get("event_time"), "event_time")
        baseline_start, baseline_end = _bounds(parameters, "baseline_")
        baseline = _window(points, baseline_start, baseline_end)
        if len(baseline) < minimum:
            return _abstention(request, "insufficient_baseline", "Too few baseline observations", len(baseline))
        tolerance = _finite_number(parameters.get("tolerance"), "tolerance")
        if tolerance < 0:
            raise QueryError("tolerance must be non-negative")
        consecutive = parameters.get("consecutive_samples", 2)
        if isinstance(consecutive, bool) or not isinstance(consecutive, int) or consecutive < 1:
            raise QueryError("consecutive_samples must be a positive integer")
        center = statistics.median(point.value for point in baseline)
        after = [point for point in selected if point.timestamp >= event_time]
        run = 0
        for index, point in enumerate(after):
            run = run + 1 if abs(point.value - center) <= tolerance else 0
            if run >= consecutive:
                recovery_point = after[index - consecutive + 1]
                seconds = (recovery_point.timestamp - event_time).total_seconds()
                return _computed(request, {"metric": metric, "baseline_median": center,
                                           "tolerance": tolerance, "recovery_seconds": seconds,
                                           "recovered_at": recovery_point.timestamp.isoformat().replace("+00:00", "Z")},
                                 _unique_sample_count(after, baseline))
        return _abstention(request, "recovery_not_observed", "Recovery was not observed in the requested window",
                           _unique_sample_count(after, baseline))

    raise AssertionError("validated operation was not implemented")
