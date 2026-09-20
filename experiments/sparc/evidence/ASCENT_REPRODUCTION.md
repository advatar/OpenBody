# ASCENT provenance investigation — 2026-09-20

**Final reproduction state: BLOCKED. No candidate was executed. No reproduction
contract or numerical tolerance was frozen.** A provenance discrepancy diagnosis
is not a computational, biological or clinical validation result.

## Identity discrepancy: explained, not equated

The [machine-readable identity chain](receipts/ascent-identity.json) ties
independent primary sources together:

1. DataCite DOI `10.26275/0JZ3-ZRLO` resolves to ASCENT Guided Mode Demo,
   Pennsieve/SPARC dataset 364/version 1, published 2023-12-28, GNU GPL v3.0.
2. Its version-addressed, hash-and-size-verified `files/template.json` names
   `7bb84d3a-24b2-11ee-a4be-02420a0bc195`. The authenticated workbook independently
   gives this URL in sheet1 cell H26, and ASCENT 1.2.1 in D12.
3. Dataset **365/version 1**, DOI `10.26275/3d2g-d3xd`, is **ASCENT Tutorial**.
   Its independently retrieved and verified template names
   `1f1f0efc-f94b-11ed-a0b9-02420a0b0ee6`, the previous lock value.
4. [ASCENT documentation at commit 20faf73](https://github.com/wmglab-duke/ascent/blob/20faf73c7e3e743909ad98db4438a01dd5743389/docs/source/Running_ASCENT/osparc.md)
   assigns the two UUIDs to Guided Mode and Full Implementation/Tutorial
   respectively. Commit `2d708dc` introduced both links on 2023-07-26;
   `20faf73` corrected Markdown syntax on July 28, before dataset publication.
5. The [SPARC citation guide](https://docs.sparc.science/docs/instructions-for-sparc-investigators-to-cite-their-datasets-in-manuscripts-1)
   labels the Tutorial UUID as Guided Mode. This explains the earlier lock error.
   The guide was readable through web search/open; scripted retrieval returned
   403. The two authenticated deposits and immutable ASCENT documentation are
   the identity anchors, independently of that guide.

**Resolution: DISTINCT_STUDIES; equivalence: INCOMPARABLE.** There is no evidence
of migration, an alias, or interchangeable revisions. The lock now uses the
Guided Mode UUID and retains `previous_osparc_study`, its disposition and the
identity-chain reference. No similar-name inference is used. The Portal version
listing exposes one dataset version (1); revision 1 metadata was also inspected.
No historical study export or authenticated server lineage was available.

## Manifest discrepancy: UPSTREAM_METADATA_DEFECT

[Raw measurements and retrieval receipts](receipts/ascent-manifest-investigation.json)
identify `364/manifest.json`, S3 version `k2bHkhvv_na3EZpeGWrWuN4UhimBiQVI`.
The file-list API declares **4,110 bytes** and SHA-256
`87033bc65df85fe5caf78688993a77f4a0842d3d2c320fa84126a990166396cb`.

Two separate version-addressed GETs and a current-object GET returned exactly
**5,318 identical bytes**, that same digest and that same version ID. HTTP
Content-Length and the manifest's own file entry both say 5,318. Requests used
`Accept-Encoding: identity`; responses contain no Content-Encoding. Measurements:

| Representation diagnostic | Size |
|---|---:|
| Raw UTF-8, no BOM | 5,318 bytes |
| Unicode character count | 5,314 characters |
| LF normalized (already LF) | 5,318 bytes |
| CRLF normalized | 5,477 bytes |
| Compact JSON diagnostic | 3,511 bytes |
| gzip diagnostic | 1,760 bytes |

None explains 4,110. No decoding or normalization was used for the digest.
The current object matches the version selected by upstream metadata, excluding
a local version-selection error. Object Last-Modified is 2026-01-07, after the
2023 publication, so regenerated metadata/stale size is plausible; the publisher's
internal regeneration history was not established. **UPSTREAM_METADATA_DEFECT**
describes the observed contradictory API/object metadata, not publisher admission
of a specific software bug. The original combined file verification remains
**FAILED**; hash agreement does not waive the size requirement.

## Reference search and runtime boundaries

The [reference search receipt](receipts/ascent-reference-search.json) records the
complete recursively enumerated public inventory: 13 objects, including all
three workbooks, template, CSV metadata, root/revision manifests and READMEs.
Every file was downloaded by immutable S3 version and checked. Workbooks were
read as bounded ZIP/XML values, including the distinction between example/help
columns and actual values; no macros or formulas were executed. The dataset
manifest lists only `template.json` as the computational payload. There are no
result/log/notebook/HOC/potential/output directories in the deposit. README and
workbook identify **ASCENT 1.2.1** but contain no numerical reference result.

Primary ASCENT source tag 1.2.1 resolves to
`1360b77920c5759a66815b6b3db29efa7f78f950`. Its o²S²PARC templates and HOC files
were inspected, not executed. The path is NEURON HOC/MOD, not a substituted
modern PyFibers implementation. The generic threshold writer uses extracellular
amplitude in **mA** (`%f` formatting). This establishes a source convention, not
an authenticated study-specific output or expected value.

The template uses `MRG_INTERPOLATION`, selectable Rat/Human cuff configurations,
`osparc` placeholders and pre-solved/supersampled potentials. Its
`PERCENT_DIFFERENCE: 1` is a threshold-search stopping rule. It does **not** define
allowable reproduction error, prove solver precision, or establish which settings
were selected in the published run. No 1% tolerance was adopted.

Guided Mode specifically uses **pre-solved FEM potentials**. The earlier blanket
COMSOL execution blocker was too broad and is corrected: a genuine Guided Mode
reproduction might require only the authenticated potentials plus the exact
NEURON service. COMSOL 5.4+ and NEURON 7.6.7+ in the generic installation guide
are minimum requirements, not the versions used for this publication. Exact
NEURON version, FEM-generating COMSOL version, service image digest, selected
parameters, morphology/electrode/potential bytes and reference output remain
unknown. A current simcore test fixture for an ASCENT service was inspected as
another lead; it cannot authenticate a published study's runtime or inputs.

Official unauthenticated `GET /v0/projects/{uuid}` returned **401** for both
studies. No credentials were inspected. No connected browser automation surface
was available; native Safari was available but concurrent user activity
interrupted navigation. Thus an authorized o²S²PARC session was **not established**,
not proven nonexistent. Current ARM64 host checks found no `comsol`, `nrniv`,
`nrnivmodl` on PATH, no named COMSOL/NEURON application in `/Applications`, and no
importable NEURON in Python 3.14.7. Exact local compatibility is NOT TESTED.

## Decision and reproducible investigation

[The non-executable gate](manifests/ascent-comparison-gate.json) retains null
reference value/digest, units, comparison method and tolerances. It is **not**
`ascent-reproduction-contract.json`; there is no contract commit SHA to report.
Missing reference evidence alone prohibits candidate execution, even if local
software or account access later becomes available.

Required next evidence: an authorized export of the **Guided Mode** study with
exact service/image versions, selected inputs, nerve/electrode/stimulation
configuration, pre-solved potentials and generating provenance, and the published
machine-readable reference output with units. Then choose a defensible comparison
method and commit its full contract **before** any candidate result exists.

```sh
python3 -m experiments.sparc.audit_ascent --output /tmp/openbody-ascent-audit
```

This is read-only retrieval/measurement; raw bytes remain outside Git. The
historical claims are preserved in compact receipts. A later retrieval must be
compared to them; changed upstream bytes must not be silently accepted as the
same artifact. Authentication alone never binds species, stimulation modality,
physiological engagement or clinical benefit. No transfer to auricular VNS,
Cymba qualification, patient data, Twin writes, control or dosing is introduced.

## Follow-up boundary

The public-deposit investigation is complete for PR #23. [Issue #25](https://github.com/advatar/OpenBody/issues/25)
owns the external reproduction bundle. Obtain it, commit a defensible contract,
then execute and compare; model/context qualification remains a separate gate.
No ASCENT execution or tolerance selection is authorized by this report.
