"""Qualified state-estimation and forecast boundary; authority and model code are host configuration.

This module supplies enforcement, not qualification evidence. No permissive
authority implementation is shipped. The frozen core protocol stays unchanged.
"""
from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Protocol
from uuid import uuid4

from jsonschema import Draft202012Validator, FormatChecker

from .observation import ObservationSource, validate_observation
from .validation import canonical_digest, parse_timestamp, semantic_validate, validate_definition

ROOT = Path(__file__).resolve().parents[3]
SCHEMA = json.loads((ROOT / "schemas/model-family-contract.schema.json").read_text())
PROFILE = "openbody.model-family-contract.v1"
REGISTRY = {row["coordinate"]: row["scale"] for row in json.loads((ROOT / "registry/coordinates.json").read_text())["coordinates"]}
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())
REQUEST_VALIDATOR = Draft202012Validator(SCHEMA["$defs"]["ExecutionRequest"], format_checker=FormatChecker())
COUNTERFACTUAL_REQUEST_VALIDATOR = Draft202012Validator(SCHEMA["$defs"]["CounterfactualRequest"], format_checker=FormatChecker())


class ModelExecutionError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def require(condition: bool, code: str, message: str) -> None:
    if not condition:
        raise ModelExecutionError(code, message)


def finite(value: Any) -> bool:
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def validate_contract(contract: Any) -> None:
    require(VALIDATOR.is_valid(contract), "invalid_contract", "Unsupported model-family contract")
    require(contract["model"]["coordinate"] in REGISTRY, "invalid_contract", "Unknown model coordinate")
    require(not set(contract["context_of_use"]) & set(contract["prohibited_uses"]), "invalid_contract", "Allowed and prohibited uses overlap")
    for rows, key in ((contract["required_observations"], "key"), (contract["behavioral_envelope"], "name"),
                      (contract["allowed_adaptation"]["parameters"], "name"), (contract["dependencies"], "ref"),
                      (contract["qualification_evidence"], "ref")):
        require(len({row[key] for row in rows}) == len(rows), "invalid_contract", "Duplicate contract identity")
    for row in contract["required_observations"]:
        require(finite(row["minimum_value"]) and finite(row["maximum_value"]) and row["minimum_value"] <= row["maximum_value"], "invalid_contract", "Invalid observation bounds")
    for row in contract["behavioral_envelope"] + contract["allowed_adaptation"]["parameters"]:
        require(finite(row["minimum"]) and finite(row["maximum"]) and row["minimum"] <= row["maximum"], "invalid_contract", "Invalid behavioral bounds")
        if "default" in row:
            require(finite(row["default"]) and row["minimum"] <= row["default"] <= row["maximum"], "invalid_contract", "Adaptation default exceeds envelope")
    kinds = {row["kind"] for row in contract["qualification_evidence"]}
    for purpose, kind in (("software_test", "software"), ("research", "research"), ("clinical_decision_support", "clinical")):
        require(purpose not in contract["context_of_use"] or kind in kinds, "invalid_contract", "Context of use lacks its qualification evidence class")
    if "counterfactual" in contract:
        boundary = contract["counterfactual"]
        perturbations = boundary["perturbations"]
        effects = boundary["effect_bounds"]
        require(len({row["id"] for row in perturbations}) == len(perturbations), "invalid_contract", "Duplicate perturbation identity")
        require({row["name"] for row in effects} == {row["name"] for row in contract["behavioral_envelope"]} and
                len({row["name"] for row in effects}) == len(effects), "invalid_contract", "Effect bounds must cover every declared metric once")
        for perturbation in perturbations:
            require(perturbation["scope"] == contract["model"]["coordinate"], "invalid_contract", "Perturbation exceeds model scope")
            require(len({row["name"] for row in perturbation["parameters"]}) == len(perturbation["parameters"]), "invalid_contract", "Duplicate perturbation parameter")
        for row in effects + [row for perturbation in perturbations for row in perturbation["parameters"]]:
            require(finite(row["minimum"]) and finite(row["maximum"]) and row["minimum"] <= row["maximum"],
                    "invalid_contract", "Invalid perturbation or effect bounds")


