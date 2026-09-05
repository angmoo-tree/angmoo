"""Deterministic observed-source receipt, relationship delta and outbox writes.

The caller owns the transaction. This service preserves the observation direction
without creating another successful source event or inferring an emotional delta.
"""
from __future__ import annotations
import json
from hashlib import sha256
from sqlalchemy.orm import Session
from app.core.ids import uuid7_string
from app.domains.relationships import models
from app.domains.relationships.constants import OBSERVATION_RELATIONSHIP_PAYLOAD_VERSION as OBSERVATION_GRAPH_PAYLOAD_VERSION
from app.domains.relationships.contracts.observations import ObservationPost, ObservationReferences
from app.domains.relationships.policies.events import _aware_utc, _snapshot as _relationship_snapshot, _clamp as _clamp_relationship
from app.domains.relationships.repository import observations as queries, events as event_queries, state as state_queries
from app.domains.social.contracts.observations import SocialObservationCommand, SocialObservationError, SocialObservationResult


def observe(
    db: Session, command: SocialObservationCommand, *, references: ObservationReferences
) -> SocialObservationResult:
    observer = references.world_character(
        world_id=command.world_id,
        world_character_id=command.observer_world_character_id,
        lock=True,
    )
    source_event = (
        queries.get_event(db, command.source_social_event_id)
        if command.source_social_event_id is not None
        else None
    )
    if source_event is None and command.source_post_id is None:
        raise SocialObservationError("source_reference_missing")
    if source_event is None:
        assert command.source_post_id is not None
        source_event = _observation_source_event_for_post(
            db,
            references=references,
            world_id=command.world_id,
            source_post_id=command.source_post_id,
        )
    if (
        source_event.world_id != command.world_id
        or source_event.result != "succeeded"
        or source_event.retrieval_status == "excluded"
    ):
        raise SocialObservationError("source_social_event_ineligible")
    if source_event.actor_world_character_id == observer.id:
        raise SocialObservationError("self_observation_forbidden")

    source_post = (
        _observation_source_post_for_event(
            db,
            references=references,
            world_id=command.world_id,
            source_event=source_event,
        )
        if command.source_post_id is None
        else references.get_post(command.source_post_id)
    )
    _validate_observation_source_post(source_post, world_id=command.world_id)
    assert source_post is not None
    evidence_matches = queries.find_matching_evidence(db, source_event=source_event, source_post=source_post)
    if evidence_matches is None:
        raise SocialObservationError("source_evidence_mismatch")

    target = references.world_character(
        world_id=command.world_id,
        world_character_id=source_event.actor_world_character_id,
    )
    if references.pair_blocked(
        world_id=command.world_id,
        actor_id=observer.id,
        target_id=target.id,
    ):
        raise SocialObservationError("world_character_blocked")
    state = _observation_relationship_state(
        db,
        world_id=command.world_id,
        actor_world_character_id=observer.id,
        target_world_character_id=target.id,
    )
    existing = event_queries.find_replay_change(db, state=state, existing=source_event)
    if existing is not None:
        _enqueue_observation_outbox(
            db,
            source_event=source_event,
            relationship_state=state,
        )
        db.flush()
        return _observation_result(
            command,
            source_event=source_event,
            state=state,
            receipt=existing,
            replayed=True,
        )

    before = _relationship_snapshot(state)
    state.familiarity = _clamp_relationship(state.familiarity + 1, 0, 100)
    state.interaction_count += 1
    state.last_event_id = source_event.id
    state.last_event_at = _aware_utc(command.observed_at)
    state.version += 1
    receipt = models.RelationshipStateChange(
        id=uuid7_string(),
        relationship_state_id=state.id,
        social_event_id=source_event.id,
        world_id=command.world_id,
        actor_world_character_id=observer.id,
        target_world_character_id=target.id,
        valence="neutral",
        intensity="low",
        delta_familiarity=1,
        delta_affinity=0,
        delta_trust=0,
        delta_tension=0,
        before_snapshot=before,
        after_snapshot=_relationship_snapshot(state),
        applied=True,
        not_applied_reason=None,
    )
    db.add(receipt)
    _enqueue_observation_outbox(
        db,
        source_event=source_event,
        relationship_state=state,
    )
    db.flush()
    return _observation_result(
        command,
        source_event=source_event,
        state=state,
        receipt=receipt,
        replayed=False,
    )


