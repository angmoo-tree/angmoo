"""Concrete media composition in the existing backend; no additional server."""
import json
import hashlib
import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from PIL import Image
from sqlalchemy import select

from app.domains.characters.models import Character, CharacterCardSource, AgentImageGenerationSetting
from app.domains.chat.models import MessageThread
from app.domains.identity.exceptions import CredentialResolutionError
from app.domains.identity.models_media import MediaCredential
from app.domains.identity.contracts import CredentialPurpose
from app.domains.identity.service import media_credentials
from app.domains.media.generation_contracts import EffectiveReference, GenerationRequest, ImagePreparationError, ComfyOptions, select_comfy_workflow, MODEL_CATALOG
from app.domains.media.contracts import InvalidProfileMediaError
from app.domains.media.service.assets import AssetService, prepare_asset_image
from app.domains.media.models import MediaAsset
from app.domains.media.service.interpretation import InterpretationService
from app.domains.routines.service.tick_schedule import APP_TIMEZONE
from app.domains.social.service.image_intent_generation import GenerationWorker, admit, source_revision
from app.domains.worlds.models import World
from app.integrations.comfy_images import ComfyImageClient
from app.integrations.image_api import ImageApiClient
from app.domains.media.api_image_policy import endpoint_parameters, validate_api_options
from app.integrations.llm.image_interpretation import GeminiImageInterpreter
from app.integrations.novelai_images import NovelImageClient, validate_t5_prompt
from app.runtime.media import binding


def quota_day(at):
    return (at if at.tzinfo else at.replace(tzinfo=timezone.utc)).astimezone(APP_TIMEZONE).date().isoformat()


def authorize_scope(db, owner_id, kind, scope_id):
    if kind == "character":
        character = db.get(Character, scope_id)
        valid = character is not None and character.owner_id == owner_id and character.deleted_at is None
    elif kind == "world":
        world = db.get(World, scope_id)
        valid = world is not None and world.owner_user_id == owner_id and world.status != "deleted"
    elif kind == "thread":
        thread = db.get(MessageThread, scope_id)
        valid = thread is not None and thread.requester_id == owner_id and thread.deleted_at is None and thread.world_scope_status == "resolved"
        if valid:
            authorize_scope(db, owner_id, "world", thread.world_id)
    else:
        valid = False
    if not valid:
        raise InvalidProfileMediaError("asset_scope_forbidden")


@dataclass(repr=False)
class PreparedExecution:
    request: GenerationRequest
    key: str | None
    reference: bytes | None
    receipt: str | None
    partner_key: str | None = None


