from __future__ import annotations

import json
from pathlib import Path

import pytest

from openbody_ref.durable_store import DurableTwinStore
from openbody_ref.host import DEFAULT_FIXTURE


def test_store_survives_restart_with_same_commitment(tmp_path: Path) -> None:
    path = tmp_path / "twin-store.json"
    first = DurableTwinStore.open(path, DEFAULT_FIXTURE)
    first_commitment = first.snapshot_commitment

    second = DurableTwinStore.open(path, DEFAULT_FIXTURE)

    assert second.snapshot_commitment == first_commitment
    assert second.state == first.state
    assert second.models == first.models
    assert second.scenarios == first.scenarios


def test_store_rejects_tampered_snapshot(tmp_path: Path) -> None:
    path = tmp_path / "twin-store.json"
    DurableTwinStore.open(path, DEFAULT_FIXTURE)
    envelope = json.loads(path.read_text(encoding="utf-8"))
    envelope["payload"]["state"]["subject"] = "subject:substituted"
    path.write_text(json.dumps(envelope), encoding="utf-8")

    with pytest.raises(ValueError, match="commitment mismatch"):
        DurableTwinStore.open(path, DEFAULT_FIXTURE)


def test_store_rejects_unknown_envelope_fields(tmp_path: Path) -> None:
    path = tmp_path / "twin-store.json"
    DurableTwinStore.open(path, DEFAULT_FIXTURE)
    envelope = json.loads(path.read_text(encoding="utf-8"))
    envelope["raw_health_data"] = {"glucose": 10.2}
    path.write_text(json.dumps(envelope), encoding="utf-8")

    with pytest.raises(ValueError, match="unknown or missing fields"):
        DurableTwinStore.open(path, DEFAULT_FIXTURE)
