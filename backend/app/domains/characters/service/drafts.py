"""Creator draft ownership, writes, expiry and completion in the caller Session.

Filesystem/LLM/Character runtime work is supplied by app composition. Cleanup
retains its existing per-draft commit/rollback policy and media-before-DB order.
"""
from datetime import UTC, datetime
import logging
from uuid import uuid4
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core import security
from app.domains.characters import models, schemas
from app.domains.characters.contracts import CharacterOwner, CreatorWorkflows
from app.domains.characters.exceptions import (
    AgentCreationDraftExpiredError, AgentCreationDraftHandleConflictError,
    AgentCreationDraftNotFoundError, AgentCreationDraftValidationError,
)
from app.domains.characters.service import persona, profile as character_profile
from app.domains.characters.service.creator import (
    DRAFT_TTL, DRAFT_COOLDOWN, _draft_read, _clean_text,
    _ensure_draft_prompt_safety, _ensure_draft_persona_prompt_safety,
    _ensure_not_in_cooldown, _parse_json_object, _safe_payload_text,
    _build_persona_enhance_prompt,
)
from app.policies import name_policy

logger = logging.getLogger(__name__)


async def create_draft(
    db: Session, user: CharacterOwner, data: schemas.AgentCreationDraftCreate,
    *, workflows: CreatorWorkflows,
) -> schemas.AgentCreationDraftRead:
    _cleanup_expired_drafts(db, workflows=workflows)
    draft_id = f"draft-{uuid4().hex[:12]}"
    await workflows.run_llm(
        db=db,
        user=user,
        draft_id=draft_id,
        provider=data.provider,
        model=data.model,
        api_key=data.api_key,
        message='Return exactly this JSON: {"ok": true}',
        extra_system_prompt=(
            "You are verifying an Angmoo user-provided LLM credential. "
            'Return only {"ok": true}. Do not call tools.'
        ),
    )
    draft = models.AgentCreationDraft(
        id=draft_id,
        user_id=user.id,
        provider=data.provider,
        model=data.model,
        encrypted_api_key=security.encrypt_secret(
            data.api_key,
            scope=security.SecretScope(
                owner_id=user.id,
                character_id="",
                provider=data.provider,
                purpose="creation_draft",
            ),
        ),
        key_fingerprint=security.fingerprint_secret(data.api_key),
        name="",
        handle=None,
        one_liner="",
        personality="",
        speech_style="",
        worldview="",
        topic_preferences="",
        safety_rules="",
        image_style="기본",
        appearance_prompt="",
        expires_at=datetime.now(UTC) + DRAFT_TTL,
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return _draft_read(draft)


def get_draft(
    db: Session, user: CharacterOwner, draft_id: str,
    *, workflows: CreatorWorkflows,
) -> schemas.AgentCreationDraftRead:
    draft = _get_owned_draft(db, user, draft_id, workflows=workflows)
    return _draft_read(draft)


def update_draft(
    db: Session,
    user: CharacterOwner,
    draft_id: str,
    data: schemas.AgentCreationDraftUpdate,
    *, workflows: CreatorWorkflows,
) -> schemas.AgentCreationDraftRead:
    draft = _get_owned_draft(db, user, draft_id, workflows=workflows)
    for field, value in data.model_dump(exclude_unset=True).items():
        if field == "handle":
            if value is None or not str(value).strip():
                draft.handle = None
                continue
            if name_policy.is_blocked_name(str(value)):
                raise AgentCreationDraftValidationError("사용할 수 없는 핸들입니다.")
            try:
                draft.handle = character_profile.validate_character_handle_for_create(
                    db, str(value)
                )
            except character_profile.CharacterHandleConflictError as exc:
                raise AgentCreationDraftHandleConflictError(str(exc)) from exc
            except character_profile.InvalidCharacterHandleError as exc:
                raise AgentCreationDraftValidationError(str(exc)) from exc
        elif value is None and field in {"avatar_temp_url", "banner_temp_url"}:
            setattr(draft, field, None)
        elif value is not None:
            cleaned = _clean_text(value)
            if field in persona.PERSONA_PROMPT_SAFETY_FIELDS:
                _ensure_draft_prompt_safety(cleaned, field_name=field)
            setattr(draft, field, cleaned)
    db.commit()
    db.refresh(draft)
    return _draft_read(draft)


async def enhance_persona(
    db: Session, user: CharacterOwner, draft_id: str,
    *, workflows: CreatorWorkflows,
) -> schemas.AgentCreationDraftRead:
    draft = _get_owned_draft(db, user, draft_id, workflows=workflows)
    _ensure_not_in_cooldown(draft.persona_enhance_available_at)
    api_key = workflows.decrypt_api_key(draft)
    raw_text = await workflows.run_llm(
        db=db,
        user=user,
        draft_id=draft.id,
        provider=draft.provider,
        model=draft.model,
        api_key=api_key,
        message="보강할 앵무 페르소나를 JSON으로 정리해 주세요.",
        extra_system_prompt=_build_persona_enhance_prompt(draft),
    )
    payload = _parse_json_object(raw_text)
    persona_values = {
        "personality": _safe_payload_text(payload.get("personality"), 2000),
        "speech_style": _safe_payload_text(payload.get("speech_style"), 1200),
        "worldview": _safe_payload_text(payload.get("worldview"), 2000),
        "topic_preferences": _safe_payload_text(
            payload.get("topic_preferences"), 1200
        ),
        "safety_rules": _safe_payload_text(payload.get("safety_rules"), 1200),
    }
    _ensure_draft_persona_prompt_safety(persona_values)
    draft.personality = persona_values["personality"]
    draft.speech_style = persona_values["speech_style"]
    draft.worldview = persona_values["worldview"]
    draft.topic_preferences = persona_values["topic_preferences"]
    draft.safety_rules = persona_values["safety_rules"]
    draft.persona_enhance_available_at = datetime.now(UTC) + DRAFT_COOLDOWN
    db.commit()
    db.refresh(draft)
    return _draft_read(draft)


def complete_draft(
    db: Session,
    user: CharacterOwner,
    draft_id: str,
    data: schemas.AgentCreationDraftComplete | None = None,
    *, workflows: CreatorWorkflows,
) -> schemas.AgentDetailRead:
    data = data or schemas.AgentCreationDraftComplete()
    draft = _get_owned_draft(db, user, draft_id, workflows=workflows)
    name = draft.name.strip()
    handle = draft.handle.strip() if draft.handle else None
    if not name:
        raise AgentCreationDraftValidationError("이름을 입력해주세요.")
    if name_policy.is_blocked_name(name):
        raise AgentCreationDraftValidationError("사용할 수 없는 닉네임입니다.")
    if handle and name_policy.is_blocked_name(handle):
        raise AgentCreationDraftValidationError("사용할 수 없는 핸들입니다.")
    if not draft.personality.strip():
        raise AgentCreationDraftValidationError("성격을 입력해주세요.")
    _ensure_draft_persona_prompt_safety(
        {
            "personality": draft.personality,
            "speech_style": draft.speech_style,
            "worldview": draft.worldview,
            "topic_preferences": draft.topic_preferences,
            "safety_rules": draft.safety_rules,
        }
    )
    api_key = workflows.decrypt_api_key(draft)
    create_data = schemas.AgentCreate(
        name=name,
        handle=handle,
        one_liner=draft.one_liner.strip(),
        personality=draft.personality.strip(),
        speech_style=draft.speech_style.strip(),
        worldview=draft.worldview.strip(),
        topic_preferences=draft.topic_preferences.strip(),
        safety_rules=draft.safety_rules.strip(),
        provider=draft.provider,
        model=draft.model,  # type: ignore[arg-type]
        api_key=api_key,
        activity_interval_minutes=data.activity_interval_minutes,
        active_hours_start=data.active_hours_start,
        active_hours_end=data.active_hours_end,
        promotion_usage_allowed=data.promotion_usage_allowed,
    )
    detail = workflows.create_character(db, user, create_data)
    character = db.get(models.Character, detail.character.id)
    if character is not None:
        if draft.avatar_temp_url:
            character.avatar_url = workflows.promote_media(
                character_id=character.id,
                media_type="avatar",
                draft_media_url=draft.avatar_temp_url,
            )
        if draft.banner_temp_url:
            character.banner_url = workflows.promote_media(
                character_id=character.id,
                media_type="banner",
                draft_media_url=draft.banner_temp_url,
            )
        db.commit()
    _delete_profile_image_candidates_for_draft(db, draft, workflows=workflows)
    workflows.delete_draft_media(draft.id)
    db.delete(draft)
    db.commit()
    return workflows.read_character(db, user, detail.character.id)


def _get_owned_draft(
    db: Session, user: CharacterOwner, draft_id: str,
    *, workflows: CreatorWorkflows,
) -> models.AgentCreationDraft:
    _cleanup_expired_drafts(db, workflows=workflows)
    draft = db.get(models.AgentCreationDraft, draft_id)
    if draft is None or draft.user_id != user.id:
        raise AgentCreationDraftNotFoundError(draft_id)
    expires_at = draft.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= datetime.now(UTC):
        _delete_profile_image_candidates_for_draft(db, draft, workflows=workflows)
        workflows.delete_draft_media(draft.id)
        db.delete(draft)
        db.commit()
        raise AgentCreationDraftExpiredError(draft_id)
    return draft


def _cleanup_expired_drafts(db: Session,
    *, workflows: CreatorWorkflows,
) -> None:
    now = datetime.now(UTC)
    expired = list(
        db.scalars(
            select(models.AgentCreationDraft)
            .where(models.AgentCreationDraft.expires_at <= now)
            .limit(20)
        )
    )
    if not expired:
        return
    for draft in expired:
        try:
            _delete_profile_image_candidates_for_draft(db, draft, workflows=workflows)
            workflows.delete_draft_media(draft.id)
            db.delete(draft)
            db.commit()
        except Exception:
            db.rollback()
            logger.exception(
                "expired agent creation draft cleanup failed: draft_id=%s",
                draft.id,
            )


def _delete_profile_image_candidates_for_draft(
    db: Session, draft: models.AgentCreationDraft,
    *, workflows: CreatorWorkflows,
) -> None:
    candidates = list(
        db.scalars(
            select(models.ProfileImageCandidate).where(
                models.ProfileImageCandidate.draft_id == draft.id
            )
        )
    )
    for candidate in candidates:
        workflows.delete_candidate_media(candidate.id, candidate.user_id)
        db.delete(candidate)
    if candidates:
        db.flush()
