from __future__ import annotations

import json
from copy import deepcopy

import httpx
import pytest
from fastapi.testclient import TestClient

from openbody_ref.client import OpenBodyClient
from openbody_ref.host import ROOT, create_app
from openbody_ref.store import InMemoryTwinStore
from openbody_ref.validation import scenario_evidence_references, semantic_validate


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

    def test_nested_cross_subject_undigested_evidence_is_rejected(self) -> None:
        scenario = fixture()
        scenario["counterfactual"]["states"][0]["evidence"].append(
            {
                "id": "nested-hostile-evidence",
                "scheme": "openbody",
                "canonical_ref": "openbody:evidence:nested-hostile",
                "source_provenance": {"source": "hostile-provider"},
                "authorization_ref": None,
                "subject": "subject:other",
            }
        )
        with pytest.raises(ValueError, match="evidence"):
            semantic_validate(scenario)


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

    def test_baseline_cannot_start_after_perturbation(self) -> None:
        scenario = fixture()
        baseline = scenario["baseline"]["states"][0]
        baseline["state_time"] = "2026-08-10T19:00:00Z"
        baseline["valid_until"] = "2026-08-10T21:00:00Z"
        response = TestClient(create_app(injected_store(scenario))).post(
            "/v1/simulations", json=simulation_request(scenario)
        )
        assert response.status_code == 200
        assert response.json()["reason_code"] == "stale_evidence"

    def test_baseline_instant_comparison_normalizes_offsets(self) -> None:
        scenario = fixture()
        baseline = scenario["baseline"]["states"][0]
        baseline["state_time"] = "2026-08-10T20:05:00+02:00"
        baseline["valid_until"] = "2026-08-10T20:15:00+02:00"
        scenario["perturbation"]["starts_at"] = "2026-08-10T18:05:00Z"
        semantic_validate(scenario)

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

    def test_scope_less_nested_producer_fails_closed(self, tmp_path) -> None:
        scenario = fixture()
        state = scenario["counterfactual"]["states"][0]
        receipt = deepcopy(scenario["model_receipts"][0])
        receipt["model_id"] = "scope-less-counterfactual-producer"
        receipt["execution_id"] = "exec-scope-less-counterfactual"
        state["subsystems"] = []
        state["couplings"] = []
        state["model_receipts"] = [receipt]
        scenario["evidence"][0]["model_refs"].append(receipt["model_id"])
        path = tmp_path / "scope-less-producer.json"
        path.write_text(json.dumps(scenario))
        with pytest.raises(ValueError, match="scope"):
            InMemoryTwinStore.from_fixture(path)

    def test_scope_less_trajectory_producer_fails_semantic_validation(self) -> None:
        scenario = fixture()
        for state in scenario["counterfactual"]["states"]:
            state["subsystems"] = []
            state["couplings"] = []
            state["model_receipts"] = []
        with pytest.raises(ValueError, match="scope"):
            semantic_validate(scenario)

    def test_wrong_scope_descriptor_for_nested_producer_fails_closed(self) -> None:
        scenario = fixture()
        store = injected_store(scenario)
        store.models["twin-state-metabolic"]["scopes"] = ["ob://human/cardiovascular/heart"]
        response = TestClient(create_app(store)).post("/v1/simulations", json=simulation_request(scenario))
        assert response.status_code == 200
        assert response.json()["reason_code"] == "unsupported_scope"

    def test_model_applicability_must_match_subject_and_receipt_scopes(self) -> None:
        scenario = fixture()
        store = injected_store(scenario)
        for model in store.models.values():
            model["applicability"] = deepcopy(model["applicability"])
            model["applicability"]["subject"] = "subject:other"
            model["applicability"]["scopes"] = ["ob://human/cardiovascular/heart"]
        response = TestClient(create_app(store)).post("/v1/simulations", json=simulation_request(scenario))
        assert response.status_code == 200
        assert response.json()["reason_code"] == "insufficient_validation"


class TestEvidenceClosure:
    def test_short_digest_is_rejected(self) -> None:
        scenario = fixture()
        scenario["evidence"][0]["content_digest"] = "sha256:a"
        with pytest.raises(Exception):
            semantic_validate(scenario)

    def test_nested_evidence_must_bind_its_exact_producer(self) -> None:
        scenario = fixture()
        nested_evidence = scenario["baseline"]["states"][0]["subsystems"][0]["evidence"][0]
        nested_evidence["model_refs"] = [scenario["model_receipts"][0]["model_id"]]
        with pytest.raises(ValueError, match="placement producer"):
            semantic_validate(scenario)

    def test_state_evidence_must_bind_producer_for_claimed_scope(self) -> None:
        scenario = fixture()
        state = scenario["counterfactual"]["states"][0]
        cardiovascular = deepcopy(state["subsystems"][0])
        cardiovascular["coordinate"] = "ob://human/cardiovascular/heart"
        cardiovascular["model_receipt"]["model_id"] = "cardiovascular-counterfactual-model"
        cardiovascular["model_receipt"]["execution_id"] = "exec-cardiovascular-counterfactual"
        state["subsystems"].append(cardiovascular)
        scenario["applicability"]["scopes"].append(cardiovascular["coordinate"])
        scenario["evidence"][0]["scopes"].append(cardiovascular["coordinate"])
        scenario["evidence"][0]["model_refs"].append(cardiovascular["model_receipt"]["model_id"])
        state_evidence = deepcopy(scenario["evidence"][0])
        state_evidence["id"] = "evidence-state-wrong-scope-producer"
        state_evidence["scopes"] = ["ob://human/metabolic/glucose_regulation"]
        state_evidence["model_refs"] = [cardiovascular["model_receipt"]["model_id"]]
        state["evidence"].append(state_evidence)
        with pytest.raises(ValueError, match="placement producer"):
            semantic_validate(scenario)


