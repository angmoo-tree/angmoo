"""One eligibility query for list/count/read/batch, using only Social storage."""
from sqlalchemy import and_, exists, func, literal, or_, select, tuple_, union_all, update
from datetime import UTC, datetime
from sqlalchemy.orm import aliased
from app.domains.social.contracts.world_notifications import NotificationScope
from app.domains.social.models.posts import Notification, Post, PostLike, PostRepost, ProfileFollow
from app.domains.social.models.feed import WorldCharacterBlock

SUPPORTED_TYPES = ("like", "reply", "quote", "mention", "repost", "follow")


def eligible(scopes: list[NotificationScope], profile_ids: set[str]):
    bindings = union_all(*(select(literal(s.world_id).label("world_id"),
        literal(s.recipient_world_character_id).label("recipient_id"),
        literal(s.recipient_character_id).label("character_id")) for s in scopes)).cte("notification_scopes")
    p, n, block = Post, Notification, WorldCharacterBlock

    def unblocked(author_id):
        return ~exists(select(block.id).where(block.world_id == bindings.c.world_id, or_(
            (block.blocker_world_character_id == bindings.c.recipient_id) & (block.blocked_world_character_id == author_id),
            (block.blocked_world_character_id == bindings.c.recipient_id) & (block.blocker_world_character_id == author_id))))

    visible = (p.visibility == "public", p.deleted_at.is_(None), p.report_hidden_at.is_(None), unblocked(p.author_world_character_id))
    # Freeze the small visibility projection once. Recursing directly over Post
    # can choose its World-only index and rescan every post per descendant.
    readable_posts = select(p.id.label("post_id"), p.world_id, p.reply_to_post_id).join(
        bindings, bindings.c.world_id == p.world_id).where(*visible).cte("notification_readable_posts").prefix_with("MATERIALIZED")
    # Reachability still requires every ancestor to belong to that visible set.
    tree = select(readable_posts.c.post_id, readable_posts.c.world_id).where(
        readable_posts.c.reply_to_post_id.is_(None)).cte("notification_visible_posts", recursive=True)
    tree = tree.union(select(readable_posts.c.post_id, readable_posts.c.world_id).join(tree,
        (readable_posts.c.reply_to_post_id == tree.c.post_id) & (readable_posts.c.world_id == tree.c.world_id)))
    # One scoped reachability set, rather than re-running a correlated recursive
    # lookup per notification. The pair keeps cross-World references ineligible.
    visible_posts = select(tree.c.post_id, tree.c.world_id)
    target_visible = tuple_(n.post_id, n.world_id).in_(visible_posts)
    source_visible = tuple_(n.source_post_id, n.world_id).in_(visible_posts)
    newer = aliased(Notification)
    newest_reaction = ~exists(select(newer.id).where(newer.world_id == n.world_id,
        newer.recipient_world_character_id == n.recipient_world_character_id,
        newer.actor_world_character_id == n.actor_world_character_id,
        newer.notification_type == n.notification_type,
        or_(newer.post_id == n.post_id, and_(newer.post_id.is_(None), n.post_id.is_(None))), newer.id > n.id))
    like_alive = exists(select(PostLike.id).where(PostLike.world_id == n.world_id,
        PostLike.post_id == n.post_id, PostLike.actor_world_character_id == n.actor_world_character_id,
        PostLike.target_world_character_id == n.recipient_world_character_id))
    repost_alive = exists(select(PostRepost.id).where(PostRepost.world_id == n.world_id,
        PostRepost.post_id == n.post_id, PostRepost.actor_world_character_id == n.actor_world_character_id,
        PostRepost.target_world_character_id == n.recipient_world_character_id))
    follow_alive = exists(select(ProfileFollow.id).where(ProfileFollow.world_id == n.world_id,
        ProfileFollow.follower_world_character_id == n.actor_world_character_id,
        ProfileFollow.target_world_character_id == n.recipient_world_character_id))
    return select(n).join(bindings, (n.world_id == bindings.c.world_id) &
        (n.recipient_world_character_id == bindings.c.recipient_id) & (n.recipient_character_id == bindings.c.character_id)).where(
        n.recipient_user_id.is_(None), n.notification_type.in_(SUPPORTED_TYPES),
        n.actor_world_character_id.is_not(None), n.actor_world_character_id != n.recipient_world_character_id,
        unblocked(n.actor_world_character_id), or_(
            and_(n.notification_type == "follow", n.actor_world_character_id.in_(profile_ids), newest_reaction, follow_alive),
            and_(n.notification_type != "follow", target_visible,
                or_(n.source_post_id.is_(None), source_visible),
                or_(n.notification_type.not_in(("reply", "quote")), n.source_post_id.is_not(None)),
                or_(n.notification_type != "like", and_(like_alive, newest_reaction)),
                or_(n.notification_type != "repost", and_(repost_alive, newest_reaction))))
    )


def unread_counts(db, scopes: list[NotificationScope], profile_ids: set[str]) -> dict[str, int]:
    if not scopes:
        return {}
    rows = eligible(scopes, profile_ids).where(Notification.read_at.is_(None)).subquery()
    return dict(db.execute(select(rows.c.world_id, func.count()).group_by(rows.c.world_id)).all())


def list_page(db, scope: NotificationScope, *, limit: int, before_id: int | None, profile_ids: set[str]):
    query = eligible([scope], profile_ids)
    if before_id is not None:
        query = query.where(Notification.id < before_id)
    return list(db.scalars(query.order_by(Notification.id.desc()).limit(limit + 1)))


def readable(db, scope: NotificationScope, notification_id: int, profile_ids: set[str]):
    return db.scalar(eligible([scope], profile_ids).where(Notification.id == notification_id))


def mark_read(db, row: Notification):
    if row.read_at is None:
        db.execute(update(Notification).where(Notification.id == row.id, Notification.read_at.is_(None))
            .values(read_at=datetime.now(UTC)).execution_options(synchronize_session="fetch"))
        db.flush()


def mark_all_read(db, scope: NotificationScope, profile_ids: set[str]):
    """Caller owns the immediate UoW; never load or update rows one at a time."""
    unread = eligible([scope], profile_ids).with_only_columns(Notification.id).where(Notification.read_at.is_(None))
    targets = unread.subquery()
    through_id = db.scalar(select(func.max(targets.c.id)))
    if through_id is None:
        return 0, None, None
    read_at = datetime.now(UTC)
    result = db.execute(update(Notification).where(Notification.read_at.is_(None),
        Notification.id.in_(unread.where(Notification.id <= through_id)))
        .values(read_at=read_at).execution_options(synchronize_session=False))
    # sqlite3 reports -1 for a WITH/CTE UPDATE. changes() on this same connection
    # counts only the direct update, excluding trigger side effects and old reads.
    # PostgreSQL reports the direct UPDATE count through its command result.
    marked_count = (result.rowcount if db.get_bind().dialect.name == 'postgresql'
                    else db.scalar(select(func.changes())))
    if marked_count < 0:
        raise RuntimeError('notification_update_count_unavailable')
    return marked_count, read_at if marked_count else None, through_id


def previews(db, post_ids: set[str]) -> dict[str, str]:
    if not post_ids:
        return {}
    return {row.id: (row.body or row.title)[:280] for row in db.scalars(select(Post).where(Post.id.in_(post_ids)))}
