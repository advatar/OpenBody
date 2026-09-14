#!/usr/bin/env python3
"""Exercise a running, enforced ProvidEHR worker/API through OpenBody HTTP.

Invoked by ProvidEHR's ignored inbound_admission_openbody_live_protocol test.
Read synthetic source configuration and locators from stdin; never print tokens
or clinical payloads. This runner does not emulate the source API or admission.
"""
from __future__ import annotations

from copy import deepcopy
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
from openbody_ref.host import create_app
from openbody_ref.observation import ProvidEHRObservationSource, validate_locator
from openbody_ref.store import InMemoryTwinStore
from openbody_ref.clinical_reference import validate_clinical_reference
from openbody_ref.validation import canonical_digest, semantic_validate, validate_definition


def synthetic_model_reference(subject):
    """Rebind a test-only scenario to the synthetic EHR and current test clock.

    This is transport/type evidence, not a model consuming the new observation.
    G3/G4 must supply actual model execution and qualification separately.
    """
    bundle = json.loads((ROOT / "examples/clinical-assertion-references.v1.json").read_text())
    scenario = json.loads((ROOT / "examples/post-meal-walk.scenario.json").read_text())
    old_subject = bundle["base_reference"]["subject"]
    now = datetime.now(timezone.utc)
    shift = now - datetime.fromisoformat(bundle["evaluated_at"].replace("Z", "+00:00"))

    def bind(value):
        if isinstance(value, dict):
            return {k: bind(v) for k, v in value.items()}
        if isinstance(value, list):
            return [bind(v) for v in value]
        if value == old_subject:
            return subject
        if isinstance(value, str) and len(value) >= 20 and value[10:11] == "T" and value.endswith("Z"):
            return (datetime.fromisoformat(value.replace("Z", "+00:00")) + shift).isoformat().replace("+00:00", "Z")
        return value

    reference, resolved = bind(bundle["base_reference"]), bind(scenario)
    reference["content_digest"] = canonical_digest(resolved)
    semantic_validate(resolved)
    validate_clinical_reference(reference, resolved, evaluated_at=now)
    return reference, resolved


def verify_model_return(configuration, observation):
    ehr = configuration["admitted"]["ehr_id"]
    reference, resolved = synthetic_model_reference(observation["subject"])
    payload = {"ehr_id": ehr, "reference": reference, "resolved_object": resolved}
    prefix = f"/v1/ehr/{ehr}/openbody"
    with httpx.Client(base_url=configuration["source_url"],
                      headers={"Authorization": f"Bearer {configuration['source_token']}"}) as api:
        response = api.post(f"{prefix}/admissions", json=payload)
        assert response.status_code == 201, response.text
        assert response.json()["admission"]["reference"]["object_kind"] == "CounterfactualScenario"
        assert response.json()["admission"]["resolved_object"] == resolved
        assert api.post(f"{prefix}/admissions", json=payload).json()["replayed"] is True
        assert api.post(f"{prefix}/simulations", json=payload).status_code == 201
        state = api.get(f"{prefix}/state")
        assert state.status_code == 200
        assert len(state.json()["projections"]) == 1
        assert state.json()["projections"][0]["reference"]["epistemic_class"] == "statistical_association"
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
    print("PASS separately typed synthetic model-reference return, replay, EHR binding, expiry and Observation rejection")


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
            verify_model_return(configuration, value)
        print("PASS live ProvidEHR worker -> authorized version API -> OpenBody HTTP ingestion/read/replay; partial/review/type/scope rejection")
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()
        source.close()


if __name__ == "__main__":
    verify(json.load(sys.stdin))
