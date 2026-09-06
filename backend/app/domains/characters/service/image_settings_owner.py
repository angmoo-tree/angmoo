"""Owner image settings, secret admission, seed lifecycle and quota presentation.

Character owns policy and setting writes. Runtime supplies the existing shared
key availability and same-Session Social usage query at their original call sites.
"""
from datetime import datetime
from typing import Literal
from sqlalchemy.orm import Session
from app.config import settings
from app.core import image_prompt_safety
from app.core.image_generation import USER_IMAGE_MODEL_OPTIONS
from app.domains.characters import models, schemas
from app.domains.characters.contracts import CharacterOwner, CharacterImageSettingsWorkflows
from app.domains.characters.exceptions import ImageSettingsInvalidError, UnsafeImagePromptError, InvalidProfileMediaError
from app.domains.characters.repository import image_settings as image_setting_repository
from app.domains.characters.service import image_settings as image_setting_service
from app.domains.characters.service.access import _get_owned_character
from app.domains.characters.service import media_storage as profile_media
from app.domains.identity.service import demo_access as demo_lock
from app.domains.operations.service import settings as operation_settings
from app.integrations import image_provider
from app.integrations.media import files as media_files


def _ensure_initial_image_settings(db: Session, character_id: str, *, workflows: CharacterImageSettingsWorkflows) -> None:
    setting = image_setting_repository.ensure_image_generation_setting(db, character_id)
    setting.image_key_mode = 'service' if workflows.service_image_available() else 'disabled'
    setting.image_generation_enabled = setting.image_key_mode != 'disabled'
    image_setting_repository.save_setting(db, setting)


def _image_generation_setting_read(db: Session, setting: models.AgentImageGenerationSetting, *, workflows: CharacterImageSettingsWorkflows) -> schemas.AgentImageGenerationSettingRead:
    visual_identity_prompt = (setting.visual_identity_prompt or '').strip() or None
    visual_identity_mode: Literal['manual', 'auto', 'none']
    if visual_identity_prompt is None:
        visual_identity_mode = 'none'
    elif setting.visual_identity_source_hash is None:
        visual_identity_mode = 'manual'
    else:
        visual_identity_mode = 'auto'
    quota = _service_image_quota_read(db, setting.character_id, workflows=workflows)
    service_model_setting = operation_settings.get_pollinations_free_image_model_setting(db)
    service_model = service_model_setting.model
    return schemas.AgentImageGenerationSettingRead(character_id=setting.character_id, image_key_mode=setting.image_key_mode, image_generation_enabled=setting.image_generation_enabled, max_images_per_day=setting.max_images_per_day, pollinations_image_model=setting.pollinations_image_model, seed_image_url=setting.seed_image_url, key_fingerprint=setting.key_fingerprint if setting.encrypted_pollinations_api_key else None, has_pollinations_api_key=bool(setting.encrypted_pollinations_api_key), replicate_key_fingerprint=setting.replicate_key_fingerprint if setting.encrypted_replicate_api_token else None, has_replicate_api_key=bool(setting.encrypted_replicate_api_token), visual_identity_prompt_available=visual_identity_prompt is not None, visual_identity_prompt=visual_identity_prompt, visual_identity_mode=visual_identity_mode, visual_identity_source_hash=setting.visual_identity_source_hash, service_image_available=workflows.service_image_available_for_model(service_model), service_image_model=service_model, service_image_model_label=operation_settings.pollinations_free_image_model_label(service_model), service_free_quota_limit=quota['limit'], service_free_quota_used=quota['used'], service_free_quota_remaining=quota['remaining'], service_free_quota_date=quota['date'], updated_at=setting.updated_at)


def _invalidate_image_visual_identity_if_present(db: Session, character_id: str) -> None:
    setting = image_setting_repository.get_image_generation_setting(db, character_id)
    if setting is None:
        return
    if setting.visual_identity_source_hash is None:
        return
    setting.visual_identity_prompt = None
    setting.visual_identity_source_hash = None


def _service_image_quota_read(db: Session, character_id: str, *, workflows: CharacterImageSettingsWorkflows) -> dict[str, int | str]:
    quota_date = datetime.now(workflows.app_timezone).date()
    limit = settings.pollinations_service_free_images_per_user_day
    character = image_setting_repository.image_secret_character(db, character_id)
    used = workflows.count_service_image_quota_used(db, user_id=character.owner_id, quota_date=quota_date) if character is not None else 0
    return {'limit': limit, 'used': used, 'remaining': max(0, limit - used), 'date': quota_date.isoformat()}


