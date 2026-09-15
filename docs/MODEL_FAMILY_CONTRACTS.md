# Model-family execution profile v1

Issue #18 implements an additive `openbody.model-family-contract.v1` profile
alongside the frozen OpenBody core 0.1 schema. Its schema is
`schemas/model-family-contract.schema.json`. Required fields cover exact model
artifact identity and coordinate, context of use, required admitted observations,
population, question, horizon, allowed adaptation, behavioral and uncertainty
bounds, abstention rules, prohibited uses, dependencies and qualification evidence.
A descriptor or a nonempty evidence reference does not establish qualification.

The reference executor supports **current state estimation** (horizon zero) and
explicitly registered **forecasts** and **intervention counterfactuals** (positive
horizons). Multi-model composition, native model call sites and the
production DG authority adapter remain unfinished G3/G4 work. Synthetic
arithmetic in the tests verifies software enforcement, not physiology or clinical
utility. This profile neither qualifies existing Model Plane labels nor supplies
a default model or permissive authority.

## Trusted inputs and qualification

`QualifiedModelRuntime` requires an explicit hosted subject and tenant,
`ObservationSource`, `QualificationAuthority`, and registered executable models.
The loader supplies the exact artifact bytes and callable; their artifact digest
must match the contract. The loader is trusted to execute those bytes with only
the declared dependencies. It is not a sandbox for arbitrary model code.

`QualificationAuthority.resolve` must obtain a current verified decision from
the host's trusted governance registry. Its lease binds the exact contract and
artifact, tenant/subject, purpose, population, question, horizon, evidence and
dependency digests, revision and validity window. The adapter must verify the
underlying qualification evidence, subject/population attestations, approval
authority and transitive dependency status. No such production DG adapter is
shipped in this slice. The fixed authority in tests is only a synthetic fixture.
There is no HTTP field for supplying a qualification lease or executable model.

Purpose is a machine code (`software_test`, `research`, or
`clinical_decision_support`), not an unrestricted prompt. Each purpose requires
its corresponding evidence class in the contract and matching current authority.
A software qualification cannot satisfy clinical use. A clinical approval does
not by itself authorize an intervention; that remains a separate DG/Mandamus
boundary.

## Execution and retained results

1. Validate the contract, request and artifact identity. Check subject, tenant,
   allowed use, population, question, horizon and adaptation bounds.
2. Resolve current qualification/dependency evidence from the trusted authority.
3. Resolve each exact clinical locator through the configured source. Reject
   source mismatch, cross-tenant/patient records, duplicate compositions, missing
   inputs, unsupported canonical code/unit/value, stale/future timestamps and
   source out-of-distribution status. Only required inputs reach the model.
4. Execute the registered callable with copies of the admitted facts and bounded
   parameters. Require exactly the declared metrics, finite numeric values,
   behavioral bounds and valid uncertainty. Model failures abstain.
5. Re-resolve the source objects and qualification after execution. A change,
   revocation, expiry or unavailability prevents returning the result.
6. Construct a separately typed core `BodyState`, a `ModelForecast` envelope containing a frozen-core `BodyTrajectory`, or a
   `ModelCounterfactual` containing a frozen-core scenario and comparison forecast. Observations keep their source,
   normalization and unknown uncertainty in evidence provenance; no source value
   is rewritten. Unknown input uncertainty either causes abstention or propagates
   as unknown in the output, according to the qualified contract.

The model receipt's `input_digest` covers the request, selected full observations
and effective parameters. `output_digest` covers the emitted state vector and
uncertainty. `environment_digest` binds the complete model-family contract,
including artifact/dependency/evidence identities. `validation_ref` identifies the
current authoritative qualification decision; source provenance retains its
revision. None of these digests substitutes for authentication or authority.

Retained results are in-memory reference state, bounded to 512 executions and
32 MiB of serialized retained content. Each result read repeats source and lease
checks; possession of an old result ID is insufficient authority. Responses use
`Cache-Control: no-store`. Consumers must revalidate before future use. Durable
cross-repository revocation, latest-version reconciliation and downstream action
invalidation remain part of G17; an immutable historical source endpoint alone
cannot establish that a newer record has not revoked its use.

## Reference HTTP surface

`create_model_execution_host(runtime)` mounts only the explicit execution
profile. It does not enable fixture replay, public patient state or default
qualification. The embedding host must provide authenticated transport and the
trusted configured resolvers. Public discovery startup does not mount these
routes.

| Operation | Route |
|---|---|
| Discover profile/capabilities | `GET /v1/capabilities` |
| Read exact schema | `GET /v1/model-families/profile` |
| Discover registered contracts | `GET /v1/model-families` |
| Execute qualified state, forecast or counterfactual | `POST /v1/model-executions` |
| Revalidate retained result | `GET /v1/model-executions/{id}` |
| Create inert adaptation candidate | `POST /v1/model-adaptation-candidates` |

Execution requests follow `$defs.ExecutionRequest`. Source locators, not caller
observation bodies, select input evidence. Unsupported requests and failed
execution return core `Abstention`; `OpenBody-Execution-Reason` carries a bounded
operational reason code. The client verifies returned type, subject, producer,
contract, output scope, bounds, digest and retained execution identity.

