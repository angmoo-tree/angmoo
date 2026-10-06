"""Resolve a supported World choice against this character's verified profiles."""
import json
from copy import deepcopy
from dataclasses import dataclass
from app.domains.media.contracts import MODEL_CATALOG, ImagePreparationError


@dataclass(frozen=True)
class WorldImageProfile:
    provider: str
    model: str
    profile: dict


def _profiles(setting):
    if setting is None:
        return []
    try:
        profiles = json.loads(setting.generation_profiles_json)
    except (ValueError, TypeError):
        return []
    if not isinstance(profiles, dict):
        return []
    result = []
    for key, profile in profiles.items():
        if not isinstance(key, str) or ":" not in key or not isinstance(profile, dict):
            continue
        provider, suffix = key.split(":", 1)
        # generation_settings.profile_key appends a final operation mode.
        # Custom ComfyUI model identifiers can themselves contain a colon.
        model = suffix.rsplit(":", 1)[0] if ":" in suffix else suffix
        if (provider == "comfyui" and model) or f"{provider}:{model}" in MODEL_CATALOG:
            result.append(WorldImageProfile(provider, model, profile))
    return result


def select_world_image_profile(setting, model):
    candidates = []
    for saved in _profiles(setting):
        if model not in (saved.model, f"{saved.provider}:{saved.model}"):
            continue
        connection = saved.profile.get("connection")
        if isinstance(connection, dict) and connection.get("ready") is True:
            candidates.append(saved)
    # A model can have multiple validated operation profiles, such as NovelAI
    # subscription and paid generation. Retain the explicitly selected one.
    if len(candidates) > 1:
        candidates = [saved for saved in candidates if saved.profile.get("active") is True]
    if len(candidates) != 1:
        raise ImagePreparationError("world_image_model_connection_unverified")
    selected = candidates[0]
    return WorldImageProfile(selected.provider, selected.model, deepcopy(selected.profile))


def available_world_image_models(setting):
    models = {}
    for saved in _profiles(setting):
        value = f"{saved.provider}:{saved.model}"
        try:
            select_world_image_profile(setting, value)
            enabled, reason = True, None
        except ImagePreparationError:
            enabled, reason = False, "world_image_model_connection_unverified"
        # Only public provider/model identifiers appear here. Saved connection
        # endpoints, credential IDs and workflow bodies stay private.
        models[value] = {"value": value, "label": f"{saved.provider} · {saved.model}",
            "enabled": enabled, "reason": reason}
    return sorted(models.values(), key=lambda item: item["value"])
