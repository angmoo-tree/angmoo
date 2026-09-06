"""Resident planner/writer wire schemas with the original validation contract.

Private class names are retained because they are also provider schema titles.
The runtime supplies IO and graph execution; these models validate its values.
"""

from __future__ import annotations

from datetime import date
from typing import Literal
from pydantic import BaseModel, Field, model_validator
from app.contracts.action_subjective_context import (
    ActionEmotionLabel,
    ActionMotivationKind,
)
from app.domains.routines.policies.topic_arc_roles import _validate_topic_arc_step_roles


_TOPIC_ARC_SCHEMA_VERSION = 1


class _PlannedAction(BaseModel):
    scope: Literal["feed", "inbox", "relationship"]
    action_type: Literal["reply", "like", "repost", "follow", "unfollow"]
    post_id: str | None = Field(default=None, max_length=64)
    notification_id: int | None = None
    notification_type: Literal["reply", "mention", "joint_activity_started"] | None = (
        None
    )
    target_type: Literal["character"] | None = None
    target_id: str | None = Field(default=None, max_length=64)
    brief: str | None = Field(default=None, max_length=600)
    motivation_kind: ActionMotivationKind | None = None
    motivation_text: str | None = Field(default=None, max_length=280)
    emotion_label: ActionEmotionLabel | None = None
    emotion_text: str | None = Field(default=None, max_length=280)
    emotion_intensity: int | None = Field(default=None, ge=0, le=100)
    conversation_judgment: (
        Literal[
            "continue_reply",
            "closing_reply",
            "ack_without_reply",
            "no_action_closed",
        ]
        | None
    ) = None
    conversation_reason: str | None = Field(default=None, max_length=500)


class _TopicArcStep(BaseModel):
    role: Literal["standalone", "setup", "development", "conclusion"]
    brief: str = Field(min_length=1, max_length=600)
    target_date: str | None = Field(default=None, max_length=10)
    relative_time_original: str | None = Field(default=None, max_length=24)


class _TopicArcDraft(BaseModel):
    arc_title: str = Field(min_length=1, max_length=200)
    steps: list[_TopicArcStep] = Field(min_length=1, max_length=5)


class _TopicArcPayload(_TopicArcDraft):
    schema_version: int = _TOPIC_ARC_SCHEMA_VERSION
    arc_id: str = Field(min_length=1, max_length=160)
    arc_source: Literal["independent", "post_seed"]
    topic_key: str | None = Field(default=None, max_length=80)
    source_post_id: str | None = Field(default=None, max_length=64)
    next_step_index: int = Field(default=0, ge=0, le=5)
    status: Literal["active", "completed"] = "active"
    last_post_id: str | None = Field(default=None, max_length=64)
    created_kst_date: str | None = Field(default=None, max_length=10)
    carryover_status: Literal["active", "completed", "expired"] = "active"

    @model_validator(mode="after")
    def validate_payload(self) -> "_TopicArcPayload":
        _validate_topic_arc_step_roles(self.steps, arc_source=self.arc_source)
        if self.next_step_index > len(self.steps):
            raise ValueError("next_step_index is outside topic arc steps")
        if self.status == "active" and self.next_step_index >= len(self.steps):
            raise ValueError("active topic arc must have a remaining step")
        return self


class _WritingPlan(BaseModel):
    mode: Literal[
        "none",
        "post_seed",
        "independent",
        "arc_continuation",
        "owner_feed_cue",
        "relationship_point",
    ] = "none"
    source_post_id: str | None = Field(default=None, max_length=64)
    topic_key: str | None = Field(default=None, max_length=80)
    feed_cue_id: int | None = None
    brief: str | None = Field(default=None, max_length=800)
    motivation_kind: ActionMotivationKind | None = None
    motivation_text: str | None = Field(default=None, max_length=280)
    emotion_label: ActionEmotionLabel | None = None
    emotion_text: str | None = Field(default=None, max_length=280)
    emotion_intensity: int | None = Field(default=None, ge=0, le=100)
    topic_arc: _TopicArcDraft | None = None
    active_step: _TopicArcStep | None = None

    @model_validator(mode="after")
    def validate_writing(self) -> "_WritingPlan":
        if self.mode != "none" and not (self.brief or "").strip():
            raise ValueError("writing brief is required")
        return self


class _ActionPlan(BaseModel):
    selection_reason: str = Field(min_length=1, max_length=1000)
    feed_actions: list[_PlannedAction] = Field(default_factory=list, max_length=4)
    inbox_actions: list[_PlannedAction] = Field(default_factory=list, max_length=6)
    relationship_actions: list[_PlannedAction] = Field(
        default_factory=list, max_length=1
    )
    writing: _WritingPlan = Field(default_factory=_WritingPlan)


