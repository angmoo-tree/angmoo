"""Actor-only limits and idempotent attempt accounting shared by SNS and Chat."""
from datetime import UTC, datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, update

from app.domains.media.models_world_policy import WorldImagePolicy, WorldImageAttempt
from app.domains.media.contracts import ImagePreparationError


def initialize_new_actor(db, *, world_character_id, generation_limit=20, vision_limit=10):
    """Creation UoW only. GET, key save and legacy row repair never call this."""
    existing = db.get(WorldImagePolicy, world_character_id)
    if existing is not None:
        return existing
    for cap in (generation_limit, vision_limit):
        if type(cap) is not int or not 1 <= cap <= 10000:
            raise ImagePreparationError("world_image_limit_invalid")
    row = WorldImagePolicy(world_character_id=world_character_id, generation_limit=generation_limit,
        vision_limit=vision_limit, generation_enabled=False, vision_enabled=False,
        generation_settings={}, revision=1, provenance="creation:v1")
    db.add(row)
    db.flush()
    return row


def period(now, timezone):
    return now.astimezone(ZoneInfo(timezone)).date().isoformat()


def usage(db, *, world_character_id, purpose, now, timezone):
    return db.scalar(select(func.count()).select_from(WorldImageAttempt).where(
        WorldImageAttempt.world_character_id == world_character_id, WorldImageAttempt.purpose == purpose,
        WorldImageAttempt.period_date == period(now, timezone), WorldImageAttempt.state != "released")) or 0


def patch(db, *, world_character_id, expected_revision, changes, require_key):
    row = db.get(WorldImagePolicy, world_character_id, populate_existing=True)
    allowed = {"generation_limit", "vision_limit", "generation_enabled", "vision_enabled", "generation_settings"}
    if row is None:
        raise ImagePreparationError("world_image_policy_missing")
    if expected_revision != row.revision:
        raise ImagePreparationError("world_image_policy_revision_conflict")
    if not changes or not set(changes) <= allowed:
        raise ImagePreparationError("world_image_policy_invalid")
    for name in ("generation_limit", "vision_limit"):
        cap = changes.get(name, getattr(row, name))
        if cap is not None and (type(cap) is not int or not 1 <= cap <= 10000):
            raise ImagePreparationError("world_image_limit_invalid")
    for prefix, purpose in (("generation", "image"), ("vision", "vision")):
        enabled = changes.get(prefix + "_enabled", getattr(row, prefix + "_enabled"))
        if type(enabled) is not bool:
            raise ImagePreparationError("world_image_policy_invalid")
        if enabled:
            if changes.get(prefix + "_limit", getattr(row, prefix + "_limit")) is None:
                raise ImagePreparationError("world_image_limit_required")
            require_key(purpose)
    changed = db.execute(update(WorldImagePolicy).where(WorldImagePolicy.world_character_id == world_character_id,
        WorldImagePolicy.revision == expected_revision).values(**changes, revision=expected_revision + 1))
    if changed.rowcount != 1:
        raise ImagePreparationError("world_image_policy_revision_conflict")
    db.refresh(row)
    return row


def reserve(db, *, world_character_id, purpose, request_key, lane, credential_revision, now, timezone, admitted=False):
    if purpose not in {"image", "vision"} or lane not in {"sns", "chat"} or not request_key or len(request_key) > 128:
        raise ImagePreparationError("world_image_attempt_invalid")
    old = db.scalar(select(WorldImageAttempt).where(WorldImageAttempt.world_character_id == world_character_id,
        WorldImageAttempt.purpose == purpose, WorldImageAttempt.request_key == request_key))
    if old is not None:
        if old.lane != lane or old.credential_revision != credential_revision:
            raise ImagePreparationError("world_image_attempt_conflict")
        return old
    # Acquire one writer fence before checking the combined actor usage.
    locked = db.execute(update(WorldImagePolicy).where(WorldImagePolicy.world_character_id == world_character_id)
        .values(revision=WorldImagePolicy.revision))
    if locked.rowcount != 1:
        raise ImagePreparationError("world_image_policy_missing")
    policy = db.get(WorldImagePolicy, world_character_id, populate_existing=True)
    prefix = "generation" if purpose == "image" else "vision"
    cap = getattr(policy, prefix + "_limit")
    if (not admitted and not getattr(policy, prefix + "_enabled")) or cap is None or cap < 1:
        raise ImagePreparationError("world_image_not_enabled")
    if usage(db, world_character_id=world_character_id, purpose=purpose, now=now, timezone=timezone) >= cap:
        raise ImagePreparationError("world_image_daily_limit_reached")
    row = WorldImageAttempt(id=uuid4().hex, world_character_id=world_character_id, purpose=purpose,
        request_key=request_key, lane=lane, period_date=period(now, timezone), state="reserved",
        credential_revision=credential_revision, created_at=now)
    db.add(row)
    db.flush()
    return row
