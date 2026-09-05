"""Existing joined profile reads in the caller Session.

Join multiplicity, SQL ordering and filtering are preserved. Access checks and
profile/state interpretation run in the WorldCharacter services before/after
these reads; this module neither grants access nor commits writes.
"""
from sqlalchemy import and_, select
from app.domains.characters.models import Character
from app.domains.world_characters.models import WorldCharacter
from app.domains.worlds.models import WorldMembership

def _active_profile_statement(world_id: str):
    return (
        select(WorldCharacter, Character)
        .join(
            Character,
            Character.id == WorldCharacter.character_id,
        )
        .join(
            WorldMembership,
            (WorldMembership.id == WorldCharacter.membership_id)
            & (WorldMembership.world_id == WorldCharacter.world_id),
        )
        .where(
            WorldCharacter.world_id == world_id,
            WorldCharacter.status == "active",
            WorldMembership.status == "active",
            Character.deleted_at.is_(None),
            Character.moderation_status == "active",
        )
        .order_by(Character.name.asc(), WorldCharacter.id.asc())
    )


class SqlAlchemyWorldCharacterQueries:
    def public_profile_rows(self, db, world_id):
        return db.execute(_active_profile_statement(world_id)).all()

    def public_profile_row(self, db, world_id, world_character_id):
        return db.execute(
            _active_profile_statement(world_id).where(WorldCharacter.id == world_character_id)
        ).one_or_none()

    def studio_rows(self, db, world_id):
        return db.execute(
            select(WorldCharacter, Character)
            .join(Character, Character.id == WorldCharacter.character_id)
            .where(
                WorldCharacter.world_id == world_id,
                WorldCharacter.status.in_(("pending", "inactive", "active")),
            )
            .order_by(Character.name.asc(), WorldCharacter.id.asc())
        ).all()

    def candidate_rows(self, db, world_id, current_user_id):
        return db.execute(
            select(Character, WorldCharacter)
            .outerjoin(
                WorldCharacter,
                and_(
                    WorldCharacter.character_id == Character.id,
                    WorldCharacter.world_id == world_id,
                ),
            )
            .where(
                Character.owner_id == current_user_id,
                Character.deleted_at.is_(None),
            )
            .order_by(Character.name.asc(), Character.id.asc())
        ).all()
