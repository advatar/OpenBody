"""Inventory the JSON Schema vocabulary a schema actually uses.

Native consumers (for example InVivo's fail-closed Swift validator for the
admitted-observation profile) implement a bounded keyword subset. This
inventory lets a contract state exactly which keywords, formats and reference
kinds a consumer must support, and lets tests notice when that set changes.
"""

from __future__ import annotations

from typing import Any

_SCHEMA_MAPS = ("properties", "$defs", "patternProperties", "dependentSchemas")
_SCHEMA_LISTS = ("allOf", "anyOf", "oneOf", "prefixItems")
_SCHEMA_SINGLE = ("not", "if", "then", "else", "items", "contains", "additionalProperties", "propertyNames")


def schema_vocabulary(schema: Any) -> dict[str, list[str]]:
    """Return sorted ``keywords``, ``formats`` and ``refs`` ("local" / "external")."""

    keywords: set[str] = set()
    formats: set[str] = set()
    refs: set[str] = set()

    def walk(node: Any) -> None:
        if not isinstance(node, dict):
            return
        keywords.update(node)
        if isinstance(node.get("format"), str):
            formats.add(node["format"])
        if isinstance(node.get("$ref"), str):
            refs.add("local" if node["$ref"].startswith("#") else "external")
        for key in _SCHEMA_MAPS:
            for child in (node.get(key) or {}).values():
                walk(child)
        for key in _SCHEMA_LISTS:
            for child in node.get(key) or []:
                walk(child)
        for key in _SCHEMA_SINGLE:
            walk(node.get(key))

    walk(schema)
    return {"keywords": sorted(keywords), "formats": sorted(formats), "refs": sorted(refs)}
