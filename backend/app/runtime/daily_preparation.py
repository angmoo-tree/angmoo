"""Compose authorized daily plans, source persona, topics and provider work."""
from __future__ import annotations

from dataclasses import asdict
import json
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.ids import uuid7_string
from app.domains.characters.service.prompt_persona import model_persona, PERSONA_INTERPRETATION
from app.domains.identity.contracts import CredentialPurpose
from app.domains.identity.service.credential_resolution import CredentialResolver
from app.domains.identity.service.world_character_credentials import find_world_character_credential
from app.domains.routines.client import generate_daily_preparation
from app.domains.routines.models.preparation import ActivityPreparationJob
from app.domains.routines.models.resident import AgentActivitySetting
from app.domains.routines.policies.planning import local_activity_date, daypart_windows
from app.domains.routines.policies.active_hours import active_hours_minutes
from app.domains.routines.schemas.daily_generation import DailyPreparationRead
from app.domains.routines.service import daily_preparation as store
from app.domains.routines.service.plans import load_preparation_scope
from app.domains.routines.service.run_backoff import _runtime_error_backoff
from app.domains.social.models.topics import RecommendationPreparation, RecommendationTopic, RecommendationTopicSource
from app.domains.social.service.recommendation_topics import replace_source_topics
from app.domains.world_characters.service.activity_state import read_state
from app.domains.world_characters.service.activity_engines import routine_state_version
from app.domains.worlds.service.generation_context import build_world_generation_context
from app.runtime.routines.plan_references import SqlAlchemyPlanReferences
from app.runtime.social.today_activity import today_social_activity_reader


def _scope(db, character_id, world_id, user):
    scope = load_preparation_scope(SqlAlchemyPlanReferences(db), character_id=character_id, world_id=world_id, user=user)
    from app.domains.worlds.service.character_entry import find_autonomous_entry_role
    if find_autonomous_entry_role(db, world_id=world_id, role_key=scope.world_character.role_key) is None:
        raise store.PreparationConflict("world_reference_invalid")
    return scope


def _topics(db, scope):
    prep = db.scalar(select(RecommendationPreparation).where(
        RecommendationPreparation.world_id == scope.world.id,
        RecommendationPreparation.source_key == scope.world_character.id))
    from app.domains.social.service.recommendation_topics import character_topics_usable
    if character_topics_usable(db, world_id=scope.world.id, source_key=scope.world_character.id):
        state = "ready"
    elif prep and prep.applied_digest:
        state = "needs_user_action"
    elif prep and prep.request_id == "initial":
        state = "pending"
    else:
        state = "needs_user_action"
    return prep, state


def _automatic_eligible(db, scope, now):
    wc = scope.world_character
    setting = db.get(AgentActivitySetting, scope.character.id)
    if (wc.status != "active" or wc.activity_runtime_mode != "routine_resident_v1"
        or not wc.autonomous_enabled or not setting or not setting.auto_enabled):
        return False
    from app.domains.world_characters.models import CharacterActiveWorld
    from app.domains.operations.service import maintenance
    active = db.get(CharacterActiveWorld, scope.character.id)
    credential = find_world_character_credential(db, character_id=scope.character.id)
    if (not active or active.world_character_id != wc.id
        or getattr(scope.character, "moderation_status", None) == "suspended"
        or not credential or not credential.enabled):
        return False
    if maintenance.agent_activity_blocks_auto_ticks(db) and scope.character.id not in maintenance.agent_activity_auto_tick_allowed_character_ids():
        return False
    cooldown = credential.cooldown_until
    if cooldown and cooldown.replace(tzinfo=UTC) > now:
        return False
    local = now.astimezone(ZoneInfo(scope.world.timezone))
    start, end = active_hours_minutes(setting.active_hours_start, setting.active_hours_end)
    minute = local.hour * 60 + local.minute
    return start != end and (start <= minute < end if start < end else minute >= start or minute < end)


