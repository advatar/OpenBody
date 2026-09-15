from __future__ import annotations

import copy
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException

from .observation import ObservationError, ObservationSource, PROFILE as OBSERVATION_PROFILE, validate_locator, validate_observation
from .store import InMemoryTwinStore, producing_model_requirements
from .validation import canonical_digest, parse_timestamp, scenario_evidence_references, scenario_horizon_seconds, semantic_validate, validate_definition

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FIXTURE = ROOT / "examples" / "post-meal-walk.scenario.json"
ABSTENTION_FIXTURE = ROOT / "examples" / "insufficient-evidence.abstention.json"


def create_model_execution_host(runtime) -> FastAPI:
    """Explicit qualified-execution host; no default models, grants or fixture replay.

    Authentication and the trusted source/qualification resolvers belong to the
    embedding host. This factory is not exposed by the public discovery startup.
    """
    from .model_family import ModelExecutionError, PROFILE, SCHEMA, QualifiedModelRuntime
    if not isinstance(runtime, QualifiedModelRuntime):
        raise ValueError("An explicitly configured qualified model runtime is required")
    app = FastAPI(title="OpenBody Qualified Model Reference Host", version="0.1.0")

    @app.get("/.well-known/openbody")
    @app.get("/v1/capabilities")
    def execution_capabilities():
        return {"protocol": "openbody", "versions": ["0.1"], "contract": contract_identity(),
                "capabilities": ["model-families.discover", "model-executions.execute", "model-executions.read", "model-forecasts.execute", "model-counterfactuals.execute", "model-adaptations.propose"],
                "profiles": [{"id": PROFILE, "schema_digest": canonical_digest(SCHEMA), "schema_url": "/v1/model-families/profile"}]}

    @app.get("/v1/model-families/profile")
    def model_family_profile():
        return copy.deepcopy(SCHEMA)

    @app.get("/v1/model-families")
    def model_families():
        return runtime.contracts()

    def checked(operation):
        from fastapi.responses import JSONResponse
        try:
            value = operation()
        except ModelExecutionError as error:
            reasons = {"invalid_request": "invalid_input", "subject_mismatch": "authorization_required", "model_unavailable": "model_unavailable",
                       "missing_evidence": "insufficient_evidence", "stale_evidence": "stale_evidence", "out_of_distribution": "out_of_distribution",
                       "unsupported_perturbation": "unsupported_perturbation"}
            value = {"schema_version": "0.1", "kind": "Abstention", "reason_code": reasons.get(error.code, "insufficient_validation"), "reasons": [str(error)]}
            # Operational failure codes are carried in a response header, keeping
            # the frozen typed abstention vocabulary intact.
            validate_definition("Abstention", value)
            return JSONResponse(value, headers={"Cache-Control": "no-store", "OpenBody-Execution-Reason": error.code})
        return JSONResponse(value, headers={"Cache-Control": "no-store"})

    @app.post("/v1/model-executions")
    def execute_model(request: dict[str, Any]):
        return checked(lambda: runtime.execute(request))

    @app.get("/v1/model-executions/{execution_id}")
    def read_execution(execution_id: str):
        return checked(lambda: runtime.read(execution_id))

    @app.post("/v1/model-adaptation-candidates")
    def propose_adaptation(request: dict[str, Any]):
        return checked(lambda: runtime.adaptation_candidate(request))

    return app


NORMATIVE_ARTIFACTS = (
    "OPENBODY.md",
    "schemas/openbody.schema.json",
    "openapi/openbody.openapi.json",
    "profiles/mcp/tools.json",
    "registry/coordinates.json",
)


