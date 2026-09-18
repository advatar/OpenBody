from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
import hashlib
import inspect

import httpx
import pytest
from fastapi.testclient import TestClient

from test_model_family import setup as state_setup
from test_model_forecast import setup as forecast_setup, synthetic_forecast
from openbody_ref.client import OpenBodyClient
from openbody_ref.host import create_model_execution_host
from openbody_ref.model_family import (CounterfactualEvaluation, CounterfactualModelRegistration,
    ForecastPoint, ModelEvaluation, ModelExecutionError, QualifiedModelRuntime, validate_contract)
from openbody_ref.model_counterfactual import counterfactual_output, validate_counterfactual
from openbody_ref.validation import canonical_digest, semantic_validate


def synthetic_counterfactual(inputs, parameters, perturbation, horizon):
    """Software arithmetic only; this fixture asserts no clinical causal effect."""
    control = synthetic_forecast(inputs, parameters, horizon)
    point = control.points[-1]
    metrics = {"synthetic_shifted_value": point.evaluation.metrics["synthetic_shifted_value"] - perturbation["parameters"]["dose"]}
    intervention = replace(control, points=(control.points[0], replace(point, evaluation=replace(point.evaluation, metrics=metrics))))
    return CounterfactualEvaluation(control, intervention, {"synthetic_shifted_value": control.uncertainty},
        control.uncertainty, ("Synthetic software test only; no clinical efficacy claim",))


@pytest.fixture
def setup(forecast_setup):
    contract, request, row, source, authority, clock, _ = forecast_setup
    artifact = inspect.getsource(synthetic_counterfactual).encode()
    contract["model"]["artifact_digest"] = "sha256:" + hashlib.sha256(artifact).hexdigest()
    contract["counterfactual"] = {"start_timing": "execution_time", "perturbations": [{"id": "test-dose", "class": "research",
        "scope": contract["model"]["coordinate"], "parameters": [{"name": "dose", "unit": "test_unit", "minimum": 0, "maximum": 2}]}],
        "effect_bounds": [{"name": "synthetic_shifted_value", "minimum": -2, "maximum": 0}]}
    request["perturbation"] = {"id": "test-dose", "parameters": {"dose": 1}}
    authority.current = replace(authority.current, contract_digest=canonical_digest(contract), artifact_digest=contract["model"]["artifact_digest"])
    def factory(evaluate=synthetic_counterfactual):
        return QualifiedModelRuntime(row["subject"], row["source"]["clinical_version"]["tenant_id"], source, authority,
            [CounterfactualModelRegistration(contract, artifact, evaluate)], clock=lambda: clock[0])
    return contract, request, row, source, authority, clock, factory


def test_actual_counterfactual_compares_control_at_same_horizon_without_action_authority(setup):
    contract, request, row, source, authority, _, factory = setup
    calls = []
    def model(inputs, parameters, perturbation, horizon):
        calls.append(deepcopy(perturbation))
        return synthetic_counterfactual(inputs, parameters, perturbation, horizon)
    runtime = factory(model)
    result = runtime.execute(request)
    assert result["kind"] == "ModelCounterfactual"
    scenario = result["scenario"]
    semantic_validate(scenario)
    assert scenario["disposition"] == "simulated" and scenario["kind"] == "CounterfactualScenario"
    assert scenario["counterfactual"]["states"][-1]["subsystems"][0]["state_vector"]["synthetic_shifted_value"] == 37
    assert result["comparison_forecast"]["trajectory"]["states"][-1]["subsystems"][0]["state_vector"]["synthetic_shifted_value"] == 38
    # Current baseline is also 37; subtracting it would incorrectly report zero.
    assert scenario["expected_effects"][0]["delta"] == -1
    assert scenario["expected_effects"][0]["epistemic_class"] == "counterfactual"
    assert scenario["uncertainty"]["coverage"] is None
    assert scenario["expected_effects"][0]["uncertainty"]["out_of_distribution"] == "unknown"
    assert calls == [scenario["perturbation"]] and "authority_ref" not in calls[0]
    assert result["execution_context"]["purpose"] == "software_test"
    assert scenario["model_receipts"][0]["output_digest"] == canonical_digest(counterfactual_output(result))
    assert source.calls == 2 and authority.calls == 2
    assert runtime.read(result["id"]) == result
    result["scenario"]["expected_effects"].clear()
    assert len(runtime.read(result["id"])["scenario"]["expected_effects"]) == 1


@pytest.mark.parametrize("case", ["missing", "unknown", "extra", "negative", "large", "nan", "bool", "authority", "scope", "time", "class"])
def test_only_exact_qualified_perturbations_reach_the_model(setup, case):
    _, request, _, _, _, _, factory = setup
    calls = []
    def model(*args): calls.append(args); return synthetic_counterfactual(*args)
    perturbation = request["perturbation"]
    if case == "missing": perturbation["parameters"] = {}
    elif case == "unknown": perturbation["id"] = "unqualified-dose"
    elif case == "extra": perturbation["parameters"]["other"] = 1
    elif case in ("negative", "large", "nan", "bool"):
        perturbation["parameters"]["dose"] = {"negative": -1, "large": 3, "nan": float("nan"), "bool": True}[case]
    else: perturbation[{"authority": "authority_ref", "scope": "scope", "time": "starts_at", "class": "class"}[case]] = "untrusted"
    with pytest.raises(ModelExecutionError): factory(model).execute(request)
    assert calls == []


