"""Research-only, exact-byte reproduction gate; never a qualification authority."""
from __future__ import annotations
import hashlib
import json
import re
import subprocess
from pathlib import Path


def digest(data):
    return hashlib.sha256(data).hexdigest()


def _git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], stderr=subprocess.DEVNULL)


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate contract key')
        result[key] = value
    return result


def _known(value):
    if isinstance(value, dict):
        return bool(value) and all(_known(v) for v in value.values())
    if isinstance(value, list):
        return bool(value) and all(_known(v) for v in value)
    return isinstance(value, str) and bool(value.strip()) and value.strip().upper() not in {
        'UNKNOWN', 'ABSENT', 'BLOCKED', 'NOT ESTABLISHED'}


def validate(contract):
    """Only exact byte equality is implemented; numerical policies fail closed."""
    required = {'profile', 'source', 'artifacts', 'inputs', 'model_version', 'environment',
                'context', 'metric', 'unit', 'reference_sha256', 'comparison', 'provenance',
                'expected_outcomes'}
    if not isinstance(contract, dict) or set(contract) != required:
        raise ValueError('incomplete contract')
    if contract['profile'] != 'openbody.research-reproduction.v1':
        raise ValueError('unsupported profile')
    for key in ('source', 'model_version', 'environment', 'context', 'metric', 'unit', 'provenance'):
        if not _known(contract[key]):
            raise ValueError('unknown binding')
    if not isinstance(contract['source'], dict) or set(contract['source']) != {'identity', 'version', 'upstream_status'}:
        raise ValueError('source binding')
    if not isinstance(contract['environment'], dict) or set(contract['environment']) != {'runtime', 'solvers'}:
        raise ValueError('environment binding')
    if not isinstance(contract['context'], dict) or set(contract['context']) != {
            'species', 'population_sample', 'anatomy', 'modality', 'device_electrode', 'parameters'}:
        raise ValueError('context binding')
    if contract['comparison'] != {'method': 'exact_bytes', 'tolerance': 'zero',
                                  'justification': 'Exact identity of the authenticated reference bytes'}:
        raise ValueError('unsupported comparison')
    if contract['expected_outcomes'] != ['PASS', 'FAIL', 'BLOCKED', 'INCOMPARABLE']:
        raise ValueError('failure states')
    for key in ('artifacts', 'inputs'):
        if not isinstance(contract[key], dict) or not contract[key]:
            raise ValueError('missing digests')
        for name, sha in contract[key].items():
            if not name or not isinstance(sha, str) or not re.fullmatch('[0-9a-f]{64}', sha):
                raise ValueError('invalid digest')
    if not isinstance(contract['reference_sha256'], str) or not re.fullmatch('[0-9a-f]{64}', contract['reference_sha256']):
        raise ValueError('invalid reference digest')


def execute(repo, path, commit, *, inputs, artifacts, reference, environment, run):
    """Invoke trusted adapter only after loading a valid committed contract.

    Adapter owns runtime/artifact attestation and must execute only the supplied
    immutable inputs. This is not a sandbox, authentication service, or proof
    against an operator running a candidate outside this gate.
    """
    receipt = {'outcome': 'BLOCKED', 'candidate_executed': False, 'validated': False}
    try:
        if not isinstance(commit, str) or not re.fullmatch('[0-9a-f]{40}', commit):
            raise ValueError('full commit required')
        relative = Path(path)
        if relative.is_absolute() or '..' in relative.parts or ':' in str(relative):
            raise ValueError('repository-relative contract required')
        _git(repo, 'merge-base', '--is-ancestor', commit, 'HEAD')
        raw = _git(repo, 'show', f'{commit}:{relative.as_posix()}')
        # Reject symlinks and changes since declaration, including staged edits.
        if not _git(repo, 'ls-tree', commit, '--', str(relative)).startswith(b'100644 blob '):
            raise ValueError('regular contract required')
        local = Path(repo) / relative
        if local.is_symlink() or local.read_bytes() != raw or _git(repo, 'diff', commit, '--', str(relative)):
            raise ValueError('contract changed after declaration')
        contract = json.loads(raw, object_pairs_hook=_object)
        validate(contract)
        receipt.update(contract_commit=commit, contract_sha256=digest(raw), input_digests=contract['inputs'],
                       artifact_digests=contract['artifacts'], reference_sha256=contract['reference_sha256'],
                       environment=contract['environment'])
        if any(not isinstance(items, dict) or not all(isinstance(v, bytes) for v in items.values()) for items in (inputs, artifacts)):
            raise ValueError('artifact/input bytes required')
        frozen_inputs = dict(inputs)
        if {key: digest(value) for key, value in frozen_inputs.items()} != contract['inputs'] or {key: digest(value) for key, value in artifacts.items()} != contract['artifacts'] or environment != contract['environment']:
            return dict(receipt, outcome='INCOMPARABLE', reason='artifact_input_or_environment_mismatch')
        if not isinstance(reference, bytes) or digest(reference) != contract['reference_sha256']:
            return dict(receipt, reason='reference_not_authenticated')
    except (ValueError, TypeError, OSError, subprocess.CalledProcessError):
        return dict(receipt, reason='missing_or_invalid_preexecution_contract')
    # This is the only candidate invocation. No candidate-derived tolerance exists.
    receipt['candidate_executed'] = True
    try:
        output = run(frozen_inputs)
    except Exception:
        return dict(receipt, outcome='FAIL', reason='candidate_execution_failed')
    if output is None:
        return dict(receipt, reason='missing_candidate_output')
    if not isinstance(output, bytes):
        return dict(receipt, outcome='INCOMPARABLE', reason='unsupported_output_representation')
    return dict(receipt, outcome='PASS' if output == reference else 'FAIL',
                output_sha256=digest(output), output_bytes=len(output),
                interpretation='Exact computational artifact reproduction only; no model qualification')
