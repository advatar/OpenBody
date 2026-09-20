# Upstream evidence lock

Checked 2026-09-20.

The current SCKAN documentation directs programmatic users to the latest GitHub/Zenodo release and supports Cypher/SPARQL. The latest GitHub release found is `sckan-2026-06-23`, explicitly marked **pre-release**. GitHub supplies SHA-256 digests for the release and graph assets; these are pinned in `upstream-lock.json`.

This improves artifact identity but does not establish a final/stable SCKAN release. We therefore keep M0 research-only and refuse silent upgrades.

The SPARC documentation identifies ASCENT Guided Mode Demo Version 1 (DOI 10.26275/0JZ3-ZRLO) and the corresponding o2S2PARC study. The tutorial also warns that runtime/version differences can cause small numerical differences. Consequently no tolerance is guessed: reference output bytes, model/runtime version, parameters and metric must be captured first.

## Query-reproduction gate

A real SCKAN container/graph must be downloaded and its bytes checked against the pinned upstream SHA-256 before any upstream query is called reproduced. Record the exact query text, engine (Cypher/SPARQL), result serialization, row count and result digest. The adapter must compare literal results; no biological inverse/transitive inference is permitted.