def contract_identity() -> dict[str, Any]:
    """What contract this host actually serves.

    Identified by `schema_version` and `registry_version`, plus a digest over the
    normative artifacts — never by a release tag. Tags increment for reasons that
    are not protocol changes, so a tag cannot tell a consumer whether the contract
    it validated against is the one being served. The registry version is reported
    separately because coordinate registries grow additively without changing
    protocol semantics.
    """
    registry = json.loads((ROOT / "registry" / "coordinates.json").read_text())
    digests: dict[str, str] = {}
    for artifact in NORMATIVE_ARTIFACTS:
        path = ROOT / artifact
        if path.exists():
            digests[artifact] = canonical_digest(path.read_text())
    return {
        "schema_version": "0.1",
        "registry_version": registry.get("registry_version"),
        "coordinate_count": len(registry.get("coordinates", [])),
        "artifact_digests": digests,
    }


def _capabilities(discovery_only: bool = False, observations_enabled: bool = False, observations_only: bool = False) -> dict[str, Any]:
    capabilities = ["models.discover"]
    if not discovery_only:
        capabilities = [
            "state.read",
            "models.discover",
            "simulation.execute",
            "simulation.read",
            "outcomes.write",
            "calibrations.write",
        ]
    if observations_enabled and not discovery_only:
        capabilities = ([] if observations_only else capabilities) + ["observations.ingest", "observations.read"]
    result = {
        "protocol": "openbody",
        "versions": ["0.1"],
        "capabilities": capabilities,
        "authorization": {"schemes": []},
        "contract": contract_identity(),
    }
    if observations_enabled and not discovery_only:
        from .observation import SCHEMA
        result["profiles"] = [{"id": OBSERVATION_PROFILE, "schema_digest": canonical_digest(SCHEMA),
                               "schema_url": "/v1/observations/profile"}]
    return result


def _abstention(reason_code: str, reason: str) -> dict[str, Any]:
    value = json.loads(ABSTENTION_FIXTURE.read_text())
    value["reason_code"] = reason_code
    value["reasons"] = [reason, "No counterfactual effect was generated"]
    semantic_validate(value)
    return value


def _producing_model_defect(store: InMemoryTwinStore, candidate: dict[str, Any]) -> tuple[str, str] | None:
    """Substantiate every producing receipt against its discoverable descriptor.

    Stored scenarios are an untrusted protocol boundary, so this runs on both the
    execute and read paths rather than only when a simulation is generated.
    """
    try:
        requirements = producing_model_requirements(candidate)
    except ValueError:
        return ("insufficient_validation", "A producing model receipt has no biological scope")
    declared_horizon = candidate["applicability"]["horizon_seconds"]
    producing_models = []
    for (model_id, model_version, family), requirement in requirements.items():
        model = store.models.get(model_id)
        if (
            model is None
            or model["version"] != model_version
            or model["family"] != family
        ):
            return ("model_unavailable", "A producing model receipt is not discoverable")
        if not requirement["capabilities"].issubset(set(model["capabilities"])):
            return ("insufficient_validation", "A producing model lacks its required capability")
        if not requirement["scopes"].issubset(set(model["scopes"])):
            return ("unsupported_scope", "A producing model does not support its receipt scopes")
        model_applicability = model.get("applicability", {})
        if (
            model_applicability.get("subject") != candidate["subject"]
            or not requirement["scopes"].issubset(set(model_applicability.get("scopes", [])))
        ):
            return (
                "insufficient_validation",
                "A producing model applicability boundary does not match its subject and receipt scopes",
            )
        producing_models.append(model)
    if not producing_models or any(
        model.get("applicability", {}).get("horizon_seconds") != declared_horizon for model in producing_models
    ):
        return ("insufficient_validation", "Producing model applicability does not match the scenario")
    return None


def _require_hosted_twin(store: InMemoryTwinStore, subjects: set[str | None]) -> None:
    """Every subject a read path discloses MUST be the host's canonical twin.

    Applied uniformly to all stored, subject-bearing reads rather than per
    endpoint: a stored object for another twin is a cross-twin disclosure
    regardless of which resource or disposition carries it.
    """
    hosted = store.state["subject"]
    if any(subject != hosted for subject in subjects):
        raise ValueError("stored object does not represent the hosted twin")


