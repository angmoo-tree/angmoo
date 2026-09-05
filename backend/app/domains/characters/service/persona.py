"""Character persona admission; provider execution is composed by callers."""
from typing import Any
from app.core import prompt_safety
from app.domains.characters.exceptions import PromptInjectionDetectedError


PERSONA_PROMPT_SAFETY_FIELDS = (
    "personality",
    "speech_style",
    "worldview",
    "topic_preferences",
    "safety_rules",
)

def ensure_persona_prompt_safety(data: object) -> None:
    for field in PERSONA_PROMPT_SAFETY_FIELDS:
        value = _field_value(data, field)
        if value is None:
            continue
        try:
            prompt_safety.ensure_no_prompt_injection_text(
                value,
                field_name=field,
                field_kind="persona",
            )
        except prompt_safety.PromptSafetyError as exc:
            raise PromptInjectionDetectedError("prompt_injection_detected") from exc

def _field_value(data: object, field: str) -> Any:
    if isinstance(data, dict):
        return data.get(field)
    return getattr(data, field, None)
