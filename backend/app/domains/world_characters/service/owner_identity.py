from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.ids import uuid7_string
from app.domains.characters.service.profile import get_character
from app.domains.characters.service.owner_controlled import (
    seed_owner_controlled_character, update_owner_controlled_character,
)
from app.domains.identity.service.owner_context import is_claimed_local_owner
from app.domains.world_characters.contracts.owner_identity import (
    LocalOwnerRequiredError,
    OwnerControlledIdentityConflictError,
    OwnerControlledIdentityNotFoundError,
    OwnerControlledIdentitySnapshot,
    OwnerControlledProfile,
    OwnerControlledRoleInvalidError,
    OwnerWorldRequiredError,
)
from app.domains.world_characters.models import (
    CharacterActiveWorld,
    WorldCharacter,
)
from app.domains.worlds.service import (
    WorldServiceError,
    get_active_membership,
    get_world,
    is_enabled_world_role,
)


class OwnerControlledIdentityService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get(
        self,
        *,
        world_id: str,
        current_user_id: str,
    ) -> OwnerControlledIdentitySnapshot:
        self._require_local_owner(current_user_id)
        self._require_owned_world_membership(world_id, current_user_id)
        world_character = self._find_identity(world_id, current_user_id)
        if world_character is None:
            raise OwnerControlledIdentityNotFoundError(world_id)
        character = get_character(self._db, world_character.character_id)
        if character is None or character.deleted_at is not None:
            raise OwnerControlledIdentityNotFoundError(world_id)
        return _snapshot(character, world_character)

    def create(
        self,
        *,
        world_id: str,
        current_user_id: str,
        profile: OwnerControlledProfile,
    ) -> OwnerControlledIdentitySnapshot:
        try:
            character, world_character = self.seed_create(
                world_id=world_id,
                current_user_id=current_user_id,
                profile=profile,
            )
            self._db.commit()
        except IntegrityError as exc:
            self._db.rollback()
            raise OwnerControlledIdentityConflictError(world_id) from exc
        self._db.refresh(character)
        self._db.refresh(world_character)
        return _snapshot(character, world_character)

    def seed_create(
        self,
        *,
        world_id: str,
        current_user_id: str,
        profile: OwnerControlledProfile,
    ):
        """Flush owner-controlled identity rows under a caller-owned UoW."""

        self._require_local_owner(current_user_id)
        membership = self._require_owned_world_membership(world_id, current_user_id)
        self._validate_role(world_id, profile.role_key)
        if self._find_identity(world_id, current_user_id) is not None:
            raise OwnerControlledIdentityConflictError(world_id)

        character_id = uuid7_string()
        world_character_id = uuid7_string()
        character = seed_owner_controlled_character(
            self._db, character_id=character_id, owner_id=current_user_id,
            display_name=profile.display_name, avatar_url=profile.avatar_url,
            intro=profile.intro, interests=profile.interests, background=profile.background,
        )
        world_character = WorldCharacter(
            id=world_character_id,
            world_id=world_id,
            character_id=character_id,
            membership_id=membership.id,
            role_key=profile.role_key,
            status="active",
            control_mode="owner_controlled",
            owner_user_id=current_user_id,
            autonomous_enabled=False,
            activity_runtime_mode="legacy_resident_v1",
            feed_runtime_mode="legacy_latest_v1",
            local_profile=_profile_document(profile),
            version=1,
        )
        self._db.add(world_character)
        self._db.flush()
        self._db.add(
            CharacterActiveWorld(
                character_id=character_id,
                world_character_id=world_character_id,
                selected_at=datetime.now(UTC),
                idempotency_key=f"owner-controlled:{world_id}:{current_user_id}",
                version=1,
            )
        )
        self._db.flush()
        return character, world_character

    def update(
        self,
        *,
        world_id: str,
        current_user_id: str,
        profile: OwnerControlledProfile,
    ) -> OwnerControlledIdentitySnapshot:
        self._require_local_owner(current_user_id)
        self._require_owned_world_membership(world_id, current_user_id)
        self._validate_role(world_id, profile.role_key)
        world_character = self._find_identity(world_id, current_user_id)
        if world_character is None:
            raise OwnerControlledIdentityNotFoundError(world_id)
        character = get_character(self._db, world_character.character_id)
        if (
            character is None
            or character.deleted_at is not None
            or character.owner_id != current_user_id
        ):
            raise OwnerControlledIdentityNotFoundError(world_id)

        update_owner_controlled_character(
            character, display_name=profile.display_name, avatar_url=profile.avatar_url,
            intro=profile.intro, interests=profile.interests, background=profile.background,
        )
        world_character.role_key = profile.role_key
        world_character.local_profile = _profile_document(profile)
        world_character.version += 1
        world_character.autonomous_enabled = False
        self._db.commit()
        self._db.refresh(character)
        self._db.refresh(world_character)
        return _snapshot(character, world_character)

    def is_owner_controlled_character(self, character_id: str) -> bool:
        return bool(
            self._db.scalar(
                select(WorldCharacter.id)
                .where(
                    WorldCharacter.character_id == character_id,
                    WorldCharacter.control_mode == "owner_controlled",
                    WorldCharacter.status == "active",
                )
                .limit(1)
            )
        )

    def owner_controlled_character_ids(
        self, character_ids: set[str]
    ) -> set[str]:
        if not character_ids:
            return set()
        return set(
            self._db.scalars(
                select(WorldCharacter.character_id).where(
                    WorldCharacter.character_id.in_(character_ids),
                    WorldCharacter.control_mode == "owner_controlled",
                    WorldCharacter.status == "active",
                )
            )
        )

    def _require_local_owner(self, user_id: str) -> None:
        if not is_claimed_local_owner(self._db, user_id):
            raise LocalOwnerRequiredError(user_id)

    def _require_owned_world_membership(self, world_id: str, user_id: str):
        try:
            world = get_world(self._db, world_id)
        except WorldServiceError as exc:
            raise OwnerWorldRequiredError(world_id) from exc
        membership = get_active_membership(
            self._db,
            world_id=world_id,
            user_id=user_id,
        )
        if (
            world.owner_user_id != user_id
            or membership is None
            or membership.role != "owner"
        ):
            raise OwnerWorldRequiredError(world_id)
        return membership

    def _validate_role(self, world_id: str, role_key: str | None) -> None:
        if role_key is None:
            return
        if not is_enabled_world_role(
            self._db,
            world_id=world_id,
            role_key=role_key,
        ):
            raise OwnerControlledRoleInvalidError(role_key)

    def _find_identity(
        self, world_id: str, owner_user_id: str
    ) -> WorldCharacter | None:
        return self._db.scalar(
            select(WorldCharacter).where(
                WorldCharacter.world_id == world_id,
                WorldCharacter.owner_user_id == owner_user_id,
                WorldCharacter.control_mode == "owner_controlled",
                WorldCharacter.status == "active",
            )
        )


