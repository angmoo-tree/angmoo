"""Bounded, read-only current-World status; no preparation/provider side effect."""
from datetime import UTC, datetime
from sqlalchemy import select, func
from app.domains.routines.models.resident import AgentPublicActionExecution
from app.domains.social.models.posts import Post
from app.domains.world_characters.schemas.status import WorldCharacterStatusRead, StatusActivity
from app.domains.world_characters.service.configuration import effective_configuration
from app.domains.identity.service.environment import snapshot
from app.core.calendar import local_period


def read(service, *, world_id, world_character_id, user):
    role, _ = service.authorize_credentials(world_id=world_id, world_character_id=world_character_id, user=user, mutation=False)
    management = service.management(world_id=world_id, world_character_id=world_character_id, user=user)
    value = effective_configuration(service.db, world_character_id=role.id)
    environment = snapshot(service.db, user.id)
    start, end = local_period(datetime.now(UTC), environment.timezone)
    scope = (AgentPublicActionExecution.world_id == world_id, AgentPublicActionExecution.actor_world_character_id == role.id)
    rows = service.db.scalars(select(AgentPublicActionExecution).where(*scope).order_by(
        AgentPublicActionExecution.created_at.desc(), AgentPublicActionExecution.id.desc()).limit(20)).all()
    posts = {p.id: p for p in service.db.scalars(select(Post).where(Post.id.in_([r.target_post_id for r in rows if r.target_post_id]),
        Post.world_id == world_id, Post.visibility == "public", Post.deleted_at.is_(None)))}
    counts = dict(service.db.execute(select(AgentPublicActionExecution.action_type, func.count()).where(*scope,
        AgentPublicActionExecution.created_at >= start, AgentPublicActionExecution.created_at < end,
        AgentPublicActionExecution.status.in_(("completed", "succeeded", "success", "ok"))).group_by(AgentPublicActionExecution.action_type)).all())
    settings = value.settings
    return WorldCharacterStatusRead(world_id=world_id, world_character_id=role.id, revision=role.version,
        autonomous_enabled=role.autonomous_enabled, state=management.item.status, timezone=environment.timezone,
        next_activity_at=management.item.next_activity_at,
        recent_activity=[StatusActivity(id=str(row.id), action=row.action_type, status=row.status,
            occurred_at=(row.created_at.replace(tzinfo=UTC) if row.created_at.tzinfo is None else row.created_at).isoformat(), post_id=row.target_post_id if row.target_post_id in posts else None,
            title=posts[row.target_post_id].title if row.target_post_id in posts else None) for row in rows],
        persona={key: getattr(settings, key) for key in ("worldview", "personality", "speech_style", "character_background", "topic_preferences", "safety_rules")},
        summary={"posts": counts.get("post", 0), "replies": counts.get("comment", 0) + counts.get("reply", 0),
            "likes": counts.get("like", 0), "post_limit": settings.max_posts_per_day, "reply_limit": settings.max_comments_per_day,
            "active_hours": settings.active_hours_start + "–" + settings.active_hours_end,
            "allowed_actions": [name for name, allowed in (("reply", settings.allow_reply), ("post", settings.allow_post), ("like", settings.allow_like)) if allowed]})