def _reference_simulate(store: InMemoryTwinStore, request: dict[str, Any]) -> dict[str, Any]:
    allowed_fields = {"state", "perturbation", "horizon_seconds", "requested_scopes", "authority_ref"}
    unexpected_fields = set(request) - allowed_fields
    if unexpected_fields:
        raise ValueError(f"unsupported simulation request fields: {sorted(unexpected_fields)}")
    validate_definition("BodyState", request.get("state"))
    validate_definition("Perturbation", request.get("perturbation"))
    horizon = request.get("horizon_seconds")
    if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon < 1:
        raise ValueError("horizon_seconds must be a positive integer")
    requested_scopes = request.get("requested_scopes")
    if not isinstance(requested_scopes, list) or not requested_scopes:
        raise ValueError("requested_scopes must be a non-empty array")
    for scope in requested_scopes:
        validate_definition("Coordinate", scope)
    if len(requested_scopes) != len(set(requested_scopes)):
        raise ValueError("requested_scopes must not contain duplicates")
    requested = request["perturbation"]
    if request.get("authority_ref") is not None or requested.get("authority_ref") is not None:
        return _abstention(
            "authorization_required",
            "The reference provider cannot validate external authority references",
        )

    candidate = next(iter(store.scenarios.values()), None)
    if candidate is None:
        return _abstention("model_unavailable", "No reference scenario is available")

    baseline_state = candidate["baseline"]["states"][0]
    hosted_subject = store.state["subject"]
    if candidate["subject"] != hosted_subject or baseline_state["subject"] != hosted_subject:
        return _abstention(
            "out_of_distribution",
            "The stored scenario does not represent the hosted twin",
        )
    if request["state"] != baseline_state:
        return _abstention(
            "out_of_distribution",
            "The deterministic reference provider only supports its exact bundled baseline state and subject",
        )
    valid_until = baseline_state.get("valid_until")
    perturbation_start = parse_timestamp(candidate["perturbation"]["starts_at"])
    if parse_timestamp(baseline_state["state_time"]) > perturbation_start or (
        valid_until is not None and parse_timestamp(valid_until) < perturbation_start
    ):
        return _abstention("stale_evidence", "The baseline BodyState does not cover perturbation start")

    declared = candidate["perturbation"]
    if requested != declared:
        return _abstention(
            "unsupported_perturbation",
            "The deterministic reference provider only supports the exact bundled perturbation",
        )

    evidence = scenario_evidence_references(candidate)
    evidence_binding_fields = ("content_digest", "observed_at", "subject", "scopes", "model_refs", "claim_refs")
    if not evidence or any(not all(reference.get(field) for field in evidence_binding_fields) for reference in evidence):
        return _abstention("insufficient_evidence", "The stored scenario lacks bound, digest-addressed evidence")
    try:
        semantic_validate(candidate)
    except Exception as exc:
        reason_code = "insufficient_evidence" if "evidence" in str(exc).lower() else "insufficient_validation"
        return _abstention(reason_code, "The stored scenario does not prove its declared applicability boundary")
    declared_horizon = candidate["applicability"]["horizon_seconds"]
    derived_horizon = scenario_horizon_seconds(candidate)
    defect = _producing_model_defect(store, candidate)
    if defect is not None:
        return _abstention(*defect)
    if declared_horizon != derived_horizon:
        return _abstention("insufficient_validation", "Declared and returned trajectory horizons do not match")
    if horizon != declared_horizon:
        return _abstention(
            "out_of_distribution",
            f"The deterministic reference provider only supports a {declared_horizon}-second horizon",
        )

    supported_scopes = set(candidate["applicability"]["scopes"])
    if set(requested_scopes) != supported_scopes:
        return _abstention("unsupported_scope", "Requested output scopes must exactly match the provider boundary")

    result = copy.deepcopy(candidate)
    semantic_validate(result)
    return result


