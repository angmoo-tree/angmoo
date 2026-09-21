"""Bounded subject identity, not the counterpart's private personality."""

from app.domains.characters.models import Character
from app.domains.world_characters.models import WorldCharacter
from app.domains.world_characters.service.event_scope import validate_event_scope
from app.domains.social.repository.blocks import world_character_pair_is_blocked


def review_identity_context(db, *, owner_id, world_id, actor_id, target_id):
    from app.domains.world_characters.exceptions import WorldCharacterSocialScopeError
    try:
        actor = validate_event_scope(db, world_id=world_id, world_character_id=actor_id)
        target = validate_event_scope(db, world_id=world_id, world_character_id=target_id, allow_retained_owner=True)
    except WorldCharacterSocialScopeError:
        raise ValueError('relationship_review_identity_unavailable') from None
    character, other = db.get(Character, actor.character_id), db.get(Character, target.character_id)
    if (actor.control_mode != 'autonomous' or character is None or character.owner_id != owner_id
        or character.deleted_at is not None or other is None or other.deleted_at is not None
        or world_character_pair_is_blocked(db, world_id=world_id, first_world_character_id=actor_id, second_world_character_id=target_id)):
        raise ValueError('relationship_review_identity_unavailable')
    return dict(subject_name=character.name, counterpart_name=other.name,
        subject_persona=(character.persona_summary or '')[:1200], subject_personality=(character.personality or '')[:800])
