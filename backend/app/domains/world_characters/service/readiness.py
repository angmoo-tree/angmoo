from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.world_characters import models
from app.domains.characters import schemas
from app.domains.world_characters.contracts.readiness import ReadinessCharacter, ReadinessSetting
from app.domains.worlds.service import character_entry as world_entry
from app.domains.world_characters.service import setup_validation as world_character_contracts
from app.domains.world_characters.policies.approved_setup import approved_pair_matches_world


def _has_legacy_tendency_analysis(setting: ReadinessSetting) -> bool:
    if setting is None:
        return False
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


def evaluate_many(db: Session, *, characters, activity_settings, world_id):
    """The same readiness rules, with a fixed number of dashboard queries."""
    from app.config import settings
    ids = [character.id for character in characters]
    selections = {row.character_id: row for row in db.scalars(select(models.CharacterActiveWorld).where(
        models.CharacterActiveWorld.character_id.in_(ids)))}
    roles = {row.id: row for row in db.scalars(select(models.WorldCharacter).where(
        models.WorldCharacter.id.in_([row.world_character_id for row in selections.values()])))}
    world = world_entry.get_character_entry_world(db, world_id)
    memberships = {row.id: row for row in world_entry.list_character_entry_memberships(db,
        [role.membership_id for role in roles.values()])}
    allowed_roles = {role.role_key for role in world_entry.list_autonomous_entry_roles(db, world_id=world_id)}
    repertoires, profiles, counts = {}, {}, {}
    if not settings.DAILY_PREPARATION_ENABLED:
        candidates = list(db.scalars(select(models.WorldActivityRepertoire).where(
            models.WorldActivityRepertoire.world_character_id.in_(roles), models.WorldActivityRepertoire.status == "ready")
            .order_by(models.WorldActivityRepertoire.approved_at.desc(), models.WorldActivityRepertoire.generated_at.desc())))
        for repertoire in candidates:
            repertoires.setdefault(repertoire.world_character_id, repertoire)
        profiles = {row.id: row for row in db.scalars(select(models.WorldCommunityProfile).where(
            models.WorldCommunityProfile.id.in_([row.community_profile_id for row in repertoires.values()])))}
        for repertoire_id, daypart, count in db.execute(select(models.WorldActivityCandidate.repertoire_id,
            models.WorldActivityCandidate.daypart, func.count(models.WorldActivityCandidate.id)).where(
            models.WorldActivityCandidate.repertoire_id.in_([row.id for row in repertoires.values()]),
            models.WorldActivityCandidate.enabled.is_(True)).group_by(models.WorldActivityCandidate.repertoire_id,
                models.WorldActivityCandidate.daypart)):
            counts.setdefault(repertoire_id, {})[daypart] = count
    result = {}
    for character in characters:
        selection = selections.get(character.id)
        role = roles.get(selection.world_character_id) if selection else None
        base = {"world_id": world_id, "world_character_id": role.id if role else None, "source": "world_community_profile"}
        membership = memberships.get(role.membership_id) if role else None
        reason = None
        if role is None or role.character_id != character.id or role.world_id != world_id or role.status != "active":
            reason = "world_character_not_ready"
        elif not world or world.status != "published" or world.readiness_status != "publish_ready" or not membership or membership.world_id != world_id or membership.user_id != character.owner_id or membership.status != "active":
            reason = "world_scope_not_ready"
        elif role.activity_runtime_mode != "routine_resident_v1":
            setting = activity_settings.get(character.id)
            reason = None if setting and _has_legacy_tendency_analysis(setting) else "legacy_tendency_not_ready"
            base["source"] = "legacy_tendency"
        elif settings.DAILY_PREPARATION_ENABLED:
            base["source"] = "daily_preparation"
            if role.control_mode != "autonomous" or role.role_key not in allowed_roles:
                reason = "world_reference_invalid"
        else:
            repertoire = repertoires.get(role.id)
            profile = profiles.get(repertoire.community_profile_id) if repertoire else None
            if repertoire is None:
                reason = "world_activity_repertoire_not_ready"
            elif profile is None or profile.world_character_id != role.id or profile.status != "ready":
                reason = "world_community_profile_not_ready"
            elif not approved_pair_matches_world(role, profile, repertoire, world_hash=world.contract_hash):
                reason = "world_activity_profile_stale"
            elif counts.get(repertoire.id) != {daypart: 10 for daypart in world_character_contracts.DAYPARTS}:
                reason = "world_activity_repertoire_not_ready"
        result[character.id] = schemas.AgentActivityProfileReadinessRead(ready=reason is None, reason_code=reason, **base)
    return result


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
    from app.config import settings
    if settings.DAILY_PREPARATION_ENABLED:
        role = world_entry.find_autonomous_entry_role(db, world_id=world.id, role_key=world_character.role_key)
        return schemas.AgentActivityProfileReadinessRead(
            ready=role is not None and world_character.control_mode == "autonomous",
            source="daily_preparation", world_id=world.id, world_character_id=world_character.id,
            reason_code=None if role else "world_reference_invalid")
    repertoire = db.scalar(
        # Historical policy below remains readable while rollout is withheld.
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
    if not approved_pair_matches_world(
        world_character, profile, repertoire, world_hash=world.contract_hash,
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