def _source(db, scope, now):
    local = now.astimezone(ZoneInfo(scope.world.timezone))
    plan = store.current_plan(db, scope.world_character.id, local.date())
    snapshot = store.plan_snapshot(db, plan)
    world = build_world_generation_context(db, scope.world).model_dump(mode="json")
    allowed = {part: {place["key"] for place in world["places"]
                     if (not place["available_dayparts"] or part in place["available_dayparts"])
                     and (not place["access_role_keys"] or scope.world_character.role_key in place["access_role_keys"])}
               for part in ("dawn", "morning", "afternoon", "evening")}
    fixed_ids = {item.id for item in store.current_items(db, plan.id) if store.preserve_item(db, item)} if plan else set()
    fixed = [{key: item[key] for key in ("daypart", "activity_kind", "title", "activity_seed", "social_mode", "place_key")}
             for item in snapshot.get("items", [])
             if item["id"] in fixed_ids]
    reservations = []
    from app.domains.routines.service.joint_reservations import reservation_for, reserved_daily_direction
    for part in allowed:
        joint = reservation_for(db, world_character_id=scope.world_character.id, local_date=local.date(), daypart=part)
        if joint:
            if part not in {item["daypart"] for item in fixed}:
                fixed.append(reserved_daily_direction(joint))
            reservations.append({"id": joint.id, "daypart": part, "activity_seed": joint.activity_seed, "place_key": joint.place_key})
    source = {"persona": {**model_persona(scope.character), "interpretation": PERSONA_INTERPRETATION},
              "world": world, "role_key": scope.world_character.role_key,
              "local_date": local.date().isoformat(), "local_now": local.isoformat(),
              "timezone": scope.world.timezone, "allowed_places": {k: sorted(v) for k, v in allowed.items()},
              "time_windows": {k: [start.astimezone(local.tzinfo).isoformat(), end.astimezone(local.tzinfo).isoformat()]
                               for k, (start, end) in daypart_windows(local.date(), scope.world.timezone).items()},
              "fixed_items": fixed, "confirmed_reservations": reservations}
    # Only stable settings/reservations fence application. Ordinary new SNS/mood
    # updates must not invalidate every request or be overwritten by its snapshot.
    digest = store.snapshot_digest({k: value for k, value in source.items() if k != "local_now"})
    today = today_social_activity_reader(db).read(owner_id=scope.character.owner_id, world_id=scope.world.id,
        subject_world_character_id=scope.world_character.id, started_at=now-timedelta(days=1), complete_through=now)
    activity = asdict(today)
    activity["records"] = activity.get("records", [])[:12]
    source["recent_activity"] = activity
    source["current_state"] = read_state(db, world_id=scope.world.id, actor_id=scope.world_character.id)
    source["previous_plan_snapshot"] = snapshot

    return json.loads(json.dumps(source, ensure_ascii=False, default=str)), digest, snapshot, allowed


def _plan_problem(db, scope, plan, now):
    if plan.timezone_name != scope.world.timezone:
        return "daily_plan_timezone_changed"
    items = store.current_items(db, plan.id)
    if len(items) != 4 or {i.daypart for i in items} != {"dawn", "morning", "afternoon", "evening"}:
        return "daily_plan_partial"
    world = build_world_generation_context(db, scope.world)
    places = {p.key: p for p in world.places}
    from app.domains.routines.models.plans import ActivityEpisode, JointActivity
    for item in items:
        if item.status in {"completed", "skipped"}:
            continue
        place = places.get(item.place_key) if item.place_key else None
        if item.place_key and (not place or (place.available_dayparts and item.daypart not in place.available_dayparts)
                or (place.access_role_keys and scope.world_character.role_key not in place.access_role_keys)):
            return "daily_plan_place_invalid"
        if item.joint_activity_id:
            joint = db.get(JointActivity, item.joint_activity_id)
            if joint is None or joint.world_id != scope.world.id or joint.status in {"cancelled", "failed"}:
                return "daily_plan_reservation_invalid"
        if db.scalar(select(ActivityEpisode.id).where(ActivityEpisode.plan_item_id == item.id)) is None:
            return "daily_plan_episode_missing"
    return None