class MediaRuntime:
    def __init__(self, sessions, settings, *, assets=None, interpreter=None, clients=None):
        self.sessions, self.settings = sessions, settings
        self.limits = InstallationGenerationLimits()
        # Only explicitly public subdirectories are mounted by public_media.py.
        # Backups must include this private directory alongside SQLite and its secret.
        root = settings.media_root_path / "private-image-assets"
        self.assets = assets or AssetService(root, authorize_scope)
        self.clients = clients or {"novelai": NovelImageClient(), "nanogpt": ImageApiClient("nanogpt"), "openrouter": ImageApiClient("openrouter")}
        self.interpretation = InterpretationService(sessions, self.assets, interpreter or GeminiImageInterpreter(), quota_day=quota_day)
        self.worker = GenerationWorker(sessions, self.assets, self, spool=root / "received-results")
        self._maintenance_task = None

    def read_generation(self, db, user, character_id):
        authorize_scope(db, user.id, "character", character_id)
        from app.domains.characters.service.generation_settings import read_settings
        return self._generation_view(db, user, character_id, read_settings(db, user, character_id, limits=self.limits))

    def write_generation(self, db, user, character_id, data, *, validated_connection=None):
        authorize_scope(db, user.id, "character", character_id)
        from app.domains.characters.service.generation_settings import write_settings
        if data.provider == "novelai" and data.auto_enabled:
            self._require_novel_validation()
            prefix = ", ".join(value.strip() for value in (data.style, data.appearance) if value.strip())
            if prefix:
                validate_t5_prompt(prefix)
            if data.negative:
                validate_t5_prompt(data.negative)
        saved = write_settings(db, user, character_id, data, assets=self.assets, limits=self.limits, validated_connection=validated_connection)
        return self._generation_view(db, user, character_id, saved)

    def _require_novel_validation(self):
        status = self._novel_validation()
        if not status.get("generation_available", False):
            raise ImagePreparationError("novelai_tokenizer_unavailable")

    def _novel_validation(self):
        return (self.clients.get("novelai") or NovelImageClient()).prompt_validation()

    def _generation_view(self, db, user, character_id, saved):
        profile = saved["active_profile"]
        preferred = bool(profile.get("reference_enabled"))
        effective = bool(profile.get("reference_effective"))
        options = profile.get("options", {})
        forced = saved["provider"] == "novelai" and options.get("mode") == "opus_free"
        unsupported = saved["provider"] in {"nanogpt", "openrouter"} and not MODEL_CATALOG.get(f"{saved['provider']}:{saved['model']}", (None, None, False))[2]
        status, reason = ("forced_off", "opus_free") if forced else ("forced_off", "reference_not_supported") if unsupported else ("off", "user_disabled") if not preferred else ("missing", "source_missing")
        reference = EffectiveReference(preferred)
        if effective and not forced and not unsupported:
            try:
                reference = self._reference(db, user.id, db.get(Character, character_id),
                    db.get(AgentImageGenerationSetting, character_id), True, materialize=False)
                if reference.source != "none":
                    status, reason = "available", None
            except (ImagePreparationError, InvalidProfileMediaError, OSError, ValueError):
                status, reason = "invalid", "reference_source_invalid"
        has_reference = status == "available"
        path = "reference" if has_reference else "text"
        if saved["provider"] == "comfyui":
            try:
                workflow = select_comfy_workflow(ComfyOptions.model_validate(options), has_reference=has_reference)
                path = "reference" if has_reference and "reference" in workflow.bindings else "text"
            except (ImagePreparationError, ValueError):
                path = "unavailable"
                reason = "comfy_reference_or_text_path_required"
        if status == "invalid":
            path = "unavailable"
        if not saved["provider"]:
            path = "unconfigured"
        validation = self._novel_validation() if saved["provider"] == "novelai" else None
        return {**saved, "reference_state": {"preferred": preferred, "applied": has_reference,
            "source": reference.source, "status": status, "reason": reason, "generation_path": path,
            "scene_only": path == "text" and not saved["appearance"].strip() and not saved["style"].strip()},
            "prompt_validation": validation,
            "effective_auto_enabled": saved["auto_enabled"] and (validation is None or validation["generation_available"])}

    def usage(self, db, owner_id):
        from app.domains.social.service.generation_usage import read_usage
        from app.domains.media.service.interpretation import read_interpretation_usage
        from app.domains.identity.service.environment import accounting_period
        day = accounting_period(db, owner_id, "day").key
        return {**read_usage(db, day), **read_interpretation_usage(db, owner_id, day)}

    @staticmethod
    def owns_post(db, owner_id, post):
        character = db.get(Character, post.author_character_id) if post.author_character_id else None
        return bool(character and character.owner_id == owner_id and not character.deleted_at)

    @staticmethod
    def authorize_post_world(db, owner_id, world_id, post_id):
        from app.domains.social.models.posts import Post
        authorize_scope(db, owner_id, "world", world_id)
        post = db.get(Post, post_id)
        if post is None or post.deleted_at or post.world_id != world_id:
            raise ImagePreparationError("image_post_world_mismatch")

    def catalog(self):
        from app.domains.media.generation_contracts import MODEL_CATALOG
        from app.integrations import image_api
        source = json.loads((Path(image_api.__file__).with_name("image_catalog.json")).read_text("utf-8"))
        models = []
        for key, (provider, model, reference) in MODEL_CATALOG.items():
            entry = source.get("models", {}).get(key, {})
            endpoints = entry.get("payload", {}).get("endpoints", [])
            endpoint = endpoints[0] if endpoints else None
            models.append({"provider": provider, "id": model, "reference_supported": reference,
                "parameters": endpoint_parameters(provider, endpoint) if endpoint else {},
                "pricing": endpoint.get("pricing") if endpoint else None,
                "availability": "local_validation_unavailable" if provider == "novelai" and not self._novel_validation()["generation_available"] else "requires_connection_check",
                "prompt_validation": self._novel_validation() if provider == "novelai" else None,
                "negative_supported": provider == "novelai"})
        return {"models": models, "captured_at": source.get("captured_at"), "quota_timezone": str(APP_TIMEZONE),
            "max_images": 1, "upload_limit_bytes": 10 * 1024 * 1024}

    async def start(self):
        if self._maintenance_task is not None:
            return
        binding.register(self)
        with self.sessions() as db:
            self.assets.expire_drafts(db, datetime.now(timezone.utc))
        self.interpretation.recover_elapsed()
        await self.worker.start()
        self._maintenance_task = asyncio.create_task(self._maintain())

    async def _maintain(self):
        while True:
            await asyncio.sleep(60)
            try:
                with self.sessions() as db:
                    self.assets.expire_drafts(db, datetime.now(timezone.utc))
                self.interpretation.recover_elapsed()
            except Exception as exc:
                logging.getLogger(__name__).warning("image_maintenance_failed type=%s", type(exc).__name__)

    async def stop(self):
        task, self._maintenance_task = self._maintenance_task, None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        await self.worker.stop()
        await self.interpretation.close()
        binding.unregister(self)

    def _reference(self, db, owner_id, character, setting, preferred, *, materialize=True):
        # Forced OFF does not even inspect card/profile files.
        if not preferred:
            return EffectiveReference(False, reason="disabled")
        if setting.reference_asset_id:
            asset, _ = self.assets.read(db, owner_id=owner_id, asset_id=setting.reference_asset_id)
            if asset.scope_kind != "character" or asset.scope_id != character.id:
                raise ImagePreparationError("reference_character_scope_mismatch")
            return EffectiveReference(True, "override", asset.id, asset.content_hash, revision=asset.revision)
        card = db.scalar(select(CharacterCardSource).where(CharacterCardSource.owner_id == owner_id,
            CharacterCardSource.character_id == character.id, CharacterCardSource.source_format == "png").order_by(CharacterCardSource.created_at.desc()))
        if card is not None:
            reference = self._reference_asset(db, owner_id, character.id, "image/png", card.source_bytes,
                source="card", materialize=materialize)
            if materialize:
                setting.card_asset_id = reference.asset_id
            return reference
        if character.avatar_url:
            prefix = getattr(self.settings, "media_url_path", "/media").rstrip("/") + "/"
            url = character.avatar_url
            if not url.startswith(prefix) or "\\" in url or "?" in url or "#" in url:
                raise ImagePreparationError("profile_reference_file_invalid")
            relative = Path(url[len(prefix):])
            if relative.is_absolute() or ".." in relative.parts:
                raise ImagePreparationError("profile_reference_file_invalid")
            root = self.settings.media_root_path.resolve()
            path = root / relative
            if path.is_symlink() or root not in path.resolve().parents or not path.is_file():
                raise ImagePreparationError("profile_reference_file_invalid")
            if path.stat().st_size > 10 * 1024 * 1024:
                raise ImagePreparationError("profile_reference_file_invalid")
            content = path.read_bytes()
            with Image.open(BytesIO(content)) as image:
                mime = Image.MIME.get(image.format)
            return self._reference_asset(db, owner_id, character.id, mime, content,
                source="profile", materialize=materialize)
        return EffectiveReference(True, reason="source_missing")

    def _reference_asset(self, db, owner_id, character_id, mime, content, *, source, materialize):
        prepared = prepare_asset_image(mime, content, max_bytes=10 * 1024 * 1024)
        pixels = prepared.content
        digest = hashlib.sha256(pixels).hexdigest()
        row = db.scalar(select(MediaAsset).where(MediaAsset.owner_id == owner_id, MediaAsset.scope_kind == "character",
            MediaAsset.scope_id == character_id, MediaAsset.state == "ready", MediaAsset.content_hash == digest))
        if row:
            self.assets.read(db, owner_id=owner_id, asset_id=row.id, digest=digest)
        elif materialize:
            row = self.assets.upload(db, owner_id=owner_id, scope_kind="character", scope_id=character_id,
                content_type=prepared.info.content_type, content=pixels, draft=False)
        return EffectiveReference(True, source, row.id if row else None, digest, revision=row.revision if row else None)

    def prepare_intent(self, db, owner_id, character_id, scene, scene_error):
        from app.domains.media.generation_contracts import compose_positive
        row = db.get(AgentImageGenerationSetting, character_id)
        if row is None or not row.generation_auto_enabled:
            return None
        if not scene_error and isinstance(scene, str) and not scene.strip():
            return None
        credential = None
        try:
            if scene_error:
                raise ImagePreparationError(scene_error)
            if not isinstance(scene, str):
                raise ImagePreparationError("scene_invalid")
            if row.generation_provider == "novelai":
                self._require_novel_validation()
            positive = compose_positive(style=row.style_prompt, appearance=row.appearance_prompt, scene=scene)
            character = db.get(Character, character_id)
            if character is None or character.owner_id != owner_id or character.deleted_at:
                raise ImagePreparationError("generation_character_forbidden")
            profile = next((p for p in json.loads(row.generation_profiles_json).values() if p.get("active")), None)
            if profile is None or not profile.get("connection", {}).get("ready"):
                raise ImagePreparationError("generation_connection_unverified")
            credential = media_credentials.find_credential(db, owner_id=owner_id, character_id=character_id,
                provider=row.generation_provider, purpose=CredentialPurpose.USER_IMAGE)
            if row.generation_provider != "comfyui" and (credential is None or not credential.enabled):
                raise ImagePreparationError("generation_key_required")
            if credential and credential.revision != profile.get("credential_revision"):
                raise ImagePreparationError("generation_key_changed")
            options = profile["options"]
            preferred = bool(profile.get("reference_effective"))
            reference = self._reference(db, owner_id, character, row, preferred)
            if row.generation_provider in {"nanogpt", "openrouter"}:
                endpoint = profile["connection"].get("endpoint")
                if not endpoint:
                    raise ImagePreparationError("model_capabilities_unverified")
                validate_api_options(row.generation_provider, endpoint, options)
                if reference.asset_id:
                    from app.integrations.image_api import prepare_api_reference
                    _, pixels = self.assets.read(db, owner_id=owner_id, asset_id=reference.asset_id, digest=reference.digest)
                    prepare_api_reference(endpoint, pixels)
            if row.generation_provider == "comfyui":
                comfy = ComfyOptions.model_validate(options)
                partner = media_credentials.find_credential(db, owner_id=owner_id, character_id=character_id,
                    provider="comfyui", purpose=CredentialPurpose.COMFY_PARTNER_IMAGE) if comfy.partner_auth else None
                if comfy.partner_auth and not (partner and partner.enabled):
                    raise ImagePreparationError("comfy_partner_key_required")
                if partner and partner.revision != profile.get("partner_credential_revision"):
                    raise ImagePreparationError("comfy_partner_key_changed")
                workflow = select_comfy_workflow(comfy, has_reference=bool(reference.asset_id))
                negative = row.negative_prompt if "negative" in workflow.bindings else None
                options = comfy.model_copy(update={"workflow": workflow, "text_workflow": None}).model_dump(exclude_none=True)
            else:
                negative = row.negative_prompt if row.generation_provider == "novelai" else None
            if row.generation_provider == "novelai":
                validate_t5_prompt(positive)
                if negative:
                    validate_t5_prompt(negative)
            request = GenerationRequest(row.generation_provider, row.generation_model, positive, negative,
                options, reference, profile["connection"].get("endpoint"),
                partner_credential_id=partner.id if row.generation_provider == "comfyui" and partner else None,
                partner_credential_revision=partner.revision if row.generation_provider == "comfyui" and partner else None)
            return request, credential, row.generation_revision, row.generation_daily_limit, None
        except Exception as exc:
            code = str(exc) if isinstance(exc, ImagePreparationError) else "reference_preparation_failed"
            return None, credential, row.generation_revision, row.generation_daily_limit, code

    def admit_post(self, db, *, post, owner_id, character_id, draft):
        from app.domains.identity.service.environment import accounting_period
        return admit(db, post=post, owner_id=owner_id, character_id=character_id,
            scene=draft._image_prompt, scene_error=draft._image_error, prepare=self.prepare_intent,
            quota_day=accounting_period(db, owner_id, "day").key)

    def authorize_job(self, db, job):
        from app.domains.social.models.posts import Post
        post = db.get(Post, job.post_id)
        if post is None:
            raise ImagePreparationError("image_job_not_found")
        authorize_scope(db, job.user_id, "character", job.character_id)
        authorize_scope(db, job.user_id, "world", post.world_id)

    @staticmethod
    def character_limit(db, character_id):
        row = db.get(AgentImageGenerationSetting, character_id)
        return row.generation_daily_limit if row else None

    @staticmethod
    def quota_day():
        return quota_day(datetime.now(timezone.utc))

    def prepare(self, db, job, intent):
        try:
            return self._prepare(db, job, intent)
        except (InvalidProfileMediaError, CredentialResolutionError) as exc:
            raise ImagePreparationError("generation_source_or_key_changed") from exc

    def _prepare(self, db, job, intent):
        from app.domains.social.models.posts import Post
        post = db.get(Post, job.post_id)
        if post is None or post.deleted_at or source_revision(post) != intent.source_revision:
            raise ImagePreparationError("post_source_changed")
        authorize_scope(db, job.user_id, "character", job.character_id)
        authorize_scope(db, job.user_id, "world", post.world_id)
        if post.author_character_id != job.character_id:
            raise ImagePreparationError("generation_post_author_changed")
        row = db.get(AgentImageGenerationSetting, job.character_id)
        if row is None or not row.generation_auto_enabled or row.generation_revision != intent.settings_revision:
            raise ImagePreparationError("generation_settings_changed")
        value = json.loads(intent.request_json)
        request = GenerationRequest(**{**value, "reference": EffectiveReference(**value["reference"])})
        if request.provider == "novelai":
            self._require_novel_validation()
            validate_t5_prompt(request.positive)
            if request.negative:
                validate_t5_prompt(request.negative)
        material = None
        if intent.credential_id:
            credential = db.get(MediaCredential, intent.credential_id)
            material = media_credentials.resolve_credential(credential, owner_id=job.user_id, character_id=job.character_id,
                provider=request.provider, purpose=CredentialPurpose.USER_IMAGE, revision=intent.credential_revision)
        elif request.provider != "comfyui":
            raise ImagePreparationError("generation_key_required")
        reference = None
        if request.reference.asset_id:
            asset, reference = self.assets.read(db, owner_id=job.user_id, asset_id=request.reference.asset_id, digest=request.reference.digest)
            if asset.scope_kind != "character" or asset.scope_id != job.character_id or asset.revision != request.reference.revision:
                raise ImagePreparationError("generation_reference_changed")
        partner_key = None
        if request.provider == "comfyui" and request.options.get("partner_auth"):
            partner = db.get(MediaCredential, request.partner_credential_id) if request.partner_credential_id else None
            partner_key = media_credentials.resolve_credential(partner, owner_id=job.user_id,
                character_id=job.character_id, provider="comfyui", purpose=CredentialPurpose.COMFY_PARTNER_IMAGE,
                revision=request.partner_credential_revision).reveal()
        return PreparedExecution(request, material.reveal() if material else None, reference, job.provider_receipt, partner_key)

    async def submit(self, execution, *, on_receipt, on_submit=None):
        request = execution.request
        if request.provider == "comfyui":
            client = self.clients.get("comfyui") or ComfyImageClient(request.options["base_url"])
            return await client.generate(request, execution.key, execution.reference, on_receipt=on_receipt,
                receipt=execution.receipt, on_submit=on_submit,
                **({"partner_key": execution.partner_key} if request.options.get("partner_auth") else {}))
        client = self.clients[request.provider]
        if request.provider in {"nanogpt", "openrouter"}:
            # Discovery is not a generation call. Never silently switch the frozen route.
            endpoint = await client.discover(request.model)
            if endpoint.get("provider_tag") != (request.endpoint or {}).get("provider_tag") or endpoint_parameters(request.provider, endpoint) != endpoint_parameters(request.provider, request.endpoint or {}) or endpoint.get("input_reference_constraints") != (request.endpoint or {}).get("input_reference_constraints"):
                raise ImagePreparationError("model_capabilities_changed")
        return await client.generate(request, execution.key, execution.reference, on_submit=on_submit)

    async def validate_connection(self, db, user, character_id, data):
        authorize_scope(db, user.id, "character", character_id)
        credential = media_credentials.find_credential(db, owner_id=user.id, character_id=character_id,
            provider=data.provider, purpose=CredentialPurpose.USER_IMAGE)
        key = data.api_key.get_secret_value() if data.api_key else None
        if key is None and credential and not data.clear_api_key:
            key = media_credentials.resolve_credential(credential, owner_id=user.id, character_id=character_id,
                provider=data.provider, purpose=CredentialPurpose.USER_IMAGE).reveal()
        if data.provider == "comfyui" and data.options.get("partner_auth"):
            partner = media_credentials.find_credential(db, owner_id=user.id, character_id=character_id,
                provider="comfyui", purpose=CredentialPurpose.COMFY_PARTNER_IMAGE)
            partner_key = data.partner_api_key.get_secret_value() if data.partner_api_key else None
            if partner_key is None and partner and not data.clear_partner_api_key:
                partner_key = media_credentials.resolve_credential(partner, owner_id=user.id,
                    character_id=character_id, provider="comfyui", purpose=CredentialPurpose.COMFY_PARTNER_IMAGE).reveal()
            if not partner_key:
                raise ImagePreparationError("comfy_partner_key_required")
        # Read-only connection checks end the read transaction before awaiting the network.
        db.rollback()
        if data.provider == "comfyui":
            options = ComfyOptions.model_validate(data.options)
            info = await ComfyImageClient(options.base_url).validate(options, key=key)
            return {"ready": True, "reference_supported": bool(options.workflow and "reference" in options.workflow.bindings),
                "object_info": {node["class_type"]: info[node["class_type"]] for workflow in (options.workflow,options.text_workflow) if workflow for node in workflow.prompt.values()},
                "checked_at": datetime.now(timezone.utc).isoformat()}
        if not key:
            raise ImagePreparationError("generation_key_required")
        if data.provider == "novelai":
            from app.domains.media.generation_contracts import NovelOptions
            options = NovelOptions.model_validate(data.options)
            self._require_novel_validation()
            prefix = ", ".join(value.strip() for value in (data.style, data.appearance) if value.strip())
            if prefix:
                validate_t5_prompt(prefix)
            if data.negative:
                validate_t5_prompt(data.negative)
            benefit = await self.clients["novelai"].subscription(key)
            if options.mode == "opus_free" and not benefit["opus_verified"]:
                raise ImagePreparationError("opus_benefit_unverified")
            validation = self._novel_validation()
            return {**benefit, "ready": validation["generation_available"], "prompt_validation": validation,
                "reference_supported": options.mode != "opus_free"}
        endpoint = await self.clients[data.provider].discover(data.model)
        validate_api_options(data.provider, endpoint, data.options)
        return {"ready": True, "credential_validation": "not_verified", "endpoint": endpoint,
            "reference_supported": endpoint_parameters(data.provider, endpoint).get("input_references", {}).get("max", 0) >= 1,
            "checked_at": datetime.now(timezone.utc).isoformat()}


def image_output_enabled(db, character_id):
    row = db.get(AgentImageGenerationSetting, character_id)
    return bool(row and row.generation_auto_enabled)


class InstallationGenerationLimits:
    @staticmethod
    def read(db):
        from app.domains.social.models.image_intents import ImageGenerationPolicy
        row = db.get(ImageGenerationPolicy, 1)
        return {"daily_limit": row.daily_limit if row else None, "revision": row.revision if row else 0}

    @staticmethod
    def write(db, value, *, expected_revision=None):
        from app.domains.social.service.generation_usage import set_installation_limit
        set_installation_limit(db, value, expected_revision=expected_revision)
