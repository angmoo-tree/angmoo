from __future__ import annotations

from typing import Any

from app.core.image_generation import (
    REPLICATE_IMAGE_MODEL_PRUNA_EDIT,
    REPLICATE_IMAGE_MODEL_ZIMAGE_TURBO_LORA,
)
from app.services import pollinations_image, replicate_image


def is_replicate_model(model: str) -> bool:
    return model in {
        REPLICATE_IMAGE_MODEL_ZIMAGE_TURBO_LORA,
        REPLICATE_IMAGE_MODEL_PRUNA_EDIT,
    }


async def generate_image(
    *,
    api_key: str,
    model: str,
    prompt: str,
    reference_image_url: str | None = None,
    allow_reference_fallback: bool = True,
    timeout_seconds: float = 90.0,
    prompt_hash: str | None = None,
    log_context: dict[str, Any] | None = None,
    route_mode: str = "direct",
    safe_filter: str | None = pollinations_image.POLLINATIONS_SAFE_FILTER,
    width: int = 1024,
    height: int = 768,
    seed: int = -1,
) -> pollinations_image.PollinationsGeneratedImage | replicate_image.ReplicateGeneratedImage:
    if model == REPLICATE_IMAGE_MODEL_ZIMAGE_TURBO_LORA:
        return await replicate_image.generate_image(
            api_key=api_key,
            prompt=prompt,
            width=width,
            height=height,
            seed=seed,
            timeout_seconds=timeout_seconds,
            log_context=log_context,
        )
    if model == REPLICATE_IMAGE_MODEL_PRUNA_EDIT:
        if not reference_image_url:
            raise replicate_image.ReplicateImageError(
                "Replicate P-Image-Edit requires a reference image",
                failure_class="reference_required",
            )
        return await replicate_image.generate_p_image_edit(
            api_key=api_key,
            prompt=prompt,
            reference_image_url=reference_image_url,
            seed=seed,
            timeout_seconds=timeout_seconds,
            log_context=log_context,
        )
    return await pollinations_image.generate_image(
        api_key=api_key,
        model=model,
        prompt=prompt,
        reference_image_url=reference_image_url,
        allow_reference_fallback=allow_reference_fallback,
        timeout_seconds=timeout_seconds,
        prompt_hash=prompt_hash,
        log_context=log_context,
        route_mode=route_mode,
        safe_filter=safe_filter,
        width=width,
        height=height,
        seed=seed,
    )
