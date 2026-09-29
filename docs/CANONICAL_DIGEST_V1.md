# OpenBody canonical JSON digest, version 1

Algorithm identifier: `openbody.canonical-digest/1`

Status: normative for the whole-person contract v1
(`openbody.whole-person-observation/1.0`, `openbody.whole-person-state/1.0`,
`openbody.whole-person-consumer-mapping/1.0`). The corrected v1 baseline pins
this file by SHA-256 in
[`fixtures/whole-person-state/v1/frozen-manifest.json`](../fixtures/whole-person-state/v1/frozen-manifest.json).

Vectors: [`fixtures/whole-person-state/v1/canonical-digest-vectors.json`](../fixtures/whole-person-state/v1/canonical-digest-vectors.json).
Python, Swift, Kotlin and Rust implementations must reproduce every positive
vector byte for byte, and must refuse every negative vector with the listed
error class.

Reference implementation: [`reference/python/openbody_ref/canonical_json.py`](../reference/python/openbody_ref/canonical_json.py)
(written from this document, and tested to equal the historical Python
`json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`
over the whole domain below).

This algorithm is **not** RFC 8785 (JCS). Objects are ordered by code point,
not by UTF-16 code unit. Numbers keep the integer/float distinction of the wire
token, and floats use the shortest round-trip form with the thresholds given
below, not ECMAScript `Number.prototype.toString`.

The key words MUST, MUST NOT and SHOULD are used as in RFC 2119.

## 1. Where it is used

In v1 the following values are digests under this algorithm:
`envelope_digest`, `derivation.parents[].envelope_digest`,
`clinical_link.content_digest`, `snapshot_digest`,
`contract.observation_schema_digest`, `contract.value_sets_digest`, and the
consumer-mapping `record_digest` values of InVivo and TwinSuite records. It does
not apply to the ProvidEHR `record_digest`, which is the SHA-256 of the source
bytes as fetched (`sha256:<source_sha256>`).

## 2. Data model

A value is exactly one of:

| Kind | Domain |
|---|---|
| null | `null` |
| boolean | `true`, `false` |
| integer | a mathematical integer `n` with `-(2^53 - 1) <= n <= 2^53 - 1` |
| float | a finite IEEE 754 binary64 value, including `-0.0` |
| string | a sequence of Unicode scalar values (U+0000..U+D7FF, U+E000..U+10FFFF) |
| array | an ordered sequence of values |
| object | a set of (key, value) members; keys are strings and are unique |

Integer and float are **different kinds**: integer `37` and float `37.0` have
different canonical forms and different digests.

A value outside this domain MUST be refused, never serialized. This covers
NaN, infinities, out-of-range integers, lone surrogates, duplicate keys,
non-string keys and any other type.

## 3. Parsing wire JSON

When the input is JSON text, an implementation MUST parse it as follows.
Parsing is the most common source of cross-language divergence.

1. The input is UTF-8 bytes of an RFC 8259 JSON text. A byte order mark is
   refused (`byte_order_mark`). Invalid UTF-8 is refused (`invalid_utf8`). Any
   other syntax error, including trailing commas, leading zeros, single quotes
   or raw U+0000..U+001F inside strings, is refused (`invalid_json`).
   Insignificant whitespace is ignored. A top-level scalar is allowed.
2. **Number kind comes from the token.** A number token that contains `.`,
   `e` or `E` is a float. Any other number token is an integer.
   - A float token is converted to the nearest binary64, with ties to even (the
     IEEE 754 default, as in `strtod`). A result that overflows to an infinity
     is refused (`non_finite_number`). A result that underflows is the rounded
     value, possibly `0.0` or `-0.0`, and is not an error.
   - An integer token is its exact mathematical value. A value outside
     `+-(2^53 - 1)` is refused (`integer_out_of_range`). `-0` is the integer
     `0`.
   - The tokens `NaN`, `Infinity` and `-Infinity` are refused
     (`non_finite_number`).
3. **Strings.** Escapes are decoded. A `\uD800`..`\uDBFF` escape that is
   immediately followed by a `\uDC00`..`\uDFFF` escape is one scalar value. Any
   other surrogate escape is refused (`lone_surrogate`). This applies to object
   keys too.
4. **Objects.** Two members with the same key, compared as scalar-value
   sequences without normalization, are refused (`duplicate_key`). Members are
   never merged and the last one does not win.

Implementations that digest an in-memory value, rather than wire text, MUST
hold the value in this data model. In particular, they MUST keep integers and
floats distinct. A platform number type that loses the distinction (for
example `NSNumber` from `JSONSerialization`, or a JavaScript `number`) cannot
be used as the source for the canonical form.

