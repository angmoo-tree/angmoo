"""Read-only resident context and lazy collaboration for a World feed cycle.

The actual context, tracker and ORM records retain their identity. Constructing
the runtime binding performs no SQL, provider request, or transaction boundary.
"""

from __future__ import annotations
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any, Protocol
from sqlalchemy.orm import Session
from app.domains.social.schemas import feed as schemas
from app.domains.social.schemas.community import (
    PostLikeCreate,
    TimelineReplyCreate,
    FollowCreate,
)
from app.domains.social.contracts.action_scope import ActionIdentity
from app.domains.social.contracts.world_feed import (
    ReadySearchProfile,
    WorldFeedReferences,
)
from app.domains.social.contracts.search_index import SocialSearchIndexPort
from app.domains.social.contracts.search_state import SocialSearchState
from app.domains.social.contracts.subjective_persistence import (
    SubjectiveExecution,
    SubjectiveEvent,
)
from app.domains.social.contracts.subjective_context import ActionSubjectiveContextV1
from app.domains.social.contracts.observations import (
    SocialObservationResult,
    ObservationLane,
)


class FeedActivityPolicy(Protocol):
    @property
    def allowed_actions(self) -> tuple[str, ...]: ...


class FeedProviderCredential(Protocol):
    """The original attached credential passed unchanged to its owner resolver."""

    @property
    def id(self) -> str: ...
    @property
    def provider(self) -> str: ...
    @property
    def model(self) -> str: ...
    @property
    def key_fingerprint(self) -> str | None: ...
    @property
    def enabled(self) -> bool: ...
    @property
    def owner_id(self) -> str: ...
    @property
    def character_id(self) -> str | None: ...
    @property
    def purpose(self) -> str: ...
    @property
    def encrypted_api_key(self) -> str | None: ...


class WorldFeedContext(Protocol):
    @property
    def db(self) -> Session: ...
    @property
    def character(self) -> ActionIdentity: ...
    @property
    def run_id(self) -> str: ...
    @property
    def session_key(self) -> str: ...
    @property
    def run_started_at(self) -> datetime: ...
    @property
    def run_mode(self) -> str: ...
    @property
    def activity_policy(self) -> FeedActivityPolicy: ...
    @property
    def social_search_index(self) -> SocialSearchIndexPort | None: ...
    @property
    def social_search_state(self) -> SocialSearchState: ...
    @property
    def credential(self) -> FeedProviderCredential: ...
    @property
    def on_rate_limit_wait(self) -> Callable[[float], Awaitable[None]] | None: ...


class ReactionTracker(Protocol):
    def summary(self) -> dict[str, Any]: ...


class ActiveFeedWorld(Protocol):
    @property
    def world_character_id(self) -> str: ...


class FeedExecution(SubjectiveExecution, Protocol):
    @property
    def result(self) -> dict[str, Any] | None: ...


class FeedProposalEligibility(Protocol):
    @property
    def eligible(self) -> bool: ...


class FeedAppliedAction(Protocol):
    @property
    def event(self) -> SubjectiveEvent: ...
    @property
    def proposal(self) -> ActionIdentity | None: ...


class FeedFollowResult(Protocol):
    @property
    def target(self) -> ActionIdentity: ...


class FeedProposalWorkflows(Protocol):
    def proposal_eligibility(
        self,
        db: Session,
        *,
        actor_world_character_id: str,
        target_post_id: str,
        now: datetime,
    ) -> FeedProposalEligibility: ...
    def validate_preview(
        self,
        db: Session,
        *,
        preview: schemas.JointActivityProposalPreview,
        world_id: str,
        proposer_world_character_id: str,
        target_post_id: str,
        now: datetime,
    ) -> object: ...


