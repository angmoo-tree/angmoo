from __future__ import annotations

from app.core import security  # compatibility hook for existing image tests
from app.config import settings
from app.core.image_generation import (
    REPLICATE_IMAGE_MODEL_PRUNA_EDIT,
    REPLICATE_IMAGE_MODEL_ZIMAGE_TURBO_LORA,
)
from app.credentials import (
    CredentialPurpose,
    CredentialResolutionError,
    CredentialResolver,
)


_SERVICE_KEY_CACHE: dict[str, str | None] = {}
_PROFILE_KEY_CACHE: dict[str, str | None] = {}


def get_service_image_api_key() -> str | None:
    if not settings.POLLINATIONS_SERVICE_IMAGE_ENABLED:
        return None
    raw_value = settings.pollinations_service_image_api_key
    if not raw_value:
        return None
    cached = _SERVICE_KEY_CACHE.get(raw_value)
    if raw_value in _SERVICE_KEY_CACHE:
        return cached
    try:
        material = CredentialResolver.resolve_configured_secret(
            raw_value,
            credential_id="service-pollinations-image",
            provider="pollinations",
            model=settings.pollinations_service_image_model,
            purpose=CredentialPurpose.SERVICE_IMAGE,
        )
        result = material.reveal() if material else None
    except CredentialResolutionError:
        result = None
    _SERVICE_KEY_CACHE[raw_value] = result
    return result


def is_service_image_available() -> bool:
    return get_service_image_api_key() is not None


def get_replicate_image_api_key() -> str | None:
    raw_value = settings.replicate_image_api_token
    if not raw_value:
        return None
    cached = _SERVICE_KEY_CACHE.get(f"replicate:{raw_value}")
    cache_key = f"replicate:{raw_value}"
    if cache_key in _SERVICE_KEY_CACHE:
        return cached
    try:
        material = CredentialResolver.resolve_configured_secret(
            raw_value,
            credential_id="service-replicate-image",
            provider="replicate",
            model=REPLICATE_IMAGE_MODEL_ZIMAGE_TURBO_LORA,
            purpose=CredentialPurpose.SERVICE_IMAGE,
        )
        result = material.reveal() if material else None
    except CredentialResolutionError:
        result = None
    _SERVICE_KEY_CACHE[cache_key] = result
    return result


def is_service_image_available_for_model(model: str) -> bool:
    if model in {
        REPLICATE_IMAGE_MODEL_ZIMAGE_TURBO_LORA,
        REPLICATE_IMAGE_MODEL_PRUNA_EDIT,
    }:
        return get_replicate_image_api_key() is not None
    return is_service_image_available()


def get_profile_image_api_key() -> str | None:
    if not settings.POLLINATIONS_PROFILE_IMAGE_ENABLED:
        return None
    raw_value = settings.pollinations_profile_image_api_key
    if not raw_value:
        return None
    cached = _PROFILE_KEY_CACHE.get(raw_value)
    if raw_value in _PROFILE_KEY_CACHE:
        return cached
    try:
        material = CredentialResolver.resolve_configured_secret(
            raw_value,
            credential_id="profile-pollinations-image",
            provider="pollinations",
            model=settings.pollinations_profile_image_model,
            purpose=CredentialPurpose.SERVICE_IMAGE,
        )
        result = material.reveal() if material else None
    except CredentialResolutionError:
        result = None
    _PROFILE_KEY_CACHE[raw_value] = result
    return result


def is_profile_image_available() -> bool:
    return get_profile_image_api_key() is not None


def is_profile_image_available_for_model(model: str) -> bool:
    if model in {
        REPLICATE_IMAGE_MODEL_ZIMAGE_TURBO_LORA,
        REPLICATE_IMAGE_MODEL_PRUNA_EDIT,
    }:
        if not settings.pollinations_profile_image_enabled:
            return False
        return get_replicate_image_api_key() is not None
    return is_profile_image_available()
