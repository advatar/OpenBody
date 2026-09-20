# ASCENT reproduction checkpoint — 2026-09-20

**BLOCKED. No ASCENT candidate simulation was executed.**
The numerical gate remains OPEN; there is no numerical PASS or validation claim.

## Authenticated deposit

Independent [DataCite DOI metadata](https://api.datacite.org/dois/10.26275/0JZ3-ZRLO)
and [Pennsieve version metadata](https://api.pennsieve.io/discover/datasets/364/versions/1)
identify **ASCENT Guided Mode Demo**, dataset **364**, version **1**, published
**2023-12-28**. The deposit is licensed **GNU GPL v3.0**. Authors: Daniel P.
Marshall, Princess Tara Zamani, Eric D. Musselman, Warren M. Grill, Nicole A.
Pelot, Katie Zhuang, and Elisabetta Iavarone. Metadata snapshots and the complete
13-file recursive listing are in `manifests/ascent-*.json`.

Twelve files pass both upstream SHA-256 and size checks, including all four files
under `files/`. The remaining root `manifest.json` has a matching digest but
**FAILED** size verification: API 4,110 bytes; observed 5,318. This is not silently
normalized. No file is executed. All source bytes remain outside Git; receipts
include immutable S3 object versions and hex-decoded upstream SHA-256 values.

The authenticated `files/template.json` is 251 bytes, SHA-256
`0263efbabffc1027f49349082ab63137a7e4ae4f1b8b42e1b28b5505104beb0f`.
It identifies study **`7bb84d3a-24b2-11ee-a4be-02420a0bc195`**, which is
**INCOMPARABLE** with locked study **`1f1f0efc-f94b-11ed-a0b9-02420a0b0ee6`**.
No relationship/version equivalence between these studies has been established.
The existing lock is retained so this discrepancy cannot disappear silently.

The revised deposit README identifies **ASCENT 1.2.1** and describes modeled
activation threshold. It explicitly describes a configuration-only deposit.
The template has a UUID, name and description; it does not contain full model
inputs, electrode configuration, reference outputs or solver versions.
No numerical output artifact, precise threshold definition, unit or expected
value could be authenticated from these files.

## Predeclared gate and environment

[ascent-comparison-gate.json](manifests/ascent-comparison-gate.json) records,
**before any candidate run**, null reference output/units/tolerances and a closed
execution gate. No arbitrary tolerance is selected. Even exact-output comparison
requires a reference output that is currently absent. A future run requires a
new committed manifest with authenticated output identity, exact metric/unit,
method and scientifically justified tolerances (or justified exact comparison).

[ASCENT 1.2.1 installation documentation](https://github.com/wmglab-duke/ascent/blob/v1.2.1/docs/source/Getting_Started.md)
specifies COMSOL 5.4 or newer (purchased license), NEURON 7.6.7 or newer (with a
compatibility caveat for newer versions), and Java 8 or Java 11 for COMSOL 6+.
These are **documented requirements**, not authenticated versions used by this
deposited run. Exact NEURON/COMSOL versions remain **NOT TESTED/unknown**.

Local checks: ARM64 macOS, Python 3.14.7; no `comsol` or `nrniv` executable on
PATH, no named COMSOL/NEURON application under the bounded `/Applications` check,
and no importable `neuron` in the checked Python environment. The host Java is
21.0.9. Docker runs ARM64 and can emulate AMD64, as demonstrated for SCKAN; that
does not establish ASCENT compatibility. No commercial license was accessed or
bypassed. Browser tooling reports no available browser, so an existing authorized
o²S²PARC session could not be used. An exploratory public-study API request
returned 404; this is not evidence about the user's account permissions.

Next requirements: resolve study identity with the publisher; obtain the exact
study export including service versions, model inputs and published output;
resolve the manifest metadata discrepancy; secure an already authorized official
o²S²PARC execution session or compatible licensed local environment; commit a
comparison criterion; then execute the pinned candidate and comparator.

Required identity/context includes anatomy, electrode geometry, stimulation
parameters, species, sex/sample/population where relevant, modality and exact
model/input/runtime artifacts. No substitution of simulator or silent transfer
between implanted cervical/abdominal/branch VNS, transcutaneous cervical VNS,
auricular VNS or other peripheral stimulation is permitted.

Possible operational outcomes remain PASS, FAIL, BLOCKED and INCOMPARABLE.
A future PASS would mean only the pinned computational result meets the
predeclared criterion. Numerical reproduction is separate from anatomical,
functional, electrical recruitment, physiological and clinical evidence. It does
not qualify OpenBody generally, Cymba, or consumer auricular stimulation.

To repeat public deposit retrieval (nonzero exit is expected for the recorded
metadata size mismatch):

```sh
python3 -m experiments.sparc.authenticate_ascent --cache /tmp/openbody-sparc-cache
```
