"""Restore only the reusable identity view; immutable import bytes never change."""
from app.domains.characters.models import Character, CharacterState
from app.domains.characters.service.import_snapshots import get_import_snapshot
from app.domains.characters.service.profile import _ensure_available_handle, _build_persona_summary


def restore_unregistered_original(db, character_id):
    row, original = get_import_snapshot(db, character_id)
    character = db.get(Character, character_id)
    if character is None or character.deleted_at is not None:
        raise ValueError("preserved_original_identity_missing")
    profile, settings = original.profile, original.settings
    character.name, character.one_liner = profile.display_name, profile.intro
    character.handle = _ensure_available_handle(db, profile.handle, current_character_id=character_id, allow_suffix=True)
    character.avatar_url, character.banner_url = profile.avatar_url, profile.banner_url
    for field in ("personality", "speech_style", "worldview", "character_background", "topic_preferences", "safety_rules"):
        setattr(character, field, getattr(settings, field))
    character.status = "inactive"
    character.persona_summary = _build_persona_summary(character)
    cached_state = db.get(CharacterState, character_id)
    if cached_state is not None:
        db.delete(cached_state)
    return row.digest
