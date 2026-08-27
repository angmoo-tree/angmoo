"""Transitional SQLite adapter for the canonical social source-write UoW.

The social domain owns commands, application use cases, and the UoW port.  This
adapter remains in the compatibility layer while the canonical ``Post`` ORM and
community persistence service still live in pre-L4 modules.  API/runtime
composition may depend on this adapter; ``app.domains.social`` must not.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app import models
from app.core import unit_of_work
from app.core.ids import uuid7_string
from app.domains.manual_social.infrastructure.sqlalchemy_models import (
    OwnerManualInboxCandidate,
    OwnerManualSocialWrite,
)
from app.domains.social.domain.writes import (
    OwnerPostCommand,
    OwnerReplyCommand,
    SocialPostSnapshot,
    SocialWriteConflictError,
    SocialWriteDelivery,
    SocialWriteForbiddenError,
    SocialWriteNotFoundError,
    SocialWriteResult,
    SocialWriteRetryableError,
    ValidatedAutonomousWriteCommand,
)
from app.domains.world_characters.public import (
    SqlAlchemyOwnerControlledIdentityRepository,
)
from app.runtime.persistence.sqlite_concurrency import (
    SqliteBusyRetryExhausted,
    SqliteRetryPolicy,
    run_sqlite_session_immediate,
)
from app.schemas.community import PostCreate, TimelineReplyCreate
from app.services import community as community_service

FailureInjector = Callable[[str], None]


class SqlAlchemySocialWriteUnitOfWork:
    """Own one source write and all canonical consequences through COMMIT."""

    def __init__(
        self,
        session: Session,
        *,
        retry_policy: SqliteRetryPolicy | None = None,
        failure_injector: FailureInjector | None = None,
    ) -> None:
        self._session = session
        self._retry_policy = retry_policy
        self._failure_injector = failure_injector

    def create_owner_post(self, command: OwnerPostCommand) -> SocialWriteResult:
        return self._run(lambda: self._create_owner_post(command))

    def create_owner_reply(self, command: OwnerReplyCommand) -> SocialWriteResult:
        return self._run(lambda: self._create_owner_reply(command))

    def apply_validated_autonomous_result(
        self, command: ValidatedAutonomousWriteCommand
    ) -> SocialWriteResult:
        """Persist validated output; no provider/LLM call is permitted here."""

        return self._run(lambda: self._apply_validated_autonomous_result(command))

    def _run(self, operation: Callable[[], SocialWriteResult]) -> SocialWriteResult:
        try:
            return run_sqlite_session_immediate(
                self._session,
                operation,
                retry_policy=self._retry_policy,
            )
        except SqliteBusyRetryExhausted as exc:
            raise SocialWriteRetryableError() from exc

    def _create_owner_post(self, command: OwnerPostCommand) -> SocialWriteResult:
        db = self._session
        actor, character, user = _owner_actor(
            db,
            world_id=command.world_id,
            current_user_id=command.current_user_id,
        )
        request_sha = _request_hash(
            operation="post",
            payload={"title": command.title, "body": command.body},
        )
        existing = _existing_write(
            db,
            world_id=command.world_id,
            principal_user_id=command.current_user_id,
            idempotency_key=command.idempotency_key,
            request_sha256=request_sha,
        )
        if existing is not None:
            _ledger, post = existing
            return _result(db, post=post, operation="post", replayed=True)

        with unit_of_work.deferred_commits():
            created = community_service.create_post(
                db,
                user,
                PostCreate(
                    title=command.title,
                    body=command.body,
                    author_character_id=character.id,
                ),
                log_manual_activity=True,
                world_id=command.world_id,
                author_world_character_id=actor.id,
            )
            post = db.get(models.Post, created.id)
            if post is None:
                raise SocialWriteConflictError("manual_post_missing")
            self._fail("after_source_post")
            _record_source_event(
                db,
                world_id=command.world_id,
                actor_world_character_id=actor.id,
                target_world_character_id=None,
                operation="post",
                post=post,
                root_post=post,
                request_key=command.idempotency_key,
                failure_injector=self._failure_injector,
            )
            db.add(
                OwnerManualSocialWrite(
                    id=uuid7_string(),
                    world_id=command.world_id,
                    owner_user_id=command.current_user_id,
                    actor_world_character_id=actor.id,
                    operation="post",
                    idempotency_key=command.idempotency_key,
                    request_sha256=request_sha,
                    target_post_id=None,
                    result_post_id=post.id,
                )
            )
            db.flush()
            self._fail("before_commit")
        return _result(db, post=post, operation="post", replayed=False)

    def _create_owner_reply(self, command: OwnerReplyCommand) -> SocialWriteResult:
        db = self._session
        actor, character, user = _owner_actor(
            db,
            world_id=command.world_id,
            current_user_id=command.current_user_id,
        )
        parent, target = _owner_reply_target(
            db,
            world_id=command.world_id,
            actor_world_character_id=actor.id,
            target_post_id=command.target_post_id,
        )
        request_sha = _request_hash(
            operation="reply",
            payload={"target_post_id": parent.id, "body": command.body},
        )
        existing = _existing_write(
            db,
            world_id=command.world_id,
            principal_user_id=command.current_user_id,
            idempotency_key=command.idempotency_key,
            request_sha256=request_sha,
        )
        if existing is not None:
            _ledger, reply = existing
            candidate = _candidate(db, reply_id=reply.id, target_id=target.id)
            return _result(
                db,
                post=reply,
                operation="reply",
                replayed=True,
                candidate_id=candidate.id if candidate is not None else None,
            )

        candidate_id = uuid7_string()
        with unit_of_work.deferred_commits():
            created = community_service.create_reply(
                db,
                user,
                parent.id,
                TimelineReplyCreate(
                    body=command.body, author_character_id=character.id
                ),
                activity_reason="owner_manual_reply",
            )
            reply = db.get(models.Post, created.id)
            if reply is None:
                raise SocialWriteConflictError("manual_reply_missing")
            self._fail("after_source_post")
            _record_source_event(
                db,
                world_id=command.world_id,
                actor_world_character_id=actor.id,
                target_world_character_id=target.id,
                operation="reply",
                post=reply,
                root_post=parent,
                request_key=command.idempotency_key,
                failure_injector=self._failure_injector,
            )
            db.add(
                OwnerManualSocialWrite(
                    id=uuid7_string(),
                    world_id=command.world_id,
                    owner_user_id=command.current_user_id,
                    actor_world_character_id=actor.id,
                    operation="reply",
                    idempotency_key=command.idempotency_key,
                    request_sha256=request_sha,
                    target_post_id=parent.id,
                    result_post_id=reply.id,
                )
            )
            db.add(
                OwnerManualInboxCandidate(
                    id=candidate_id,
                    world_id=command.world_id,
                    actor_world_character_id=actor.id,
                    target_world_character_id=target.id,
                    source_reply_post_id=reply.id,
                    target_post_id=parent.id,
                    status="pending",
                    version=1,
                )
            )
            db.flush()
            self._fail("after_inbox_candidate")
            self._fail("before_commit")
        return _result(
            db,
            post=reply,
            operation="reply",
            replayed=False,
            candidate_id=candidate_id,
        )

    def _apply_validated_autonomous_result(
        self, command: ValidatedAutonomousWriteCommand
    ) -> SocialWriteResult:
        db = self._session
        actor, character, user = _autonomous_actor(
            db,
            world_id=command.world_id,
            actor_world_character_id=command.actor_world_character_id,
        )
        target_post: models.Post | None = None
        target_actor: models.WorldCharacter | None = None
        if command.operation == "reply":
            if command.target_post_id is None:
                raise SocialWriteConflictError("autonomous_reply_target_required")
            target_post, target_actor = _autonomous_reply_target(
                db,
                world_id=command.world_id,
                actor_world_character_id=actor.id,
                target_post_id=command.target_post_id,
            )
        elif command.target_post_id is not None:
            raise SocialWriteConflictError("autonomous_post_target_forbidden")

        # The legacy ledger column still stores the owning user ID. Include the
        # WorldCharacter in the canonical key so two autonomous actors owned by
        # one user cannot collide when their planners reuse an operation key.
        request_key = f"autonomous:{actor.id}:{command.idempotency_key}"
        request_sha = _request_hash(
            operation=command.operation,
            payload={
                "actor_world_character_id": actor.id,
                "target_post_id": command.target_post_id,
                "title": command.title,
                "body": command.body,
            },
        )
        existing = _existing_write(
            db,
            world_id=command.world_id,
            principal_user_id=user.id,
            idempotency_key=request_key,
            request_sha256=request_sha,
        )
        if existing is not None:
            _ledger, post = existing
            return _result(db, post=post, operation=command.operation, replayed=True)

        with unit_of_work.deferred_commits():
            if command.operation == "post":
                created = community_service.create_post(
                    db,
                    user,
                    PostCreate(
                        title=command.title,
                        body=command.body,
                        author_character_id=character.id,
                    ),
                    log_manual_activity=False,
                    world_id=command.world_id,
                    author_world_character_id=actor.id,
                )
            else:
                assert target_post is not None
                created = community_service.create_reply(
                    db,
                    user,
                    target_post.id,
                    TimelineReplyCreate(
                        body=command.body, author_character_id=character.id
                    ),
                    activity_reason="autonomous_validated_reply",
                    enforce_user_quota=False,
                )
            post = db.get(models.Post, created.id)
            if post is None:
                raise SocialWriteConflictError("autonomous_result_post_missing")
            self._fail("after_source_post")
            _record_source_event(
                db,
                world_id=command.world_id,
                actor_world_character_id=actor.id,
                target_world_character_id=target_actor.id
                if target_actor is not None
                else None,
                operation=command.operation,
                post=post,
                root_post=target_post or post,
                request_key=request_key,
                failure_injector=self._failure_injector,
            )
            db.add(
                OwnerManualSocialWrite(
                    id=uuid7_string(),
                    world_id=command.world_id,
                    owner_user_id=user.id,
                    actor_world_character_id=actor.id,
                    operation=command.operation,
                    idempotency_key=request_key,
                    request_sha256=request_sha,
                    target_post_id=target_post.id if target_post is not None else None,
                    result_post_id=post.id,
                )
            )
            db.flush()
            self._fail("before_commit")
        return _result(db, post=post, operation=command.operation, replayed=False)

    def _fail(self, stage: str) -> None:
        if self._failure_injector is not None:
            self._failure_injector(stage)


def _owner_actor(
    db: Session, *, world_id: str, current_user_id: str
) -> tuple[models.WorldCharacter, models.Character, models.User]:
    snapshot = SqlAlchemyOwnerControlledIdentityRepository(db).get(
        world_id=world_id,
        current_user_id=current_user_id,
    )
    actor = db.get(models.WorldCharacter, snapshot.world_character_id)
    character = db.get(models.Character, snapshot.character_id)
    user = db.get(models.User, current_user_id)
    if (
        actor is None
        or character is None
        or user is None
        or character.deleted_at is not None
        or character.owner_id != current_user_id
        or actor.world_id != world_id
        or actor.owner_user_id != current_user_id
        or actor.control_mode != "owner_controlled"
        or actor.status != "active"
        or actor.autonomous_enabled
    ):
        raise SocialWriteForbiddenError("owner_actor_invalid")
    _require_membership(db, actor=actor, expected_user_id=current_user_id)
    return actor, character, user


def _autonomous_actor(
    db: Session, *, world_id: str, actor_world_character_id: str
) -> tuple[models.WorldCharacter, models.Character, models.User]:
    actor = db.get(models.WorldCharacter, actor_world_character_id)
    character = (
        db.get(models.Character, actor.character_id) if actor is not None else None
    )
    user = db.get(models.User, character.owner_id) if character is not None else None
    if (
        actor is None
        or character is None
        or user is None
        or actor.world_id != world_id
        or actor.status != "active"
        or actor.control_mode != "autonomous"
        or not actor.autonomous_enabled
        or actor.activity_runtime_mode != "routine_resident_v1"
        or character.deleted_at is not None
    ):
        raise SocialWriteForbiddenError("autonomous_actor_invalid")
    _require_membership(db, actor=actor, expected_user_id=character.owner_id)
    return actor, character, user


def _require_membership(
    db: Session, *, actor: models.WorldCharacter, expected_user_id: str
) -> None:
    membership = db.get(models.WorldMembership, actor.membership_id)
    if (
        membership is None
        or membership.world_id != actor.world_id
        or membership.user_id != expected_user_id
        or membership.status != "active"
    ):
        raise SocialWriteForbiddenError("world_membership_inactive")


def _request_hash(*, operation: str, payload: dict[str, object]) -> str:
    encoded = json.dumps(
        {"operation": operation, **payload},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _existing_write(
    db: Session,
    *,
    world_id: str,
    principal_user_id: str,
    idempotency_key: str,
    request_sha256: str,
) -> tuple[OwnerManualSocialWrite, models.Post] | None:
    row = db.scalar(
        select(OwnerManualSocialWrite).where(
            OwnerManualSocialWrite.world_id == world_id,
            OwnerManualSocialWrite.owner_user_id == principal_user_id,
            OwnerManualSocialWrite.idempotency_key == idempotency_key,
        )
    )
    if row is None:
        return None
    if row.request_sha256 != request_sha256:
        raise SocialWriteConflictError("idempotency_payload_mismatch")
    post = db.get(models.Post, row.result_post_id)
    if post is None or post.world_id != world_id:
        raise SocialWriteConflictError("idempotency_result_missing")
    return row, post


def _blocked(db: Session, *, world_id: str, actor_id: str, target_id: str) -> bool:
    return (
        db.scalar(
            select(models.WorldCharacterBlock.id)
            .where(
                models.WorldCharacterBlock.world_id == world_id,
                or_(
                    (models.WorldCharacterBlock.blocker_world_character_id == actor_id)
                    & (
                        models.WorldCharacterBlock.blocked_world_character_id
                        == target_id
                    ),
                    (models.WorldCharacterBlock.blocker_world_character_id == target_id)
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


def _public_root_post(
    db: Session, *, world_id: str, target_post_id: str
) -> models.Post:
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
        raise SocialWriteNotFoundError("reply_target_unavailable")
    return post


def _owner_reply_target(
    db: Session,
    *,
    world_id: str,
    actor_world_character_id: str,
    target_post_id: str,
) -> tuple[models.Post, models.WorldCharacter]:
    post = _public_root_post(db, world_id=world_id, target_post_id=target_post_id)
    target = db.get(models.WorldCharacter, post.author_world_character_id)
    if (
        target is None
        or target.id == actor_world_character_id
        or target.world_id != world_id
        or target.status != "active"
        or target.control_mode != "autonomous"
        or target.activity_runtime_mode != "routine_resident_v1"
    ):
        raise SocialWriteForbiddenError("reply_target_not_autonomous")
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
        raise SocialWriteForbiddenError("reply_target_blocked")
    return post, target


def _autonomous_reply_target(
    db: Session,
    *,
    world_id: str,
    actor_world_character_id: str,
    target_post_id: str,
) -> tuple[models.Post, models.WorldCharacter]:
    post = _public_root_post(db, world_id=world_id, target_post_id=target_post_id)
    target = db.get(models.WorldCharacter, post.author_world_character_id)
    if (
        target is None
        or target.id == actor_world_character_id
        or target.world_id != world_id
        or target.status != "active"
        or _blocked(
            db,
            world_id=world_id,
            actor_id=actor_world_character_id,
            target_id=target.id,
        )
    ):
        raise SocialWriteForbiddenError("autonomous_reply_target_invalid")
    return post, target


def _candidate(
    db: Session, *, reply_id: str, target_id: str
) -> OwnerManualInboxCandidate | None:
    return db.scalar(
        select(OwnerManualInboxCandidate).where(
            OwnerManualInboxCandidate.source_reply_post_id == reply_id,
            OwnerManualInboxCandidate.target_world_character_id == target_id,
        )
    )


def _record_source_event(
    db: Session,
    *,
    world_id: str,
    actor_world_character_id: str,
    target_world_character_id: str | None,
    operation: str,
    post: models.Post,
    root_post: models.Post,
    request_key: str,
    failure_injector: FailureInjector | None,
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


def _post_snapshot(db: Session, post: models.Post) -> SocialPostSnapshot:
    if post.world_id is None or post.author_world_character_id is None:
        raise SocialWriteConflictError("world_post_scope_missing")
    author = db.get(models.WorldCharacter, post.author_world_character_id)
    return SocialPostSnapshot(
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


def _result(
    db: Session,
    *,
    post: models.Post,
    operation: str,
    replayed: bool,
    candidate_id: str | None = None,
) -> SocialWriteResult:
    return SocialWriteResult(
        operation="reply" if operation == "reply" else "post",
        replayed=replayed,
        post=_post_snapshot(db, post),
        delivery=SocialWriteDelivery(
            inbox_candidate_id=candidate_id,
            inbox_status="pending"
            if operation == "reply" and candidate_id
            else "not_applicable",
        ),
    )


__all__ = ["SqlAlchemySocialWriteUnitOfWork"]
