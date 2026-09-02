from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from .demo_composition import DemoCompositionError, compose
from .durable_store import DurableTwinStore
from .host import DEFAULT_FIXTURE, create_app


STORE_PATH = Path(os.environ.get("OPENBODY_STORE_PATH", "/var/lib/openbody/twin-store.json"))
FIXTURE_PATH = Path(os.environ.get("OPENBODY_FIXTURE_PATH", str(DEFAULT_FIXTURE)))

store = DurableTwinStore.open(STORE_PATH, FIXTURE_PATH)
app = create_app(store=store)


@app.post("/v1/demo/compose")
def compose_demo_state(request: dict[str, Any]) -> dict[str, Any]:
    """Compose only receipt-bound outputs; defects become a visible abstention."""

    try:
        return compose(request)
    except DemoCompositionError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
