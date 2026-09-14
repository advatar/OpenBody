"""Admitted observation profile and an authoritative ProvidEHR source resolver.

The host accepts a clinical-version locator, never a caller's clinical values or
admission status. The resolver's configured origin and credentials define the
trust boundary. This profile adds no authority to the originating admission.
"""
from __future__ import annotations

from copy import deepcopy
import json
import math
import re
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote, urlsplit

import httpx
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = ROOT / "schemas" / "admitted-observation.schema.json"
SCHEMA = json.loads(SCHEMA_PATH.read_text())
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())
PROFILE = "openbody.admitted-observation.v1"


class ObservationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def validate_locator(value: Any) -> None:
    schema = {"$schema": SCHEMA["$schema"], **SCHEMA["$defs"]["ClinicalVersion"]}
    if not Draft202012Validator(schema).is_valid(value):
        raise ObservationError("invalid_source_locator", "An exact tenant/EHR/composition/version locator is required")
    component = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,254}", re.ASCII)
    if any(not component.fullmatch(value[key]) or "::" in value[key] for key in ("ehr_id", "composition_uid")):
        raise ObservationError("invalid_source_locator", "Clinical identifiers must be canonical URI-safe components")
    parts = value["version_uid"].split("::")
    if len(parts) != 3 or parts[0] != value["composition_uid"] or not component.fullmatch(parts[1]) or not re.fullmatch(r"[1-9][0-9]{0,9}", parts[2], re.ASCII) or int(parts[2]) > 2**32 - 1:
        raise ObservationError("invalid_source_locator", "Clinical version does not belong to the requested composition")


def validate_observation(value: Any, *, subject: str | None = None) -> None:
    if not VALIDATOR.is_valid(value):
        raise ObservationError("invalid_observation", "The source is not a normalized Observation in the supported profile")
    version = value["source"]["clinical_version"]
    validate_locator(version)
    if value["id"] != f"urn:openbody:observation:{version['version_uid']}":
        raise ObservationError("version_mismatch", "Observation identity is not bound to its clinical version")
    expected_subject = f"subject:providehr:ehr:{version['ehr_id']}"
    if value["subject"] != expected_subject or (subject is not None and value["subject"] != subject):
        raise ObservationError("subject_mismatch", "Observation does not represent the bound EHR/twin")
    normalization = value["normalization"]
    if (value["code"] != normalization["concept"] or value["quantity"] != normalization["quantity"]
            or value["effective_time"] != normalization["source"]["effective_time"]
            or value["source"]["resource_ref"] != normalization["source"]["source_id"]):
        raise ObservationError("admission_mismatch", "Observation differs from the admitted fact")
    if any(trace["rule_version"] != normalization["rule_pack"]["version"] for trace in normalization["trace"]):
        raise ObservationError("rule_pack_mismatch", "Transformation trace and rule pack versions disagree")
    numbers = [value["quantity"]["value"], normalization["source"]["quantity"]["value"]]
    numbers += [v for k, v in value["uncertainty"].items() if k in {"epistemic", "aleatoric", "coverage"} and v is not None]
    try:
        finite = all(math.isfinite(v) for v in numbers)
    except (OverflowError, TypeError):
        finite = False
    if not finite:
        raise ObservationError("invalid_number", "Observation values and uncertainty must be finite")
    parent = value["source"]["parent"]
    if parent is not None and parent["subject_reference"] != f"Patient/{value['source']['patient_external_id']}":
        raise ObservationError("subject_mismatch", "Contained observation and parent subjects disagree")


class ObservationSource(Protocol):
    def resolve(self, locator: dict[str, str]) -> dict[str, Any]: ...


