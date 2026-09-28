"""Bounded, content-free evidence for a provider's structured request errors."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

_FIELD = re.compile(r"[A-Za-z_][A-Za-z0-9_.\[\]-]{0,255}\Z")
_REASON = re.compile(r"[A-Z][A-Z0-9_]{0,119}\Z")
_DOMAIN = re.compile(r"[a-z0-9.-]{1,120}\Z")
_GENERIC_MESSAGES = frozenset({
    "Request contains an invalid argument.",
    "Invalid argument.",
    "The request is invalid.",
})


def _hash(value: Any) -> str:
    return hashlib.sha256(str(value).encode("utf-8", errors="replace")).hexdigest()


def safe_provider_message(value: Any) -> tuple[str | None, bool]:
    if not isinstance(value, str):
        return None, False
    return (value, False) if value in _GENERIC_MESSAGES else (None, True)


def structured_error_evidence(sources: list[tuple[str, Any]], *, unavailable: bool = False) -> dict[str, Any]:
    violations: list[dict[str, str]] = []
    reasons: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    excluded = 0
    truncated = False
    source_names: list[str] = []
    for source_name, value in sources:
        if not isinstance(value, dict):
            continue
        container = value.get("error", value)
        if not isinstance(container, dict):
            continue
        items = container.get("details")
        if not isinstance(items, list):
            continue
        source_names.append(source_name)
        for item in items:
            if not isinstance(item, dict):
                excluded += 1
                continue
            kind = str(item.get("@type") or item.get("type") or "")
            if kind.endswith("google.rpc.BadRequest"):
                fields = item.get("fieldViolations", item.get("field_violations", []))
                if not isinstance(fields, list):
                    excluded += 1
                    continue
                for field in fields:
                    if not isinstance(field, dict):
                        excluded += 1
                        continue
                    path = field.get("field")
                    if not isinstance(path, str) or not _FIELD.fullmatch(path):
                        excluded += 1
                        continue
                    key = ("field", path)
                    if key in seen:
                        continue
                    seen.add(key)
                    if len(violations) >= 16:
                        truncated = True
                        continue
                    entry = {"field": path}
                    description = field.get("description")
                    if description:
                        # Provider descriptions can quote a prompt, enum value or key.
                        entry["description_sha256"] = _hash(description)
                        excluded += 1
                    violations.append(entry)
            elif kind.endswith("google.rpc.ErrorInfo"):
                reason, domain = item.get("reason"), item.get("domain")
                if not isinstance(reason, str) or not _REASON.fullmatch(reason):
                    excluded += 1
                    continue
                safe_domain = domain if isinstance(domain, str) and _DOMAIN.fullmatch(domain) else None
                key = (reason, safe_domain or "")
                if key in seen:
                    continue
                seen.add(key)
                if len(reasons) >= 8:
                    truncated = True
                    continue
                reasons.append({"reason": reason, **({"domain": safe_domain} if safe_domain else {})})
            else:
                excluded += 1
    status = "present" if violations or reasons else "unavailable" if unavailable else "absent"
    if status == "absent" and excluded:
        status = "redacted"
    if truncated:
        status = "truncated"
    return {"provider_detail_status": status, "field_violations": violations,
            "error_reasons": reasons, "detail_sources": source_names,
            "diagnostic_excluded_count": excluded, "diagnostic_truncated": truncated}


_SCHEMA_KEYS = {"type", "properties", "required", "items", "enum", "format", "nullable",
                "minimum", "maximum", "minLength", "maxLength", "minItems", "maxItems",
                "pattern", "additionalProperties"}


def schema_evidence(schema: Any) -> dict[str, Any]:
    """Hash the exact ordered SDK schema; persist only a redacted structure."""
    if schema is None:
        return {"schema_status": "absent"}
    if not isinstance(schema, dict):
        return {"schema_status": "unavailable", "schema_type": type(schema).__name__[:80]}
    raw = json.dumps(schema, ensure_ascii=False, separators=(",", ":"), default=str)
    counts = {"properties": 0, "enum_values": 0, "array_constraints": 0, "max_depth": 0}
    excluded = [0]

    def clean(node: Any, depth: int = 0, key: str = "") -> Any:
        counts["max_depth"] = max(counts["max_depth"], depth)
        if depth > 32:
            excluded[0] += 1
            return {"omitted": "depth_limit"}
        if isinstance(node, dict):
            result = {}
            for name, value in node.items():
                if key == "properties":
                    counts["properties"] += 1
                    if not isinstance(name, str) or not _FIELD.fullmatch(name):
                        excluded[0] += 1
                        continue
                    result[name] = clean(value, depth + 1)
                elif name in _SCHEMA_KEYS:
                    result[name] = clean(value, depth + 1, name)
                else:
                    excluded[0] += 1
            return result
        if isinstance(node, list):
            if key == "enum":
                counts["enum_values"] += len(node)
                excluded[0] += len(node)
                return [{"sha256": _hash(value), "chars": len(str(value))} for value in node[:128]]
            if key == "required":
                return [item for item in node[:128] if isinstance(item, str) and _FIELD.fullmatch(item)]
            return [clean(item, depth + 1, key) for item in node[:128]]
        if key in {"minItems", "maxItems"}:
            counts["array_constraints"] += 1
        if isinstance(node, bool) or isinstance(node, (int, float)):
            return node
        if isinstance(node, str) and key in {"type", "format"} and _FIELD.fullmatch(node):
            return node
        excluded[0] += 1
        return {"sha256": _hash(node)}

    snapshot = clean(schema)
    return {"schema_status": "redacted" if excluded[0] else "complete",
            "complete_sdk_schema": excluded[0] == 0,
            "schema_sha256_ordered_v1": hashlib.sha256(raw.encode()).hexdigest(),
            "schema_bytes": len(raw.encode()), "schema_counts": counts,
            "schema_redacted_count": excluded[0], "schema_snapshot": snapshot}
