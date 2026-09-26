"""Creator draft ownership, writes, expiry and completion in the caller Session.

Filesystem/LLM/Character runtime work is supplied by app composition. Cleanup
retains its existing per-draft commit/rollback policy and media-before-DB order.
"""
from datetime import UTC, datetime, timedelta
import logging
from uuid import uuid4
from sqlalchemy import select, update, delete
from sqlalchemy.orm import Session
from app.domains.characters.policies.persona import PERSONA_LIMITS
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
    if workflows.resolve_target is None:
        raise AgentCreationDraftValidationError("creation_target_resolver_required")
    target_world_id = workflows.resolve_target(db, user, data.target_world_id)
    draft = models.AgentCreationDraft(
        id=draft_id,
        user_id=user.id,
        provider=data.provider,
        model=data.model,
        thinking_level=data.thinking_level,
        encrypted_api_key=None,
        key_fingerprint=None,
        contract_version=2,
        revision=1,
        target_world_id=target_world_id,
        source_kind="external" if data.execution_mode == "local" else "direct",
        status="editing",
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
        expires_at=datetime.now(UTC) + timedelta(days=7),
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
    if draft.contract_version >= 2:
        claim_edit(db, draft, data.revision)
    try:
        for field, value in data.model_dump(exclude_unset=True, exclude={"revision"}).items():
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
                if field in {"avatar_temp_url", "banner_temp_url"}:
                    from app.config import settings
                    from app.integrations.media.files import media_url_to_path
                    try:
                        path = media_url_to_path(cleaned).resolve()
                        path.relative_to((settings.media_root_path / "drafts" / draft.id).resolve())
                        if not path.is_file():
                            raise ValueError("media_missing")
                    except ValueError as exc:
                        db.rollback()
                        raise AgentCreationDraftValidationError("draft_media_not_owned") from exc
                if field in persona.PERSONA_PROMPT_SAFETY_FIELDS:
                    _ensure_draft_prompt_safety(cleaned, field_name=field)
                setattr(draft, field, cleaned)
        db.commit()
        db.refresh(draft)
    except Exception:
        db.rollback()
        raise
    return _draft_read(draft)


def claim_edit(db: Session, draft, revision: int | None) -> None:
    result = db.execute(update(models.AgentCreationDraft).where(
        models.AgentCreationDraft.id == draft.id,
        models.AgentCreationDraft.revision == revision,
        models.AgentCreationDraft.status == "editing",
    ).values(revision=models.AgentCreationDraft.revision + 1,
             expires_at=datetime.now(UTC) + timedelta(days=7)).execution_options(synchronize_session="fetch"))
    if result.rowcount != 1:
        db.rollback()
        raise AgentCreationDraftHandleConflictError("draft_revision_conflict")


async def enhance_persona(
    db: Session, user: CharacterOwner, draft_id: str,
    *, workflows: CreatorWorkflows,
) -> schemas.AgentCreationDraftRead:
    draft = _get_owned_draft(db, user, draft_id, workflows=workflows)
    if draft.contract_version >= 2:
        raise AgentCreationDraftValidationError("AI 설정은 등록 후 활동 준비에서 진행해주세요.")
    _ensure_not_in_cooldown(draft.persona_enhance_available_at)
    api_key = workflows.decrypt_api_key(draft)
    raw_text = await workflows.run_llm(
        db=db,
        user=user,
        draft_id=draft.id,
        provider=draft.provider,
        model=draft.model,
        thinking_level=draft.thinking_level,
        api_key=api_key,
        message="보강할 앵무 페르소나를 JSON으로 정리해 주세요.",
        extra_system_prompt=_build_persona_enhance_prompt(draft),
    )
    payload = _parse_json_object(raw_text)
    try:
        validated = schemas.AgentPersonaUpdate.model_validate({
            key: _safe_payload_text(payload.get(key), limit) for key, limit in PERSONA_LIMITS.items() if key != "one_liner"
        })
    except ValueError as exc:
        raise AgentCreationDraftValidationError("AI 보강 결과가 항목별 길이 또는 입력 형식 제한을 넘었습니다. 기존 내용은 유지됩니다.") from exc
    persona_values = validated.model_dump()
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
    if draft.contract_version >= 2:
        if workflows.register_draft is None:
            raise AgentCreationDraftValidationError("registration_workflow_required")
        return workflows.register_draft(db, user, draft, data)
    raise AgentCreationDraftValidationError("이전 초안은 새 등록 방식으로 이어간 뒤 완료해주세요.")


def adopt_legacy_draft(db, user, draft_id, data: schemas.AgentCreationDraftAdopt, *, workflows):
    draft = _get_owned_draft(db, user, draft_id, workflows=workflows)
    if workflows.resolve_target is None:
        raise AgentCreationDraftValidationError("creation_target_resolver_required")
    target = workflows.resolve_target(db, user, data.target_world_id)
    if draft.contract_version >= 2:
        if draft.target_world_id != target:
            raise AgentCreationDraftHandleConflictError("draft_target_conflict")
        return _draft_read(draft)
    try:
        claim_edit(db, draft, data.revision)
        draft.contract_version = 2
        draft.target_world_id = target
        draft.source_kind = "direct"
        # Keep legacy encrypted material in its private row, but never attach it
        # to the newly registered character. Preparation requires explicit setup.
        db.commit()
        db.refresh(draft)
    except Exception:
        db.rollback()
        raise
    return _draft_read(draft)


def _get_owned_draft(
    db: Session, user: CharacterOwner, draft_id: str,
    *, workflows: CreatorWorkflows,
) -> models.AgentCreationDraft:
    draft = db.get(models.AgentCreationDraft, draft_id)
    if draft is None or draft.user_id != user.id:
        raise AgentCreationDraftNotFoundError(draft_id)
    expires_at = draft.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if draft.status != "completed" and expires_at <= datetime.now(UTC):
        # Ownership reads never mutate data or delete media. Explicit lifecycle
        # cleanup retains responsibility for expired, unregistered drafts.
        raise AgentCreationDraftExpiredError(draft_id)
    return draft


def _cleanup_expired_drafts(db: Session,
    *, workflows: CreatorWorkflows,
) -> None:
    now = datetime.now(UTC)
    expired = list(
        db.scalars(
            select(models.AgentCreationDraft)
            .where(models.AgentCreationDraft.expires_at <= now, models.AgentCreationDraft.status != "completed")
            .limit(20)
        )
    )
    if not expired:
        return
    for draft in expired:
        try:
            if draft.contract_version >= 2:
                claimed = db.execute(update(models.AgentCreationDraft).where(
                    models.AgentCreationDraft.id == draft.id,
                    models.AgentCreationDraft.status == "editing",
                    models.AgentCreationDraft.expires_at <= now,
                ).values(status="expiring").execution_options(synchronize_session="fetch"))
                if claimed.rowcount != 1:
                    db.rollback()
                    continue
            if draft.contract_version >= 2:
                db.execute(delete(models.CharacterCardSource).where(models.CharacterCardSource.draft_id == draft.id, models.CharacterCardSource.character_id.is_(None)))
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
