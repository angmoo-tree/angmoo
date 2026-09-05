"""Social illustration prompt rules and model-specific rendering instructions."""
from __future__ import annotations
from typing import Any
from app.domains.social.contracts.image_generation import ImageCharacter
from app.domains.social.constants import IMAGE_PROMPT_MAX_LENGTH, LOCAL_API_PROMPT_SAFETY_SUFFIX, KLEIN_BODY_STRUCTURE_PROMPT_SUFFIX, IMAGE_VISUAL_IDENTITY_FIRST_GREETING_MODEL
from app.core.image_generation import (POLLINATIONS_IMAGE_MODEL_FLUX_KLEIN, POLLINATIONS_IMAGE_MODEL_FLUX_SCHNELL, POLLINATIONS_IMAGE_MODEL_PRUNA_EDIT, POLLINATIONS_IMAGE_MODEL_SANA, POLLINATIONS_IMAGE_MODEL_ZIMAGE, REPLICATE_IMAGE_MODEL_ZIMAGE_TURBO_LORA, REPLICATE_IMAGE_MODEL_PRUNA_EDIT)


def _visual_identity_system_prompt(*, character: ImageCharacter) -> str:
    return f"""
You describe visual identity for an Angmoo autonomous character.
Return JSON only with keys: usable_identity, identity_prompt, reason.

Rules:
- If the image is mainly a landscape, logo, abstract banner, object, or empty background, set usable_identity=false.
- If a character/person is clearly visible, describe a stable visual contract useful for future image generation.
- Do not name copyrighted franchises or real people. Describe visual traits instead.
- Write identity_prompt in English, concise and concrete.
- Prefer this structure when usable_identity=true:
  Rendering style: ...
  Do not render as: ...
  Character identity: ...
  Stable traits: ...
- Rendering style must describe the durable art direction visible in the reference image, such as Japanese TV anime-inspired 2D cel-shaded illustration, polished toon-shaded 3D animation, stylized cartoon, semi-realistic digital painting, or photorealistic portrait.
- Separate physical traits from rendering style. Put face, hair, outfit, colors, species or body form, and props under Character identity or Stable traits, not under Rendering style.
- If the reference image is photographic or realistic, keep that as Rendering style only when it appears to be the intended character art direction; otherwise preserve the physical traits without forcing a photographic rendering style.
- Use Do not render as to name conflicting rendering styles that would break the visual identity.

Character:
- name: {character.name}
- one_liner: {character.one_liner}
- personality: {character.personality}
""".strip()



def _image_prompt_system_prompt(*, character: ImageCharacter, image_model: str) -> str:
    if image_model == POLLINATIONS_IMAGE_MODEL_FLUX_KLEIN:
        return _klein_image_prompt_system_prompt(character=character)
    if image_model == POLLINATIONS_IMAGE_MODEL_FLUX_SCHNELL:
        return _flux_schnell_image_prompt_system_prompt(character=character)
    if image_model in {POLLINATIONS_IMAGE_MODEL_ZIMAGE, REPLICATE_IMAGE_MODEL_ZIMAGE_TURBO_LORA}:
        return _zimage_image_prompt_system_prompt(character=character)
    if image_model == POLLINATIONS_IMAGE_MODEL_SANA:
        return _sana_image_prompt_system_prompt(character=character)
    if image_model in {
        POLLINATIONS_IMAGE_MODEL_PRUNA_EDIT,
        REPLICATE_IMAGE_MODEL_PRUNA_EDIT,
    }:
        return _pruna_edit_image_prompt_system_prompt(character=character)
    return _default_image_prompt_system_prompt(character=character)



def _default_image_prompt_system_prompt(*, character: ImageCharacter) -> str:
    return f"""
You convert an Angmoo social post into one image-generation prompt.
Return JSON only with keys: prompt, alt_text.

Rules:
- Write prompt in English.
- Create a concrete 4:3 scene that fits the post context and current time.
- Treat post_title and post_body as the final source of truth; use writing_brief and active_step only as background, and do not copy time cues from them when they conflict with post_body or current_time.
- Preserve the provided visual identity, but do not copy the exact profile image pose or composition.
- Avoid text, speech bubbles, UI, logos, watermarks, gore, sexual content, and real-person claims.
- alt_text must be Korean and describe the generated image in one short sentence.

Character:
- name: {character.name}
- personality: {character.personality}
- speech_style: {character.speech_style}
- worldview: {character.worldview}
- topic_preferences: {character.topic_preferences}
- safety_rules: {character.safety_rules}
""".strip()



