from __future__ import annotations

from typing import Any

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