@dataclass(frozen=True)
class QualificationLease:
    """A resolver's current authoritative decision, never an HTTP request field.

    Resolvers must verify decision authority, subject/population evidence,
    artifact identity and transitive dependency status in their trusted registry.
    A lease is checked before/after execution and on every retained-result read.
    """
    reference: str
    revision: str
    contract_digest: str
    subject: str
    tenant_id: str
    purpose: str
    population: str
    question: str
    horizon_seconds: int
    artifact_digest: str
    dependency_digests: tuple[tuple[str, str], ...]
    evidence_digests: tuple[tuple[str, str], ...]
    valid_from: datetime
    valid_until: datetime
    status: str
    # A fresh audit receipt may differ while the reviewed qualification stays the
    # same. It is provenance, not a reusable authorization or a semantic revision.
    resolution_reference: str | None = field(default=None, compare=False)


class QualificationAuthority(Protocol):
    def resolve(self, contract_digest: str, request: dict[str, Any]) -> QualificationLease: ...


@dataclass(frozen=True)
class ModelEvaluation:
    metrics: dict[str, float]
    uncertainty: dict[str, Any]


@dataclass(frozen=True)
class ModelRegistration:
    contract: dict[str, Any]
    # Verified executable bytes from the loader. The callable must execute this
    # artifact and only its declared dependencies; this is a trusted host adapter.
    artifact: bytes
    evaluate: Callable[[dict[str, list[dict[str, Any]]], dict[str, float]], ModelEvaluation]


@dataclass(frozen=True)
class ForecastPoint:
    offset_seconds: int
    evaluation: ModelEvaluation


@dataclass(frozen=True)
class ForecastEvaluation:
    points: tuple[ForecastPoint, ...]
    uncertainty: dict[str, Any]
    assumptions: tuple[str, ...]


@dataclass(frozen=True)
class ForecastModelRegistration(ModelRegistration):
    evaluate: Callable[[dict[str, list[dict[str, Any]]], dict[str, float], int], ForecastEvaluation]


@dataclass(frozen=True)
class CounterfactualEvaluation:
    control: ForecastEvaluation
    intervention: ForecastEvaluation
    effect_uncertainty: dict[str, dict[str, Any]]
    uncertainty: dict[str, Any]
    assumptions: tuple[str, ...]


@dataclass(frozen=True)
class CounterfactualModelRegistration(ModelRegistration):
    evaluate: Callable[[dict[str, list[dict[str, Any]]], dict[str, float], dict[str, Any], int], CounterfactualEvaluation]