def _validate_observation_source_post(
    post: ObservationPost | None, *, world_id: str
) -> None:
    if post is None or post.world_id != world_id:
        raise SocialObservationError("evidence_post_world_mismatch")
    if post.deleted_at is not None:
        raise SocialObservationError("evidence_source_deleted")
    if post.report_hidden_at is not None or post.visibility != "public":
        raise SocialObservationError("evidence_source_hidden")


def _observation_source_event_for_post(
    db: Session,
    *,
    references: ObservationReferences,
    world_id: str,
    source_post_id: str,
) -> models.SocialEvent:
    post = references.get_post(source_post_id)
    _validate_observation_source_post(post, world_id=world_id)
    assert post is not None
    if post.author_world_character_id is None:
        raise SocialObservationError("source_world_character_missing")
    event = queries.find_source_event_for_post(db, world_id=world_id, post=post)
    if event is None:
        raise SocialObservationError("source_social_event_missing")
    return event


def _observation_source_post_for_event(
    db: Session,
    *,
    references: ObservationReferences,
    world_id: str,
    source_event: models.SocialEvent,
) -> ObservationPost:
    evidence = queries.find_first_evidence(db, source_event=source_event)
    if evidence is None:
        raise SocialObservationError("source_evidence_missing")
    candidates = (
        evidence.source_post_id,
        evidence.target_post_id,
        evidence.root_post_id,
        evidence.source_object_id if evidence.source_object_type == "post" else None,
    )
    for post_id in candidates:
        if post_id is None:
            continue
        post = references.get_post(post_id)
        try:
            _validate_observation_source_post(post, world_id=world_id)
        except SocialObservationError:
            continue
        assert post is not None
        return post
    raise SocialObservationError("source_post_missing")


def _observation_relationship_state(
    db: Session,
    *,
    world_id: str,
    actor_world_character_id: str,
    target_world_character_id: str,
) -> models.RelationshipState:
    state = state_queries.find_direction_for_update(db, world_id=world_id, actor_world_character_id=actor_world_character_id, target_world_character_id=target_world_character_id)
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


def _enqueue_observation_outbox(
    db: Session,
    *,
    source_event: models.SocialEvent,
    relationship_state: models.RelationshipState,
) -> models.GraphProjectionOutbox:
    """Project observer direction while preserving source-event direction."""

    payload: dict[str, object] = {
        "world_id": source_event.world_id,
        "source_event_id": source_event.id,
        "actor_world_character_id": relationship_state.actor_world_character_id,
        "target_world_character_id": relationship_state.target_world_character_id,
        "relationship_state_id": relationship_state.id,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    signature = sha256(canonical.encode("utf-8")).hexdigest()
    dedupe_key = sha256(
        (
            f"relationship_state|{source_event.id}|"
            f"{OBSERVATION_GRAPH_PAYLOAD_VERSION}|{relationship_state.id}"
        ).encode("utf-8")
    ).hexdigest()
    existing = event_queries.find_outbox_by_dedupe(db, dedupe_key=dedupe_key)
    if existing is not None:
        return existing
    row = models.GraphProjectionOutbox(
        id=uuid7_string(),
        world_id=source_event.world_id,
        source_event_id=source_event.id,
        projection_type="relationship_state",
        payload_version=OBSERVATION_GRAPH_PAYLOAD_VERSION,
        payload=payload,
        source_signature=signature,
        dedupe_key=dedupe_key,
        status="pending",
        attempt_count=0,
    )
    db.add(row)
    return row


def _observation_result(
    command: SocialObservationCommand,
    *,
    source_event: models.SocialEvent,
    state: models.RelationshipState,
    receipt: models.RelationshipStateChange,
    replayed: bool,
) -> SocialObservationResult:
    return SocialObservationResult(
        source_social_event_id=source_event.id,
        receipt_id=receipt.id,
        relationship_state_id=state.id,
        replayed=replayed,
        lane=command.lane,
    )
