from __future__ import annotations

import json
from copy import deepcopy

import httpx
import pytest
from fastapi.testclient import TestClient

from openbody_ref.client import OpenBodyClient
from openbody_ref.host import ROOT, create_app
from openbody_ref.store import InMemoryTwinStore
from openbody_ref.validation import semantic_validate


def fixture() -> dict:
    return json.loads((ROOT / "examples" / "post-meal-walk.scenario.json").read_text())


def simulation_request(scenario: dict) -> dict:
    return {
        "state": scenario["baseline"]["states"][0],
        "perturbation": scenario["perturbation"],
        "horizon_seconds": scenario["applicability"]["horizon_seconds"],
        "requested_scopes": scenario["applicability"]["scopes"],
    }


def injected_store(scenario: dict) -> InMemoryTwinStore:
    store = InMemoryTwinStore.from_fixture(ROOT / "examples" / "post-meal-walk.scenario.json")
    store.state = scenario["baseline"]["states"][0]
    store.scenarios[scenario["id"]] = scenario
    return store


class TestSubjectClosure:
    def test_cross_subject_scenario_evidence_is_rejected(self) -> None:
        scenario = fixture()
        scenario["evidence"][0]["subject"] = "subject:other"
        with pytest.raises(ValueError, match="evidence subject"):
            semantic_validate(scenario)
        response = TestClient(create_app(injected_store(scenario))).post(
            "/v1/simulations", json=simulation_request(scenario)
        )
        assert response.status_code == 200
        assert response.json()["reason_code"] == "insufficient_evidence"


class TestScopeClosure:
    def test_scenario_evidence_cannot_add_unrequested_scope(self) -> None:
        scenario = fixture()
        scenario["evidence"][0]["scopes"].append("ob://human/cardiovascular/heart")
        with pytest.raises(ValueError, match="output scopes"):
            semantic_validate(scenario)
        response = TestClient(create_app(injected_store(scenario))).post(
            "/v1/simulations", json=simulation_request(scenario)
        )
        assert response.status_code == 200
        assert response.json()["reason_code"] == "insufficient_validation"


class TestTemporalClosure:
    def test_expired_baseline_abstains(self) -> None:
        scenario = fixture()
        scenario["baseline"]["states"][0]["valid_until"] = "2026-08-10T07:00:00Z"
        response = TestClient(create_app(injected_store(scenario))).post(
            "/v1/simulations", json=simulation_request(scenario)
        )
        assert response.status_code == 200
        assert response.json()["reason_code"] == "stale_evidence"

    def test_impossible_state_validity_interval_is_rejected(self) -> None:
        state = deepcopy(fixture()["counterfactual"]["states"][0])
        state["valid_until"] = "2000-01-01T00:00:00Z"
        with pytest.raises(ValueError, match="valid_until"):
            semantic_validate(state)


class TestReceiptModelClosure:
    def test_baseline_trajectory_only_receipt_is_discoverable(self, tmp_path) -> None:
        scenario = fixture()
        receipt = deepcopy(scenario["model_receipts"][0])
        receipt["model_id"] = "baseline-only-property-model"
        receipt["execution_id"] = "exec-baseline-property"
        scenario["baseline"]["model_receipts"].append(receipt)
        scenario["evidence"][0]["model_refs"].append(receipt["model_id"])
        path = tmp_path / "baseline-only.json"
        path.write_text(json.dumps(scenario))
        store = InMemoryTwinStore.from_fixture(path)
        descriptor = store.models[receipt["model_id"]]
        assert (descriptor["version"], descriptor["family"]) == (
            receipt["model_version"],
            receipt["family"],
        )

    def test_counterfactual_subsystem_receipt_has_counterfactual_role(self, tmp_path) -> None:
        scenario = fixture()
        receipt = deepcopy(scenario["counterfactual"]["states"][0]["subsystems"][0]["model_receipt"])
        receipt["model_id"] = "counterfactual-subsystem-property-model"
        receipt["execution_id"] = "exec-counterfactual-subsystem-property"
        scenario["counterfactual"]["states"][0]["subsystems"][0]["model_receipt"] = receipt
        scenario["evidence"][0]["model_refs"].append(receipt["model_id"])
        path = tmp_path / "counterfactual-subsystem.json"
        path.write_text(json.dumps(scenario))
        descriptor = InMemoryTwinStore.from_fixture(path).models[receipt["model_id"]]
        assert "counterfactual" in descriptor["capabilities"]

    def test_empty_model_capability_and_scope_fail_closed(self) -> None:
        scenario = fixture()
        store = injected_store(scenario)
        for model in store.models.values():
            model["capabilities"] = []
            model["scopes"] = []
        response = TestClient(create_app(store)).post("/v1/simulations", json=simulation_request(scenario))
        assert response.status_code == 200
        assert response.json()["reason_code"] == "insufficient_validation"


