from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from hashlib import sha256
import json
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app import models
from app.core.ids import uuid7_string
from app.models.social_memory import SOCIAL_EVENT_TYPES


SOCIAL_EVENT_SCHEMA_VERSION = "social-event-v1"
GRAPH_PAYLOAD_VERSION = "relationship-v1"
SOURCE_EXCLUSION_PAYLOAD_VERSION = "source-exclusion-v1"


class SocialEventRuntimeError(Exception):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


@dataclass(frozen=True)
class EvidenceInput:
    evidence_kind: Literal[
        "post",
        "reply_post",
        "like",
        "repost",
        "follow",
        "notification",
        "execution",
        "joint_activity",
    ]
    source_object_type: Literal[
        "post",
        "post_like",
        "post_repost",
        "profile_follow",
        "notification",
        "agent_public_action_execution",
        "joint_activity",
    ]
    source_object_id: str
    root_post_id: str | None = None
    source_post_id: str | None = None
    target_post_id: str | None = None
    source_notification_id: int | None = None
    agent_run_id: str | None = None
    public_action_execution_id: int | None = None
    interaction_intent: str | None = None
    comment_purpose: str | None = None
    proposal_decision: str | None = None
    source_text: str | None = None
    source_visibility_at_event: str | None = None
    source_author_id_at_event: str | None = None


@dataclass(frozen=True)
class EventApplyResult:
    event: models.SocialEvent
    relationship_state: models.RelationshipState | None
    relationship_change: models.RelationshipStateChange | None
    reused: bool


@dataclass(frozen=True)
class _Delta:
    familiarity: int = 0
    affinity: int = 0
    trust: int = 0
    tension: int = 0
    valence: str = "neutral"
    intensity: str = "low"


_RELATION_EVENT_TYPES = {
    "comment_created",
    "reply_created",
    "mention_created",
    "like_added",
    "like_removed",
    "follow_added",
    "follow_removed",
    "repost_added",
    "repost_removed",
    "joint_accepted",
    "joint_completed",
    "joint_declined",
    "joint_cancelled",
}


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _world_zone(world: models.World) -> ZoneInfo:
    try:
        return ZoneInfo(world.timezone)
    except ZoneInfoNotFoundError as exc:
        raise SocialEventRuntimeError("world_timezone_invalid") from exc


def _local_day_bounds(world: models.World, occurred_at: datetime) -> tuple[datetime, datetime]:
    zone = _world_zone(world)
    local_date = _aware_utc(occurred_at).astimezone(zone).date()
    start = datetime.combine(local_date, time.min, tzinfo=zone).astimezone(UTC)
    return start, start + timedelta(days=1)


def _snapshot(state: models.RelationshipState) -> dict[str, int]:
    return {
        "familiarity": state.familiarity,
        "affinity": state.affinity,
        "trust": state.trust,
        "tension": state.tension,
        "interaction_count": state.interaction_count,
        "version": state.version,
    }


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


def _purpose_delta(event_type: str, purpose: str | None) -> _Delta:
    positive = {"empathy", "encouragement", "humor"}
    neutral = {"question", "advice", "information", "observation"}
    if purpose in positive:
        valence, intensity = "positive", "low"
        affinity = 1 if event_type == "comment_created" else 2
        trust = 0 if event_type == "comment_created" else 1
        tension = 0
    elif purpose == "competition":
        valence, intensity = "negative", "medium"
        affinity = -1 if event_type == "comment_created" else -2
        trust = 0
        tension = 1 if event_type == "comment_created" else 2
    elif purpose == "disagreement":
        valence, intensity = "negative", "low"
        affinity = -1
        trust = 0
        tension = 1
    elif purpose in neutral or purpose is None:
        valence, intensity = "neutral", "low"
        affinity = trust = tension = 0
    else:
        raise SocialEventRuntimeError("comment_purpose_invalid")
    return _Delta(
        familiarity=2,
        affinity=affinity,
        trust=trust,
        tension=tension,
        valence=valence,
        intensity=intensity,
    )


def _delta(event_type: str, purpose: str | None) -> _Delta:
    if event_type in {"comment_created", "reply_created", "mention_created"}:
        return _purpose_delta(event_type, purpose)
    return {
        "like_added": _Delta(familiarity=1, affinity=1, valence="positive"),
        "follow_added": _Delta(familiarity=3, affinity=1, valence="positive"),
        "follow_removed": _Delta(affinity=-1, valence="negative"),
        "repost_added": _Delta(familiarity=2, affinity=1, valence="positive"),
        "joint_accepted": _Delta(familiarity=2, trust=1, valence="positive"),
        "joint_completed": _Delta(
            familiarity=4,
            affinity=2,
            trust=3,
            valence="positive",
            intensity="medium",
        ),
    }.get(event_type, _Delta())


