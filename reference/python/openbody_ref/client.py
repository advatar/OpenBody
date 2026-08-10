from __future__ import annotations

from typing import Any

import httpx

from .validation import semantic_validate


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
        return response.json()

    def simulation(self, scenario_id: str) -> dict[str, Any]:
        response = self._client.get(f"/v1/simulations/{scenario_id}")
        response.raise_for_status()
        value = response.json()
        semantic_validate(value)
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
