from sqlalchemy.orm import Session
from app.domains.characters import models, schemas
from app.domains.characters.repository import image_settings as image_repository
from app.core import security

def _image_secret_scope(
    db: Session,
    setting: models.AgentImageGenerationSetting,
    *,
    provider: str,
) -> security.SecretScope:
    character = image_repository.image_secret_character(db, setting.character_id)
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
    image_repository.save_setting(db, setting)
    return setting
