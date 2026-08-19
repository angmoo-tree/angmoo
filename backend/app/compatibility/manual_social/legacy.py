from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
import json

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models
from app.core import unit_of_work
from app.core.ids import uuid7_string
from app.domains.manual_social.api.schemas import (
    ManualSocialDeliveryRead,
    ManualSocialFeedRead,
    ManualSocialPostRead,
    ManualSocialWriteRead,
    OwnerManualPostWrite,
    OwnerManualReplyWrite,
)
from app.domains.manual_social.infrastructure.sqlalchemy_models import (
    OwnerManualInboxCandidate,
    OwnerManualSocialWrite,
)
from app.domains.world_characters.public import (
    SqlAlchemyOwnerControlledIdentityRepository,
)
from app.schemas.community import PostCreate, TimelineReplyCreate
from app.services import community as community_service


class ManualSocialError(Exception):
    reason_code = "manual_social_error"

    def __init__(self, reason_code: str | None = None) -> None:
        if reason_code:
            self.reason_code = reason_code
        super().__init__(self.reason_code)


class ManualSocialNotFoundError(ManualSocialError):
    reason_code = "manual_social_not_found"


class ManualSocialForbiddenError(ManualSocialError):
    reason_code = "manual_social_forbidden"


class ManualSocialConflictError(ManualSocialError):
    reason_code = "manual_social_conflict"


def _owner_actor(
    db: Session, *, world_id: str, current_user_id: str
) -> tuple[models.WorldCharacter, models.Character]:
    snapshot = SqlAlchemyOwnerControlledIdentityRepository(db).get(
        world_id=world_id,
        current_user_id=current_user_id,
    )
    world_character = db.get(models.WorldCharacter, snapshot.world_character_id)
    character = db.get(models.Character, snapshot.character_id)
    if (
        world_character is None
        or character is None
        or character.deleted_at is not None
        or character.owner_id != current_user_id
        or world_character.world_id != world_id
        or world_character.owner_user_id != current_user_id
        or world_character.control_mode != "owner_controlled"
        or world_character.status != "active"
        or world_character.autonomous_enabled
    ):
        raise ManualSocialForbiddenError("owner_actor_invalid")
    membership = db.get(models.WorldMembership, world_character.membership_id)
    if (
        membership is None
        or membership.world_id != world_id
        or membership.user_id != current_user_id
        or membership.status != "active"
    ):
        raise ManualSocialForbiddenError("owner_membership_inactive")
    return world_character, character


