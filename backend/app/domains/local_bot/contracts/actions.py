"""Typed owner collaborations used by actual LocalBot action workflows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, Sequence

from sqlalchemy.orm import Session

from app.domains.characters.schemas import CharacterStateRead, CharacterStateWrite
from app.domains.local_bot.contracts.authentication import (
    LocalBotCharacter,
    LocalBotContext,
    LocalBotOwner,
)
from app.domains.local_bot.contracts.rate_limits import RateLimitLog, RateLimitWorkflows
from app.domains.social.schemas import community as schemas


class LocalBotSocial(Protocol):
    def build_post_created_activity_result(
        self,
        *,
        post_id: str,
        title: str | None,
        body: str | None,
        topic_signature: str | None = None,
        novelty_basis: str | None = None,
        lore_chunk_ids: list[str] | None = None,
        retrieval_mode: str | None = None,
        lore_query_mode: str | None = None,
        message: str | None = None,
    ) -> str: ...

    def create_post(
        self,
        db: Session,
        user: LocalBotOwner,
        data: schemas.PostCreate,
        *,
        log_manual_activity: bool = True,
        post_info: schemas.PostInfoMetadata | None = None,
        world_id: str | None = None,
        author_world_character_id: str | None = None,
    ) -> schemas.PostDetail: ...

    def create_reply(
        self,
        db: Session,
        user: LocalBotOwner,
        post_id: str,
        data: schemas.TimelineReplyCreate,
        *,
        activity_reason: str = "manual_reply",
        enforce_user_quota: bool = True,
    ) -> schemas.PostDetail: ...

    def follow_profile(
        self, db: Session, user: LocalBotOwner, data: schemas.FollowCreate
    ) -> schemas.FollowRead: ...

    def get_character_profile(
        self, db: Session, character_id: str
    ) -> schemas.ProfileRead: ...

    def get_post_thread(self, db: Session, post_id: str) -> schemas.PostThreadRead: ...

    def like_post(
        self,
        db: Session,
        user: LocalBotOwner,
        post_id: str,
        data: schemas.PostLikeCreate,
        *,
        activity_reason: str = "manual_like",
    ) -> schemas.PostDetail: ...

    def list_character_following_feed(
        self,
        db: Session,
        user: LocalBotOwner,
        character_id: str,
        *,
        limit: int = 20,
        cursor: str | None = None,
        content: schemas.FeedContentFilter = "all",
    ) -> schemas.FeedPage: ...

    def list_feed(
        self,
        db: Session,
        *,
        limit: int = 20,
        cursor: str | None = None,
        content: schemas.FeedContentFilter = "all",
    ) -> schemas.FeedPage: ...

    def list_notifications_for_character(
        self,
        db: Session,
        *,
        user_id: str,
        character_id: str,
        limit: int = 50,
        cursor: str | None = None,
    ) -> schemas.NotificationPage: ...

    def mark_character_notification_read(
        self, db: Session, *, user_id: str, character_id: str, notification_id: int
    ) -> schemas.NotificationRead: ...

    def repost_post(
        self,
        db: Session,
        user: LocalBotOwner,
        post_id: str,
        data: schemas.PostLikeCreate,
        *,
        activity_reason: str = "manual_repost",
    ) -> schemas.PostDetail: ...

    def save_character_state(
        self, db: Session, character_id: str, data: CharacterStateWrite
    ) -> CharacterStateRead: ...

    def unfollow_profile(
        self, db: Session, user: LocalBotOwner, data: schemas.FollowCreate
    ) -> None: ...

    def unlike_post(
        self,
        db: Session,
        user: LocalBotOwner,
        post_id: str,
        data: schemas.PostLikeCreate,
    ) -> schemas.PostDetail: ...

    def unrepost_post(
        self,
        db: Session,
        user: LocalBotOwner,
        post_id: str,
        data: schemas.PostLikeCreate,
    ) -> schemas.PostDetail: ...


class LocalBotActivityRow(Protocol):
    action_type: str
    target_post_id: str | None
    created_at: datetime


class LocalBotSavedState(Protocol):
    character_id: str
    mood: str
    summary: str
    memory_note: str
    updated_at: datetime


class LocalBotReads(Protocol):
    def read_character_state(
        self, db: Session, context: LocalBotContext
    ) -> LocalBotSavedState | None: ...
    def list_activity(
        self, db: Session, context: LocalBotContext, *, limit: int
    ) -> Sequence[LocalBotActivityRow]: ...
    def _post_like_exists(
        self, db: Session, context: LocalBotContext, post_id: str
    ) -> bool: ...
    def _post_repost_exists(
        self, db: Session, context: LocalBotContext, post_id: str
    ) -> bool: ...
    def _profile_follow_exists(
        self, db: Session, context: LocalBotContext, target_character_id: str
    ) -> bool: ...


class LocalBotImageRequest(Protocol):
    def __call__(
        self,
        *,
        db: Session,
        user_id: str,
        local_key_prefix: str,
        character: LocalBotCharacter,
        post_id: str,
        image_prompt: str,
        requested_at: datetime,
    ) -> schemas.BotImageRequestRead: ...


@dataclass(frozen=True)
class LocalBotWorkflows:
    social: LocalBotSocial
    reads: LocalBotReads
    limits: RateLimitWorkflows
    log_activity: RateLimitLog
    request_image: LocalBotImageRequest
