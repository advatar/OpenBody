"""Actual native DG + EUWallet command at the OpenBody HTTP model boundary.

Explicit local qualification, with public synthetic software keys and arithmetic.
Set DG_WALLET_TEST_BIN, DG_MODEL_FIXTURE_BIN and DG_SURREAL_TEST_BIN to run.
"""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import socket
import subprocess
import time
from urllib.request import Request, urlopen

from fastapi.testclient import TestClient
import pytest

from test_model_family import setup as model_setup, ARTIFACT, synthetic_model
from openbody_ref.dg_qualification import DgModelBinding, DgQualificationConfig, qualification_candidate, qualification_evidence
from openbody_ref.host import create_dg_model_execution_host
from openbody_ref.model_family import ModelRegistration


@pytest.fixture
def native(model_setup, tmp_path):
    names = ('DG_WALLET_TEST_BIN', 'DG_MODEL_FIXTURE_BIN', 'DG_SURREAL_TEST_BIN')
    if not any(name in os.environ for name in names):
        pytest.skip('Explicit native DG/wallet/SurrealDB binaries required')
    binaries = [Path(os.environ[name]) for name in names]
    assert all(p.is_absolute() and p.is_file() for p in binaries)
    wallet, fixture, surreal = map(str, binaries)
    contract, request, row, source, _, _, _ = model_setup
    now = datetime.now(timezone.utc)
    row['effective_time'] = (now - timedelta(seconds=60)).isoformat()
    row['normalization']['source']['effective_time'] = row['effective_time']
    tenant, subject = row['source']['clinical_version']['tenant_id'], row['subject']
    candidate = qualification_candidate(contract, tenant, subject)
    effect = {'id': 'model-qualification', 'action': 'model.qualification.read', 'provider': 'openbody',
              'tool': 'openbody_resolve_model_qualification', 'resource': 'people/subject/model', 'arguments': candidate}
    with socket.socket() as address:
        address.bind(('127.0.0.1', 0)); port = address.getsockname()[1]
    endpoint = f'http://127.0.0.1:{port}'
    with (tmp_path / 'database.log').open('wb') as log:
        database = subprocess.Popen([surreal, 'start', '--no-banner', '--unauthenticated', '--allow-guests',
                                     '--bind', f'127.0.0.1:{port}', 'memory'], env={}, stdin=subprocess.DEVNULL, stdout=log, stderr=log)
    try:
        deadline = time.monotonic() + 10
        while True:
            assert database.poll() is None, 'Owned test database exited'
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=0.1): break
            except OSError:
                assert time.monotonic() < deadline
                time.sleep(0.02)
        query = {'id': 1, 'method': 'query', 'params': ['DEFINE NAMESPACE wallet_model_test; USE NS wallet_model_test; DEFINE DATABASE models;']}
        with urlopen(Request(endpoint + '/rpc', data=json.dumps(query).encode(), headers={'content-type': 'application/json'}), timeout=10) as response:
            reply = json.load(response)
        assert 'error' not in reply and all(r['status'] == 'OK' for r in reply['result']), reply
        seeded = False
        calls = [0]
        def build(*, omit_review_dependency=False, during=None):
            nonlocal seeded
            if not seeded:
                seed = {'candidate': candidate, 'effect': effect, 'evidence': qualification_evidence(candidate),
                        'omit_review_dependency': omit_review_dependency}
                result = subprocess.run([fixture, '--seed', str(tmp_path), endpoint], input=json.dumps(seed).encode(),
                                        capture_output=True, timeout=30, env={})
                assert result.returncode == 0, result.stderr.decode()
                seeded = True
            command = [wallet, 'resolve-qualification', '--tenant', tenant, '--db-url', endpoint,
                       '--namespace', 'wallet_model_test', '--database', 'models', '--execution-principal', 'operator']
            for flag, filename in [('credential-config','host.json'), ('execution-policy','execution.json'),
                                   ('execution-key','execution.pem'), ('review-policy','review.json'), ('human-keys','humans.json')]:
                command += ['--' + flag, str(tmp_path / filename)]
            config = DgQualificationConfig(tuple(command), 'operator', json.loads((tmp_path/'execution.json').read_text()),
                                            (tmp_path/'public.pem').read_text(), {}, 10000)
            def evaluate(inputs, parameters):
                calls[0] += 1
                if during: during()
                return synthetic_model(inputs, parameters)
            return TestClient(create_dg_model_execution_host(subject, tenant, source,
                [ModelRegistration(contract, ARTIFACT, evaluate)], config,
                {contract['model']['id']: DgModelBinding('model-qualification', effect)}))
        def mutate(mode, value):
            result = subprocess.run([fixture, '--' + mode, str(tmp_path), value], capture_output=True, timeout=10, env={})
            assert result.returncode == 0, result.stderr.decode()
        yield build, mutate, request, contract, calls, tmp_path
    finally:
        if database.poll() is None: database.terminate()
        try: database.wait(timeout=5)
        except subprocess.TimeoutExpired: database.kill(); database.wait(timeout=5)


@pytest.mark.parametrize('change', ['privacy', 'operator', 'subject_consent', 'evidence', 'withdraw', 'inputs'])
def test_real_current_graph_and_wallet_guard_execution_and_retained_reads(native, change):
    build, mutate, request, contract, calls, directory = native
    with build() as client:
        response = client.post('/v1/model-executions', json=request)
        assert response.status_code == 200, response.text
        state = response.json()
        assert state['kind'] == 'BodyState', state
        assert calls[0] == 1
        assert state['uncertainty']['coverage'] is None
        assert state['subsystems'][0]['state_vector']['synthetic_shifted_value'] == 37
        assert state['evidence'][0]['source_provenance']['qualification_resolution_ref'].startswith('urn:dg:qualification-resolution:')
        assert client.get('/v1/model-executions/' + state['id']).json() == state
        if change == 'inputs': (directory/'inputs.json').unlink()
        elif change == 'evidence': mutate('revoke-evidence', contract['dependencies'][0]['ref'])
        elif change == 'withdraw': mutate('withdraw', 'subject_consent')
        else: mutate('status', change)
        blocked = client.post('/v1/model-executions', json=request).json()
        assert blocked['kind'] == 'Abstention', blocked
        assert client.get('/v1/model-executions/' + state['id']).json()['kind'] == 'Abstention'
        assert calls[0] == 1


def test_real_signed_candidate_cannot_omit_native_review_of_declared_dependencies(native):
    build, _, request, _, calls, _ = native
    with build(omit_review_dependency=True) as client:
        state = client.post('/v1/model-executions', json=request).json()
        assert state['kind'] == 'Abstention', state
        assert calls[0] == 0


def test_real_withdrawal_during_model_call_suppresses_the_result(native):
    build, mutate, request, _, calls, _ = native
    with build(during=lambda: mutate('withdraw', 'subject_consent')) as client:
        state = client.post('/v1/model-executions', json=request).json()
        assert state['kind'] == 'Abstention', state
        assert calls[0] == 1
