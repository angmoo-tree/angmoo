"""Retire old SNS identities before scheduling, restore reuse or a new claim."""
from datetime import UTC, datetime
from types import SimpleNamespace

from sqlalchemy import JSON, or_, select, update

from app.domains.world_characters.activity_models import ActivityEnginePolicy, ActivityGraphRun
from app.domains.world_characters.contracts.activity_retirement import (
    ActivityTransition, HISTORICAL_TERMINAL, LEGACY_ABANDONED, retired_identity,
)
from app.domains.world_characters.models import WorldCharacter
from app.domains.routines.service.legacy_claims import claim_hold, settle_expired_claims


def old_runs(db, actor):
    return [row for row in db.scalars(select(ActivityGraphRun).where(
        ActivityGraphRun.world_character_id == actor.id, ActivityGraphRun.world_id == actor.world_id)
        .order_by(ActivityGraphRun.started_at).with_for_update())
        if retired_identity(row.engine, row.contract_version) and row.status not in HISTORICAL_TERMINAL]


def effect_hold(db, actor):
    from app.domains.social.models.topics import RecommendationDelivery
    if db.scalar(select(RecommendationDelivery.id).where(RecommendationDelivery.world_id == actor.world_id,
            RecommendationDelivery.world_character_id == actor.id,
            RecommendationDelivery.state.in_(("dispatched", "uncertain"))).limit(1)) is not None:
        return "legacy_feed_delivery_unconfirmed"
    from app.domains.relationships.models.personalization import RelationshipMetricApplication, RelationshipExperienceReceipt
    if db.scalar(select(RelationshipMetricApplication.id).join(RelationshipExperienceReceipt,
            RelationshipMetricApplication.experience_id == RelationshipExperienceReceipt.id).where(
                RelationshipExperienceReceipt.world_id == actor.world_id,
                RelationshipExperienceReceipt.actor_world_character_id == actor.id,
                RelationshipMetricApplication.status == "pending").limit(1)) is not None:
        return "legacy_relationship_effect_pending"
    return None


def retire_actor(db, actor, *, now, entry_run_id=None):
    rows = old_runs(db, actor)
    if not rows:
        return ActivityTransition("settled")
    ids = [row.activity_id for row in rows]
    reason = claim_hold(db, character_id=actor.character_id, run_ids=ids, now=now,
                        entry_run_id=entry_run_id if entry_run_id not in ids else None)
    reason = reason or effect_hold(db, actor)
    if reason:
        return ActivityTransition("pending_settlement", reason)
    # Retirement changes only terminal facts, never success effects, snapshots,
    # retention tags, consumed recovery reservations or the historical identity.
    settle_expired_claims(db, run_ids=ids, now=now, reason=LEGACY_ABANDONED)
    for row in rows:
        previous = row.result
        payload = {**(previous or {}), "reason": LEGACY_ABANDONED,
                   "retirement": {"reason": LEGACY_ABANDONED, "retired_at": now.isoformat()}}
        count = db.execute(update(ActivityGraphRun).where(ActivityGraphRun.activity_id == row.activity_id,
            ActivityGraphRun.status == row.status,
            (ActivityGraphRun.result == previous if previous is not None else
             or_(ActivityGraphRun.result.is_(None), ActivityGraphRun.result == JSON.NULL))).values(
                status="abandoned", stage="Retired", finished_at=now, result=payload)
            .execution_options(synchronize_session=False)).rowcount
        if count != 1:
            raise ValueError("legacy_activity_retirement_conflict")
        db.expire(row)
    db.flush()
    return ActivityTransition("settled", abandoned_count=len(rows))


def v2_readiness(db, actor, *, now):
    """Read existing approved setup and plans; never generate or approve."""
    from app.domains.world_characters.service.approved_setup import get_approved_pair
    from app.domains.world_characters.policies.approved_setup import approved_pair_matches_world
    from app.domains.worlds.models import World
    world = db.get(World, actor.world_id)
    pair = get_approved_pair(db, actor.id)
    if world is None or pair is None or not approved_pair_matches_world(
            actor, pair[0], pair[1], world_hash=world.contract_hash):
        return "legacy_v2_setup_not_ready"
    from app.runtime.daily_preparation import read_preparation
    from app.domains.routines.service.daily_preparation import PreparationConflict
    from app.domains.characters.models import Character
    character = db.get(Character, actor.character_id)
    if character is None:
        return "legacy_v2_setup_not_ready"
    try:
        preparation = read_preparation(db, character_id=actor.character_id, world_id=actor.world_id,
            user=SimpleNamespace(id=character.owner_id), now=now)
    except (PreparationConflict, ValueError, LookupError):
        return "legacy_v2_preparation_not_ready"
    if preparation.plan_state != "ready" or preparation.topic_state != "ready":
        return "legacy_v2_preparation_not_ready"
    return None


def policy_actors(db, policy):
    query = select(WorldCharacter).where(WorldCharacter.control_mode == "autonomous", WorldCharacter.status == "active")
    if policy.world_character_id:
        query = query.where(WorldCharacter.id == policy.world_character_id)
    elif policy.world_id:
        query = query.where(WorldCharacter.world_id == policy.world_id)
    return list(db.scalars(query.order_by(WorldCharacter.id)))


