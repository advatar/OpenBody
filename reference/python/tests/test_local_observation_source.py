"""Observation hosting without an authorized clinical API.

The local source removes a network dependency, not a check: these tests hold it to
the same admission verification as the ProvidEHR resolver, and hold the deployment
to admitting that its source is not authoritative.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from openbody_ref.host import ROOT, create_local_observation_host_from_env
from openbody_ref.observation import LocalObservationSource, ObservationError

SHIPPED = ROOT / "examples" / "local-observations" / "synthetic-body-temperature.v1.json"
LOCATOR = {
    "tenant_id": "synthetic-tenant",
    "ehr_id": "11111111-1111-4111-8111-111111111111",
    "composition_uid": "22222222-2222-4222-8222-222222222222",
    "version_uid": "22222222-2222-4222-8222-222222222222::provid-ehr::1",
}


@pytest.fixture
def directory(tmp_path: Path) -> Path:
    (tmp_path / "observation.json").write_text(SHIPPED.read_text())
    return tmp_path


@pytest.fixture
def source(directory: Path) -> LocalObservationSource:
    return LocalObservationSource(directory, LOCATOR["tenant_id"], LOCATOR["ehr_id"])


class TestResolution:
    def test_resolves_the_shipped_admitted_version(self, source):
        value = source.resolve(dict(LOCATOR))
        assert value["id"] == f"urn:openbody:observation:{LOCATOR['version_uid']}"
        assert value["subject"] == f"subject:providehr:ehr:{LOCATOR['ehr_id']}"
        assert value["source"]["clinical_version"] == LOCATOR

    def test_returns_a_copy_a_caller_cannot_mutate_into_the_source(self, source):
        source.resolve(dict(LOCATOR))["quantity"]["value"] = 41.0
        assert source.resolve(dict(LOCATOR))["quantity"]["value"] == 37.0

    def test_an_absent_version_is_unavailable_not_invented(self, source):
        absent = dict(LOCATOR) | {"version_uid": f"{LOCATOR['composition_uid']}::provid-ehr::2"}
        with pytest.raises(ObservationError) as error:
            source.resolve(absent)
        assert error.value.code == "source_unavailable"

    @pytest.mark.parametrize("field", ["tenant_id", "ehr_id"])
    def test_a_locator_outside_the_bound_scope_is_refused(self, source, field):
        with pytest.raises(ObservationError) as error:
            source.resolve(dict(LOCATOR) | {field: "11111111-1111-4111-8111-111111111112"})
        assert error.value.code == "source_scope_mismatch"

    def test_a_malformed_locator_is_refused_before_lookup(self, source):
        with pytest.raises(ObservationError) as error:
            source.resolve({"tenant_id": "synthetic-tenant"})
        assert error.value.code == "invalid_source_locator"

    def test_resolution_follows_the_document_not_its_file_name(self, tmp_path):
        """A file named for one version must not resolve as another."""
        (tmp_path / "some-other-version.json").write_text(SHIPPED.read_text())
        source = LocalObservationSource(tmp_path, LOCATOR["tenant_id"], LOCATOR["ehr_id"])
        assert source.resolve(dict(LOCATOR))["source"]["clinical_version"] == LOCATOR


class TestStartupVerification:
    def test_a_tampered_clinical_value_cannot_start_a_host(self, directory):
        path = directory / "observation.json"
        document = json.loads(path.read_text())
        document["composition"]["content"]["observation"]["value"] = 41.0
        path.write_text(json.dumps(document))
        with pytest.raises(ObservationError) as error:
            LocalObservationSource(directory, LOCATOR["tenant_id"], LOCATOR["ehr_id"])
        assert error.value.code == "admission_mismatch"

    def test_a_document_for_another_ehr_cannot_start_a_host(self, directory):
        with pytest.raises(ValueError, match="not the bound"):
            LocalObservationSource(directory, LOCATOR["tenant_id"], "11111111-1111-4111-8111-111111111112")

    def test_another_tenant_cannot_start_a_host(self, directory):
        with pytest.raises(ObservationError) as error:
            LocalObservationSource(directory, "other-tenant", LOCATOR["ehr_id"])
        assert error.value.code == "source_scope_mismatch"

    def test_a_duplicate_version_cannot_start_a_host(self, directory):
        (directory / "copy.json").write_text(SHIPPED.read_text())
        with pytest.raises(ValueError, match="duplicate clinical version"):
            LocalObservationSource(directory, LOCATOR["tenant_id"], LOCATOR["ehr_id"])

    def test_an_empty_directory_cannot_start_a_host(self, tmp_path):
        with pytest.raises(ValueError, match="no clinical version document"):
            LocalObservationSource(tmp_path, LOCATOR["tenant_id"], LOCATOR["ehr_id"])

    def test_a_missing_directory_cannot_start_a_host(self, tmp_path):
        with pytest.raises(ValueError, match="is not a directory"):
            LocalObservationSource(tmp_path / "absent", LOCATOR["tenant_id"], LOCATOR["ehr_id"])


class TestFactory:
    @pytest.fixture(autouse=True)
    def _environment(self, monkeypatch, directory):
        monkeypatch.setenv("OPENBODY_SOURCE_DIRECTORY", str(directory))
        monkeypatch.setenv("OPENBODY_SOURCE_TENANT", LOCATOR["tenant_id"])
        monkeypatch.setenv("OPENBODY_SOURCE_EHR", LOCATOR["ehr_id"])
        monkeypatch.setenv("OPENBODY_ACCEPT_LOCAL_SOURCE", "yes")

    def test_a_non_authoritative_source_requires_an_explicit_opt_in(self, monkeypatch):
        monkeypatch.delenv("OPENBODY_ACCEPT_LOCAL_SOURCE")
        with pytest.raises(ValueError, match="OPENBODY_ACCEPT_LOCAL_SOURCE"):
            create_local_observation_host_from_env()

    def test_incomplete_configuration_fails_closed(self, monkeypatch):
        monkeypatch.delenv("OPENBODY_SOURCE_TENANT")
        with pytest.raises(ValueError, match="source directory, tenant and EHR"):
            create_local_observation_host_from_env()

    def test_health_names_the_source_the_process_is_bound_to(self):
        body = TestClient(create_local_observation_host_from_env()).get("/healthz").json()
        assert body["observation_source"] == "local-directory"

    def test_the_host_loads_no_demo_twin(self):
        client = TestClient(create_local_observation_host_from_env())
        assert client.get("/v1/state").status_code == 404
        capabilities = client.get("/v1/capabilities").json()["capabilities"]
        assert "observations.ingest" in capabilities and "state.read" not in capabilities

    def test_ingest_and_read_round_trip_through_the_local_source(self):
        client = TestClient(create_local_observation_host_from_env())
        ingested = client.post("/v1/observations", json=dict(LOCATOR))
        assert ingested.status_code == 200, ingested.text
        observation_id = ingested.json()["id"]
        read = client.get(f"/v1/observations/{observation_id}")
        assert read.status_code == 200
        assert read.json() == ingested.json()

    def test_an_unresolvable_version_is_reported_as_source_unavailable(self):
        client = TestClient(create_local_observation_host_from_env())
        absent = dict(LOCATOR) | {"version_uid": f"{LOCATOR['composition_uid']}::provid-ehr::2"}
        response = client.post("/v1/observations", json=absent)
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "source_unavailable"
