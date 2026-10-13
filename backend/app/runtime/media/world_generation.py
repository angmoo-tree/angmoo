"""World-owned image inputs and reservations on the publication Session."""
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4
from sqlalchemy import select
from app.domains.characters.models import CharacterCardSource
from app.domains.world_characters.models import WorldCharacter
from app.domains.world_characters.service.configuration import configuration_for_actor
from app.domains.media.models_world_policy import WorldImagePolicy
from app.domains.media.generation_contracts import (GenerationRequest, EffectiveReference, ImagePreparationError,
    NovelOptions, ComfyOptions, ApiImageOptions, MODEL_CATALOG, compose_positive)
from app.domains.media.api_image_policy import validate_api_options
from app.domains.media.service import world_policy
from app.domains.identity.service import world_credentials
from app.domains.identity.service.environment import snapshot
from app.domains.social.models.image_intents import ImageGenerationAttempt, ImageIntent
from app.domains.social.models.posts import PostImageGenerationJob, Post
from app.runtime.world_credential_binding import capture
from app.domains.media.service.comfy_workflows import required_roles, freeze_comfy_request, select_comfy_workflow, validate_app_workflow, validate_base_url, partner_submission_target


def validate_settings(value, *, previous=None, active_profile=None, auto_enabled=False):
    from app.domains.media.schemas import WorldGenerationSettings
    parsed = WorldGenerationSettings.model_validate(value).model_dump()
    if parsed.get("legacy_reference") != (previous or {}).get("legacy_reference"):
        raise ImagePreparationError("generation_reference_changed")
    for key, profile in parsed["profiles"].items():
        model_key = key.rsplit(":", 1)[0] if key.endswith((":opus_free", ":allow_anlas")) else key
        if model_key not in MODEL_CATALOG and model_key != "comfyui:workflow":
            if profile == (previous or {}).get("profiles", {}).get(key):
                continue  # Retain an unsupported historical profile without executing it.
            raise ImagePreparationError("model_not_supported")
        if not isinstance(profile, dict) or not set(profile) <= {"options", "connection"}:
            raise ImagePreparationError("world_image_policy_invalid")
        provider = key.split(":", 1)[0]
        options = profile.get("options", {})
        typed = (NovelOptions if provider == "novelai" else ComfyOptions if provider == "comfyui" else ApiImageOptions).model_validate(options)
        if provider == "comfyui":
            validate_base_url(typed.base_url)
            old_options = (previous or {}).get("profiles", {}).get(key, {}).get("options")
            same_options = old_options is not None and ComfyOptions.model_validate(old_options).model_dump(exclude_none=True) == typed.model_dump(exclude_none=True)
            if not same_options or (auto_enabled and key == active_profile):
                partner_submission_target(typed.base_url, typed.partner_auth)
            for workflow in (typed.workflow, typed.text_workflow):
                if workflow is not None:
                    validate_app_workflow(workflow)
        parsed_options = typed.model_dump(exclude_none=True)
        profile["options"] = parsed_options
        connection = profile.get("connection")
        old = (previous or {}).get("profiles", {}).get(key, {})
        if connection is not None and connection != old.get("connection"):
            raise ImagePreparationError("generation_connection_unverified")
        if (provider == "comfyui" and parsed_options != old.get("options")) or (
            provider == "novelai" and parsed_options.get("mode") != old.get("options", {}).get("mode")
        ):
            profile.pop("connection", None)
        if provider in {"nanogpt", "openrouter"} and connection:
            validate_api_options(provider, connection.get("endpoint", {}), parsed_options)
    return parsed


