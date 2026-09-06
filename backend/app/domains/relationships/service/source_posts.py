"""Audit-only successful source and evidence in the caller's write transaction.

Source success is recorded independently of an observer's later relationship
receipt. No relationship delta or projection is inferred by this write.
"""
from __future__ import annotations
import json
from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256
from sqlalchemy.orm import Session
from app.core.ids import uuid7_string
from app.domains.relationships import models
from app.domains.relationships.contracts.source_posts import SourceEventPost


def record_source_post_event(
    db: Session,
    *,
    world_id: str,
    actor_world_character_id: str,
    target_world_character_id: str | None,
    operation: str,
    post: SourceEventPost,
    root_post: SourceEventPost,
    request_key: str,
    failure_injector: Callable[[str], None] | None,
) -> None:
    occurred_at = datetime.now(UTC)
    event_id = uuid7_string()
    event_type = "post_published" if operation == "post" else "reply_created"
    event_key = sha256(
        f"social-source-v1|{world_id}|{actor_world_character_id}|{request_key}|{operation}".encode()
    ).hexdigest()
    db.add(
        models.SocialEvent(
            id=event_id,
            world_id=world_id,
            actor_world_character_id=actor_world_character_id,
            target_world_character_id=target_world_character_id,
            event_type=event_type,
            result="succeeded",
            occurred_at=occurred_at,
            idempotency_key=event_key,
            schema_version="social-event-v1",
            retrieval_status="audit_only",
        )
    )
    db.flush()
    if failure_injector is not None:
        failure_injector("after_source_event")
    content_digest = sha256(
        json.dumps(
            {"title": post.title, "body": post.body},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    db.add(
        models.SocialEventEvidence(
            id=uuid7_string(),
            social_event_id=event_id,
            evidence_kind="post" if operation == "post" else "reply_post",
            source_object_type="post",
            source_object_id=post.id,
            root_post_id=root_post.id,
            source_post_id=post.id,
            target_post_id=None if operation == "post" else root_post.id,
            content_sha256=content_digest,
            source_visibility_at_event=post.visibility,
            source_author_id_at_event=actor_world_character_id,
            occurred_at=occurred_at,
        )
    )
    db.flush()
    if failure_injector is not None:
        failure_injector("after_source_evidence")