## 4. Serialization

The canonical text is produced recursively. It contains no whitespace.

- **null / booleans:** `null`, `true`, `false`.
- **Integer:** the decimal digits with no leading zeros, preceded by `-` if
  negative. `0` for zero.
- **Float:** see section 5.
- **String:** `"` followed by each scalar value in order, then `"`. Each scalar value is written as:
  - `"` as `\"`, and `\` as `\\`;
  - U+0008 as `\b`, U+000C as `\f`, U+000A as `\n`, U+000D as `\r`, and U+0009 as `\t`;
  - any other U+0000..U+001F as `\u00` followed by two **lowercase** hex digits
    (for example, U+001B is `\u001b`);
  - every other scalar value (including `/`, U+007F, non-ASCII characters,
    U+2028/U+2029 and astral characters) as itself, unescaped.

  No Unicode normalization is applied.
- **Array:** `[`, the canonical elements in their original order separated by
  `,`, then `]`.
- **Object:** `{`, then the members sorted by key, each written as the canonical
  key string, `:` and the canonical value, separated by `,`, then `}`. Keys are
  compared as sequences of **Unicode scalar values by numeric code point**,
  lexicographically, with a proper prefix sorting first. This is neither
  UTF-16 code-unit order nor locale collation: `"￿"` sorts before
  `"\u{1F600}"`. Swift `String <`, Java/Kotlin `String.compareTo` and
  JavaScript `<` do not implement this order for all inputs.

## 5. Float formatting

Let `v` be a finite binary64.

1. If `v` is `+0.0`, the result is `0.0`. If `v` is `-0.0`, the result is `-0.0`.
2. Otherwise, let `s` be `-` if `v < 0`, else empty, and let `m = |v|`.
3. **Digits.** Let `P` be the smallest integer `1 <= P <= 17` such that
   rounding `m` correctly (round-half-even on the exact binary value) to `P`
   significant decimal digits gives a decimal that converts back to exactly `m`.
   Let `d` be those `P` digits with trailing zeros removed (at least one digit
   remains), and let `x` be the decimal exponent of the first digit, so that
   `m ~ d1.d2d3... x 10^x`. This gives the same digits as the "shortest
   round-trip" algorithms (Ryu, Grisu with fallback, `dtoa` mode 0) when they
   pick the digit string nearest to `m`.
4. **Fixed notation** when `-4 <= x < 16`:
   - `x < 0`: `0.` followed by `-x - 1` zeros, then `d`;
   - `x >= 0` and `len(d) <= x + 1`: `d`, then `x + 1 - len(d)` zeros, then `.0`;
   - otherwise: the first `x + 1` digits of `d`, then `.`, then the rest of `d`.
5. **Exponential notation** otherwise: `d1`, then `.` and `d2...` if
   `len(d) > 1`, then `e`, then `+` or `-`, then `|x|` in decimal with at
   least two digits.
6. The result is `s` followed by the fixed or exponential form.

Examples: `37.0`, `5.6`, `0.1`, `0.0001`, `1e-05`, `1e-07`,
`1000000000000000.0`, `1e+16`, `1.2345678901234568e+29`, `5e-324`,
`1.7976931348623157e+308`, `9007199254740992.0`, `-0.0`.

## 6. Digest

`digest(v) = "sha256:" + lowercase_hex(SHA-256(UTF-8(canonical_text(v))))`.

## 7. Conformance

An implementation conforms to `openbody.canonical-digest/1` when:

1. for every entry of `positive` in the vectors file, parsing `wire` and
   serializing gives exactly `canonical` (the bytes are `canonical_utf8_hex`)
   and the digest equals `digest`;
2. for every entry of `negative`, parsing `wire` (or the bytes `wire_hex`) is
   refused with the listed error class. Implementations may use their own error
   types, but they must map one-to-one onto these class names in their tests;
3. every entry of `corpus` (a repository file plus an RFC 6901 pointer)
   produces the listed digest.

## 8. Versioning

The v1 rules above are frozen. Any change to them, including the domain, the
number formatting or the key order, is a new algorithm (`openbody.canonical-digest/2`),
not an edit of this one. A new algorithm needs:

- a new identifier recorded next to every digest it produces (a new contract
  version);
- a migration that recomputes or dual-publishes digests for existing
  envelopes, derivation parents, clinical links and snapshots;
- a period in which verifiers accept both algorithms, but only when the
  identifier says which one applies.

A digest computed under one algorithm is never compared with a digest computed
under another.
