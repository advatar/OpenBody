"""The deployment entrypoint and its documented configuration must agree.

A deployment asset that drifts from the code fails at 3am on someone else's
server, so the mode selection, the environment contract it publishes, and the
process manager files that set it are checked here rather than by reading.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
DEPLOY = ROOT / "deploy" / "openbody"
sys.path.insert(0, str(DEPLOY))

from openbody_asgi import MODES, create_app_from_env  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from test_discovery_host import descriptor  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_mode_environment(monkeypatch):
    for name in ("OPENBODY_MODE", "OPENBODY_MODEL_DIRECTORY", "OPENBODY_ACCEPT_DEMO_TWIN",
                 "OPENBODY_SOURCE_URL", "OPENBODY_SOURCE_TOKEN_FILE", "OPENBODY_SOURCE_TENANT",
                 "OPENBODY_SOURCE_EHR"):
        monkeypatch.delenv(name, raising=False)


class TestModeSelection:
    def test_unset_mode_fails_closed(self):
        with pytest.raises(ValueError, match="OPENBODY_MODE"):
            create_app_from_env()

    def test_unknown_mode_fails_closed(self, monkeypatch):
        monkeypatch.setenv("OPENBODY_MODE", "twin")
        with pytest.raises(ValueError, match="OPENBODY_MODE"):
            create_app_from_env()

    def test_demo_twin_requires_explicit_opt_in(self, monkeypatch):
        monkeypatch.setenv("OPENBODY_MODE", "demo-twin")
        with pytest.raises(ValueError, match="OPENBODY_ACCEPT_DEMO_TWIN"):
            create_app_from_env()

    def test_demo_twin_serves_the_fixture_twin_when_accepted(self, monkeypatch):
        monkeypatch.setenv("OPENBODY_MODE", "demo-twin")
        monkeypatch.setenv("OPENBODY_ACCEPT_DEMO_TWIN", "yes")
        client = TestClient(create_app_from_env())
        assert client.get("/v1/state").json()["subject"] == "subject:local-demo"

    def test_catalogue_requires_a_model_directory(self, monkeypatch):
        monkeypatch.setenv("OPENBODY_MODE", "catalogue")
        with pytest.raises(ValueError, match="OPENBODY_MODEL_DIRECTORY"):
            create_app_from_env()

    def test_catalogue_rejects_a_missing_directory(self, monkeypatch, tmp_path):
        monkeypatch.setenv("OPENBODY_MODE", "catalogue")
        monkeypatch.setenv("OPENBODY_MODEL_DIRECTORY", str(tmp_path / "absent"))
        with pytest.raises(ValueError, match="not a directory"):
            create_app_from_env()

    def test_catalogue_mounts_no_subject_bearing_route(self, monkeypatch, tmp_path):
        import json
        (tmp_path / "model.json").write_text(json.dumps(descriptor("model-catalogue-001")))
        monkeypatch.setenv("OPENBODY_MODE", "catalogue")
        monkeypatch.setenv("OPENBODY_MODEL_DIRECTORY", str(tmp_path))
        client = TestClient(create_app_from_env())
        assert client.get("/v1/models").status_code == 200
        assert client.get("/v1/state").status_code == 404
        assert "state.read" not in client.get("/v1/capabilities").json()["capabilities"]

    def test_observations_mode_requires_its_source_configuration(self, monkeypatch):
        monkeypatch.setenv("OPENBODY_MODE", "observations")
        with pytest.raises(ValueError, match="source URL, token file, tenant and EHR"):
            create_app_from_env()


class TestDeploymentAssets:
    def test_documented_environment_covers_every_mode(self):
        example = (DEPLOY / "env.example").read_text()
        for mode in MODES:
            assert mode in example, f"env.example does not document mode {mode}"

    def test_source_variables_match_the_reference_factories(self):
        """Every OPENBODY_SOURCE_* name a host factory requires is documented.

        A variable the code reads and the example omits is a silent startup failure
        on someone else's server, which is exactly what this handover must not ship.
        """
        factory = (ROOT / "reference" / "python" / "openbody_ref" / "host.py").read_text()
        required = {name for name in factory.split('"') if name.startswith("OPENBODY_SOURCE_")}
        documented = {line.lstrip("# ").split("=")[0].removesuffix("_HOST")
                      for line in (DEPLOY / "env.example").read_text().splitlines()
                      if line.lstrip("# ").startswith("OPENBODY_SOURCE_")}
        assert required and required <= documented

    def test_the_non_authoritative_source_opt_in_is_documented(self):
        """A local source is not an authorized one; the example must say the word."""
        example = (DEPLOY / "env.example").read_text()
        assert "OPENBODY_ACCEPT_LOCAL_SOURCE" in example
        assert "OPENBODY_ACCEPT_DEMO_TWIN" in example

    @pytest.mark.parametrize("asset", ["Dockerfile", "openbody-host.service"])
    def test_process_managers_start_the_deployment_entrypoint(self, asset):
        text = (DEPLOY / asset).read_text()
        assert "openbody_asgi:create_app_from_env" in text and "--factory" in text
        assert "reference/python" in text, "PYTHONPATH must include the reference package"

    def test_no_asset_binds_the_unauthenticated_host_to_a_public_interface(self):
        """The host implements no authorization, so a proxy must own the boundary."""
        published = [line.strip() for line in (DEPLOY / "compose.yaml").read_text().splitlines()
                     if ":8797" in line and line.strip().startswith("- \"")]
        assert published and all(line.startswith('- "127.0.0.1:') for line in published)
        assert "--host 127.0.0.1" in (DEPLOY / "openbody-host.service").read_text()
