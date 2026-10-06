"""Audit-only manual reaction transitions in the caller's source transaction."""
from datetime import UTC, datetime
from hashlib import sha256
import json
from sqlalchemy.orm import Session
from app.core.ids import uuid7_string
from app.domains.relationships import models
from app.domains.relationships.contracts.source_posts import SourceEventPost


def record_source_reaction_event(db: Session, *, world_id: str, actor_world_character_id: str,
        target_world_character_id: str, post: SourceEventPost, root_post: SourceEventPost,
        event_type: str, transition_key: str):
    if event_type not in {"like_added", "like_removed"}:
        raise ValueError("source_reaction_type_invalid")
    now = datetime.now(UTC)
    event = models.SocialEvent(id=uuid7_string(), world_id=world_id,
        actor_world_character_id=actor_world_character_id, target_world_character_id=target_world_character_id,
        event_type=event_type, result="succeeded", occurred_at=now,
        idempotency_key=sha256(f"manual-reaction-v1|{world_id}|{actor_world_character_id}|{transition_key}".encode()).hexdigest(),
        schema_version="social-event-v1", retrieval_status="audit_only")
    db.add(event)
    db.flush()
    db.add(models.SocialEventEvidence(id=uuid7_string(), social_event_id=event.id,
        evidence_kind="like", source_object_type="post", source_object_id=post.id,
        root_post_id=root_post.id, source_post_id=post.id, target_post_id=post.id,
        content_sha256=sha256(json.dumps({"title":post.title,"body":post.body},ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest(),
        source_visibility_at_event=post.visibility, source_author_id_at_event=target_world_character_id, occurred_at=now))
    db.flush()
