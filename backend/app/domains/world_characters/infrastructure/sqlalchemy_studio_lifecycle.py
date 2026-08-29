from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.domains.characters.public import Character
from app.domains.world_characters.domain.studio_lifecycle import (
    CandidateReason,
    StudioCharacterCandidate,
    StudioWorldCharacterConflictError,
    StudioWorldCharacterForbiddenError,
    StudioWorldCharacterNotFoundError,
    StudioWorldCharacterValidationError,
    WorldCharacterLeaveResult,
)
from app.domains.world_characters.infrastructure.sqlalchemy_models import (
    CharacterActiveWorld,
    WorldCharacter,
)
from app.domains.world_characters.ports.studio_lifecycle import (
    WorldCharacterLeaveRuntimeGuard,
)
from app.domains.worlds.public import require_creator_access


class _CurrentUser:
    def __init__(self, user_id: str) -> None:
        self.id = user_id


class SqlAlchemyStudioWorldCharacterLifecycle:
    def __init__(
        self,
        db: Session,
        *,
        runtime_guard: WorldCharacterLeaveRuntimeGuard | None = None,
    ) -> None:
        self.db = db
        self.runtime_guard = runtime_guard

    def list_candidates(
        self,
        *,
        world_id: str,
        current_user_id: str,
    ) -> tuple[StudioCharacterCandidate, ...]:
        require_creator_access(
            self.db,
            world_id=world_id,
            user=_CurrentUser(current_user_id),
        )
        rows = self.db.execute(
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
        return tuple(
            self._candidate(character, world_character)
            for character, world_character in rows
        )

    @staticmethod
    def _candidate(
        character: Character,
        world_character: WorldCharacter | None,
    ) -> StudioCharacterCandidate:
        reason: CandidateReason | None = None
        if character.moderation_status != "active":
            reason = "character_moderation_inactive"
        elif character.execution_mode != "llm":
            reason = "local_execution_mode_unsupported"
        elif world_character is not None:
            if world_character.status in {"pending", "inactive", "active"}:
                reason = "already_linked"
            elif world_character.status == "left":
                reason = "world_character_left_restore_unsupported"
            else:
                reason = "world_character_ineligible"
        return StudioCharacterCandidate(
            character_id=character.id,
            display_name=character.name,
            handle=character.handle,
            avatar_url=character.avatar_url,
            current_world_status=(
                world_character.status if world_character is not None else None
            ),
            eligible=reason is None,
            reason_code=reason,
        )

    def leave(
        self,
        *,
        world_id: str,
        character_id: str,
        current_user_id: str,
        world_character_id: str,
        expected_version: int,
        confirmation_name: str,
        idempotency_key: str,
    ) -> WorldCharacterLeaveResult:
        require_creator_access(
            self.db,
            world_id=world_id,
            user=_CurrentUser(current_user_id),
        )
        world_character = self.db.scalar(
            select(WorldCharacter)
            .where(
                WorldCharacter.id == world_character_id,
                WorldCharacter.world_id == world_id,
                WorldCharacter.character_id == character_id,
            )
            .with_for_update()
        )
        if world_character is None:
            raise StudioWorldCharacterNotFoundError()
        character = self.db.get(Character, character_id)
        if character is None or character.deleted_at is not None:
            raise StudioWorldCharacterNotFoundError()
        if character.owner_id != current_user_id:
            raise StudioWorldCharacterForbiddenError()
        if world_character.control_mode != "autonomous":
            raise StudioWorldCharacterValidationError(
                "owner_controlled_world_character_protected"
            )
        if confirmation_name.strip() != character.name:
            raise StudioWorldCharacterValidationError("confirmation_name_mismatch")

        local_profile = dict(world_character.local_profile or {})
        if world_character.status == "left":
            if local_profile.get("leave_idempotency_key") == idempotency_key:
                return self._leave_result(world_character, replayed=True)
            raise StudioWorldCharacterValidationError(
                "world_character_left_restore_unsupported"
            )
        if world_character.version != expected_version:
            raise StudioWorldCharacterConflictError(
                "stale_world_character_version"
            )
        if world_character.status not in {"pending", "inactive", "active"}:
            raise StudioWorldCharacterValidationError("world_character_ineligible")
        if world_character.autonomous_enabled:
            raise StudioWorldCharacterConflictError(
                "world_character_autonomy_enabled"
            )

        active_world = self.db.get(CharacterActiveWorld, character_id)
        selected_active_world = bool(
            active_world is not None
            and active_world.world_character_id == world_character.id
        )
        if self.runtime_guard is not None:
            self.runtime_guard.require_idle(
                owner_user_id=current_user_id,
                character_id=character_id,
                world_character_id=world_character.id,
                selected_active_world=selected_active_world,
            )

        if selected_active_world and active_world is not None:
            self.db.delete(active_world)
            character.status = "inactive"
        local_profile.update(
            {
                "leave_idempotency_key": idempotency_key,
                "leave_expected_version": expected_version,
                "left_at": datetime.now(UTC).isoformat(),
            }
        )
        world_character.status = "left"
        world_character.autonomous_enabled = False
        world_character.local_profile = local_profile
        world_character.version += 1
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        self.db.refresh(world_character)
        return self._leave_result(world_character, replayed=False)

    @staticmethod
    def _leave_result(
        world_character: WorldCharacter,
        *,
        replayed: bool,
    ) -> WorldCharacterLeaveResult:
        return WorldCharacterLeaveResult(
            world_character_id=world_character.id,
            world_id=world_character.world_id,
            character_id=world_character.character_id,
            status="left",
            autonomous_enabled=False,
            version=world_character.version,
            scheduler_assignment_released=True,
            history_preserved=True,
            replayed=replayed,
        )


__all__ = ["SqlAlchemyStudioWorldCharacterLifecycle"]
