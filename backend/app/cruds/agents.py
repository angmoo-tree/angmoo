from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas
from app.core.agent_activity_limits import (
    DEFAULT_MAX_COMMENTS_PER_DAY,
    DEFAULT_MAX_POSTS_PER_DAY,
)
from app.core.image_generation import (
    DEFAULT_USER_IMAGE_MODEL,
    DEFAULT_MAX_IMAGES_PER_DAY,
)
from app.core import security
from app.core import active_hours
from app.core import unit_of_work


HIDDEN_ACTIVITY_ACTION_TYPES = (
    "state_save_suppressed",
    "feed_perception_debug",
    "feed_viewed",
    "feed_interests_noted",
    "feed_seed_consumed",
    "inbox_notifications_provided",
    "inbox_reviewed",
    "observation_note_saved",
    "complete_tick_rejected",
)
STATE_SAVE_DEDUPE_WINDOW = timedelta(seconds=90)


def default_auth_profile_id(provider: str, character_id: str) -> str:
    safe_character_id = "".join(
        char if char.isalnum() or char in {"-", "_"} else "-" for char in character_id
    )
    return f"{provider}:{safe_character_id}"


def default_credential_model() -> str:
    return "gemini-3.1-flash-lite"


def get_setting(db: Session, character_id: str) -> models.AgentActivitySetting | None:
    return db.get(models.AgentActivitySetting, character_id)


def ensure_setting(
    db: Session,
    character_id: str,
    *,
    commit: bool = True,
) -> models.AgentActivitySetting:
    setting = get_setting(db, character_id)
    if setting is not None:
        return setting
    setting = models.AgentActivitySetting(
        character_id=character_id,
        auto_enabled=False,
        activity_level="normal",
        activity_interval_minutes=60,
        comment_cooldown_minutes=180,
        max_comments_per_day=DEFAULT_MAX_COMMENTS_PER_DAY,
        post_cooldown_hours=24,
        max_posts_per_day=DEFAULT_MAX_POSTS_PER_DAY,
        like_policy="normal",
        allow_post=True,
        allow_reply=True,
        allow_like=True,
        allow_repost=True,
        allow_follow=True,
        allow_unfollow=True,
        allow_observe=True,
        tendency_summary="",
        tendency_action_ranges={},
        planner_tendency_profile={},
        tendency_error=None,
        active_hours_start=active_hours.DEFAULT_ACTIVE_HOURS_START,
        active_hours_end=active_hours.DEFAULT_ACTIVE_HOURS_END,
        autonomy_level="balanced",
        writing_temperature=0.6,
        writing_presence_penalty=0.3,
        writing_repetition_level="light",
    )
    db.add(setting)
    if commit:
        db.commit()
        db.refresh(setting)
    else:
        db.flush()
    return setting


def update_setting(
    db: Session,
    setting: models.AgentActivitySetting,
    data: schemas.AgentActivitySettingUpdate,
    *,
    commit: bool = True,
) -> models.AgentActivitySetting:
    for field, value in data.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(setting, field, value)
    if commit:
        db.commit()
        db.refresh(setting)
    else:
        db.flush()
    return setting


def get_image_generation_setting(
    db: Session, character_id: str
) -> models.AgentImageGenerationSetting | None:
    return db.get(models.AgentImageGenerationSetting, character_id)


def ensure_image_generation_setting(
    db: Session, character_id: str
) -> models.AgentImageGenerationSetting:
    setting = get_image_generation_setting(db, character_id)
    if setting is not None:
        return setting
    setting = models.AgentImageGenerationSetting(
        character_id=character_id,
        encrypted_openrouter_api_key=None,
        encrypted_pollinations_api_key=None,
        encrypted_replicate_api_token=None,
        key_fingerprint=None,
        replicate_key_fingerprint=None,
        image_key_mode="disabled",
        image_generation_enabled=False,
        max_images_per_day=DEFAULT_MAX_IMAGES_PER_DAY,
        openrouter_image_model="black-forest-labs/flux.2-klein-4b",
        pollinations_image_model=DEFAULT_USER_IMAGE_MODEL,
        seed_image_url=None,
        visual_identity_prompt=None,
        visual_identity_source_hash=None,
    )
    db.add(setting)
    db.commit()
    db.refresh(setting)
    return setting


