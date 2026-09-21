# Local observation source

A runnable directory for `OPENBODY_MODE=observations-local`: admitted clinical
version documents resolved from disk instead of from an authorized clinical API.

The bundled document is the synthetic body-temperature composition produced by the
real ProvidEHR projector and used by the conformance suite. Its patient, tenant and
EHR are synthetic.

```
tenant_id        synthetic-tenant
ehr_id           11111111-1111-4111-8111-111111111111
composition_uid  22222222-2222-4222-8222-222222222222
version_uid      22222222-2222-4222-8222-222222222222::provid-ehr::1
```

Ingest it against a host started in this mode:

```bash
curl -s http://127.0.0.1:8797/v1/observations \
  -H 'content-type: application/json' \
  -d '{"tenant_id":"synthetic-tenant",
       "ehr_id":"11111111-1111-4111-8111-111111111111",
       "composition_uid":"22222222-2222-4222-8222-222222222222",
       "version_uid":"22222222-2222-4222-8222-222222222222::provid-ehr::1"}'
```

**This directory is not a clinical authority.** Every document here is verified
exactly as an API response is — locator identity, template, tenant, projection and
admission agreement, payload digest and canonical clinical values — so nothing
inadmissible can be served. What disappears is the authorization boundary: whoever
can write this directory decides what counts as admitted. Mount it read-only, and
never point this mode at real patient data.
