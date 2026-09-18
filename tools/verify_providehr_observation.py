#!/usr/bin/env python3
"""Exercise a running, enforced ProvidEHR worker/API through OpenBody HTTP.

Invoked by ProvidEHR's ignored inbound_admission_openbody_live_protocol test.
Read synthetic source configuration and locators from stdin; never print tokens
or clinical payloads. This runner does not emulate the source API or admission.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone, timedelta
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
from openbody_ref.host import create_app, create_model_execution_host
from providehr_model_publication import prepare_publication
from openbody_ref.observation import ProvidEHRObservationSource, validate_locator
from openbody_ref.store import InMemoryTwinStore
from openbody_ref.clinical_reference import validate_clinical_reference
from openbody_ref.validation import canonical_digest, semantic_validate, validate_definition


def verify_model_return(configuration, observation, source):
    from fastapi.responses import JSONResponse
    runtime, publisher, request, fixture_request, authority, identity, sources = prepare_publication(configuration, observation, source)
    app = create_model_execution_host(runtime, clinical_publisher=publisher)

    @app.middleware("http")
    async def authenticate(request, call_next):
        if request.headers.get("authorization") != "Bearer " + configuration["publisher_token"]:
            return JSONResponse({"error": "unauthorized"}, status_code=401, headers={"Cache-Control": "no-store"})
        return await call_next(request)

    sock = socket.socket()
    sock.bind(("127.0.0.1", configuration["publisher_port"]))
    sock.listen(128)
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", access_log=False))
    thread = Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    try:
        deadline = monotonic() + 10
        while not server.started:
            if not thread.is_alive() or monotonic() > deadline:
                raise RuntimeError("Qualified model publisher failed to start")
            Event().wait(0.01)
        ehr = configuration["admitted"]["ehr_id"]
        prefix = f"/v1/ehr/{ehr}/openbody"
        with httpx.Client(base_url=configuration["publisher_url"], headers={"Authorization": "Bearer " + configuration["publisher_token"]}) as model_api, httpx.Client(
                base_url=configuration["source_url"], headers={"Authorization": "Bearer " + configuration["source_token"]}) as api:
            # Execute the real worker observation without strengthening it.
            unknown = model_api.post("/v1/model-executions", json=request).json()
            assert unknown["kind"] == "ModelCounterfactual"
            assert unknown["scenario"]["uncertainty"]["coverage"] is None
            assert unknown["scenario"]["evidence"][0]["source_provenance"]["uncertainty"] == observation["uncertainty"]
            refused = model_api.get(f"/v1/model-executions/{unknown['id']}/clinical-reference")
            assert refused.json()["kind"] == "Abstention"
            assert refused.headers["OpenBody-Execution-Reason"] == "uncertainty_unknown"
            assert api.post(f"{prefix}/admissions", json={"ehr_id": ehr, "reference": refused.json(), "resolved_object": unknown}).status_code == 422
            assert api.get(f"{prefix}/state").json()["projections"] == []
            # An independent known-input software fixture exercises positive
            # runtime publication. It is not the worker's admitted observation.
            result = model_api.post("/v1/model-executions", json=fixture_request).json()
            payload = model_api.get(f"/v1/model-executions/{result['id']}/clinical-reference").json()
            reference, resolved = payload["reference"], payload["resolved_object"]
            assert resolved == result["scenario"]
            assert resolved["evidence"][0]["source_provenance"]["source"]["system"] == "synthetic-test-only"
            assert resolved["evidence"][0]["id"] != observation["id"]
            response = api.post(f"{prefix}/admissions", json=payload)
            assert response.status_code == 201, response.text
            assert response.json()["admission"]["resolved_object"] == resolved
            assert api.post(f"{prefix}/admissions", json=payload).json()["replayed"] is True
            assert api.post(f"{prefix}/simulations", json=payload).status_code == 201
            state = api.get(f"{prefix}/state")
            assert state.status_code == 200, state.text
            assert len(state.json()["projections"]) == 1
            assert state.json()["projections"][0]["reference"]["epistemic_class"] == "counterfactual"
            original = deepcopy(state.json()["projections"][0])
            ui = api.post("/v1/a2ui/intent", json={"intent": "openbody_clinical_state", "ehr_id": ehr})
            assert ui.status_code == 200, ui.text
            forged = deepcopy(payload)
            forged["reference"]["subject"] = "subject:providehr:ehr:another"
            assert api.post(f"{prefix}/admissions", json=forged).status_code == 422
            assert api.post(f"{prefix}/admissions", json=payload | {"reference": observation, "resolved_object": observation}).status_code == 422
            expired = deepcopy(payload)
            expired["reference"]["validity"]["valid_until"] = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
            assert api.post(f"{prefix}/admissions", json=expired).status_code == 422
            wrong_kind = deepcopy(payload)
            wrong_kind["reference"]["object_kind"] = "BodyState"
            assert api.post(f"{prefix}/simulations", json=wrong_kind).status_code == 422
            for change in ("qualification", "dependency", "identity", "source"):
                lease, binding, fixture = authority.current, identity.current, deepcopy(sources.fixture)
                if change == "qualification": authority.current = replace(lease, status="revoked")
                elif change == "dependency": authority.current = replace(lease, dependency_digests=())
                elif change == "identity": identity.current = replace(binding, status="revoked")
                else: sources.fixture["uncertainty"]["coverage"] = 0.7
                for route in ("state", "simulations"):
                    denied = api.get(f"{prefix}/{route}")
                    assert denied.status_code == 422, denied.text
                    assert denied.json()["code"] == "openbody_not_current"
                for route in ("admissions", "simulations"):
                    assert api.post(f"{prefix}/{route}", json=payload).status_code == 422
                ui = api.post("/v1/a2ui/intent", json={"intent": "openbody_clinical_state", "ehr_id": ehr})
                assert ui.status_code == 422, ui.text
                assert ui.json()["code"] == "openbody_not_current"
                authority.current, identity.current, sources.fixture = lease, binding, fixture
                restored = api.get(f"{prefix}/state")
                assert restored.status_code == 200, restored.text
                assert restored.json()["projections"][0] == original
            assert source.resolve(configuration["admitted"]) == observation
        print("PASS actual worker observation -> qualified model preserves unknown uncertainty and refuses clinical publication")
        print("PASS separate synthetic known-input model -> publisher -> real ProvidEHR admission/read/replay; issuer qualification/dependency/identity/source revocation denies reuse and preserves history")
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()


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
        if configuration.get("verify_model_return"):
            verify_model_return(configuration, value, source)
        print("PASS live ProvidEHR worker -> authorized version API -> OpenBody HTTP ingestion/read/replay; partial/review/type/scope rejection")
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()
        source.close()


if __name__ == "__main__":
    verify(json.load(sys.stdin))
