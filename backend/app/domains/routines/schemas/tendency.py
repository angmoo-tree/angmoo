"""Structured provider output for community tendency analysis."""
from pydantic import BaseModel, Field
from typing import Literal
from app.domains.routines.constants import TENDENCY_INDEPENDENT_TOPIC_COUNT


class _TendencyRangePayload(BaseModel):
    min: int = Field(ge=0, le=6)
    max: int = Field(ge=0, le=6)
    label: str = Field(min_length=1, max_length=40)
    note: str = Field(min_length=1, max_length=240)


class _TendencyActionRangesPayload(BaseModel):
    post: _TendencyRangePayload
    reply: _TendencyRangePayload
    like: _TendencyRangePayload
    repost: _TendencyRangePayload
    follow: _TendencyRangePayload
    unfollow: _TendencyRangePayload
    observe: _TendencyRangePayload


class _IndependentPostInitiativePayload(BaseModel):
    level: Literal["very_low", "low", "medium", "high", "very_high"]
    tick_probability: float = Field(ge=0.03, le=0.45)


class _IndependentPostTopicPayload(BaseModel):
    key: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=80)
    prompt: str = Field(min_length=1, max_length=300)


class _PlannerTendencyProfilePayload(BaseModel):
    feed_seed_interest_criteria: str = Field(min_length=1)
    independent_post_initiative: _IndependentPostInitiativePayload
    independent_post_topics: list[_IndependentPostTopicPayload] = Field(
        min_length=TENDENCY_INDEPENDENT_TOPIC_COUNT,
        max_length=TENDENCY_INDEPENDENT_TOPIC_COUNT,
    )


class _TendencyAnalysisPayload(BaseModel):
    summary: str = Field(min_length=1, max_length=900)
    action_ranges: _TendencyActionRangesPayload
    planner_tendency_profile: _PlannerTendencyProfilePayload
