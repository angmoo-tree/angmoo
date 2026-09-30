"""Character image configuration, saved profiles and revision conflict rules."""
import json
from sqlalchemy import update
from app.domains.characters.repository.image_settings import ensure_image_generation_setting
from app.domains.characters.service.access import _get_owned_character
from app.domains.identity.service import media_credentials
from app.domains.identity.contracts import CredentialPurpose
from app.domains.identity.service.demo_access import ensure_demo_user_mutable
from app.domains.media.contracts import MODEL_CATALOG, NovelOptions, ApiImageOptions, ComfyOptions, ImagePreparationError, initial_reference


def profile_key(provider, model, options):
    return f"{provider}:{model}:{options.get('mode', '')}"


def read_settings(db, user, character_id, *, limits):
    _get_owned_character(db, user, character_id)
    row = ensure_image_generation_setting(db, character_id, commit=False)
    profiles = json.loads(row.generation_profiles_json)
    active = next((p for p in profiles.values() if p.get("active")), {})
    credential = media_credentials.find_credential(db, owner_id=user.id, character_id=character_id,
        provider=row.generation_provider or "novelai", purpose=CredentialPurpose.USER_IMAGE)
    return {"character_id": character_id, "revision": row.generation_revision,
        "provider": row.generation_provider, "model": row.generation_model,
        "auto_enabled": row.generation_auto_enabled, "daily_limit": row.generation_daily_limit,
        "installation_daily_limit": limits.read(db)["daily_limit"], "appearance": row.appearance_prompt,
        "installation_revision": limits.read(db)["revision"],
        "style": row.style_prompt, "negative": row.negative_prompt,
        "reference_asset_id": row.reference_asset_id,
        "profiles": profiles, "active_profile": active,
        "has_api_key": bool(credential and credential.enabled),
        "credential_revision": credential.revision if credential else 0}


def write_settings(db, user, character_id, data, *, assets, limits, validated_connection=None):
    _get_owned_character(db, user, character_id)
    ensure_demo_user_mutable(user)
    row = ensure_image_generation_setting(db, character_id, commit=False)
    if data.expected_revision not in (row.generation_revision, 0 if row.generation_provider is None else -1):
        raise ImagePreparationError("settings_revision_conflict")
    provider, model = data.provider, data.model
    if provider != "comfyui" and f"{provider}:{model}" not in MODEL_CATALOG:
        raise ImagePreparationError("model_not_supported")
    option_type = NovelOptions if provider == "novelai" else ComfyOptions if provider == "comfyui" else ApiImageOptions
    options = option_type.model_validate(data.options).model_dump(exclude_none=True)
    if data.reference_asset_id:
        asset = assets.owned(db, owner_id=user.id, asset_id=data.reference_asset_id, scope_kind="character", scope_id=character_id)
        if asset.state == "draft":
            assets.attach(db, owner_id=user.id, asset_id=asset.id, scope_kind="character", scope_id=character_id)
    profiles = json.loads(row.generation_profiles_json)
    key = profile_key(provider, model, options)
    previous = profiles.get(key)
    connection = validated_connection or (previous or {}).get("connection")
    if provider == "comfyui" and previous and options != previous.get("options"):
        connection = validated_connection
    if data.api_key is not None or data.clear_api_key:
        media_credentials.save_credential(db, owner_id=user.id, character_id=character_id,
            provider=provider, purpose=CredentialPurpose.USER_IMAGE,
            secret=data.api_key.get_secret_value() if data.api_key is not None else None)
        connection = validated_connection
    credential = media_credentials.find_credential(db, owner_id=user.id, character_id=character_id, provider=provider, purpose=CredentialPurpose.USER_IMAGE)
    reference_validated = bool(connection and connection.get("reference_supported"))
    initialized = bool(previous and previous.get("reference_initialized", True))
    preferred = data.reference_enabled if data.reference_enabled is not None else (previous.get("reference_enabled") if initialized else initial_reference(provider, model, mode=options.get("mode", ""), reference_validated=reference_validated))
    if provider != "comfyui" and not MODEL_CATALOG[f"{provider}:{model}"][2] and preferred:
        raise ImagePreparationError("reference_not_supported")
    forced_off = provider == "novelai" and options["mode"] == "opus_free"
    if provider == "comfyui" and preferred and not reference_validated:
        raise ImagePreparationError("reference_workflow_unverified")
    if data.installation_daily_limit is not None:
        limits.write(db, data.installation_daily_limit, expected_revision=data.installation_expected_revision)
    if data.auto_enabled:
        if not data.daily_limit or not limits.read(db)["daily_limit"]:
            raise ImagePreparationError("generation_limits_required")
        if provider != "comfyui" and not (credential and credential.enabled):
            raise ImagePreparationError("generation_key_required")
        if not connection or not connection.get("ready"):
            raise ImagePreparationError("generation_connection_unverified")
        if provider == "novelai" and forced_off and not connection.get("opus_verified"):
            raise ImagePreparationError("opus_benefit_unverified")
    for profile in profiles.values():
        profile["active"] = False
    profiles[key] = {"active": True, "options": options, "reference_enabled": preferred,
        "reference_initialized": initialized or data.reference_enabled is not None or provider != "comfyui" or reference_validated,
        "reference_asset_id": data.reference_asset_id,
        "reference_effective": preferred and not forced_off, "reference_reason": "opus_free" if forced_off else None,
        "connection": connection, "credential_revision": credential.revision if credential else None}
    from app.domains.characters.models import AgentImageGenerationSetting
    expected = row.generation_revision
    result = db.execute(update(AgentImageGenerationSetting).where(
        AgentImageGenerationSetting.character_id == character_id,
        AgentImageGenerationSetting.generation_revision == expected).values(
        generation_provider=provider, generation_model=model, generation_profiles_json=json.dumps(profiles),
        generation_revision=expected + 1, generation_auto_enabled=data.auto_enabled,
        generation_daily_limit=data.daily_limit, appearance_prompt=data.appearance, style_prompt=data.style,
        negative_prompt=data.negative, reference_asset_id=data.reference_asset_id))
    if result.rowcount != 1:
        raise ImagePreparationError("settings_revision_conflict")
    db.flush()
    db.expire(row)
    return read_settings(db, user, character_id, limits=limits)
