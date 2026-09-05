from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.ids import uuid7_string
from app.domains.routines import schemas
from app.domains.routines.infrastructure import sqlalchemy_daily_plan_models as models
from app.domains.routines.service import joint_reservations as sqlalchemy_joint_reservations
from app.domains.world_characters.public import character_contract_hash
from app.domains.routines.constants import DAYPARTS, DAYPART_START_HOURS, SELECTION_CONTRACT_VERSION, TIMEZONE_CONTRACT_VERSION, EVENT_CONSUMPTION_NAMESPACE, RECENT_EXACT_DAYS, USAGE_WINDOW_DAYS, INITIAL_STATE
from app.domains.routines.exceptions import DailyActivityPlanError, DailyActivityPlanNotFoundError, DailyActivityPlanForbiddenError, DailyActivityPlanConflictError, DailyActivityPlanValidationError
from app.domains.routines.policies.planning import _zone, _resolve_local_boundary, daypart_windows, local_activity_date, _select_candidate, _snapshot
from app.domains.routines.service.scheduling import aware_utc as _aware_utc


@dataclass(frozen=True)
class PlanScope:
    world: models.World
    membership: models.WorldMembership
    world_character: models.WorldCharacter
    character: models.Character


def _load_scope(
    db: Session,
    *,
    character_id: str,
    world_id: str,
    user: models.User,
    lock_for_update: bool = False,
) -> PlanScope:
    character = db.get(models.Character, character_id)
    if character is None or character.deleted_at is not None:
        raise DailyActivityPlanNotFoundError(character_id)
    if character.owner_id != user.id:
        raise DailyActivityPlanForbiddenError(character_id)

    statement = select(models.WorldCharacter).where(
        models.WorldCharacter.world_id == world_id,
        models.WorldCharacter.character_id == character_id,
    )
    if lock_for_update:
        statement = statement.with_for_update()
    world_character = db.scalar(statement)
    if world_character is None:
        raise DailyActivityPlanNotFoundError(character_id)
    if world_character.control_mode != "autonomous":
        raise DailyActivityPlanValidationError(
            "owner_controlled_automation_disabled"
        )

    membership = db.get(models.WorldMembership, world_character.membership_id)
    if (
        membership is None
        or membership.world_id != world_id
        or membership.user_id != user.id
        or membership.status != "active"
    ):
        raise DailyActivityPlanValidationError("world_membership_inactive")
    world = db.get(models.World, world_id)
    if world is None:
        raise DailyActivityPlanNotFoundError(world_id)
    return PlanScope(world, membership, world_character, character)


def _ready_repertoire(
    db: Session,
    *,
    scope: PlanScope,
) -> tuple[models.WorldActivityRepertoire, list[models.WorldActivityCandidate]]:
    if scope.world.status != "published" or scope.world.readiness_status != "publish_ready":
        raise DailyActivityPlanValidationError("world_not_ready")
    if scope.world_character.status not in {"pending", "inactive", "active"}:
        raise DailyActivityPlanValidationError("world_character_ineligible")

    character_hash = character_contract_hash(scope.character)
    world_hash = scope.world.contract_hash
    repertoire = db.scalar(
        select(models.WorldActivityRepertoire).where(
            models.WorldActivityRepertoire.world_character_id
            == scope.world_character.id,
            models.WorldActivityRepertoire.status == "ready",
        )
    )
    if repertoire is None:
        raise DailyActivityPlanValidationError("repertoire_not_ready")
    profile = db.get(models.WorldCommunityProfile, repertoire.community_profile_id)
    if profile is None or profile.status != "ready":
        raise DailyActivityPlanValidationError("profile_not_ready")
    if (
        repertoire.character_contract_hash != character_hash
        or repertoire.world_contract_hash != world_hash
        or scope.world_character.character_contract_hash != character_hash
        or scope.world_character.world_contract_hash != world_hash
    ):
        raise DailyActivityPlanValidationError("repertoire_stale")

    candidates = list(
        db.scalars(
            select(models.WorldActivityCandidate).where(
                models.WorldActivityCandidate.repertoire_id == repertoire.id,
                models.WorldActivityCandidate.enabled.is_(True),
            )
        )
    )
    if len(candidates) != 40:
        raise DailyActivityPlanValidationError("repertoire_candidate_count_invalid")
    signatures = {candidate.canonical_signature for candidate in candidates}
    if len(signatures) != 40:
        raise DailyActivityPlanValidationError("repertoire_candidate_count_invalid")
    for daypart in DAYPARTS:
        if sum(candidate.daypart == daypart for candidate in candidates) != 10:
            raise DailyActivityPlanValidationError("daypart_candidate_count_invalid")
    return repertoire, candidates


