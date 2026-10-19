"""WorldCharacters owns the bounded unfinished activity interruption record."""
from sqlalchemy import select
from app.domains.world_characters.activity_models import ActivityGraphRun
from app.domains.world_characters.models import WorldCharacter


def unfinished(db, *, owner_id, character_id):
    # Ownership is established by the Routines run/slot UoW; scope matches the
    # graph's own canonical actor, not an arbitrary client-supplied activity.
    from app.domains.characters.service import owns_active_character
    if not owns_active_character(db, owner_id=owner_id, character_id=character_id):
        return None
    return db.scalar(select(ActivityGraphRun).join(WorldCharacter,
        WorldCharacter.id == ActivityGraphRun.world_character_id).where(
        WorldCharacter.character_id == character_id,
        ActivityGraphRun.engine == "personalized_graph_v2", ActivityGraphRun.contract_version == 2,
        ActivityGraphRun.status.in_(("running", "waiting", "interrupted")),
    ).order_by(ActivityGraphRun.started_at).limit(1))


def interrupt(db, *, owner_id, character_id, lease_run_id, reason, now):
    row = unfinished(db, owner_id=owner_id, character_id=character_id)
    if row is None:
        return None
    row.status = "interrupted"
    row.result = {**(row.result or {}), "_interruption": {"revision":"activity-interruption.v1",
        "reason":str(reason), "lease_run_id":lease_run_id, "cancelled_at":now.isoformat()}}
    db.flush()
    return row


def remember_routine(db, *, activity_id, actor_id, beat_id):
    row = db.get(ActivityGraphRun, activity_id, populate_existing=True)
    if row is None or row.world_character_id != actor_id or row.status not in {"running", "waiting", "interrupted"}:
        raise ValueError("activity_recovery_binding_invalid")
    row.result = {**(row.result or {}), "_routine_recovery": {"revision":"routine-recovery.v1", "beat_id":beat_id}}
    db.commit()