def _image_secret_scope(
    db: Session,
    setting: models.AgentImageGenerationSetting,
    *,
    provider: str,
) -> security.SecretScope:
    character = db.get(models.Character, setting.character_id)
    if character is None:
        raise ValueError("image credential character is missing")
    return security.SecretScope(
        owner_id=character.owner_id,
        character_id=character.id,
        provider=provider,
        purpose="user_image",
    )


def update_image_generation_setting(
    db: Session,
    setting: models.AgentImageGenerationSetting,
    data: schemas.AgentImageGenerationSettingUpdate,
) -> models.AgentImageGenerationSetting:
    payload = data.model_dump(exclude_unset=True)
    api_key = payload.pop("pollinations_api_key", None)
    clear_key = bool(payload.pop("clear_pollinations_api_key", False))
    replicate_api_key = payload.pop("replicate_api_key", None)
    clear_replicate_key = bool(payload.pop("clear_replicate_api_key", False))
    visual_identity_prompt = payload.pop("visual_identity_prompt", None)
    clear_visual_identity = bool(payload.pop("clear_visual_identity_prompt", False))
    for field, value in payload.items():
        if value is not None:
            setattr(setting, field, value)
    if api_key is not None:
        setting.encrypted_pollinations_api_key = security.encrypt_secret(
            api_key,
            scope=_image_secret_scope(db, setting, provider="pollinations"),
        )
        setting.key_fingerprint = security.fingerprint_secret(api_key)
    elif clear_key:
        setting.encrypted_pollinations_api_key = None
        setting.key_fingerprint = None
        if setting.image_key_mode == "user":
            setting.image_key_mode = "disabled"
    if replicate_api_key is not None:
        setting.encrypted_replicate_api_token = security.encrypt_secret(
            replicate_api_key,
            scope=_image_secret_scope(db, setting, provider="replicate"),
        )
        setting.replicate_key_fingerprint = security.fingerprint_secret(replicate_api_key)
    elif clear_replicate_key:
        setting.encrypted_replicate_api_token = None
        setting.replicate_key_fingerprint = None
        if setting.image_key_mode == "user" and setting.pollinations_image_model == "replicate-zimage-turbo-lora":
            setting.image_key_mode = "disabled"
    if visual_identity_prompt is not None:
        prompt = visual_identity_prompt.strip()
        setting.visual_identity_prompt = prompt or None
        setting.visual_identity_source_hash = None
    elif clear_visual_identity:
        setting.visual_identity_prompt = None
        setting.visual_identity_source_hash = None
    setting.image_generation_enabled = setting.image_key_mode != "disabled"
    db.commit()
    db.refresh(setting)
    return setting


def clear_image_visual_identity(
    db: Session,
    character_id: str,
    *,
    commit: bool = True,
) -> models.AgentImageGenerationSetting:
    setting = ensure_image_generation_setting(db, character_id)
    setting.visual_identity_prompt = None
    setting.visual_identity_source_hash = None
    if commit:
        db.commit()
        db.refresh(setting)
    else:
        db.flush()
    return setting


def get_character_credential(
    db: Session, character_id: str
) -> models.LlmCredential | None:
    return db.scalar(
        select(models.LlmCredential)
        .where(models.LlmCredential.character_id == character_id)
        .where(models.LlmCredential.purpose == "agent")
    )


def get_active_local_key(
    db: Session, character_id: str
) -> models.AgentLocalKey | None:
    return db.scalar(
        select(models.AgentLocalKey)
        .where(models.AgentLocalKey.character_id == character_id)
        .where(models.AgentLocalKey.enabled.is_(True))
        .where(models.AgentLocalKey.revoked_at.is_(None))
        .order_by(
            models.AgentLocalKey.created_at.desc(),
            models.AgentLocalKey.id.desc(),
        )
        .limit(1)
    )


def get_active_local_key_by_hash(
    db: Session, token_hash: str
) -> models.AgentLocalKey | None:
    return db.scalar(
        select(models.AgentLocalKey)
        .where(models.AgentLocalKey.token_hash == token_hash)
        .where(models.AgentLocalKey.enabled.is_(True))
        .where(models.AgentLocalKey.revoked_at.is_(None))
        .limit(1)
    )