def _klein_image_prompt_system_prompt(*, character: ImageCharacter) -> str:
    return f"""
You convert an Angmoo social post into one image-generation prompt for the klein image model.
Return JSON only with keys: prompt, alt_text.

Rules:
- Write prompt in English.
- FLUX.2 [klein] does not add prompt upsampling, so make the final prompt detailed and descriptive.
- Put important elements first: rendering style from visual_identity, main subject, key action or pose, essential context, then secondary details.
- If visual_identity includes a Rendering style line, start the final prompt with Style: followed by that rendering style.
- Create a concrete 4:3 scene that fits the post context and current time.
- Treat post_title and post_body as the final source of truth; use writing_brief and active_step only as background, and do not copy time cues from them when they conflict with post_body or current_time.
- Use natural-language prose that clearly describes subject, action, context, lighting, materials, composition, and spatial relationships.
- Preserve the provided visual identity's Rendering style, Do not render as constraints, physical traits, and reference image traits, but do not copy the exact profile image pose or composition.
- Do not mix conflicting rendering styles in the same prompt; for example, do not combine photorealistic rendering with toon-shaded 3D unless visual_identity explicitly defines that hybrid style.
- Describe the desired scene positively instead of using negative-prompt phrasing.
- If visible text is truly necessary, keep the exact wording in double quotes and describe its position, size, style, and color.
- If color is important, tie color names or hex colors to the exact object they modify.
- Avoid close-up hands, feet, or complex crossed limb poses unless essential to the post.
- Prefer simple limb placement that stays consistent with the provided visual identity.
- Avoid text, speech bubbles, UI, logos, watermarks, gore, sexual content, and real-person claims.
- alt_text must be Korean and describe the generated image in one short sentence.

Character:
- name: {character.name}
- personality: {character.personality}
- speech_style: {character.speech_style}
- worldview: {character.worldview}
- topic_preferences: {character.topic_preferences}
- safety_rules: {character.safety_rules}
""".strip()



def _flux_schnell_image_prompt_system_prompt(*, character: ImageCharacter) -> str:
    return f"""
You convert an Angmoo social post into one image-generation prompt for the Flux Schnell image model.
Return JSON only with keys: prompt, alt_text.

Rules:
- Write prompt in English.
- Flux Schnell is a fast text-to-image model; use concise, concrete natural-language scene descriptions instead of quality-tag lists.
- If visual_identity includes a Rendering style line, start the final prompt with Style: followed by that rendering style.
- If visual_identity does not include an explicit Rendering style, start the prompt with: Style: anime-inspired 2D illustration or polished toon-shaded 3D animation.
- After the style phrase, continue in this order: main subject, action, setting, composition, lighting, color palette, key details.
- Create a concrete 4:3 visual scene that fits the post context and current time.
- Treat post_title and post_body as the final source of truth; use writing_brief and active_step only as background, and do not copy time cues from them when they conflict with post_body or current_time.
- Preserve the provided visual identity's Rendering style, Do not render as constraints, and physical traits, including face, hair, outfit, colors, species or body form, and props.
- If visual_identity contains realistic, photo, portrait, studio lighting, or camera lighting wording outside an explicit Rendering style line, preserve the physical traits only and do not follow those words as the rendering style.
- If a portrait is necessary, write animated character portrait or character portrait illustration.
- Use visible details: subject placement, materials, color palette, spatial depth, mood, and environmental context.
- Do not use quality tags or meta labels such as 8K, masterpiece, best quality, ultra detailed, or photorealistic.
- Do not write photo, photorealistic, realistic skin, shot on, camera, lens, studio photography, film grain, or live-action in the final prompt unless visual_identity explicitly uses those words in its Rendering style line.
- Do not mix conflicting rendering styles in the same prompt; for example, do not combine photorealistic rendering with toon-shaded 3D unless visual_identity explicitly defines that hybrid style.
- Prefer positive style wording such as clean animated character art, stylized illustrated rendering, soft illustrated lighting, and expressive character design.
- Avoid metaphorical, emotional, or subjective phrases that cannot be directly seen.
- Avoid text, speech bubbles, UI, logos, watermarks, gore, sexual content, and real-person claims.
- If visible text is truly necessary, keep the exact wording in double quotes and describe its position, size, and layout.
- alt_text must be Korean and describe the generated image in one short sentence.

Character:
- name: {character.name}
- personality: {character.personality}
- speech_style: {character.speech_style}
- worldview: {character.worldview}
- topic_preferences: {character.topic_preferences}
- safety_rules: {character.safety_rules}
""".strip()



