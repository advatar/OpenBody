#!/usr/bin/env python3
"""Exercise a running, enforced ProvidEHR worker/API through OpenBody HTTP.

Invoked by ProvidEHR's ignored inbound_admission_openbody_live_protocol test.
Read synthetic source configuration and locators from stdin; never print tokens
or clinical payloads. This runner does not emulate the source API or admission.
"""
from __future__ import annotations

import json
from pathlib import Path
import socket
import sys
from threading import Event, Thread
from time import monotonic

import httpx
import uvicorn
from jsonschema.exceptions import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reference" / "python"))

from openbody_ref.client import OpenBodyClient
from openbody_ref.host import create_app
from openbody_ref.observation import ProvidEHRObservationSource, validate_locator
from openbody_ref.store import InMemoryTwinStore
from openbody_ref.validation import validate_definition


def verify(configuration):
    locator = configuration["admitted"]
    validate_locator(locator)
    subject = f"subject:providehr:ehr:{locator['ehr_id']}"
    source = ProvidEHRObservationSource(configuration["source_url"], configuration["source_token"],
                                       locator["tenant_id"], locator["ehr_id"])
    store = InMemoryTwinStore(state={"subject": subject})
    app = create_app(store=store, observation_source=source, observations_only=True)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", access_log=False))
    thread = Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    try:
        deadline = monotonic() + 10
        while not server.started:
            if not thread.is_alive() or monotonic() > deadline:
                raise RuntimeError("OpenBody host failed to start")
            Event().wait(0.01)
        base = f"http://127.0.0.1:{port}"
        with OpenBodyClient(base) as client:
            value = client.ingest_observation(locator)
            assert value["subject"] == subject
            assert value["quantity"]["code"] == "Cel"
            assert abs(value["quantity"]["value"] - 37) < 1e-9
            assert value["normalization"]["source"]["quantity"]["value"] == 98.6
            assert value["source"]["clinical_version"] == locator
            assert value["uncertainty"]["out_of_distribution"] == "unknown"
            assert value["uncertainty"]["coverage"] is None
            assert client.ingest_observation(locator) == value
            assert client.observation(value["id"], subject=subject) == value
        assert len(store.observations) == 1
        with httpx.Client(base_url=base) as api:
            assert api.get("/v1/state").status_code == 404
            assert api.post("/v1/observations", json=value).status_code == 422
            for rejected in configuration["not_admitted"]:
                response = api.post("/v1/observations", json=rejected)
                assert response.status_code == 422
                assert response.json()["detail"]["code"] == "source_not_admitted"
            assert api.post("/v1/observations", json=locator | {"tenant_id": "other-tenant"}).status_code == 422
            assert api.post("/v1/observations", json=locator | {"ehr_id": "other-ehr"}).status_code == 422
        try:
            validate_definition("BodyState", value)
        except ValidationError:
            pass
        else:
            raise AssertionError("Observation became BodyState without a model")
        assert len(store.observations) == 1
        print("PASS live ProvidEHR worker -> authorized version API -> OpenBody HTTP ingestion/read/replay; partial/review/type/scope rejection")
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()
        source.close()


if __name__ == "__main__":
    verify(json.load(sys.stdin))
