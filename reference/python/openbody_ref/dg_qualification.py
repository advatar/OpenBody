"""Current native DG qualification in the actual model runtime.

Trusted command, issuer key, policies, model bindings and environment are host
configuration. Clinical requests cannot supply these values. A qualification is
model eligibility, never a provider-effect authorization.
"""
from __future__ import annotations

import base64
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import selectors
import signal
import subprocess
import time
from typing import Any, Callable, Mapping

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
import rfc8785

from .model_family import ModelExecutionError, QualificationLease, validate_contract
from .validation import canonical_digest, parse_timestamp

REQUEST_DOMAIN = "decision_graph.qualification_request.v1"
RESPONSE_DOMAIN = "decision_graph.current_qualification.v1"
MAX_BYTES = 524288
_ENVIRONMENT = frozenset("DECISION_GRAPH_" + name for name in (
    "TENANT", "DB_URL", "DB_NAMESPACE", "DB_DATABASE", "DB_USERNAME", "DB_PASSWORD", "DB_TOKEN",
    "REVIEW_POLICY", "HUMAN_KEYS", "EXECUTION_POLICY", "EXECUTION_KEY_FILE", "EXECUTION_PRINCIPAL",
    "CREDENTIAL_CONFIG", "SIGNING_KEY_FILE", "PUBLIC_KEY_FILE", "KID", "ANCHOR_SINK"))


def _refuse() -> ModelExecutionError:
    return ModelExecutionError("unqualified", "Current DG model qualification refused")


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _decode(value: Any, length: int) -> bytes:
    if not isinstance(value, str) or len(value) > length * 2:
        raise _refuse()
    decoded = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    if len(decoded) != length or _b64(decoded) != value:
        raise _refuse()
    return decoded


def dg_digest(value: Any) -> str:
    return "sha256:" + _b64(hashlib.sha256(rfc8785.dumps(value)).digest())


def qualification_candidate(contract: dict[str, Any], tenant_id: str, subject: str) -> dict[str, Any]:
    """Application vocabulary for a reviewed human-model candidate; not a VC schema."""
    validate_contract(contract)
    return {"domain": "openbody.dg_model_qualification.v1", "tenant_id": tenant_id, "subject": subject,
            "contract_digest": canonical_digest(contract), "artifact_digest": contract["model"]["artifact_digest"],
            "purposes": deepcopy(contract["context_of_use"]), "populations": deepcopy(contract["supported_population"]),
            "questions": deepcopy(contract["supported_question"]), "horizons_seconds": deepcopy(contract["prediction_horizon_seconds"]),
            "dependencies": deepcopy(contract["dependencies"]), "qualification_evidence": deepcopy(contract["qualification_evidence"])}


