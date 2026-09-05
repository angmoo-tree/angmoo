"""Canonical event eligibility and source invalidation in the caller transaction."""
from hashlib import sha256
from app.core.ids import uuid7_string
from app.domains.relationships import models
from app.domains.relationships.constants import SOCIAL_EVENT_TYPES, SOCIAL_EVENT_SCHEMA_VERSION, _RELATION_EVENT_TYPES
from app.domains.relationships.contracts.events import EvidenceInput, EventApplyResult, EventReferences
from app.domains.relationships.exceptions import SocialEventRuntimeError
from app.domains.relationships.service.evidence import _validate_evidence_source
from app.domains.relationships.policies.events import _snapshot, _clamp, _delta
from app.domains.relationships.service.state import _relationship_state, _delta_is_capped
from app.domains.relationships.service.projection_events import _enqueue_outbox
from datetime import datetime
from typing import Literal
from sqlalchemy.orm import Session
from app.domains.relationships.repository import events as event_repository
from app.domains.relationships.policies.events import _aware_utc
from app.domains.relationships.service.projection_events import _enqueue_source_exclusion_outbox


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
    event_ids = event_repository.source_event_ids(db, unique_post_ids=unique_post_ids)
    changed = 0
    for event_id in event_ids:
        event = event_repository.find_event_for_update(db, event_id=event_id)
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
    references: EventReferences,
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
    world = references.get_world(world_id)
    if world is None:
        raise SocialEventRuntimeError("world_not_found")
    references.validate_world_character(
        world_id=world_id,
        world_character_id=actor_world_character_id,
        lock=True,
    )
    if target_world_character_id is not None:
        if target_world_character_id == actor_world_character_id:
            raise SocialEventRuntimeError("self_target_forbidden")
        references.validate_world_character(
            world_id=world_id,
            world_character_id=target_world_character_id,
        )
        if references.world_character_pair_is_blocked(
            world_id=world_id,
            first_world_character_id=actor_world_character_id,
            second_world_character_id=target_world_character_id,
        ):
            raise SocialEventRuntimeError("world_character_blocked")
    elif event_type not in {"post_published", "joint_started"}:
        raise SocialEventRuntimeError("event_target_required")
    existing = event_repository.find_event_by_idempotency(db, idempotency_key=idempotency_key)
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
            state = event_repository.find_replay_state(db, existing=existing)
            if state is not None:
                change = event_repository.find_replay_change(db, state=state, existing=existing)
        return EventApplyResult(existing, state, change, True)

    _validate_evidence_source(references, world_id=world_id, evidence=evidence)
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
        execution = references.get_execution(evidence.public_action_execution_id)
        if execution is None:
            raise SocialEventRuntimeError("execution_evidence_invalid")
        references.set_social_event_id(execution, social_event_id=event.id)
    db.flush()
    return EventApplyResult(event, state, change, False)