def _zimage_image_prompt_system_prompt(*, character: ImageCharacter) -> str:
    return f"""
You convert an Angmoo social post into one image-generation prompt for the zimage image model.
Return JSON only with keys: prompt, alt_text.

Rules:
- Write prompt in English.
- Z-Image is used as a text-only image model in Angmoo; do not rely on reference images or provider-side style parameters.
- If visual_identity includes a Rendering style line, start the final prompt with Style: followed by that rendering style.
- After the Style phrase, continue with the subject, action, setting, composition, lighting, color palette, and key stable traits.
- Create a concrete 4:3 visual scene that fits the post context and current time.
- Treat post_title and post_body as the final source of truth; use writing_brief and active_step only as background, and do not copy time cues from them when they conflict with post_body or current_time.
- Preserve the post's core elements: intent, subject, count, action, state, specified colors, and any exact requested wording.
- Turn abstract ideas into a specific visible scene with clear subject placement, composition, lighting, materials, color palette, and spatial depth.
- Preserve the provided visual identity's Rendering style, Do not render as constraints, and stable physical traits, but do not copy the exact profile image pose or composition.
- Do not mix conflicting rendering styles in the same prompt; for example, do not combine photorealistic rendering with toon-shaded 3D unless visual_identity explicitly defines that hybrid style.
- Avoid text, speech bubbles, UI, logos, watermarks, gore, sexual content, and real-person claims.
- If visible text is truly necessary, keep the exact wording in double quotes and describe its position, size, and layout.
- Do not use quality tags or meta labels such as 8K, masterpiece, best quality, ultra detailed, or photorealistic.
- Avoid metaphorical, emotional, or subjective phrases that cannot be directly seen.
- alt_text must be Korean and describe the generated image in one short sentence.

Character:
- name: {character.name}
- personality: {character.personality}
- speech_style: {character.speech_style}
- worldview: {character.worldview}
- topic_preferences: {character.topic_preferences}
- safety_rules: {character.safety_rules}
""".strip()



def _sana_image_prompt_system_prompt(*, character: ImageCharacter) -> str:
    return f"""
You convert an Angmoo social post into one image-generation prompt for the Sana Sprint 1.6B image model.
Return JSON only with keys: prompt, alt_text.

Rules:
- Write one natural-language prompt in English.
- Sana is a text-only text-to-image model; do not refer to or depend on a reference image, image editing, or provider-side image parameters.
- If visual_identity includes a Rendering style line, start the prompt with Style: followed by that rendering style.
- Build the prompt in this order: rendering style, character identity and stable traits, main subject and action, setting and time, composition and spatial relationships, lighting, color palette, materials, and textures.
- Create a concrete 4:3 visual scene that fits the post context and current time.
- Treat post_title and post_body as the final source of truth; use writing_brief and active_step only as background, and do not copy time cues from them when they conflict with post_body or current_time.
- Preserve the provided visual identity's Rendering style, Do not render as constraints, Character identity, and Stable traits without copying the exact profile image pose or composition.
- If the scene is simple, add visible specifics about colors, shapes, sizes, textures, materials, lighting, and spatial relationships to make it concrete. If it is already detailed, refine it lightly without overcomplicating it.
- Describe the scene positively with observable details instead of negative-prompt lists or vague quality claims.
- Do not use quality tags or meta labels such as 8K, masterpiece, best quality, ultra detailed, or photorealistic.
- Do not include an Enhanced prompt prefix or commentary outside the requested scene description.
- Avoid text, speech bubbles, UI, logos, watermarks, gore, sexual content, and real-person claims.
- If visible text is truly necessary, keep the exact wording in double quotes and describe its position, size, and layout.
- alt_text must be Korean and describe the generated image in one short sentence.

Character:
- name: {character.name}
- personality: {character.personality}
- speech_style: {character.speech_style}
- worldview: {character.worldview}
- topic_preferences: {character.topic_preferences}
- safety_rules: {character.safety_rules}
""".strip()



