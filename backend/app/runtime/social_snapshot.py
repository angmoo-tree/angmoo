"""Resolve the actual active SNS actor before preparing a Relationships snapshot."""
from dataclasses import replace
from sqlalchemy import select
from app.config import settings
from app.domains.characters.models import Character
from app.domains.world_characters.models import WorldCharacter
from app.domains.relationships.contracts.graph_recall import GraphRecallScope
from app.domains.relationships.contracts.social_context import SocialContextChangedError
from app.domains.relationships.contracts.social_consumption import SocialContextUse
from app.domains.relationships.service.social_context import SocialContextService
from app.domains.relationships.service.graph_recall import GraphRecallService
from app.runtime.graph_projection.relationship_graph_read import SqlAlchemyRelationshipGraphReadGateway


def prepare_activity_social_context(ctx, *, active_actor):
    if settings.CHAT_RECALL_MODE == "legacy_checkpoint":
        return ctx
    actor = active_actor(ctx.db, character_id=ctx.character.id)
    scope = GraphRecallScope(ctx.user_id, actor.world_id, actor.id)
    labels = dict(ctx.db.execute(select(WorldCharacter.id, Character.name).join(Character,
        Character.id == WorldCharacter.character_id).where(WorldCharacter.world_id == actor.world_id,
            WorldCharacter.status == "active", Character.deleted_at.is_(None), Character.moderation_status == "active")).all())
    gateway = GraphRecallService(SqlAlchemyRelationshipGraphReadGateway(ctx.db, config=settings, graph_provider="ladybug"))
    service = SocialContextService(gateway.execute)
    snapshot = service.prepare(scope, labels=labels)
    def validate():
        current = active_actor(ctx.db, character_id=ctx.character.id)
        if (current.id, current.world_id) != (scope.subject_world_character_id, scope.world_id):
            raise SocialContextChangedError("social_context_scope_changed")
        service.assert_current(snapshot)
    return replace(ctx, social_context=SocialContextUse(snapshot, validate))


def with_social_receipts(ctx, result):
    use = getattr(ctx, "social_context", None)
    if use is not None:
        result = {**result, "social_context": use.snapshot.manifest(), "social_context_consumers": list(use.receipts)}
    return result