def read_preparation(db, *, character_id, world_id, user, now=None):
    now = now or datetime.now(UTC)
    scope = _scope(db, character_id, world_id, user)
    target = local_activity_date(now, scope.world.timezone)
    plan = store.current_plan(db, scope.world_character.id, target)
    _prep, topic_state = _topics(db, scope)
    job = db.scalar(select(ActivityPreparationJob).where(
        ActivityPreparationJob.world_character_id == scope.world_character.id,
        ActivityPreparationJob.local_date == target).order_by(ActivityPreparationJob.created_at.desc(), ActivityPreparationJob.id.desc()))
    state, reason = "pending", None
    if plan:
        reason = _plan_problem(db, scope, plan, now)
        state = "needs_user_action" if reason else "ready"
    elif job and job.state == "ready":
        state, reason = "needs_user_action", "daily_plan_lost"
    if job and job.state in {"pending", "running", "waiting", "failed", "needs_user_action"}:
        if state not in {"ready", "needs_user_action"}:
            state, reason = job.state, job.reason_code
    if job and state == "running" and job.lease_expires_at and job.lease_expires_at.replace(tzinfo=UTC) <= now:
        state, reason = "waiting", "preparation_claim_expired"
    return DailyPreparationRead(world_character_id=scope.world_character.id, local_date=target.isoformat(),
        plan_state=state, topic_state=topic_state, request_id=job.request_id if job else None,
        attempt_count=job.attempt_count if job else 0, reason_code=reason,
        plan_id=plan.id if plan else None, plan_version=plan.version if plan else None,
        request_state=job.state if job else None, request_reason_code=job.reason_code if job else None,
        next_retry_at=job.next_retry_at.isoformat() if job and job.next_retry_at else None)


