"""Resident planning-history input; metadata is locked by the server skeleton."""

from pydantic import BaseModel, Field


class AgentFeedHistorySanitizeItem(BaseModel):
    post_id: str | None = Field(default=None, max_length=64)
    topic_signature: str | None = Field(default=None, max_length=300)
    novelty_basis: str | None = Field(default=None, max_length=500)
    source_title: str | None = Field(default=None, max_length=160)
    seed_semantic_summary: str | None = Field(default=None, max_length=500)
    own_root_semantic_summary: str | None = Field(default=None, max_length=500)
    interest_reason_summary: str | None = Field(default=None, max_length=500)
    warnings: list[str] = Field(default_factory=list, max_length=5)


class AgentFeedHistorySanitizeCreate(BaseModel):
    consumed_sources: list[AgentFeedHistorySanitizeItem] = Field(
        default_factory=list, max_length=20
    )
    recent_feed_interests: list[AgentFeedHistorySanitizeItem] = Field(
        default_factory=list, max_length=5
    )
    recent_own_root_topics: list[AgentFeedHistorySanitizeItem] = Field(
        default_factory=list, max_length=5
    )
