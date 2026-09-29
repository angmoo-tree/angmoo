"""Date preparation persistence. Provider and Topic composition live in runtime.

Claim/reserve finish their short transactions. apply_plan participates in the
caller's transaction and never commits, so initial topics and plan apply together.
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
from functools import wraps
import json

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.ids import uuid7_string
from app.core.sqlite_concurrency import run_sqlite_session_immediate
from app.domains.routines.models.preparation import ActivityPreparationJob
from app.domains.routines.models.plans import DailyActivityPlan, DailyActivityPlanItem, ActivityEpisode
from app.domains.routines.constants import TIMEZONE_CONTRACT_VERSION
from app.domains.routines.policies.activity_state import initial_state
from app.domains.routines.policies.planning import daypart_windows
from app.domains.routines.schemas.daily_generation import GeneratedDailyPlan, OrdinaryGeneratedPlan, DAYPARTS
from app.domains.routines.service import joint_reservations

CONTRACT = "daily-plan-v1"


class PreparationConflict(ValueError):
    pass


def snapshot_digest(value) -> str:
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def current_plan(db: Session, world_character_id: str, local_date: date):
    return db.scalar(select(DailyActivityPlan).where(
        DailyActivityPlan.world_character_id == world_character_id,
        DailyActivityPlan.local_date == local_date,
    ))


def current_items(db: Session, plan_id: str):
    return list(db.scalars(select(DailyActivityPlanItem).where(
        DailyActivityPlanItem.plan_id == plan_id,
        DailyActivityPlanItem.status != "superseded",
    ).order_by(DailyActivityPlanItem.daypart)))


def plan_snapshot(db: Session, plan):
    if plan is None:
        return {}
    items = current_items(db, plan.id)
    episodes = list(db.scalars(select(ActivityEpisode).where(
        ActivityEpisode.plan_item_id.in_([item.id for item in items])).order_by(ActivityEpisode.id)))
    return {"plan_id": plan.id, "version": plan.version,
            "items": [{"id": item.id, "version": item.version, "status": item.status,
                       "joint_activity_id": item.joint_activity_id, "is_user_pinned": item.is_user_pinned,
                       "daypart": item.daypart, "activity_kind": item.activity_kind,
                       "title": item.title, "activity_seed": item.activity_seed,
                       "social_mode": item.social_mode, "place_key": item.place_key}
                      for item in items],
            "episodes": [{"id": ep.id, "version": ep.version, "last_successful_beat_id": ep.last_successful_beat_id,
                          "status": ep.status} for ep in episodes]}


def job_for(db: Session, wc_id: str, target_date: date, request_id: str):
    return db.scalar(select(ActivityPreparationJob).where(
        ActivityPreparationJob.world_character_id == wc_id,
        ActivityPreparationJob.local_date == target_date,
        ActivityPreparationJob.request_id == request_id))


def write_preparation(db: Session, operation):
    """Own a short write in the dedicated preparation Session, never across AI."""
    if db.new or db.dirty or db.deleted:
        raise PreparationConflict("preparation_session_has_pending_changes")
    db.rollback()  # Only preparation-owned reads; caller uses a separate Session.
    if db.get_bind().dialect.name == "sqlite":
        return run_sqlite_session_immediate(db, operation, require_clean=True)
    with db.begin():
        return operation()


def _write(function):
    @wraps(function)
    def wrapped(db, *args, **kwargs):
        return write_preparation(db, lambda: function(db, *args, **kwargs))
    return wrapped


@_write

def claim(db: Session, *, wc_id: str, world_id: str, target_date: date, timezone: str,
          mode: str, request_id: str, source: dict, input_digest: str, now: datetime, lock_actor):
    # Serialize all generations for this actor, including different request IDs.
    # SQLite owns the writer; PostgreSQL owns a stable actor-row lock.
    lock_actor(db, wc_id)
    running = db.scalar(select(ActivityPreparationJob).where(
        ActivityPreparationJob.world_character_id == wc_id,
        ActivityPreparationJob.state == "running"))
    if running:
        lease = running.lease_expires_at
        lease = lease.replace(tzinfo=UTC) if lease and lease.tzinfo is None else lease
        if lease and lease > now:
            return running, None
        running.state = "waiting" if running.request_id == request_id and running.local_date == target_date else "cancelled"
        running.reason_code = "preparation_claim_expired"
        running.lease_expires_at = None
        db.flush()
    job = job_for(db, wc_id, target_date, request_id)
    if job is None:
        job = ActivityPreparationJob(id=uuid7_string(), world_id=world_id,
            world_character_id=wc_id, local_date=target_date, timezone_name=timezone,
            mode=mode, request_id=request_id, state="pending", input_digest=input_digest,
            input_snapshot=source, attempt_count=0, json_retry_count=0)
        db.add(job)
        db.flush()
    if job.input_digest != input_digest:
        job.state, job.reason_code = "failed", "preparation_source_changed"
    if job.state in {"ready", "failed", "needs_user_action", "cancelled"}:
        return job, None
    def aware(value):
        return value.replace(tzinfo=UTC) if value and value.tzinfo is None else value
    if ((job.state == "running" and aware(job.lease_expires_at) and aware(job.lease_expires_at) > now)
            or (aware(job.next_retry_at) and aware(job.next_retry_at) > now)):
        return job, None
    if job.attempt_count >= 4:
        job.state, job.reason_code = "failed", "preparation_attempts_exhausted"
        return job, None
    token = uuid7_string()
    changed = db.execute(update(ActivityPreparationJob).where(
        ActivityPreparationJob.id == job.id, ActivityPreparationJob.version == job.version,
    ).values(state="running", claim_token=token, lease_expires_at=now + timedelta(minutes=8),
             version=job.version + 1)).rowcount
    if changed != 1:
        raise PreparationConflict("preparation_claim_conflict")
    db.refresh(job)  # Return the accepted CAS state even with expire_on_commit=False.
    return job, token


@_write
def reserve_attempt(db: Session, job_id: str, token: str, *, json_retry=False):
    column = ActivityPreparationJob.json_retry_count if json_retry else ActivityPreparationJob.attempt_count
    changed = db.execute(update(ActivityPreparationJob).where(
        ActivityPreparationJob.id == job_id, ActivityPreparationJob.claim_token == token,
        ActivityPreparationJob.state == "running", column < (1 if json_retry else 4),
        ActivityPreparationJob.lease_expires_at > datetime.now(UTC),
    ).values({column: column + 1}).execution_options(synchronize_session=False)).rowcount
    if changed != 1:
        raise PreparationConflict("preparation_retry_exhausted" if json_retry else "preparation_attempts_exhausted")


@_write
def finish_failure(db: Session, job_id: str, token: str, code: str, *, retry_at=None, usage=None):
    job = db.get(ActivityPreparationJob, job_id, populate_existing=True)
    if job is None or job.claim_token != token or job.state != "running":
        return
    job.state = "waiting" if retry_at and job.attempt_count < 4 else "failed"
    job.reason_code = code
    if usage is not None:
        job.usage_snapshot = usage
    job.next_retry_at = retry_at if job.state == "waiting" else None
    job.lease_expires_at = None


def validate_plan(output: GeneratedDailyPlan, *, allowed_places: dict[str, set[str]], fixed_items: list[dict]):
    by_daypart = {item.daypart: item for item in output.items}
    for item in output.items:
        fixed = next((row for row in fixed_items if row["daypart"] == item.daypart), None)
        if (item.activity_kind == "joint_activity" or item.social_mode == "joint") and fixed is None:
            raise PreparationConflict("daily_plan_joint_not_reserved")
        if item.place_key is not None and item.place_key not in allowed_places.get(item.daypart, set()):
            raise PreparationConflict("daily_plan_place_invalid")
    for fixed in fixed_items:
        proposed = by_daypart[fixed["daypart"]].model_dump()
        if any(proposed[key] != fixed[key] for key in proposed):
            raise PreparationConflict("daily_plan_fixed_item_changed")


def compose_generated_plan(output: OrdinaryGeneratedPlan | None, *, generated_dayparts: list[str],
                           fixed_items: list[dict], allowed_places: dict[str, set[str]]) -> GeneratedDailyPlan:
    """Validate new directions, then combine untouched server-held directions."""
    items = OrdinaryGeneratedPlan.model_validate(output.model_dump()).items if output is not None else []
    if len(items) != len(generated_dayparts) or {item.daypart for item in items} != set(generated_dayparts):
        raise PreparationConflict("daily_generation_dayparts_mismatch")
    fixed = {item["daypart"]: item for item in fixed_items}
    if len(fixed) != len(fixed_items) or set(fixed) & set(generated_dayparts) or set(fixed) | set(generated_dayparts) != set(DAYPARTS):
        raise PreparationConflict("daily_generation_partition_invalid")
    # Historical completed/pinned data is not re-authored or revalidated as a
    # new ordinary direction. Generated place values still require permission.
    for item in items:
        if item.place_key is not None and item.place_key not in allowed_places.get(item.daypart, set()):
            raise PreparationConflict("daily_plan_place_invalid")
    by_daypart = {**fixed, **{item.daypart: item.model_dump() for item in items}}
    return GeneratedDailyPlan(items=[by_daypart[part] for part in DAYPARTS])


def preserve_item(db: Session, item) -> bool:
    if item.status == "completed" or item.is_user_pinned:
        return True
    if not item.joint_activity_id:
        return False
    from app.domains.routines.models.plans import JointActivity
    joint = db.get(JointActivity, item.joint_activity_id)
    return joint is not None and joint.status in joint_reservations.ACTIVE_JOINT_STATUSES


def apply_plan(db: Session, *, scope, output: GeneratedDailyPlan, target_date: date,
               now: datetime, source_digest: str, expected_snapshot: dict, state_schema_version: int = 1):
    """Apply validated directions; keep successful episodes and reservation rules."""
    plan = current_plan(db, scope.world_character.id, target_date)
    if plan_snapshot(db, plan) != expected_snapshot:
        raise PreparationConflict("daily_plan_changed_during_generation")
    if plan is None:
        plan = DailyActivityPlan(id=uuid7_string(), world_id=scope.world.id,
            world_character_id=scope.world_character.id, local_date=target_date,
            timezone_name=scope.world.timezone, timezone_contract_version=TIMEZONE_CONTRACT_VERSION,
            repertoire_id=None, generation_source="daily_generation", preparation_contract_version=CONTRACT,
            world_definition_hash=scope.world.contract_hash,
            character_definition_hash=source_digest, repertoire_contract_version=CONTRACT,
            selection_contract_version=CONTRACT, selection_seed_hash=source_digest,
            status="planned", revision_count=0, version=1)
        db.add(plan)
        db.flush()
    else:
        plan.version += 1
        plan.generation_source = "daily_generation"
        plan.preparation_contract_version = CONTRACT
        plan.timezone_name = scope.world.timezone
        plan.world_definition_hash = scope.world.contract_hash
    previous = {item.daypart: item for item in current_items(db, plan.id)}
    windows = daypart_windows(target_date, scope.world.timezone)
    for item in output.items:
        old = previous.get(item.daypart)
        if old and preserve_item(db, old):
            continue
        if old:
            old.status, old.terminal_reason_code = "superseded", "manual_daily_preparation"
            old.version += 1
            for episode in db.scalars(select(ActivityEpisode).where(ActivityEpisode.plan_item_id == old.id)):
                if episode.status in {"planned", "active"}:
                    episode.status = "interrupted"
                    episode.terminal_reason_code = "manual_daily_preparation"
                    episode.version += 1
            db.flush()
        start, end = windows[item.daypart]
        reservation = joint_reservations.reservation_for(db, world_character_id=scope.world_character.id,
            local_date=target_date, daypart=item.daypart)
        if reservation is not None and end > now:
            joint_reservations.materialize_reservation_for_new_plan(db, plan=plan, joint=reservation,
                scheduled_start_at=start, scheduled_end_at=end, now=now, state_schema_version=state_schema_version)
            continue
        row = DailyActivityPlanItem(id=uuid7_string(), plan_id=plan.id, world_id=plan.world_id,
            world_character_id=plan.world_character_id, **item.model_dump(), origin_type="daily_generation",
            scheduled_start_at=start, scheduled_end_at=end, status="skipped" if end <= now else "planned",
            terminal_reason_code="plan_created_after_window" if end <= now else None,
            supersedes_plan_item_id=old.id if old else None, revision_count=0, version=1)
        db.add(row)
        db.flush()
        if end > now:
            db.add(ActivityEpisode(id=uuid7_string(), world_id=plan.world_id,
                world_character_id=plan.world_character_id, plan_item_id=row.id,
                effective_activity_snapshot=item.model_dump(exclude={"daypart"}), status="planned",
                current_state_schema_version=state_schema_version, current_state_snapshot=initial_state(schema_version=state_schema_version), next_sequence_no=1, version=1))
    db.flush()
    return plan
