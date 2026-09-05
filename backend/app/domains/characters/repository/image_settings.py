from sqlalchemy.orm import Session
from app.domains.characters import models
from app.core.image_generation import DEFAULT_USER_IMAGE_MODEL, DEFAULT_MAX_IMAGES_PER_DAY

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

def image_secret_character(db: Session, character_id: str) -> models.Character | None:
    return db.get(models.Character, character_id)

def save_setting(db: Session, setting: models.AgentImageGenerationSetting) -> None:
    db.commit()
    db.refresh(setting)
