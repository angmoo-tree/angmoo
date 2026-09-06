"""World profile input, visibility, pagination and presentation policies."""

from __future__ import annotations
from datetime import datetime
from sqlalchemy.orm import Session
from app.domains.social.contracts.profile_activity import (
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
from app.domains.social.models.posts import Post
import re
from collections import defaultdict
from app.domains.social.contracts.profile_references import ProfileActivityReferences
from app.domains.social.repository.world_profile import WorldProfileRepository
from app.domains.social.service.profile_cursor import _encode_cursor
from app.domains.world_characters.contracts.public_profile import WorldCharacterProfileNotFoundError


_MENTION_HANDLE_RE = re.compile(
    "(?<![A-Za-z0-9_.])@([a-z0-9_]{2,40})(?=$|[^A-Za-z0-9_.]|\\.(?=$|[^A-Za-z0-9_]))"
)


class WorldSocialProfileService:
    def __init__(self, db: Session, *, references: ProfileActivityReferences) -> None:
        self.repository = WorldProfileRepository(db)
        self.references = references

    def read(
        self, query: WorldCharacterSocialProfileQuery
    ) -> WorldCharacterSocialProfilePage:
        if not query.world_id.strip() or not query.world_character_id.strip():
            raise WorldCharacterSocialProfileValidationError()
        if not query.current_user_id.strip():
            raise WorldCharacterSocialProfileValidationError()
        if query.tab not in {"posts", "replies", "likes"}:
            raise WorldCharacterSocialProfileValidationError()
        if query.limit < 1 or query.limit > 20:
            raise WorldCharacterSocialProfileValidationError()
        try:
            profile = self.references.profile(query)
        except WorldCharacterProfileNotFoundError as exc:
            raise WorldCharacterSocialProfileNotFoundError() from exc
        viewer_ids = self.references._viewer_world_character_ids(query)
        blocked_ids = self.repository._blocked_world_character_ids(
            query.world_id, viewer_ids
        )
        if query.world_character_id in blocked_ids:
            raise WorldCharacterSocialProfileForbiddenError()
        counts = self.repository._counts(query, blocked_ids)
        if query.tab == "likes":
            posts, cursor_values = self.repository._liked_posts(query, blocked_ids)
        else:
            posts, cursor_values = self.repository._authored_posts(query, blocked_ids)
        has_more = len(posts) > query.limit
        visible_posts = posts[: query.limit]
        visible_cursor_values = cursor_values[: query.limit]
        items = self._post_snapshots(
            world_id=query.world_id, posts=visible_posts, blocked_ids=blocked_ids
        )
        next_cursor = None
        if has_more and visible_cursor_values:
            created_at, item_id = visible_cursor_values[-1]
            next_cursor = _encode_cursor(query, created_at=created_at, item_id=item_id)
        return WorldCharacterSocialProfilePage(
            world_id=query.world_id,
            world_character_id=query.world_character_id,
            character_id=profile.character_id,
            counts=counts,
            tab=query.tab,
            items=items,
            next_cursor=next_cursor,
        )

    def _post_snapshots(
        self, *, world_id: str, posts: list[Post], blocked_ids: frozenset[str]
    ) -> tuple[WorldCharacterSocialProfilePost, ...]:
        if not posts:
            return ()
        post_ids = [post.id for post in posts]
        author_ids = {
            str(post.author_world_character_id)
            for post in posts
            if post.author_world_character_id is not None
        }
        authors = self.references.authors(author_ids)
        active_author_ids = self.references.active_author_ids(
            world_id=world_id, author_ids=author_ids
        )
        reply_counts = self.repository.reply_counts(
            world_id=world_id, post_ids=post_ids, blocked_ids=blocked_ids
        )
        like_counts = self.repository.like_counts(
            world_id=world_id, post_ids=post_ids, blocked_ids=blocked_ids
        )
        media_by_post: dict[str, list[WorldCharacterSocialProfileMedia]] = defaultdict(
            list
        )
        for media in self.repository.media(post_ids):
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
                    author_profile_capability="available"
                    if author_id in active_author_ids and author_id not in blocked_ids
                    else "unavailable",
                    mentioned_characters=mentions_by_post.get(post.id, ()),
                    media=tuple(media_by_post.get(post.id, ())),
                )
            )
        return tuple(snapshots)

    def _mentions_by_post(
        self, posts: list[Post]
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
        characters = self.references.characters_by_handles(all_handles)
        result: dict[str, tuple[WorldCharacterSocialProfileMention, ...]] = {}
        for post_id, handles in handles_by_post.items():
            result[post_id] = tuple(
                (
                    WorldCharacterSocialProfileMention(
                        handle=handle, character_id=character.id, name=character.name
                    )
                    for handle in handles
                    if (character := characters.get(handle)) is not None
                )
            )
        return result