def _selection_history(
    db: Session,
    *,
    world_character_id: str,
    local_date: date,
) -> list[tuple[models.DailyActivityPlanItem, date]]:
    earliest = local_date - timedelta(days=USAGE_WINDOW_DAYS)
    rows = db.execute(
        select(models.DailyActivityPlanItem, models.DailyActivityPlan.local_date)
        .join(
            models.DailyActivityPlan,
            models.DailyActivityPlan.id == models.DailyActivityPlanItem.plan_id,
        )
        .where(
            models.DailyActivityPlan.world_character_id == world_character_id,
            models.DailyActivityPlan.local_date >= earliest,
            models.DailyActivityPlan.local_date < local_date,
        )
    )
    return [(item, history_date) for item, history_date in rows]


def prepare_activity_plan(
    db: Session,
    *,
    character_id: str,
    world_id: str,
    user: models.User,
    data: schemas.DailyActivityPlanPrepareCreate,
    now: datetime | None = None,
) -> schemas.DailyActivityPlanRead:
    del data  # the date-scoped unique resource is the durable idempotency boundary
    current = _aware_utc(now or datetime.now(UTC))
    scope = _load_scope(
        db,
        character_id=character_id,
        world_id=world_id,
        user=user,
        lock_for_update=True,
    )
    target_date = local_activity_date(current, scope.world.timezone)
    existing = db.scalar(
        select(models.DailyActivityPlan).where(
            models.DailyActivityPlan.world_character_id == scope.world_character.id,
            models.DailyActivityPlan.local_date == target_date,
        )
    )
    if existing is not None:
        return _plan_read(
            db,
            plan=existing,
            world_character=scope.world_character,
            now=current,
            reused=True,
        )

    repertoire, candidates = _ready_repertoire(db, scope=scope)
    windows = daypart_windows(target_date, scope.world.timezone)
    history = _selection_history(
        db,
        world_character_id=scope.world_character.id,
        local_date=target_date,
    )
    reservations = {
        daypart: sqlalchemy_joint_reservations.reservation_for(
            db,
            world_character_id=scope.world_character.id,
            local_date=target_date,
            daypart=daypart,
        )
        for daypart in DAYPARTS
    }
    selected = {
        daypart: _select_candidate(
            world_character_id=scope.world_character.id,
            local_date=target_date,
            daypart=daypart,
            repertoire=repertoire,
            candidates=candidates,
            history=history,
        )
        for daypart in DAYPARTS
        if reservations[daypart] is None
    }
    seed_hash = sha256(
        "|".join(
            (
                scope.world_character.id,
                target_date.isoformat(),
                repertoire.id,
                f"p2-repertoire-v{repertoire.schema_version}",
                SELECTION_CONTRACT_VERSION,
            )
        ).encode("utf-8")
    ).hexdigest()
    plan = models.DailyActivityPlan(
        id=uuid7_string(),
        world_id=scope.world.id,
        world_character_id=scope.world_character.id,
        local_date=target_date,
        timezone_name=scope.world.timezone,
        timezone_contract_version=TIMEZONE_CONTRACT_VERSION,
        repertoire_id=repertoire.id,
        world_definition_hash=scope.world.contract_hash,
        character_definition_hash=repertoire.character_contract_hash,
        repertoire_contract_version=f"p2-repertoire-v{repertoire.schema_version}",
        selection_contract_version=SELECTION_CONTRACT_VERSION,
        selection_seed_hash=seed_hash,
        status="planned",
        revision_count=0,
        version=1,
    )
    db.add(plan)
    pending_episodes: list[models.ActivityEpisode] = []
    for daypart in DAYPARTS:
        start_at, end_at = windows[daypart]
        already_ended = end_at <= current
        reservation = reservations[daypart]
        if reservation is not None:
            if already_ended:
                db.rollback()
                raise DailyActivityPlanConflictError(
                    "joint_activity_reservation_expired"
                )
            try:
                sqlalchemy_joint_reservations.materialize_reservation_for_new_plan(
                    db,
                    plan=plan,
                    joint=reservation,
                    scheduled_start_at=start_at,
                    scheduled_end_at=end_at,
                    now=current,
                )
            except sqlalchemy_joint_reservations.JointActivityReservationError as exc:
                db.rollback()
                raise DailyActivityPlanConflictError(exc.reason_code) from exc
            continue
        candidate = selected[daypart]
        item = models.DailyActivityPlanItem(
            id=uuid7_string(),
            plan_id=plan.id,
            world_id=scope.world.id,
            world_character_id=scope.world_character.id,
            daypart=daypart,
            selected_candidate_id=candidate.id,
            candidate_signature=candidate.canonical_signature,
            candidate_ordinal=candidate.ordinal,
            activity_kind=candidate.activity_kind,
            title=candidate.title,
            activity_seed=candidate.activity_seed,
            social_mode=candidate.social_mode,
            place_key=candidate.place_key,
            scheduled_start_at=start_at,
            scheduled_end_at=end_at,
            status="skipped" if already_ended else "planned",
            revision_count=0,
            terminal_reason_code=("plan_created_after_window" if already_ended else None),
            version=1,
        )
        db.add(item)
        if not already_ended:
            pending_episodes.append(
                models.ActivityEpisode(
                    id=uuid7_string(),
                    world_id=scope.world.id,
                    world_character_id=scope.world_character.id,
                    plan_item_id=item.id,
                    effective_activity_snapshot=_snapshot(candidate),
                    status="planned",
                    current_state_schema_version=1,
                    current_state_snapshot=dict(INITIAL_STATE),
                    next_sequence_no=1,
                    version=1,
                )
            )
    try:
        db.flush()
        db.add_all(pending_episodes)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        replay = db.scalar(
            select(models.DailyActivityPlan).where(
                models.DailyActivityPlan.world_character_id
                == scope.world_character.id,
                models.DailyActivityPlan.local_date == target_date,
            )
        )
        if replay is None:
            raise DailyActivityPlanConflictError("activity_plan_conflict") from exc
        return _plan_read(
            db,
            plan=replay,
            world_character=scope.world_character,
            now=current,
            reused=True,
        )
    return _plan_read(
        db,
        plan=plan,
        world_character=scope.world_character,
        now=current,
        reused=False,
    )


