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
from app.cruds import agent_runs as agent_run_crud
from app.services import community as community_service
from app.services.feed_reaction_planner import DirectFeedReactionProvider
from app.services.direct_llm import (
    DirectLlmDeferred,
    DirectLlmError,
    DirectLlmJsonError,
    RunLlmTracker,
)


class RuntimeWorldFeedWorkflows:
    llm_deferred = DirectLlmDeferred
    llm_error = DirectLlmError
    llm_json_error = DirectLlmJsonError
    proposals = activity_proposal_runtime
    executions = agent_run_crud
    publishing = community_service
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
