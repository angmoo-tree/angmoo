"""Concrete image workflow: same-Session owners, credential/LLM clients and reference files."""
from __future__ import annotations

from app.domains.social.service import image_generation as image_policy, image_identity


from app.domains.social.contracts.image_generation import (
    PreparedPostImage,
)
from app.domains.social.schemas.image_generation import (
    _VisualIdentityPayload,
    _ImagePromptPayload,
)
from app.domains.social.service.image_prompts import _visual_identity_system_prompt, _image_prompt_system_prompt, json_safe_prompt

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
import hashlib
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.domains.characters.models import Character
from app.domains.identity.models import LlmCredential
from app.models.agent_settings import AgentImageGenerationSetting
from app.domains.social.schemas import community as schemas
from app.config import settings
from app.credentials import (
    CredentialPurpose,
    CredentialResolutionError,
    CredentialResolver,
)
from app.cruds import agents as agent_crud
from app.integrations import image_provider
from app.domains.social.service import media_storage as profile_media
from app.integrations.media import files as media_files
from app.services import image_prompt_safety, operation_settings, service_image_key
from app.services.direct_llm import (
    DirectLlmCallContext,
    DirectLlmError,
    DirectLlmImagePart,
    RunLlmTracker,
    generate_json,
)


@dataclass(frozen=True)
class _ReferenceImage:
    source: str
    url: str
    source_hash: str
    llm_part: DirectLlmImagePart
    public_url: str | None


async def prepare_post_image(
    *,
    db: Session,
    character: Character,
    credential: LlmCredential,
    run_id: str,
    tracker: RunLlmTracker,
    writing_mode: str,
    post_title: str,
    post_body: str,
    writing_plan: dict[str, Any],
    current_time_text: str,
    run_started_at: datetime,
    on_rate_limit_wait: Callable[[float], Awaitable[None]] | None = None,
) -> PreparedPostImage:
    return await image_policy.prepare_post_image(
        workflows=RuntimeImageGenerationWorkflows(),
        db=db,
        character=character,
        credential=credential,
        run_id=run_id,
        tracker=tracker,
        writing_mode=writing_mode,
        post_title=post_title,
        post_body=post_body,
        writing_plan=writing_plan,
        current_time_text=current_time_text,
        run_started_at=run_started_at,
        on_rate_limit_wait=on_rate_limit_wait,
    )


def create_local_api_post_image_request(
    *,
    db: Session,
    user_id: str,
    local_key_prefix: str,
    character: Character,
    post_id: str,
    image_prompt: str,
    requested_at: datetime,
) -> schemas.BotImageRequestRead:
    return image_policy.create_local_api_post_image_request(
        workflows=RuntimeImageGenerationWorkflows(),
        db=db,
        user_id=user_id,
        local_key_prefix=local_key_prefix,
        character=character,
        post_id=post_id,
        image_prompt=image_prompt,
        requested_at=requested_at,
    )


async def prepare_local_api_post_image(
    *,
    db: Session,
    character: Character,
    image_prompt: str,
    run_started_at: datetime,
    key_source: str = "user",
    quota_reservation_id: int | None = None,
    post_id: str | None = None,
    job_id: int | None = None,
) -> PreparedPostImage:
    return await image_policy.prepare_local_api_post_image(
        workflows=RuntimeImageGenerationWorkflows(),
        db=db,
        character=character,
        image_prompt=image_prompt,
        run_started_at=run_started_at,
        key_source=key_source,
        quota_reservation_id=quota_reservation_id,
        post_id=post_id,
        job_id=job_id,
    )


async def _ensure_visual_identity(
    *,
    db: Session,
    setting: AgentImageGenerationSetting,
    character: Character,
    credential: LlmCredential,
    reference: _ReferenceImage,
    tracker: RunLlmTracker,
    run_id: str,
    on_rate_limit_wait: Callable[[float], Awaitable[None]] | None,
    model_override: str | None = None,
) -> str | None:
    return await image_identity._ensure_visual_identity(workflows=RuntimeImageGenerationWorkflows(), db=db, setting=setting, character=character, credential=credential, reference=reference, tracker=tracker, run_id=run_id, on_rate_limit_wait=on_rate_limit_wait, model_override=model_override)


def _build_reference_image(*, source: str, url: str) -> _ReferenceImage | None:
    if url.startswith("/media/"):
        try:
            path = media_files.media_url_to_path(url)
            content = path.read_bytes()
        except (OSError, profile_media.InvalidProfileMediaError):
            return None
        mime_type = _mime_type_from_url(url)
        source_hash = hashlib.sha256(f"{source}:{url}:".encode("utf-8") + content).hexdigest()
        return _ReferenceImage(
            source=source,
            url=url,
            source_hash=source_hash,
            llm_part=DirectLlmImagePart(mime_type=mime_type, data=content),
            public_url=_public_media_url(url),
        )
    if url.startswith("https://"):
        mime_type = _mime_type_from_url(url)
        source_hash = hashlib.sha256(f"{source}:{url}".encode("utf-8")).hexdigest()
        return _ReferenceImage(
            source=source,
            url=url,
            source_hash=source_hash,
            llm_part=DirectLlmImagePart(mime_type=mime_type, url=url),
            public_url=url,
        )
    return None