def _validate_world_character(
    db: Session,
    *,
    world_id: str,
    world_character_id: str,
    lock: bool = False,
) -> models.WorldCharacter:
    statement = select(models.WorldCharacter).where(
        models.WorldCharacter.id == world_character_id
    )
    if lock:
        statement = statement.with_for_update()
    row = db.scalar(statement)
    if row is None or row.world_id != world_id:
        raise SocialEventRuntimeError("cross_world_reference")
    if row.status != "active":
        raise SocialEventRuntimeError("world_character_inactive")
    membership = db.get(models.WorldMembership, row.membership_id)
    if (
        membership is None
        or membership.world_id != world_id
        or membership.status != "active"
    ):
        raise SocialEventRuntimeError("world_membership_inactive")
    return row


def _pair_blocked(
    db: Session,
    *,
    world_id: str,
    first_world_character_id: str,
    second_world_character_id: str,
) -> bool:
    return db.scalar(
        select(models.WorldCharacterBlock.id).where(
            models.WorldCharacterBlock.world_id == world_id,
            or_(
                (
                    models.WorldCharacterBlock.blocker_world_character_id
                    == first_world_character_id
                )
                & (
                    models.WorldCharacterBlock.blocked_world_character_id
                    == second_world_character_id
                ),
                (
                    models.WorldCharacterBlock.blocker_world_character_id
                    == second_world_character_id
                )
                & (
                    models.WorldCharacterBlock.blocked_world_character_id
                    == first_world_character_id
                ),
            ),
        )
    ) is not None


def _validate_live_public_post(post: models.Post | None, *, world_id: str) -> None:
    if post is None or post.world_id != world_id:
        raise SocialEventRuntimeError("evidence_post_world_mismatch")
    if post.deleted_at is not None:
        raise SocialEventRuntimeError("evidence_source_deleted")
    if post.report_hidden_at is not None or post.visibility != "public":
        raise SocialEventRuntimeError("evidence_source_hidden")


def _validate_evidence_source(
    db: Session, *, world_id: str, evidence: EvidenceInput
) -> None:
    source: object | None
    if evidence.source_object_type == "post":
        source = db.get(models.Post, evidence.source_object_id)
        _validate_live_public_post(source, world_id=world_id)
    elif evidence.source_object_type in {
        "post_like",
        "post_repost",
        "profile_follow",
        "notification",
        "agent_public_action_execution",
    }:
        try:
            source_id = int(evidence.source_object_id)
        except (TypeError, ValueError) as exc:
            raise SocialEventRuntimeError("evidence_source_invalid") from exc
        source_model = {
            "post_like": models.PostLike,
            "post_repost": models.PostRepost,
            "profile_follow": models.ProfileFollow,
            "notification": models.Notification,
            "agent_public_action_execution": models.AgentPublicActionExecution,
        }[evidence.source_object_type]
        source = db.get(source_model, source_id)
    else:
        source = db.get(models.JointActivity, evidence.source_object_id)
    if source is None:
        raise SocialEventRuntimeError("evidence_source_invalid")
    if getattr(source, "world_id", None) != world_id:
        raise SocialEventRuntimeError("evidence_source_world_mismatch")
    post_ids = {
        post_id
        for post_id in (
            evidence.root_post_id,
            evidence.source_post_id,
            evidence.target_post_id,
        )
        if post_id is not None
    }
    for post_id in post_ids:
        _validate_live_public_post(db.get(models.Post, post_id), world_id=world_id)


def _relationship_state(
    db: Session,
    *,
    world_id: str,
    actor_world_character_id: str,
    target_world_character_id: str,
) -> models.RelationshipState:
    state = db.scalar(
        select(models.RelationshipState)
        .where(
            models.RelationshipState.world_id == world_id,
            models.RelationshipState.actor_world_character_id
            == actor_world_character_id,
            models.RelationshipState.target_world_character_id
            == target_world_character_id,
        )
        .with_for_update()
    )
    if state is None:
        state = models.RelationshipState(
            id=uuid7_string(),
            world_id=world_id,
            actor_world_character_id=actor_world_character_id,
            target_world_character_id=target_world_character_id,
            familiarity=0,
            affinity=0,
            trust=0,
            tension=0,
            interaction_count=0,
            version=1,
        )
        db.add(state)
        db.flush()
    return state


