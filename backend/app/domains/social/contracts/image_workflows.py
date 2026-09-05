"""Existing Character/settings and client collaboration for Social image workflows.

The Session and opaque LLM tracker retain the caller's identity; constructing the
runtime binding performs no query, credential resolution, or provider request.
"""
from __future__ import annotations
from collections.abc import Awaitable, Callable
from typing import Any, Protocol
from sqlalchemy.orm import Session
from app.domains.social.contracts.image_generation import ImageCharacter, ImageReferenceLocation


class ImageSetting(Protocol):
    @property
    def image_generation_enabled(self) -> bool: ...

    @property
    def max_images_per_day(self) -> int: ...

    @property
    def pollinations_image_model(self) -> str: ...

    @property
    def encrypted_pollinations_api_key(self) -> str | None: ...

    @property
    def encrypted_replicate_api_token(self) -> str | None: ...

    @property
    def seed_image_url(self) -> str | None: ...

    @property
    def visual_identity_prompt(self) -> str | None: ...

    @property
    def visual_identity_source_hash(self) -> str | None: ...


class ImageCredential(Protocol):
    @property
    def id(self) -> str: ...

    @property
    def provider(self) -> str: ...

    @property
    def model(self) -> str: ...

    @property
    def key_fingerprint(self) -> str | None: ...


class ImageReference(ImageReferenceLocation, Protocol):
    @property
    def source(self) -> str: ...

    @property
    def source_hash(self) -> str: ...

    @property
    def llm_part(self) -> object: ...


class ImageGenerationWorkflows(Protocol):
    @property
    def llm_error(self) -> type[Exception]: ...

    def get_image_generation_setting(self, db: Session, character_id: str) -> ImageSetting | None: ...
    def service_image_available(self, model: str) -> bool: ...
    def free_image_model(self, db: Session | None) -> str: ...
    def image_route_mode(self, db: Session) -> str: ...
    def image_key_for_source(self,
        setting: ImageSetting,
        key_source: str,
        model: str,
        *,
        character: ImageCharacter,
    ) -> str | None: ...

    def unsafe_image_text_reason(self, text: str | None) -> str | None: ...

    def log_local_api_image_rejected(self,
        *,
        db: Session,
        user_id: str,
        character_id: str,
        post_id: str,
        local_key_prefix: str,
    ) -> None: ...

    def build_reference_image(self, *, source: str, url: str) -> ImageReference | None: ...
    def store_image_visual_identity(self, db: Session, setting: ImageSetting, *, identity_prompt: str, source_hash: str) -> str: ...

    async def generate_visual_identity_payload(self,
        *,
        character: ImageCharacter,
        credential: ImageCredential,
        reference: ImageReference,
        tracker: object,
        run_id: str,
        on_rate_limit_wait: Callable[[float], Awaitable[None]] | None,
        model_override: str | None = None,
    ) -> dict[str, Any]: ...

    async def generate_image_prompt_payload(self,
        *,
        character: ImageCharacter,
        credential: ImageCredential,
        tracker: object,
        run_id: str,
        image_model: str,
        current_time_text: str,
        post_title: str,
        post_body: str,
        writing_plan: dict[str, Any],
        visual_identity: str,
        on_rate_limit_wait: Callable[[float], Awaitable[None]] | None,
        model_override: str | None = None,
    ) -> dict[str, Any]: ...
