"""Runtime persistence adapter for declared SNS action subjective context."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
import json

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domains.relationships.infrastructure.sqlalchemy_social_models import (
    SocialEvent,
    SocialEventEvidence,
)
from app.domains.social.infrastructure.sqlalchemy_subjective_context_models import (
    SocialActionSubjectiveContext,
)
from app.domains.worlds.infrastructure.sqlalchemy_models import World
from app.runtime.social.sqlalchemy_read_repository import (
    social_persistence_models as models,
)
from app.core.ids import uuid7_string
from app.domains.social.domain.subjective_context import ActionSubjectiveContextV1


class SubjectiveContextPersistenceError(ValueError):
    """Stable fail-closed persistence error."""


def subjective_context_digest(
    *,
    execution: models.AgentPublicActionExecution,
    event: SocialEvent,
    source_content_digest: str | None,
    context: ActionSubjectiveContextV1,
) -> str:
    payload = {
        "version": context.version,
        "execution_signature": execution.signature,
        "social_event_id": event.id,
        "source_content_digest": source_content_digest,
        "motivation_kind": context.motivation_kind.value,
        "motivation_text": context.normalized_motivation_text,
        "emotion_label": context.emotion_label.value,
        "emotion_text": context.normalized_emotion_text,
        "emotion_intensity": context.emotion_intensity,
        "provenance_kind": context.provenance_kind.value,
    }
    return sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def record_declared_subjective_context(
    db: Session,
    *,
    execution: models.AgentPublicActionExecution,
    event: SocialEvent,
    source_post_id: str | None,
    context: ActionSubjectiveContextV1 | None,
    captured_at: datetime,
) -> SocialActionSubjectiveContext | None:
    """Attach one validated declaration to one already-successful action.

    Callers own the surrounding action transaction. This function flushes but
    never commits, so a failed action cannot leave an active subjective row.
    """

    if context is None:
        return None
    captured = (
        captured_at.replace(tzinfo=UTC)
        if captured_at.tzinfo is None
        else captured_at.astimezone(UTC)
    )
    if execution.status != "succeeded":
        raise SubjectiveContextPersistenceError(
            "subjective_context_execution_not_succeeded"
        )
    if (
        execution.social_event_id != event.id
        or execution.world_id != event.world_id
        or execution.actor_world_character_id != event.actor_world_character_id
        or event.result != "succeeded"
        or event.invalidated_at is not None
    ):
        raise SubjectiveContextPersistenceError(
            "subjective_context_execution_event_mismatch"
        )
    world = db.get(World, event.world_id)
    actor = db.get(models.WorldCharacter, event.actor_world_character_id)
    if (
        world is None
        or actor is None
        or actor.world_id != world.id
        or actor.status != "active"
    ):
        raise SubjectiveContextPersistenceError("subjective_context_scope_invalid")
    evidence = db.scalar(
        select(SocialEventEvidence)
        .where(
            SocialEventEvidence.social_event_id == event.id,
            SocialEventEvidence.public_action_execution_id == execution.id,
        )
        .order_by(SocialEventEvidence.id)
        .limit(1)
    )
    if evidence is None:
        raise SubjectiveContextPersistenceError(
            "subjective_context_event_evidence_missing"
        )
    evidence_post_id = evidence.source_post_id
    if source_post_id is not None and source_post_id not in {
        evidence.source_post_id,
        evidence.target_post_id,
        evidence.root_post_id,
    }:
        raise SubjectiveContextPersistenceError(
            "subjective_context_source_post_mismatch"
        )
    canonical_post_id = source_post_id or evidence_post_id
    if canonical_post_id is not None:
        post = db.get(models.Post, canonical_post_id)
        if (
            post is None
            or post.world_id != world.id
            or post.deleted_at is not None
            or post.report_hidden_at is not None
        ):
            raise SubjectiveContextPersistenceError(
                "subjective_context_source_post_invalid"
            )

    digest = subjective_context_digest(
        execution=execution,
        event=event,
        source_content_digest=evidence.content_sha256,
        context=context,
    )
    existing = db.scalar(
        select(SocialActionSubjectiveContext).where(
            SocialActionSubjectiveContext.public_action_execution_id
            == execution.id
        )
    )
    if existing is not None:
        if existing.source_digest != digest:
            raise SubjectiveContextPersistenceError(
                "subjective_context_idempotency_conflict"
            )
        return existing
    row = SocialActionSubjectiveContext(
        id=uuid7_string(),
        owner_id=world.owner_user_id,
        world_id=world.id,
        actor_world_character_id=actor.id,
        social_event_id=event.id,
        public_action_execution_id=execution.id,
        source_post_id=canonical_post_id,
        schema_version=context.version,
        motivation_kind=context.motivation_kind.value,
        motivation_text=context.normalized_motivation_text,
        emotion_label=context.emotion_label.value,
        emotion_text=context.normalized_emotion_text,
        emotion_intensity=context.emotion_intensity,
        provenance_kind=context.provenance_kind.value,
        source_digest=digest,
        captured_at=captured,
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError as exc:
        raise SubjectiveContextPersistenceError(
            "subjective_context_uniqueness_conflict"
        ) from exc
    return row


__all__ = [
    "SubjectiveContextPersistenceError",
    "record_declared_subjective_context",
    "subjective_context_digest",
]