@pytest.mark.parametrize("case", ["scope", "duplicate", "parameters", "effects", "bounds", "timing"])
def test_counterfactual_contract_must_define_unambiguous_bounds(setup, case):
    contract = setup[0]
    boundary = contract["counterfactual"]
    if case == "scope": boundary["perturbations"][0]["scope"] = "ob://human/cardiovascular"
    elif case == "duplicate": boundary["perturbations"] *= 2
    elif case == "parameters": boundary["perturbations"][0]["parameters"] *= 2
    elif case == "effects": boundary["effect_bounds"][0]["name"] = "other"
    elif case == "bounds": boundary["effect_bounds"][0]["minimum"] = 3
    else: boundary["start_timing"] = "caller_supplied"
    with pytest.raises(ModelExecutionError): validate_contract(contract)


@pytest.mark.parametrize("case", ["wrong_type", "baseline", "grid", "effect", "uncertainty", "effect_uncertainty", "assumptions"])
def test_model_cannot_emit_unbounded_or_inconsistent_comparisons(setup, case):
    def model(*args):
        value = synthetic_counterfactual(*args)
        if case == "wrong_type": return value.control
        if case == "uncertainty": return replace(value, uncertainty=dict(value.uncertainty, out_of_distribution=True))
        if case == "effect_uncertainty": return replace(value, effect_uncertainty={})
        if case == "assumptions": return replace(value, assumptions=("x" * 2049,))
        arm = value.intervention
        if case == "grid": arm = replace(arm, points=(arm.points[0], ForecastPoint(3600, arm.points[0].evaluation), arm.points[-1]))
        else:
            index = 0 if case == "baseline" else -1
            point = arm.points[index]
            changed = replace(point, evaluation=replace(point.evaluation, metrics={"synthetic_shifted_value": 40}))
            arm = replace(arm, points=(changed, arm.points[-1]) if index == 0 else (arm.points[0], changed))
        return replace(value, intervention=arm)
    with pytest.raises(ModelExecutionError): setup[-1](model).execute(setup[1])


@pytest.mark.parametrize("case", ["source", "qualification", "dependency", "expiry"])
def test_revocation_during_comparison_invalidates_new_and_retained_results(setup, case):
    _, request, _, source, authority, clock, factory = setup
    runtime = factory(); retained = runtime.execute(request)
    def model(*args):
        value = synthetic_counterfactual(*args)
        if case == "source": source.unavailable = True
        elif case == "qualification": authority.current = replace(authority.current, status="revoked")
        elif case == "dependency": authority.current = replace(authority.current, dependency_digests=())
        else: clock[0] = authority.current.valid_until
        return value
    with pytest.raises(ModelExecutionError): factory(model).execute(request)
    with pytest.raises(ModelExecutionError): runtime.read(retained["id"])


@pytest.mark.parametrize("case", ["effect", "authority", "perturbation", "scope", "time", "role", "subject", "horizon", "context", "generalizable", "baseline", "forecast_only"])
def test_client_rejects_tampered_comparisons_even_with_recomputed_aggregate_digest(setup, case):
    contract, request, row, _, _, _, factory = setup
    result = factory().execute(request)
    scenario = result["scenario"]
    if case == "effect": scenario["expected_effects"][0]["delta"] = 0
    elif case == "authority": scenario["perturbation"]["authority_ref"] = "urn:forged:authority"
    elif case == "perturbation": scenario["perturbation"]["parameters"]["dose"] = 2
    elif case == "scope": scenario["perturbation"]["scope"] = "ob://human/cardiovascular"
    elif case == "time": scenario["perturbation"]["starts_at"] = "2020-01-01T00:00:00Z"
    elif case == "role": scenario["counterfactual"]["trajectory_kind"] = "observed"
    elif case == "subject": result["subject"] = "subject:other"
    elif case == "horizon": result["horizon_seconds"] = 3600
    elif case == "context": result["execution_context"]["purpose"] = "clinical_decision_support"
    elif case == "generalizable": scenario["applicability"]["generalizable"] = True
    elif case == "baseline": scenario["baseline"]["states"] = result["comparison_forecast"]["trajectory"]["states"]
    scenario["model_receipts"][0]["output_digest"] = canonical_digest(counterfactual_output(result))
    if case == "forecast_only": result = result["comparison_forecast"]
    with OpenBodyClient("http://counterfactual.test", httpx.MockTransport(lambda _: httpx.Response(200, json=result))) as client:
        with pytest.raises(Exception): client.execute_model(request, contract=contract)


def test_http_host_client_executes_and_revalidates_the_counterfactual(setup):
    contract, request, row, _, authority, _, factory = setup
    api = TestClient(create_model_execution_host(factory()))
    def handle(request):
        response = api.request(request.method, request.url.raw_path.decode(), content=request.content, headers={"content-type": "application/json"})
        assert response.headers["cache-control"] == "no-store"
        return httpx.Response(response.status_code, content=response.content, headers=response.headers)
    with OpenBodyClient("http://counterfactual.test", httpx.MockTransport(handle)) as client:
        result = client.execute_model(request, contract=contract)
        assert result["scenario"]["expected_effects"][0]["delta"] == -1
        assert client.model_execution(result["id"], subject=row["subject"], contract=contract) == result
        authority.current = replace(authority.current, status="revoked")
        assert client.model_execution(result["id"], subject=row["subject"], contract=contract)["kind"] == "Abstention"