def _delta_is_capped(
    db: Session,
    *,
    world: models.World,
    event: models.SocialEvent,
    evidence: EvidenceInput,
) -> bool:
    if event.target_world_character_id is None:
        return False
    if event.event_type in {"comment_created", "reply_created", "mention_created"}:
        start, end = _local_day_bounds(world, event.occurred_at)
        count = db.scalar(
            select(func.count(models.RelationshipStateChange.id))
            .join(
                models.SocialEvent,
                models.SocialEvent.id == models.RelationshipStateChange.social_event_id,
            )
            .where(
                models.RelationshipStateChange.world_id == event.world_id,
                models.RelationshipStateChange.actor_world_character_id
                == event.actor_world_character_id,
                models.RelationshipStateChange.target_world_character_id
                == event.target_world_character_id,
                models.RelationshipStateChange.applied.is_(True),
                models.SocialEvent.event_type.in_(
                    ("comment_created", "reply_created", "mention_created")
                ),
                models.SocialEvent.occurred_at >= start,
                models.SocialEvent.occurred_at < end,
            )
        )
        return int(count or 0) >= 4
    if event.event_type not in {"like_added", "repost_added"}:
        return False
    source_post_id = evidence.target_post_id or evidence.source_post_id
    if source_post_id is None:
        return False
    prior = db.scalar(
        select(models.RelationshipStateChange.id)
        .join(
            models.SocialEvent,
            models.SocialEvent.id == models.RelationshipStateChange.social_event_id,
        )
        .join(
            models.SocialEventEvidence,
            models.SocialEventEvidence.social_event_id == models.SocialEvent.id,
        )
        .where(
            models.RelationshipStateChange.world_id == event.world_id,
            models.RelationshipStateChange.actor_world_character_id
            == event.actor_world_character_id,
            models.RelationshipStateChange.target_world_character_id
            == event.target_world_character_id,
            models.RelationshipStateChange.applied.is_(True),
            models.SocialEvent.event_type == event.event_type,
            models.SocialEventEvidence.target_post_id == source_post_id,
            models.SocialEvent.id != event.id,
        )
        .limit(1)
    )
    return prior is not None


def _enqueue_outbox(
    db: Session,
    *,
    event: models.SocialEvent,
    relationship_state: models.RelationshipState | None,
) -> models.GraphProjectionOutbox:
    if event.event_type in {
        "joint_proposed",
        "joint_declined",
        "joint_cancelled",
        "joint_started",
    }:
        projection_type = "source_exclusion"
    elif relationship_state is not None:
        projection_type = "relationship_state"
    else:
        projection_type = "social_event"
    payload: dict[str, object] = {
        "world_id": event.world_id,
        "source_event_id": event.id,
        "actor_world_character_id": event.actor_world_character_id,
        "target_world_character_id": event.target_world_character_id,
    }
    if relationship_state is not None:
        payload["relationship_state_id"] = relationship_state.id
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    signature = sha256(canonical.encode("utf-8")).hexdigest()
    dedupe_key = sha256(
        f"{projection_type}|{event.id}|{GRAPH_PAYLOAD_VERSION}".encode("utf-8")
    ).hexdigest()
    existing = db.scalar(
        select(models.GraphProjectionOutbox).where(
            models.GraphProjectionOutbox.dedupe_key == dedupe_key
        )
    )
    if existing is not None:
        return existing
    row = models.GraphProjectionOutbox(
        id=uuid7_string(),
        world_id=event.world_id,
        source_event_id=event.id,
        projection_type=projection_type,
        payload_version=GRAPH_PAYLOAD_VERSION,
        payload=payload,
        source_signature=signature,
        dedupe_key=dedupe_key,
        status="pending",
        attempt_count=0,
    )
    db.add(row)
    return row


