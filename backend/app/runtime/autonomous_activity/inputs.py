"""Backend-scoped current persona, today activity and directional relationships."""
from dataclasses import asdict
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.domains.characters.models import Character
from app.domains.relationships.contracts.graph_recall import GraphRecallScope
from app.domains.relationships.service.graph_recall import GraphRecallService
from app.domains.relationships.service.social_context import SocialContextService
from app.domains.world_characters.models import WorldCharacter
from app.domains.world_characters.service.activity_state import read_state
from app.runtime.graph_projection.relationship_graph_read import SqlAlchemyRelationshipGraphReadGateway
from app.runtime.social.today_activity import today_social_activity_reader
from app.config import settings
from app.runtime.autonomous_activity.contracts import TODAY_LIMIT


def relationship_snapshot(ctx, actor, *, counterpart_id=None):
    if not settings.SNS_SOCIAL_CONTEXT_ENABLED:
        return None
    labels = dict(ctx.db.execute(select(WorldCharacter.id, Character.name).join(Character,
        Character.id == WorldCharacter.character_id).where(WorldCharacter.world_id == actor.world_id,
        WorldCharacter.status == "active", Character.deleted_at.is_(None))).all())
    gateway = GraphRecallService(SqlAlchemyRelationshipGraphReadGateway(ctx.db, config=settings, graph_provider="ladybug"))
    service = SocialContextService(gateway.execute)
    return service.prepare(GraphRecallScope(ctx.user_id, actor.world_id, actor.id), labels=labels, counterpart_id=counterpart_id)


def shared_input(ctx, actor, world):
    now = datetime.now(UTC)
    local = now.astimezone(ZoneInfo(world.timezone))
    start = local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
    today = today_social_activity_reader(ctx.db).read(owner_id=ctx.user_id, world_id=actor.world_id,
        subject_world_character_id=actor.id, started_at=start, complete_through=now)
    data = asdict(today)
    # Provider needs bounded actual records, not projection internals.
    records = data.get("records", [])
    if len(records) > TODAY_LIMIT:
        data["records"] = records[:TODAY_LIMIT]
        data["omitted_records"] = len(records) - TODAY_LIMIT
    character = ctx.character
    state = read_state(ctx.db, world_id=actor.world_id, actor_id=actor.id)
    confirmed = datetime.fromisoformat(state["confirmed_at"]) if state["confirmed_at"] else None
    return {"world_id": actor.world_id, "actor_id": actor.id, "now": now.isoformat(),
        "world": {"name": world.name, "tagline": world.tagline, "timezone": world.timezone},
        "world_profile": actor.local_profile or {},
        "persona": {"name": character.name, "summary": character.persona_summary,
            "personality": character.personality, "speech_style": character.speech_style, "worldview": character.worldview,
            "interests": character.topic_preferences, "boundaries": character.safety_rules},
        "current_state": state, "state_elapsed_seconds": max(0, int((now - confirmed).total_seconds())) if confirmed else None,
        "today_activity": data}