def transition_actor(db, actor, *, now=None, entry_run_id=None, readiness=v2_readiness):
    now = now or datetime.now(UTC)
    outcome = retire_actor(db, actor, now=now, entry_run_id=entry_run_id)
    if outcome.state != "settled":
        return outcome
    from app.domains.world_characters.service.activity_engines import resolve_engine, set_engine
    effective = resolve_engine(db, actor)
    if effective["engine"] != "current":
        return ActivityTransition("ready", abandoned_count=outcome.abandoned_count)
    key = f"character:{actor.id}" if effective["source"] == "character" else f"world:{actor.world_id}" if effective["source"] == "world" else "global"
    policy = db.get(ActivityEnginePolicy, key, populate_existing=True)
    if policy is None or policy.engine != "current" or policy.version != effective["version"]:
        return ActivityTransition("pending_conversion", "engine_policy_conflict", outcome.abandoned_count)
    affected = policy_actors(db, policy)
    for affected_actor in affected:
        # More specific overrides are not changed by this shared conversion.
        if resolve_engine(db, affected_actor)["source"] != effective["source"]:
            continue
        if old_runs(db, affected_actor):
            return ActivityTransition("pending_settlement", "legacy_shared_scope_pending", outcome.abandoned_count)
        problem = readiness(db, affected_actor, now=now)
        if problem:
            return ActivityTransition("needs_preparation", problem, outcome.abandoned_count)
    try:
        set_engine(db, engine="personalized_graph_v2", expected_version=policy.version,
                   world_id=policy.world_id, actor_id=policy.world_character_id, settled_current=True)
    except ValueError as exc:
        if str(exc) != "engine_policy_conflict":
            raise
        # A conflicting revision must be read again on a later transition; it
        # cannot undo settled historical work or stop independent actors.
        return ActivityTransition("pending_conversion", "engine_policy_conflict", outcome.abandoned_count)
    return ActivityTransition("ready", abandoned_count=outcome.abandoned_count, converted_count=1)


def transition_all(db, *, now=None, readiness=v2_readiness):
    """One startup/restore boundary; blocked actors do not stop other actors."""
    now = now or datetime.now(UTC)
    actors = list(db.scalars(select(WorldCharacter).where(WorldCharacter.control_mode == "autonomous")
                            .order_by(WorldCharacter.id)))
    # Settle identities before examining shared overrides.
    outcomes = {actor.id: retire_actor(db, actor, now=now) for actor in actors}
    for actor in actors:
        if outcomes[actor.id].state == "settled":
            abandoned = outcomes[actor.id].abandoned_count
            converted = transition_actor(db, actor, now=now, readiness=readiness)
            outcomes[actor.id] = ActivityTransition(converted.state, converted.reason,
                abandoned + converted.abandoned_count, converted.converted_count)
    db.flush()
    return outcomes


def transition_uow(db, *, actor_id=None, entry_run_id=None, now=None, readiness=v2_readiness):
    """Enter with no transaction so SQLite validation precedes the writer CAS."""
    if db.in_transaction():
        raise ValueError("legacy_transition_requires_clean_session")
    def apply():
        if actor_id is None:
            return transition_all(db, now=now, readiness=readiness)
        actor = db.get(WorldCharacter, actor_id, populate_existing=True)
        if actor is None:
            raise ValueError("legacy_transition_actor_missing")
        return transition_actor(db, actor, now=now, entry_run_id=entry_run_id, readiness=readiness)
    if db.get_bind().dialect.name == "sqlite":
        from app.core.sqlite_concurrency import run_sqlite_session_immediate
        return run_sqlite_session_immediate(db, apply, require_clean=True)
    try:
        result = apply()
        db.commit()
        return result
    except BaseException:
        db.rollback()
        raise


def inspect_transition(db, actor, *, now=None):
    """Read-only UI status; it cannot authorize conversion or settle a claim."""
    now = now or datetime.now(UTC)
    rows = [row for row in db.scalars(select(ActivityGraphRun).where(
        ActivityGraphRun.world_character_id == actor.id, ActivityGraphRun.world_id == actor.world_id))
        if retired_identity(row.engine, row.contract_version) and row.status not in HISTORICAL_TERMINAL]
    if rows:
        reason = claim_hold(db, character_id=actor.character_id, run_ids=[row.activity_id for row in rows],
                            now=now, lock=False) or effect_hold(db, actor) or "legacy_transition_required"
        return {"state": "pending_settlement", "reason": reason}
    from app.domains.world_characters.service.activity_engines import resolve_engine
    effective = resolve_engine(db, actor)
    if effective["engine"] == "current":
        key = f"character:{actor.id}" if effective["source"] == "character" else f"world:{actor.world_id}" if effective["source"] == "world" else "global"
        policy = db.get(ActivityEnginePolicy, key)
        if policy is None or policy.version != effective["version"]:
            return {"state": "pending_conversion", "reason": "engine_policy_conflict"}
        for affected in policy_actors(db, policy):
            if resolve_engine(db, affected)["source"] != effective["source"]:
                continue
            pending = db.scalars(select(ActivityGraphRun).where(
                ActivityGraphRun.world_character_id == affected.id, ActivityGraphRun.world_id == affected.world_id))
            if any(retired_identity(row.engine, row.contract_version) and row.status not in HISTORICAL_TERMINAL for row in pending):
                return {"state": "pending_settlement", "reason": "legacy_shared_scope_pending"}
            reason = v2_readiness(db, affected, now=now)
            if reason:
                return {"state": "needs_preparation", "reason": reason}
        return {"state": "pending_conversion", "reason": "legacy_transition_required"}
    return {"state": "ready", "reason": None}
