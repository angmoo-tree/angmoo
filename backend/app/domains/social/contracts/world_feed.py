"""Attached World feed facts and search results; foreign values remain read-only."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Protocol
from app.domains.social.models.feed import WorldCharacterFeedObservation
from app.domains.social.models.posts import Post
from app.domains.social.schemas import feed as feed_schemas


class FeedWorld(Protocol):
    @property
    def name(self) -> str: ...
    @property
    def tagline(self) -> str | None: ...
    @property
    def id(self) -> str: ...
    @property
    def status(self) -> str: ...
    @property
    def readiness_status(self) -> str: ...
    @property
    def contract_hash(self) -> str: ...
    @property
    def timezone(self) -> str: ...


class FeedWorldCharacter(Protocol):
    @property
    def local_profile(self) -> dict[str, object] | None: ...
    @property
    def id(self) -> str: ...
    @property
    def status(self) -> str: ...
    @property
    def feed_runtime_mode(self) -> str: ...
    @property
    def character_id(self) -> str: ...
    @property
    def membership_id(self) -> str: ...
    @property
    def world_id(self) -> str: ...
    @property
    def character_contract_hash(self) -> str: ...
    @property
    def world_contract_hash(self) -> str: ...
    @property
    def autonomous_enabled(self) -> bool: ...


class FeedMembership(Protocol):
    @property
    def world_id(self) -> str: ...
    @property
    def user_id(self) -> str: ...
    @property
    def status(self) -> str: ...


class FeedCharacter(Protocol):
    @property
    def name(self) -> str: ...
    @property
    def persona_summary(self) -> str | None: ...
    @property
    def speech_style(self) -> str | None: ...
    @property
    def id(self) -> str: ...
    @property
    def owner_id(self) -> str: ...
    @property
    def deleted_at(self) -> datetime | None: ...


class FeedCommunityProfile(Protocol):
    @property
    def character_contract_hash(self) -> str: ...
    @property
    def world_contract_hash(self) -> str: ...
    @property
    def visible_summary(self) -> str: ...
    @property
    def core_interests(self) -> list[str]: ...
    @property
    def adjacent_interests(self) -> list[str]: ...
    @property
    def avoid_topics(self) -> list[str]: ...
    @property
    def discovery_openness(self) -> int: ...
    @property
    def search_keywords(self) -> list[str]: ...
    @property
    def action_profile(self) -> dict[str, object]: ...


class FeedOwner(Protocol):
    @property
    def id(self) -> str: ...


class FeedPost(Protocol):
    @property
    def id(self) -> str: ...
    @property
    def author_character_id(self) -> str | None: ...


@dataclass(frozen=True)
class ReadySearchProfile:
    world: FeedWorld
    world_character: FeedWorldCharacter
    membership: FeedMembership
    character: FeedCharacter
    profile: FeedCommunityProfile
    keywords: tuple[str, ...]
    avoid_topics: tuple[str, ...]
    action_profile: dict[str, object]
    imported_world_runtime_locked: bool


@dataclass(frozen=True)
class KeywordClaim:
    cursor_offset: int
    keywords: tuple[str, str]
    duplicate_cycle: bool
    previous_summary: dict[str, object] | None


@dataclass(frozen=True)
class CandidateSearchResult:
    candidates: tuple[feed_schemas.WorldFeedCandidateRead, ...]
    raw_candidate_count: int
    filtered_candidate_count: int
    query_latency_ms: int


@dataclass(frozen=True)
class ObservationClaimResult:
    candidates: tuple[feed_schemas.WorldFeedCandidateRead, ...]
    observations: tuple[WorldCharacterFeedObservation, ...]
    claim_conflict_count: int


class WorldFeedReferences(Protocol):
    def world_character(self, identity: str) -> FeedWorldCharacter | None: ...
    def character(self, identity: str) -> FeedCharacter | None: ...
    def membership(self, identity: str) -> FeedMembership | None: ...
    def world(self, identity: str) -> FeedWorld | None: ...
    def ready_profile(self, world_character_id: str) -> FeedCommunityProfile | None: ...
    def character_hash(self, character: FeedCharacter) -> str: ...
    def imported_lineage(self, world_id: str) -> str | None: ...
    def candidate_rows(
        self, profile: ReadySearchProfile
    ) -> Callable[[tuple[str, ...]], dict[str, tuple[Post, FeedWorldCharacter]]]: ...
    def post_context(self, post_ids: list[str]) -> list[tuple[str, str, str]]: ...