class _FeedPlannerAction(BaseModel):
    item_index: int = Field(ge=0, le=29)
    action_type: Literal["reply", "like", "repost"]
    brief: str | None = Field(default=None, max_length=600)
    motivation_kind: ActionMotivationKind | None = None
    motivation_text: str | None = Field(default=None, max_length=280)
    emotion_label: ActionEmotionLabel | None = None
    emotion_text: str | None = Field(default=None, max_length=280)
    emotion_intensity: int | None = Field(default=None, ge=0, le=100)


class _InboxPlannerAction(BaseModel):
    item_index: int = Field(ge=0, le=9)
    action_type: Literal["reply", "like", "follow"]
    brief: str | None = Field(default=None, max_length=600)
    motivation_kind: ActionMotivationKind | None = None
    motivation_text: str | None = Field(default=None, max_length=280)
    emotion_label: ActionEmotionLabel | None = None
    emotion_text: str | None = Field(default=None, max_length=280)
    emotion_intensity: int | None = Field(default=None, ge=0, le=100)


class _InboxConversationDecision(BaseModel):
    item_index: int = Field(ge=0, le=9)
    conversation_judgment: Literal[
        "continue_reply",
        "closing_reply",
        "ack_without_reply",
        "no_action_closed",
    ]
    conversation_reason: str | None = Field(default=None, max_length=500)


class _FeedPlannerWriting(BaseModel):
    mode: Literal["none", "post_seed"] = "none"
    source_item_index: int | None = Field(default=None, ge=0, le=29)
    brief: str | None = Field(default=None, max_length=800)
    motivation_kind: ActionMotivationKind | None = None
    motivation_text: str | None = Field(default=None, max_length=280)
    emotion_label: ActionEmotionLabel | None = None
    emotion_text: str | None = Field(default=None, max_length=280)
    emotion_intensity: int | None = Field(default=None, ge=0, le=100)
    topic_arc: _TopicArcDraft | None = None


class _FeedActionPlan(BaseModel):
    selection_reason: str | None = Field(default="", max_length=1000)
    feed_actions: list[_FeedPlannerAction] = Field(default_factory=list, max_length=4)
    writing: _FeedPlannerWriting = Field(default_factory=_FeedPlannerWriting)


class _InboxActionPlan(BaseModel):
    selection_reason: str | None = Field(default="", max_length=1000)
    inbox_actions: list[_InboxPlannerAction] = Field(default_factory=list, max_length=6)
    conversation_decisions: list[_InboxConversationDecision] = Field(
        default_factory=list, max_length=10
    )


class _RelationshipActionPlan(BaseModel):
    decision: Literal["none", "follow", "unfollow_watch", "unfollow"] = "none"
    target_character_id: str | None = Field(default=None, max_length=64)
    reason_tag: str | None = Field(default=None, max_length=80)
    evidence_summary: str | None = Field(default=None, max_length=800)
    motivation_kind: ActionMotivationKind | None = None
    motivation_text: str | None = Field(default=None, max_length=280)
    emotion_label: ActionEmotionLabel | None = None
    emotion_text: str | None = Field(default=None, max_length=280)
    emotion_intensity: int | None = Field(default=None, ge=0, le=100)
    relationship_actions: list[_PlannedAction] = Field(
        default_factory=list, max_length=1
    )


class _IndependentWritingChoice(BaseModel):
    mode: Literal["none", "independent", "relationship_point"] = "none"
    topic_key: str | None = Field(default=None, max_length=80)
    relationship_point_id: int | None = None
    source_mix: Literal["none", "feed_seed", "relationship_point"] = "none"
    mention_target_handle: str | None = Field(default=None, max_length=80)
    brief: str | None = Field(default=None, max_length=800)
    motivation_kind: ActionMotivationKind | None = None
    motivation_text: str | None = Field(default=None, max_length=280)
    emotion_label: ActionEmotionLabel | None = None
    emotion_text: str | None = Field(default=None, max_length=280)
    emotion_intensity: int | None = Field(default=None, ge=0, le=100)
    topic_arc: _TopicArcDraft | None = None


class _IndependentWritingPlan(BaseModel):
    selection_reason: str | None = Field(default="", max_length=1000)
    writing: _IndependentWritingChoice = Field(
        default_factory=_IndependentWritingChoice
    )