def get_activity_plan(
    db: Session,
    *,
    character_id: str,
    world_id: str,
    user: models.User,
    now: datetime | None = None,
) -> schemas.DailyActivityPlanRead:
    current = _aware_utc(now or datetime.now(UTC))
    scope = _load_scope(
        db,
        character_id=character_id,
        world_id=world_id,
        user=user,
    )
    target_date = local_activity_date(current, scope.world.timezone)
    plan = db.scalar(
        select(models.DailyActivityPlan).where(
            models.DailyActivityPlan.world_character_id == scope.world_character.id,
            models.DailyActivityPlan.local_date == target_date,
        )
    )
    if plan is None:
        raise DailyActivityPlanNotFoundError(character_id)
    return _plan_read(
        db,
        plan=plan,
        world_character=scope.world_character,
        now=current,
        reused=True,
    )


def update_activity_runtime_mode(
    db: Session,
    *,
    character_id: str,
    world_id: str,
    user: models.User,
    data: schemas.WorldCharacterRuntimeModeUpdate,
    now: datetime | None = None,
) -> schemas.WorldCharacterRuntimeModeRead:
    current = _aware_utc(now or datetime.now(UTC))
    scope = _load_scope(
        db,
        character_id=character_id,
        world_id=world_id,
        user=user,
        lock_for_update=True,
    )
    if data.activity_runtime_mode == "routine_resident_v1":
        repertoire, _candidates = _ready_repertoire(db, scope=scope)
        credential = db.get(models.LlmCredential, repertoire.credential_id)
        if (
            credential is None
            or not credential.enabled
            or credential.owner_id != user.id
            or credential.character_id not in {None, character_id}
        ):
            raise DailyActivityPlanValidationError("credential_required")
        target_date = local_activity_date(current, scope.world.timezone)
        plan = db.scalar(
            select(models.DailyActivityPlan).where(
                models.DailyActivityPlan.world_character_id
                == scope.world_character.id,
                models.DailyActivityPlan.local_date == target_date,
            )
        )
        if plan is None:
            raise DailyActivityPlanValidationError("activity_plan_not_ready")
        plan_read = _plan_read(
            db,
            plan=plan,
            world_character=scope.world_character,
            now=current,
            reused=True,
        )
        if plan_read.current_daypart is None:
            raise DailyActivityPlanValidationError("activity_plan_not_ready")
        current_item = next(
            (item for item in plan_read.items if item.daypart == plan_read.current_daypart),
            None,
        )
        if current_item is None or current_item.episode is None:
            raise DailyActivityPlanValidationError("activity_plan_not_ready")

    scope.world_character.activity_runtime_mode = data.activity_runtime_mode
    scope.world_character.version += 1
    db.commit()
    return schemas.WorldCharacterRuntimeModeRead(
        world_character_id=scope.world_character.id,
        world_id=scope.world_character.world_id,
        character_id=scope.world_character.character_id,
        activity_runtime_mode=scope.world_character.activity_runtime_mode,
        autonomous_enabled=scope.world_character.autonomous_enabled,
    )


