"""Deployment ASGI entrypoint: select a host mode from the environment.

The reference package exposes `create_app()` for the bundled demo twin and
`create_observation_host_from_env()` for source-backed ingestion, but a catalogue
deployment has no entrypoint of its own — it needs `create_app(model_directory=...,
discovery_only=True)`. A process manager should not have to inline Python to start
the one mode that is actually safe to expose, so the selection happens here, once,
and fails closed on an unknown or unconfigured mode.

    uvicorn openbody_asgi:create_app_from_env --factory

`OPENBODY_MODE` picks the mode:

* `catalogue`    — discovery-only; no subject-bearing route exists. Requires
                   `OPENBODY_MODEL_DIRECTORY`.
* `observations` — source-backed ingestion against the authorized clinical API,
                   no demo state. Requires the four `OPENBODY_SOURCE_*` variables
                   read by the reference factory.
* `observations-local` — the same ingestion path resolving a local directory of
                   admitted clinical version documents, for a deployment with no
                   clinical API to reach. Requires `OPENBODY_SOURCE_DIRECTORY`,
                   the tenant/EHR binding, and `OPENBODY_ACCEPT_LOCAL_SOURCE=yes`,
                   because a directory is not an authorized clinical source.
* `demo-twin`    — the bundled `subject:local-demo` fixture. Requires an explicit
                   `OPENBODY_ACCEPT_DEMO_TWIN=yes`, because this mode serves a
                   complete `BodyState` to anyone who can reach the port and a
                   fixture read as a person's data is the expensive mistake.
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI

from openbody_ref.host import (
    create_app,
    create_local_observation_host_from_env,
    create_observation_host_from_env,
)

MODES = ("catalogue", "observations", "observations-local", "demo-twin")


def create_app_from_env() -> FastAPI:
    mode = os.environ.get("OPENBODY_MODE", "").strip()
    if mode not in MODES:
        raise ValueError(f"OPENBODY_MODE must be one of {', '.join(MODES)}; got {mode!r}")
    if mode == "observations":
        return create_observation_host_from_env()
    if mode == "observations-local":
        return create_local_observation_host_from_env()
    if mode == "catalogue":
        directory = os.environ.get("OPENBODY_MODEL_DIRECTORY", "").strip()
        if not directory:
            raise ValueError("catalogue hosting requires OPENBODY_MODEL_DIRECTORY")
        path = Path(directory)
        if not path.is_dir():
            raise ValueError(f"OPENBODY_MODEL_DIRECTORY {directory!r} is not a directory")
        return create_app(model_directory=path, discovery_only=True)
    if os.environ.get("OPENBODY_ACCEPT_DEMO_TWIN", "").strip().lower() != "yes":
        raise ValueError("demo-twin hosting serves the bundled fixture twin and requires OPENBODY_ACCEPT_DEMO_TWIN=yes")
    return create_app()