def qualification_evidence(candidate: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Descriptors whose exact retained bytes must be dependencies of DG review.

    These are reviewed content identities, not evidence of scientific truth.
    The trusted model loader remains responsible for actual dependency bytes.
    """
    descriptors = {}
    for group, domain in (("dependencies", "openbody.model_dependency.v1"),
                          ("qualification_evidence", "openbody.model_evidence.v1")):
        for item in candidate[group]:
            reference = item["ref"]
            if reference in descriptors:
                raise ValueError("Qualification evidence references must be unique")
            descriptors[reference] = {"domain": domain, "reference": reference,
                                      "content_digest": item["digest"], "kind": item.get("kind", "dependency")}
    return descriptors


@dataclass(frozen=True)
class DgModelBinding:
    change_id: str
    effect: dict[str, Any]


@dataclass(frozen=True)
class DgQualificationConfig:
    command: tuple[str, ...]
    principal: str
    policy: dict[str, Any]
    public_key_pem: str
    environment: Mapping[str, str]
    timeout_ms: int = 3000


def _exchange(command: tuple[str, ...], environment: dict[str, str], request: bytes, timeout: float) -> bytes:
    """Bound all pipe activity; kill the owned process group on timeout/refusal."""
    if len(request) > MAX_BYTES:
        raise _refuse()
    child = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, env=environment, start_new_session=True)
    deadline = time.monotonic() + timeout
    output = bytearray()
    written = 0
    try:
        with selectors.DefaultSelector() as selector:
            os.set_blocking(child.stdin.fileno(), False)
            os.set_blocking(child.stdout.fileno(), False)
            selector.register(child.stdin, selectors.EVENT_WRITE)
            selector.register(child.stdout, selectors.EVENT_READ)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise _refuse()
                for key, _ in selector.select(remaining):
                    if key.fileobj is child.stdin:
                        written += os.write(key.fd, request[written:written + 65536])
                        if written == len(request):
                            selector.unregister(child.stdin)
                            child.stdin.close()
                    else:
                        chunk = os.read(key.fd, min(65536, MAX_BYTES + 1 - len(output)))
                        output.extend(chunk)
                        if len(output) > MAX_BYTES:
                            raise _refuse()
                        if not chunk:
                            selector.unregister(child.stdout)
                            child.stdout.close()
            remaining = deadline - time.monotonic()
            if remaining <= 0 or child.wait(timeout=remaining) != 0:
                raise _refuse()
        return bytes(output)
    finally:
        if child.returncode is None:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.wait()
        for pipe in (child.stdin, child.stdout):
            if pipe is not None:
                pipe.close()


def _object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise _refuse()
        value[key] = item
    return value


class DgQualificationAuthority:
    def __init__(self, tenant_id: str, subject: str, config: DgQualificationConfig,
                 contracts: list[dict[str, Any]], bindings: dict[str, DgModelBinding], *,
                 clock: Callable[[], datetime] | None = None):
        try:
            if os.name != "posix" or not tenant_id or not subject.startswith("subject:") or not config.principal:
                raise _refuse()
            if not config.command or len(config.command) > 64 or not Path(config.command[0]).is_absolute():
                raise _refuse()
            if any(not isinstance(v, str) or "\0" in v or len(v) > 65536 for v in config.command):
                raise _refuse()
            self._policy = deepcopy(config.policy)
            if set(self._policy) != {"id", "version", "audience", "kid", "credential_policy", "grant_lifetime_seconds", "use_lifetime_seconds", "routes"}:
                raise _refuse()
            for name in ("id", "version", "audience", "kid"):
                if not isinstance(self._policy[name], str) or not self._policy[name]:
                    raise _refuse()
            _decode(self._policy["credential_policy"].removeprefix("sha256:"), 32)
            if not self._policy["credential_policy"].startswith("sha256:"):
                raise _refuse()
            lifetime = self._policy["use_lifetime_seconds"]
            grant = self._policy["grant_lifetime_seconds"]
            if type(lifetime) is not int or not 1 <= lifetime <= 10 or type(grant) is not int or not 1 <= grant <= 300:
                raise _refuse()
            if type(config.timeout_ms) is not int or not 1 <= config.timeout_ms <= lifetime * 1000:
                raise _refuse()
            if len(config.public_key_pem) > 8192:
                raise _refuse()
            self._key = serialization.load_pem_public_key(config.public_key_pem.encode())
            if not isinstance(self._key, Ed25519PublicKey):
                raise _refuse()
            self._environment = dict(config.environment)
            if set(self._environment) - _ENVIRONMENT or any(not isinstance(v, str) or "\0" in v or len(v) > 65536 for v in self._environment.values()):
                raise _refuse()
            self._models = {}
            for contract in contracts:
                candidate = qualification_candidate(contract, tenant_id, subject)
                qualification_evidence(candidate)
                binding = bindings[contract["model"]["id"]]
                effect = deepcopy(binding.effect)
                if set(effect) != {"id", "action", "provider", "tool", "resource", "arguments"} or not binding.change_id:
                    raise _refuse()
                if (effect["action"], effect["provider"], effect["tool"]) != ("model.qualification.read", "openbody", "openbody_resolve_model_qualification"):
                    raise _refuse()
                if rfc8785.dumps(effect["arguments"]) != rfc8785.dumps(candidate):
                    raise _refuse()
                routes = [r for r in self._policy["routes"] if all(r[k] == effect[k] for k in ("action", "provider", "tool"))]
                if len(routes) != 1 or set(routes[0]) != {"action", "provider", "tool", "runtime_action", "power"}:
                    raise _refuse()
                digest = candidate["contract_digest"]
                if digest in self._models:
                    raise _refuse()
                self._models[digest] = (candidate, DgModelBinding(binding.change_id, effect))
            if not self._models or set(bindings) != {c["model"]["id"] for c in contracts}:
                raise _refuse()
            self._tenant, self._subject = tenant_id, subject
            self._command, self._principal = tuple(config.command), config.principal
            self._timeout = config.timeout_ms / 1000
            self._clock = clock or (lambda: datetime.now(timezone.utc))
        except Exception as error:
            raise ValueError("Invalid trusted DG qualification configuration") from error

    def resolve(self, contract_digest: str, request: dict[str, Any]) -> QualificationLease:
        try:
            candidate, binding = self._models[contract_digest]
            if request["subject"] != self._subject:
                raise _refuse()
            for field, allowed in (("purpose", "purposes"), ("population", "populations"), ("question", "questions"), ("horizon_seconds", "horizons_seconds")):
                if request[field] not in candidate[allowed] or (field == "horizon_seconds" and type(request[field]) is not int):
                    raise _refuse()
            started = self._clock()
            if started.tzinfo is None:
                raise _refuse()
            started = started.astimezone(timezone.utc)
            end = started + timedelta(seconds=self._policy["use_lifetime_seconds"])
            stamp = lambda v: v.isoformat(timespec="milliseconds").replace("+00:00", "Z")
            challenge = {"domain": REQUEST_DOMAIN, "tenant_id": self._tenant, "principal": self._principal,
                         "audience": self._policy["audience"], "policy_digest": dg_digest(self._policy),
                         "change_id": binding.change_id, "effect": binding.effect, "clinical": None,
                         "nonce": _b64(secrets.token_bytes(32)),
                         "operation_id": "openbody-qualification:" + canonical_digest({"contract_digest": contract_digest, "request": request}),
                         "issued_at": stamp(started), "expires_at": stamp(end)}
            raw = _exchange(self._command, self._environment, rfc8785.dumps(challenge), self._timeout)
            signed = json.loads(raw, object_pairs_hook=_object, parse_constant=lambda _: (_ for _ in ()).throw(_refuse()))
            if not isinstance(signed, dict) or set(signed) != {"payload", "signature"}:
                raise _refuse()
            payload = signed["payload"]
            fields = {"domain", "kid", "request", "subject", "candidate", "candidate_digest", "reviewed_evidence", "decision_root", "evidence_root", "resolution_root", "qualification_valid_from", "qualification_valid_until", "issued_at", "expires_at"}
            if not isinstance(payload, dict) or set(payload) != fields:
                raise _refuse()
            self._key.verify(_decode(signed["signature"], 64), rfc8785.dumps(payload))
            if payload["domain"] != RESPONSE_DOMAIN or payload["kid"] != self._policy["kid"] or rfc8785.dumps(payload["request"]) != rfc8785.dumps(challenge):
                raise _refuse()
            if payload["subject"] != self._subject or rfc8785.dumps(payload["candidate"]) != rfc8785.dumps(candidate) or payload["candidate_digest"] != dg_digest(candidate):
                raise _refuse()
            expected = qualification_evidence(candidate)
            reviewed = payload["reviewed_evidence"]
            if not isinstance(reviewed, list) or len(reviewed) != len(expected):
                raise _refuse()
            seen = set()
            for item in reviewed:
                if set(item) != {"commitment", "content_digest"}:
                    raise _refuse()
                commitment = item["commitment"]
                if set(commitment) != {"reference", "entity", "id", "record_id", "receipt_hash", "row_digest", "payload_ref", "payload_hash"}:
                    raise _refuse()
                reference = commitment["reference"]
                if reference in seen or reference not in expected or commitment["entity"] != "finding" or commitment["id"] != reference:
                    raise _refuse()
                if item["content_digest"] != dg_digest(expected[reference]):
                    raise _refuse()
                for name in ("row_digest", "payload_hash"):
                    if not commitment[name].startswith("sha256:"):
                        raise _refuse()
                    _decode(commitment[name][7:], 32)
                if not re.fullmatch(r"[0-9a-f]{64}", commitment["receipt_hash"]) or not commitment["record_id"] or not commitment["payload_ref"]:
                    raise _refuse()
                seen.add(reference)
            for name in ("decision_root", "evidence_root"):
                if not payload[name].startswith("sha256:"):
                    raise _refuse()
                _decode(payload[name][7:], 32)
            if not re.fullmatch(r"[0-9a-f]{64}", payload["resolution_root"]):
                raise _refuse()
            issued, expires, valid_from, valid_until = (parse_timestamp(payload[name]) for name in ("issued_at", "expires_at", "qualification_valid_from", "qualification_valid_until"))
            now = self._clock()
            if any(v.tzinfo is None for v in (issued, expires, valid_from, valid_until, now)):
                raise _refuse()
            if not (parse_timestamp(challenge["issued_at"]) <= issued <= now < expires <= end and valid_from <= now < valid_until and expires <= valid_until):
                raise _refuse()
            return QualificationLease(
                "urn:dg:model-decision:" + payload["decision_root"][7:], payload["decision_root"], contract_digest,
                self._subject, self._tenant, request["purpose"], request["population"], request["question"], request["horizon_seconds"],
                candidate["artifact_digest"], tuple((v["ref"], v["digest"]) for v in candidate["dependencies"]),
                tuple((v["ref"], v["digest"]) for v in candidate["qualification_evidence"]), valid_from, valid_until, "active",
                resolution_reference="urn:dg:qualification-resolution:" + payload["resolution_root"])
        except Exception as error:
            raise _refuse() from error
