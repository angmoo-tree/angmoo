"""Social visual-identity cache, provider output validation and reference choice."""
from __future__ import annotations
from collections.abc import Awaitable, Callable
from typing import Any
from pydantic import ValidationError
from sqlalchemy.orm import Session
from app.domains.social.contracts.image_generation import ImageCharacter
from app.domains.social.contracts.image_workflows import ImageCredential, ImageSetting, ImageReference, ImageGenerationWorkflows
from app.domains.social.schemas.image_generation import _VisualIdentityPayload, _ImagePromptPayload
from app.domains.social.service.image_prompts import _fallback_visual_identity


async def _ensure_visual_identity(
    *,
    workflows: ImageGenerationWorkflows,
    db: Session,
    setting: ImageSetting,
    character: ImageCharacter,
    credential: ImageCredential,
    reference: ImageReference,
    tracker: object,
    run_id: str,
    on_rate_limit_wait: Callable[[float], Awaitable[None]] | None,
    model_override: str | None = None,
) -> str | None:
    if setting.visual_identity_prompt and setting.visual_identity_source_hash is None:
        return setting.visual_identity_prompt.strip() or None
    if (
        setting.visual_identity_prompt
        and setting.visual_identity_source_hash == reference.source_hash
    ):
        return setting.visual_identity_prompt.strip() or None
    payload = await workflows.generate_visual_identity_payload(
        character=character,
        credential=credential,
        reference=reference,
        tracker=tracker,
        run_id=run_id,
        on_rate_limit_wait=on_rate_limit_wait,
        model_override=model_override,
    )
    try:
        identity = _VisualIdentityPayload.model_validate(payload)
    except ValidationError:
        return None
    if not identity.usable_identity or not identity.identity_prompt.strip():
        if reference.source == "banner":
            return None
        return None
    return workflows.store_image_visual_identity(
        db, setting, identity_prompt=identity.identity_prompt, source_hash=reference.source_hash,
    )


async def _resolve_visual_identity(
    *,
    workflows: ImageGenerationWorkflows,
    db: Session,
    setting: ImageSetting,
    character: ImageCharacter,
    credential: ImageCredential,
    reference: ImageReference | None,
    tracker: object,
    run_id: str,
    on_rate_limit_wait: Callable[[float], Awaitable[None]] | None,
    model_override: str | None = None,
) -> str:
    if setting.visual_identity_prompt and setting.visual_identity_source_hash is None:
        return setting.visual_identity_prompt.strip()
    if reference is None:
        return setting.visual_identity_prompt or _fallback_visual_identity(character)
    visual_identity = await _ensure_visual_identity(workflows=workflows,
        db=db,
        setting=setting,
        character=character,
        credential=credential,
        reference=reference,
        tracker=tracker,
        run_id=run_id,
        on_rate_limit_wait=on_rate_limit_wait,
        model_override=model_override,
    )
    return visual_identity or _fallback_visual_identity(character)


async def _refine_image_prompt(
    *,
    workflows: ImageGenerationWorkflows,
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
) -> dict[str, str]:
    payload = await workflows.generate_image_prompt_payload(
        character=character,
        credential=credential,
        tracker=tracker,
        run_id=run_id,
        image_model=image_model,
        current_time_text=current_time_text,
        post_title=post_title,
        post_body=post_body,
        writing_plan=writing_plan,
        visual_identity=visual_identity,
        on_rate_limit_wait=on_rate_limit_wait,
        model_override=model_override,
    )
    refined = _ImagePromptPayload.model_validate(payload).model_dump()
    return {
        "prompt": refined["prompt"].strip(),
        "alt_text": refined["alt_text"].strip(),
    }


def _select_reference_image(
    character: ImageCharacter,
    setting: ImageSetting,
    *, workflows: ImageGenerationWorkflows,
) -> ImageReference | None:
    candidates = [
        ("seed", setting.seed_image_url),
        ("avatar", character.avatar_url),
        ("banner", character.banner_url),
    ]
    for source, url in candidates:
        if not url:
            continue
        reference = workflows.build_reference_image(source=source, url=url)
        if reference is not None:
            return reference
    return None
