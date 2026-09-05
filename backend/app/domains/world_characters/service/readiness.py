from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.world_characters import models
from app.domains.characters import schemas
from app.domains.world_characters.contracts.readiness import ReadinessCharacter, ReadinessSetting
from app.domains.worlds.service import character_entry as world_entry
from app.domains.world_characters.service import setup_validation as world_character_contracts


def _has_legacy_tendency_analysis(setting: ReadinessSetting) -> bool:
    profile = (
        setting.planner_tendency_profile
        if isinstance(setting.planner_tendency_profile, dict)
        else {}
    )
    criteria = profile.get("feed_seed_interest_criteria")
    return bool(
        setting.tendency_updated_at
        and setting.tendency_summary.strip()
        and setting.tendency_action_ranges
        and isinstance(criteria, str)
        and criteria.strip()
    )


def evaluate(
    db: Session,
    *,
    character: ReadinessCharacter,
    setting: ReadinessSetting,
) -> schemas.AgentActivityProfileReadinessRead:
    """Return the single readiness contract used by UI and resident execution."""

    active_world = db.get(models.CharacterActiveWorld, character.id)
    if active_world is None:
        ready = _has_legacy_tendency_analysis(setting)
        return schemas.AgentActivityProfileReadinessRead(
            ready=ready,
            source="legacy_tendency",
            reason_code=None if ready else "legacy_tendency_not_ready",
        )
    world_character = db.get(models.WorldCharacter, active_world.world_character_id)
    if world_character is None or world_character.character_id != character.id:
        return schemas.AgentActivityProfileReadinessRead(
            ready=False,
            source="world_community_profile",
            reason_code="world_character_not_ready",
            world_character_id=active_world.world_character_id,
        )
    if world_character.activity_runtime_mode != "routine_resident_v1":
        ready = _has_legacy_tendency_analysis(setting)
        return schemas.AgentActivityProfileReadinessRead(
            ready=ready,
            source="legacy_tendency",
            reason_code=None if ready else "legacy_tendency_not_ready",
        )

    base = {
        "source": "world_community_profile",
        "world_id": world_character.world_id,
        "world_character_id": world_character.id,
    }
    if world_character.status != "active":
        return schemas.AgentActivityProfileReadinessRead(
            ready=False,
            reason_code="world_character_not_ready",
            **base,
        )
    world = world_entry.get_character_entry_world(db, world_character.world_id)
    membership = world_entry.get_character_entry_membership(db, world_character.membership_id)
    if (
        world is None
        or world.status != "published"
        or world.readiness_status != "publish_ready"
        or membership is None
        or membership.world_id != world_character.world_id
        or membership.user_id != character.owner_id
        or membership.status != "active"
    ):
        return schemas.AgentActivityProfileReadinessRead(
            ready=False,
            reason_code="world_scope_not_ready",
            **base,
        )
    repertoire = db.scalar(
        select(models.WorldActivityRepertoire)
        .where(
            models.WorldActivityRepertoire.world_character_id == world_character.id,
            models.WorldActivityRepertoire.status == "ready",
        )
        .order_by(
            models.WorldActivityRepertoire.approved_at.desc(),
            models.WorldActivityRepertoire.generated_at.desc(),
        )
    )
    if repertoire is None:
        return schemas.AgentActivityProfileReadinessRead(
            ready=False,
            reason_code="world_activity_repertoire_not_ready",
            **base,
        )
    profile = db.get(models.WorldCommunityProfile, repertoire.community_profile_id)
    if (
        profile is None
        or profile.world_character_id != world_character.id
        or profile.status != "ready"
    ):
        return schemas.AgentActivityProfileReadinessRead(
            ready=False,
            reason_code="world_community_profile_not_ready",
            **base,
        )
    character_hash = world_character_contracts.character_contract_hash(character)
    if (
        world_character.character_contract_hash != character_hash
        or world_character.world_contract_hash != world.contract_hash
        or repertoire.character_contract_hash != character_hash
        or repertoire.world_contract_hash != world.contract_hash
        or profile.character_contract_hash != character_hash
        or profile.world_contract_hash != world.contract_hash
    ):
        return schemas.AgentActivityProfileReadinessRead(
            ready=False,
            reason_code="world_activity_profile_stale",
            **base,
        )
    candidate_counts = dict(
        db.execute(
            select(
                models.WorldActivityCandidate.daypart,
                func.count(models.WorldActivityCandidate.id),
            )
            .where(
                models.WorldActivityCandidate.repertoire_id == repertoire.id,
                models.WorldActivityCandidate.enabled.is_(True),
            )
            .group_by(models.WorldActivityCandidate.daypart)
        ).all()
    )
    if candidate_counts != {
        daypart: 10 for daypart in world_character_contracts.DAYPARTS
    }:
        return schemas.AgentActivityProfileReadinessRead(
            ready=False,
            reason_code="world_activity_repertoire_not_ready",
            **base,
        )
    return schemas.AgentActivityProfileReadinessRead(
        ready=True,
        reason_code=None,
        **base,
    )
