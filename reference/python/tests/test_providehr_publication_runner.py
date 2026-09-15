"""The live helper must not turn real worker uncertainty into synthetic certainty."""
from copy import deepcopy
from dataclasses import replace
import importlib.util
from pathlib import Path

from fastapi.testclient import TestClient

from test_model_family import setup as state_setup
from openbody_ref.host import create_model_execution_host
from openbody_ref.validation import semantic_validate

path = Path(__file__).resolve().parents[3] / "tools/providehr_model_publication.py"
spec = importlib.util.spec_from_file_location("live_publication_helper", path)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


def test_live_helper_executes_distinct_real_unknown_and_synthetic_known_sources(state_setup):
    _, _, row, source, _, _, _ = state_setup
    before = deepcopy(row)
    configuration = {"admitted": row["source"]["clinical_version"], "publisher_url": "http://localhost"}
    runtime, publisher, real_request, fixture_request, authority, identity, sources = helper.prepare_publication(configuration, row, source)
    client = TestClient(create_model_execution_host(runtime, clinical_publisher=publisher))
    actual = client.post("/v1/model-executions", json=real_request).json()
    assert actual["kind"] == "ModelCounterfactual"
    assert actual["scenario"]["uncertainty"]["coverage"] is None
    assert actual["scenario"]["evidence"][0]["source_provenance"]["source"] == row["source"]
    assert client.get(f"/v1/model-executions/{actual['id']}/clinical-reference").json()["kind"] == "Abstention"
    known = client.post("/v1/model-executions", json=fixture_request).json()
    assert known["kind"] == "ModelCounterfactual"
    response = client.get(f"/v1/model-executions/{known['id']}/clinical-reference")
    packet = response.json()
    assert "reference" in packet, packet
    semantic_validate(packet["resolved_object"])
    assert packet["resolved_object"] == known["scenario"]
    assert known["scenario"]["evidence"][0]["source_provenance"]["source"]["system"] == "synthetic-test-only"
    assert known["scenario"]["evidence"][0]["id"] != row["id"]
    assert packet["reference"]["epistemic_class"] == "counterfactual"
    assert row == before and source.resolve(real_request["observations"][0]) == before
    for change in ("qualification", "dependency", "identity", "source"):
        lease, binding, fixture = authority.current, identity.current, deepcopy(sources.fixture)
        if change == "qualification": authority.current = replace(lease, status="revoked")
        elif change == "dependency": authority.current = replace(lease, dependency_digests=())
        elif change == "identity": identity.current = replace(binding, status="revoked")
        else: sources.fixture["uncertainty"]["coverage"] = 0.7
        assert client.get(packet["reference"]["canonical_ref"]).json()["kind"] == "Abstention"
        authority.current, identity.current, sources.fixture = lease, binding, fixture
        assert client.get(f"/v1/model-executions/{known['id']}/clinical-reference").json() == packet