def get_latest_local_key(
    db: Session, character_id: str
) -> models.AgentLocalKey | None:
    return db.scalar(
        select(models.AgentLocalKey)
        .where(models.AgentLocalKey.character_id == character_id)
        .order_by(
            models.AgentLocalKey.created_at.desc(),
            models.AgentLocalKey.id.desc(),
        )
        .limit(1)
    )


def create_local_key(
    db: Session,
    *,
    user: models.User,
    character: models.Character,
    token: str,
    token_prefix: str,
) -> models.AgentLocalKey:
    revoke_active_local_key(db, character.id, commit=False)
    key = models.AgentLocalKey(
        id=f"local-key-{uuid4().hex[:12]}",
        owner_id=user.id,
        character_id=character.id,
        token_hash=security.hash_token(token),
        token_prefix=token_prefix,
        enabled=True,
    )
    db.add(key)
    db.commit()
    db.refresh(key)
    return key


def revoke_active_local_key(
    db: Session, character_id: str, *, commit: bool = True
) -> models.AgentLocalKey | None:
    key = get_active_local_key(db, character_id)
    if key is None:
        return None
    key.enabled = False
    key.revoked_at = datetime.now(UTC)
    if commit:
        db.commit()
        db.refresh(key)
    else:
        db.flush()
    return key


def mark_local_key_used(
    db: Session, key: models.AgentLocalKey, *, used_at: datetime | None = None
) -> models.AgentLocalKey:
    key.last_used_at = used_at or datetime.now(UTC)
    db.commit()
    db.refresh(key)
    return key


def upsert_credential(
    db: Session,
    *,
    user: models.User,
    character: models.Character,
    provider: str,
    model: str | None,
    api_key: str,
    auth_profile_id: str | None,
    label: str | None,
    commit: bool = True,
) -> models.LlmCredential:
    credential = get_character_credential(db, character.id)
    profile_id = auth_profile_id or default_auth_profile_id(provider, character.id)
    credential_model = model or default_credential_model()
    encrypted_api_key = security.encrypt_secret(
        api_key,
        scope=security.SecretScope(
            owner_id=user.id,
            character_id=character.id,
            provider=provider,
            purpose="agent",
        ),
    )
    key_fingerprint = security.fingerprint_secret(api_key)
    if credential is None:
        credential = models.LlmCredential(
            id=f"cred-{uuid4().hex[:12]}",
            owner_id=user.id,
            character_id=character.id,
            provider=provider,
            purpose="agent",
            model=credential_model,
            auth_profile_id=profile_id,
            label=label or f"{character.name} {provider}",
            encrypted_api_key=encrypted_api_key,
            key_fingerprint=key_fingerprint,
            enabled=True,
        )
        db.add(credential)
    else:
        credential.provider = provider
        credential.model = credential_model
        credential.auth_profile_id = profile_id
        credential.label = label or credential.label
        credential.encrypted_api_key = encrypted_api_key
        credential.key_fingerprint = key_fingerprint
        credential.enabled = True
    if commit:
        db.commit()
        db.refresh(credential)
    else:
        db.flush()
    return credential


def filter_visible_activity_logs(
    logs: list[models.AgentActivityLog], *, limit: int
) -> list[models.AgentActivityLog]:
    visible: list[models.AgentActivityLog] = []
    state_saved_seen: list[datetime] = []
    for log in logs:
        if log.action_type in HIDDEN_ACTIVITY_ACTION_TYPES:
            continue
        if log.action_type == "state_saved":
            if any(
                abs(saved_at - log.created_at) <= STATE_SAVE_DEDUPE_WINDOW
                for saved_at in state_saved_seen
            ):
                continue
            state_saved_seen.append(log.created_at)
        visible.append(log)
        if len(visible) >= limit:
            break
    return visible


def list_recent_activity(
    db: Session, character_id: str, limit: int = 20
) -> list[models.AgentActivityLog]:
    logs = list(
        db.scalars(
            select(models.AgentActivityLog)
            .where(models.AgentActivityLog.character_id == character_id)
            .where(
                models.AgentActivityLog.action_type.not_in(
                    HIDDEN_ACTIVITY_ACTION_TYPES
                )
            )
            .order_by(
                models.AgentActivityLog.created_at.desc(), models.AgentActivityLog.id.desc()
            )
            .limit(max(limit * 3, limit + 20))
        )
    )
    return filter_visible_activity_logs(logs, limit=limit)


