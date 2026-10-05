"""Final creation UoW: bind a permanent origin and initialize this World once."""
from sqlalchemy import select
from app.domains.characters.contracts import ImportConfiguration, ImportProfile, ImportSettings
from app.domains.characters.models_import import CharacterImportOrigin
from app.domains.characters.models import AgentImageGenerationSetting
from app.domains.characters.service.import_snapshots import capture_creation, get_import_snapshot, attach_copy_origin
from app.domains.routines.models import AgentActivitySetting
from app.domains.world_characters.service.configuration import initialize_configuration


def creation_configuration(db, character, *, inherited=None):
    values = inherited.model_dump() if inherited else ImportSettings().model_dump()
    for name in ("personality", "speech_style", "worldview", "character_background", "topic_preferences", "safety_rules"):
        values[name] = getattr(character, name, "") or ""
    activity = db.get(AgentActivitySetting, character.id)
    if activity is not None and inherited is None:
        for name in ("active_hours_start", "active_hours_end", "activity_interval_minutes", "max_posts_per_day", "max_comments_per_day",
                     "allow_post", "allow_reply", "allow_like", "allow_repost", "allow_follow", "allow_unfollow"):
            values[name] = getattr(activity, name)
    image = db.get(AgentImageGenerationSetting, character.id)
    if image is not None and inherited is None:
        values.update(image_model=image.generation_model,
            image_style=image.style_prompt, appearance_prompt=image.appearance_prompt)
    if inherited is None:
        from app.domains.identity.models import LlmCredential
        model = db.scalar(select(LlmCredential.model).where(LlmCredential.character_id == character.id, LlmCredential.enabled.is_(True)))
        values["generation_model"] = model
    return ImportConfiguration(profile=ImportProfile(display_name=character.name, handle=character.handle,
        avatar_url=character.avatar_url, banner_url=character.banner_url, intro=character.one_liner or ""),
        settings=ImportSettings.model_validate(values))


def initialize_created_world_character(db, *, character, world_character, draft_id=None):
    copied = attach_copy_origin(db, draft_id=draft_id, character_id=character.id) if draft_id else None
    inherited = get_import_snapshot(db, character.id)[1].settings if copied else None
    configuration = creation_configuration(db, character, inherited=inherited)
    origin = copied or capture_creation(db, character_id=character.id, configuration=configuration,
        provenance=f"registration:{draft_id}" if draft_id else "verified_creation_uow")
    initialize_configuration(db, world_character=world_character, snapshot_id=origin.id, configuration=configuration)
    return configuration


def initialize_entered_world_character(db, *, world_character_id):
    """The legacy explicit entry route attaches the existing immutable basis."""
    from app.domains.world_characters.models import WorldCharacter
    from app.domains.world_characters.exceptions import WorldCharacterSetupValidationError
    role = db.get(WorldCharacter, world_character_id)
    if role is None:
        raise WorldCharacterSetupValidationError("world_character_not_ready")
    try:
        origin, configuration = get_import_snapshot(db, role.character_id)
        return initialize_configuration(db, world_character=role, snapshot_id=origin.id, configuration=configuration)
    except ValueError as exc:
        raise WorldCharacterSetupValidationError("character_import_origin_invalid") from exc
