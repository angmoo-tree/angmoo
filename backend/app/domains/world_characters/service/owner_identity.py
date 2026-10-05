from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.ids import uuid7_string
from app.domains.characters.service.profile import get_character
from app.domains.characters.service.owner_controlled import (
    seed_owner_controlled_character,
)
from app.domains.world_characters.configuration_models import WorldCharacterConfiguration
from app.domains.world_characters.service.configuration import effective_configuration, initialize_configuration
from app.domains.characters.contracts import ImportConfiguration, ImportProfile, ImportSettings
from app.domains.characters.service.import_snapshots import capture_creation
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
from app.domains.world_characters.exceptions import OwnerProfileSelectionRequiredError
from app.domains.worlds.service import (
    WorldServiceError,
    get_active_membership,
    get_world,
    is_enabled_world_role,
)


class OwnerControlledIdentityService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def ensure(self, *, world_id: str, current_user_id: str):
        self._require_local_owner(current_user_id)
        self._require_owned_world_membership(world_id, current_user_id)
        identities = self.list_identities(world_id=world_id, current_user_id=current_user_id)
        active = next((identity for identity in identities if identity.status == "active"), None)
        if active is not None:
            return active
        if identities:
            raise OwnerProfileSelectionRequiredError(world_id)
        try:
            return self.create(world_id=world_id, current_user_id=current_user_id,
                               profile=OwnerControlledProfile("사용자", None, "", None, "", (), ""))
        except OwnerControlledIdentityConflictError:
            if self._find_identity(world_id, current_user_id) is None:
                raise
            return self.get(world_id=world_id, current_user_id=current_user_id)

    def patch(self, *, world_id: str, current_user_id: str, data):
        from app.domains.identity.service.environment import lock_environment_admission
        lock_environment_admission(self._db, current_user_id)
        self.get(world_id=world_id, current_user_id=current_user_id)
        row = self._find_identity(world_id, current_user_id)
        character = get_character(self._db, row.character_id)
        changes = data.model_dump(exclude_unset=True, exclude={"version"})
        from app.domains.characters.service.profile import normalize_character_handle
        from app.policies import name_policy
        if "display_name" in changes and name_policy.is_blocked_name(changes["display_name"]):
            raise ValueError("사용할 수 없는 이름입니다.")
        stored = self._db.get(WorldCharacterConfiguration, row.id)
        if stored is None:
            raise OwnerControlledIdentityConflictError("world_configuration_missing")
        if "handle" in changes:
            changes["handle"] = normalize_character_handle(changes["handle"])
            profiles = self._db.execute(select(WorldCharacter.id, WorldCharacterConfiguration.profile).join(
                WorldCharacterConfiguration, WorldCharacterConfiguration.world_character_id == WorldCharacter.id)
                .where(WorldCharacter.world_id == world_id, WorldCharacter.id != row.id)).all()
            if any(profile.get("handle") == changes["handle"] for _, profile in profiles):
                raise OwnerControlledIdentityConflictError("profile_handle_conflict")
        from app.config import settings
        from app.integrations.media.files import media_url_to_path
        for field in ("avatar_url", "banner_url"):
            value = changes.get(field)
            if value and value != stored.profile.get(field):
                path = media_url_to_path(value).resolve()
                path.relative_to((settings.media_root_path / "characters" / character.id).resolve())
                if not path.is_file():
                    raise ValueError("profile_media_missing")
        updated = self._db.execute(update(WorldCharacter).where(
            WorldCharacter.id == row.id, WorldCharacter.version == data.version,
        ).values(version=WorldCharacter.version + 1).execution_options(synchronize_session="fetch"))
        if updated.rowcount != 1:
            self._db.rollback()
            raise OwnerControlledIdentityConflictError("profile_version_conflict")
        stored.profile = ImportProfile.model_validate({**stored.profile, **changes}).model_dump(mode="json")
        try:
            self._db.commit()
        except IntegrityError as exc:
            self._db.rollback()
            raise OwnerControlledIdentityConflictError("profile_handle_conflict") from exc
        return self.get(world_id=world_id, current_user_id=current_user_id)

    def upload_media(self, *, world_id: str, current_user_id: str, data):
        from app.domains.characters.service.media_storage import save_profile_media
        from app.domains.world_characters.schemas.identity import MyProfilePatch
        from app.integrations.media.files import media_url_to_path
        current = self.get(world_id=world_id, current_user_id=current_user_id)
        if current.version != data.version:
            raise OwnerControlledIdentityConflictError("profile_version_conflict")
        url = save_profile_media(character_id=current.character_id, media_type=data.media_type,
            content_type=data.content_type, data_base64=data.data_base64)
        try:
            return self.patch(world_id=world_id, current_user_id=current_user_id,
                data=MyProfilePatch(version=data.version, **{f"{data.media_type}_url": url}))
        except Exception:
            self._db.rollback()
            media_url_to_path(url).unlink(missing_ok=True)
            raise

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
        return _snapshot(character, world_character, db=self._db)

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
        return _snapshot(character, world_character, db=self._db)

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
        configuration = ImportConfiguration(profile=ImportProfile(display_name=character.name, handle=character.handle,
            avatar_url=character.avatar_url, banner_url=character.banner_url, intro=character.one_liner or ""),
            settings=ImportSettings(character_background=profile.background, topic_preferences="\n".join(profile.interests)))
        origin = capture_creation(self._db, character_id=character.id, configuration=configuration, provenance="owner_identity_creation_uow")
        initialize_configuration(self._db, world_character=world_character, snapshot_id=origin.id, configuration=configuration)
        return character, world_character

    def list_identities(self, *, world_id: str, current_user_id: str):
        self._require_local_owner(current_user_id)
        self._require_owned_world_membership(world_id, current_user_id)
        rows = self._db.scalars(select(WorldCharacter).where(
            WorldCharacter.world_id == world_id, WorldCharacter.owner_user_id == current_user_id,
            WorldCharacter.control_mode == "owner_controlled", WorldCharacter.status.in_(("active", "inactive"))
        ).order_by(WorldCharacter.created_at, WorldCharacter.id))
        return [_snapshot(character, row, db=self._db) for row in rows
                if (character := get_character(self._db, row.character_id)) is not None and character.deleted_at is None]

    def select_identity(self, *, world_id: str, current_user_id: str, world_character_id: str):
        self._require_local_owner(current_user_id)
        self._require_owned_world_membership(world_id, current_user_id)
        selected = self._db.get(WorldCharacter, world_character_id)
        if (selected is None or selected.world_id != world_id or selected.owner_user_id != current_user_id
            or selected.control_mode != "owner_controlled" or selected.status not in {"active", "inactive"}):
            raise OwnerControlledIdentityNotFoundError(world_character_id)
        character = get_character(self._db, selected.character_id)
        if character is None or character.deleted_at is not None:
            raise OwnerControlledIdentityNotFoundError(world_character_id)
        previous = self._find_identity(world_id, current_user_id)
        if previous is not None and previous.id != selected.id:
            previous.status = "inactive"
            previous.version += 1
            self._db.flush()
        if selected.status != "active":
            selected.status = "active"
            selected.version += 1
        self._db.commit()
        return _snapshot(character, selected, db=self._db)

    def create_replacement(self, *, world_id: str, current_user_id: str, profile):
        self._require_local_owner(current_user_id)
        self._require_owned_world_membership(world_id, current_user_id)
        previous = self._find_identity(world_id, current_user_id)
        try:
            if previous is not None:
                previous.status = "inactive"
                previous.version += 1
                self._db.flush()
            character, row = self.seed_create(world_id=world_id, current_user_id=current_user_id, profile=profile)
            self._db.commit()
            return _snapshot(character, row, db=self._db)
        except Exception:
            self._db.rollback()
            raise

    def update(
        self,
        *,
        world_id: str,
        current_user_id: str,
        profile: OwnerControlledProfile,
    ) -> OwnerControlledIdentitySnapshot:
        from app.domains.identity.service.environment import lock_environment_admission
        lock_environment_admission(self._db, current_user_id)
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

        stored = self._db.get(WorldCharacterConfiguration, world_character.id)
        if stored is None:
            raise OwnerControlledIdentityConflictError("world_configuration_missing")
        stored.profile = ImportProfile.model_validate({**stored.profile, "display_name": profile.display_name,
            "avatar_url": profile.avatar_url, "intro": profile.intro}).model_dump(mode="json")
        stored.settings = ImportSettings.model_validate({**stored.settings, "character_background": profile.background,
            "topic_preferences": "\n".join(profile.interests)}).model_dump(mode="json")
        world_character.role_key = profile.role_key
        world_character.local_profile = _profile_document(profile)
        world_character.version += 1
        world_character.autonomous_enabled = False
        self._db.commit()
        self._db.refresh(character)
        self._db.refresh(world_character)
        return _snapshot(character, world_character, db=self._db)

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
    *, db,
) -> OwnerControlledIdentitySnapshot:
    local_profile = (
        world_character.local_profile
        if isinstance(world_character.local_profile, dict)
        else {}
    )
    interests = local_profile.get("interests")
    effective = effective_configuration(db, world_character_id=world_character.id).profile
    return OwnerControlledIdentitySnapshot(
        world_character_id=world_character.id,
        world_id=world_character.world_id,
        character_id=character.id,
        control_mode="owner_controlled",
        status=world_character.status,
        autonomous_enabled=False,
        version=world_character.version,
        profile=OwnerControlledProfile(
            display_name=effective.display_name,
            handle=effective.handle,
            banner_url=effective.banner_url,
            avatar_url=effective.avatar_url,
            intro=effective.intro,
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
