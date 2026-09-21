"""Bind a World feed cycle to the existing resident context and owner operations."""

from __future__ import annotations
from typing import Any
from sqlalchemy.orm import Session
from app.domains.world_characters.models import CharacterActiveWorld
from app.domains.social.contracts.feed_execution import FeedReactionProvider, WorldFeedContext
from app.domains.social.service import feed_cycle as service
from app.runtime.social.world_feed_queries import WorldFeedQueries
from app.runtime.activity_proposals import composition as activity_proposal_runtime
from app.runtime.social import world_feed_actions as world_feed_social_apply
from app.runtime.social.observations import observe_source
from app.runtime.social.subjective_composition import record_declared_subjective_context, record_activity_thought
from app.domains.routines.repository import public_action_executions as execution_queries
from app.domains.routines.service import public_action_executions as execution_service
from app.runtime.social.agent_tools import agent_tool_actions
from app.runtime.social.feed_reaction_provider import DirectFeedReactionProvider
from app.integrations.direct_llm import (
    DirectLlmDeferred,
    DirectLlmError,
    DirectLlmJsonError,
    RunLlmTracker,
)


class WorldFeedExecutions:
    get_public_action_execution_by_signature = staticmethod(execution_queries.get_public_action_execution_by_signature)
    create_public_action_execution = staticmethod(execution_service.create_public_action_execution)
    mark_public_action_execution_finished = staticmethod(execution_service.mark_public_action_execution_finished)


class RuntimeWorldFeedWorkflows:
    def refresh_social_context(self, ctx, *, counterpart_id=None):
        from dataclasses import replace
        from app.runtime.social_snapshot import prepare_activity_social_context
        from app.runtime.social.langgraph_actions import active_world_character
        refreshed = prepare_activity_social_context(ctx, active_actor=active_world_character, counterpart_id=counterpart_id)
        previous = getattr(ctx, "social_context", None)
        current = getattr(refreshed, "social_context", None)
        if previous is not None and current is not None:
            refreshed = replace(refreshed, social_context=replace(current, receipts=previous.receipts))
        return refreshed

    def validate_candidate_relationships(self, db, profile, candidates):
        from app.runtime.social.feed_relationship_context import validate
        if profile.world_character.feed_runtime_mode == "topic_recommendation_v1":
            validate(db, profile, candidates)

    def refresh_candidate_relationships(self, db, profile, candidates):
        from app.runtime.social.feed_relationship_context import refresh
        return refresh(db, profile, candidates)

    @property
    def thought_enabled(self):
        from app.config import settings
        return settings.ACTIVITY_THOUGHT_POLICY == "thought_v1"

    llm_deferred = DirectLlmDeferred
    llm_error = DirectLlmError
    llm_json_error = DirectLlmJsonError
    proposals = activity_proposal_runtime
    executions = WorldFeedExecutions()
    publishing = agent_tool_actions
    social_apply = world_feed_social_apply
    new_tracker = staticmethod(RunLlmTracker)
    default_provider = staticmethod(DirectFeedReactionProvider)
    observe_source = staticmethod(observe_source)
    record_activity_thought = staticmethod(record_activity_thought)
    record_declared_subjective_context = staticmethod(
        record_declared_subjective_context
    )

    def active_world(
        self, db: Session, character_id: str
    ) -> CharacterActiveWorld | None:
        return db.get(CharacterActiveWorld, character_id)

    def search_references(self, db: Session) -> WorldFeedQueries:
        return WorldFeedQueries(db)


async def run_world_keyword_feed(
    ctx: WorldFeedContext, *, provider: FeedReactionProvider | None = None
) -> dict[str, Any]:
    from app.runtime.social_snapshot import prepare_activity_social_context, with_social_receipts
    from app.runtime.social.langgraph_actions import active_world_character
    ctx = prepare_activity_social_context(ctx, active_actor=active_world_character)
    try:
        result = await service.run_world_keyword_feed(ctx, workflows=RuntimeWorldFeedWorkflows(), provider=provider)
    finally:
        from app.runtime.relationships.social_metrics import settle_activity
        settle_activity(ctx)
    return with_social_receipts(ctx, result)