def _reference(media, db, owner, actor, config, values, *, materialize=True):
    if not values.get("reference_enabled"):
        return EffectiveReference(False, reason="disabled")
    if values.get("reference_asset_id"):
        asset, _ = media.assets.read(db, owner_id=owner, asset_id=values["reference_asset_id"])
        if not reference_owned_by_actor(asset, actor, values):
            raise ImagePreparationError("generation_reference_changed")
        return EffectiveReference(True, "override", asset.id, asset.content_hash, revision=asset.revision)
    card = db.scalar(select(CharacterCardSource).where(CharacterCardSource.character_id == actor.character_id,
        CharacterCardSource.source_format == "png").order_by(CharacterCardSource.created_at.desc(), CharacterCardSource.id.desc()))
    if card:
        return media._reference_asset(db, owner, actor.character_id, "image/png", card.source_bytes,
            source="card", materialize=materialize, actor_id=actor.id)
    url = config.profile.avatar_url
    if url:
        prefix = media.settings.media_url_path.rstrip("/") + "/"
        if not url.startswith(prefix) or any(c in url for c in ("\\", "?", "#")):
            raise ImagePreparationError("profile_reference_file_invalid")
        relative = Path(url[len(prefix):]); root = media.settings.media_root_path.resolve(); path = root / relative
        if relative.is_absolute() or ".." in relative.parts or path.is_symlink() or root not in path.resolve().parents or not path.is_file() or path.stat().st_size > 10 * 1024 * 1024:
            raise ImagePreparationError("profile_reference_file_invalid")
        from PIL import Image
        from io import BytesIO
        pixels = path.read_bytes()
        with Image.open(BytesIO(pixels)) as image:
            mime = Image.MIME.get(image.format)
        return media._reference_asset(db, owner, actor.character_id, mime, pixels, source="profile", materialize=materialize, actor_id=actor.id)
    return EffectiveReference(True, reason="source_missing")


def reference_owned_by_actor(asset, actor, values):
    if asset.scope_kind == "world_character" and asset.scope_id == actor.id:
        return True
    old = values.get("legacy_reference") or {}
    return (asset.scope_kind == "character" and asset.scope_id == actor.character_id == old.get("character_id")
        and asset.id == old.get("asset_id") and asset.revision == old.get("asset_revision")
        and asset.content_hash == old.get("asset_digest"))


def prepare_intent(media, db, owner, character_id, scene, scene_error, config):
    policy = db.get(WorldImagePolicy, config.world_character_id)
    if not policy or not policy.generation_enabled or (not scene_error and (not isinstance(scene, str) or not scene.strip())):
        return None
    try:
        actor = db.get(WorldCharacter, config.world_character_id)
        if actor is None or actor.character_id != character_id or actor.world_id != config.world_id:
            raise ImagePreparationError("world_configuration_snapshot_scope_invalid")
        binding = capture(db, owner_id=owner, world_id=actor.world_id, actor_id=actor.id, purpose="image")
        values = policy.generation_settings or {}
        profile = values.get("profiles", {}).get(f'{binding["provider"]}:{binding["model"]}', {})
        connection, options = profile.get("connection", {}), profile.get("options", {})
        provider, model = binding["provider"], binding["model"]
        if scene_error:
            raise ImagePreparationError(scene_error)
        # Opus-free never reads or materializes a private reference it cannot send.
        reference = EffectiveReference(False, reason="opus_free") if provider == "novelai" and options.get("mode", "opus_free") == "opus_free" else _reference(media, db, owner, actor, config, values)
        material, partner = world_credentials.resolve_image_keys(db, owner_id=owner, world_id=actor.world_id,
            world_character_id=actor.id, revision=binding["revision"])
        if not connection.get("ready"):
            raise ImagePreparationError("generation_connection_unverified")
        if provider == "comfyui":
            comfy = ComfyOptions.model_validate(options)
            if comfy.partner_auth and not partner:
                raise ImagePreparationError("comfy_partner_key_required")
            workflow = select_comfy_workflow(comfy, has_reference=bool(reference.asset_id))
            negative = values.get("negative") if "negative" in required_roles(workflow) else None
            options = comfy.model_dump(exclude_none=True)
        elif provider == "novelai":
            options = NovelOptions.model_validate(options).model_dump()
            if options["mode"] == "opus_free":
                reference = EffectiveReference(False, reason="opus_free")
                if not connection.get("opus_verified"):
                    raise ImagePreparationError("opus_benefit_unverified")
            negative = values.get("negative")
        else:
            options = ApiImageOptions.model_validate(options).model_dump(exclude_none=True)
            validate_api_options(provider, connection.get("endpoint", {}), options)
            negative = None
        positive = compose_positive(style=values.get("style", ""), appearance=values.get("appearance", ""), scene=scene)
        if provider == "novelai":
            media._require_novel_validation()
            from app.integrations.novelai_images import validate_t5_prompt
            validate_t5_prompt(positive)
            if negative:
                validate_t5_prompt(negative)
        request = GenerationRequest(provider, model, positive, negative, options, reference,
            connection.get("endpoint"), world_id=actor.world_id, world_character_id=actor.id,
            world_configuration_revision=config.revision, credential_binding=binding,
            world_image_policy_revision=policy.revision)
        return freeze_comfy_request(request), None, policy.revision, policy.generation_limit, None
    except Exception as exc:
        code = str(exc) if isinstance(exc, ImagePreparationError) else "generation_source_or_key_changed"
        return None, None, policy.revision, policy.generation_limit, code


