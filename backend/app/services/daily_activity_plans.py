from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from hashlib import sha256
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models, schemas
from app.core.ids import uuid7_string
from app.services import world_character_contracts


DAYPARTS = ("dawn", "morning", "afternoon", "evening")
DAYPART_START_HOURS = (0, 6, 12, 18)
SELECTION_CONTRACT_VERSION = "daily-activity-selection-v1"
TIMEZONE_CONTRACT_VERSION = "world-local-dayparts-v1"
EVENT_CONSUMPTION_NAMESPACE = "next_activity_beat"
RECENT_EXACT_DAYS = 3
USAGE_WINDOW_DAYS = 7

INITIAL_STATE = {
    "mood": "neutral",
    "mood_intensity": 0,
    "energy": 50,
    "social_energy": 50,
    "action_note": "",
}


class DailyActivityPlanError(Exception):
    reason_code = "daily_activity_plan_error"


class DailyActivityPlanNotFoundError(DailyActivityPlanError):
    reason_code = "activity_plan_not_found"


class DailyActivityPlanForbiddenError(DailyActivityPlanError):
    reason_code = "character_not_owned"


class DailyActivityPlanConflictError(DailyActivityPlanError):
    reason_code = "activity_plan_conflict"

    def __init__(self, reason_code: str | None = None) -> None:
        if reason_code is not None:
            self.reason_code = reason_code
        super().__init__(self.reason_code)


class DailyActivityPlanValidationError(DailyActivityPlanError):
    reason_code = "activity_plan_invalid"

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


@dataclass(frozen=True)
class PlanScope:
    world: models.World
    membership: models.WorldMembership
    world_character: models.WorldCharacter
    character: models.Character


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


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


def _zone(timezone_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise DailyActivityPlanValidationError("world_timezone_invalid") from exc


def _resolve_local_boundary(local_naive: datetime, zone: ZoneInfo) -> datetime:
    probe = local_naive
    for _ in range(181):
        candidates: list[datetime] = []
        for fold in (0, 1):
            aware = probe.replace(tzinfo=zone, fold=fold)
            instant = aware.astimezone(UTC)
            round_trip = instant.astimezone(zone).replace(tzinfo=None)
            if round_trip == probe:
                candidates.append(instant)
        if candidates:
            return min(candidates)
        probe += timedelta(minutes=1)
    raise DailyActivityPlanValidationError("world_timezone_invalid")


def daypart_windows(
    local_date: date,
    timezone_name: str,
) -> dict[str, tuple[datetime, datetime]]:
    zone = _zone(timezone_name)
    local_boundaries = [
        datetime.combine(local_date, time(hour=hour))
        for hour in DAYPART_START_HOURS
    ]
    local_boundaries.append(datetime.combine(local_date + timedelta(days=1), time()))
    utc_boundaries = [
        _resolve_local_boundary(boundary, zone) for boundary in local_boundaries
    ]
    if any(
        current >= following
        for current, following in zip(utc_boundaries, utc_boundaries[1:])
    ):
        raise DailyActivityPlanValidationError("world_timezone_invalid")
    return {
        daypart: (utc_boundaries[index], utc_boundaries[index + 1])
        for index, daypart in enumerate(DAYPARTS)
    }


def local_activity_date(now: datetime, timezone_name: str) -> date:
    return _aware_utc(now).astimezone(_zone(timezone_name)).date()


def _ready_repertoire(
    db: Session,
    *,
    scope: PlanScope,
) -> tuple[models.WorldActivityRepertoire, list[models.WorldActivityCandidate]]:
    if scope.world.status != "published" or scope.world.readiness_status != "publish_ready":
        raise DailyActivityPlanValidationError("world_not_ready")
    if scope.world_character.status not in {"pending", "inactive", "active"}:
        raise DailyActivityPlanValidationError("world_character_ineligible")

    character_hash = world_character_contracts.character_contract_hash(scope.character)
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


def _select_candidate(
    *,
    world_character_id: str,
    local_date: date,
    daypart: str,
    repertoire: models.WorldActivityRepertoire,
    candidates: list[models.WorldActivityCandidate],
    history: list[tuple[models.DailyActivityPlanItem, date]],
) -> models.WorldActivityCandidate:
    options = [candidate for candidate in candidates if candidate.daypart == daypart]
    recent_cutoff = local_date - timedelta(days=RECENT_EXACT_DAYS)
    recent_signatures = {
        item.candidate_signature
        for item, history_date in history
        if item.daypart == daypart and history_date >= recent_cutoff
    }
    unused = [
        candidate
        for candidate in options
        if candidate.canonical_signature not in recent_signatures
    ]
    pool = unused or options
    usage = Counter(
        item.candidate_signature
        for item, _history_date in history
        if item.daypart == daypart
    )
    minimum_usage = min(usage[candidate.canonical_signature] for candidate in pool)
    pool = [
        candidate
        for candidate in pool
        if usage[candidate.canonical_signature] == minimum_usage
    ]
    previous_kind = next(
        (
            item.activity_kind
            for item, history_date in history
            if item.daypart == daypart
            and history_date == local_date - timedelta(days=1)
        ),
        None,
    )
    different_kind = [
        candidate for candidate in pool if candidate.activity_kind != previous_kind
    ]
    if different_kind:
        pool = different_kind

    base_seed = "|".join(
        (
            world_character_id,
            local_date.isoformat(),
            daypart,
            repertoire.id,
            f"p2-repertoire-v{repertoire.schema_version}",
            SELECTION_CONTRACT_VERSION,
        )
    )
    return min(
        pool,
        key=lambda candidate: sha256(
            f"{base_seed}|{candidate.canonical_signature}".encode("utf-8")
        ).hexdigest(),
    )


def _snapshot(candidate: models.WorldActivityCandidate) -> dict[str, object]:
    return {
        "candidate_id": candidate.id,
        "candidate_signature": candidate.canonical_signature,
        "candidate_ordinal": candidate.ordinal,
        "daypart": candidate.daypart,
        "activity_kind": candidate.activity_kind,
        "title": candidate.title,
        "activity_seed": candidate.activity_seed,
        "social_mode": candidate.social_mode,
        "place_key": candidate.place_key,
    }


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
        candidate = selected[daypart]
        start_at, end_at = windows[daypart]
        already_ended = end_at <= current
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
                models.DailyActivityPlanItem.plan_id == plan.id
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
        item_reads.append(
            schemas.DailyActivityPlanItemRead(
                id=item.id,
                daypart=item.daypart,
                selected_candidate_id=item.selected_candidate_id,
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
                        last_successful_beat_at=(
                            _aware_utc(last_successful_beat.completed_at)
                            if last_successful_beat is not None
                            and last_successful_beat.completed_at is not None
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
        current_daypart=current_daypart,
        reused=reused,
        items=item_reads,
    )
