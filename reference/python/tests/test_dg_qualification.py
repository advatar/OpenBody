"""Wire-verifier tests use explicit synthetic signed replies; native composition is separate."""
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
import json
import os
from pathlib import Path
import sys
import time

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
import pytest

from test_model_family import setup as model_setup, ARTIFACT, synthetic_model
from openbody_ref.dg_qualification import (DgModelBinding, DgQualificationAuthority, DgQualificationConfig,
    _exchange, dg_digest, qualification_candidate, qualification_evidence)
from openbody_ref.host import create_dg_model_execution_host
from openbody_ref.model_family import ModelExecutionError, ModelRegistration, QualifiedModelRuntime
from openbody_ref.validation import canonical_digest

SCRIPT = r'''
import base64, hashlib, json, sys, time, uuid
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import rfc8785
config=json.load(open(sys.argv[1])); q=json.load(sys.stdin); mode=config.get('mode','valid')
if mode=='refuse': sys.exit(1)
if mode=='late': time.sleep(5)
if mode=='oversize': print('x'*524289); sys.exit()
if mode=='malformed': print('bad'); sys.exit()
assert not any(k in __import__('os').environ for k in ['COSMIC_CLIENT_SECRET','OPENBODY_PROVIDER_TOKEN'])
b64=lambda b:base64.urlsafe_b64encode(b).decode().rstrip('=')
digest=lambda v:'sha256:'+b64(hashlib.sha256(rfc8785.dumps(v)).digest())
p={'domain':'decision_graph.current_qualification.v1','kid':'dg-test','request':q,'subject':config['subject'],'candidate':config['candidate'],
 'reviewed_evidence':config['reviewed_evidence'],'candidate_digest':digest(config['candidate']),'decision_root':digest('decision'),'evidence_root':digest('evidence'),
 'resolution_root':hashlib.sha256(uuid.uuid4().bytes).hexdigest(),'qualification_valid_from':config['valid_from'],'qualification_valid_until':config['valid_until'],
 'issued_at':q['issued_at'],'expires_at':q['expires_at']}
if mode=='evidence_missing': p['reviewed_evidence']=[]
if mode=='evidence_digest': p['reviewed_evidence'][0]['content_digest']=digest('unreviewed')
if mode=='evidence_duplicate': p['reviewed_evidence'][1]=p['reviewed_evidence'][0]
if mode=='evidence_reference': p['reviewed_evidence'][0]['commitment']['reference']='unreviewed'
if mode=='domain': p['domain']='decision_graph.effect_authorization.v1'
if mode=='subject': p['subject']='subject:other'
if mode=='candidate': p['candidate']['artifact_digest']='sha256:'+'f'*64; p['candidate_digest']=digest(p['candidate'])
if mode=='candidate_type': p['candidate']['horizons_seconds']=[False]
if mode=='nonce': p['request']['nonce']=b64(bytes(32))
if mode=='context': p['request']['operation_id']='other-model-input'
if mode=='stale': p['expires_at']=config['valid_from']
if mode=='window': p['expires_at']=config['valid_until']
if mode=='deadline': p['qualification_valid_until']=config['valid_from']
if mode=='extra': p['allow']=True
if mode=='root': p['resolution_root']='not-a-commitment'
signature=Ed25519PrivateKey.from_private_bytes(bytes([41])*32).sign(rfc8785.dumps(p))
if mode=='signature': signature=bytes(64)
text=json.dumps({'payload':p,'signature':b64(signature)})
if mode=='duplicate': text=text[:-1]+',"signature":"ignored"}'
print(text)
'''


@pytest.fixture
def setup(model_setup, tmp_path):
    contract, request, row, source, _, clock, _ = model_setup
    subject, tenant = row["subject"], row["source"]["clinical_version"]["tenant_id"]
    candidate = qualification_candidate(contract, tenant, subject)
    effect = {"id": "model-qualification", "action": "model.qualification.read", "provider": "openbody",
              "tool": "openbody_resolve_model_qualification", "resource": "people/subject/model", "arguments": candidate}
    policy = {"id": "model-qualification", "version": "1", "kid": "dg-test", "audience": "openbody-model-host",
              "credential_policy": dg_digest("required-wallet-inputs"), "grant_lifetime_seconds": 120, "use_lifetime_seconds": 5,
              "routes": [{**{k: effect[k] for k in ("action", "provider", "tool")}, "runtime_action": "qualification.read", "power": "READ"}]}
    key = Ed25519PrivateKey.from_private_bytes(bytes([41]) * 32)
    script = tmp_path / "signed_reply.py"; script.write_text(SCRIPT)
    reply_file = tmp_path / "reply.json"
    reviewed = [{"commitment": {"reference": ref, "entity": "finding", "id": ref, "record_id": "test-row",
                 "receipt_hash": "a" * 64, "row_digest": dg_digest(ref), "payload_ref": "test-payload",
                 "payload_hash": dg_digest("encrypted-test-bytes")}, "content_digest": dg_digest(descriptor)}
                for ref, descriptor in qualification_evidence(candidate).items()]
    reply = {"subject": subject, "candidate": candidate, "reviewed_evidence": reviewed,
             "valid_from": (clock[0] - timedelta(seconds=10)).isoformat(), "valid_until": (clock[0] + timedelta(hours=1)).isoformat()}
    def mode(value):
        reply["mode"] = value; reply_file.write_text(json.dumps(reply))
    mode("valid")
    config = DgQualificationConfig((sys.executable, str(script), str(reply_file)), "operator", policy,
        key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode(), {}, 2000)
    bindings = {contract["model"]["id"]: DgModelBinding("qualified-model", effect)}
    def authority(config_override=None):
        return DgQualificationAuthority(tenant, subject, config_override or config, [contract], bindings, clock=lambda: clock[0])
    return contract, request, source, clock, config, bindings, authority, mode


