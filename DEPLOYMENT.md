# Deploying OpenBody

This document is the operational handover for running the OpenBody reference host
on your own server. It covers what is runnable, what it deliberately does not do,
and what you must supply around it.

Read [`ARCHITECTURE.md`](ARCHITECTURE.md) for why the modes below are separate, and
[`docs/ADMITTED_OBSERVATIONS.md`](docs/ADMITTED_OBSERVATIONS.md) for the clinical
source boundary.

## What is deployable

Most of this repository is protocol: schemas, OpenAPI, the MCP profile, the
coordinate registry, and the normative prose. Two things execute.

| Artifact | What it is |
| --- | --- |
| `reference/python/openbody_ref` | The conformance-first reference host and client (FastAPI) |
| `tools/validate_openbody.py` | Schema plus protocol-invariant conformance validator |

The reference host exists to prove interoperability. Its bundled simulation
provider replays one bundled subject, perturbation and horizon and abstains on
every mismatch. It is not a clinical model and is not a medical device.

## Prerequisites

* **Python 3.12.** `pyproject.toml` requires `>=3.11`; CI validates on 3.12. A
  system Python 3.9 will not run this.
* **Docker** (for the container path) or a systemd host with a dedicated user.
* **A terminating proxy** you control. The host implements no authorization.
* **For `observations` mode only:** a reachable ProvidEHR deployment, a bearer
  token, and the tenant and EHR identifiers this instance is authorized for.
  No ProvidEHR access? Run `observations-local`, which serves the same ingestion
  path from a directory of admitted version documents and requires no clinical API.

## Four modes, chosen by `OPENBODY_MODE`

The modes are not configuration flavours of one service. They differ in which
routes exist at all, which is a stronger guarantee than guarding them.

### `catalogue` — publishable

Discovery only: `/healthz`, `/.well-known/openbody`, `/v1/capabilities`,
`/v1/models`. No `/v1/state`, no simulations, no outcomes, no calibrations —
those routes are not mounted. Every descriptor in `OPENBODY_MODEL_DIRECTORY`
must declare `applicability.subject = "subject:catalogue"`, and the host refuses
to start otherwise, because a descriptor normally names the twin it applies to
and `applicability.subject` identifies a person. Build the directory with
`python tools/make_catalogue.py --out DIR DESCRIPTOR...`, which performs and
checks that transform rather than trusting a hand edit.

This is the mode that is multi-tenant and safe to deploy immediately.

### `observations` — source-backed, single-tenant

Ingests admitted clinical observations by exact version locator and loads no demo
state. The caller submits a locator, never values or admission status: the host
re-resolves the authoritative version through the configured ProvidEHR origin on
every read, so a cached projection cannot outlive denied source access.

Requires all four of `OPENBODY_SOURCE_URL`, `OPENBODY_SOURCE_TOKEN_FILE`,
`OPENBODY_SOURCE_TENANT`, `OPENBODY_SOURCE_EHR`; startup fails if any is empty.
The URL must be HTTPS unless it is loopback, and may carry no embedded
credentials, query or fragment. The token file must be non-empty and at most
8192 bytes.

### `observations-local` — the same path, no clinical API

Identical ingestion, store and read paths to `observations`; only the resolver
differs. Instead of calling ProvidEHR, it indexes a directory of admitted clinical
version documents and verifies each one **at startup** with the same function the
API resolver uses: locator identity, template, tenant, projection and admission
agreement, payload digest, and canonical clinical values. A tampered document does
not produce a bad read later — it refuses to start the host.

```bash
cd deploy/openbody && cp env.example .env
# .env: OPENBODY_MODE=observations-local, OPENBODY_ACCEPT_LOCAL_SOURCE=yes,
#       OPENBODY_SOURCE_TENANT=synthetic-tenant,
#       OPENBODY_SOURCE_EHR=11111111-1111-4111-8111-111111111111,
#       OPENBODY_SOURCE_DIRECTORY_HOST=../../examples/local-observations
docker compose --profile observations-local up -d --build
```

[`examples/local-observations/`](examples/local-observations/) ships one runnable
document — the synthetic body-temperature composition produced by the real
ProvidEHR projector — with the locator to POST to `/v1/observations`.