def _profile_document(profile: OwnerControlledProfile) -> dict[str, object]:
    return {
        "schema_version": "owner-controlled-profile-v1",
        "preferred_address": profile.preferred_address,
        "interests": list(profile.interests),
        "background": profile.background,
    }


def _snapshot(
    character,
    world_character: WorldCharacter,
) -> OwnerControlledIdentitySnapshot:
    local_profile = (
        world_character.local_profile
        if isinstance(world_character.local_profile, dict)
        else {}
    )
    interests = local_profile.get("interests")
    return OwnerControlledIdentitySnapshot(
        world_character_id=world_character.id,
        world_id=world_character.world_id,
        character_id=character.id,
        control_mode="owner_controlled",
        status=world_character.status,
        autonomous_enabled=False,
        version=world_character.version,
        profile=OwnerControlledProfile(
            display_name=character.name,
            avatar_url=character.avatar_url,
            intro=character.one_liner,
            role_key=world_character.role_key,
            preferred_address=str(local_profile.get("preferred_address") or ""),
            interests=tuple(
                str(value)
                for value in interests
                if isinstance(value, str)
            )
            if isinstance(interests, list)
            else (),
            background=str(local_profile.get("background") or ""),
        ),
    )


__all__ = ["OwnerControlledIdentityService"]


def is_owner_controlled_character(db: Session, character_id: str) -> bool:
    return OwnerControlledIdentityService(db).is_owner_controlled_character(character_id)


def owner_controlled_character_ids(db: Session, character_ids: set[str]) -> set[str]:
    return OwnerControlledIdentityService(db).owner_controlled_character_ids(character_ids)
