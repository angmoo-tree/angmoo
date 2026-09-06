"""Describe the existing foreign source joins for Memory recovery.

Constructing this reader only resolves registered SQL tables. Queries run later
in Memory's repository, with the same caller Session and original predicates.
"""

from sqlalchemy import or_
from app.models import Base


def build_source_catalogs():
    tables = Base.metadata.tables

    def source_catalogs(setting, subject):
        posts, likes, events = (
            tables["posts"],
            tables["post_likes"],
            tables["social_events"],
        )
        messages, threads, observations = (
            tables["message_messages"],
            tables["message_threads"],
            tables["world_character_feed_observations"],
        )
        catalogs = [
            (
                posts,
                posts.c.created_at,
                posts.c.id,
                ("POST", "REPLY"),
                [
                    posts.c.world_id == setting.world_id,
                    posts.c.author_world_character_id == subject,
                ],
                posts,
            ),
            (
                likes,
                likes.c.created_at,
                likes.c.id,
                ("REACTION",),
                [
                    likes.c.world_id == setting.world_id,
                    likes.c.actor_world_character_id == subject,
                ],
                likes,
            ),
            (
                events,
                events.c.created_at,
                events.c.id,
                ("SOCIAL_EVENT",),
                [
                    events.c.world_id == setting.world_id,
                    or_(
                        events.c.actor_world_character_id == subject,
                        events.c.target_world_character_id == subject,
                    ),
                    ~events.c.event_type.in_(
                        (
                            "post_published",
                            "reply_created",
                            "comment_created",
                            "like_added",
                        )
                    ),
                ],
                events,
            ),
            (
                messages.join(threads, threads.c.id == messages.c.thread_id),
                messages.c.created_at,
                messages.c.id,
                ("CHAT_MESSAGE",),
                [
                    threads.c.world_id == setting.world_id,
                    threads.c.responding_world_character_id == subject,
                    messages.c.role == "assistant",
                    messages.c.status == "ok",
                    threads.c.world_scope_status == "resolved",
                ],
                messages,
            ),
            (
                observations.join(posts, posts.c.id == observations.c.post_id),
                observations.c.observed_at,
                posts.c.id,
                ("POST", "REPLY"),
                [
                    observations.c.world_id == setting.world_id,
                    observations.c.observer_world_character_id == subject,
                    observations.c.status == "observed",
                ],
                posts,
            ),
        ]
        return catalogs

    return source_catalogs
