# SCKAN reproduction checkpoint — 2026-09-20

**VERIFIED:** `SciCrunch/NIF-Ontology`, tag `sckan-2026-06-23`, explicitly
**prerelease**, published `2026-06-23T14:59:10Z`. Independent GitHub release API
metadata matches both locked asset names, sizes and upstream SHA-256 digests.
Both downloaded archives match those digests locally. See
[artifact receipts](receipts/sckan-artifacts.json) and
[upstream metadata](manifests/sckan-release.json). No large artifacts are in Git.

| Asset | Bytes | Upstream and observed SHA-256 |
|---|---:|---|
| release-2026-06-23T135208Z-sckan.zip | 159258100 | `3473cc9cf4eaf1fb4b22dc72569cc7431eacf0da70d0460938414b133da37945` |
| sparc-sckan-graph-20260623T070119.zip | 496886143 | `d6cf12f5a1daada792c6329771d9cd1160e15df5072b6d3657b791cb438b64f7` |

The release ZIP was inspected and extracted with `authenticate.safe_extract`:
35 entries, 1,083,776,098 uncompressed bytes. Limits are 100,000 entries,
8 GiB total and 1,000:1 per-entry expansion. Absolute/traversing paths,
backslashes, colon paths, duplicates, symlinks and special entries are rejected.
Extraction requires a fresh private directory. The graph ZIP was verified but
not extracted or executed: this gate uses the release's native Blazegraph journal.

**VERIFIED execution binding:** extracted journal SHA-256
`841289a3eff9d1339a094aa93741cbd73e42c4d830817e466183bc0eb0e46096`.
A private copy was mounted into upstream `tgbugs/musl:blazegraph`, pinned as
`tgbugs/musl@sha256:0eca49ed3b0e0cb93145710ad7d587dc49868df16f63747559abaac5bda20897`.
The engine reports Blazegraph `2.1.6-SNAPSHOT`, commit
`6b0c935523f5064b80279b30a5175a858cddd2a1`, OpenJDK `25.0.3`.
Execution used Linux AMD64 emulation on an ARM64 macOS host, Docker ARM64 engine,
2 CPUs/4 GiB container limits, and a loopback-only endpoint. No public mutable
endpoint, unpinned latest data, or locally invented Simple SCKAN transformation
was used. Queries are SELECT-only. The runner verifies the ZIP member, extracted
journal, inspected container mount/image/port and engine version, and checks
journal bytes again after execution.

## Query scope and semantics