def prepare_execution(media, db, job, intent, request):
    actor = db.get(WorldCharacter, request.world_character_id)
    policy = db.get(WorldImagePolicy, request.world_character_id, populate_existing=True)
    post = db.get(Post, job.post_id)
    if actor is None or actor.status != "active" or post.author_world_character_id != actor.id or actor.character_id != job.character_id:
        raise ImagePreparationError("generation_post_author_changed")
    binding = request.credential_binding
    prior = world_credentials.find_revision(db, owner_id=job.user_id, world_id=actor.world_id,
        world_character_id=actor.id, purpose="image", credential_id=binding["credential_id"], revision=binding["revision"])
    # Settings/connection verification govern future admission. This accepted
    # request already contains its immutable settings and authenticated key
    # revision; an explicit key revoke or actor removal still rejects it.
    if (prior.provider, prior.model) != (request.provider, request.model) or not policy:
        raise ImagePreparationError("generation_source_or_key_changed")
    material, partner = world_credentials.resolve_image_keys(db, owner_id=job.user_id, world_id=actor.world_id,
        world_character_id=actor.id, revision=binding["revision"])
    reference = None
    if request.reference.asset_id:
        asset, reference = media.assets.read(db, owner_id=job.user_id, asset_id=request.reference.asset_id, digest=request.reference.digest)
        if not reference_owned_by_actor(asset, actor, policy.generation_settings) or asset.revision != request.reference.revision:
            raise ImagePreparationError("generation_reference_changed")
    if request.provider == "comfyui" and request.options.get("partner_auth") and not partner:
        raise ImagePreparationError("comfy_partner_key_required")
    return material.reveal() if material else None, partner, reference


def reserve_attempt(media, db, *, job_id, owner_id, character_id, character_limit, quota_day):
    job = db.get(PostImageGenerationJob, job_id)
    intent = db.get(ImageIntent, job.intent_id)
    value = json.loads(intent.request_json)
    binding = value.get("credential_binding")
    if not binding:
        from app.domains.social.service.generation_usage import reserve_attempt as legacy_reserve
        if value.get("world_character_id"):
            raise ImagePreparationError("generation_binding_unproven")
        return legacy_reserve(db, job_id=job_id, owner_id=owner_id, character_id=character_id,
            character_limit=character_limit, quota_day=quota_day)
    identity = uuid4().hex
    world_policy.reserve(db, world_character_id=binding["actor_id"], purpose="image", request_key=identity,
        lane="sns", credential_revision=binding["revision"], now=datetime.now(UTC), timezone=snapshot(db, owner_id).timezone,
        admitted=True)
    row = ImageGenerationAttempt(id=identity, job_id=job_id, owner_id=owner_id, character_id=character_id,
        quota_day=quota_day, status="reserved", created_at=datetime.now(UTC))
    db.add(row); db.flush()
    return row
