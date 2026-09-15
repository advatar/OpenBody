from __future__ import annotations

from typing import Any
from urllib.parse import quote

from .observation import validate_locator, validate_observation

import httpx

from .validation import canonical_digest, counterfactual_output_scopes, semantic_validate, validate_definition


class OpenBodyClient:
    def __init__(self, base_url: str, transport: httpx.BaseTransport | None = None) -> None:
        self._client = httpx.Client(base_url=base_url.rstrip("/"), transport=transport, timeout=10.0)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "OpenBodyClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def capabilities(self) -> dict[str, Any]:
        response = self._client.get("/v1/capabilities")
        response.raise_for_status()
        return response.json()

    def model_families(self) -> list[dict[str, Any]]:
        from .model_family import validate_contract
        response = self._client.get("/v1/model-families")
        response.raise_for_status()
        values = response.json()
        if not isinstance(values, list):
            raise ValueError("model-family discovery must return an array")
        for value in values:
            validate_contract(value)
        return values

    def execute_model(self, request: dict[str, Any], *, contract: dict[str, Any]) -> dict[str, Any]:
        from .model_family import REQUEST_VALIDATOR, validate_contract
        validate_contract(contract)
        REQUEST_VALIDATOR.validate(request)
        if request["model_id"] != contract["model"]["id"]:
            raise ValueError("requested model differs from pinned contract")
        response = self._client.post("/v1/model-executions", json=request)
        response.raise_for_status()
        value = self._checked_model_result(response.json(), contract, request["subject"], request=request)
        return value

    def model_execution(self, execution_id: str, *, subject: str, contract: dict[str, Any]) -> dict[str, Any]:
        from .model_family import validate_contract
        validate_contract(contract)
        response = self._client.get(f"/v1/model-executions/{quote(execution_id, safe='')}")
        response.raise_for_status()
        value = self._checked_model_result(response.json(), contract, subject)
        if value["kind"] != "Abstention" and value["id"] != execution_id:
            raise ValueError("model result identity differs from requested execution")
        return value

    @staticmethod
    def _checked_model_result(value, contract, subject, *, request=None):
        if value.get("kind") == "ModelForecast":
            from .model_forecast import validate_forecast
            return validate_forecast(value, contract, subject, request=request)
        if value.get("kind") != "Abstention" and (contract["prediction_horizon_seconds"] != [0] or
                                                 request is not None and request["horizon_seconds"] != 0):
            raise ValueError("a nonzero forecast cannot be returned as current state")
        return OpenBodyClient._checked_model_state(value, contract, subject)

    @staticmethod
    def _checked_model_state(value: dict[str, Any], contract: dict[str, Any], subject: str) -> dict[str, Any]:
        if value.get("kind") == "Abstention":
            validate_definition("Abstention", value)
            return value
        validate_definition("BodyState", value)
        semantic_validate(value)
        if value["subject"] != subject or len(value["subsystems"]) != 1 or value["couplings"] or len(value["model_receipts"]) != 1:
            raise ValueError("model result exceeds the requested state boundary")
        subsystem, receipt = value["subsystems"][0], value["model_receipts"][0]
        model = contract["model"]
        if subsystem["coordinate"] != model["coordinate"] or subsystem["model_receipt"] != receipt:
            raise ValueError("model result scope or receipt differs from contract")
        from .model_family import finite
        bounds = {row["name"]: row for row in contract["behavioral_envelope"]}
        vector = subsystem["state_vector"]
        if set(vector) != set(bounds) or any(not finite(number) or not bounds[name]["minimum"] <= number <= bounds[name]["maximum"] for name, number in vector.items()):
            raise ValueError("model result values exceed the contract envelope")
        if subsystem["uncertainty"] != value["uncertainty"] or subsystem["evidence"] != value["evidence"]:
            raise ValueError("model result evidence or uncertainty disagrees across placements")
        if any(receipt[key] != model[name] for key, name in (("model_id", "id"), ("model_version", "version"), ("family", "family"))):
            raise ValueError("model result producer differs from contract")
        if receipt["environment_digest"] != canonical_digest(contract) or receipt["execution_id"] != value["id"]:
            raise ValueError("model result is not bound to its contract and execution")
        if receipt["output_digest"] != canonical_digest({"state_vector": subsystem["state_vector"], "uncertainty": value["uncertainty"]}):
            raise ValueError("model result output digest differs from its values")
        return value

    def ingest_observation(self, locator: dict[str, str]) -> dict[str, Any]:
        validate_locator(locator)
        response = self._client.post("/v1/observations", json=locator)
        response.raise_for_status()
        value = response.json()
        validate_observation(value, subject=f"subject:providehr:ehr:{locator['ehr_id']}")
        if value["source"]["clinical_version"] != locator:
            raise ValueError("observation response source does not match request")
        return value

    def observation(self, observation_id: str, *, subject: str) -> dict[str, Any]:
        response = self._client.get(f"/v1/observations/{quote(observation_id, safe='')}")
        response.raise_for_status()
        value = response.json()
        validate_observation(value, subject=subject)
        if value["id"] != observation_id:
            raise ValueError("observation response identity does not match request")
        return value

    def state(self) -> dict[str, Any]:
        response = self._client.get("/v1/state")
        response.raise_for_status()
        value = response.json()
        semantic_validate(value)
        return value

    def subsystem_state(self, coordinate: str) -> dict[str, Any]:
        encoded = coordinate.removeprefix("ob://")
        response = self._client.get(f"/v1/state/{encoded}")
        response.raise_for_status()
        value = response.json()
        validate_definition("BodySubsystemState", value)
        return value

    def simulation(self, scenario_id: str) -> dict[str, Any]:
        response = self._client.get(f"/v1/simulations/{scenario_id}")
        response.raise_for_status()
        value = response.json()
        semantic_validate(value)
        return value

    def simulate(
        self,
        state: dict[str, Any],
        perturbation: dict[str, Any],
        horizon_seconds: int,
        requested_scopes: list[str],
        authority_ref: str | None = None,
    ) -> dict[str, Any]:
        semantic_validate(state)
        validate_definition("Perturbation", perturbation)
        if not requested_scopes or len(requested_scopes) != len(set(requested_scopes)):
            raise ValueError("requested_scopes must be non-empty and unique")
        for scope in requested_scopes:
            validate_definition("Coordinate", scope)
        payload = {
            "state": state,
            "perturbation": perturbation,
            "horizon_seconds": horizon_seconds,
            "requested_scopes": requested_scopes,
            "authority_ref": authority_ref,
        }
        response = self._client.post("/v1/simulations", json=payload)
        response.raise_for_status()
        value = response.json()
        semantic_validate(value)
        if value.get("kind") == "CounterfactualScenario" and value.get("disposition") == "simulated":
            if value["subject"] != state["subject"]:
                raise ValueError("simulation response subject does not match request")
            if canonical_digest(value["baseline"]["states"]) != canonical_digest([state]):
                raise ValueError("simulation response baseline does not match request state")
            if value["perturbation"] != perturbation:
                raise ValueError("simulation response perturbation does not match request")
            if value["applicability"]["horizon_seconds"] != horizon_seconds:
                raise ValueError("simulation response horizon does not match request")
            requested_scope_set = set(requested_scopes)
            if set(value["applicability"]["scopes"]) != requested_scope_set:
                raise ValueError("simulation response applicability scopes do not match request")
            if counterfactual_output_scopes(value) != requested_scope_set:
                raise ValueError("simulation response contains unrequested output scopes")
        return value

    def record_outcome(self, outcome: dict[str, Any]) -> dict[str, Any]:
        semantic_validate(outcome)
        response = self._client.post("/v1/outcomes", json=outcome)
        response.raise_for_status()
        value = response.json()
        semantic_validate(value)
        return value

    def record_calibration(self, calibration: dict[str, Any]) -> dict[str, Any]:
        semantic_validate(calibration)
        response = self._client.post("/v1/calibrations", json=calibration)
        response.raise_for_status()
        value = response.json()
        semantic_validate(value)
        return value
