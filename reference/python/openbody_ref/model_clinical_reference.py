"""Publish actual qualified executions as separately typed clinical references.

The embedding host authenticates readers and supplies independent identity and
qualification authorities. No caller can provide a binding proof, output, or
clinical-purpose label to this publisher. Publication grants no action authority.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from typing import Protocol
from urllib.parse import quote, urlsplit

from .clinical_reference import validate_clinical_reference
from .model_family import ModelExecutionError, QualifiedModelRuntime, ROOT, require
from .validation import canonical_digest, semantic_validate


@dataclass(frozen=True)
class VerifiedSubjectBinding:
    """Current independent proof, resolved by trusted host configuration.

    The authority must verify the proof/issuer and current revocation state, not
    echo caller fields or treat a patient's local own-record checkbox as proof.
    """
    subject: str
    tenant_id: str
    ehr_id: str
    reference: str
    issuer: str
    proof_digest: str
    revocation_ref: str
    verified_at: datetime
    expires_at: datetime
    status: str


class SubjectBindingAuthority(Protocol):
    def resolve(self, subject: str, tenant_id: str, ehr_id: str) -> VerifiedSubjectBinding: ...


def timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


class QualifiedClinicalReferencePublisher:
    def __init__(self, runtime: QualifiedModelRuntime, binding_authority: SubjectBindingAuthority,
                 canonical_base_url: str):
        require(isinstance(runtime, QualifiedModelRuntime) and binding_authority is not None,
                "invalid_configuration", "Explicit runtime and independent subject-binding authority are required")
        url = urlsplit(canonical_base_url)
        require(url.scheme in {"http", "https"} and bool(url.hostname) and not url.username and not url.password
                and not url.query and not url.fragment and not any(char.isspace() for char in canonical_base_url),
                "invalid_configuration", "Canonical publication origin must be a fixed HTTP(S) base URL")
        require(url.scheme == "https" or url.hostname in {"localhost", "127.0.0.1", "::1"},
                "invalid_configuration", "Remote clinical publication requires HTTPS")
        require(runtime.subject.startswith("subject:providehr:ehr:"), "invalid_configuration",
                "Clinical publication requires the admitted EHR subject convention")
        self.runtime = runtime
        self._authority = binding_authority
        self._base = canonical_base_url.rstrip("/")
        self._ehr_id = runtime.subject.removeprefix("subject:providehr:ehr:")
        require(bool(self._ehr_id), "invalid_configuration", "An exact EHR subject is required")

    def _binding(self) -> VerifiedSubjectBinding:
        try:
            value = deepcopy(self._authority.resolve(self.runtime.subject, self.runtime.tenant_id, self._ehr_id))
            now = self.runtime._clock()
            require(isinstance(value, VerifiedSubjectBinding) and value.status == "verified",
                    "subject_binding_unavailable", "Independent subject binding is not verified")
            require((value.subject, value.tenant_id, value.ehr_id) == (self.runtime.subject, self.runtime.tenant_id, self._ehr_id),
                    "subject_binding_mismatch", "Binding does not represent the exact hosted tenant and EHR")
            require(value.verified_at.tzinfo is not None and value.expires_at.tzinfo is not None and
                    value.verified_at <= now < value.expires_at,
                    "subject_binding_expired", "Independent subject binding is outside its validity window")
            return value
        except ModelExecutionError:
            raise
        except Exception as error:
            raise ModelExecutionError("subject_binding_unavailable", "Independent subject-binding authority is unavailable") from error

    def publish(self, execution_id: str) -> dict:
        retained = self.runtime._validated_result(execution_id)
        request, _, lease, result, _ = retained
        require(request["purpose"] == "clinical_decision_support", "clinical_use_unqualified",
                "Software and research executions cannot be relabeled as clinical assertions")
        # Reuse the strict model result validator, including the complete control
        # comparison for counterfactuals. The frozen core scenario stays intact.
        from .client import OpenBodyClient
        model, _ = self.runtime._request(request)
        OpenBodyClient._checked_model_result(result, model.contract, self.runtime.subject, request=request)
        if result["kind"] == "BodyState":
            resolved = result
            epistemic_class = "inference"
        elif result["kind"] == "ModelCounterfactual":
            resolved = result["scenario"]
            epistemic_class = "counterfactual"
        else:
            raise ModelExecutionError("unsupported_clinical_object", "This execution kind has no supported standalone clinical reference projection")
        uncertainty = resolved["uncertainty"]
        require(not self.runtime._unknown(uncertainty) and uncertainty["out_of_distribution"] is False,
                "uncertainty_unknown", "Unknown model or source uncertainty cannot become known clinical uncertainty")
        binding = self._binding()
        valid_until = min(lease.valid_until, binding.expires_at)
        evidence = resolved["evidence"]
        scope = [model.contract["model"]["coordinate"]]
        receipt = resolved["model_receipts"][0]
        execution_url = self._base + "/v1/model-executions/" + quote(execution_id, safe="")
        binding_wire = {"status": binding.status, "binding_ref": binding.reference, "issuer": binding.issuer,
                        "proof_digest": binding.proof_digest, "revocation_ref": binding.revocation_ref,
                        "verified_at": timestamp(binding.verified_at), "expires_at": timestamp(binding.expires_at)}
        # Stable for the same execution and binding. Repeated reads cannot create
        # a conflict in ProvidEHR's immutable reference-id admission records.
        identity = canonical_digest({"execution": execution_id, "binding": binding_wire,
                                     "content": canonical_digest(resolved), "valid_until": timestamp(valid_until)})
        reference = {
            "schema_version": "openbody.clinical-assertion-reference/1.0", "projection_class": "openbody_reference",
            "reference_id": "clinical-reference:" + identity.removeprefix("sha256:"),
            "object_kind": resolved["kind"], "canonical_ref": execution_url + "/clinical-object",
            "content_digest": canonical_digest(resolved), "subject": self.runtime.subject,
            "subject_binding": binding_wire, "scope": scope,
            "contract": {"openbody_schema_version": "0.1",
                         "openbody_schema_digest": "sha256:" + hashlib.sha256((ROOT / "schemas/openbody.schema.json").read_bytes()).hexdigest(),
                         "coordinate_registry_version": json.loads((ROOT / "registry/coordinates.json").read_text())["registry_version"]},
            "producer": {**{key: receipt[key] for key in ("model_id", "model_version", "family", "execution_id", "executed_at", "input_digest", "output_digest")},
                         "receipt_ref": execution_url + ("#/scenario/model_receipts/0" if epistemic_class == "counterfactual" else "#/model_receipts/0")},
            "evidence_lineage": [{key: row[key] for key in ("canonical_ref", "content_digest", "observed_at", "subject", "scopes", "model_refs")} for row in evidence],
            "epistemic_class": epistemic_class,
            "applicability": {"status": "applicable", "subject": self.runtime.subject, "scopes": scope,
                              "evaluated_at": receipt["executed_at"], "reasons": ["Execution context is covered by the current exact qualification lease"]},
            "uncertainty": {**deepcopy(uncertainty), "status": "known", "interval": uncertainty.get("interval"),
                            "calibration_ref": uncertainty.get("calibration_ref")},
            "validity": {"status": "valid", "assessed_at": receipt["executed_at"], "valid_until": timestamp(valid_until),
                         "validity_ref": lease.reference},
            "abstention": {"status": "not_abstained"},
            "summary": f"Model {epistemic_class} from {receipt['model_id']} {receipt['model_version']}; requires clinical review; grants no treatment authority",
        }
        try:
            semantic_validate(resolved)
            validate_clinical_reference(reference, resolved, evaluated_at=self.runtime._clock())
        except ValueError as error:
            raise ModelExecutionError("invalid_clinical_reference", "Execution cannot produce a conformant clinical assertion reference") from error
        require(self._binding() == binding, "subject_binding_changed", "Subject binding changed during publication")
        require(self.runtime._validated_result(execution_id) == retained, "execution_changed", "Execution authority or source changed during publication")
        require(self.runtime._clock() < valid_until, "publication_expired", "Publication authority expired before return")
        return {"ehr_id": self._ehr_id, "reference": reference, "resolved_object": deepcopy(resolved)}