What this substitutes is the transport, not the policy. It cannot admit anything
the production path would reject, and it verifies no less. What it gives up is the
authorization boundary: **the file system becomes the trust boundary**, so whoever
can write that directory decides what counts as admitted. Mount it read-only, keep
it synthetic, and never point this mode at real patient data. `/healthz` reports
`"observation_source": "local-directory"` so an operator can tell the two apart,
and the mode requires `OPENBODY_ACCEPT_LOCAL_SOURCE=yes` rather than letting a
non-authoritative source arrive by leaving a variable unset.

### `demo-twin` — local development

The bundled `subject:local-demo` fixture, served as a complete `BodyState` to
anyone who reaches the port. It requires `OPENBODY_ACCEPT_DEMO_TWIN=yes` so that
exposing a fixture that reads like a person's record has to be a decision.

## Container path

```bash
cd deploy/openbody
cp env.example .env         # fill in
docker compose --profile catalogue up -d --build
curl -s http://127.0.0.1:8797/healthz | python -m json.tool
```

The image can re-run its own conformance suite, which is the fastest way to prove
a deployed image serves the contract you validated:

```bash
docker run --rm -e PYTHONPATH=/app/reference/python openbody-host:local \
  pytest -q reference/python/tests -k "not identity_changes_when_an_artifact_changes"
```

The deselected test mutates `registry/coordinates.json` to prove the contract
digest tracks it. The image's application tree is root-owned and the process runs
unprivileged, so that write is correctly refused — run the full suite from a
writable checkout.

Both compose services publish on `127.0.0.1` only, run read-only with all
capabilities dropped, and drop to an unprivileged user.

## Systemd path

`deploy/openbody/openbody-host.service` installs the checkout at
`/opt/openbody/src` with a 3.12 virtualenv at `/opt/openbody/venv` and reads its
configuration from `/etc/openbody/host.env`. Installation steps are in the unit's
header comment.

## Proxy and network boundary

`deploy/openbody/Caddyfile.example` has a public read-only block for catalogue
hosting and a client-certificate block for a subject API. The requirement behind
it is not Caddy-specific: **the upstream port must not be reachable without an
authenticated boundary in front of it.**

## Constraints you must design around

These are properties of the current implementation, not oversights to work around
quietly.

* **A local source is not an authority.** `observations-local` exists so the
  protocol path can run standalone. Any deployment handling real clinical data
  resolves through the authorized clinical API; the admitted-observation profile
  adds no authority to the originating admission in either mode.
* **No authorization, by design.** `/.well-known/openbody` advertises
  `"schemes": []` and means it. Anything that reaches the port can read state and
  POST outcomes and calibrations. Authority lives outside this host; the protocol
  says a model may propose and a separate layer authorizes.
* **State is in memory.** `InMemoryTwinStore` holds observations, scenarios,
  outcomes and calibrations. A restart drops all of them, and there is no
  database, migration or backup path. Treat a running host as a conformance
  surface, not a system of record; the authoritative clinical record stays in the
  source system.
* **The checkout is the runtime.** `openbody_ref` resolves `schemas/`,
  `registry/` and `examples/` from the repository root via
  `Path(__file__).resolve().parents[3]`. Deploy the whole tree and set
  `PYTHONPATH=<checkout>/reference/python`. Installing the built wheel alone will
  import and then fail to read its own schemas.
* **Single-tenant by construction.** `store.state["subject"]` is the hosted twin
  and every read path binds to it. Serve multiple subjects as one instance per
  subject behind a shared gateway. A shared process whose subject is configured
  rather than authenticated per request converts a structural guarantee into a
  deployment assumption.
* **The contract is identified by digest, not by tag.** `/healthz` and
  `/.well-known/openbody` report `schema_version`, `registry_version` and
  per-artifact digests. Compare those against what your consumer validated
  against; a release tag cannot tell you whether the served contract changed.

## Verifying a deployment

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
PYTHONPATH=reference/python python tools/validate_openbody.py
PYTHONPATH=reference/python pytest -q reference/python/tests
curl -s https://<host>/healthz | python -m json.tool     # contract digests
curl -s https://<host>/.well-known/openbody | python -m json.tool
```

CI (`.github/workflows/conformance.yml`) runs the same validator and suite on
every pull request and push to `main`.

## Landing page

The marketing site is a separate private submodule,
`git@github.com:advatar/openbody-display.git`, checked out at `LandingPage/`. It
needs its own GitHub access and a Bun/Node toolchain (`bun install`,
`bun run build`), and is served on `:8796` behind its own proxy site block. It is
authored through Lovable, which commits to that repository directly, so local
hand edits can be overwritten. It shares nothing with the protocol host; a clone
without submodule access still deploys everything above.
