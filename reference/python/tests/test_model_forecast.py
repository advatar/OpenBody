from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
import hashlib
import inspect

import httpx
import pytest
from fastapi.testclient import TestClient

from test_model_family import setup as state_setup, synthetic_model
from openbody_ref.client import OpenBodyClient
from openbody_ref.host import create_model_execution_host
from openbody_ref.model_family import (ForecastEvaluation, ForecastModelRegistration, ForecastPoint,
    ModelEvaluation, ModelExecutionError, ModelRegistration, QualifiedModelRuntime)
from openbody_ref.model_forecast import FORECAST_VALIDATOR, forecast_output, validate_forecast
from openbody_ref.validation import canonical_digest, parse_timestamp


def synthetic_forecast(inputs, parameters, horizon):
    """Deterministic software fixture. No physiological dynamics are asserted."""
    start = synthetic_model(inputs, parameters)
    end = ModelEvaluation({"synthetic_shifted_value": start.metrics["synthetic_shifted_value"] + 1}, start.uncertainty)
    return ForecastEvaluation((ForecastPoint(0, start), ForecastPoint(horizon, end)), start.uncertainty, ("Synthetic software test only",))


@pytest.fixture
def setup(state_setup):
    contract, request, row, source, authority, clock, _ = state_setup
    artifact = inspect.getsource(synthetic_forecast).encode()
    contract["prediction_horizon_seconds"] = [7200]
    contract["model"]["artifact_digest"] = "sha256:" + hashlib.sha256(artifact).hexdigest()
    request["horizon_seconds"] = 7200
    authority.current = replace(authority.current, horizon_seconds=7200, contract_digest=canonical_digest(contract),
                                artifact_digest=contract["model"]["artifact_digest"])
    def factory(evaluate=synthetic_forecast):
        return QualifiedModelRuntime(row["subject"], row["source"]["clinical_version"]["tenant_id"], source, authority,
            [ForecastModelRegistration(contract, artifact, evaluate)], clock=lambda: clock[0])
    return contract, request, row, source, authority, clock, factory


def test_actual_forecast_call_has_separate_type_horizon_and_complete_digest(setup):
    contract, request, row, source, authority, clock, factory = setup
    calls = []
    def model(inputs, parameters, horizon):
        calls.append(horizon)
        return synthetic_forecast(inputs, parameters, horizon)
    runtime = factory(model)
    result = runtime.execute(request)
    FORECAST_VALIDATOR.validate(result)
    assert result["kind"] == "ModelForecast"
    assert result["request_digest"] == canonical_digest(request)
    trajectory = result["trajectory"]
    assert trajectory["trajectory_kind"] == "predicted"
    assert calls == [7200]
    states = trajectory["states"]
    assert [point["subsystems"][0]["state_vector"]["synthetic_shifted_value"] for point in states] == [37, 38]
    assert parse_timestamp(states[0]["state_time"]) == clock[0]
    assert parse_timestamp(states[-1]["state_time"]) - parse_timestamp(states[0]["state_time"]) == timedelta(hours=2)
    assert trajectory["model_receipts"][0]["output_digest"] == canonical_digest(forecast_output(result))
    assert result["qualification_valid_until"] == authority.current.valid_until.isoformat().replace("+00:00", "Z")
    assert parse_timestamp(result["qualification_valid_until"]) < parse_timestamp(states[-1]["state_time"])
    assert all("valid_until" not in state for state in states)
    assert all(state["uncertainty"]["coverage"] is None for state in states)
    assert trajectory["uncertainty"]["coverage"] is None
    assert states[-1]["evidence"][0]["source_provenance"]["source"] == row["source"]
    assert source.calls == 2 and authority.calls == 2
    assert runtime.read(result["id"]) == result
    result["trajectory"]["states"].clear()
    assert len(runtime.read(result["id"])["trajectory"]["states"]) == 2