def _enqueue_source_exclusion_outbox(
    db: Session,
    *,
    event: models.SocialEvent,
    reason: Literal["source_deleted", "source_hidden"],
) -> models.GraphProjectionOutbox:
    projection_type = "source_exclusion"
    payload: dict[str, object] = {
        "world_id": event.world_id,
        "source_event_id": event.id,
        "reason": reason,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    signature = sha256(canonical.encode("utf-8")).hexdigest()
    dedupe_key = sha256(
        (
            f"{projection_type}|{event.id}|"
            f"{SOURCE_EXCLUSION_PAYLOAD_VERSION}"
        ).encode("utf-8")
    ).hexdigest()
    existing = db.scalar(
        select(models.GraphProjectionOutbox).where(
            models.GraphProjectionOutbox.dedupe_key == dedupe_key
        )
    )
    if existing is not None:
        return existing
    row = models.GraphProjectionOutbox(
        id=uuid7_string(),
        world_id=event.world_id,
        source_event_id=event.id,
        projection_type=projection_type,
        payload_version=SOURCE_EXCLUSION_PAYLOAD_VERSION,
        payload=payload,
        source_signature=signature,
        dedupe_key=dedupe_key,
        status="pending",
        attempt_count=0,
    )
    db.add(row)
    return row


def exclude_events_for_posts(
    db: Session,
    *,
    post_ids: list[str],
    reason: Literal["source_deleted", "source_hidden"],
    invalidated_at: datetime,
) -> int:
    unique_post_ids = sorted({post_id for post_id in post_ids if post_id})
    if not unique_post_ids:
        return 0
    event_ids = list(
        db.scalars(
            select(models.SocialEventEvidence.social_event_id)
            .where(
                or_(
                    models.SocialEventEvidence.root_post_id.in_(unique_post_ids),
                    models.SocialEventEvidence.source_post_id.in_(unique_post_ids),
                    models.SocialEventEvidence.target_post_id.in_(unique_post_ids),
                    (
                        (models.SocialEventEvidence.source_object_type == "post")
                        & (
                            models.SocialEventEvidence.source_object_id.in_(
                                unique_post_ids
                            )
                        )
                    ),
                )
            )
            .distinct()
        )
    )
    changed = 0
    for event_id in event_ids:
        event = db.scalar(
            select(models.SocialEvent)
            .where(models.SocialEvent.id == event_id)
            .with_for_update()
        )
        if event is None:
            continue
        if (
            event.retrieval_status != "excluded"
            or event.invalidation_reason != reason
        ):
            event.retrieval_status = "excluded"
            event.invalidated_at = _aware_utc(invalidated_at)
            event.invalidation_reason = reason
            changed += 1
        _enqueue_source_exclusion_outbox(db, event=event, reason=reason)
    db.flush()
    return changed


def record_successful_social_event(
    db: Session,
    *,
    world_id: str,
    actor_world_character_id: str,
    target_world_character_id: str | None,
    event_type: str,
    occurred_at: datetime,
    idempotency_key: str,
    evidence: EvidenceInput,
) -> EventApplyResult:
    if event_type not in SOCIAL_EVENT_TYPES:
        raise SocialEventRuntimeError("event_type_invalid")
    if len(idempotency_key) > 128 or not idempotency_key:
        raise SocialEventRuntimeError("event_idempotency_invalid")
    world = db.get(models.World, world_id)
    if world is None:
        raise SocialEventRuntimeError("world_not_found")
    _validate_world_character(
        db,
        world_id=world_id,
        world_character_id=actor_world_character_id,
        lock=True,
    )
    if target_world_character_id is not None:
        if target_world_character_id == actor_world_character_id:
            raise SocialEventRuntimeError("self_target_forbidden")
        _validate_world_character(
            db,
            world_id=world_id,
            world_character_id=target_world_character_id,
        )
        if _pair_blocked(
            db,
            world_id=world_id,
            first_world_character_id=actor_world_character_id,
            second_world_character_id=target_world_character_id,
        ):
            raise SocialEventRuntimeError("world_character_blocked")
    elif event_type not in {"post_published", "joint_started"}:
        raise SocialEventRuntimeError("event_target_required")
    existing = db.scalar(
        select(models.SocialEvent).where(
            models.SocialEvent.idempotency_key == idempotency_key
        )
    )
    if existing is not None:
        if (
            existing.world_id != world_id
            or existing.actor_world_character_id != actor_world_character_id
            or existing.target_world_character_id != target_world_character_id
            or existing.event_type != event_type
            or existing.result != "succeeded"
        ):
            raise SocialEventRuntimeError("event_idempotency_collision")
        state = None
        change = None
        if existing.target_world_character_id is not None:
            state = db.scalar(
                select(models.RelationshipState).where(
                    models.RelationshipState.world_id == existing.world_id,
                    models.RelationshipState.actor_world_character_id
                    == existing.actor_world_character_id,
                    models.RelationshipState.target_world_character_id
                    == existing.target_world_character_id,
                )
            )
            if state is not None:
                change = db.scalar(
                    select(models.RelationshipStateChange).where(
                        models.RelationshipStateChange.relationship_state_id == state.id,
                        models.RelationshipStateChange.social_event_id == existing.id,
                    )
                )
        return EventApplyResult(existing, state, change, True)

    _validate_evidence_source(db, world_id=world_id, evidence=evidence)
    event = models.SocialEvent(
        id=uuid7_string(),
        world_id=world_id,
        actor_world_character_id=actor_world_character_id,
        target_world_character_id=target_world_character_id,
        event_type=event_type,
        result="succeeded",
        occurred_at=_aware_utc(occurred_at),
        idempotency_key=idempotency_key,
        schema_version=SOCIAL_EVENT_SCHEMA_VERSION,
        retrieval_status="eligible",
    )
    db.add(event)
    db.flush()
    evidence_row = models.SocialEventEvidence(
        id=uuid7_string(),
        social_event_id=event.id,
        evidence_kind=evidence.evidence_kind,
        source_object_type=evidence.source_object_type,
        source_object_id=evidence.source_object_id,
        root_post_id=evidence.root_post_id,
        source_post_id=evidence.source_post_id,
        target_post_id=evidence.target_post_id,
        source_notification_id=evidence.source_notification_id,
        agent_run_id=evidence.agent_run_id,
        public_action_execution_id=evidence.public_action_execution_id,
        interaction_intent=evidence.interaction_intent,
        comment_purpose=evidence.comment_purpose,
        proposal_decision=evidence.proposal_decision,
        content_sha256=(
            sha256(evidence.source_text.encode("utf-8")).hexdigest()
            if evidence.source_text is not None
            else None
        ),
        source_visibility_at_event=evidence.source_visibility_at_event,
        source_author_id_at_event=evidence.source_author_id_at_event,
        occurred_at=event.occurred_at,
    )
    db.add(evidence_row)

    state: models.RelationshipState | None = None
    change: models.RelationshipStateChange | None = None
    if (
        target_world_character_id is not None
        and event_type in _RELATION_EVENT_TYPES
    ):
        state = _relationship_state(
            db,
            world_id=world_id,
            actor_world_character_id=actor_world_character_id,
            target_world_character_id=target_world_character_id,
        )
        before = _snapshot(state)
        delta = _delta(event_type, evidence.comment_purpose)
        capped = _delta_is_capped(
            db, world=world, event=event, evidence=evidence
        )
        has_delta = any(
            (delta.familiarity, delta.affinity, delta.trust, delta.tension)
        )
        applied = has_delta and not capped
        if applied:
            state.familiarity = _clamp(
                state.familiarity + delta.familiarity, 0, 100
            )
            state.affinity = _clamp(state.affinity + delta.affinity, -100, 100)
            state.trust = _clamp(state.trust + delta.trust, -100, 100)
            state.tension = _clamp(state.tension + delta.tension, 0, 100)
        state.interaction_count += 1
        state.last_event_id = event.id
        state.last_event_at = event.occurred_at
        state.version += 1
        after = _snapshot(state)
        change = models.RelationshipStateChange(
            id=uuid7_string(),
            relationship_state_id=state.id,
            social_event_id=event.id,
            world_id=world_id,
            actor_world_character_id=actor_world_character_id,
            target_world_character_id=target_world_character_id,
            valence=delta.valence,
            intensity=delta.intensity,
            delta_familiarity=delta.familiarity if applied else 0,
            delta_affinity=delta.affinity if applied else 0,
            delta_trust=delta.trust if applied else 0,
            delta_tension=delta.tension if applied else 0,
            before_snapshot=before,
            after_snapshot=after,
            applied=applied,
            not_applied_reason=(
                "daily_delta_cap" if capped else (None if has_delta else "no_delta_event")
            ),
        )
        db.add(change)
    _enqueue_outbox(db, event=event, relationship_state=state)
    if evidence.public_action_execution_id is not None:
        execution = db.get(
            models.AgentPublicActionExecution,
            evidence.public_action_execution_id,
        )
        if execution is None:
            raise SocialEventRuntimeError("execution_evidence_invalid")
        execution.social_event_id = event.id
    db.flush()
    return EventApplyResult(event, state, change, False)
