"""SQLite-owned semantic repair for PR G autonomous runtime modes."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Collection
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.sqlite_concurrency import run_sqlite_session_immediate
from app.domains.world_characters.domain.runtime_modes import (
    AUTONOMOUS_ACTIVITY_RUNTIME_MODE,
    AUTONOMOUS_FEED_RUNTIME_MODE,
    LEGACY_FEED_RUNTIME_MODE,
    is_affected_local_entry_runtime_pair,
)
from app.domains.world_characters.infrastructure import (
    autonomous_setup_contracts as world_character_contracts,
    autonomous_setup_models as models,
)
@dataclass(frozen=True, slots=True)
class AutonomousRuntimeModeRepairResult:
    scanned_count: int
    repaired_count: int
    skipped_reasons: tuple[tuple[str, int], ...]


def reconcile_local_autonomous_runtime_modes(
    session_factory: Callable[[], Session],
    *,
    excluded_world_ids: Collection[str] = (),
) -> AutonomousRuntimeModeRepairResult:
    """Repair only proven PR G local rows before embedded workers start."""

    with session_factory() as db:
        return run_sqlite_session_immediate(
            db,
            lambda: repair_affected_local_autonomous_runtime_modes(
                db,
                excluded_world_ids=excluded_world_ids,
            ),
        )


def repair_affected_local_autonomous_runtime_modes(
    db: Session,
    *,
    excluded_world_ids: Collection[str] = (),
) -> AutonomousRuntimeModeRepairResult:
    """Apply one caller-owned, idempotent semantic repair transaction."""

    candidates = list(
        db.scalars(
            select(models.WorldCharacter)
            .where(
                models.WorldCharacter.control_mode == "autonomous",
                models.WorldCharacter.owner_user_id.is_(None),
                models.WorldCharacter.activity_runtime_mode
                == AUTONOMOUS_ACTIVITY_RUNTIME_MODE,
                models.WorldCharacter.feed_runtime_mode
                == LEGACY_FEED_RUNTIME_MODE,
                models.WorldCharacter.status.in_({"pending", "inactive", "active"}),
            )
            .order_by(models.WorldCharacter.id)
        )
    )
    skipped: Counter[str] = Counter()
    repaired_count = 0
    repaired_at = datetime.now(UTC)
    excluded_world_id_set = frozenset(excluded_world_ids)
    for world_character in candidates:
        outcome = repair_local_autonomous_runtime_mode(
            db,
            world_character=world_character,
            repaired_at=repaired_at,
            excluded_world_ids=excluded_world_id_set,
        )
        if outcome != "repaired":
            skipped[outcome] += 1
            continue
        repaired_count += 1
    if repaired_count:
        db.flush()
    return AutonomousRuntimeModeRepairResult(
        scanned_count=len(candidates),
        repaired_count=repaired_count,
        skipped_reasons=tuple(sorted(skipped.items())),
    )


def repair_local_autonomous_runtime_mode(
    db: Session,
    *,
    world_character: models.WorldCharacter,
    repaired_at: datetime | None = None,
    excluded_world_ids: Collection[str] = (),
) -> str:
    """Repair one exact PR G row and return a privacy-safe outcome code."""

    if world_character.feed_runtime_mode == AUTONOMOUS_FEED_RUNTIME_MODE:
        return "already_ready"
    reason = _repair_ineligibility_reason(
        db,
        world_character,
        excluded_world_ids=excluded_world_ids,
    )
    if reason is not None:
        return reason
    world_character.feed_runtime_mode = AUTONOMOUS_FEED_RUNTIME_MODE
    world_character.version += 1
    world_character.updated_at = repaired_at or datetime.now(UTC)
    db.flush()
    return "repaired"


def _repair_ineligibility_reason(
    db: Session,
    world_character: models.WorldCharacter,
    *,
    excluded_world_ids: Collection[str],
) -> str | None:
    if not is_affected_local_entry_runtime_pair(
        control_mode=world_character.control_mode,
        owner_user_id=world_character.owner_user_id,
        activity_runtime_mode=world_character.activity_runtime_mode,
        feed_runtime_mode=world_character.feed_runtime_mode,
        local_profile=world_character.local_profile,
    ):
        return "source_marker_missing"
    character = db.get(models.Character, world_character.character_id)
    membership = db.get(models.WorldMembership, world_character.membership_id)
    world = db.get(models.World, world_character.world_id)
    if (
        character is None
        or character.deleted_at is not None
        or character.moderation_status != "active"
    ):
        return "character_ineligible"
    if (
        membership is None
        or membership.world_id != world_character.world_id
        or membership.user_id != character.owner_id
        or membership.status != "active"
    ):
        return "membership_ineligible"
    if (
        world is None
        or world.status != "published"
        or world.readiness_status != "publish_ready"
    ):
        return "world_ineligible"
    if world_character.world_id in excluded_world_ids:
        return "imported_world"
    role = db.scalar(
        select(models.WorldRole).where(
            models.WorldRole.world_id == world_character.world_id,
            models.WorldRole.role_key == world_character.role_key,
            models.WorldRole.status == "enabled",
            models.WorldRole.autonomous_allowed.is_(True),
        )
    )
    if role is None:
        return "role_ineligible"
    character_hash = world_character_contracts.character_contract_hash(character)
    if (
        world_character.character_contract_hash != character_hash
        or world_character.world_contract_hash != world.contract_hash
    ):
        return "world_character_contract_stale"
    profile = db.scalar(
        select(models.WorldCommunityProfile).where(
            models.WorldCommunityProfile.world_character_id == world_character.id,
            models.WorldCommunityProfile.status == "ready",
        )
    )
    if (
        profile is None
        or profile.character_contract_hash != character_hash
        or profile.world_contract_hash != world.contract_hash
    ):
        return "profile_not_ready"
    repertoire = db.scalar(
        select(models.WorldActivityRepertoire).where(
            models.WorldActivityRepertoire.world_character_id == world_character.id,
            models.WorldActivityRepertoire.status == "ready",
        )
    )
    if (
        repertoire is None
        or repertoire.community_profile_id != profile.id
        or repertoire.character_contract_hash != character_hash
        or repertoire.world_contract_hash != world.contract_hash
    ):
        return "repertoire_not_ready"
    daypart_counts = dict(
        db.execute(
            select(
                models.WorldActivityCandidate.daypart,
                func.count(models.WorldActivityCandidate.id),
            )
            .where(models.WorldActivityCandidate.repertoire_id == repertoire.id)
            .group_by(models.WorldActivityCandidate.daypart)
        ).all()
    )
    if daypart_counts != {
        "dawn": 10,
        "morning": 10,
        "afternoon": 10,
        "evening": 10,
    }:
        return "repertoire_candidate_count_invalid"
    return None


__all__ = [
    "AutonomousRuntimeModeRepairResult",
    "reconcile_local_autonomous_runtime_modes",
    "repair_local_autonomous_runtime_mode",
    "repair_affected_local_autonomous_runtime_modes",
]
