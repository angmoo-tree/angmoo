"""Persist self-expression only inside a successful action transaction."""

from datetime import datetime
from hashlib import sha256
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.contracts.activity_thought import ActivityThought
from app.core.ids import uuid7_string
from app.domains.social.contracts.subjective_persistence import SubjectiveExecution, SubjectiveEvent, SubjectiveReferences
from app.domains.social.exceptions import SubjectiveContextPersistenceError
from app.domains.social.models.activity_thought import SocialActivityThought
from app.domains.social.repository.subjective_context import get_source_post


def record_activity_thought(db: Session, *, execution: SubjectiveExecution,
                            event: SubjectiveEvent, source_post_id: str | None,
                            thought: ActivityThought, captured_at: datetime,
                            references: SubjectiveReferences) -> SocialActivityThought:
    if (execution.status != "succeeded" or execution.social_event_id != event.id
        or execution.world_id != event.world_id or execution.actor_world_character_id != event.actor_world_character_id
        or event.result != "succeeded" or event.invalidated_at is not None):
        raise SubjectiveContextPersistenceError("activity_thought_execution_invalid")
    world = references.get_world(event.world_id)
    actor = references.get_actor(event.actor_world_character_id)
    evidence = references.get_evidence(event_id=event.id, execution_id=execution.id)
    if world is None or actor is None or actor.world_id != world.id or actor.status != "active" or evidence is None:
        raise SubjectiveContextPersistenceError("activity_thought_scope_invalid")
    if source_post_id is not None:
        post = get_source_post(db, source_post_id)
        if (post is None or post.world_id != world.id or post.author_world_character_id != actor.id
            or post.deleted_at is not None or post.report_hidden_at is not None or evidence.source_post_id != post.id):
            raise SubjectiveContextPersistenceError("activity_thought_source_invalid")
    digest = post_thought_digest(post) if source_post_id is not None else sha256(
        f"{execution.signature}:{event.id}".encode()).hexdigest()
    if not digest or len(digest) != 64:
        raise SubjectiveContextPersistenceError("activity_thought_source_digest_invalid")
    existing = db.scalar(select(SocialActivityThought).where(SocialActivityThought.public_action_execution_id == execution.id))
    if existing is not None:
        if (existing.social_event_id != event.id or existing.source_post_id != source_post_id
            or existing.source_digest != digest or existing.thought_text != thought.text
            or existing.status != thought.status or existing.truncated != thought.truncated):
            raise SubjectiveContextPersistenceError("activity_thought_replay_conflict")
        return existing
    row = SocialActivityThought(
        id=uuid7_string(), owner_id=world.owner_user_id, world_id=world.id,
        actor_world_character_id=actor.id, social_event_id=event.id,
        public_action_execution_id=execution.id, source_post_id=source_post_id,
        source_kind="post_revision" if source_post_id is not None else "action_event",
        source_digest=digest, thought_text=thought.text, status=thought.status,
        truncated=thought.truncated, created_at=captured_at,
    )
    db.add(row)
    db.flush()
    return row


def post_thought_digest(post) -> str:
    """Own final source revision, independent of event producer text formatting."""
    return sha256(json.dumps({"title": post.title, "body": post.body},
                             ensure_ascii=False, sort_keys=True,
                             separators=(",", ":")).encode()).hexdigest()
