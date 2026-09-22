"""State settlement; caller owns commit, scope validation and claim fencing."""
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.domains.world_characters.activity_models import ActivityStateReceipt, CharacterActivityState
from app.domains.world_characters.models import WorldCharacter
from app.domains.world_characters.schemas.activity_state import StateUpdate


def utc(value: datetime | None) -> datetime | None:
    return None if value is None else value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def read_state(db: Session, *, world_id: str, actor_id: str) -> dict:
    actor = db.get(WorldCharacter, actor_id)
    if actor is None or actor.world_id != world_id:
        raise ValueError("activity_state_scope_invalid")
    row = db.get(CharacterActivityState, actor_id, populate_existing=True)
    if row is None:
        return {"known": False, "version": 0, "mood": None, "mood_intensity": None, "state_note": None, "changed_at": None, "confirmed_at": None}
    return {"known": row.mood is not None, "version": row.version,
            "mood": row.mood, "mood_intensity": row.mood_intensity, "state_note": row.state_note,
            "changed_at": utc(row.changed_at).isoformat() if row.changed_at else None,
            "confirmed_at": utc(row.confirmed_at).isoformat() if row.confirmed_at else None}


def settle_state(db: Session, *, world_id: str, actor_id: str, activity_id: str,
                 decision_key: str, expected_version: int, proposal: StateUpdate | None,
                 judged_at: datetime, source_keys: list[str], valid_source_keys: set[str],
                 context_reassessment: bool = False) -> str:
    """CAS and receipt in caller's transaction; never retry AI for a conflict.

    Evidence keys come from validated current observations, not retrieval hits.
    Already interpreted observations may be context but cannot reapply a state.
    """
    snapshot = read_state(db, world_id=world_id, actor_id=actor_id)
    receipt = db.get(ActivityStateReceipt, decision_key)
    if receipt:
        if (receipt.world_id, receipt.world_character_id, receipt.activity_id) != (world_id, actor_id, activity_id):
            raise ValueError("activity_state_receipt_scope_invalid")
        return receipt.outcome
    if not set(source_keys) <= valid_source_keys or (not source_keys and not context_reassessment):
        return "invalid_evidence"
    used = set()
    if source_keys:
        for keys in db.scalars(select(ActivityStateReceipt.source_keys).where(
            ActivityStateReceipt.world_character_id == actor_id,
            ActivityStateReceipt.outcome.in_(("updated", "kept")),
        )):
            used.update(keys)
    duplicate = bool(source_keys) and set(source_keys) <= used
    judged_at = utc(judged_at)
    values = {}
    row = db.get(CharacterActivityState, actor_id)
    stale_time = row is not None and row.confirmed_at is not None and utc(row.confirmed_at) > judged_at
    if duplicate:
        outcome = "already_interpreted"
    elif snapshot["version"] != expected_version or stale_time:
        outcome = "conflict_not_applied"
    elif proposal is None and not snapshot["known"]:
        outcome = "unknown_kept"
    else:
        values = {"confirmed_at": judged_at, "version": expected_version + 1, "origin": activity_id}
        if proposal is not None:
            values.update(proposal.model_dump())
            if any(snapshot.get(key) != value for key, value in proposal.model_dump().items()):
                values["changed_at"] = judged_at
        if row is None:
            db.add(CharacterActivityState(world_id=world_id, world_character_id=actor_id, **values))
            db.flush()
            outcome = "updated"
        else:
            count = db.execute(update(CharacterActivityState).where(
                CharacterActivityState.world_character_id == actor_id,
                CharacterActivityState.version == expected_version,
            ).values(**values)).rowcount
            outcome = ("updated" if "changed_at" in values else "kept") if count else "conflict_not_applied"
    db.add(ActivityStateReceipt(decision_key=decision_key, world_character_id=actor_id,
        world_id=world_id, activity_id=activity_id, outcome=outcome,
        expected_version=expected_version, resulting_version=expected_version + 1 if outcome in {"updated", "kept"} else snapshot["version"],
        source_keys=sorted(set(source_keys)), judged_at=judged_at))
    db.flush()
    return outcome
