"""Allowlisted Routine read views, separate from attached effect/claim records."""
from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime
from types import SimpleNamespace
import json

from app.domains.memory.contracts.activity_situation import stable_digest

FIELDS = {
    "world": "id name tagline setting_description daily_life_description tone_tags timezone",
    "world_character": "id world_id character_id local_profile",
    "character": "id name one_liner worldview personality speech_style character_background topic_preferences safety_rules persona_summary",
    "profile": "id visible_summary core_interests action_profile",
    "plan": "id version local_date timezone_name",
    "item": "id daypart activity_kind title activity_seed social_mode place_key scheduled_start_at scheduled_end_at joint_activity_id",
    "episode": "id version effective_activity_snapshot state_schema_version",
    "previous_beat": "id sequence_no result_snapshot",
    "previous_post": "id created_at title body topic_signature",
}


def _encode(value):
    if isinstance(value, datetime):
        return {"_instant": value.isoformat()}
    if isinstance(value, date):
        return {"_date": value.isoformat()}
    if isinstance(value, dict):
        return {key: _encode(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_encode(item) for item in value]
    return value


def _decode(value):
    if isinstance(value, dict):
        if set(value) == {"_instant"}:
            return datetime.fromisoformat(value["_instant"])
        if set(value) == {"_date"}:
            return date.fromisoformat(value["_date"])
        return {key: _decode(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_decode(item) for item in value]
    return value


def capture(context):
    rows = {name: None if (row := getattr(context, name)) is None else {
        field: _encode(deepcopy(getattr(row, field, None))) for field in fields.split()}
        for name, fields in FIELDS.items()}
    if len(json.dumps(rows, ensure_ascii=False).encode()) > 512 * 1024:
        raise ValueError("routine_initial_input_limit")
    return {"policy": "routine-initial-input.v1", "rows": rows, "digest": stable_digest(rows)}


def restore(context, frozen):
    if len(json.dumps(frozen, ensure_ascii=False, allow_nan=False).encode()) > 512 * 1024:
        raise ValueError("routine_initial_input_limit")
    if (not isinstance(frozen, dict) or frozen.get("policy") != "routine-initial-input.v1"
            or set(frozen.get("rows", {})) != set(FIELDS)
            or frozen.get("digest") != stable_digest(frozen["rows"])):
        raise ValueError("routine_initial_input_unavailable")
    values = {}
    for name, raw in frozen["rows"].items():
        if raw is not None and set(raw) != set(FIELDS[name].split()):
            raise ValueError("routine_initial_input_invalid")
        original = getattr(context, name)
        if name not in {"previous_beat", "previous_post"} and (
                None if original is None else original.id) != (None if raw is None else raw["id"]):
            raise ValueError("routine_initial_input_scope_invalid")
        values[name] = None if raw is None else SimpleNamespace(**_decode(raw))
    return replace(context, **values)
