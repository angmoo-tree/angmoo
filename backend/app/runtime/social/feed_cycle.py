"""Bind a World feed cycle to the existing resident context and owner operations."""

from __future__ import annotations
from typing import Any
from sqlalchemy.orm import Session
from app.domains.world_characters.models import CharacterActiveWorld
from app.domains.social.contracts.feed_execution import FeedReactionProvider
from app.domains.social.service import feed_cycle as service
from app.runtime.resident.context import LangGraphResidentContext
from app.runtime.social.world_feed_queries import WorldFeedQueries
from app.runtime.activity_proposals import composition as activity_proposal_runtime
from app.runtime.social import world_feed_actions as world_feed_social_apply
from app.runtime.social.observations import observe_source
from app.runtime.social.subjective_composition import record_declared_subjective_context
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
    ctx: LangGraphResidentContext, *, provider: FeedReactionProvider | None = None
) -> dict[str, Any]:
    return await service.run_world_keyword_feed(
        ctx, workflows=RuntimeWorldFeedWorkflows(), provider=provider
    )