def _request_hash(*, operation: str, payload: dict[str, object]) -> str:
    encoded = json.dumps(
        {"operation": operation, **payload},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _post_read(db: Session, post: models.Post) -> ManualSocialPostRead:
    if post.world_id is None or post.author_world_character_id is None:
        raise ManualSocialConflictError("world_post_scope_missing")
    author = db.get(models.WorldCharacter, post.author_world_character_id)
    return ManualSocialPostRead(
        id=post.id,
        world_id=post.world_id,
        author_world_character_id=post.author_world_character_id,
        author_name=post.author_name,
        title=post.title,
        body=post.body,
        post_type=post.post_type,
        reply_to_post_id=post.reply_to_post_id,
        created_at=post.created_at,
        can_owner_reply=(
            post.reply_to_post_id is None
            and author is not None
            and author.status == "active"
            and author.control_mode == "autonomous"
            and author.activity_runtime_mode == "routine_resident_v1"
        ),
    )


def _existing_write(
    db: Session,
    *,
    world_id: str,
    current_user_id: str,
    idempotency_key: str,
    request_sha256: str,
) -> tuple[OwnerManualSocialWrite, models.Post] | None:
    row = db.scalar(
        select(OwnerManualSocialWrite).where(
            OwnerManualSocialWrite.world_id == world_id,
            OwnerManualSocialWrite.owner_user_id == current_user_id,
            OwnerManualSocialWrite.idempotency_key == idempotency_key,
        )
    )
    if row is None:
        return None
    if row.request_sha256 != request_sha256:
        raise ManualSocialConflictError("idempotency_payload_mismatch")
    post = db.get(models.Post, row.result_post_id)
    if post is None or post.world_id != world_id:
        raise ManualSocialConflictError("idempotency_result_missing")
    return row, post


def _blocked(
    db: Session, *, world_id: str, actor_id: str, target_id: str
) -> bool:
    return (
        db.scalar(
            select(models.WorldCharacterBlock.id)
            .where(
                models.WorldCharacterBlock.world_id == world_id,
                or_(
                    (
                        models.WorldCharacterBlock.blocker_world_character_id
                        == actor_id
                    )
                    & (
                        models.WorldCharacterBlock.blocked_world_character_id
                        == target_id
                    ),
                    (
                        models.WorldCharacterBlock.blocker_world_character_id
                        == target_id
                    )
                    & (
                        models.WorldCharacterBlock.blocked_world_character_id
                        == actor_id
                    ),
                ),
            )
            .limit(1)
        )
        is not None
    )


def _reply_target(
    db: Session,
    *,
    world_id: str,
    actor_world_character_id: str,
    target_post_id: str,
) -> tuple[models.Post, models.WorldCharacter]:
    post = db.get(models.Post, target_post_id)
    if (
        post is None
        or post.world_id != world_id
        or post.reply_to_post_id is not None
        or post.deleted_at is not None
        or post.report_hidden_at is not None
        or post.visibility != "public"
        or post.author_world_character_id is None
    ):
        raise ManualSocialNotFoundError("reply_target_unavailable")
    target = db.get(models.WorldCharacter, post.author_world_character_id)
    if (
        target is None
        or target.id == actor_world_character_id
        or target.world_id != world_id
        or target.status != "active"
        or target.control_mode != "autonomous"
        or target.activity_runtime_mode != "routine_resident_v1"
    ):
        raise ManualSocialForbiddenError("reply_target_not_autonomous")
    membership = db.get(models.WorldMembership, target.membership_id)
    if (
        membership is None
        or membership.world_id != world_id
        or membership.status != "active"
        or _blocked(
            db,
            world_id=world_id,
            actor_id=actor_world_character_id,
            target_id=target.id,
        )
    ):
        raise ManualSocialForbiddenError("reply_target_blocked")
    return post, target


def list_owner_world_feed(
    db: Session, *, world_id: str, current_user_id: str, limit: int = 100
) -> ManualSocialFeedRead:
    actor, _character = _owner_actor(
        db, world_id=world_id, current_user_id=current_user_id
    )
    items = list(
        db.scalars(
            select(models.Post)
            .where(
                models.Post.world_id == world_id,
                models.Post.visibility == "public",
                models.Post.deleted_at.is_(None),
                models.Post.report_hidden_at.is_(None),
            )
            .order_by(models.Post.created_at.desc(), models.Post.id.desc())
            .limit(max(1, min(limit, 200)))
        )
    )
    return ManualSocialFeedRead(
        world_id=world_id,
        owner_world_character_id=actor.id,
        items=[_post_read(db, post) for post in items],
    )


def create_owner_post(
    db: Session,
    *,
    world_id: str,
    current_user: models.User,
    idempotency_key: str,
    data: OwnerManualPostWrite,
) -> ManualSocialWriteRead:
    actor, character = _owner_actor(
        db, world_id=world_id, current_user_id=current_user.id
    )
    request_sha = _request_hash(
        operation="post", payload={"title": data.title, "body": data.body}
    )
    existing = _existing_write(
        db,
        world_id=world_id,
        current_user_id=current_user.id,
        idempotency_key=idempotency_key,
        request_sha256=request_sha,
    )
    if existing is not None:
        _ledger, post = existing
        return ManualSocialWriteRead(
            operation="post",
            replayed=True,
            post=_post_read(db, post),
            delivery=ManualSocialDeliveryRead(inbox_status="not_applicable"),
        )
    try:
        with unit_of_work.deferred_commits():
            post_read = community_service.create_post(
                db,
                current_user,
                PostCreate(
                    title=data.title,
                    body=data.body,
                    author_character_id=character.id,
                ),
                log_manual_activity=True,
                world_id=world_id,
                author_world_character_id=actor.id,
            )
            post = db.get(models.Post, post_read.id)
            if post is None:
                raise ManualSocialConflictError("manual_post_missing")
            db.add(
                OwnerManualSocialWrite(
                    id=uuid7_string(),
                    world_id=world_id,
                    owner_user_id=current_user.id,
                    actor_world_character_id=actor.id,
                    operation="post",
                    idempotency_key=idempotency_key,
                    request_sha256=request_sha,
                    target_post_id=None,
                    result_post_id=post.id,
                )
            )
            db.flush()
        db.commit()
    except IntegrityError:
        db.rollback()
        replay = _existing_write(
            db,
            world_id=world_id,
            current_user_id=current_user.id,
            idempotency_key=idempotency_key,
            request_sha256=request_sha,
        )
        if replay is None:
            raise
        _ledger, post = replay
        return ManualSocialWriteRead(
            operation="post",
            replayed=True,
            post=_post_read(db, post),
            delivery=ManualSocialDeliveryRead(inbox_status="not_applicable"),
        )
    db.refresh(post)
    return ManualSocialWriteRead(
        operation="post",
        replayed=False,
        post=_post_read(db, post),
        delivery=ManualSocialDeliveryRead(inbox_status="not_applicable"),
    )


def create_owner_reply(
    db: Session,
    *,
    world_id: str,
    target_post_id: str,
    current_user: models.User,
    idempotency_key: str,
    data: OwnerManualReplyWrite,
) -> ManualSocialWriteRead:
    actor, character = _owner_actor(
        db, world_id=world_id, current_user_id=current_user.id
    )
    parent, target = _reply_target(
        db,
        world_id=world_id,
        actor_world_character_id=actor.id,
        target_post_id=target_post_id,
    )
    request_sha = _request_hash(
        operation="reply", payload={"target_post_id": parent.id, "body": data.body}
    )
    existing = _existing_write(
        db,
        world_id=world_id,
        current_user_id=current_user.id,
        idempotency_key=idempotency_key,
        request_sha256=request_sha,
    )
    if existing is not None:
        _ledger, reply = existing
        candidate = db.scalar(
            select(OwnerManualInboxCandidate).where(
                OwnerManualInboxCandidate.source_reply_post_id == reply.id,
                OwnerManualInboxCandidate.target_world_character_id == target.id,
            )
        )
        return ManualSocialWriteRead(
            operation="reply",
            replayed=True,
            post=_post_read(db, reply),
            delivery=ManualSocialDeliveryRead(
                inbox_candidate_id=candidate.id if candidate is not None else None,
                inbox_status="pending",
            ),
        )
    candidate_id = uuid7_string()
    try:
        with unit_of_work.deferred_commits():
            reply_read = community_service.create_reply(
                db,
                current_user,
                parent.id,
                TimelineReplyCreate(
                    body=data.body,
                    author_character_id=character.id,
                ),
                activity_reason="owner_manual_reply",
            )
            reply = db.get(models.Post, reply_read.id)
            if reply is None:
                raise ManualSocialConflictError("manual_reply_missing")
            db.add(
                OwnerManualSocialWrite(
                    id=uuid7_string(),
                    world_id=world_id,
                    owner_user_id=current_user.id,
                    actor_world_character_id=actor.id,
                    operation="reply",
                    idempotency_key=idempotency_key,
                    request_sha256=request_sha,
                    target_post_id=parent.id,
                    result_post_id=reply.id,
                )
            )
            db.add(
                OwnerManualInboxCandidate(
                    id=candidate_id,
                    world_id=world_id,
                    actor_world_character_id=actor.id,
                    target_world_character_id=target.id,
                    source_reply_post_id=reply.id,
                    target_post_id=parent.id,
                    status="pending",
                    version=1,
                )
            )
            db.flush()
        db.commit()
    except IntegrityError:
        db.rollback()
        replay = _existing_write(
            db,
            world_id=world_id,
            current_user_id=current_user.id,
            idempotency_key=idempotency_key,
            request_sha256=request_sha,
        )
        if replay is None:
            raise
        _ledger, reply = replay
        candidate = db.scalar(
            select(OwnerManualInboxCandidate).where(
                OwnerManualInboxCandidate.source_reply_post_id == reply.id,
                OwnerManualInboxCandidate.target_world_character_id == target.id,
            )
        )
        candidate_id = candidate.id if candidate is not None else candidate_id
        return ManualSocialWriteRead(
            operation="reply",
            replayed=True,
            post=_post_read(db, reply),
            delivery=ManualSocialDeliveryRead(
                inbox_candidate_id=candidate_id,
                inbox_status="pending",
            ),
        )
    db.refresh(reply)
    return ManualSocialWriteRead(
        operation="reply",
        replayed=False,
        post=_post_read(db, reply),
        delivery=ManualSocialDeliveryRead(
            inbox_candidate_id=candidate_id,
            inbox_status="pending",
        ),
    )


__all__ = [
    "ManualSocialConflictError",
    "ManualSocialError",
    "ManualSocialForbiddenError",
    "ManualSocialNotFoundError",
    "create_owner_post",
    "create_owner_reply",
    "list_owner_world_feed",
]
