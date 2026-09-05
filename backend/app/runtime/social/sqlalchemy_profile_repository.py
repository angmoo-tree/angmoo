"""SQLAlchemy adapter for exact-World WorldCharacter social profile activity."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import re
from collections import defaultdict
from datetime import datetime
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.config import settings
from app.domains.social.public import (
    WorldCharacterSocialProfileCounts,
    WorldCharacterSocialProfileForbiddenError,
    WorldCharacterSocialProfileMedia,
    WorldCharacterSocialProfileMention,
    WorldCharacterSocialProfileNotFoundError,
    WorldCharacterSocialProfilePage,
    WorldCharacterSocialProfilePost,
    WorldCharacterSocialProfileQuery,
    WorldCharacterSocialProfileValidationError,
)
from app.domains.world_characters.public import (
    SqlAlchemyWorldCharacterPublicProfileReader,
    WorldCharacterProfileNotFoundError,
)
from app.runtime.social.sqlalchemy_read_repository import (
    social_persistence_models as models,
)

_CURSOR_VERSION = "world-character-social-profile-cursor-v1"
_CURSOR_AAD = _CURSOR_VERSION.encode("ascii")
_CURSOR_NONCE_BYTES = 12
_MENTION_HANDLE_RE = re.compile(
    r"(?<![A-Za-z0-9_.])@([a-z0-9_]{2,40})(?=$|[^A-Za-z0-9_.]|\.(?=$|[^A-Za-z0-9_]))"
)


class SqlAlchemyWorldCharacterSocialProfileReader:
    def __init__(self, db: Session) -> None:
        self.db = db

    def read(
        self,
        query: WorldCharacterSocialProfileQuery,
    ) -> WorldCharacterSocialProfilePage:
        try:
            profile = SqlAlchemyWorldCharacterPublicProfileReader(
                self.db
            ).get_for_world(
                world_id=query.world_id,
                world_character_id=query.world_character_id,
                current_user_id=query.current_user_id,
            )
        except WorldCharacterProfileNotFoundError as exc:
            raise WorldCharacterSocialProfileNotFoundError() from exc

        viewer_ids = self._viewer_world_character_ids(query)
        blocked_ids = self._blocked_world_character_ids(query.world_id, viewer_ids)
        if query.world_character_id in blocked_ids:
            raise WorldCharacterSocialProfileForbiddenError()

        counts = self._counts(query, blocked_ids)
        if query.tab == "likes":
            posts, cursor_values = self._liked_posts(query, blocked_ids)
        else:
            posts, cursor_values = self._authored_posts(query, blocked_ids)

        has_more = len(posts) > query.limit
        visible_posts = posts[: query.limit]
        visible_cursor_values = cursor_values[: query.limit]
        items = self._post_snapshots(
            world_id=query.world_id,
            posts=visible_posts,
            blocked_ids=blocked_ids,
        )
        next_cursor = None
        if has_more and visible_cursor_values:
            created_at, item_id = visible_cursor_values[-1]
            next_cursor = _encode_cursor(
                query,
                created_at=created_at,
                item_id=item_id,
            )
        return WorldCharacterSocialProfilePage(
            world_id=query.world_id,
            world_character_id=query.world_character_id,
            character_id=profile.character_id,
            counts=counts,
            tab=query.tab,
            items=items,
            next_cursor=next_cursor,
        )

    def _viewer_world_character_ids(
        self,
        query: WorldCharacterSocialProfileQuery,
    ) -> tuple[str, ...]:
        rows = self.db.scalars(
            select(models.WorldCharacter.id)
            .join(
                models.WorldMembership,
                (models.WorldMembership.id == models.WorldCharacter.membership_id)
                & (models.WorldMembership.world_id == models.WorldCharacter.world_id),
            )
            .where(
                models.WorldCharacter.world_id == query.world_id,
                models.WorldCharacter.owner_user_id == query.current_user_id,
                models.WorldCharacter.control_mode == "owner_controlled",
                models.WorldCharacter.status == "active",
                models.WorldMembership.user_id == query.current_user_id,
                models.WorldMembership.status == "active",
            )
            .order_by(models.WorldCharacter.id.asc())
        )
        return tuple(str(value) for value in rows)

    def _blocked_world_character_ids(
        self,
        world_id: str,
        viewer_ids: tuple[str, ...],
    ) -> frozenset[str]:
        if not viewer_ids:
            return frozenset()
        rows = self.db.execute(
            select(
                models.WorldCharacterBlock.blocker_world_character_id,
                models.WorldCharacterBlock.blocked_world_character_id,
            ).where(
                models.WorldCharacterBlock.world_id == world_id,
                or_(
                    models.WorldCharacterBlock.blocker_world_character_id.in_(
                        viewer_ids
                    ),
                    models.WorldCharacterBlock.blocked_world_character_id.in_(
                        viewer_ids
                    ),
                ),
            )
        ).all()
        blocked: set[str] = set()
        viewer_set = set(viewer_ids)
        for blocker_id, blocked_id in rows:
            if blocker_id in viewer_set:
                blocked.add(str(blocked_id))
            if blocked_id in viewer_set:
                blocked.add(str(blocker_id))
        return frozenset(blocked)

    def _counts(
        self,
        query: WorldCharacterSocialProfileQuery,
        blocked_ids: frozenset[str],
    ) -> WorldCharacterSocialProfileCounts:
        authored = (
            models.Post.world_id == query.world_id,
            models.Post.author_world_character_id == query.world_character_id,
            models.Post.visibility == "public",
            models.Post.deleted_at.is_(None),
            models.Post.report_hidden_at.is_(None),
        )
        post_count = self.db.scalar(
            select(func.count(models.Post.id)).where(
                *authored,
                models.Post.reply_to_post_id.is_(None),
                models.Post.repost_of_post_id.is_(None),
            )
        )

        parent = aliased(models.Post)
        reply_count_statement = (
            select(func.count(models.Post.id))
            .join(parent, parent.id == models.Post.reply_to_post_id)
            .where(
                *authored,
                models.Post.reply_to_post_id.is_not(None),
                parent.world_id == query.world_id,
                parent.visibility == "public",
                parent.deleted_at.is_(None),
                parent.report_hidden_at.is_(None),
            )
        )
        if blocked_ids:
            reply_count_statement = reply_count_statement.where(
                parent.author_world_character_id.not_in(blocked_ids)
            )
        reply_count = self.db.scalar(reply_count_statement)

        liked_post_statement = (
            select(func.count(models.PostLike.id))
            .join(models.Post, models.Post.id == models.PostLike.post_id)
            .outerjoin(parent, parent.id == models.Post.reply_to_post_id)
            .where(
                models.PostLike.world_id == query.world_id,
                models.PostLike.actor_world_character_id == query.world_character_id,
                models.Post.world_id == query.world_id,
                models.Post.visibility == "public",
                models.Post.deleted_at.is_(None),
                models.Post.report_hidden_at.is_(None),
                or_(
                    models.Post.reply_to_post_id.is_(None),
                    and_(
                        parent.world_id == query.world_id,
                        parent.visibility == "public",
                        parent.deleted_at.is_(None),
                        parent.report_hidden_at.is_(None),
                    ),
                ),
            )
        )
        if blocked_ids:
            liked_post_statement = liked_post_statement.where(
                models.Post.author_world_character_id.not_in(blocked_ids)
            )
        liked_post_count = self.db.scalar(liked_post_statement)

        received_like_statement = (
            select(func.count(models.PostLike.id))
            .join(models.Post, models.Post.id == models.PostLike.post_id)
            .outerjoin(parent, parent.id == models.Post.reply_to_post_id)
            .where(
                models.PostLike.world_id == query.world_id,
                models.PostLike.target_world_character_id == query.world_character_id,
                models.Post.world_id == query.world_id,
                models.Post.author_world_character_id == query.world_character_id,
                models.Post.visibility == "public",
                models.Post.deleted_at.is_(None),
                models.Post.report_hidden_at.is_(None),
                models.Post.repost_of_post_id.is_(None),
                or_(
                    models.Post.reply_to_post_id.is_(None),
                    and_(
                        parent.world_id == query.world_id,
                        parent.visibility == "public",
                        parent.deleted_at.is_(None),
                        parent.report_hidden_at.is_(None),
                    ),
                ),
            )
        )
        if blocked_ids:
            received_like_statement = received_like_statement.where(
                models.PostLike.actor_world_character_id.not_in(blocked_ids),
                or_(
                    models.Post.reply_to_post_id.is_(None),
                    parent.author_world_character_id.not_in(blocked_ids),
                ),
            )
        received_like_count = self.db.scalar(received_like_statement)
        return WorldCharacterSocialProfileCounts(
            post_count=int(post_count or 0),
            reply_count=int(reply_count or 0),
            liked_post_count=int(liked_post_count or 0),
            received_like_count=int(received_like_count or 0),
        )

    def _authored_posts(
        self,
        query: WorldCharacterSocialProfileQuery,
        blocked_ids: frozenset[str],
    ) -> tuple[list[models.Post], list[tuple[datetime, str]]]:
        statement = select(models.Post).where(
            models.Post.world_id == query.world_id,
            models.Post.author_world_character_id == query.world_character_id,
            models.Post.visibility == "public",
            models.Post.deleted_at.is_(None),
            models.Post.report_hidden_at.is_(None),
        )
        if query.tab == "posts":
            statement = statement.where(
                models.Post.reply_to_post_id.is_(None),
                models.Post.repost_of_post_id.is_(None),
            )
        else:
            parent = aliased(models.Post)
            statement = statement.join(
                parent,
                parent.id == models.Post.reply_to_post_id,
            ).where(
                models.Post.reply_to_post_id.is_not(None),
                parent.world_id == query.world_id,
                parent.visibility == "public",
                parent.deleted_at.is_(None),
                parent.report_hidden_at.is_(None),
            )
            if blocked_ids:
                statement = statement.where(
                    parent.author_world_character_id.not_in(blocked_ids)
                )
        cursor = _decode_cursor(query)
        if cursor is not None:
            created_at, post_id = cursor
            statement = statement.where(
                or_(
                    models.Post.created_at < created_at,
                    and_(
                        models.Post.created_at == created_at,
                        models.Post.id < post_id,
                    ),
                )
            )
        posts = list(
            self.db.scalars(
                statement.order_by(
                    models.Post.created_at.desc(),
                    models.Post.id.desc(),
                ).limit(query.limit + 1)
            )
        )
        return posts, [(post.created_at, post.id) for post in posts]

    def _liked_posts(
        self,
        query: WorldCharacterSocialProfileQuery,
        blocked_ids: frozenset[str],
    ) -> tuple[list[models.Post], list[tuple[datetime, str]]]:
        parent = aliased(models.Post)
        statement = (
            select(models.PostLike, models.Post)
            .join(models.Post, models.Post.id == models.PostLike.post_id)
            .outerjoin(parent, parent.id == models.Post.reply_to_post_id)
            .where(
                models.PostLike.world_id == query.world_id,
                models.PostLike.actor_world_character_id == query.world_character_id,
                models.Post.world_id == query.world_id,
                models.Post.visibility == "public",
                models.Post.deleted_at.is_(None),
                models.Post.report_hidden_at.is_(None),
                or_(
                    models.Post.reply_to_post_id.is_(None),
                    and_(
                        parent.world_id == query.world_id,
                        parent.visibility == "public",
                        parent.deleted_at.is_(None),
                        parent.report_hidden_at.is_(None),
                    ),
                ),
            )
        )
        if blocked_ids:
            statement = statement.where(
                models.Post.author_world_character_id.not_in(blocked_ids)
            )
        cursor = _decode_cursor(query)
        if cursor is not None:
            created_at, like_id = cursor
            try:
                like_id_value = int(like_id)
            except ValueError as exc:
                raise WorldCharacterSocialProfileValidationError() from exc
            statement = statement.where(
                or_(
                    models.PostLike.created_at < created_at,
                    and_(
                        models.PostLike.created_at == created_at,
                        models.PostLike.id < like_id_value,
                    ),
                )
            )
        rows = self.db.execute(
            statement.order_by(
                models.PostLike.created_at.desc(),
                models.PostLike.id.desc(),
            ).limit(query.limit + 1)
        ).all()
        posts = [row[1] for row in rows]
        cursor_values = [(row[0].created_at, str(row[0].id)) for row in rows]
        return posts, cursor_values

    def _post_snapshots(
        self,
        *,
        world_id: str,
        posts: list[models.Post],
        blocked_ids: frozenset[str],
    ) -> tuple[WorldCharacterSocialProfilePost, ...]:
        if not posts:
            return ()
        post_ids = [post.id for post in posts]
        author_ids = {
            str(post.author_world_character_id)
            for post in posts
            if post.author_world_character_id is not None
        }
        authors = {
            str(world_character.id): (world_character, character)
            for world_character, character in self.db.execute(
                select(models.WorldCharacter, models.Character)
                .join(
                    models.Character,
                    models.Character.id == models.WorldCharacter.character_id,
                )
                .where(models.WorldCharacter.id.in_(author_ids))
            ).all()
        }
        active_author_ids = {
            str(value)
            for value in self.db.scalars(
                select(models.WorldCharacter.id)
                .join(
                    models.Character,
                    models.Character.id == models.WorldCharacter.character_id,
                )
                .join(
                    models.WorldMembership,
                    (models.WorldMembership.id == models.WorldCharacter.membership_id)
                    & (
                        models.WorldMembership.world_id
                        == models.WorldCharacter.world_id
                    ),
                )
                .where(
                    models.WorldCharacter.id.in_(author_ids),
                    models.WorldCharacter.world_id == world_id,
                    models.WorldCharacter.status == "active",
                    models.WorldMembership.status == "active",
                    models.Character.deleted_at.is_(None),
                    models.Character.moderation_status == "active",
                )
            )
        }

        reply_counts_statement = select(
            models.Post.reply_to_post_id, func.count(models.Post.id)
        ).where(
            models.Post.world_id == world_id,
            models.Post.reply_to_post_id.in_(post_ids),
            models.Post.visibility == "public",
            models.Post.deleted_at.is_(None),
            models.Post.report_hidden_at.is_(None),
        )
        if blocked_ids:
            reply_counts_statement = reply_counts_statement.where(
                models.Post.author_world_character_id.not_in(blocked_ids)
            )
        reply_counts = {
            str(post_id): int(count)
            for post_id, count in self.db.execute(
                reply_counts_statement.group_by(models.Post.reply_to_post_id)
            ).all()
            if post_id is not None
        }

        like_counts_statement = select(
            models.PostLike.post_id,
            func.count(models.PostLike.id),
        ).where(
            models.PostLike.world_id == world_id,
            models.PostLike.post_id.in_(post_ids),
        )
        if blocked_ids:
            like_counts_statement = like_counts_statement.where(
                models.PostLike.actor_world_character_id.not_in(blocked_ids)
            )
        like_counts = {
            str(post_id): int(count)
            for post_id, count in self.db.execute(
                like_counts_statement.group_by(models.PostLike.post_id)
            ).all()
        }

        media_by_post: dict[str, list[WorldCharacterSocialProfileMedia]] = defaultdict(
            list
        )
        for media in self.db.scalars(
            select(models.PostMedia)
            .where(models.PostMedia.post_id.in_(post_ids))
            .order_by(models.PostMedia.post_id.asc(), models.PostMedia.id.asc())
        ):
            url = media.url.strip()
            if not url.startswith("/media/") or url.startswith("//"):
                continue
            media_by_post[str(media.post_id)].append(
                WorldCharacterSocialProfileMedia(
                    id=media.id,
                    post_id=media.post_id,
                    media_type=media.media_type,
                    url=url,
                    alt_text=media.alt_text,
                    model=media.model,
                    prompt_hash=media.prompt_hash,
                    byte_size=media.byte_size,
                    width=media.width,
                    height=media.height,
                    created_at=media.created_at,
                )
            )

        mentions_by_post = self._mentions_by_post(posts)
        snapshots: list[WorldCharacterSocialProfilePost] = []
        for post in posts:
            author_id = str(post.author_world_character_id or "")
            author_row = authors.get(author_id)
            world_character = author_row[0] if author_row else None
            character = author_row[1] if author_row else None
            local_profile = (
                world_character.local_profile
                if world_character is not None
                and isinstance(world_character.local_profile, dict)
                else {}
            )
            avatar = (
                local_profile.get("avatar_url") or character.avatar_url
                if character is not None
                else None
            )
            snapshots.append(
                WorldCharacterSocialProfilePost(
                    id=post.id,
                    world_id=world_id,
                    author_world_character_id=author_id,
                    author_name=post.author_name,
                    author_handle=character.handle if character is not None else None,
                    author_avatar_url=str(avatar) if avatar else None,
                    title=post.title,
                    body=post.body,
                    post_type=post.post_type,
                    reply_to_post_id=post.reply_to_post_id,
                    created_at=post.created_at,
                    reply_count=reply_counts.get(post.id, 0),
                    like_count=like_counts.get(post.id, 0),
                    author_profile_capability=(
                        "available"
                        if author_id in active_author_ids
                        and author_id not in blocked_ids
                        else "unavailable"
                    ),
                    mentioned_characters=mentions_by_post.get(post.id, ()),
                    media=tuple(media_by_post.get(post.id, ())),
                )
            )
        return tuple(snapshots)

    def _mentions_by_post(
        self,
        posts: list[models.Post],
    ) -> dict[str, tuple[WorldCharacterSocialProfileMention, ...]]:
        handles_by_post: dict[str, list[str]] = {}
        all_handles: set[str] = set()
        for post in posts:
            seen: set[str] = set()
            handles: list[str] = []
            for text in (post.title, post.body):
                for match in _MENTION_HANDLE_RE.finditer(text or ""):
                    handle = match.group(1)
                    if handle in seen:
                        continue
                    seen.add(handle)
                    handles.append(handle)
                    all_handles.add(handle)
            handles_by_post[post.id] = handles
        if not all_handles:
            return {}
        characters = {
            str(character.handle): character
            for character in self.db.scalars(
                select(models.Character).where(
                    models.Character.handle.in_(all_handles),
                    models.Character.deleted_at.is_(None),
                    models.Character.moderation_status == "active",
                )
            )
            if character.handle is not None
        }
        result: dict[str, tuple[WorldCharacterSocialProfileMention, ...]] = {}
        for post_id, handles in handles_by_post.items():
            result[post_id] = tuple(
                WorldCharacterSocialProfileMention(
                    handle=handle,
                    character_id=character.id,
                    name=character.name,
                )
                for handle in handles
                if (character := characters.get(handle)) is not None
            )
        return result


def _encode_cursor(
    query: WorldCharacterSocialProfileQuery,
    *,
    created_at: datetime,
    item_id: str,
) -> str:
    payload = {
        "created_at": created_at.isoformat(),
        "item_id": item_id,
        "tab": query.tab,
        "version": _CURSOR_VERSION,
        "world_character_id": query.world_character_id,
        "world_id": query.world_id,
    }
    nonce = os.urandom(_CURSOR_NONCE_BYTES)
    plaintext = json.dumps(
        payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    encrypted = AESGCM(_cursor_key()).encrypt(nonce, plaintext, _CURSOR_AAD)
    encoded = base64.urlsafe_b64encode(nonce + encrypted).decode("ascii")
    return encoded.rstrip("=")


def _decode_cursor(
    query: WorldCharacterSocialProfileQuery,
) -> tuple[datetime, str] | None:
    if query.cursor is None:
        return None
    try:
        padding = "=" * (-len(query.cursor) % 4)
        encrypted = base64.urlsafe_b64decode(query.cursor + padding)
        if len(encrypted) <= _CURSOR_NONCE_BYTES + 16:
            raise ValueError("cursor_length")
        plaintext = AESGCM(_cursor_key()).decrypt(
            encrypted[:_CURSOR_NONCE_BYTES],
            encrypted[_CURSOR_NONCE_BYTES:],
            _CURSOR_AAD,
        )
        decoded: Any = json.loads(plaintext.decode("utf-8"))
        if not isinstance(decoded, dict) or set(decoded) != {
            "created_at",
            "item_id",
            "tab",
            "version",
            "world_character_id",
            "world_id",
        }:
            raise ValueError("cursor_shape")
        if (
            decoded["version"] != _CURSOR_VERSION
            or decoded["world_id"] != query.world_id
            or decoded["world_character_id"] != query.world_character_id
            or decoded["tab"] != query.tab
            or not isinstance(decoded["item_id"], str)
            or not decoded["item_id"]
            or not isinstance(decoded["created_at"], str)
        ):
            raise ValueError("cursor_scope")
        return datetime.fromisoformat(decoded["created_at"]), decoded["item_id"]
    except (
        binascii.Error,
        InvalidTag,
        UnicodeDecodeError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        raise WorldCharacterSocialProfileValidationError() from exc


def _cursor_key() -> bytes:
    return hashlib.sha256(
        f"{_CURSOR_VERSION}\0{settings.app_secret}".encode("utf-8")
    ).digest()


__all__ = ["SqlAlchemyWorldCharacterSocialProfileReader"]