#: The only subject a publicly discoverable descriptor may declare.
#:
#: OpenBody applicability is per-subject, so a descriptor normally names the twin it
#: applies to — which means publishing descriptors verbatim would disclose that
#: identifier. A catalogue answers "which models exist and what are they competent
#: for", a question that needs no subject at all.
CATALOGUE_SUBJECT = "subject:catalogue"


def load_model_directory(directory: Path, public: bool = False) -> dict[str, dict[str, Any]]:
    """Load `BodyModel` descriptors from disk, refusing to start on an invalid one.

    Fails closed at startup rather than per request. A host that serves an invalid
    descriptor makes every scenario citing that model unsubstantiable, and the
    failure would surface far from its cause — so an unservable directory is a
    startup error, not a runtime surprise.
    """
    models: dict[str, dict[str, Any]] = {}
    for path in sorted(directory.glob("*.json")):
        descriptor = json.loads(path.read_text())
        if descriptor.get("kind") != "BodyModel":
            raise ValueError(f"{path.name} is not a BodyModel descriptor")
        semantic_validate(descriptor)
        model_id = descriptor["id"]
        if model_id in models:
            raise ValueError(f"duplicate model id {model_id}")
        if public:
            # Refuse at startup rather than leak per request. A descriptor naming a
            # real twin cannot be served publicly, because applicability.subject is
            # an identifier for a person.
            subject = descriptor.get("applicability", {}).get("subject")
            if subject != CATALOGUE_SUBJECT:
                raise ValueError(
                    f"{path.name} declares applicability.subject {subject!r}; a public "
                    f"catalogue may only declare {CATALOGUE_SUBJECT!r}"
                )
        models[model_id] = descriptor
    return models


