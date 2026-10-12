"""World authorization and Identity writes share the management Session."""
from app.domains.identity.service import world_credentials


def read(service, *, world_id, world_character_id, user, purpose):
    role, _ = service.authorize_credentials(world_id=world_id, world_character_id=world_character_id, user=user, basic=purpose in {"sns", "image"})
    row = world_credentials.find(service.db, owner_id=user.id, world_id=world_id,
        world_character_id=world_character_id, purpose=purpose)
    result = world_credentials.metadata(row, purpose=purpose)
    if purpose == "image":
        from app.domains.identity.service import world_image_credentials
        from app.domains.media.models_world_policy import WorldImagePolicy
        key = world_image_credentials.metadata(service.db, owner_id=user.id, world_id=world_id,
            world_character_id=world_character_id, provider=result.provider)
        policy = service.db.get(WorldImagePolicy, role.id)
        result = result.model_copy(update={"key_revision": key.key_revision, "configuration_revision": policy.revision if policy else 0})
    if purpose == "sns":
        result = result.model_copy(update={"configuration_revision": role.version})
    if purpose == "consolidation":
        from app.domains.memory.service.subject_profiles import read as read_profile
        from app.domains.memory.contracts.scope import MemoryScope
        from app.runtime.memory.composition import memory_repository
        profile = read_profile(service.db, scope=MemoryScope(user.id, world_id, world_character_id), repository=memory_repository(service.db))
        result = result.model_copy(update={"configuration_revision": profile.version if profile else 0,
            **({"model": profile.model_id, "thinking_level": profile.thinking_level} if profile and row is None else {})})
    return result


def write(service, *, world_id, world_character_id, user, purpose, data, remove=False):
    try:
        from app.domains.identity.service.environment import lock_environment_admission
        lock_environment_admission(service.db, user.id)
        role, _ = service.authorize_credentials(world_id=world_id, world_character_id=world_character_id, user=user, mutation=True, basic=purpose in {"sns", "image"})
        scope = dict(owner_id=user.id, world_id=world_id, world_character_id=world_character_id, purpose=purpose)
        if purpose == "image":
            from app.domains.media.models_world_policy import WorldImagePolicy
            from app.domains.identity.service import world_image_credentials
            policy = service.db.get(WorldImagePolicy, role.id)
            if data.expected_configuration_revision != (policy.revision if policy else 0):
                raise ValueError("world_image_policy_revision_conflict")
            before = world_credentials.find(service.db, **scope)
            selected_provider = before.provider if before else None
            if not remove and data.provider == "comfyui" and not data.clear_partner_key:
                from app.domains.media.generation_contracts import ComfyOptions
                from app.domains.media.service.comfy_workflows import partner_submission_target
                profile=((policy.generation_settings if policy else {}) or {}).get("profiles",{}).get(f"comfyui:{data.model}")
                if profile and (before is None or before.provider != data.provider or before.model != data.model
                    or (data.partner_api_key is not None and data.partner_api_key.get_secret_value().strip())):
                    typed=ComfyOptions.model_validate(profile.get("options",{}))
                    partner_submission_target(typed.base_url,typed.partner_auth)
            result = world_image_credentials.delete_provider(service.db, owner_id=user.id, world_id=world_id,
                world_character_id=world_character_id, data=data) if remove else world_credentials.save(service.db, **scope, data=data)
            if policy is not None and (not remove or (data.provider or selected_provider) == selected_provider):
                profiles = (policy.generation_settings or {}).get("profiles", {})
                policy.generation_settings = {**(policy.generation_settings or {}), "profiles": {
                    key: {**value, "connection": None} for key, value in profiles.items()
                }}
                policy.generation_enabled = False
                policy.revision += 1
            result = result.model_copy(update={"configuration_revision": policy.revision if policy else 0})
        else:
            result = world_credentials.delete(service.db, **scope, expected_revision=data.expected_revision) if remove else world_credentials.save(service.db, **scope, data=data)
        if purpose == "sns" and not remove:
            from app.domains.world_characters.configuration_models import WorldCharacterConfiguration
            configuration = service.db.get(WorldCharacterConfiguration, role.id)
            if configuration is None:
                raise ValueError("world_configuration_missing")
            # The purpose binding owns the execution model. Key/model rotation
            # must not mutate the actor configuration captured by an admitted job.
            if role.version != data.expected_configuration_revision:
                raise ValueError("world_character_version_conflict")
            result = result.model_copy(update={"configuration_revision": role.version})
        if purpose == "consolidation" and not remove:
            from app.domains.memory.service.subject_profiles import save as save_profile
            from app.domains.memory.contracts.scope import MemoryScope
            from app.runtime.memory.composition import memory_repository
            revision = save_profile(service.db, scope=MemoryScope(user.id, world_id, world_character_id),
                repository=memory_repository(service.db), model=data.model, thinking=data.thinking_level,
                expected_revision=data.expected_configuration_revision)
            result = result.model_copy(update={"configuration_revision": revision})
        elif purpose == "consolidation":
            from app.domains.memory.service.subject_profiles import read as read_profile
            from app.domains.memory.contracts.scope import MemoryScope
            from app.runtime.memory.composition import memory_repository
            profile = read_profile(service.db, scope=MemoryScope(user.id, world_id, world_character_id), repository=memory_repository(service.db))
            result = result.model_copy(update={"configuration_revision": profile.version if profile else 0})
        service.db.commit()
        return result
    except BaseException:
        service.db.rollback()
        raise


def read_image_provider(service, *, world_id, world_character_id, user, provider):
    from app.domains.identity.service import world_image_credentials
    service.authorize_credentials(world_id=world_id, world_character_id=world_character_id, user=user, basic=True)
    return world_image_credentials.metadata(service.db, owner_id=user.id, world_id=world_id,
        world_character_id=world_character_id, provider=provider)