def test_actual_http_model_boundary_rechecks_qualification_and_retains_its_audit_reference(setup):
    contract, request, source, clock, config, bindings, _, mode = setup
    app = create_dg_model_execution_host(request["subject"], bindings[contract["model"]["id"]].effect["arguments"]["tenant_id"],
        source, [ModelRegistration(contract, ARTIFACT, synthetic_model)], config, bindings, clock=lambda: clock[0])
    with TestClient(app) as client:
        response = client.post('/v1/model-executions', json=request)
        assert response.status_code == 200, response.text
        state = response.json(); assert state['kind'] == 'BodyState'
        assert state['evidence'][0]['source_provenance']['qualification_resolution_ref'].startswith('urn:dg:qualification-resolution:')
        assert state['uncertainty']['coverage'] is None
        assert client.get('/v1/model-executions/' + state['id']).json() == state
        mode('refuse')
        assert client.get('/v1/model-executions/' + state['id']).json()['kind'] == 'Abstention'
        assert client.post('/v1/model-executions', json=request).json()['kind'] == 'Abstention'


@pytest.mark.parametrize('mode_name', ['evidence_missing','evidence_digest','evidence_duplicate','evidence_reference','domain','subject','candidate','candidate_type','nonce','context','stale','window','deadline','extra','root','signature','duplicate','malformed','oversize','refuse'])
def test_signed_or_malformed_replies_cannot_cross_the_model_boundary(setup, mode_name):
    contract, request, source, clock, _, _, authority, mode = setup
    mode(mode_name)
    def never(*_): pytest.fail('refused qualification reached model')
    runtime = QualifiedModelRuntime(request['subject'], source.resolve(request['observations'][0])['source']['clinical_version']['tenant_id'],
        source, authority(), [ModelRegistration(contract,ARTIFACT,never)],clock=lambda:clock[0])
    source.calls = 0
    with pytest.raises(ModelExecutionError): runtime.execute(request)
    assert source.calls == 0


def test_current_qualification_change_during_model_execution_suppresses_result(setup):
    contract, request, source, clock, _, bindings, authority, mode = setup
    def changed(inputs, parameters):
        mode('refuse'); return synthetic_model(inputs, parameters)
    runtime = QualifiedModelRuntime(request['subject'], bindings[contract['model']['id']].effect['arguments']['tenant_id'],
        source, authority(), [ModelRegistration(contract,ARTIFACT,changed)],clock=lambda:clock[0])
    with pytest.raises(ModelExecutionError): runtime.execute(request)


def test_new_resolution_receipt_does_not_change_the_reviewed_qualification_identity(setup):
    contract, request, _, _, _, _, authority, _ = setup
    service=authority()
    first=service.resolve(canonical_digest(contract),request)
    second=service.resolve(canonical_digest(contract),request)
    assert first == second
    assert first.resolution_reference != second.resolution_reference


def test_bounded_process_timeout_and_no_inherited_provider_environment(setup, monkeypatch):
    contract, request, _, _, config, _, authority, mode=setup
    monkeypatch.setenv('COSMIC_CLIENT_SECRET','synthetic-test-secret')
    monkeypatch.setenv('OPENBODY_PROVIDER_TOKEN','synthetic-test-token')
    authority().resolve(canonical_digest(contract),request)
    mode('late'); started=time.monotonic()
    with pytest.raises(ModelExecutionError): authority(replace(config,timeout_ms=100)).resolve(canonical_digest(contract),request)
    assert time.monotonic()-started < 2


@pytest.mark.parametrize('fault',['no_policy','key','relative','timeout','environment','candidate','effect'])
def test_untrusted_or_incomplete_host_configuration_refuses(setup,fault):
    contract, _, _, _, config, bindings, authority, _=setup
    if fault=='no_policy':
        p=deepcopy(config.policy);p.pop('credential_policy');config=replace(config,policy=p)
    elif fault=='key': config=replace(config,public_key_pem='untrusted')
    elif fault=='relative': config=replace(config,command=('relative-command',))
    elif fault=='timeout': config=replace(config,timeout_ms=5001)
    elif fault=='environment': config=replace(config,environment={'COSMIC_CLIENT_SECRET':'not-permitted'})
    elif fault=='candidate': bindings[contract['model']['id']].effect['arguments']['artifact_digest']='substituted'
    else: bindings[contract['model']['id']].effect['action']='clinical.intervene'
    with pytest.raises(ValueError): authority(config)