class ProvidEHRObservationSource:
    """Resolve a stored projection through the existing authorized clinical API.

    The constructor binds one tenant and EHR. Input cannot select an origin,
    credentials, redirects, patient or arbitrary API operation. Responses must
    identify the exact immutable version and agree with its admission evidence.
    """
    def __init__(self, base_url: str, access_token: str, tenant_id: str, ehr_id: str,
                 *, transport: httpx.BaseTransport | None = None) -> None:
        url = urlsplit(base_url)
        if url.scheme not in {"http", "https"} or not url.netloc or url.username or url.password or url.query or url.fragment:
            raise ValueError("source origin must be an HTTP(S) base without embedded credentials, query or fragment")
        if url.scheme == "http" and url.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("remote clinical source resolution requires HTTPS")
        if not access_token or not tenant_id or not ehr_id:
            raise ValueError("source credentials and tenant/EHR binding are required")
        self.tenant_id = tenant_id
        self.ehr_id = ehr_id
        self._client = httpx.Client(base_url=base_url.rstrip("/") + "/", transport=transport,
                                   headers={"Authorization": f"Bearer {access_token}"},
                                   timeout=10.0, follow_redirects=False)

    def close(self) -> None:
        self._client.close()

    def resolve(self, locator: dict[str, str]) -> dict[str, Any]:
        validate_locator(locator)
        if locator["tenant_id"] != self.tenant_id or locator["ehr_id"] != self.ehr_id:
            raise ObservationError("source_scope_mismatch", "Source reference exceeds the configured tenant/EHR")
        fields = {key: quote(locator[key], safe="") for key in ("ehr_id", "composition_uid", "version_uid")}
        path = f"v1/ehr/{fields['ehr_id']}/composition/{fields['composition_uid']}/version/{fields['version_uid']}"
        try:
            response = self._client.get(path)
            response.raise_for_status()
            version = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise ObservationError("source_unavailable", "The authorized clinical source could not be resolved") from error
        if not isinstance(version, dict) or any(version.get(field) != locator[field] for field in ("ehr_id", "composition_uid", "version_uid")):
            raise ObservationError("version_mismatch", "The source returned another clinical version")
        composition = version.get("composition", {})
        if not isinstance(composition, dict) or composition.get("template_id") != "providehr.cosmic_observation.v1":
            raise ObservationError("source_not_admitted", "Only an admitted canonical clinical observation is a source")
        context = composition.get("context", {})
        if not isinstance(context, dict) or context.get("tenant_id") != self.tenant_id:
            raise ObservationError("source_scope_mismatch", "The source version has another tenant")
        value = context.get("openbody_observation")
        validate_observation(value, subject=f"subject:providehr:ehr:{self.ehr_id}")
        if value["source"]["clinical_version"] != locator:
            raise ObservationError("version_mismatch", "The stored projection identifies another clinical version")
        if (context.get("external_source_system") != value["source"]["system"]
                or context.get("external_resource_type") != "Observation"
                or context.get("upstream_version") != value["source"]["resource_version"]):
            raise ObservationError("admission_mismatch", "The projection has different source provenance")
        admission = context.get("semantic_admission", {})
        evidence = context.get("source_evidence", {})
        if (not isinstance(admission, dict) or admission.get("kind") != "observation"
                or admission.get("result") != value["normalization"]
                or not isinstance(evidence, dict) or f"sha256:{evidence.get('payload_hash')}" != value["source"]["resource_digest"]
                or evidence.get("parent") != value["source"]["parent"]):
            raise ObservationError("admission_mismatch", "The projection is not backed by this clinical version's admission")
        content = composition.get("content", {})
        canonical = content.get("observation") if isinstance(content, dict) else None
        if not isinstance(canonical, dict) or any(canonical.get(field) != expected for field, expected in {
            "code": value["code"], "value": value["quantity"]["value"], "unit": value["quantity"]["code"],
            "effective_time": value["effective_time"], "patient_external_id": value["source"]["patient_external_id"],
        }.items()):
            raise ObservationError("admission_mismatch", "The source's canonical clinical values differ from the projection")
        return deepcopy(value)
