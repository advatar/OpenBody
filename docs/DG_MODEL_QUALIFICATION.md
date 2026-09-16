# Current DG qualification at the model boundary

`create_dg_model_execution_host` installs `DgQualificationAuthority` in the actual
`QualifiedModelRuntime` execution and retained-read routes. DG resolves the current
human-model revision, independent review, separate subject consent, objections,
evidence and operator standing, using EUWallet-verified credential inputs. The
runtime checks qualification before and after the model call and on every retained
read. Failure returns an `Abstention`; no unavailable-graph fallback is installed.

This adapter verifies model eligibility. Consequential clinical effects require a
separate fresh DG authorization bound to the exact effect at its execution boundary.
Capabilities and credentials alone do not provide permission.

## Host configuration and reviewed model

The trusted embedding host supplies subject, tenant, source resolver, verified model
registrations, `DgQualificationConfig` and model-ID-to-`DgModelBinding` mappings.
The config contains an absolute fixed command, independently pinned Ed25519 public
key, execution policy (including credential policy digest), operator principal,
explicit `DECISION_GRAPH_*` environment and bounded timeout. No inherited provider
credentials reach the child. Clinical requests cannot select trust settings.
Transport authentication, model loading and subject provisioning remain host duties.

For each contract, compute `qualification_candidate(contract, tenant, subject)`.
It binds the complete contract digest, artifact, uses, populations, questions,
horizons, dependencies and qualification evidence. Propose that exact object as a
DG `HumanModel` candidate for the same subject. Its reviewed effect must contain:

```python
{
    "id": "host-chosen-qualification-effect",
    "action": "model.qualification.read",
    "provider": "openbody",
    "tool": "openbody_resolve_model_qualification",
    "resource": "host/chosen/model/resource",
    "arguments": candidate,
}
```

The change resource equals the effect resource; host mappings pin both the change
ID and complete effect. Configure the matching native execution route and current
operator standing. Reviewers and the separate consenting subject sign native DG
challenges with holder-bound credential proofs before activation. Current status,
trust, scope and graph authority are rechecked on every qualification resolution.

`qualification_evidence(candidate)` returns the exact JSON descriptors that must
be stored as protected DG Finding payloads, with each reference also used as the
Finding ID. Include **every** descriptor reference in `ChangeRequest.evidence_refs`
before review. Dependency descriptors use `openbody.model_dependency.v1`; evidence
descriptors use `openbody.model_evidence.v1`. Each includes `reference`, the declared
`content_digest` and `kind`. References must be unique across both groups.

The adapter requires exact coverage by the native reviewed commitments and compares
the signed plaintext content digest to the expected descriptor's JCS digest. An
otherwise valid signed candidate that omits native review of a dependency refuses.
DG rechecks the frozen reference's current binding, retained payload and revocation.
Descriptors are reviewed content identities, not proof of scientific truth. The
trusted loader must execute the actual pinned artifact and declared dependencies;
reviewed evidence must support the claimed purpose and population independently.

## Wire verification and retained provenance

The command is the native wallet-enabled `decision-graph-wallet resolve-qualification`
with persistent `--db-url` and normal host policies/keys plus `--credential-config`.
Each request has a new random 32-byte nonce; its operation identity binds the full
model request and contract. DG request/reply domains differ from effect authorization.
The verifier uses RFC 8785 canonical JSON and Ed25519. It checks the signature,
complete pending challenge, subject, candidate, reviewed evidence, commitment shapes
and current issue/expiry window. OpenBody's existing contract digests keep their
own canonicalization; they are not silently reinterpreted as native DG digests.

Unix subprocess input/output are limited to 512 KiB, all pipe activity and process
exit share a deadline of at most ten seconds, and failure kills the owned process
group. Only explicitly configured environment variables reach the child. This is
bounded command execution, not a sandbox for an untrusted executable. Keep command,
config and ancestor directories under trusted host control.

The model receipt identifies the stable reviewed decision. Source provenance also
retains `qualification_resolution_ref` for the fresh DG audit receipt. A new audit
receipt alone does not change the semantic qualification lease. Changed model
revision, evidence, current authority or validity limits do. Refreshing a source
with different validity bounds may conservatively invalidate a retained result.
A historical result or receipt is not permission to reuse its output later.

## Reproduce locally

Build DG's wallet binary and test fixture from the source checkpoint recorded in
`STATUS.md` and DG PR #8:

```sh
cargo +1.97.1 build --locked --manifest-path /path/to/DG/integrations/euwallet/Cargo.toml \
  --bin decision-graph-wallet --example model-qualification-fixture
```

Then run OpenBody's actual composition with explicit absolute executable paths:

```sh
DG_WALLET_TEST_BIN=/absolute/decision-graph-wallet \
DG_MODEL_FIXTURE_BIN=/absolute/model-qualification-fixture \
DG_SURREAL_TEST_BIN=/absolute/surreal \
PYTHONPATH=reference/python python -m pytest -q reference/python/tests/test_dg_model_composition.py
```

The tests own a temporary loopback SurrealDB 3.1.4 server and terminate it afterward.
They use real native DG review/activation, real EUWallet issuer/holder/status crypto,
separate command processes and the actual FastAPI model boundary. Public synthetic
software keys and arithmetic are confined to fixtures. Without the three binary
paths these eight composition tests explicitly skip; wire/unit tests run normally.
Setting only some paths is an error, not a silently skipped qualification run.

Positive execution preserves unknown input uncertainty. Negative cases cover revoked
reviewer/operator/subject credential status, withdrawn consent, revoked evidence,
missing inputs, omitted native review dependencies and withdrawal during execution.
These establish enforcement, not clinical efficacy, issuer enrollment, independent
patient identity or production device key provisioning. Native physiological model
integration, qualified model composition and full G3/G4/G7/G8/G17 remain open.
