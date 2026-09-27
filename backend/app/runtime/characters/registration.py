"""One Session/UoW for the existing creator's completed local registration."""
from datetime import UTC, datetime
import hashlib
import json

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.core.ids import uuid7_string
from app.domains.characters import models, schemas
from app.domains.characters.exceptions import AgentCreationDraftHandleConflictError, AgentCreationDraftValidationError
from app.domains.characters.service import profile, persona
from app.domains.characters.service.creator import _ensure_draft_persona_prompt_safety
from app.domains.world_characters.models import CharacterActiveWorld, CharacterWorldBinding, WorldCharacter
from app.domains.world_characters.contracts.runtime_modes import AUTONOMOUS_ACTIVITY_RUNTIME_MODE, AUTONOMOUS_FEED_RUNTIME_MODE
from app.domains.worlds.exceptions import ReservedWorldRoleConflictError, WorldServiceError
from app.domains.worlds.service import ensure_no_specific_role
from app.domains.worlds.service.character_entry import refresh_entry_world_contract
from app.domains.worlds.service.creator import require_creator_access
from app.domains.worlds.service.default_space import ensure_default_space
from app.domains.routines.service.activity_settings import ensure_setting
from app.policies import name_policy


def resolve_target(db, user, world_id):
    if world_id is None:
        world_id = ensure_default_space(db, owner_id=user.id).id
    try:
        require_creator_access(db, world_id=world_id, user=user)
    except WorldServiceError as exc:
        raise AgentCreationDraftValidationError(exc.reason_code) from exc
    return world_id


def validate_copy_target(db, character_id, world_id):
    existing = db.scalar(select(WorldCharacter.id).where(
        WorldCharacter.character_id == character_id, WorldCharacter.world_id == world_id))
    if existing is not None:
        raise AgentCreationDraftValidationError("이미 이 World에 있는 캐릭터입니다. 기존 프로필을 열어주세요.")


def register_draft(db, user, draft, data):
    from app.runtime.characters.management import get_agent
    from app.domains.characters.service import media_storage as profile_storage

    digest = hashlib.sha256(json.dumps(data.model_dump(), sort_keys=True).encode()).hexdigest()
    receipt = db.get(models.CharacterRegistrationReceipt, draft.id)
    if receipt:
        if receipt.request_digest != digest:
            raise AgentCreationDraftHandleConflictError("registration_request_changed")
        return get_agent(db, user, receipt.character_id)
    if draft.status != "editing" or data.revision != draft.revision:
        raise AgentCreationDraftHandleConflictError("draft_revision_conflict")
    if data.activity_interval_minutes is not None or data.active_hours_start is not None or data.promotion_usage_allowed:
        raise AgentCreationDraftValidationError("실행 설정은 등록 후 활동 준비에서 지정해주세요.")
    if not draft.name.strip() or (draft.source_kind != "external" and not draft.worldview.strip()):
        raise AgentCreationDraftValidationError("이름과 캐릭터 설명을 입력해주세요.")
    try:
        schemas.AgentCreationDraftUpdate(**{key: getattr(draft, key) for key in (
            "name", "one_liner", "personality", "speech_style", "worldview", "character_background", "topic_preferences", "safety_rules")})
    except ValueError as exc:
        raise AgentCreationDraftValidationError("항목별 길이를 확인해주세요.") from exc
    if name_policy.is_blocked_name(draft.name):
        raise AgentCreationDraftValidationError("사용할 수 없는 이름입니다.")
    values = {key: getattr(draft, key) for key in persona.PERSONA_PROMPT_SAFETY_FIELDS}
    _ensure_draft_persona_prompt_safety(values)
    world, membership = require_creator_access(db, world_id=draft.target_world_id, user=user)
    character_id, world_character_id = uuid7_string(), uuid7_string()
    handle = profile.validate_character_handle_for_create(db, draft.handle) if draft.handle else f"angmoo_{character_id.replace('-', '')}"
    promoted_files = []
    try:
        locked = db.execute(update(models.AgentCreationDraft).where(
            models.AgentCreationDraft.id == draft.id, models.AgentCreationDraft.revision == data.revision,
            models.AgentCreationDraft.status == "editing",
        ).values(status="registering").execution_options(synchronize_session="fetch"))
        if locked.rowcount != 1:
            db.rollback()
            receipt = db.get(models.CharacterRegistrationReceipt, draft.id)
            if receipt and receipt.request_digest == digest:
                return get_agent(db, user, receipt.character_id)
            raise AgentCreationDraftHandleConflictError("registration_conflict")
        character = models.Character(id=character_id, owner_id=user.id, name=draft.name.strip(), handle=handle,
            one_liner=draft.one_liner, personality=draft.personality, speech_style=draft.speech_style,
            worldview=draft.worldview, character_background=draft.character_background,
            topic_preferences=draft.topic_preferences, safety_rules=draft.safety_rules,
            status="inactive", execution_mode="local" if draft.source_kind == "external" else "llm", persona_summary="")
        character.persona_summary = profile._build_persona_summary(character)
        for kind in ("avatar", "banner"):
            source = getattr(draft, f"{kind}_temp_url")
            if source:
                from app.config import settings
                from app.integrations.media.files import media_url_to_path
                media_url_to_path(source).resolve().relative_to((settings.media_root_path / "drafts" / draft.id).resolve())
                url = profile_storage.promote_draft_profile_media(
                    character_id=character_id, media_type=kind, draft_media_url=source)
                promoted_files.append(media_url_to_path(url))
                setattr(character, f"{kind}_url", url)
        db.add(character)
        db.flush()
        try:
            role = ensure_no_specific_role(db, world_id=world.id)
        except ReservedWorldRoleConflictError as exc:
            raise AgentCreationDraftValidationError("world_reference_invalid") from exc
        refresh_entry_world_contract(db, world)
        row = WorldCharacter(id=world_character_id, world_id=world.id, character_id=character.id,
            membership_id=membership.id, role_key=role.role_key, status="active", control_mode="autonomous",
            autonomous_enabled=False, activity_runtime_mode=AUTONOMOUS_ACTIVITY_RUNTIME_MODE,
            feed_runtime_mode=AUTONOMOUS_FEED_RUNTIME_MODE, local_profile={}, version=1)
        db.add(row)
        db.flush()
        db.add(CharacterWorldBinding(character_id=character.id, world_id=world.id))
        db.add(CharacterActiveWorld(character_id=character.id, world_character_id=row.id,
            selected_at=datetime.now(UTC), idempotency_key=f"register:{draft.id}", version=1))
        ensure_setting(db, character.id, commit=False)
        from app.domains.characters.repository.image_settings import ensure_image_generation_setting
        ensure_image_generation_setting(db, character.id, commit=False)
        source = db.scalar(select(models.CharacterCardSource).where(models.CharacterCardSource.draft_id == draft.id))
        if source:
            source.character_id = character.id
        db.add(models.CharacterRegistrationReceipt(draft_id=draft.id, request_digest=digest,
            character_id=character.id, world_character_id=row.id))
        draft.status = "completed"
        draft.encrypted_api_key = None
        draft.key_fingerprint = None
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        for path in promoted_files:
            path.unlink(missing_ok=True)
        receipt = db.get(models.CharacterRegistrationReceipt, draft.id)
        if receipt and receipt.request_digest == digest:
            return get_agent(db, user, receipt.character_id)
        raise AgentCreationDraftHandleConflictError("registration_conflict") from exc
    except Exception:
        db.rollback()
        for path in promoted_files:
            path.unlink(missing_ok=True)
        raise
    return get_agent(db, user, character_id)
