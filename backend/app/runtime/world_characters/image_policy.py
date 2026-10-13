from datetime import UTC, datetime
from app.domains.media.models_world_policy import WorldImagePolicy
from app.domains.media.service.world_policy import patch, usage
from app.domains.media.generation_contracts import ImagePreparationError
from app.domains.identity.service.world_credentials import resolve
from app.domains.identity.service.environment import snapshot
from app.core.calendar import local_period


def read(service, *, world_id, world_character_id, user):
    service.authorize_credentials(world_id=world_id, world_character_id=world_character_id, user=user, basic=True)
    row = service.db.get(WorldImagePolicy, world_character_id)
    if row is None:
        raise ImagePreparationError("world_image_policy_missing")
    now, timezone = datetime.now(UTC), snapshot(service.db, user.id).timezone
    return {"world_id": world_id, "world_character_id": world_character_id,
        **{key: getattr(row, key) for key in ("revision", "generation_limit", "vision_limit", "generation_enabled", "vision_enabled", "generation_settings")},
        "generation_usage": usage(service.db, world_character_id=world_character_id, purpose="image", now=now, timezone=timezone),
        "vision_usage": usage(service.db, world_character_id=world_character_id, purpose="vision", now=now, timezone=timezone),
        "timezone": timezone, "reset_at": local_period(now, timezone)[1].isoformat()}


def write(service, *, world_id, world_character_id, user, data):
    try:
        changes = data.model_dump(exclude_unset=True, exclude={"expected_revision"})
        from app.domains.identity.service.environment import lock_environment_admission
        lock_environment_admission(service.db, user.id)
        actor, _ = service.authorize_credentials(world_id=world_id, world_character_id=world_character_id, user=user, mutation=True,
            basic=not bool({"vision_limit", "vision_enabled"} & changes.keys()))
        if "generation_settings" in changes:
            from app.runtime.media.world_generation import validate_settings
            from app.runtime.media.binding import current
            old = service.db.get(WorldImagePolicy, world_character_id)
            from app.domains.identity.service.world_credentials import find as selected_image
            selected=selected_image(service.db,owner_id=user.id,world_id=world_id,world_character_id=world_character_id,purpose="image")
            changes["generation_settings"] = validate_settings(changes["generation_settings"], previous=old.generation_settings if old else {},
                active_profile=f"{selected.provider}:{selected.model}" if selected else None,
                auto_enabled=changes.get("generation_enabled",old.generation_enabled if old else False))
            asset_id = changes["generation_settings"].get("reference_asset_id")
            if asset_id:
                media = current()
                if media is None:
                    raise ImagePreparationError("image_runtime_unavailable")
                from app.runtime.media.world_generation import reference_owned_by_actor
                asset, _ = media.assets.read(service.db, owner_id=user.id, asset_id=asset_id)
                if not reference_owned_by_actor(asset, actor, changes["generation_settings"]):
                    raise ImagePreparationError("generation_reference_changed")
        def require_key(purpose):
            if purpose == "image":
                from app.domains.identity.service.world_credentials import resolve_image_keys
                from app.runtime.world_credential_binding import capture_image_settings
                binding = capture_image_settings(service, user=user, world_id=world_id, actor_id=world_character_id)
                old_policy = service.db.get(WorldImagePolicy, world_character_id)
                values = changes.get("generation_settings", old_policy.generation_settings)
                profile = values.get("profiles", {}).get(f'{binding["provider"]}:{binding["model"]}', {})
                connection = profile.get("connection") or {}
                if binding["provider"] == "comfyui":
                    from app.domains.media.generation_contracts import ComfyOptions
                    from app.domains.media.service.comfy_workflows import partner_submission_target
                    typed=ComfyOptions.model_validate(profile.get("options",{}))
                    partner_submission_target(typed.base_url,typed.partner_auth)
                if not connection.get("ready") or (binding["provider"] == "novelai" and profile.get("options", {}).get("mode", "opus_free") == "opus_free" and not connection.get("opus_verified")):
                    raise ImagePreparationError("generation_connection_unverified")
                return resolve_image_keys(service.db, owner_id=user.id, world_id=world_id, world_character_id=world_character_id)
            return resolve(service.db, owner_id=user.id, world_id=world_id, world_character_id=world_character_id, purpose=purpose)
        patch(service.db, world_character_id=world_character_id, expected_revision=data.expected_revision,
            changes=changes, require_key=require_key)
        service.db.commit()
        return read(service, world_id=world_id, world_character_id=world_character_id, user=user)
    except BaseException:
        service.db.rollback()
        raise