class QualifiedModelRuntime:
    def __init__(self, subject: str, tenant_id: str, source: ObservationSource, authority: QualificationAuthority,
                 models: list[ModelRegistration], *, clock: Callable[[], datetime] | None = None):
        require(subject.startswith("subject:") and bool(tenant_id) and source is not None and authority is not None, "invalid_configuration", "Explicit subject, tenant, source and qualification authority are required")
        self.subject, self.tenant_id = subject, tenant_id
        self._source, self._authority = source, authority
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._models: dict[str, ModelRegistration] = {}
        self._results: OrderedDict[str, tuple[Any, ...]] = OrderedDict()
        self._retained_bytes = 0
        self._lock = RLock()
        for registration in models:
            contract = deepcopy(registration.contract)
            validate_contract(contract)
            require(type(registration) in (ModelRegistration, ForecastModelRegistration, CounterfactualModelRegistration), "invalid_configuration", "Unsupported executable registration")
            horizons = contract["prediction_horizon_seconds"]
            require(all(type(value) is int for value in horizons), "invalid_configuration", "Horizons must be integer seconds")
            require(all(value > 0 for value in horizons) if type(registration) is not ModelRegistration else horizons == [0],
                    "invalid_configuration", "Registration kind differs from declared prediction horizons")
            require(("counterfactual" in contract) == isinstance(registration, CounterfactualModelRegistration),
                    "invalid_configuration", "Counterfactual contracts require explicit counterfactual registration")
            identity = contract["model"]
            require(identity["id"] not in self._models, "invalid_configuration", "Duplicate model registration")
            require("sha256:" + hashlib.sha256(registration.artifact).hexdigest() == identity["artifact_digest"], "invalid_configuration", "Loaded artifact differs from qualified model identity")
            self._models[identity["id"]] = type(registration)(contract, bytes(registration.artifact), registration.evaluate)

    def contracts(self) -> list[dict[str, Any]]:
        return [deepcopy(row.contract) for row in self._models.values()]

    def _request(self, request: Any) -> tuple[ModelRegistration, dict[str, float]]:
        model = self._request_model(request)
        validator = COUNTERFACTUAL_REQUEST_VALIDATOR if isinstance(model, CounterfactualModelRegistration) else REQUEST_VALIDATOR
        require(validator.is_valid(request), "invalid_request", "Unsupported model execution request")
        require(request["subject"] == self.subject, "subject_mismatch", "Request does not represent the hosted Twin")
        model = self._models.get(request["model_id"])
        require(model is not None, "model_unavailable", "Model is not registered")
        contract = model.contract
        for field, allowed in (("purpose", "context_of_use"), ("population", "supported_population"),
                               ("question", "supported_question"), ("horizon_seconds", "prediction_horizon_seconds")):
            require(request[field] in contract[allowed], "unsupported_context", "Requested context exceeds the model contract")
        require(request["purpose"] not in contract["prohibited_uses"], "unsupported_context", "Requested use is prohibited")
        parameters = {row["name"]: row for row in contract["allowed_adaptation"]["parameters"]}
        require(set(request["adaptation"]) <= set(parameters), "adaptation_requires_review", "New adaptation parameters require DG review")
        values = {name: request["adaptation"].get(name, row["default"]) for name, row in parameters.items()}
        require(all(finite(value) and parameters[name]["minimum"] <= value <= parameters[name]["maximum"] for name, value in values.items()), "adaptation_requires_review", "Adaptation exceeds the qualified envelope")
        if isinstance(model, CounterfactualModelRegistration):
            from .model_counterfactual import validate_perturbation_request
            validate_perturbation_request(contract, request["perturbation"])
        return model, values

    def _request_model(self, request: Any):
        if isinstance(request, dict) and isinstance(request.get("model_id"), str):
            return self._models.get(request["model_id"])
        return None

    def _lease(self, model: ModelRegistration, request: dict[str, Any]) -> QualificationLease:
        contract = model.contract
        digest = canonical_digest(contract)
        try:
            lease = deepcopy(self._authority.resolve(digest, deepcopy(request)))
            now = self._clock()
            require(isinstance(lease, QualificationLease) and lease.status == "active" and bool(lease.reference) and bool(lease.revision), "unqualified", "Model qualification is not active")
            require(lease.valid_from.tzinfo is not None and lease.valid_until.tzinfo is not None and lease.valid_from <= now < lease.valid_until, "unqualified", "Model qualification is outside its validity window")
            require(lease.contract_digest == digest and lease.artifact_digest == contract["model"]["artifact_digest"], "unqualified", "Qualification does not bind this contract and artifact")
            require(lease.tenant_id == self.tenant_id, "unqualified", "Qualification belongs to another tenant")
            require(all(getattr(lease, key) == request[key] for key in ("subject", "purpose", "population", "question", "horizon_seconds")), "unqualified", "Qualification does not cover this subject and use")
            for entries, wanted in ((lease.dependency_digests, contract["dependencies"]), (lease.evidence_digests, contract["qualification_evidence"])):
                require(len(entries) == len(wanted) and dict(entries) == {row["ref"]: row["digest"] for row in wanted}, "dependency_unavailable", "Current qualification dependencies or evidence differ")
            return lease
        except ModelExecutionError:
            raise
        except Exception as error:
            raise ModelExecutionError("unqualified", "Current qualification authority is unavailable") from error

    def _observations(self, model: ModelRegistration, request: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
        rows = []
        size = 0
        try:
            for locator in request["observations"]:
                require(locator["tenant_id"] == self.tenant_id, "subject_mismatch", "Observation locator exceeds the hosted tenant")
                row = deepcopy(self._source.resolve(deepcopy(locator)))
                validate_observation(row, subject=self.subject)
                require(row["source"]["clinical_version"] == locator, "invalid_source", "Source returned another clinical version")
                size += len(json.dumps(row, allow_nan=False).encode())
                require(size <= 4 * 1024 * 1024, "invalid_source", "Observation batch exceeds the execution bound")
                rows.append(row)
        except ModelExecutionError:
            raise
        except Exception as error:
            raise ModelExecutionError("source_unavailable", "Admitted source evidence is unavailable") from error
        versions = [row["source"]["clinical_version"] for row in rows]
        require(len({row["composition_uid"] for row in versions}) == len(rows), "invalid_source", "Multiple versions of one composition cannot inflate support")
        require(len({row["tenant_id"] for row in versions}) == 1, "subject_mismatch", "Observation batch crosses tenant boundaries")
        grouped = {}
        selected = set()
        now = self._clock()
        for requirement in model.contract["required_observations"]:
            matches = [row for row in rows if (row["code"]["system"], row["code"]["code"], row["quantity"]["code"]) ==
                       (requirement["code_system"], requirement["code"], requirement["unit"])]
            require(len(matches) >= requirement["minimum_count"], "missing_evidence", "Required admitted observations are missing")
            for row in matches:
                require(row["effective_time"] is not None and 0 <= (now - parse_timestamp(row["effective_time"])).total_seconds() <= requirement["maximum_age_seconds"], "stale_evidence", "Observation time is absent, stale or in the future")
                require(requirement["minimum_value"] <= row["quantity"]["value"] <= requirement["maximum_value"], "out_of_distribution", "Observation exceeds qualified input bounds")
                require(row["uncertainty"]["out_of_distribution"] is not True, "out_of_distribution", "Source reports out-of-distribution evidence")
                if model.contract["uncertainty_contract"]["unknown_input"] == "abstain":
                    require(not self._unknown(row["uncertainty"]), "missing_evidence", "Required source uncertainty is unknown")
                selected.add(row["id"])
            grouped[requirement["key"]] = sorted(matches, key=lambda row: (row["effective_time"], row["id"]))
        require(selected == {row["id"] for row in rows}, "invalid_source", "Unrequested observations exceed the model input boundary")
        return grouped

    @staticmethod
    def _unknown(uncertainty: dict[str, Any]) -> bool:
        return any(uncertainty[key] is None for key in ("epistemic", "aleatoric", "coverage")) or uncertainty["out_of_distribution"] == "unknown"

    def execute(self, request: dict[str, Any]) -> dict[str, Any]:
        request = deepcopy(request)
        model, parameters = self._request(request)
        lease = self._lease(model, request)
        inputs = self._observations(model, request)
        try:
            if isinstance(model, CounterfactualModelRegistration):
                from .model_counterfactual import build_counterfactual, execution_perturbation
                origin = self._clock()
                perturbation = execution_perturbation(model.contract, request["perturbation"], origin)
                evaluation = deepcopy(model.evaluate(deepcopy(inputs), deepcopy(parameters), deepcopy(perturbation), request["horizon_seconds"]))
                state = build_counterfactual(self, model, request, inputs, parameters, evaluation, lease, origin, perturbation)
            elif isinstance(model, ForecastModelRegistration):
                from .model_forecast import build_forecast
                origin = self._clock()
                evaluation = deepcopy(model.evaluate(deepcopy(inputs), deepcopy(parameters), request["horizon_seconds"]))
                state = build_forecast(self, model, request, inputs, parameters, evaluation, lease, origin)
            else:
                evaluation = deepcopy(model.evaluate(deepcopy(inputs), deepcopy(parameters)))
                self._validate_evaluation(model, evaluation)
                state = self._state(model, request, inputs, parameters, evaluation, lease)
        except ModelExecutionError:
            raise
        except Exception as error:
            raise ModelExecutionError("invalid_output", "Model execution did not produce a valid bounded result") from error
        require(self._observations(model, request) == inputs, "source_changed", "Source evidence changed during model execution")
        require(self._lease(model, request) == lease, "unqualified", "Qualification changed during model execution")
        retained_size = len(json.dumps([request, inputs, state], allow_nan=False).encode())
        require(retained_size <= 16 * 1024 * 1024, "invalid_output", "Execution result exceeds retention bound")
        with self._lock:
            self._results[state["id"]] = (request, inputs, lease, deepcopy(state), retained_size)
            self._retained_bytes += retained_size
            while len(self._results) > 512 or self._retained_bytes > 32 * 1024 * 1024:
                _, evicted = self._results.popitem(last=False)
                self._retained_bytes -= evicted[-1]
        return state

    @staticmethod
    def _validate_evaluation(model: ModelRegistration, evaluation: ModelEvaluation) -> None:
        require(isinstance(evaluation, ModelEvaluation), "invalid_output", "Model returned an unsupported result type")
        bounds = {row["name"]: row for row in model.contract["behavioral_envelope"]}
        require(set(evaluation.metrics) == set(bounds), "invalid_output", "Model output does not match the qualified metrics")
        require(all(finite(value) and bounds[name]["minimum"] <= value <= bounds[name]["maximum"] for name, value in evaluation.metrics.items()), "invalid_output", "Model output exceeds its behavioral envelope")
        validate_definition("Uncertainty", evaluation.uncertainty)
        require(evaluation.uncertainty["out_of_distribution"] is not True, "out_of_distribution", "Model abstained outside its distribution")
        require(type(evaluation.uncertainty["out_of_distribution"]) is bool or evaluation.uncertainty["out_of_distribution"] == "unknown", "invalid_output", "Invalid model distribution verdict")
        # Validate finite values even where JSON Schema's Python comparison
        # semantics would otherwise accept NaN, or booleans in numeric enums.
        require(all(value is None or finite(value) for key, value in evaluation.uncertainty.items() if key in ("epistemic", "aleatoric", "coverage")), "invalid_output", "Invalid model uncertainty")
        interval = evaluation.uncertainty.get("interval")
        if interval is not None:
            require(all(finite(value) for value in interval.values()) and interval["lower"] <= interval["point"] <= interval["upper"], "invalid_output", "Invalid model uncertainty interval")

    def read(self, execution_id: str) -> dict[str, Any]:
        return self._validated_result(execution_id)[3]

    def _validated_result(self, execution_id: str) -> tuple[Any, ...]:
        """Internal publication boundary: detached result and its current authority."""
        with self._lock:
            retained = deepcopy(self._results.get(execution_id))
        require(retained is not None, "execution_unavailable", "Execution is not retained")
        request, inputs, lease, state, _ = retained
        model, _ = self._request(request)
        require(self._observations(model, request) == inputs, "source_changed", "Execution source evidence is no longer current")
        require(self._lease(model, request) == lease, "unqualified", "Execution qualification is no longer current")
        return retained

    def adaptation_candidate(self, request: dict[str, Any]) -> dict[str, Any]:
        # An inert proposal, never an update of the registered contract or model.
        validator = COUNTERFACTUAL_REQUEST_VALIDATOR if isinstance(self._request_model(request), CounterfactualModelRegistration) else REQUEST_VALIDATOR
        require(validator.is_valid(request) and request["subject"] == self.subject, "invalid_request", "Invalid adaptation proposal")
        model = self._models.get(request["model_id"])
        require(model is not None, "model_unavailable", "Model is not registered")
        require(all(finite(value) for value in request["adaptation"].values()), "invalid_request", "Adaptation values must be finite")
        return {"profile": PROFILE, "schema_version": "0.1", "kind": "ModelAdaptationCandidate", "id": "candidate:" + str(uuid4()),
                "subject": self.subject, "model_id": request["model_id"], "contract_digest": canonical_digest(model.contract),
                "requested_parameters": deepcopy(request["adaptation"]), "status": "dg_review_required", "activated": False}

    def _state(self, model: ModelRegistration, request: dict[str, Any], inputs: dict[str, Any], parameters: dict[str, float],
               evaluation: ModelEvaluation, lease: QualificationLease, *, state_time: str | None = None, generated_at: str | None = None) -> dict[str, Any]:
        now = generated_at or self._clock().isoformat().replace("+00:00", "Z")
        identity = model.contract["model"]
        state_id = "model-execution:" + str(uuid4())
        uncertainty = deepcopy(evaluation.uncertainty)
        if any(self._unknown(row["uncertainty"]) for rows in inputs.values() for row in rows):
            uncertainty = {"epistemic": None, "aleatoric": None, "coverage": None, "out_of_distribution": "unknown",
                           "reasons": uncertainty["reasons"] + ["Input measurement uncertainty is unknown; output uncertainty is not quantified"]}
        receipt = {"model_id": identity["id"], "model_version": identity["version"], "family": identity["family"],
                   "execution_id": state_id, "executed_at": now, "input_digest": canonical_digest({"request": request, "inputs": inputs, "parameters": parameters}),
                   "output_digest": canonical_digest({"state_vector": evaluation.metrics, "uncertainty": uncertainty}),
                   "environment_digest": canonical_digest(model.contract), "validation_ref": lease.reference}
        unique = {row["id"]: row for rows in inputs.values() for row in rows}
        evidence = [{"id": row["id"], "scheme": "openbody", "canonical_ref": row["id"], "content_digest": canonical_digest(row),
                     "observed_at": row["effective_time"], "subject": self.subject, "scopes": [identity["coordinate"]],
                     "model_refs": [identity["id"]], "claim_refs": [state_id],
                     "source_provenance": {"profile": row["profile"], "source": deepcopy(row["source"]),
                                           "normalization": deepcopy(row["normalization"]), "uncertainty": deepcopy(row["uncertainty"]),
                                           "contract_digest": canonical_digest(model.contract), "qualification_revision": lease.revision}}
                    for row in sorted(unique.values(), key=lambda row: row["id"])]
        if lease.resolution_reference is not None:
            for row in evidence:
                row["source_provenance"]["qualification_resolution_ref"] = lease.resolution_reference
        state = {"schema_version": "0.1", "kind": "BodyState", "id": state_id, "subject": self.subject, "generated_at": now,
                 "state_time": state_time or now, "valid_until": lease.valid_until.isoformat().replace("+00:00", "Z"),
                 "subsystems": [{"coordinate": identity["coordinate"], "organizational_scale": REGISTRY[identity["coordinate"]],
                                 "state_vector": deepcopy(evaluation.metrics), "trend": "indeterminate", "uncertainty": uncertainty,
                                 "evidence": evidence, "model_receipt": receipt}],
                 "couplings": [], "evidence": evidence, "uncertainty": uncertainty, "model_receipts": [receipt]}
        if state_time is not None:
            # Core state validity is physiological time, whereas the qualification
            # lease expires in execution/use time. The forecast envelope carries
            # that expiry separately; never stretch it to the prediction horizon.
            state.pop("valid_until")
        semantic_validate(state)
        return state