def _plan_read(
    db: Session,
    *,
    plan: models.DailyActivityPlan,
    world_character: models.WorldCharacter,
    now: datetime,
    reused: bool,
) -> schemas.DailyActivityPlanRead:
    items = list(
        db.scalars(
            select(models.DailyActivityPlanItem).where(
                models.DailyActivityPlanItem.plan_id == plan.id,
                models.DailyActivityPlanItem.status != "superseded",
            )
        )
    )
    if len(items) != 4:
        raise DailyActivityPlanValidationError("activity_plan_partial")
    item_ids = [item.id for item in items]
    episodes = {
        episode.plan_item_id: episode
        for episode in db.scalars(
            select(models.ActivityEpisode).where(
                models.ActivityEpisode.plan_item_id.in_(item_ids)
            )
        )
    }
    successful_beat_ids = [
        episode.last_successful_beat_id
        for episode in episodes.values()
        if episode.last_successful_beat_id is not None
    ]
    successful_beats = (
        {
            beat.id: beat
            for beat in db.scalars(
                select(models.ActivityBeat).where(
                    models.ActivityBeat.id.in_(successful_beat_ids),
                    models.ActivityBeat.status == "succeeded",
                )
            )
        }
        if successful_beat_ids
        else {}
    )
    all_beats = list(
        db.scalars(
            select(models.ActivityBeat)
            .where(models.ActivityBeat.episode_id.in_([episode.id for episode in episodes.values()]))
            .order_by(models.ActivityBeat.created_at.desc(), models.ActivityBeat.id.desc())
        )
    )
    latest_beats: dict[str, models.ActivityBeat] = {}
    for beat in all_beats:
        latest_beats.setdefault(beat.episode_id, beat)
    order = {daypart: index for index, daypart in enumerate(DAYPARTS)}
    items.sort(key=lambda item: order[item.daypart])
    current_daypart = next(
        (
            item.daypart
            for item in items
            if _aware_utc(item.scheduled_start_at)
            <= now
            < _aware_utc(item.scheduled_end_at)
        ),
        None,
    )
    item_reads: list[schemas.DailyActivityPlanItemRead] = []
    for item in items:
        episode = episodes.get(item.id)
        last_successful_beat = (
            successful_beats.get(episode.last_successful_beat_id)
            if episode is not None and episode.last_successful_beat_id is not None
            else None
        )
        latest_beat = latest_beats.get(episode.id) if episode is not None else None
        result_snapshot = (
            last_successful_beat.result_snapshot
            if last_successful_beat is not None
            and isinstance(last_successful_beat.result_snapshot, dict)
            else {}
        )
        considered_ids = result_snapshot.get("considered_source_event_ids", [])
        used_ids = result_snapshot.get("used_source_event_ids", [])
        overflow_count = result_snapshot.get("overflow_count", 0)
        item_reads.append(
            schemas.DailyActivityPlanItemRead(
                id=item.id,
                daypart=item.daypart,
                selected_candidate_id=item.selected_candidate_id,
                origin_type=item.origin_type,
                supersedes_plan_item_id=item.supersedes_plan_item_id,
                is_user_pinned=item.is_user_pinned,
                candidate_signature=item.candidate_signature,
                candidate_ordinal=item.candidate_ordinal,
                activity_kind=item.activity_kind,
                title=item.title,
                activity_seed=item.activity_seed,
                social_mode=item.social_mode,
                place_key=item.place_key,
                joint_activity_id=item.joint_activity_id,
                scheduled_start_at=_aware_utc(item.scheduled_start_at),
                scheduled_end_at=_aware_utc(item.scheduled_end_at),
                status=item.status,
                revision_count=item.revision_count,
                terminal_reason_code=item.terminal_reason_code,
                episode=(
                    schemas.ActivityEpisodeRead(
                        id=episode.id,
                        plan_item_id=episode.plan_item_id,
                        status=episode.status,
                        current_state_schema_version=episode.current_state_schema_version,
                        current_state_snapshot=episode.current_state_snapshot,
                        last_successful_beat_id=episode.last_successful_beat_id,
                        last_successful_post_id=(
                            last_successful_beat.source_post_id
                            if last_successful_beat is not None
                            else None
                        ),
                        last_successful_sequence_no=(
                            last_successful_beat.sequence_no
                            if last_successful_beat is not None
                            else None
                        ),
                        last_successful_beat_at=(
                            _aware_utc(last_successful_beat.completed_at)
                            if last_successful_beat is not None
                            and last_successful_beat.completed_at is not None
                            else None
                        ),
                        considered_event_count=(
                            len(considered_ids) if isinstance(considered_ids, list) else 0
                        ),
                        used_event_count=(
                            len(used_ids) if isinstance(used_ids, list) else 0
                        ),
                        overflow_event_count=(
                            overflow_count
                            if isinstance(overflow_count, int)
                            and not isinstance(overflow_count, bool)
                            and overflow_count >= 0
                            else 0
                        ),
                        recent_outcome=(
                            (
                                latest_beat.failure_reason_code
                                or latest_beat.status
                            )
                            if latest_beat is not None
                            else None
                        ),
                        next_sequence_no=episode.next_sequence_no,
                        started_at=episode.started_at,
                        completed_at=episode.completed_at,
                        terminal_reason_code=episode.terminal_reason_code,
                    )
                    if episode is not None
                    else None
                ),
            )
        )
    return schemas.DailyActivityPlanRead(
        id=plan.id,
        world_id=plan.world_id,
        world_character_id=plan.world_character_id,
        local_date=plan.local_date,
        timezone_name=plan.timezone_name,
        timezone_contract_version=plan.timezone_contract_version,
        repertoire_id=plan.repertoire_id,
        world_definition_hash=plan.world_definition_hash,
        character_definition_hash=plan.character_definition_hash,
        repertoire_contract_version=plan.repertoire_contract_version,
        selection_contract_version=plan.selection_contract_version,
        selection_seed_hash=plan.selection_seed_hash,
        status=plan.status,
        revision_count=plan.revision_count,
        version=plan.version,
        autonomous_enabled=world_character.autonomous_enabled,
        activity_runtime_mode=world_character.activity_runtime_mode,
        current_daypart=current_daypart,
        reused=reused,
        items=item_reads,
    )
