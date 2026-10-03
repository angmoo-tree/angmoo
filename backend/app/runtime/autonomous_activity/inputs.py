"""Backend-scoped current persona, today activity and directional relationships."""
from dataclasses import asdict
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.domains.characters.models import Character
from app.domains.characters.service.prompt_persona import request_persona, PERSONA_INTERPRETATION
from app.domains.relationships.contracts.graph_recall import GraphRecallScope
from app.domains.relationships.service.graph_recall import GraphRecallService
from app.domains.relationships.service.social_context import SocialContextService
from app.domains.world_characters.models import WorldCharacter
from app.domains.world_characters.service.activity_state import read_state
from app.runtime.graph_projection.relationship_graph_read import SqlAlchemyRelationshipGraphReadGateway
from app.runtime.social.today_activity import today_social_activity_reader
from app.config import settings
from app.runtime.autonomous_activity.contracts import TODAY_LIMIT
from app.contracts.environment import EnvironmentSnapshot
from app.core.calendar import local_period


def relationship_snapshot(ctx, actor, *, counterpart_id=None):
    if not settings.SNS_SOCIAL_CONTEXT_ENABLED:
        return None
    labels = dict(ctx.db.execute(select(WorldCharacter.id, Character.name).join(Character,
        Character.id == WorldCharacter.character_id).where(WorldCharacter.world_id == actor.world_id,
        WorldCharacter.status == "active", Character.deleted_at.is_(None))).all())
    gateway = GraphRecallService(SqlAlchemyRelationshipGraphReadGateway(ctx.db, config=settings, graph_provider="ladybug"))
    service = SocialContextService(gateway.execute)
    return service.prepare(GraphRecallScope(ctx.user_id, actor.world_id, actor.id), labels=labels, counterpart_id=counterpart_id)


def shared_input(ctx, actor, world, *, environment=None):
    now = datetime.now(UTC)
    if environment is None:
        from app.domains.identity.service.environment import snapshot
        environment = snapshot(ctx.db, ctx.user_id)
    start, _ = local_period(now, environment.timezone)
    today = today_social_activity_reader(ctx.db).read(owner_id=ctx.user_id, world_id=actor.world_id,
        subject_world_character_id=actor.id, started_at=start, complete_through=now)
    data = asdict(today)
    # Provider needs bounded actual records, not projection internals.
    records = data.get("records", [])
    if len(records) > TODAY_LIMIT:
        data["records"] = records[:TODAY_LIMIT]
        data["omitted_records"] = len(records) - TODAY_LIMIT
    character = ctx.character
    from app.runtime.autonomous_activity.name_binding import activity_name_binding
    name_binding = activity_name_binding(ctx)
    state = read_state(ctx.db, world_id=actor.world_id, actor_id=actor.id)
    confirmed = datetime.fromisoformat(state["confirmed_at"]) if state["confirmed_at"] else None
    return {"world_id": actor.world_id, "actor_id": actor.id, "now": now.isoformat(),
        "world": {"name": world.name, "tagline": world.tagline, "timezone": environment.timezone},
        "environment": environment.to_dict(),
        "world_profile": actor.local_profile or {},
        "persona": {**request_persona(character, name_binding), "interpretation": PERSONA_INTERPRETATION},
        "current_state": state, "state_elapsed_seconds": max(0, int((now - confirmed).total_seconds())) if confirmed else None,
        "today_activity": data}