[Exact queries](../queries/) and [compact receipts and selected typed facts](receipts/sckan-queries.json)
record language, engine, release, times, duration, row counts and result hashes. Full typed result dumps are external, not vendored.
`upstream-apinatomy.rq` is the native OWL example from
[SciCrunch/sparc-curation](https://github.com/SciCrunch/sparc-curation/blob/54a4c7ed112bc60387e46bb61287d2092239b5c5/docs/simple-sckan/readme.md),
with only surrounding code-fence whitespace removed. The upstream MIT notice is
included in `queries/LICENSE.upstream`. It retains the published LIMIT 999; 516
rows is below that bound. This is execution on the new pinned release, **not** a
claim to reproduce historical result counts from a different release.

The other queries are explicitly OpenBody-authored bounded native queries,
following the documented OWL representation, rather than verbatim upstream
competency queries:

- `keast-5`: explicit Keast bladder population 5 restrictions, including the
  pelvic splanchnic nerve (`UBERON:0018675`), native species and annotations.
- `keast-5-rat`: the same query constrained to `NCBITaxon:10116`.
- `bladder-target`: exact asserted `hasOrganTarget` to `UBERON:0001556`.
- `missing-population`: deliberately unsupported URN; zero rows means UNKNOWN.

This provides a bounded example of connectivity used in whole-body maps; it
neither reconstructs nor reproduces the SPARC review's entire map demonstration.
The Keast restriction query preserves `owl:onProperty`, `owl:someValuesFrom`
and nested filler predicates in separate columns. The table is **not** a set of
asserted neuron-to-anatomy triples. `partOf` remains existential part-of; it does
not imply precise localization. RDF list traversal is structural parsing, not
transitive neural connectivity. The original upstream query joins soma and
terminal restrictions; its paired rows do not establish signal direction.

The 72 Keast rows are joined restriction/annotation rows, **not 72 neurons or
connections**. Native metadata includes literature citations, expert consultant
ORCID, Composer statement and ApiNATOMY annotation identifiers. Those classes
remain separate. Rat context is preserved. No sex value is invented when absent.
Complex nested fillers not supported by this bounded projection remain in the
digest-addressed upstream artifact; the adapter explicitly reports this
limitation and does not claim a lossless complete ontology export.

**NOT REPRODUCED:** the newer Simple SCKAN CQ2 vagus query returned zero rows in
this native journal. The query repository has no detected redistribution license,
so its code/results are not vendored; the diagnostic receipt records its immutable
source and hashes. No Simple SCKAN transform was improvised. Broader published
competency-query reproduction remains an open gate.

## Canonicalization and reuse

SPARQL JSON variables are sorted. Every complete typed binding dictionary is
retained (including datatype/language), rows are sorted by their compact,
key-sorted UTF-8 JSON serialization, and duplicates are retained. The canonical
object uses `ensure_ascii=False`, separators `(',', ':')`, no terminal newline,
and rejects NaN. SHA-256 covers those bytes. Blank-node-valued projected bindings
are rejected because execution-local labels are not stable identifiers. Empty
bindings remain UNKNOWN. No inverse/transitive edges or signal-flow facts are
added. The second execution checks digest stability; its receipt remains distinct
from the first execution.

SCKAN ontology attribution: SciCrunch/NIF-Ontology and its contributors,
[pinned source and CC BY 4.0 notice](https://github.com/SciCrunch/NIF-Ontology/tree/sckan-2026-06-23).
Derived typed result excerpts are redistributed with this attribution and
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Query metadata does not
upgrade the scientific evidence class. Imported ontology terms retain native IRIs.

## Repeat locally

From the repository root (Python standard library plus Docker):

```sh
python3 -m experiments.sparc.authenticate --cache /tmp/openbody-sparc-cache --evidence /tmp/openbody-sckan-authentication
```

Extract only after authentication succeeds (the target must not exist):

```sh
python3 - <<'PYTHON'
from pathlib import Path
from experiments.sparc.authenticate import safe_extract, verify
import json, shutil
cache = Path('/tmp/openbody-sparc-cache')
lock = json.loads(Path('experiments/sparc/upstream-lock.json').read_text())['sckan']
archive = cache / lock['artifact']
verify(archive, lock['sha256'], lock['size_bytes'])
print(safe_extract(archive, cache / 'release'))
data = cache / 'release' / lock['artifact'][:-4] / 'data'
run = cache / 'blazegraph-run'
run.mkdir(exist_ok=False)
for name in ('blazegraph.jnl', 'prefixes.conf'):
    shutil.copyfile(data / name, run / name)
PYTHON
```

For another invocation, reuse the already verified cache/journal rather than
extracting over an existing directory. Start the official service with the exact
image above (only a disposable journal copy is writable):

```sh
docker run --detach --name openbody-sparc-reproduction --platform linux/amd64 \
  --memory 4g --cpus 2 -p 127.0.0.1:19999:9999 \
  -v /tmp/openbody-sparc-cache/blazegraph-run:/var/lib/blazegraph \
  tgbugs/musl@sha256:0eca49ed3b0e0cb93145710ad7d587dc49868df16f63747559abaac5bda20897
python3 -m experiments.sparc.reproduce_sckan --cache /tmp/openbody-sparc-cache --output /tmp/openbody-sckan-results
docker stop openbody-sparc-reproduction
```

[Upstream service mechanism](https://github.com/tgbugs/dockerfiles/blob/master/source.org#blazegraph)
uses the same journal mount and Blazegraph SPARQL interface. Reproduction is
manual; synthetic CI never downloads these artifacts or starts a database.

## Observed canonical results

| Query | Rows | SHA-256 |
|---|---:|---|
| `bladder-target` | 10 | `0854a10d2e74156f8ed50c305433a1f10732837105ff72e77e739359533edac4` |
| `keast-5-rat` | 72 | `97e6ebc4dda328816b395e2c52b7672cd1c5a6aa52a5bd7dff4bcf9e807e5b1c` |
| `keast-5` | 72 | `97e6ebc4dda328816b395e2c52b7672cd1c5a6aa52a5bd7dff4bcf9e807e5b1c` |
| `missing-population` | 0 | `17f1e24a64a61eaeb837f3c2549a4451ba81f91858d875fb1a9c1a47554fbb10` |
| `upstream-apinatomy` | 516 | `278bf46e3ba3afc4ab54c8bb6131e984e38e9cf2a18bc216cf714da0bd8d2ad9` |

## Compact evidence policy

The frozen queries, source/engine identities, row counts and result digests are
unchanged. Each receipt retains at most two typed regression rows plus both
execution timestamps/durations/digests. These samples cannot establish the full
result hash on their own. Reconstruction and verification are explicit:

```sh
python3 -m experiments.sparc.evidence_tools --results /tmp/openbody-sckan-results/sckan-queries.json
```

That verifier checks every full canonical result, including unselected rows,
query bytes, count, species summary, metadata predicates and source/engine
bindings against the frozen compact receipts. Both original full runs passed it
before removal from the branch tip. No SCKAN query was added or rerun for cleanup.
The original generated receipts remain recoverable from Git commit
`90d3d3c3412ecebc87ecef5f858fee4b407e1957`; they are not required for a fresh rerun.
The native runner now writes only to external output, verifies the mounted
journal at completion, and fails if output differs from the frozen result.
Offline CI tests exercise this verifier with tampered unselected rows; they do
not pretend a summary alone independently verifies upstream execution.
