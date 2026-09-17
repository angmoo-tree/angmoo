"""Opt-in provider schema conversion; legacy read contracts stay unchanged."""

from copy import deepcopy
from dataclasses import asdict
import json

from app.contracts.activity_thought import ActivityThought, parse_activity_thought

LEGACY_SELF_VIEW_FIELDS = frozenset({"motivation_kind", "motivation_text", "emotion_label", "emotion_text", "emotion_intensity"})


def thought_response_schema(schema: dict, *, include_thought: bool) -> dict:
    result = deepcopy(schema)
    for key in LEGACY_SELF_VIEW_FIELDS:
        result.get("properties", {}).pop(key, None)
    result["required"] = [key for key in result.get("required", []) if key not in LEGACY_SELF_VIEW_FIELDS]
    if include_thought:
        result.setdefault("properties", {})["thought"] = {"type": "string"}
        if "thought" not in result["required"]:
            result["required"].append("thought")
    return result


def extract_activity_thought(payload: dict, *, include_thought: bool) -> tuple[dict, ActivityThought | None]:
    result = {k: v for k, v in payload.items() if k not in LEGACY_SELF_VIEW_FIELDS and k != "thought"}
    return result, parse_activity_thought(payload.get("thought")) if include_thought else None


def without_legacy_self_view_prompt(system: str, user: str) -> tuple[str, str]:
    """Remove superseded instructions rather than asking for both declarations."""
    system = "\n".join(line for line in system.splitlines() if not any(
        marker in line for marker in ("Declare one short public-safe", "declare one short public-safe motivation", "motivation_kind/motivation_text")
    ))
    def clean(value):
        if isinstance(value, dict):
            return {k: clean(v) for k, v in value.items() if k not in LEGACY_SELF_VIEW_FIELDS and k not in {"subjective_context", "subjective_context_rule"}}
        if isinstance(value, list):
            return [clean(v) for v in value]
        return value
    try:
        parsed = json.loads(user)
    except ValueError:
        return system, user
    return system, json.dumps(clean(parsed), ensure_ascii=False, default=str)


def resident_thought_schema(schema: dict, *, writer: bool) -> dict:
    """Transform nested action/task objects without touching execution fields."""
    def visit(value):
        if isinstance(value, list):
            return [visit(v) for v in value]
        if not isinstance(value, dict):
            return value
        result = {k: visit(v) for k, v in value.items()}
        properties = result.get("properties")
        if isinstance(properties, dict):
            include = (writer and ("body" in properties or "post_body" in properties)) or (not writer and ("action_type" in properties or ("decision" in properties and "motivation_kind" in properties)))
            result = thought_response_schema(result, include_thought=include)
        return result
    return visit(schema)


def resident_thought_payload(payload: dict, model, *, writer: bool) -> dict:
    """Validate original body/action fields first; attach only corresponding thought."""
    def strip(value):
        if isinstance(value, dict):
            return {k: strip(v) for k, v in value.items() if k not in LEGACY_SELF_VIEW_FIELDS and k not in {"thought", "_activity_thought"}}
        if isinstance(value, list):
            return [strip(v) for v in value]
        return value
    validated = model.model_validate(strip(payload)).model_dump()
    def attach(value, raw):
        if isinstance(value, list) and isinstance(raw, list):
            return [attach(v, r) for v, r in zip(value, raw, strict=True)]
        if not isinstance(value, dict):
            return value
        raw = raw if isinstance(raw, dict) else {}
        result = {k: attach(v, raw.get(k)) for k, v in value.items() if k not in LEGACY_SELF_VIEW_FIELDS}
        include = (writer and ("body" in value or "post_body" in value)) or (not writer and (value.get("action_type") in {"like", "repost", "follow", "unfollow"} or value.get("decision") in {"follow", "unfollow"}))
        if include:
            result["_activity_thought"] = asdict(parse_activity_thought(raw.get("thought")))
        return result
    return attach(validated, payload)