class FeedExecutionWorkflows(Protocol):
    def get_public_action_execution_by_signature(
        self, db: Session, signature: str
    ) -> FeedExecution | None: ...
    def create_public_action_execution(
        self,
        db: Session,
        *,
        run_id: str,
        character_id: str,
        signature: str,
        scope: str,
        action_type: str,
        target_post_id: str | None = None,
        target_profile_type: str | None = None,
        target_profile_id: str | None = None,
        brief_hash: str | None = None,
        world_id: str | None = None,
        actor_world_character_id: str | None = None,
        feed_observation_id: str | None = None,
        interaction_intent: str | None = None,
        comment_purpose: str | None = None,
    ) -> FeedExecution: ...
    def mark_public_action_execution_finished(
        self,
        db: Session,
        execution: FeedExecution,
        *,
        status: str,
        result: dict[str, Any] | None = None,
        failure_class: str | None = None,
    ) -> FeedExecution: ...


class FeedPublishingWorkflows(Protocol):
    def like_agent_tool_post(
        self, db: Session, session_key: str, post_id: str, data: PostLikeCreate
    ) -> ActionIdentity: ...
    def reply_agent_tool_post(
        self, db: Session, session_key: str, post_id: str, data: TimelineReplyCreate
    ) -> ActionIdentity: ...
    def repost_agent_tool_post(
        self, db: Session, session_key: str, post_id: str, data: PostLikeCreate
    ) -> ActionIdentity: ...
    def follow_agent_tool_profile(
        self, db: Session, session_key: str, data: FollowCreate
    ) -> FeedFollowResult: ...


class FeedActionWorkflows(Protocol):
    def apply_successful_world_feed_action(
        self,
        db: Session,
        *,
        profile: ReadySearchProfile,
        candidate: schemas.WorldFeedCandidateRead,
        decision: schemas.FeedReactionDecision,
        draft: schemas.FeedCommentDraft | schemas.JointActivityProposalPreview | None,
        action_result: dict[str, object],
        execution: FeedExecution,
        occurred_at: datetime,
    ) -> FeedAppliedAction: ...


class WorldFeedWorkflows(Protocol):
    @property
    def llm_deferred(self) -> type[Exception]: ...
    @property
    def llm_error(self) -> type[Exception]: ...
    @property
    def llm_json_error(self) -> type[Exception]: ...
    @property
    def proposals(self) -> FeedProposalWorkflows: ...
    @property
    def executions(self) -> FeedExecutionWorkflows: ...
    @property
    def publishing(self) -> FeedPublishingWorkflows: ...
    @property
    def social_apply(self) -> FeedActionWorkflows: ...
    def new_tracker(self, *, max_calls: int) -> ReactionTracker: ...
    def default_provider(self) -> FeedReactionProvider: ...
    def active_world(
        self, db: Session, character_id: str
    ) -> ActiveFeedWorld | None: ...
    def search_references(self, db: Session) -> WorldFeedReferences: ...
    def observe_source(
        self,
        db: Session,
        *,
        world_id: str,
        observer_world_character_id: str,
        source_social_event_id: str | None,
        source_post_id: str | None,
        lane: ObservationLane,
        observed_at: datetime,
    ) -> SocialObservationResult: ...
    def record_declared_subjective_context(
        self,
        db: Session,
        *,
        execution: FeedExecution,
        event: SubjectiveEvent,
        source_post_id: str | None,
        context: ActionSubjectiveContextV1 | None,
        captured_at: datetime,
    ) -> object: ...


class FeedReactionProvider(Protocol):
    async def plan(
        self,
        *,
        resident_context: WorldFeedContext,
        profile: ReadySearchProfile,
        candidates: tuple[schemas.WorldFeedCandidateRead, ...],
        tracker: ReactionTracker,
        proposal_eligible_indices: frozenset[int] = frozenset(),
    ) -> schemas.FeedReactionDecision: ...

    async def write_comment(
        self,
        *,
        resident_context: WorldFeedContext,
        profile: ReadySearchProfile,
        candidate: schemas.WorldFeedCandidateRead,
        decision: schemas.FeedReactionDecision,
        tracker: ReactionTracker,
    ) -> schemas.FeedCommentDraft | schemas.JointActivityProposalPreview: ...
