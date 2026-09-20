# Upstream evidence lock

Checked 2026-09-20.

The current SCKAN documentation directs programmatic users to the latest GitHub/Zenodo release and supports Cypher/SPARQL. The latest GitHub release found is `sckan-2026-06-23`, explicitly marked **pre-release**. GitHub supplies SHA-256 digests for the release and graph assets; these are pinned in `upstream-lock.json`.

This improves artifact identity but does not establish a final/stable SCKAN release. We therefore keep M0 research-only and refuse silent upgrades.

The Guided Mode target is dataset 364/version 1, DOI `10.26275/0JZ3-ZRLO`,
with template `7bb84d3a-24b2-11ee-a4be-02420a0bc195`. The previous UUID belongs
to ASCENT Tutorial (dataset 365), as independently shown by its authenticated
file and versioned ASCENT documentation. The lock retains the rejected UUID and
links the [identity chain](evidence/receipts/ascent-identity.json).
These studies are INCOMPARABLE, not interchangeable revisions.

The deposited README and workbook identify ASCENT 1.2.1. Guided Mode uses
pre-solved FEM potentials; exact potential/input/output bytes and solver versions
are not deposited. The generic source template's threshold-search stopping rule
is not a reproduction tolerance. Warnings about older simulations in the Portal
tutorial refer to a separate dataset (311), not an authenticated Guided Mode run.

## Query-reproduction gate

A real SCKAN container/graph must be downloaded and its bytes checked against the pinned upstream SHA-256 before any upstream query is called reproduced. Record the exact query text, engine (Cypher/SPARQL), result serialization, row count and result digest. The adapter must compare literal results; no biological inverse/transitive inference is permitted.