@pytest.mark.parametrize("offsets", [(), (0,), (1, 7200), (0, 7199), (0, 7201), (0, 0, 7200),
    (0, 7200, 3600, 7200), (-1, 7200), (False, 7200), (0, 7200.0), tuple(range(513)) + (7200,)])
def test_invalid_or_unbounded_time_points_abstain(setup, offsets):
    def model(inputs, parameters, horizon):
        evaluation = synthetic_forecast(inputs, parameters, horizon)
        return replace(evaluation, points=tuple(ForecastPoint(offset, evaluation.points[0].evaluation) for offset in offsets))
    with pytest.raises(ModelExecutionError): setup[-1](model).execute(setup[1])


@pytest.mark.parametrize("case", ["wrong_type", "wrong_point", "wrong_metric", "out_of_bounds", "nan", "bool", "ood", "interval", "uncertainty", "assumptions", "too_many_assumptions"])
def test_every_point_and_aggregate_obeys_its_output_contract(setup, case):
    def model(inputs, parameters, horizon):
        value = synthetic_forecast(inputs, parameters, horizon)
        if case == "wrong_type": return value.points[0].evaluation
        if case == "wrong_point": return replace(value, points=(value.points[0], "not a point"))
        if case == "assumptions": return replace(value, assumptions=("x" * 2049,))
        if case == "too_many_assumptions": return replace(value, assumptions=("test",) * 65)
        if case == "uncertainty": return replace(value, uncertainty=dict(value.uncertainty, coverage=float("nan")))
        point = value.points[-1]
        metrics, uncertainty = deepcopy(point.evaluation.metrics), deepcopy(point.evaluation.uncertainty)
        if case == "wrong_metric": metrics["undeclared"] = 1
        elif case in ("out_of_bounds", "nan", "bool"):
            metrics["synthetic_shifted_value"] = {"out_of_bounds": 102, "nan": float("nan"), "bool": True}[case]
        elif case == "ood": uncertainty["out_of_distribution"] = True
        elif case == "interval": uncertainty["interval"] = {"lower": 3, "point": 2, "upper": 1}
        return replace(value, points=(value.points[0], replace(point, evaluation=ModelEvaluation(metrics, uncertainty))))
    with pytest.raises(ModelExecutionError): setup[-1](model).execute(setup[1])


@pytest.mark.parametrize("case", ["source", "revoked", "dependency", "expired"])
def test_revocation_during_execution_and_retained_read_abstains(setup, case):
    _, request, _, source, authority, clock, factory = setup
    def revoke():
        if case == "source": source.unavailable = True
        elif case == "revoked": authority.current = replace(authority.current, status="revoked")
        elif case == "dependency": authority.current = replace(authority.current, dependency_digests=())
        else: clock[0] = authority.current.valid_until
    runtime = factory()
    stored = runtime.execute(request)
    def model(inputs, parameters, horizon):
        value = synthetic_forecast(inputs, parameters, horizon)
        revoke()
        return value
    with pytest.raises(ModelExecutionError): factory(model).execute(request)
    with pytest.raises(ModelExecutionError): runtime.read(stored["id"])


def test_state_and_forecast_registrations_cannot_substitute_for_each_other(setup):
    contract, request, row, source, authority, clock, factory = setup
    request["horizon_seconds"] = 0
    with pytest.raises(ModelExecutionError): factory().execute(request)
    request["horizon_seconds"] = 3600
    with pytest.raises(ModelExecutionError): factory().execute(request)
    contract["prediction_horizon_seconds"] = [0]
    with pytest.raises(ModelExecutionError): factory()


def test_forecast_state_size_is_checked_before_accumulating_all_points(setup, monkeypatch):
    import openbody_ref.model_forecast as forecast
    monkeypatch.setattr(forecast, "MAX_FORECAST_STATE_BYTES", 1)
    runtime = setup[-1]()
    with pytest.raises(ModelExecutionError, match="size bound"): runtime.execute(setup[1])
    assert runtime._retained_bytes == 0