class TestEvidenceClosure:
    def test_short_digest_is_rejected(self) -> None:
        scenario = fixture()
        scenario["evidence"][0]["content_digest"] = "sha256:a"
        with pytest.raises(Exception):
            semantic_validate(scenario)


class TestRequestResponseClosure:
    def test_internally_valid_cross_subject_response_is_rejected(self) -> None:
        request_scenario = fixture()
        response_scenario = deepcopy(request_scenario)
        response_scenario["subject"] = "subject:other"
        response_scenario["applicability"]["subject"] = "subject:other"
        response_scenario["evidence"][0]["subject"] = "subject:other"
        for trajectory_name in ("baseline", "counterfactual"):
            for state in response_scenario[trajectory_name]["states"]:
                state["subject"] = "subject:other"

        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=response_scenario)

        with OpenBodyClient("http://openbody.test", transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(ValueError, match="response subject"):
                client.simulate(
                    request_scenario["baseline"]["states"][0],
                    request_scenario["perturbation"],
                    request_scenario["applicability"]["horizon_seconds"],
                    request_scenario["applicability"]["scopes"],
                )


class TestAuthorityClosure:
    def test_embedded_perturbation_authority_abstains(self) -> None:
        scenario = fixture()
        scenario["perturbation"]["authority_ref"] = "authority:opaque-unverified"
        response = TestClient(create_app(injected_store(scenario))).post(
            "/v1/simulations", json=simulation_request(scenario)
        )
        assert response.status_code == 200
        assert response.json()["reason_code"] == "authorization_required"


class TestOutcomeCalibrationLineageClosure:
    def test_poisoned_scenario_cannot_extend_outcome_window(self) -> None:
        scenario = fixture()
        scenario["counterfactual"]["states"][-1]["state_time"] = "2099-01-01T00:00:00Z"
        store = injected_store(scenario)
        outcome = {
            "schema_version": "0.1",
            "kind": "ObservedOutcome",
            "id": "outcome-poisoned-window",
            "subject": scenario["subject"],
            "perturbation_id": scenario["perturbation"]["id"],
            "started_at": "2098-12-31T23:00:00Z",
            "ended_at": "2099-01-01T00:00:00Z",
            "observed_effects": [scenario["expected_effects"][0]],
            "evidence": [],
        }
        response = TestClient(create_app(store)).post("/v1/outcomes", json=outcome)
        assert response.status_code == 422

    def test_calibration_cannot_cross_metric_scope_lineage(self) -> None:
        scenario = fixture()
        client = TestClient(create_app())
        outcome = {
            "schema_version": "0.1",
            "kind": "ObservedOutcome",
            "id": "outcome-invariant-calibration",
            "subject": scenario["subject"],
            "perturbation_id": scenario["perturbation"]["id"],
            "started_at": scenario["perturbation"]["starts_at"],
            "ended_at": scenario["perturbation"]["ends_at"],
            "observed_effects": [scenario["expected_effects"][0]],
            "evidence": [],
        }
        assert client.post("/v1/outcomes", json=outcome).status_code == 202
        calibration = {
            "schema_version": "0.1",
            "kind": "CalibrationEvent",
            "id": "calibration-invariant-mismatch",
            "scenario_id": scenario["id"],
            "outcome_id": outcome["id"],
            "generated_at": "2026-08-10T21:00:00Z",
            "absolute_errors": {"unrelated_metric": 1.0},
            "within_predicted_interval": {"unrelated_metric": True},
        }
        assert client.post("/v1/calibrations", json=calibration).status_code == 422
