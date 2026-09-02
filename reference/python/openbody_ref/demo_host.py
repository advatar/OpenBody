from __future__ import annotations

import os
from pathlib import Path

from .durable_store import DurableTwinStore
from .host import DEFAULT_FIXTURE, create_app


STORE_PATH = Path(os.environ.get("OPENBODY_STORE_PATH", "/var/lib/openbody/twin-store.json"))
FIXTURE_PATH = Path(os.environ.get("OPENBODY_FIXTURE_PATH", str(DEFAULT_FIXTURE)))

store = DurableTwinStore.open(STORE_PATH, FIXTURE_PATH)
app = create_app(store=store)