def get_pending_feed_cue(db: Session, character_id: str) -> models.AgentFeedCue | None:
    return db.scalar(
        select(models.AgentFeedCue)
        .where(
            models.AgentFeedCue.character_id == character_id,
            models.AgentFeedCue.status == "pending",
        )
        .order_by(models.AgentFeedCue.created_at.asc(), models.AgentFeedCue.id.asc())
        .limit(1)
    )


def create_feed_cue(
    db: Session, *, user: models.User, character: models.Character, topic: str
) -> models.AgentFeedCue:
    cue = models.AgentFeedCue(
        user_id=user.id,
        character_id=character.id,
        topic=topic.strip(),
        status="pending",
    )
    db.add(cue)
    db.commit()
    db.refresh(cue)
    return cue


def mark_pending_feed_cue_used(
    db: Session, *, character_id: str, run_id: str | None, post_id: str
) -> models.AgentFeedCue | None:
    cue = get_pending_feed_cue(db, character_id)
    if cue is None:
        return None
    cue.status = "used"
    cue.consumed_run_id = run_id
    cue.consumed_post_id = post_id
    cue.consumed_at = datetime.now(UTC)
    db.commit()
    db.refresh(cue)
    return cue


def log_activity(
    db: Session,
    *,
    user_id: str,
    character_id: str,
    action_type: str,
    target_post_id: str | None,
    reason: str,
    result: str,
) -> models.AgentActivityLog:
    log = models.AgentActivityLog(
        user_id=user_id,
        character_id=character_id,
        action_type=action_type,
        target_post_id=target_post_id,
        reason=reason,
        result=result,
    )
    db.add(log)
    unit_of_work.finish_write(db, log)
    return log


def get_assigned_slot(
    db: Session, character_id: str
) -> models.AgentSlot | None:
    return db.scalar(
        select(models.AgentSlot)
        .where(models.AgentSlot.assigned_character_id == character_id)
        .order_by(
            (models.AgentSlot.status == "running").desc(),
            models.AgentSlot.last_run_at.desc().nullslast(),
            models.AgentSlot.updated_at.desc(),
            models.AgentSlot.agent_id.asc(),
        )
    )


def set_character_status(db: Session, character: models.Character, status: str) -> None:
    character.status = status
    db.commit()


def disable_other_active_settings(
    db: Session,
    *,
    user_id: str,
    keep_character_id: str,
    commit: bool = True,
) -> list[models.AgentActivitySetting]:
    settings = list_other_active_settings(
        db, user_id=user_id, keep_character_id=keep_character_id
    )
    now = datetime.now(UTC)
    for setting in settings:
        setting.auto_enabled = False
        setting.updated_at = now
    if settings and commit:
        db.commit()
    elif settings:
        db.flush()
    return settings


def list_other_active_settings(
    db: Session, *, user_id: str, keep_character_id: str
) -> list[models.AgentActivitySetting]:
    settings = list(
        db.scalars(
            select(models.AgentActivitySetting)
            .join(models.Character)
            .where(
                models.Character.owner_id == user_id,
                models.Character.deleted_at.is_(None),
                models.Character.id != keep_character_id,
                models.AgentActivitySetting.auto_enabled.is_(True),
            )
        )
    )
    return settings


def count_effective_active_server_llm_autonomy_agents(
    db: Session, *, exclude_character_ids: set[str] | None = None
) -> int:
    excluded = exclude_character_ids or set()
    auto_enabled_ids = set(
        db.scalars(
            select(models.Character.id)
            .join(models.AgentActivitySetting)
            .where(
                models.Character.execution_mode == "llm",
                models.Character.deleted_at.is_(None),
                models.Character.moderation_status != "suspended",
                models.AgentActivitySetting.auto_enabled.is_(True),
            )
        )
    )
    assigned_slot_ids = set(
        db.scalars(
            select(models.AgentSlot.assigned_character_id)
            .join(
                models.Character,
                models.Character.id == models.AgentSlot.assigned_character_id,
            )
            .where(
                models.AgentSlot.assigned_character_id.is_not(None),
                models.Character.execution_mode == "llm",
                models.Character.deleted_at.is_(None),
                models.Character.moderation_status != "suspended",
            )
        )
    )
    return len((auto_enabled_ids | assigned_slot_ids) - excluded)
