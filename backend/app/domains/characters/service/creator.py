"""Creator draft response, persona validation and generation result policy."""
from datetime import UTC, datetime, timedelta
import json
import re
from typing import Any
from app.core import prompt_safety
from app.domains.characters import models, schemas
from app.domains.characters.service import persona as agent_service
from app.domains.characters.exceptions import AgentCreationDraftParseError, AgentCreationDraftCooldownError, AgentCreationDraftValidationError


DRAFT_TTL = timedelta(hours=1)

DRAFT_COOLDOWN = timedelta(seconds=60)

PROFILE_IMAGE_CANDIDATE_TTL = timedelta(hours=1)

def _ensure_draft_persona_prompt_safety(values: dict[str, str]) -> None:
    for field, value in values.items():
        if field in agent_service.PERSONA_PROMPT_SAFETY_FIELDS:
            _ensure_draft_prompt_safety(value, field_name=field)

def _ensure_draft_prompt_safety(value: str, *, field_name: str) -> None:
    try:
        prompt_safety.ensure_no_prompt_injection_text(
            value,
            field_name=field_name,
            field_kind="persona",
        )
    except prompt_safety.PromptSafetyError as exc:
        raise AgentCreationDraftValidationError("prompt_injection_detected") from exc

def _draft_read(draft: models.AgentCreationDraft) -> schemas.AgentCreationDraftRead:
    result = schemas.AgentCreationDraftRead.model_validate(draft)
    return result.model_copy(
        update={
            "avatar_temp_url": (
                f"/api/v1/agents/drafts/{draft.id}/media/avatar"
                if draft.avatar_temp_url
                else None
            ),
            "banner_temp_url": (
                f"/api/v1/agents/drafts/{draft.id}/media/banner"
                if draft.banner_temp_url
                else None
            ),
        }
    )

def _build_persona_enhance_prompt(draft: models.AgentCreationDraft) -> str:
    return f"""
You refine an Angmoo character persona from rough Korean notes.
Return only JSON with these exact keys:
personality, speech_style, worldview, topic_preferences, safety_rules.
Every value must be a Korean string, not an array or object.

Rules:
- Write Korean.
- Keep the user's intent and do not overwrite the character.
- If a field is short, make it concrete enough for an autonomous social character.
- Fill topic_preferences and safety_rules even if the current draft leaves them empty.
- Do not add sexual content, illegal instructions, private data, or real-person claims.
- Each value must be concise and directly usable in the Angmoo character form.

Current draft:
- name: {draft.name}
- one_liner: {draft.one_liner}
- personality: {draft.personality}
- speech_style: {draft.speech_style}
- worldview: {draft.worldview}
- topic_preferences: {draft.topic_preferences}
- safety_rules: {draft.safety_rules}
""".strip()

def _parse_json_object(text: str) -> dict[str, Any]:
    raw = text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        raw = match.group(0)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AgentCreationDraftParseError("페르소나 보강 결과를 읽지 못했습니다.") from exc
    if not isinstance(payload, dict):
        raise AgentCreationDraftParseError("페르소나 보강 결과 형식이 올바르지 않습니다.")
    return payload

def _safe_payload_text(value: Any, max_length: int) -> str:
    if not isinstance(value, str):
        if isinstance(value, list):
            value = "\n".join(
                str(item).strip()
                for item in value
                if isinstance(item, (str, int, float)) and str(item).strip()
            )
        else:
            return ""
    return value.strip()[:max_length]

def _clean_text(value: Any) -> Any:
    return value.strip() if isinstance(value, str) else value

def _ensure_not_in_cooldown(available_at: datetime | None) -> None:
    if available_at is not None and available_at > datetime.now(UTC):
        raise AgentCreationDraftCooldownError(available_at)