An adaptation within the declared parameter envelope can execute under the
current qualification. An out-of-envelope request is refused. Proposal returns
`$defs.AdaptationCandidate`, with `activated: false` and `dg_review_required`.
It neither mutates the registered model nor publishes a DG decision. Submission,
review, activation and native adaptation storage remain G4/G7 follow-up work.

## Forecast execution and time semantics

A `ForecastModelRegistration` binds verified artifact bytes to a callable receiving
admitted inputs, bounded adaptation parameters and the exact qualified horizon.
Its contract permits only positive horizons; an ordinary `ModelRegistration`
permits only `[0]`. The same execution/read routes return `$defs.ForecastResult`
with kind `ModelForecast`. The client rejects a future forecast returned as a
current-state result. An ordinary forecast request cannot carry a perturbation. Counterfactual
simulation requires the explicit contract and registration described below.

The callable returns `ForecastEvaluation`: 2–512 ordered `ForecastPoint` values,
each with a `ModelEvaluation`, aggregate uncertainty and bounded assumptions.
Offsets begin at zero and end at the exact requested horizon. Every point must
satisfy the metric, uncertainty and out-of-distribution rules. The origin is
captured before execution; completion after the final prediction time abstains.
Accumulated serialized states are bounded to 8 MiB before further points are built,
with the existing overall execution/retention bounds still applied.

The output uses `trajectory_kind: predicted`. Source uncertainty propagates to
each point; unknown point uncertainty also prevents a quantified aggregate. Each
point keeps its source versions and qualification revision. The aggregate receipt
binds origin, horizon, exact request digest, qualification expiry, ordered complete
states, uncertainty and assumptions. Clients check those bindings, consistent
source/qualification across points, bounds, time order and exact execution ID.

`qualification_valid_until` describes permission to execute/read, which may end
before a predicted future time. It is carried separately on the forecast envelope.
Nested states omit the core `valid_until` field, whose meaning concerns the state's
physiological time. The runtime never extends qualification to reach a forecast
horizon. Reusing a retained forecast still requires a fresh source and qualification
check; extracting a nested state does not confer independent authority.

The schema's trajectory reference resolves against the frozen core schema supplied
locally to the validator; verification requires no network schema retrieval.
Forecast tests execute deterministic synthetic arithmetic, not a physiological
forecast or clinical qualification. Native source integration and qualified model registration remain required for
the post-meal family. Execution results now expose the exact purpose, population
and question alongside the request digest; those fields are receipt-bound.

## Qualified intervention counterfactuals

The optional contract `counterfactual` section declares exact permitted
perturbation IDs, classes, scope, required numeric parameters and units, parameter
bounds and per-metric effect bounds. Its timing policy is `execution_time`: this
version simulates an intervention starting at model invocation. Scheduled starts
are not supported. A `CounterfactualModelRegistration` is required; ordinary
state/forecast registrations cannot consume or advertise this contract.

Requests use `$defs.CounterfactualRequest`. Callers select a perturbation ID and
bounded parameters. The host derives its class, scope and start time from the
qualified contract and clock. Supplied authority references, alternative scopes,
classes, timing or extra parameters are refused before the model runs. This
qualification permits simulation only and grants no authority to carry out an
intervention; DG/Mandamus still govern those effects separately.

The actual callable returns `CounterfactualEvaluation`: a control forecast,
intervention forecast, uncertainty for each declared effect, overall uncertainty
and bounded assumptions. Both forecasts must have the same initial model state,
time grid and exact horizon, and satisfy all forecast metric, uncertainty and
size limits. The runtime computes each effect as intervention minus control at
the final shared time and enforces its effect bounds. It does not subtract the
present baseline from a future intervention outcome or synthesize confidence
intervals by assuming independence. Unknown source, arm or effect uncertainty
remains unknown in effects and the overall scenario.

`$defs.CounterfactualResult` has kind `ModelCounterfactual`. Its `scenario` is a
frozen-core `CounterfactualScenario` with an initial-state baseline and an
intervention trajectory. The core baseline represents state at or before the
perturbation; the future no-intervention comparison therefore remains explicitly
available as `comparison_forecast`. Results label effects as `counterfactual`,
carry `generalizable: false`, and never turn estimates into observations or
clinical assertions.

Both arms retain the same admitted source evidence and qualification revision,
with distinct execution/state identities and explicit scenario claim references.
The aggregate receipt binds the complete comparison, context, perturbation,
effects, uncertainty, time and qualification expiry. Clients verify these bindings,
including the same-horizon differences, and reject a lone forecast returned for a
counterfactual request. Existing source/qualification checks run after construction
and on every retained read. Counterfactual output is limited to 12 MiB before the
runtime's total execution and retention bounds are applied.

The 42 counterfactual tests exercise the actual callable and HTTP path with
synthetic arithmetic and a fixture authority. They establish software enforcement,
not physiological validity, causal identification, clinical efficacy or DG
intervention approval. Production authority resolution and native model/source
integration remain unfinished G3/G4 work.