def test_unknown_point_uncertainty_cannot_be_quantified_by_the_aggregate(setup):
    contract, request, row, _, _, _, factory = setup
    row["uncertainty"] = {"epistemic": 0.2, "aleatoric": 0.2, "coverage": 0.8, "out_of_distribution": False, "reasons": ["Test fixture"]}
    def model(inputs, parameters, horizon):
        value = synthetic_forecast(inputs, parameters, horizon)
        point = value.points[-1]
        unknown = dict(point.evaluation.uncertainty, coverage=None)
        return replace(value, points=(value.points[0], replace(point, evaluation=replace(point.evaluation, uncertainty=unknown))))
    result = factory(model).execute(request)
    assert result["trajectory"]["uncertainty"]["coverage"] is None
    changed = deepcopy(result)
    changed["trajectory"]["uncertainty"] = deepcopy(row["uncertainty"])
    changed["trajectory"]["model_receipts"][0]["output_digest"] = canonical_digest(forecast_output(changed))
    with pytest.raises(ModelExecutionError): validate_forecast(changed, contract, row["subject"])


@pytest.mark.parametrize("case", ["subject", "horizon", "origin", "order", "point_time", "state_type", "producer", "value", "contract", "digest", "request", "current_state", "input", "evidence"])
def test_http_client_rejects_mismatched_or_tampered_forecasts(setup, case):
    contract, request, row, _, _, _, factory = setup
    result = factory().execute(request)
    trajectory = result["trajectory"]
    if case == "subject": result["subject"] = "subject:other"
    elif case == "horizon": result["horizon_seconds"] = 3600
    elif case == "origin": result["forecast_origin"] = trajectory["states"][-1]["state_time"]
    elif case == "order": trajectory["states"].reverse()
    elif case == "point_time": trajectory["states"][-1]["state_time"] = result["forecast_origin"]
    elif case == "state_type": trajectory["states"][-1] = row
    elif case == "producer": trajectory["states"][-1]["model_receipts"][0]["model_version"] = "other"
    elif case == "value": trajectory["states"][-1]["subsystems"][0]["state_vector"]["synthetic_shifted_value"] = 99
    elif case == "contract": result["contract_digest"] = "sha256:" + "f" * 64
    elif case == "digest": trajectory["model_receipts"][0]["output_digest"] = "sha256:" + "f" * 64
    elif case == "request": request["adaptation"] = {"offset": 1}
    elif case == "current_state": result = trajectory["states"][-1]
    elif case == "input": trajectory["states"][-1]["model_receipts"][0]["input_digest"] = "sha256:" + "f" * 64
    elif case == "evidence": trajectory["states"][-1]["evidence"][0]["content_digest"] = "sha256:" + "f" * 64
    with OpenBodyClient("http://forecast.test", httpx.MockTransport(lambda _: httpx.Response(200, json=result))) as client:
        with pytest.raises(Exception): client.execute_model(request, contract=contract)


def test_http_host_client_round_trip_and_revoked_forecast_read(setup):
    contract, request, row, _, authority, _, factory = setup
    api = TestClient(create_model_execution_host(factory()))
    def handle(request):
        response = api.request(request.method, request.url.raw_path.decode(), content=request.content, headers={"content-type": "application/json"})
        assert response.headers["cache-control"] == "no-store"
        return httpx.Response(response.status_code, content=response.content, headers=response.headers)
    assert "model-forecasts.execute" in api.get("/v1/capabilities").json()["capabilities"]
    with OpenBodyClient("http://forecast.test", httpx.MockTransport(handle)) as client:
        value = client.execute_model(request, contract=contract)
        assert value["kind"] == "ModelForecast"
        assert client.model_execution(value["id"], contract=contract, subject=row["subject"]) == value
        authority.current = replace(authority.current, status="revoked")
        assert client.model_execution(value["id"], contract=contract, subject=row["subject"])["kind"] == "Abstention"