def create_app(
    store: InMemoryTwinStore | None = None,
    model_directory: Path | None = None,
    discovery_only: bool = False,
    observation_source: ObservationSource | None = None,
    observations_only: bool = False,
    lifespan=None,
) -> FastAPI:
    """Build the reference host.

    `observation_source` enables the admitted-observation profile using a
    configured authoritative resolver. With no resolver, observation routes do
    not exist. Ingestion accepts only exact source-version locators. The source
    is resolved again on reads, so a cached projection cannot bypass denied or
    unavailable source access. This reference host still requires a separately
    authorized/private deployment boundary before serving real clinical data.

    `model_directory` serves a validated descriptor set read-only, which is the
    deployable discovery configuration: it makes models *discoverable* and asserts
    nothing about clinical validity. Each descriptor carries its own maturity,
    validation status, and prohibited uses, so a research baseline stays labelled as
    one wherever it is served.

    `discovery_only` mounts **only** the model-discovery surface: health, the
    well-known document, capabilities, and models. No subject-bearing endpoint
    exists at all — not `/v1/state`, not `/v1/simulations`, not outcomes or
    calibrations.

    In this mode every descriptor must declare `CATALOGUE_SUBJECT`. A descriptor
    normally names the twin it applies to, so serving one verbatim would disclose that
    person's identifier through `applicability.subject`. The host refuses to start
    rather than leak it per request.

    That distinction matters for anywhere a discovery host is actually deployed. The
    default configuration is backed by the bundled demo twin, so exposing it would
    publish a `BodyState` for `subject:local-demo` and invite a reader to mistake a
    fixture for a person's data. A model descriptor carries no subject data; a
    `BodyState` is nothing but subject data. Omitting the routes is a stronger
    guarantee than guarding them, because a route that does not exist cannot be
    misconfigured into existence.
    """
    if observations_only and (discovery_only or store is None or observation_source is None):
        raise ValueError("observation-only hosting requires an explicit subject store and source resolver")
    store = store or InMemoryTwinStore.from_fixture(DEFAULT_FIXTURE)
    if model_directory is not None:
        store.models = load_model_directory(model_directory, public=discovery_only)
    app = FastAPI(title="OpenBody Reference Host", version="0.1.0-draft.2", lifespan=lifespan)

    @app.get("/healthz")
    def healthz() -> dict[str, Any]:
        """Operational liveness, outside the protocol surface.

        Reports the contract being served so a deployment check can detect a host
        running a different contract than the consumer validated against.
        """
        return {
            "status": "ok",
            "contract": contract_identity(),
            "models": len(store.models),
        }

    @app.get("/.well-known/openbody")
    def well_known() -> dict[str, Any]:
        return _capabilities(discovery_only=discovery_only, observations_enabled=observation_source is not None, observations_only=observations_only) | {"base_url": "/v1"}

    @app.get("/v1/capabilities")
    def capabilities() -> dict[str, Any]:
        return _capabilities(discovery_only=discovery_only, observations_enabled=observation_source is not None, observations_only=observations_only)

    @app.get("/v1/models")
    def list_models() -> list[dict[str, Any]]:
        models = list(store.models.values())
        try:
            for model in models:
                validate_definition("BodyModel", model)
            if not discovery_only:
                # A twin host must not disclose a descriptor for another twin. A
                # catalogue host has no hosted twin: its stricter rule is that every
                # descriptor declares CATALOGUE_SUBJECT, enforced at startup.
                _require_hosted_twin(
                    store, {model.get("applicability", {}).get("subject") for model in models}
                )
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return models

    @app.get("/v1/models/{model_id}")
    def get_model(model_id: str) -> dict[str, Any]:
        model = store.models.get(model_id)
        if model is None:
            raise HTTPException(status_code=404, detail="model not found")
        try:
            semantic_validate(model)
            if not discovery_only:
                _require_hosted_twin(store, {model.get("applicability", {}).get("subject")})
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return model

    if discovery_only:
        # Everything below discloses or accepts subject data. On a discovery
        # deployment those routes must not exist.
        return app

    if observation_source is not None:
        def resolve_observation(locator: dict[str, str]) -> dict[str, Any]:
            validate_locator(locator)
            value = observation_source.resolve(copy.deepcopy(locator))
            validate_observation(value, subject=store.state["subject"])
            if value["source"]["clinical_version"] != locator:
                raise ObservationError("version_mismatch", "Source returned another clinical version")
            return value

        def observation_http_error(error: ObservationError) -> HTTPException:
            status = 503 if error.code == "source_unavailable" else 422
            return HTTPException(status_code=status, detail={"code": error.code, "message": str(error)})

        @app.get("/v1/observations/profile")
        def observation_profile() -> dict[str, Any]:
            from .observation import SCHEMA
            return {"profile": OBSERVATION_PROFILE, "schema": SCHEMA}

        @app.post("/v1/observations")
        def ingest_observation(locator: dict[str, Any]) -> dict[str, Any]:
            try:
                value = resolve_observation(locator)
                store.put_observation(value)
                return store.observation(value["id"])
            except ObservationError as error:
                raise observation_http_error(error) from error

        @app.get("/v1/observations/{observation_id}")
        def read_observation(observation_id: str) -> dict[str, Any]:
            try:
                stored_observation = store.observation(observation_id)
                current = resolve_observation(stored_observation["source"]["clinical_version"])
                if current != stored_observation:
                    raise ObservationError("source_changed", "The source no longer confirms this stored observation")
                return current
            except KeyError as error:
                raise HTTPException(status_code=404, detail="observation not found") from error
            except ObservationError as error:
                raise observation_http_error(error) from error

    if observations_only:
        return app

    @app.get("/v1/state")
    def get_state() -> dict[str, Any]:
        semantic_validate(store.state)
        return store.state

    @app.get("/v1/state/{coordinate:path}")
    def get_subsystem_state(coordinate: str) -> dict[str, Any]:
        normalized = coordinate if coordinate.startswith("ob://") else f"ob://{coordinate}"
        for subsystem in store.state.get("subsystems", []):
            if subsystem.get("coordinate") == normalized:
                validate_definition("BodySubsystemState", subsystem)
                return subsystem
        raise HTTPException(status_code=404, detail="OpenBody coordinate not present in current state")

    @app.get("/v1/trajectories/{trajectory_id}")
    def get_trajectory(trajectory_id: str) -> dict[str, Any]:
        trajectory = store.trajectories.get(trajectory_id)
        if trajectory is None:
            raise HTTPException(status_code=404, detail="trajectory not found")
        try:
            validate_definition("BodyTrajectory", trajectory)
            _require_hosted_twin(store, {state.get("subject") for state in trajectory.get("states", [])})
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return trajectory

    @app.post("/v1/simulations")
    def simulate(request: dict[str, Any]) -> dict[str, Any]:
        try:
            result = _reference_simulate(store, request)
            semantic_validate(result)
            return result
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/v1/simulations/{scenario_id}")
    def get_simulation(scenario_id: str) -> dict[str, Any]:
        scenario = store.scenarios.get(scenario_id)
        if scenario is None:
            raise HTTPException(status_code=404, detail="scenario not found")
        try:
            semantic_validate(scenario)
            # Every disposition carries a required baseline trajectory, so the
            # hosted-twin binding cannot be limited to simulated scenarios.
            subjects = {scenario.get("subject")}
            for trajectory_name in ("baseline", "counterfactual"):
                trajectory = scenario.get(trajectory_name)
                if trajectory is not None:
                    subjects.update(state.get("subject") for state in trajectory.get("states", []))
            _require_hosted_twin(store, subjects)
            if scenario.get("disposition") == "simulated":
                defect = _producing_model_defect(store, scenario)
                if defect is not None:
                    raise ValueError(defect[1])
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return scenario

    @app.post("/v1/outcomes", status_code=202)
    def record_outcome(value: dict[str, Any]) -> dict[str, Any]:
        try:
            store.put_outcome(value)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return value

    @app.post("/v1/calibrations", status_code=202)
    def record_calibration(value: dict[str, Any]) -> dict[str, Any]:
        try:
            store.put_calibration(value)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return value

    return app


