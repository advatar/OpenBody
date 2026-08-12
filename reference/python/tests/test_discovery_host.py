"""The deployable read-only discovery configuration.

Covers contract identity, the operational health check, and serving a validated
descriptor directory. Discoverability is not clinical validity: these tests assert
that a research baseline stays labelled as one wherever it is served.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from openbody_ref.host import ROOT, contract_identity, create_app, load_model_directory


def descriptor(
    model_id: str,
    maturity: str = "shipped",
    scope: str = "ob://human/metabolic",
    subject: str = "subject:catalogue",
) -> dict:
    return {
        "schema_version": "0.1",
        "kind": "BodyModel",
        "id": model_id,
        "version": "0.1.0",
        "family": "statistical",
        "provider": "test",
        "scopes": [scope],
        "capabilities": ["state_estimation"],
        "required_inputs": ["some_series"],
        "outputs": ["some_state"],
        "applicability": {
            "mode": maturity,
            "subject": subject,
            "scopes": [scope],
            "horizon_seconds": 86_400,
            "evidence_boundary": "the subject's own observations",
            "generalizable": False,
        },
        "validation": {
            "status": "software_behaviour_only" if maturity == "researchBaseline" else "evaluated_in_product",
            "references": [],
        },
        "prohibited_uses": ["clinical decision-making"],
        "execution": {"mode": "on_device"},
        "dependencies": [],
    }


class TestContractIdentity:
    def test_identity_names_the_contract_not_a_tag(self) -> None:
        identity = contract_identity()
        assert identity["schema_version"] == "0.1"
        # The registry version is reported separately because registries grow
        # additively without changing protocol semantics.
        assert identity["registry_version"]
        assert identity["coordinate_count"] > 0
        # A tag cannot tell a consumer which contract is served.
        assert "tag" not in identity
        assert "version" not in identity

    def test_identity_digests_every_normative_artifact(self) -> None:
        digests = contract_identity()["artifact_digests"]
        for artifact in (
            "OPENBODY.md",
            "schemas/openbody.schema.json",
            "openapi/openbody.openapi.json",
            "profiles/mcp/tools.json",
            "registry/coordinates.json",
        ):
            assert artifact in digests, artifact
            assert digests[artifact].startswith("sha256:")

    def test_identity_changes_when_an_artifact_changes(self) -> None:
        before = contract_identity()["artifact_digests"]["registry/coordinates.json"]
        registry_path = ROOT / "registry" / "coordinates.json"
        original = registry_path.read_text()
        try:
            mutated = json.loads(original)
            mutated["registry_version"] = "9.9"
            registry_path.write_text(json.dumps(mutated, indent=2) + "\n")
            after = contract_identity()
            assert after["artifact_digests"]["registry/coordinates.json"] != before
            assert after["registry_version"] == "9.9"
        finally:
            registry_path.write_text(original)


class TestHealthCheck:
    def test_health_reports_the_contract_being_served(self) -> None:
        response = TestClient(create_app()).get("/healthz")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        # A deployment check must be able to detect a host running a different
        # contract than the consumer validated against.
        assert body["contract"]["schema_version"] == "0.1"
        assert body["contract"]["registry_version"]

    def test_well_known_carries_contract_identity(self) -> None:
        body = TestClient(create_app()).get("/.well-known/openbody").json()
        assert body["contract"]["schema_version"] == "0.1"
        assert body["base_url"] == "/v1"


class TestModelDirectory:
    def test_serves_a_validated_descriptor_set(self, tmp_path) -> None:
        (tmp_path / "a.json").write_text(json.dumps(descriptor("model-a")))
        (tmp_path / "b.json").write_text(json.dumps(descriptor("model-b")))
        client = TestClient(create_app(model_directory=tmp_path, discovery_only=True))

        listing = client.get("/v1/models")
        assert listing.status_code == 200
        assert {model["id"] for model in listing.json()} == {"model-a", "model-b"}

        one = client.get("/v1/models/model-a")
        assert one.status_code == 200
        assert one.json()["id"] == "model-a"

    def test_health_reports_the_served_model_count(self, tmp_path) -> None:
        (tmp_path / "a.json").write_text(json.dumps(descriptor("model-a")))
        body = TestClient(create_app(model_directory=tmp_path, discovery_only=True)).get("/healthz").json()
        assert body["models"] == 1

    def test_unknown_model_is_not_found(self, tmp_path) -> None:
        (tmp_path / "a.json").write_text(json.dumps(descriptor("model-a")))
        client = TestClient(create_app(model_directory=tmp_path, discovery_only=True))
        assert client.get("/v1/models/absent").status_code == 404

    # A host that serves an invalid descriptor makes every scenario citing that
    # model unsubstantiable, and the failure would surface far from its cause.
    def test_an_invalid_descriptor_prevents_startup(self, tmp_path) -> None:
        broken = descriptor("model-broken")
        del broken["capabilities"]
        (tmp_path / "broken.json").write_text(json.dumps(broken))
        with pytest.raises(Exception):
            load_model_directory(tmp_path)

    def test_a_non_descriptor_prevents_startup(self, tmp_path) -> None:
        (tmp_path / "scenario.json").write_text(
            (ROOT / "examples" / "post-meal-walk.scenario.json").read_text()
        )
        with pytest.raises(ValueError, match="not a BodyModel"):
            load_model_directory(tmp_path)

    def test_duplicate_model_ids_prevent_startup(self, tmp_path) -> None:
        (tmp_path / "a.json").write_text(json.dumps(descriptor("same-id")))
        (tmp_path / "b.json").write_text(json.dumps(descriptor("same-id")))
        with pytest.raises(ValueError, match="duplicate model id"):
            load_model_directory(tmp_path)

    def test_an_empty_directory_serves_nothing_rather_than_failing(self, tmp_path) -> None:
        # An empty corpus is a deployment mistake, but it is the conformance gate's
        # job to catch it. The host should not pretend to serve models it lacks.
        client = TestClient(create_app(model_directory=tmp_path, discovery_only=True))
        assert client.get("/v1/models").json() == []


class TestDiscoverabilityIsNotValidity:
    """Serving a descriptor makes a model discoverable, never clinically validated."""

    def test_a_research_baseline_stays_labelled_when_served(self, tmp_path) -> None:
        (tmp_path / "baseline.json").write_text(
            json.dumps(descriptor("model-baseline", maturity="researchBaseline"))
        )
        served = TestClient(create_app(model_directory=tmp_path, discovery_only=True))\
            .get("/v1/models/model-baseline").json()
        # The maturity, its validation status, and its prohibitions travel with it.
        assert served["validation"]["status"] == "software_behaviour_only"
        assert served["applicability"]["mode"] == "researchBaseline"
        assert "clinical decision-making" in served["prohibited_uses"]

    def test_every_served_descriptor_declares_prohibited_uses(self, tmp_path) -> None:
        (tmp_path / "a.json").write_text(json.dumps(descriptor("model-a")))
        client = TestClient(create_app(model_directory=tmp_path, discovery_only=True))
        for model in client.get("/v1/models").json():
            assert model["prohibited_uses"], f"{model['id']} prohibits nothing"

    def test_no_served_descriptor_claims_generalizability(self, tmp_path) -> None:
        (tmp_path / "a.json").write_text(json.dumps(descriptor("model-a")))
        client = TestClient(create_app(model_directory=tmp_path, discovery_only=True))
        for model in client.get("/v1/models").json():
            assert model["applicability"]["generalizable"] is False


class TestDiscoveryOnlySurface:
    """A discovery deployment must expose no subject-bearing endpoint at all.

    The default host is backed by the bundled demo twin, so serving its state would
    publish a `BodyState` for `subject:local-demo` and invite a reader to mistake a
    fixture for a person's data. A model descriptor carries no subject data; a
    `BodyState` is nothing but subject data.
    """

    def client(self, tmp_path):
        (tmp_path / "a.json").write_text(json.dumps(descriptor("model-a")))
        return TestClient(create_app(model_directory=tmp_path, discovery_only=True))

    def test_discovery_surface_is_available(self, tmp_path) -> None:
        client = self.client(tmp_path)
        for path in ("/healthz", "/.well-known/openbody", "/v1/capabilities", "/v1/models"):
            assert client.get(path).status_code == 200, path
        assert client.get("/v1/models/model-a").status_code == 200

    def test_no_subject_bearing_route_exists(self, tmp_path) -> None:
        client = self.client(tmp_path)
        # Omitted rather than guarded: a route that does not exist cannot be
        # misconfigured into existence.
        for path in (
            "/v1/state",
            "/v1/state/human/metabolic",
            "/v1/simulations/scenario-post-meal-walk-001",
            "/v1/trajectories/anything",
        ):
            assert client.get(path).status_code == 404, path

    def test_no_write_route_exists(self, tmp_path) -> None:
        client = self.client(tmp_path)
        for path in ("/v1/simulations", "/v1/outcomes", "/v1/calibrations"):
            response = client.post(path, json={})
            # 404 for absent, never 422 from a handler that ran.
            assert response.status_code == 404, f"{path} -> {response.status_code}"

    def test_no_real_subject_identifier_appears_in_any_response(self, tmp_path) -> None:
        client = self.client(tmp_path)
        for path in ("/healthz", "/.well-known/openbody", "/v1/capabilities", "/v1/models"):
            assert "local-demo" not in client.get(path).text, path

    def test_a_subject_bound_descriptor_cannot_be_published(self, tmp_path) -> None:
        # applicability.subject identifies a person, so a catalogue that served it
        # verbatim would disclose whose twin the model applies to.
        (tmp_path / "bound.json").write_text(
            json.dumps(descriptor("model-bound", subject="subject:a-real-person"))
        )
        with pytest.raises(ValueError, match="public catalogue"):
            load_model_directory(tmp_path, public=True)

    def test_the_same_descriptor_is_fine_for_a_private_host(self, tmp_path) -> None:
        (tmp_path / "bound.json").write_text(
            json.dumps(descriptor("model-bound", subject="subject:a-real-person"))
        )
        # Subject binding is required for substantiation; it is publication that is
        # the problem, not the binding.
        assert "model-bound" in load_model_directory(tmp_path, public=False)

    def test_the_full_host_still_serves_everything(self) -> None:
        # discovery_only must be opt-in, so the reference host is unchanged.
        client = TestClient(create_app())
        assert client.get("/v1/state").status_code == 200
