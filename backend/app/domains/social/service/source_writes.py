"""Atomic source-write policies, replay and delivery decisions.

The runtime owns BEGIN IMMEDIATE and retry. These methods keep all source,
audit evidence and inbox candidate writes in that same caller transaction.
"""
from __future__ import annotations
from collections.abc import Callable
from sqlalchemy.orm import Session
from app.core import unit_of_work
from app.core.ids import uuid7_string
from app.domains.social.models import posts as models
from app.domains.social.models.manual_writes import OwnerManualSocialWrite, OwnerManualInboxCandidate
from app.domains.social.contracts.actors import SocialCharacter, SocialUser
from app.domains.social.contracts.source_writes import SourceWriteReferences, SourceWorldCharacter
from app.domains.social.contracts.writes import OwnerPostCommand, OwnerReplyCommand, SocialPostSnapshot, SocialWriteConflictError, SocialWriteDelivery, SocialWriteForbiddenError, SocialWriteResult, ValidatedAutonomousWriteCommand
from app.domains.social.schemas.community import PostCreate, TimelineReplyCreate
from app.domains.social.service.timeline import SocialTimelineService
from app.domains.social.service.manual_writes import _existing_write, _public_root_post
from app.domains.social.repository.manual_writes import _candidate
from app.domains.social.repository.blocks import write_pair_is_blocked as _blocked
from app.domains.social.utils.source_writes import _request_hash


class SocialSourceWriteService:
    def __init__(self, session: Session, *, timeline: SocialTimelineService, references: SourceWriteReferences, failure_injector: Callable[[str], None] | None = None) -> None:
        self._session = session
        self._timeline = timeline
        self._references = references
        self._failure_injector = failure_injector


    def create_owner_post(self, command: OwnerPostCommand) -> SocialWriteResult:
        db = self._session
        actor, character, user = _owner_actor(
            self._references,
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
            return _result(db, references=self._references, post=post, operation="post", replayed=True)

        with unit_of_work.deferred_commits():
            created = self._timeline.create_post(
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
            self._references.record_source_event(
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
        return _result(db, references=self._references, post=post, operation="post", replayed=False)

    def create_owner_reply(self, command: OwnerReplyCommand) -> SocialWriteResult:
        db = self._session
        actor, character, user = _owner_actor(
            self._references,
            world_id=command.world_id,
            current_user_id=command.current_user_id,
        )
        parent, target = _owner_reply_target(
            db,
            references=self._references,
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
                references=self._references,
                post=reply,
                operation="reply",
                replayed=True,
                candidate_id=candidate.id if candidate is not None else None,
            )

        candidate_id = uuid7_string()
        with unit_of_work.deferred_commits():
            created = self._timeline.create_reply(
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
            self._references.record_source_event(
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
            references=self._references,
            post=reply,
            operation="reply",
            replayed=False,
            candidate_id=candidate_id,
        )

    def apply_validated_autonomous_result(
        self, command: ValidatedAutonomousWriteCommand
    ) -> SocialWriteResult:
        db = self._session
        actor, character, user = _autonomous_actor(
            self._references,
            world_id=command.world_id,
            actor_world_character_id=command.actor_world_character_id,
        )
        target_post: models.Post | None = None
        target_actor: SourceWorldCharacter | None = None
        if command.operation == "reply":
            if command.target_post_id is None:
                raise SocialWriteConflictError("autonomous_reply_target_required")
            target_post, target_actor = _autonomous_reply_target(
                db,
                references=self._references,
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
            return _result(db, references=self._references, post=post, operation=command.operation, replayed=True)

        with unit_of_work.deferred_commits():
            if command.operation == "post":
                created = self._timeline.create_post(
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
                created = self._timeline.create_reply(
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
            self._references.record_source_event(
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
        return _result(db, references=self._references, post=post, operation=command.operation, replayed=False)

    def _fail(self, stage: str) -> None:
        if self._failure_injector is not None:
            self._failure_injector(stage)


def _owner_actor(
    references: SourceWriteReferences, *, world_id: str, current_user_id: str
) -> tuple[SourceWorldCharacter, SocialCharacter, SocialUser]:
    snapshot = references.get_owner_identity(
        world_id=world_id,
        current_user_id=current_user_id,
    )
    actor = references.get_world_character(snapshot.world_character_id)
    character = references.get_character(snapshot.character_id)
    user = references.get_user(current_user_id)
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
    _require_membership(references, actor=actor, expected_user_id=current_user_id)
    return actor, character, user


def _autonomous_actor(
    references: SourceWriteReferences, *, world_id: str, actor_world_character_id: str
) -> tuple[SourceWorldCharacter, SocialCharacter, SocialUser]:
    actor = references.get_world_character(actor_world_character_id)
    character = (
        references.get_character(actor.character_id) if actor is not None else None
    )
    user = references.get_user(character.owner_id) if character is not None else None
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
    _require_membership(references, actor=actor, expected_user_id=character.owner_id)
    return actor, character, user


def _require_membership(
    references: SourceWriteReferences, *, actor: SourceWorldCharacter, expected_user_id: str
) -> None:
    membership = references.get_membership(actor.membership_id)
    if (
        membership is None
        or membership.world_id != actor.world_id
        or membership.user_id != expected_user_id
        or membership.status != "active"
    ):
        raise SocialWriteForbiddenError("world_membership_inactive")


def _owner_reply_target(
    db: Session,
    *,
    references: SourceWriteReferences,
    world_id: str,
    actor_world_character_id: str,
    target_post_id: str,
) -> tuple[models.Post, SourceWorldCharacter]:
    post = _public_root_post(db, world_id=world_id, target_post_id=target_post_id)
    target = references.get_world_character(post.author_world_character_id)
    if (
        target is None
        or target.id == actor_world_character_id
        or target.world_id != world_id
        or target.status != "active"
        or target.control_mode != "autonomous"
        or target.activity_runtime_mode != "routine_resident_v1"
    ):
        raise SocialWriteForbiddenError("reply_target_not_autonomous")
    membership = references.get_membership(target.membership_id)
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
    references: SourceWriteReferences,
    world_id: str,
    actor_world_character_id: str,
    target_post_id: str,
) -> tuple[models.Post, SourceWorldCharacter]:
    post = _public_root_post(db, world_id=world_id, target_post_id=target_post_id)
    target = references.get_world_character(post.author_world_character_id)
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


def _post_snapshot(references: SourceWriteReferences, post: models.Post) -> SocialPostSnapshot:
    if post.world_id is None or post.author_world_character_id is None:
        raise SocialWriteConflictError("world_post_scope_missing")
    author = references.get_world_character(post.author_world_character_id)
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
    references: SourceWriteReferences,
    post: models.Post,
    operation: str,
    replayed: bool,
    candidate_id: str | None = None,
) -> SocialWriteResult:
    return SocialWriteResult(
        operation="reply" if operation == "reply" else "post",
        replayed=replayed,
        post=_post_snapshot(references, post),
        delivery=SocialWriteDelivery(
            inbox_candidate_id=candidate_id,
            inbox_status="pending"
            if operation == "reply" and candidate_id
            else "not_applicable",
        ),
    )