def delete_image_seed(db: Session, user: CharacterOwner, character_id: str, *, workflows: CharacterImageSettingsWorkflows) -> schemas.AgentImageGenerationSettingRead:
    character = _get_owned_character(db, user, character_id)
    demo_lock.ensure_demo_user_mutable(user)
    setting = image_setting_repository.ensure_image_generation_setting(db, character.id)
    media_files.delete_media_url(setting.seed_image_url)
    setting.seed_image_url = None
    if setting.visual_identity_source_hash is not None:
        setting.visual_identity_prompt = None
        setting.visual_identity_source_hash = None
    image_setting_repository.save_setting(db, setting)
    return _image_generation_setting_read(db, setting, workflows=workflows)


def get_image_settings(db: Session, user: CharacterOwner, character_id: str, *, workflows: CharacterImageSettingsWorkflows) -> schemas.AgentImageGenerationSettingRead:
    character = _get_owned_character(db, user, character_id)
    return _image_generation_setting_read(db, image_setting_repository.ensure_image_generation_setting(db, character.id), workflows=workflows)


def update_image_settings(db: Session, user: CharacterOwner, character_id: str, data: schemas.AgentImageGenerationSettingUpdate, *, workflows: CharacterImageSettingsWorkflows) -> schemas.AgentImageGenerationSettingRead:
    character = _get_owned_character(db, user, character_id)
    demo_lock.ensure_demo_user_mutable(user)
    if data.visual_identity_prompt is not None:
        try:
            image_prompt_safety.ensure_safe_image_text(data.visual_identity_prompt)
        except image_prompt_safety.UnsafeImagePromptError as exc:
            raise UnsafeImagePromptError(str(exc)) from exc
    setting = image_setting_repository.ensure_image_generation_setting(db, character.id)
    requested_mode = data.image_key_mode
    effective_model = data.pollinations_image_model or setting.pollinations_image_model
    if data.pollinations_image_model is not None and data.pollinations_image_model not in USER_IMAGE_MODEL_OPTIONS:
        raise ImageSettingsInvalidError('사용자 이미지 모델은 Replicate 모델만 선택할 수 있습니다.')
    effective_mode = requested_mode or setting.image_key_mode
    if effective_mode == 'service':
        service_model = operation_settings.get_pollinations_free_image_model(db)
        if not workflows.service_image_available_for_model(service_model):
            raise ImageSettingsInvalidError('현재 Angmoo 무료 이미지가 준비되어 있지 않습니다.')
    if effective_mode == 'user':
        is_replicate = image_provider.is_replicate_model(effective_model)
        has_new_key = bool(((data.replicate_api_key if is_replicate else data.pollinations_api_key) or '').strip())
        has_saved_key = bool(setting.encrypted_replicate_api_token if is_replicate else setting.encrypted_pollinations_api_key)
        clearing_key = data.clear_replicate_api_key if is_replicate else data.clear_pollinations_api_key
        if not has_new_key and (not has_saved_key or clearing_key):
            provider_label = 'Replicate API token' if is_replicate else 'Pollinations API key'
            raise ImageSettingsInvalidError(f'내 key를 사용하려면 {provider_label}이 필요합니다.')
    setting = image_setting_service.update_image_generation_setting(db, setting, data)
    return _image_generation_setting_read(db, setting, workflows=workflows)


def upload_image_seed(db: Session, user: CharacterOwner, character_id: str, data: schemas.AgentImageSeedUpload, *, workflows: CharacterImageSettingsWorkflows) -> schemas.AgentImageGenerationSettingRead:
    character = _get_owned_character(db, user, character_id)
    demo_lock.ensure_demo_user_mutable(user)
    setting = image_setting_repository.ensure_image_generation_setting(db, character.id)
    try:
        seed_image_url = profile_media.save_seed_image(character_id=character.id, content_type=data.content_type, data_base64=data.data_base64)
    except profile_media.InvalidProfileMediaError as exc:
        raise InvalidProfileMediaError(str(exc)) from exc
    media_files.delete_media_url(setting.seed_image_url)
    setting.seed_image_url = seed_image_url
    if setting.visual_identity_source_hash is not None:
        setting.visual_identity_prompt = None
        setting.visual_identity_source_hash = None
    image_setting_repository.save_setting(db, setting)
    return _image_generation_setting_read(db, setting, workflows=workflows)