def _public_media_url(url: str) -> str | None:
    public_base_url = settings.public_base_url
    media_prefix = f"{settings.media_url_path.rstrip('/')}/"
    if public_base_url is None or not url.startswith(media_prefix):
        return None
    return f"{public_base_url}{url}"


def _mime_type_from_url(url: str) -> str:
    suffix = urlparse(url).path.lower().rsplit(".", 1)[-1]
    if suffix in {"jpg", "jpeg"}:
        return "image/jpeg"
    if suffix == "png":
        return "image/png"
    if suffix == "webp":
        return "image/webp"
    return "image/jpeg"


def _image_model_for_key_source(
    setting: AgentImageGenerationSetting | None,
    key_source: str,
    *,
    db: Session | None = None,
) -> str:
    return image_policy._image_model_for_key_source(workflows=RuntimeImageGenerationWorkflows(), setting=setting, key_source=key_source, db=db)


def _image_key_for_source(
    setting: AgentImageGenerationSetting,
    key_source: str,
    model: str,
    *,
    character: Character,
) -> str | None:
    if key_source == "service":
        if image_provider.is_replicate_model(model):
            return service_image_key.get_replicate_image_api_key()
        return service_image_key.get_service_image_api_key()
    encrypted_key = (
        setting.encrypted_replicate_api_token
        if image_provider.is_replicate_model(model)
        else setting.encrypted_pollinations_api_key
    )
    if not encrypted_key:
        return None
    try:
        return CredentialResolver.resolve_encrypted_material(
            encrypted_secret=encrypted_key,
            credential_id="user-image-setting",
            provider="replicate"
            if image_provider.is_replicate_model(model)
            else "pollinations",
            model=model,
            fingerprint=None,
            purpose=CredentialPurpose.USER_IMAGE,
            owner_id=character.owner_id,
            character_id=character.id,
            stored_purpose="user_image",
        ).reveal()
    except CredentialResolutionError:
        return None


def _unsafe_image_text_reason(text: str | None) -> str | None:
    return image_prompt_safety.unsafe_image_text_reason(text)


def _log_local_api_image_rejected(
    *,
    db: Session,
    user_id: str,
    character_id: str,
    post_id: str,
    local_key_prefix: str,
) -> None:
    agent_crud.log_activity(
        db,
        user_id=user_id,
        character_id=character_id,
        action_type="local_api_image_rejected",
        target_post_id=post_id,
        reason="unsafe_prompt",
        result=f"skip_reason=unsafe_prompt; token_prefix={local_key_prefix}",
    )


class RuntimeImageGenerationWorkflows:
    @property
    def llm_error(self) -> type[Exception]:
        return DirectLlmError

    def get_image_generation_setting(self, db: Session, character_id: str):
        return agent_crud.get_image_generation_setting(db, character_id)

    def service_image_available(self, model: str) -> bool:
        return service_image_key.is_service_image_available_for_model(model)

    def free_image_model(self, db: Session | None) -> str:
        return operation_settings.get_pollinations_free_image_model(db)

    def image_route_mode(self, db: Session) -> str:
        return operation_settings.get_pollinations_image_route_mode(db)


    def image_key_for_source(self,
        setting: AgentImageGenerationSetting,
        key_source: str,
        model: str,
        *,
        character: Character,
    ) -> str | None:
        return _image_key_for_source(setting, key_source, model, character=character)

    def unsafe_image_text_reason(self, text: str | None) -> str | None:
        return _unsafe_image_text_reason(text)

    def log_local_api_image_rejected(self,
        *,
        db: Session,
        user_id: str,
        character_id: str,
        post_id: str,
        local_key_prefix: str,
    ) -> None:
        return _log_local_api_image_rejected(db=db, user_id=user_id, character_id=character_id, post_id=post_id, local_key_prefix=local_key_prefix)

    def build_reference_image(self, *, source: str, url: str) -> _ReferenceImage | None:
        return _build_reference_image(source=source, url=url)

    def store_image_visual_identity(self, db: Session, setting: AgentImageGenerationSetting, *, identity_prompt: str, source_hash: str) -> str:
        # Preserve the attached setting and the caller's explicit commit/refresh.
        setting.visual_identity_prompt = identity_prompt.strip()
        setting.visual_identity_source_hash = source_hash
        db.commit()
        db.refresh(setting)
        return setting.visual_identity_prompt

    async def generate_visual_identity_payload(self,
        *,
        character: Character,
        credential: LlmCredential,
        reference: _ReferenceImage,
        tracker: RunLlmTracker,
        run_id: str,
        on_rate_limit_wait: Callable[[float], Awaitable[None]] | None,
        model_override: str | None = None,
    ) -> dict[str, Any]:
        return await _generate_visual_identity_payload(character=character, credential=credential, reference=reference, tracker=tracker, run_id=run_id, on_rate_limit_wait=on_rate_limit_wait, model_override=model_override)

    async def generate_image_prompt_payload(self,
        *,
        character: Character,
        credential: LlmCredential,
        tracker: RunLlmTracker,
        run_id: str,
        image_model: str,
        current_time_text: str,
        post_title: str,
        post_body: str,
        writing_plan: dict[str, Any],
        visual_identity: str,
        on_rate_limit_wait: Callable[[float], Awaitable[None]] | None,
        model_override: str | None = None,
    ) -> dict[str, Any]:
        return await _generate_image_prompt_payload(character=character, credential=credential, tracker=tracker, run_id=run_id, image_model=image_model, current_time_text=current_time_text, post_title=post_title, post_body=post_body, writing_plan=writing_plan, visual_identity=visual_identity, on_rate_limit_wait=on_rate_limit_wait, model_override=model_override)