async def check(service, *, world_id, world_character_id, user, data):
    """Explicit user check only. Normal GET/save never contacts a provider."""
    from app.runtime.media.binding import current
    from app.runtime.world_credential_binding import capture_image_settings
    from app.domains.identity.service.world_credentials import resolve_image_keys
    from app.runtime.media.world_generation import validate_settings
    from app.domains.media.generation_contracts import NovelOptions, ComfyOptions, ApiImageOptions
    from app.domains.media.api_image_policy import validate_api_options, endpoint_parameters
    from app.integrations.comfy_images import ComfyImageClient
    media = current()
    if media is None:
        raise ImagePreparationError("image_runtime_unavailable")
    actor, _ = service.authorize_credentials(world_id=world_id, world_character_id=world_character_id, user=user, mutation=True,
        basic=not bool({"vision_limit", "vision_enabled"} & data.model_fields_set))
    row = service.db.get(WorldImagePolicy, world_character_id)
    if row is None or row.revision != data.expected_revision:
        raise ImagePreparationError("world_image_policy_revision_conflict")
    binding = capture_image_settings(service, user=user, world_id=world_id, actor_id=world_character_id)
    values = validate_settings(data.generation_settings if data.generation_settings is not None else row.generation_settings,
        previous=row.generation_settings)
    key = f'{binding["provider"]}:{binding["model"]}'
    options = values.get("profiles", {}).get(key, {}).get("options", {})
    material, partner = resolve_image_keys(service.db, owner_id=user.id, world_id=world_id,
        world_character_id=world_character_id, revision=binding["revision"])
    secret = material.reveal() if material else None
    if binding["provider"] == "comfyui":
        from app.runtime.media.world_generation import _reference
        from app.domains.world_characters.service.configuration import effective_configuration
        reference = _reference(media, service.db, user.id, actor,
            effective_configuration(service.db, world_character_id=actor.id), values, materialize=False)
        has_reference = bool(reference.asset_id) or reference.source != "none"
    service.db.rollback()
    provider = binding["provider"]
    if provider == "comfyui":
        typed = ComfyOptions.model_validate(options)
        if typed.partner_auth and not partner:
            raise ImagePreparationError("comfy_partner_key_required")
        connection = await ComfyImageClient(typed.base_url).validate(typed, key=secret, has_reference=has_reference)
    elif provider == "novelai":
        typed = NovelOptions.model_validate(options)
        media._require_novel_validation()
        connection = await media.clients[provider].subscription(secret)
        if typed.mode == "opus_free" and not connection.get("opus_verified"):
            raise ImagePreparationError("opus_benefit_unverified")
        connection.update(ready=True, reference_supported=typed.mode != "opus_free")
    else:
        typed = ApiImageOptions.model_validate(options)
        endpoint = await media.clients[provider].discover(binding["model"])
        validate_api_options(provider, endpoint, typed.model_dump(exclude_none=True))
        connection = {"ready": True, "credential_validation": "not_verified", "endpoint": endpoint,
            "reference_supported": endpoint_parameters(provider, endpoint).get("input_references", {}).get("max", 0) >= 1}
    service.authorize_credentials(world_id=world_id, world_character_id=world_character_id, user=user, mutation=True,
        basic=not bool({"vision_limit", "vision_enabled"} & data.model_fields_set))
    if capture_image_settings(service, user=user, world_id=world_id, actor_id=world_character_id) != binding:
        raise ImagePreparationError("generation_source_or_key_changed")
    connection["checked_at"] = datetime.now(UTC).isoformat()
    values.setdefault("profiles", {})[key] = {"options": typed.model_dump(exclude_none=True), "connection": connection}
    changes = data.model_dump(exclude_unset=True, exclude={"expected_revision"})
    changes["generation_settings"] = values
    try:
        patch(service.db, world_character_id=world_character_id, expected_revision=data.expected_revision,
            changes=changes, require_key=lambda purpose: resolve_image_keys(service.db, owner_id=user.id,
                world_id=world_id, world_character_id=world_character_id) if purpose == "image" else resolve(service.db,
                owner_id=user.id, world_id=world_id, world_character_id=world_character_id, purpose=purpose))
        service.db.commit()
        return read(service, world_id=world_id, world_character_id=world_character_id, user=user)
    except BaseException:
        service.db.rollback()
        raise