def create_observation_host_from_env() -> FastAPI:
    """Uvicorn factory for source-backed ingestion without a fabricated Twin.

    Start with `uvicorn openbody_ref.host:create_observation_host_from_env --factory`.
    The private deployment's access boundary remains the operator's responsibility,
    exactly as for the existing reference host. This factory never uses a demo state.
    """
    from .observation import ProvidEHRObservationSource
    names = ("OPENBODY_SOURCE_URL", "OPENBODY_SOURCE_TOKEN_FILE", "OPENBODY_SOURCE_TENANT", "OPENBODY_SOURCE_EHR")
    configuration = {name: os.environ.get(name, "") for name in names}
    if not all(configuration.values()):
        raise ValueError("source URL, token file, tenant and EHR are required for observation hosting")
    with Path(configuration["OPENBODY_SOURCE_TOKEN_FILE"]).open("rb") as token_file:
        token = token_file.read(8193)
    if not token or len(token) > 8192:
        raise ValueError("source token file must contain a bounded credential")
    source = ProvidEHRObservationSource(configuration["OPENBODY_SOURCE_URL"], token.decode("utf-8").strip(),
                                       configuration["OPENBODY_SOURCE_TENANT"], configuration["OPENBODY_SOURCE_EHR"])
    store = InMemoryTwinStore(state={"subject": f"subject:providehr:ehr:{configuration['OPENBODY_SOURCE_EHR']}"})
    @asynccontextmanager
    async def source_lifespan(app):
        try:
            yield
        finally:
            source.close()

    return create_app(store=store, observation_source=source, observations_only=True, lifespan=source_lifespan)


app = create_app()