async def _generate_visual_identity_payload(
    *,
    character: Character,
    credential: LlmCredential,
    reference: _ReferenceImage,
    tracker: RunLlmTracker,
    run_id: str,
    on_rate_limit_wait: Callable[[float], Awaitable[None]] | None,
    model_override: str | None = None,
) -> dict[str, Any]:
    try:
        api_key = CredentialResolver.resolve_llm_credential(
            credential,
            purpose=CredentialPurpose.USER_IMAGE,
            owner_id=character.owner_id,
            character_id=character.id,
            allowed_stored_purposes={"agent"},
        ).reveal()
    except CredentialResolutionError as exc:
        raise DirectLlmError("text credential key cannot be resolved") from exc
    def _validator(payload: dict[str, Any]) -> dict[str, Any]:
        return _VisualIdentityPayload.model_validate(payload).model_dump()
    payload = await generate_json(
        api_key=api_key,
        context=DirectLlmCallContext(
            credential_id=credential.id,
            character_id=character.id,
            agent_run_id=run_id,
            node="ImageVisualIdentity",
            lane="image_visual_identity",
            provider=credential.provider,
            model=model_override or credential.model,
            key_fingerprint=credential.key_fingerprint,
        ),
        tracker=tracker,
        system_prompt=_visual_identity_system_prompt(character=character),
        user_prompt=(
            "Inspect the reference image and return JSON describing the stable visual "
            "identity to preserve for future social post illustrations."
        ),
        response_schema=_VisualIdentityPayload,
        validator=_validator,
        max_output_tokens=800,
        user_image_parts=[reference.llm_part],
        on_rate_limit_wait=on_rate_limit_wait,
    )
    return payload


async def _generate_image_prompt_payload(
    *,
    character: Character,
    credential: LlmCredential,
    tracker: RunLlmTracker,
    run_id: str,
    image_model: str,
    current_time_text: str,
    post_title: str,
    post_body: str,
    writing_plan: dict[str, Any],
    visual_identity: str,
    on_rate_limit_wait: Callable[[float], Awaitable[None]] | None,
    model_override: str | None = None,
) -> dict[str, Any]:
    try:
        api_key = CredentialResolver.resolve_llm_credential(
            credential,
            purpose=CredentialPurpose.USER_IMAGE,
            owner_id=character.owner_id,
            character_id=character.id,
            allowed_stored_purposes={"agent"},
        ).reveal()
    except CredentialResolutionError as exc:
        raise DirectLlmError("text credential key cannot be resolved") from exc
    def _validator(payload: dict[str, Any]) -> dict[str, Any]:
        return _ImagePromptPayload.model_validate(payload).model_dump()
    payload = await generate_json(
        api_key=api_key,
        context=DirectLlmCallContext(
            credential_id=credential.id,
            character_id=character.id,
            agent_run_id=run_id,
            node="ImagePromptRefiner",
            lane="image_prompt_refiner",
            provider=credential.provider,
            model=model_override or credential.model,
            key_fingerprint=credential.key_fingerprint,
        ),
        tracker=tracker,
        system_prompt=_image_prompt_system_prompt(
            character=character,
            image_model=image_model,
        ),
        user_prompt=json_safe_prompt(
            {
                "current_time": current_time_text,
                "post_title": post_title,
                "post_body": post_body,
                "writing_mode": writing_plan.get("mode"),
                "writing_brief": writing_plan.get("brief"),
                "active_step": writing_plan.get("active_step"),
                "visual_identity": visual_identity,
            }
        ),
        response_schema=_ImagePromptPayload,
        validator=_validator,
        max_output_tokens=1100,
        on_rate_limit_wait=on_rate_limit_wait,
    )
    return payload
