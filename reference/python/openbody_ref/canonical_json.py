"""OpenBody canonical JSON digest, version 1 (``openbody.canonical-digest/1``).

This module implements ``docs/CANONICAL_DIGEST_V1.md``. It is written from that
specification, not by delegating to ``json.dumps``. For every value in the
defined domain it produces the same bytes as the pinned v1 algorithm
(``json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)``).
The tests check this equivalence. Values outside the domain are refused with a
stable :class:`CanonicalDomainError` code, never serialized. The domain excludes
non-finite numbers, integers beyond +/-(2**53 - 1), lone surrogates, duplicate
object keys and non-string keys.

Cross-language vectors: ``fixtures/whole-person-state/v1/canonical-digest-vectors.json``.
Changing any rule here needs a new algorithm identifier and a migration.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any

ALGORITHM = "openbody.canonical-digest/1"
MAX_SAFE_INTEGER = 2**53 - 1

_SHORT_ESCAPES = {
    '"': '\\"',
    "\\": "\\\\",
    "\b": "\\b",
    "\f": "\\f",
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
}


_SURROGATE = re.compile("[\ud800-\udfff]")
_ESCAPE = re.compile('[\x00-\x1f"\\\\]')


def _escape(match: re.Match[str]) -> str:
    char = match.group()
    return _SHORT_ESCAPES.get(char) or f"\\u{ord(char):04x}"


class CanonicalDomainError(ValueError):
    """A value or wire text that is outside the canonical-digest v1 domain."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _fail(code: str, message: str) -> None:
    raise CanonicalDomainError(code, message)


# ---------------------------------------------------------------------------
# Wire parsing (spec section "Parsing")
# ---------------------------------------------------------------------------


def _object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("duplicate_key", f"Duplicate object key {key!r}")
        result[key] = value
    return result


def _parse_float(token: str) -> float:
    value = float(token)
    if not math.isfinite(value):
        _fail("non_finite_number", f"Number {token} overflows binary64")
    return value


def _parse_int(token: str) -> int:
    value = int(token)
    if abs(value) > MAX_SAFE_INTEGER:
        _fail("integer_out_of_range", f"Integer {token} is outside +/-(2**53 - 1)")
    return value


def _parse_constant(token: str) -> Any:
    _fail("non_finite_number", f"{token} is not a JSON number")


def parse(wire: str | bytes) -> Any:
    """Parse RFC 8259 JSON text into the canonical data model, failing closed."""

    if isinstance(wire, (bytes, bytearray)):
        if bytes(wire[:3]) == b"\xef\xbb\xbf":
            _fail("byte_order_mark", "A byte order mark is not allowed")
        try:
            wire = bytes(wire).decode("utf-8", errors="strict")
        except UnicodeDecodeError as error:
            _fail("invalid_utf8", f"Wire bytes are not UTF-8: {error}")
    if wire.startswith("﻿"):
        _fail("byte_order_mark", "A byte order mark is not allowed")
    try:
        value = json.loads(
            wire,
            object_pairs_hook=_object_pairs,
            parse_float=_parse_float,
            parse_int=_parse_int,
            parse_constant=_parse_constant,
        )
    except CanonicalDomainError:
        raise
    except ValueError as error:
        _fail("invalid_json", f"Not RFC 8259 JSON text: {error}")
    _check_domain(value)
    return value


def _check_domain(value: Any) -> None:
    canonical_text(value)


# ---------------------------------------------------------------------------
# Serialization (spec section "Serialization")
# ---------------------------------------------------------------------------


def format_double(value: float) -> str:
    """Shortest round-trip decimal form of a finite binary64 (spec "Numbers").

    Digits are the fewest significant decimal digits that parse back to the
    same binary64; among those, the correctly rounded (nearest) one. With
    ``x`` the decimal exponent of the first digit, fixed notation is used when
    ``-4 <= x < 16`` (always with a fraction, so ``37.0``), otherwise
    ``d[.ddd]e(+|-)XX`` with at least two exponent digits.
    """

    if not math.isfinite(value):
        _fail("non_finite_number", "Non-finite numbers are outside the domain")
    if value == 0.0:
        return "-0.0" if math.copysign(1.0, value) < 0 else "0.0"
    sign = "-" if value < 0 else ""
    magnitude = abs(value)
    for precision in range(17):
        text = f"{magnitude:.{precision}e}"
        if float(text) == magnitude:
            break
    mantissa, exponent_text = text.split("e")
    digits = mantissa.replace(".", "").rstrip("0") or "0"
    exponent = int(exponent_text)
    if -4 <= exponent < 16:
        if exponent < 0:
            body = "0." + "0" * (-exponent - 1) + digits
        elif len(digits) <= exponent + 1:
            body = digits + "0" * (exponent + 1 - len(digits)) + ".0"
        else:
            body = digits[: exponent + 1] + "." + digits[exponent + 1 :]
        return sign + body
    fraction = "." + digits[1:] if len(digits) > 1 else ""
    return f"{sign}{digits[0]}{fraction}e{'-' if exponent < 0 else '+'}{abs(exponent):02d}"


def _string(value: str) -> str:
    """Quote a string: '"' and '\\' escaped, the five short control escapes, other
    U+0000..U+001F as lowercase \\u00xx, everything else (including '/') raw."""

    if _SURROGATE.search(value):
        _fail("lone_surrogate", "Strings must be sequences of Unicode scalar values")
    return '"' + _ESCAPE.sub(_escape, value) + '"'


def canonical_text(value: Any) -> str:
    """Canonical text of a value in the data model (null, bool, int, float, str, list, dict)."""

    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        if abs(value) > MAX_SAFE_INTEGER:
            _fail("integer_out_of_range", f"Integer {value} is outside +/-(2**53 - 1)")
        return str(value)
    if isinstance(value, float):
        return format_double(value)
    if isinstance(value, str):
        return _string(value)
    if isinstance(value, list):
        return "[" + ",".join(canonical_text(item) for item in value) + "]"
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            _fail("non_string_key", "Object keys must be strings")
        # Python orders str by Unicode code point, which is what the spec requires
        # (not UTF-16 code units and not locale collation).
        keys = sorted(value)
        return "{" + ",".join(_string(key) + ":" + canonical_text(value[key]) for key in keys) + "}"
    _fail("unsupported_type", f"{type(value).__name__} is not a JSON value")
    return ""  # pragma: no cover


def canonical_bytes(value: Any) -> bytes:
    return canonical_text(value).encode("utf-8")


def digest(value: Any) -> str:
    """``sha256:`` + lowercase hex SHA-256 of the canonical UTF-8 bytes."""

    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def digest_wire(wire: str | bytes) -> str:
    """Parse wire JSON text strictly, then digest it."""

    return digest(parse(wire))
