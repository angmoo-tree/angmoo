from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas
from app.core.image_generation import (
    DEFAULT_USER_IMAGE_MODEL,
    DEFAULT_MAX_IMAGES_PER_DAY,
)
from app.core import security
from app.core import active_hours
from app.core import unit_of_work


def default_auth_profile_id(provider: str, character_id: str) -> str:
    safe_character_id = "".join(
        char if char.isalnum() or char in {"-", "_"} else "-" for char in character_id
    )
    return f"{provider}:{safe_character_id}"


def default_credential_model() -> str:
    return "gemini-3.1-flash-lite"


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

from app.domains.routines.constants import HIDDEN_ACTIVITY_ACTION_TYPES, STATE_SAVE_DEDUPE_WINDOW
from app.domains.routines.service.activity_logs import filter_visible_activity_logs, list_recent_activity, log_activity
from app.domains.routines.service.activity_settings import get_setting, ensure_setting, update_setting