async def _ensure_preparation(db, *, character_id, world_id, user, request_id=None,
                             expected_version=None, now=None, generator=generate_daily_preparation,
                             evaluation_reserve=None):
    fixed_clock = now is not None
    now = now or datetime.now(UTC)
    scope = _scope(db, character_id, world_id, user)
    status = read_preparation(db, character_id=character_id, world_id=world_id, user=user, now=now)
    manual = request_id is not None
    if not manual:
        if status.plan_state in {"ready", "failed", "needs_user_action"} or not _automatic_eligible(db, scope, now):
            return status
    target = local_activity_date(now, scope.world.timezone)
    if manual:
        prior_request = store.job_for(db, scope.world_character.id, target, request_id)
        if prior_request and prior_request.state in {"ready", "failed", "needs_user_action", "cancelled"}:
            return status  # Lost HTTP responses reuse the completed request before version checks.
    prep, topic_state = _topics(db, scope)
    initial = topic_state == "pending" and status.plan_id is None
    if topic_state == "needs_user_action" and status.plan_id is None and not prep:
        # Historical unknown data needs an explicit request, never automatic enrollment.
        if not manual:
            return status.model_copy(update={"plan_state": "needs_user_action", "reason_code": "preparation_history_unknown"})
    source, digest, before, allowed = _source(db, scope, now)
    if expected_version is not None and before.get("version") != expected_version:
        raise store.PreparationConflict("daily_plan_version_conflict")
    credential = find_world_character_credential(db, character_id=character_id)
    material = CredentialResolver.resolve_llm_credential(credential, purpose=CredentialPurpose.WORLD_CHARACTER_SETUP_LLM,
                                                       owner_id=user.id, character_id=character_id)
    request_id = request_id or (status.request_id if status.plan_state in {"waiting", "running"} else None) or f"automatic:{target.isoformat()}"
    from app.domains.world_characters.service.preparation_lock import lock_preparation_actor
    from app.domains.world_characters.service.name_binding import resolve_name_binding, validate_name_binding
    from app.contracts.name_binding import read_name_binding, NameBindingError
    from app.domains.characters.service.prompt_persona import render_persona
    new_names = resolve_name_binding(db, actor=scope.world_character, owner_id=user.id)
    source = {**source, "name_binding_policy": new_names.policy_version, "name_binding": new_names.to_dict()}
    job, token = store.claim(db, wc_id=scope.world_character.id, world_id=world_id, target_date=target,
        timezone=scope.world.timezone, mode="initial" if initial else "manual_plan" if manual else "daily",
        request_id=request_id, source=source, input_digest=digest, now=now, lock_actor=lock_preparation_actor)
    job_id, wc_id = job.id, scope.world_character.id
    if token is None:
        return read_preparation(db, character_id=character_id, world_id=world_id, user=user, now=now)
    # The claim keeps its accepted raw source and names across retries/restarts.
    source = dict(job.input_snapshot)
    try:
        names = read_name_binding(source)
        request_source = dict(source)
        if names is not None:
            validate_name_binding(db, names, actor=scope.world_character, owner_id=user.id)
            request_source["persona"] = render_persona(source["persona"], names)
    except NameBindingError as exc:
        db.rollback()
        store.write_preparation(db, lambda: store.finish_failure(db, job_id, token, str(exc)))
        return read_preparation(db, character_id=character_id, world_id=world_id, user=user, now=now)
    # Topic's own request generation also fences initial application. No Topic is
    # written until both outputs pass validation and this claim still belongs to us.
    initial_prep_request = prep.request_id if prep else None
    initial_prep_digest = prep.applied_digest if prep else None
    from app.runtime.social.topic_preparation import load_scope as topic_scope
    topic_digest = topic_scope(db, world_id=world_id, owner_id=user.id, world_character_id=wc_id,
                               allow_unapproved=True).digest
    db.commit()

    def reserve():
        current_time = now if fixed_clock else datetime.now(UTC)
        db.expire_all()
        current_scope = _scope(db, character_id, world_id, user)
        if local_activity_date(current_time, current_scope.world.timezone) != target or (
            not manual and not _automatic_eligible(db, current_scope, current_time)):
            raise store.PreparationConflict("preparation_scope_changed")
        if _source(db, current_scope, current_time)[1] != digest:
            raise store.PreparationConflict("preparation_source_changed")
        if names is not None:
            validate_name_binding(db, names, actor=current_scope.world_character, owner_id=user.id)
        if evaluation_reserve:
            evaluation_reserve()
        store.reserve_attempt(db, job_id, token)

    tracker = None
    try:
        output, tracker = await generator(material=material, character_id=character_id, source=request_source,
            initial=initial, reserve=reserve,
            reserve_json_retry=lambda: store.reserve_attempt(db, job_id, token, json_retry=True))
        current_time = now if fixed_clock else datetime.now(UTC)
        def apply():
            from app.domains.world_characters.service.preparation_lock import lock_preparation_actor
            lock_preparation_actor(db, wc_id)
            db.expire_all()
            scope = _scope(db, character_id, world_id, user)
            if target != local_activity_date(current_time, scope.world.timezone) or (not manual and not _automatic_eligible(db, scope, current_time)):
                raise store.PreparationConflict("preparation_scope_changed")
            current_credential = find_world_character_credential(db, character_id=character_id)
            current_material = CredentialResolver.resolve_llm_credential(current_credential,
                purpose=CredentialPurpose.WORLD_CHARACTER_SETUP_LLM, owner_id=user.id, character_id=character_id)
            if (current_material.credential_id, current_material.fingerprint, current_material.model, current_material.thinking_level) != (material.credential_id, material.fingerprint, material.model, material.thinking_level):
                raise store.PreparationConflict("preparation_credential_changed")
            fresh, current_digest, _, current_allowed = _source(db, scope, current_time)
            if current_digest != digest:
                raise store.PreparationConflict("preparation_source_changed")
            if names is not None:
                validate_name_binding(db, names, actor=scope.world_character, owner_id=user.id)
            from app.runtime.preparation_names import authored_preparation
            output_value = authored_preparation(output, names)
            store.validate_plan(output_value.daily_plan, allowed_places=current_allowed, fixed_items=source["fixed_items"])
            claimed = db.execute(update(ActivityPreparationJob).where(
                ActivityPreparationJob.id == job_id, ActivityPreparationJob.claim_token == token,
                ActivityPreparationJob.state == "running", ActivityPreparationJob.lease_expires_at > current_time,
            ).values(state="ready", lease_expires_at=None).execution_options(synchronize_session=False)).rowcount
            if claimed != 1:
                raise store.PreparationConflict("preparation_claim_lost")
            if initial:
                prep, current_topic_state = _topics(db, scope)
                if not prep or prep.request_id != initial_prep_request or prep.applied_digest != initial_prep_digest or prep.state == "running":
                    raise store.PreparationConflict("preparation_topics_changed")
                replace_source_topics(db, world_id=world_id, world_character_id=wc_id,
                    topics=[(t.name, t.scope) for t in output_value.recommendation_topics])
                prep.state, prep.applied_digest, prep.source_digest = "ready", topic_digest, topic_digest
                prep.last_code = None
            plan = store.apply_plan(db, scope=scope, output=output_value.daily_plan, target_date=target,
                now=current_time, source_digest=digest, expected_snapshot=before,
                state_schema_version=routine_state_version(db, scope.world_character))
            job = db.get(ActivityPreparationJob, job_id, populate_existing=True)
            job.plan_id, job.plan_version = plan.id, plan.version
            job.applied_snapshot = store.plan_snapshot(db, plan)
            job.usage_snapshot = {"calls": tracker.calls, "model": material.model, "thinking_level": material.thinking_level}
        store.write_preparation(db, apply)
    except Exception as exc:
        db.rollback()
        backoff = _runtime_error_backoff(exc, now=now, db=db, character_id=character_id, credential_id=material.credential_id)
        code = str(exc) if isinstance(exc, (store.PreparationConflict, NameBindingError)) else backoff.kind if backoff else "preparation_generation_failed"
        store.write_preparation(db, lambda: store.finish_failure(db, job_id, token, code,
            retry_at=backoff.retry_at if backoff else None, usage=getattr(exc, "preparation_usage", None)))
    return read_preparation(db, character_id=character_id, world_id=world_id, user=user, now=now)


