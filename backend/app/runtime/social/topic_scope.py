"""Canonical current membership facts for a World topic catalog."""
from sqlalchemy import select
from app.domains.characters.models import Character
from app.domains.worlds.models import WorldMembership
from app.domains.world_characters.models import WorldCharacter
from app.domains.social.service.recommendation_topics import configure_subject_reader


def valid_interest_subjects(db, world_id):
    return db.scalars(select(WorldCharacter.id).join(Character, Character.id == WorldCharacter.character_id).join(
        WorldMembership, WorldMembership.id == WorldCharacter.membership_id,
    ).where(WorldCharacter.world_id == world_id, WorldCharacter.status.in_(("active", "inactive")),
        Character.deleted_at.is_(None), WorldMembership.world_id == world_id,
        WorldMembership.status == "active", WorldMembership.user_id == Character.owner_id,
    ).order_by(WorldCharacter.id)).all()


def configure():
    configure_subject_reader(valid_interest_subjects)