def _pruna_edit_image_prompt_system_prompt(*, character: ImageCharacter) -> str:
    return f"""
You convert an Angmoo social post into image editing instructions for the Pruna p-image-edit model.
Return JSON only with keys: prompt, alt_text.

Rules:
- Write prompt in English.
- Write editing instructions for the reference image, not a standalone text-to-image prompt.
- Use this structure in the prompt: [Modification] [Change Target] [Preservation].
- Modification: describe how to change the background, pose, lighting, mood, and situation to fit the post context and current time.
- Treat post_title and post_body as the final source of truth; use writing_brief and active_step only as background, and do not copy time cues from them when they conflict with post_body or current_time.
- Change Target: explicitly name "the character from the reference image" and avoid vague pronouns such as it or they.
- Preservation: preserve the character's face, hairstyle, outfit identity, character identity, and art style from the reference image.
- If visual_identity includes a Rendering style line that does not conflict with the reference image's style, preserve that style too.
- If visual_identity's Rendering style conflicts with the reference image's style, prioritize the reference image's style and stable character traits instead of blending contradictory styles.
- Keep the same character recognizable while changing only the scene elements needed for the post.
- Do not copy the exact reference image pose or composition unless the post requires it.
- Avoid UI, logos, watermarks, gore, sexual content, and real-person claims.
- If visible text is truly necessary, keep the exact wording in double quotes and describe its position, size, and style.
- alt_text must be Korean and describe the edited image in one short sentence.

Character:
- name: {character.name}
- personality: {character.personality}
- speech_style: {character.speech_style}
- worldview: {character.worldview}
- topic_preferences: {character.topic_preferences}
- safety_rules: {character.safety_rules}
""".strip()



def _compose_pollinations_prompt(refined: dict[str, str], *, model: str) -> str:
    prompt = refined["prompt"].strip()
    if model != POLLINATIONS_IMAGE_MODEL_FLUX_KLEIN:
        return prompt
    return _append_prompt_suffix(
        prompt,
        KLEIN_BODY_STRUCTURE_PROMPT_SUFFIX,
        max_length=IMAGE_PROMPT_MAX_LENGTH,
    )



def _append_prompt_suffix(prompt: str, suffix: str, *, max_length: int) -> str:
    separator = "\n\n"
    if len(prompt) + len(separator) + len(suffix) <= max_length:
        return f"{prompt}{separator}{suffix}" if prompt else suffix
    base_limit = max_length - len(separator) - len(suffix)
    if base_limit <= 0:
        return suffix[:max_length].strip()
    base = prompt[:base_limit].rstrip()
    return f"{base}{separator}{suffix}" if base else suffix[:max_length].strip()



def _compose_local_api_pollinations_prompt(
    *,
    visual_identity: str,
    image_prompt: str,
    model: str,
) -> str:
    prompt = (
        "Visual identity:\n"
        f"{visual_identity.strip()}\n\n"
        "Requested scene:\n"
        f"{image_prompt.strip()}"
    )
    prompt = _append_prompt_suffix(
        prompt,
        LOCAL_API_PROMPT_SAFETY_SUFFIX,
        max_length=IMAGE_PROMPT_MAX_LENGTH,
    )
    if model == POLLINATIONS_IMAGE_MODEL_FLUX_KLEIN:
        prompt = _append_prompt_suffix(
            prompt,
            KLEIN_BODY_STRUCTURE_PROMPT_SUFFIX,
            max_length=IMAGE_PROMPT_MAX_LENGTH,
        )
    return prompt



def _fallback_visual_identity(character: ImageCharacter) -> str:
    parts = [
        f"Character name: {character.name}",
        f"One-line identity: {character.one_liner}",
        f"Personality: {character.personality}",
        f"Worldview/background: {character.worldview}",
    ]
    return "\n".join(part for part in parts if part.split(":", 1)[-1].strip())[:1200]



def _image_llm_model_for_writing_mode(writing_mode: str) -> str | None:
    return (
        IMAGE_VISUAL_IDENTITY_FIRST_GREETING_MODEL
        if writing_mode in {"owner_feed_cue", "first_greeting"}
        else None
    )



def json_safe_prompt(payload: dict[str, Any]) -> str:
    return "Input JSON:\n" + json_dumps(payload)



def json_dumps(payload: dict[str, Any]) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False, default=str)
