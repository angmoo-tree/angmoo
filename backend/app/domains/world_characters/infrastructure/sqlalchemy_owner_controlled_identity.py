from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.ids import uuid7_string
from app.domains.characters.public import Character
from app.domains.identity.public import InstallationIdentity, LOCAL_INSTALLATION_KEY
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
from app.domains.worlds.public import (
    WorldServiceError,
    get_active_membership,
    get_world,
    is_enabled_world_role,
)


class SqlAlchemyOwnerControlledIdentityRepository:
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
        character = self._db.get(Character, world_character.character_id)
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
    ) -> tuple[Character, WorldCharacter]:
        """Flush owner-controlled identity rows under a caller-owned UoW."""

        self._require_local_owner(current_user_id)
        membership = self._require_owned_world_membership(world_id, current_user_id)
        self._validate_role(world_id, profile.role_key)
        if self._find_identity(world_id, current_user_id) is not None:
            raise OwnerControlledIdentityConflictError(world_id)

        character_id = uuid7_string()
        world_character_id = uuid7_string()
        character = Character(
            id=character_id,
            owner_id=current_user_id,
            name=profile.display_name,
            handle=f"owner-{character_id[-20:]}",
            avatar_url=profile.avatar_url,
            banner_url=None,
            one_liner=profile.intro,
            personality="",
            speech_style="",
            worldview="",
            topic_preferences=", ".join(profile.interests),
            safety_rules="",
            status="active",
            execution_mode="local",
            promotion_usage_allowed=False,
            persona_summary=profile.background or profile.intro,
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
        self._db.add(character)
        self._db.flush()
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
        character = self._db.get(Character, world_character.character_id)
        if (
            character is None
            or character.deleted_at is not None
            or character.owner_id != current_user_id
        ):
            raise OwnerControlledIdentityNotFoundError(world_id)

        character.name = profile.display_name
        character.avatar_url = profile.avatar_url
        character.one_liner = profile.intro
        character.topic_preferences = ", ".join(profile.interests)
        character.persona_summary = profile.background or profile.intro
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
        installation = self._db.get(
            InstallationIdentity, LOCAL_INSTALLATION_KEY
        )
        if (
            installation is None
            or installation.bootstrap_state != "claimed"
            or installation.owner_user_id != user_id
        ):
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
    character: Character,
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


__all__ = ["SqlAlchemyOwnerControlledIdentityRepository"]
