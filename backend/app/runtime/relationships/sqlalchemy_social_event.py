"""Runtime SQLAlchemy adapter for canonical social-event and relationship writes."""

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
from app.domains.relationships.models.social import (
    SOCIAL_EVENT_TYPES,
)
from app.domains.relationships.exceptions import (
    SocialEventRuntimeError,
)
from app.domains.relationships.constants import (
    SOCIAL_EVENT_SCHEMA_VERSION,
    GRAPH_PAYLOAD_VERSION,
    SOURCE_EXCLUSION_PAYLOAD_VERSION,
    _RELATION_EVENT_TYPES,
)
from app.domains.relationships.contracts.events import (
    EvidenceInput,
    EventApplyResult,
    _Delta,
)
from app.domains.relationships.policies.events import (
    _aware_utc,
    _world_zone,
    _local_day_bounds,
    _snapshot,
    _clamp,
    _purpose_delta,
    _delta,
)
from app.domains.relationships.service.state import (
    _relationship_state,
    _delta_is_capped,
)
from app.domains.relationships.service.projection_events import (
    _enqueue_outbox,
    _enqueue_source_exclusion_outbox,
)
from app.domains.relationships.service.events import (
    exclude_events_for_posts,
)


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


def world_character_pair_is_blocked(
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
        if world_character_pair_is_blocked(
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
