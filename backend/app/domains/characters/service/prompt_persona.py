"""Pure, versioned character settings for model-facing contexts.

``worldview`` remains the persisted/API name of the complete description.
The optional background is never inferred from, or copied into, that field.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from app.domains.characters.policies.name_macros import render_names
from app.domains.characters.policies.authored_names import authored_thought


PERSONA_INPUT_VERSION = "character-persona-input-v1"
PERSONA_INTERPRETATION = (
    "The character description can contain personality, speech, appearance, history, "
    "interests and preferences. Read it together with any explicitly supplied detail. "
    "An empty detail field does not mean the description lacks that trait. Where the "
    "description and an explicit detail conflict on the same trait, use the explicit "
    "detail; for origin, past and affiliation use the separate character background. "
    "Card dialogue examples and fictional backstory are not actual conversations, "
    "events, relationships or memories. Current World time, places, roles, actual "
    "history and application rules take precedence over character settings."
)


def _value(source: object, key: str) -> str:
    value = source.get(key, "") if isinstance(source, Mapping) else getattr(source, key, "")
    return value if isinstance(value, str) else ""


def legacy_persona_summary(source: object) -> str:
    """Keep the historical deterministic summary contract unchanged."""
    values = (
        _value(source, "one_liner").strip(),
        *(f"{label}: {value}" if value else "" for label, value in (
            ("성격", _value(source, "personality").strip()),
            ("말투", _value(source, "speech_style").strip()),
            ("세계관", _value(source, "worldview").strip()),
            ("관심 주제", _value(source, "topic_preferences").strip()),
            ("피해야 할 행동", _value(source, "safety_rules").strip()),
        )),
    )
    return "\n".join(value for value in values if value)


def model_persona(source: object) -> dict[str, Any]:
    """Build a stable snapshot from supplied values, without any DB or AI work."""
    summary = _value(source, "persona_summary")
    result: dict[str, Any] = {
        "schema_version": PERSONA_INPUT_VERSION,
        "name": _value(source, "name"),
        "one_liner": _value(source, "one_liner"),
        "description": _value(source, "worldview"),
        "personality": _value(source, "personality"),
        "speech_style": _value(source, "speech_style"),
        "character_background": _value(source, "character_background"),
        "topic_preferences": _value(source, "topic_preferences"),
        "safety_rules": _value(source, "safety_rules"),
    }
    if summary and summary != legacy_persona_summary(source):
        result["legacy_persona_summary_extra"] = summary
    return result


def request_persona(source: object, binding) -> dict[str, Any]:
    """A new model-facing copy; edit/export APIs continue to use model_persona."""
    return render_persona(model_persona(source), binding)


def render_persona(value: dict, binding) -> dict[str, Any]:
    """Render an already assembled persona, with an explicit field allowlist."""
    from app.domains.characters.policies.name_macros import render_names, NAME_INPUT_GUIDANCE
    from app.domains.characters.policies.persona import PERSONA_LIMITS, PERSONA_SUMMARY_LIMIT
    persona = dict(value)
    if binding is None:
        return persona
    limits = {**PERSONA_LIMITS, "description": PERSONA_LIMITS["worldview"],
              "legacy_persona_summary_extra": PERSONA_SUMMARY_LIMIT}
    receipts = {}
    for key in ("one_liner", "description", "personality", "speech_style", "character_background",
                "topic_preferences", "safety_rules", "legacy_persona_summary_extra"):
        if key in persona:
            rendered = render_names(persona[key], binding, limit=limits[key])
            persona[key] = rendered.text
            receipts[key] = rendered.receipt()
    persona["name"] = binding.actor_display_name
    persona["name_binding"] = {"policy_version": binding.policy_version,
        "binding_digest": binding.digest, "fields": receipts, "instruction": NAME_INPUT_GUIDANCE}
    return persona


def request_persona_text(source: object, field: str, binding, *, limit: int | None = None) -> str:
    from app.domains.characters.policies.name_macros import render_names
    value = _value(source, field)
    return render_names(value, binding, limit=limit).text if binding is not None else value
