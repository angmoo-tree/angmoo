from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


FeedAction = Literal["like", "comment", "repost", "follow"]
FeedInteractionIntent = Literal[
    "ordinary_comment",
    "joint_activity_proposal",
    "proposal_response",
]
FeedCommentPurpose = Literal[
    "question",
    "advice",
    "empathy",
    "encouragement",
    "information",
    "humor",
    "disagreement",
    "competition",
    "observation",
]
FeedNoActionReason = Literal[
    "no_searchable_keyword",
    "no_candidate",
    "no_allowed_action",
    "model_abstained",
    "proposal_ineligible",
    "proposal_apply_not_ready",
    "target_stale",
    "writer_invalid",
    "search_rebuilding",
    "search_schema_mismatch",
    "search_digest_stale",
    "search_unavailable",
]


class WorldFeedSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class WorldFeedCandidateRead(WorldFeedSchema):
    candidate_index: int = Field(ge=0, le=7)
    post_id: str
    author_world_character_id: str
    author_character_id: str
    author_name: str
    title: str
    body_preview: str
    topic_signature: str
    created_at: datetime
    world_local_datetime: str
    age_seconds: int = Field(ge=0)
    age_bucket: Literal["recent", "days_old", "weeks_old", "older"]
    matched_keywords: list[str]
    matched_fields: list[Literal["title", "body", "topic_signature"]]
    rank_score: float
    allowed_actions: list[FeedAction]


class FeedReactionDecision(WorldFeedSchema):
    selected_candidate_index: int | None = Field(default=None, ge=0, le=7)
    selected_action: FeedAction | None = None
    interaction_intent: FeedInteractionIntent | None = None
    comment_purpose: FeedCommentPurpose | None = None
    reason_code: FeedNoActionReason | None = None
    brief: str | None = Field(default=None, max_length=280)

    @model_validator(mode="after")
    def _coherent_decision(self) -> "FeedReactionDecision":
        if self.selected_action is None:
            if self.selected_candidate_index is not None:
                raise ValueError("candidate index must be null for NO_ACTION")
            if self.interaction_intent is not None or self.comment_purpose is not None:
                raise ValueError("intent and purpose must be null for NO_ACTION")
            if self.reason_code is None:
                raise ValueError("NO_ACTION requires a reason code")
            if self.brief is not None:
                raise ValueError("brief must be null for NO_ACTION")
            return self
        if self.selected_candidate_index is None:
            raise ValueError("selected action requires a candidate index")
        if self.reason_code is not None:
            raise ValueError("selected action cannot have a NO_ACTION reason")
        if not (self.brief or "").strip():
            raise ValueError("selected action requires a bounded brief")
        if self.selected_action == "comment":
            if self.interaction_intent not in {
                "ordinary_comment",
                "joint_activity_proposal",
            }:
                raise ValueError("feed comment requires a supported interaction intent")
            if (
                self.interaction_intent == "ordinary_comment"
                and self.comment_purpose is None
            ):
                raise ValueError("ordinary comment requires a purpose")
        elif self.interaction_intent is not None or self.comment_purpose is not None:
            raise ValueError("non-comment action cannot have intent or purpose")
        return self


class FeedCommentDraft(WorldFeedSchema):
    text: str = Field(min_length=1, max_length=500)
    source_post_id: str
    interaction_intent: Literal["ordinary_comment"]
    comment_purpose: FeedCommentPurpose


class JointActivityProposalPreview(WorldFeedSchema):
    text: str = Field(min_length=1, max_length=500)
    source_post_id: str
    activity_seed: str = Field(min_length=1, max_length=500)
    target_world_character_id: str
    place_key: str | None = Field(default=None, max_length=64)
    target_daypart: Literal["dawn", "morning", "afternoon", "evening"]
    date_policy: Literal["exact", "earliest_available"]
    target_date: date | None = None

    @model_validator(mode="after")
    def _coherent_schedule(self) -> "JointActivityProposalPreview":
        if self.date_policy == "exact" and self.target_date is None:
            raise ValueError("exact proposal requires target_date")
        return self


class WorldFeedObservationRead(WorldFeedSchema):
    observation_id: str
    post_id: str
    post_title: str
    author_name: str
    post_created_at: datetime
    status: Literal["claimed", "observed", "retryable_failed"]
    decision_outcome: Literal["not_selected", "action_selected", "no_action"] | None
    selected_action: FeedAction | None
    interaction_intent: FeedInteractionIntent | None
    comment_purpose: FeedCommentPurpose | None
    reason_code: FeedNoActionReason | None
    matched_keywords: list[str]
    matched_fields: list[str]
    rank_score: float
    observed_at: datetime | None


class WorldFeedCycleStatusRead(WorldFeedSchema):
    world_id: str
    world_character_id: str
    feed_runtime_mode: Literal["legacy_latest_v1", "keyword_search_v1"]
    runtime_state: Literal[
        "routine_only_legacy_feed",
        "three_lane_ready",
        "imported_locked",
        "autonomy_disabled",
        "feed_search_degraded",
    ]
    profile_keyword_count: int = Field(ge=0, le=64)
    profile_keywords_ready: bool
    next_keywords: list[str] = Field(max_length=2)
    next_keyword_offset: int = Field(ge=0, le=6)
    last_cycle_key: str | None
    last_cycle_at: datetime | None
    last_run_id: str | None
    last_cycle_summary: dict[str, object] | None
    recent_observations: list[WorldFeedObservationRead]