class _FeedSeedSelection(BaseModel):
    mode: Literal["none", "use_seed"] = "none"
    post_id: str | None = Field(default=None, max_length=64)
    author_character_id: str | None = Field(default=None, max_length=64)
    author_handle: str | None = Field(default=None, max_length=80)
    seed_brief: str | None = Field(default=None, max_length=800)
    use_reason: str | None = Field(default=None, max_length=500)
    mention_required: bool = False


class _IndependentTopicComposition(BaseModel):
    source: Literal[
        "owner_feed_cue",
        "base_topic",
        "relationship_point",
        "action_continuation",
    ] = "base_topic"
    topic_key: str | None = Field(default=None, max_length=80)
    relationship_point_id: int | None = None
    writing_form: Literal["thought", "community_observation", "monologue", "action"] = (
        "thought"
    )
    action_step_count: int = Field(default=1, ge=1, le=3)
    brief: str = Field(min_length=1, max_length=1000)
    motivation_kind: ActionMotivationKind | None = None
    motivation_text: str | None = Field(default=None, max_length=280)
    emotion_label: ActionEmotionLabel | None = None
    emotion_text: str | None = Field(default=None, max_length=280)
    emotion_intensity: int | None = Field(default=None, ge=0, le=100)
    use_post_seed: bool = False
    seed_post_id: str | None = Field(default=None, max_length=64)
    mention_target_handle: str | None = Field(default=None, max_length=80)
    selection_reason: str | None = Field(default=None, max_length=600)


class _ReplyText(BaseModel):
    scope: Literal["feed", "inbox"]
    index: int = Field(ge=0, le=8)
    post_id: str = Field(min_length=1, max_length=64)
    body: str = Field(min_length=1, max_length=1000)


class _PersonaWriting(BaseModel):
    reply_bodies: list[_ReplyText] = Field(default_factory=list, max_length=9)
    post_title: str | None = Field(default=None, max_length=160)
    post_body: str | None = Field(default=None, max_length=4000)


class _ReplyTaskText(BaseModel):
    task_id: str = Field(min_length=1, max_length=180)
    body: str | None = Field(default=None, max_length=1000)
    proposal_decision: Literal["accept", "reject", "counter"] | None = None
    counter_activity_seed: str | None = Field(default=None, max_length=500)
    counter_place_key: str | None = Field(default=None, max_length=64)
    counter_target_daypart: (
        Literal["dawn", "morning", "afternoon", "evening"] | None
    ) = None
    counter_date_policy: Literal["exact", "earliest_available"] | None = None
    counter_target_date: date | None = None

    @model_validator(mode="after")
    def validate_counter_contract(self) -> "_ReplyTaskText":
        counter_values = (
            self.counter_activity_seed,
            self.counter_place_key,
            self.counter_target_daypart,
            self.counter_date_policy,
            self.counter_target_date,
        )
        if self.proposal_decision != "counter":
            if any(value is not None for value in counter_values):
                raise ValueError("counter fields require proposal_decision=counter")
            return self
        if (
            not self.counter_activity_seed
            or self.counter_target_daypart is None
            or self.counter_date_policy is None
            or (
                self.counter_date_policy == "exact" and self.counter_target_date is None
            )
        ):
            raise ValueError("counter response fields are incomplete")
        return self


class _ReplyWriterOutput(BaseModel):
    replies: list[_ReplyTaskText] = Field(default_factory=list, max_length=9)


class _PostWriterOutput(BaseModel):
    task_id: str | None = Field(default=None, max_length=180)
    post_title: str | None = Field(default=None, max_length=160)
    post_body: str | None = Field(default=None, max_length=4000)


class _PostWriterPlannerOutput(BaseModel):
    task_id: str | None = Field(default=None, max_length=180)
    time_framing: str | None = Field(default=None, max_length=160)
    topic_focus: str | None = Field(default=None, max_length=400)
    title_direction: str | None = Field(default=None, max_length=240)
    body_beats: list[str] = Field(default_factory=list, max_length=5)
    tone_notes: str | None = Field(default=None, max_length=300)
    constraints: list[str] = Field(default_factory=list, max_length=8)


class _LoreQueryRewriteOutput(BaseModel):
    query: str | None = Field(default=None, max_length=500)
    focus_terms: list[str] = Field(default_factory=list, max_length=8)


class _StateWrite(BaseModel):
    mood: str = Field(default="neutral", max_length=80)
    summary: str = Field(min_length=1, max_length=2000)
    memory_note: str = Field(default="", max_length=2000)
    observation_note: str | None = Field(default=None, max_length=1000)
