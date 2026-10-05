"""Immutable World static policy combined with this actor's learned activity facts."""
from dataclasses import dataclass
from copy import deepcopy
from types import MappingProxyType
from typing import Any, Mapping

from app.domains.world_characters.contracts.configuration import configuration_from_request
from app.domains.characters.service.prompt_persona import legacy_persona_summary

STATIC_ACTIVITY_FIELDS = (
    "active_hours_start", "active_hours_end", "activity_interval_minutes", "max_posts_per_day", "max_comments_per_day",
    "allow_post", "allow_reply", "allow_like", "allow_repost", "allow_follow", "allow_unfollow",
)


@dataclass(frozen=True)
class EffectiveActivitySettings:
    values: Mapping[str, Any]

    def __getattr__(self, name):
        try:
            return self.values[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


def configured_setting(setting, configuration):
    if setting is None or configuration is None:
        return setting
    # Copies contain learned metadata, never credentials or another World.
    values = {column.key: deepcopy(getattr(setting, column.key)) for column in setting.__mapper__.column_attrs}
    values["tendency_analysis_ready"] = setting.tendency_analysis_ready
    values.update({name: getattr(configuration.settings, name) for name in STATIC_ACTIVITY_FIELDS})
    values["auto_enabled"] = configuration.autonomous_enabled
    return EffectiveActivitySettings(MappingProxyType(values))


def configuration_for_input(input_snapshot, *, character_id):
    if not input_snapshot or "_world_configuration" not in input_snapshot:
        return None
    configuration = configuration_from_request(input_snapshot["_world_configuration"])
    if configuration.character_id != character_id:
        raise ValueError("world_configuration_snapshot_scope_invalid")
    return configuration


def setting_for_input(setting, input_snapshot, *, character_id):
    return configured_setting(setting, configuration_for_input(input_snapshot, character_id=character_id))


@dataclass(frozen=True)
class EffectiveCharacter:
    """Model-facing values only. The attached Character and credentials stay owned."""
    values: Mapping[str, Any]

    def __getattr__(self, name):
        try:
            return self.values[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


def configured_character(character, configuration):
    if character is None or configuration is None:
        return character
    if character.id != configuration.character_id:
        raise ValueError("world_configuration_snapshot_scope_invalid")
    values = {name: getattr(character, name) for name in (
        "id", "owner_id", "deleted_at", "status", "moderation_status", "execution_mode", "created_at"
    ) if hasattr(character, name)}
    profile, settings = configuration.profile, configuration.settings
    values.update(name=profile.display_name, handle=profile.handle, avatar_url=profile.avatar_url,
        banner_url=profile.banner_url, one_liner=profile.intro, world_id=configuration.world_id,
        world_character_id=configuration.world_character_id, world_configuration_revision=configuration.revision)
    values.update({name: getattr(settings, name) for name in (
        "personality", "speech_style", "worldview", "character_background", "topic_preferences", "safety_rules"
    )})
    # No legacy free-text summary from the common Character leaks into a World.
    values["persona_summary"] = legacy_persona_summary(values)
    return EffectiveCharacter(MappingProxyType(values))


def character_for_input(character, input_snapshot):
    if character is None or not input_snapshot or "_world_configuration" not in input_snapshot:
        return character
    return configured_character(character, configuration_for_input(input_snapshot, character_id=character.id))
