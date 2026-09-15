"""Synthetic authority/identity fixtures test software boundaries, not clinical qualification."""
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from urllib.parse import quote

from fastapi.testclient import TestClient
import pytest

from test_model_family import setup as state_setup
from test_model_forecast import setup as forecast_setup
from test_model_counterfactual import setup as counterfactual_setup
from openbody_ref.clinical_reference import validate_clinical_reference
from openbody_ref.host import create_app, create_model_execution_host
from openbody_ref.model_clinical_reference import QualifiedClinicalReferencePublisher, VerifiedSubjectBinding
from openbody_ref.model_family import ModelExecutionError
from openbody_ref.validation import canonical_digest, parse_timestamp, semantic_validate


def prepare(data):
    contract, request, row, source, authority, clock, factory = data
    # Fake clinical policy is intentionally confined to this software test.
    contract["context_of_use"] = ["software_test", "research", "clinical_decision_support"]
    contract["prohibited_uses"] = ["autonomous_treatment"]
    contract["qualification_evidence"] += [
        {"ref": "test:synthetic-clinical-policy", "digest": "sha256:" + "3" * 64, "kind": "clinical"},
        {"ref": "test:synthetic-research-policy", "digest": "sha256:" + "4" * 64, "kind": "research"}]
    request["purpose"] = "clinical_decision_support"
    authority.current = replace(authority.current, purpose=request["purpose"], contract_digest=canonical_digest(contract),
        evidence_digests=tuple((row["ref"], row["digest"]) for row in contract["qualification_evidence"]))
    row["uncertainty"].update(epistemic=0.1, aleatoric=0.1, coverage=0.9, out_of_distribution=False)
    runtime = factory()

    class BindingAuthority:
        calls = 0
        current = VerifiedSubjectBinding(runtime.subject, runtime.tenant_id, row["source"]["clinical_version"]["ehr_id"],
            "test:identity-binding", "test-only-identity-authority", "sha256:" + "5" * 64, "test:identity-revocation",
            clock[0] - timedelta(seconds=10), clock[0] + timedelta(minutes=5), "verified")
        def resolve(self, subject, tenant_id, ehr_id):
            self.calls += 1
            assert (subject, tenant_id, ehr_id) == (runtime.subject, runtime.tenant_id, row["source"]["clinical_version"]["ehr_id"])
            return self.current
    binding = BindingAuthority()
    publisher = QualifiedClinicalReferencePublisher(runtime, binding, "http://localhost")
    return data, runtime, publisher, binding


@pytest.fixture(params=["state_setup", "counterfactual_setup"])
def configured(request):
    return prepare(request.getfixturevalue(request.param))


def test_actual_execution_to_clinical_reference_http_round_trip(configured):
    data, runtime, publisher, binding = configured
    contract, request, row, source, authority, clock, _ = data
    client = TestClient(create_model_execution_host(runtime, clinical_publisher=publisher))
    result = client.post("/v1/model-executions", json=request).json()
    assert result["kind"] in {"BodyState", "ModelCounterfactual"}
    path = "/v1/model-executions/" + quote(result["id"], safe="")
    response = client.get(path + "/clinical-reference")
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    packet = response.json()
    reference, resolved = packet["reference"], packet["resolved_object"]
    validate_clinical_reference(reference, resolved, evaluated_at=clock[0])
    semantic_validate(resolved)
    assert packet["ehr_id"] == row["source"]["clinical_version"]["ehr_id"]
    assert reference["content_digest"] == canonical_digest(resolved)
    assert reference["uncertainty"]["coverage"] == result.get("scenario", result)["uncertainty"]["coverage"]
    assert parse_timestamp(reference["validity"]["valid_until"]) == binding.current.expires_at < authority.current.valid_until
    assert reference["producer"]["input_digest"] == resolved["model_receipts"][0]["input_digest"]
    assert reference["evidence_lineage"][0]["content_digest"] == canonical_digest(row)
    assert resolved["evidence"][0]["source_provenance"]["source"] == row["source"]
    if result["kind"] == "ModelCounterfactual":
        assert reference["epistemic_class"] == "counterfactual"
        assert resolved == result["scenario"] and resolved["expected_effects"][0]["delta"] == -1
        assert "authority_ref" not in resolved["perturbation"]
        assert reference["producer"]["receipt_ref"].endswith("#/scenario/model_receipts/0")
    else:
        assert reference["epistemic_class"] == "inference" and resolved == result
    assert client.get(reference["canonical_ref"]).json() == resolved
    clock[0] += timedelta(seconds=1)
    assert client.get(path + "/clinical-reference").json() == packet
    packet["reference"]["uncertainty"]["coverage"] = 1
    assert publisher.publish(result["id"])["reference"]["uncertainty"]["coverage"] == 0.8
    assert "model-clinical-references.read" in client.get("/v1/capabilities").json()["capabilities"]


@pytest.mark.parametrize("purpose", ["software_test", "research"])
def test_existing_execution_cannot_acquire_clinical_purpose_at_publication(configured, purpose):
    data, runtime, publisher, binding = configured
    _, request, _, _, authority, _, _ = data
    request["purpose"] = purpose
    authority.current = replace(authority.current, purpose=purpose)
    result = runtime.execute(request)
    with pytest.raises(ModelExecutionError, match="cannot be relabeled"): publisher.publish(result["id"])
    assert binding.calls == 0