async def ensure_preparation(db, **kwargs):
    """Preparation owns a separate Session; caller transactions are never rolled back."""
    from app.domains.identity.exceptions import CredentialResolutionError
    with Session(db.get_bind(), expire_on_commit=False) as preparation_db:
        try:
            return await _ensure_preparation(preparation_db, **kwargs)
        except CredentialResolutionError as exc:
            raise store.PreparationConflict("preparation_credential_unavailable") from exc


async def prepare_due_dates(db, *, limit=3):
    """Scheduler preparation events do not change SNS slots or publish anything."""
    from types import SimpleNamespace
    import logging
    from app.domains.characters.models import Character
    from app.domains.world_characters.models import WorldCharacter, CharacterActiveWorld
    subjects = db.execute(select(Character.id, Character.owner_id, WorldCharacter.world_id).join(
        CharacterActiveWorld, CharacterActiveWorld.character_id == Character.id).join(
        WorldCharacter, WorldCharacter.id == CharacterActiveWorld.world_character_id).join(
        AgentActivitySetting, AgentActivitySetting.character_id == Character.id).where(
        Character.deleted_at.is_(None), WorldCharacter.autonomous_enabled.is_(True),
        WorldCharacter.status == "active", AgentActivitySetting.auto_enabled.is_(True)
    ).order_by(Character.id)).all()
    db.rollback()  # scheduler-owned lookup; caller committed lifecycle reconciliation
    attempted = 0
    for character_id, owner_id, world_id in subjects:
        if attempted >= limit:
            break
        try:
            with Session(db.get_bind(), expire_on_commit=False) as check:
                user = SimpleNamespace(id=owner_id)
                scope = _scope(check, character_id, world_id, user)
                now = datetime.now(UTC)
                if not _automatic_eligible(check, scope, now):
                    continue
                status = read_preparation(check, character_id=character_id, world_id=world_id, user=user, now=now)
                if status.plan_state not in {"pending", "waiting"}:
                    continue
                if status.next_retry_at and datetime.fromisoformat(status.next_retry_at).replace(tzinfo=UTC) > now:
                    continue
            attempted += 1
            await ensure_preparation(db, character_id=character_id, world_id=world_id, user=user)
        except Exception as exc:
            # One ineligible credential/scope must not stop another actor's tick.
            logging.getLogger(__name__).warning("daily preparation unavailable: %s", type(exc).__name__)
    return attempted
