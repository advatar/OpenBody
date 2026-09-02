from __future__ import annotations

import hashlib
import json
import os
import tempfile
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .store import InMemoryTwinStore
from .validation import semantic_validate


STORE_SCHEMA = "openbody.reference-twin-store.v1"


def _canonical_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _commitment(value: dict[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


@dataclass
class DurableTwinStore(InMemoryTwinStore):
    """Single-writer, restart-safe store for the reference twin host.

    Domain objects are stored byte-for-byte as JSON values. The surrounding
    snapshot commitment is operational metadata; it never changes an OpenBody
    object's canonical digest or adds fields to the strict protocol objects.
    """

    storage_path: Path = field(default_factory=lambda: Path("openbody-twin-store.json"))

    @classmethod
    def open(cls, storage_path: Path, fixture_path: Path) -> "DurableTwinStore":
        storage_path = storage_path.expanduser().resolve()
        if storage_path.exists():
            return cls._restore(storage_path)

        seed = InMemoryTwinStore.from_fixture(fixture_path)
        store = cls(
            state=deepcopy(seed.state),
            models=deepcopy(seed.models),
            trajectories=deepcopy(seed.trajectories),
            scenarios=deepcopy(seed.scenarios),
            outcomes=deepcopy(seed.outcomes),
            calibrations=deepcopy(seed.calibrations),
            storage_path=storage_path,
        )
        store.persist()
        return store

    @classmethod
    def _restore(cls, storage_path: Path) -> "DurableTwinStore":
        envelope = json.loads(storage_path.read_text(encoding="utf-8"))
        if set(envelope) != {"schema", "payload", "commitment"}:
            raise ValueError("durable twin store envelope has unknown or missing fields")
        if envelope["schema"] != STORE_SCHEMA:
            raise ValueError("durable twin store schema is unsupported")
        payload = envelope["payload"]
        if envelope["commitment"] != _commitment(payload):
            raise ValueError("durable twin store commitment mismatch")
        if set(payload) != {
            "state",
            "models",
            "trajectories",
            "scenarios",
            "outcomes",
            "calibrations",
        }:
            raise ValueError("durable twin store payload has unknown or missing fields")

        semantic_validate(payload["state"])
        for collection in ("models", "trajectories", "scenarios", "outcomes", "calibrations"):
            if not isinstance(payload[collection], dict):
                raise ValueError(f"durable twin store {collection} must be an object map")
            for object_id, value in payload[collection].items():
                if not isinstance(value, dict) or value.get("id") != object_id:
                    raise ValueError(f"durable twin store {collection} identity mismatch")
                semantic_validate(value)

        return cls(
            state=payload["state"],
            models=payload["models"],
            trajectories=payload["trajectories"],
            scenarios=payload["scenarios"],
            outcomes=payload["outcomes"],
            calibrations=payload["calibrations"],
            storage_path=storage_path,
        )

    def _payload(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "models": self.models,
            "trajectories": self.trajectories,
            "scenarios": self.scenarios,
            "outcomes": self.outcomes,
            "calibrations": self.calibrations,
        }

    @property
    def snapshot_commitment(self) -> str:
        return _commitment(self._payload())

    def persist(self) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        payload = self._payload()
        envelope = {
            "schema": STORE_SCHEMA,
            "payload": payload,
            "commitment": _commitment(payload),
        }
        encoded = _canonical_bytes(envelope) + b"\n"
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=self.storage_path.parent,
                prefix=f".{self.storage_path.name}.",
                delete=False,
            ) as handle:
                temporary_path = Path(handle.name)
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self.storage_path)
            directory_fd = os.open(self.storage_path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()

    def put_outcome(self, value: dict[str, Any]) -> None:
        previous = deepcopy(self.outcomes)
        super().put_outcome(value)
        try:
            self.persist()
        except Exception:
            self.outcomes = previous
            raise

    def put_calibration(self, value: dict[str, Any]) -> None:
        previous = deepcopy(self.calibrations)
        super().put_calibration(value)
        try:
            self.persist()
        except Exception:
            self.calibrations = previous
            raise