def test_unknown_source_uncertainty_never_becomes_known_reference_uncertainty(configured):
    data, runtime, publisher, _ = configured
    row = data[2]
    row["uncertainty"].update(epistemic=None, aleatoric=None, coverage=None, out_of_distribution="unknown")
    result = runtime.execute(data[1])
    with pytest.raises(ModelExecutionError, match="Unknown"): publisher.publish(result["id"])


@pytest.mark.parametrize("field,value", [("subject", "subject:other"), ("tenant_id", "other"), ("ehr_id", "other"),
    ("status", "revoked"), ("proof_digest", ""), ("reference", "not a URI")])
def test_subject_binding_must_be_current_exact_and_well_formed(configured, field, value):
    data, runtime, publisher, binding = configured
    result = runtime.execute(data[1])
    binding.current = replace(binding.current, **{field: value})
    with pytest.raises(ModelExecutionError): publisher.publish(result["id"])


@pytest.mark.parametrize("case", ["expired", "exact_expiry", "future", "naive"])
def test_subject_binding_time_boundaries(configured, case):
    data, runtime, publisher, binding = configured
    result = runtime.execute(data[1]); now = data[5][0]
    if case == "expired": binding.current = replace(binding.current, expires_at=now - timedelta(seconds=1))
    elif case == "exact_expiry": binding.current = replace(binding.current, expires_at=now)
    elif case == "future": binding.current = replace(binding.current, verified_at=now + timedelta(seconds=1))
    else: binding.current = replace(binding.current, verified_at=now.replace(tzinfo=None))
    with pytest.raises(ModelExecutionError): publisher.publish(result["id"])


@pytest.mark.parametrize("change", ["source", "source_content", "qualification", "dependency", "binding", "binding_unavailable"])
def test_revocation_and_changes_stop_reference_and_canonical_object_reads(configured, change):
    data, runtime, publisher, binding = configured
    _, request, row, source, authority, _, _ = data
    result = runtime.execute(request)
    packet = publisher.publish(result["id"])
    if change == "source": source.unavailable = True
    elif change == "source_content": row["uncertainty"]["coverage"] = 0.7
    elif change == "qualification": authority.current = replace(authority.current, status="revoked")
    elif change == "dependency": authority.current = replace(authority.current, dependency_digests=())
    elif change == "binding": binding.current = replace(binding.current, status="revoked")
    else:
        def unavailable(*args): raise OSError("identity provider down")
        binding.resolve = unavailable
    client = TestClient(create_model_execution_host(runtime, clinical_publisher=publisher))
    for url in [packet["reference"]["canonical_ref"], "/v1/model-executions/" + quote(result["id"], safe="") + "/clinical-reference"]:
        response = client.get(url)
        assert response.json()["kind"] == "Abstention"
        assert response.headers["cache-control"] == "no-store"
        assert "reference" not in response.json() and "resolved_object" not in response.json()


@pytest.mark.parametrize("change", ["binding", "source", "qualification", "expires_during_return"])
def test_changes_during_publication_fail_before_return(configured, change):
    data, runtime, publisher, binding = configured
    _, request, _, source, authority, clock, _ = data
    result = runtime.execute(request)
    original = binding.resolve
    def mutate(*args):
        value = original(*args)
        if binding.calls == 2:
            if change == "binding": return replace(value, proof_digest="sha256:" + "6" * 64)
            if change == "source": source.unavailable = True
            if change == "qualification": authority.current = replace(authority.current, status="revoked")
            if change == "expires_during_return": clock[0] = binding.current.expires_at
        return value
    binding.resolve = mutate
    with pytest.raises(ModelExecutionError): publisher.publish(result["id"])


def test_forecast_is_not_mislabeled_as_a_core_clinical_state(forecast_setup):
    data, runtime, publisher, _ = prepare(forecast_setup)
    result = runtime.execute(data[1])
    with pytest.raises(ModelExecutionError, match="no supported standalone"): publisher.publish(result["id"])


def test_clinical_publication_is_opt_in_and_bound_to_exact_host_runtime(state_setup):
    data, runtime, publisher, _ = prepare(state_setup)
    result = runtime.execute(data[1])
    path = "/v1/model-executions/" + quote(result["id"], safe="") + "/clinical-reference"
    client = TestClient(create_model_execution_host(runtime))
    assert client.get(path).status_code == 404
    assert "model-clinical-references.read" not in client.get("/v1/capabilities").json()["capabilities"]
    assert TestClient(create_app(discovery_only=True)).get(path).status_code == 404
    with pytest.raises(ValueError): create_model_execution_host(data[-1](), clinical_publisher=publisher)


@pytest.mark.parametrize("origin", ["http://remote.example", "https://u:p@example.org", "https://example.org?x=1", "https://example.org#x", "https://bad host"])
def test_canonical_reference_origin_is_host_pinned_and_secure(state_setup, origin):
    _, runtime, _, binding = prepare(state_setup)
    with pytest.raises(ModelExecutionError): QualifiedClinicalReferencePublisher(runtime, binding, origin)
