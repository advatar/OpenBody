from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from .demo_composition import DemoCompositionError, compose
from .demo_counterfactual import DemoCounterfactualError, simulate
from .durable_store import DurableTwinStore
from .host import DEFAULT_FIXTURE, create_app


STORE_PATH = Path(os.environ.get("OPENBODY_STORE_PATH", "/var/lib/openbody/twin-store.json"))
FIXTURE_PATH = Path(os.environ.get("OPENBODY_FIXTURE_PATH", str(DEFAULT_FIXTURE)))
COUNTERFACTUAL_FIXTURE_PATH = Path(
    os.environ.get(
        "OPENBODY_COUNTERFACTUAL_FIXTURE_PATH",
        "/srv/openbody/examples/post-meal-walk.scenario.json",
    )
)

store = DurableTwinStore.open(STORE_PATH, FIXTURE_PATH)
app = create_app(store=store)


@app.post("/v1/demo/compose")
def compose_demo_state(request: dict[str, Any]) -> dict[str, Any]:
    """Compose only receipt-bound outputs; defects become a visible abstention."""

    try:
        return compose(request)
    except DemoCompositionError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/v1/demo/counterfactual")
def run_demo_counterfactual(request: dict[str, Any]) -> dict[str, Any]:
    """Replay the exact qualified 7,200-second OpenBody fixture."""

    try:
        return simulate(request, COUNTERFACTUAL_FIXTURE_PATH)
    except (DemoCounterfactualError, OSError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
