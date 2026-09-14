# Admitted clinical observation profile

`openbody.admitted-observation.v1` is an additive measured-observation profile.
It does not change the frozen OpenBody 0.1 core schema. Its schema is
[`schemas/admitted-observation.schema.json`](../schemas/admitted-observation.schema.json).
The host advertises the profile and its schema digest separately from core
contract identity, only when an authoritative observation source is configured.

ProvidEHR's actual COSMIC worker writes the projection into
`composition.context.openbody_observation` in the same atomic transaction as the
immutable clinical version, original fetched FHIR JSON, normalization result,
replay receipt and integration event acknowledgement. Only normalized canonical
observations have a projection. Partial/review sources retain their clinical
evidence but never become an Observation in this profile.

The projection preserves canonical coding, quantity/UCUM unit, effective time,
source identity/version/digest, contained-resource parent, patient binding, and
the normalization rule pack and transformation trace. Unknown effective time
remains null. Unquantified uncertainty remains null/`unknown`; successful
terminology normalization does not prove a measurement's certainty or a model's
fitness. The source digest names SHA-256 over ProvidEHR's fetched JSON hash
representation, not original HTTP response bytes.

`subject:providehr:ehr:{ehr_id}` is the explicit inter-system subject convention.
The exact tenant, EHR, composition and version remain separate in
`source.clinical_version`. No probabilistic patient matching occurs here.

## Ingestion and reads

`POST /v1/observations` accepts **only** this locator:

```json
{
  "tenant_id": "synthetic-tenant",
  "ehr_id": "11111111-1111-4111-8111-111111111111",
  "composition_uid": "22222222-2222-4222-8222-222222222222",
  "version_uid": "22222222-2222-4222-8222-222222222222::provid-ehr::1"
}
```

The configured `ProvidEHRObservationSource` resolves the existing
`GET /v1/ehr/{ehr}/composition/{composition}/version/{version}` API, which enforces
`patient/composition.read`. Caller input cannot choose credentials or an origin.
The consumer requires exact subject/version/tenant, canonical template, source
provenance, admission and clinical-value agreement. Redirects are refused;
remote source origins require HTTPS. The host never accepts caller-provided
values or an asserted normalization status as admission evidence.

Identical ingestion is idempotent. Conflicting content for an immutable version
is rejected. `GET /v1/observations/{id}` validates the stored record and resolves
the authorized source again; denied/unavailable source access never returns a
cached observation. Historical evidence is retained. This does not yet provide
transitive model/evidence revocation, which belongs to production closure G17.

## Run a private observation host

Use a source access token authorized for the bound tenant and EHR, supplied in
a file. Keep this reference service on loopback or behind an authenticated
private deployment boundary; it has no independent inbound identity provider.

```sh
export OPENBODY_SOURCE_URL=https://providehr.example
export OPENBODY_SOURCE_TOKEN_FILE=/run/secrets/providehr-source-token
export OPENBODY_SOURCE_TENANT=your-tenant
export OPENBODY_SOURCE_EHR=your-ehr-id
PYTHONPATH=reference/python uvicorn \
  openbody_ref.host:create_observation_host_from_env --factory --host 127.0.0.1
```

This factory requires explicit configuration and does not load the demo Twin.
It exposes observation ingestion/read with an in-memory store. It does not
expose BodyState, trajectory, simulation, outcome or calibration routes. Model
assimilation, durable Twin evolution and model-family qualification require the
G3/G4 consumer integration. Observation, model-derived state, simulation and
clinical assertion remain different types; the existing clinical assertion
reference profile explicitly excludes Observation.

## Executable evidence and its limits

`reference/python/tests/fixtures/providehr-kernel-observation.json` is generated
by ProvidEHR's `openbody_observation_fixture` example with synthetic data. It
checks cross-language encoding and admission binding, and does not claim that a
worker/store ran. Regenerate from the producer, rather than hand-editing values:

```sh
cargo run --locked -p ehr-integration --features openehr-projection \
  --example openbody_observation_fixture > providehr-kernel-observation.json
```

`tools/verify_providehr_observation.py` instead connects to an actual gateway
started by ProvidEHR's `inbound_admission_openbody_live_protocol` integration
test after its real COSMIC worker commits synthetic input. It starts a real
OpenBody HTTP host and verifies conversion, provenance, read/replay, partial and
review rejection, subject/tenant rejection and separation from BodyState. It
receives the ephemeral source token on stdin and prints only pass/fail evidence.
The source test uses the in-memory ClinicalStore backend and an injected COSMIC
transport; it is execution-path evidence, not a live vendor deployment claim.
Record the exact producer/consumer revisions and successful CI run before
claiming this cross-repository check passed.

The integration runner can also exercise the separately typed model-reference
return through ProvidEHR's admission and simulation endpoints. It uses the
existing synthetic scenario rebound to the synthetic EHR/test clock, preserving
its `statistical_association` class and uncertainty. That proves transport and
type separation; it does not execute a model on the new observation. The
producer enforces physician admission/record grants and clinical read grants,
and revalidates stored EHR/tenant/subject/digest/current validity on reads.
Execution of this expanded check is tracked in advatar/ProvidEHR#525. Neither
the fixture nor the forward bridge alone closes G2.