class TestRequestResponseClosure:
    def test_internally_valid_cross_subject_response_is_rejected(self) -> None:
        request_scenario = fixture()
        response_scenario = deepcopy(request_scenario)
        response_scenario["subject"] = "subject:other"
        response_scenario["applicability"]["subject"] = "subject:other"
        for reference in scenario_evidence_references(response_scenario):
            reference["subject"] = "subject:other"
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

    @pytest.mark.parametrize("mutation", ["subsystem", "state_vector", "uncertainty", "evidence", "model_receipt"])
    def test_returned_baseline_must_equal_requested_state(self, mutation: str) -> None:
        request_scenario = fixture()
        response_scenario = deepcopy(request_scenario)
        baseline = response_scenario["baseline"]["states"][0]
        if mutation == "subsystem":
            subsystem = deepcopy(baseline["subsystems"][0])
            baseline["subsystems"].append(subsystem)
        elif mutation == "state_vector":
            baseline["subsystems"][0]["state_vector"]["glucose_recovery_minutes"] += 1
        elif mutation == "uncertainty":
            baseline["uncertainty"]["epistemic"] = 0.21
        elif mutation == "evidence":
            baseline["evidence"].append(deepcopy(baseline["subsystems"][0]["evidence"][0]))
        else:
            baseline["subsystems"][0]["model_receipt"]["execution_id"] = "exec-altered-baseline"

        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=response_scenario)

        with OpenBodyClient("http://openbody.test", transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(ValueError, match="baseline"):
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

    def test_calibration_revalidates_stored_outcome_window(self) -> None:
        scenario = fixture()
        store = InMemoryTwinStore.from_fixture(ROOT / "examples" / "post-meal-walk.scenario.json")
        outcome = {
            "schema_version": "0.1",
            "kind": "ObservedOutcome",
            "id": "outcome-poisoned-calibration-window",
            "subject": scenario["subject"],
            "perturbation_id": scenario["perturbation"]["id"],
            "started_at": scenario["perturbation"]["starts_at"],
            "ended_at": scenario["perturbation"]["ends_at"],
            "observed_effects": [scenario["expected_effects"][0]],
            "evidence": [],
        }
        store.put_outcome(outcome)
        store.outcomes[outcome["id"]]["started_at"] = "2099-01-01T00:00:00Z"
        store.outcomes[outcome["id"]]["ended_at"] = "2099-01-01T01:00:00Z"
        calibration = {
            "schema_version": "0.1",
            "kind": "CalibrationEvent",
            "id": "calibration-poisoned-outcome-window",
            "scenario_id": scenario["id"],
            "outcome_id": outcome["id"],
            "generated_at": "2099-01-01T02:00:00Z",
            "absolute_errors": {scenario["expected_effects"][0]["metric"]: 1.0},
            "within_predicted_interval": {scenario["expected_effects"][0]["metric"]: True},
        }
        response = TestClient(create_app(store)).post("/v1/calibrations", json=calibration)
        assert response.status_code == 422

    def test_calibration_rejects_foreign_subject_store_lineage(self) -> None:
        scenario = fixture()
        store = InMemoryTwinStore.from_fixture(ROOT / "examples" / "post-meal-walk.scenario.json")
        foreign_scenario = deepcopy(scenario)
        foreign_scenario["subject"] = "subject:other"
        foreign_scenario["applicability"]["subject"] = "subject:other"
        for reference in scenario_evidence_references(foreign_scenario):
            reference["subject"] = "subject:other"
        for trajectory_name in ("baseline", "counterfactual"):
            for state in foreign_scenario[trajectory_name]["states"]:
                state["subject"] = "subject:other"
        foreign_outcome = {
            "schema_version": "0.1",
            "kind": "ObservedOutcome",
            "id": "outcome-foreign-subject-calibration",
            "subject": "subject:other",
            "perturbation_id": foreign_scenario["perturbation"]["id"],
            "started_at": foreign_scenario["perturbation"]["starts_at"],
            "ended_at": foreign_scenario["perturbation"]["ends_at"],
            "observed_effects": [foreign_scenario["expected_effects"][0]],
            "evidence": [],
        }
        store.scenarios[foreign_scenario["id"]] = foreign_scenario
        store.outcomes[foreign_outcome["id"]] = foreign_outcome
        calibration = {
            "schema_version": "0.1",
            "kind": "CalibrationEvent",
            "id": "calibration-foreign-subject",
            "scenario_id": foreign_scenario["id"],
            "outcome_id": foreign_outcome["id"],
            "generated_at": "2026-08-10T21:00:00Z",
            "absolute_errors": {foreign_scenario["expected_effects"][0]["metric"]: 1.0},
            "within_predicted_interval": {foreign_scenario["expected_effects"][0]["metric"]: True},
        }
        response = TestClient(create_app(store)).post("/v1/calibrations", json=calibration)
        assert response.status_code == 422
