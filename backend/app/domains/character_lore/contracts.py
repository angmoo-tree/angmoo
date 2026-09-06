"""Document chunk values and embedding credential material used by lore."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from sqlalchemy.orm import Session

from app.domains.character_lore.constants import EMBEDDING_MODEL


@dataclass(frozen=True)
class LoreChunkDraft:
    section_hint: str | None
    text: str
    content_hash: str


@dataclass(frozen=True)
class RetrievedLoreChunk:
    id: str
    source_id: str
    source_filename: str
    section_hint: str | None
    text: str
    distance: float


@dataclass(frozen=True)
class LoreRetrievalResult:
    mode: str
    chunks: tuple[RetrievedLoreChunk, ...] = ()
    error_message: str | None = None

    @property
    def chunk_ids(self) -> list[str]:
        return [chunk.id for chunk in self.chunks]


@dataclass(frozen=True)
class _GoogleEmbeddingCredential:
    api_key: str
    credential_id: str
    key_fingerprint: str | None
    provider: str
    model: str = EMBEDDING_MODEL


class LoreOwner(Protocol):
    id: str


class LoreRankedSource(Protocol):
    filename: str


class LoreRankedChunk(Protocol):
    """Read-only ranking input supplied by the caller's loaded lore rows."""

    id: str
    source_id: str
    source: LoreRankedSource | None
    section_hint: str | None
    text: str
    usage_count: int
    last_used_at: datetime | None
    chunk_index: int


class LoreCharacter(Protocol):
    """The caller Session's attached Character view; Lore does not own its table."""

    id: str
    owner_id: str
    deleted_at: datetime | None
    name: str
    persona_summary: str
    personality: str
    speech_style: str
    worldview: str
    topic_preferences: str


class LoreEmbeddingContext(Protocol):
    credential_id: str
    key_fingerprint: str | None
    character_id: str | None
    agent_run_id: str | None
    node: str
    lane: str
    provider: str
    model: str


class LoreEmbeddingTracker(Protocol):
    """An existing run tracker is passed through without copying or resetting it."""

    def next_provider_call_order(self) -> int: ...


class LoreTrackedEmbedding(Protocol):
    def __call__(
        self,
        api_key: str,
        text: str,
        *,
        context: LoreEmbeddingContext,
        tracker: LoreEmbeddingTracker,
    ) -> Awaitable[list[float]]: ...


class LoreEmbeddingContextFactory(Protocol):
    def __call__(
        self,
        *,
        credential_id: str,
        key_fingerprint: str | None,
        character_id: str,
        agent_run_id: str,
        node: str,
        lane: str,
        provider: str,
        model: str,
    ) -> LoreEmbeddingContext: ...


class LoreRecentTopics(Protocol):
    def __call__(self, db: Session, *, character_id: str) -> str: ...


@dataclass(frozen=True)
class LoreWorkflows:
    """Actual foreign lookups and transport; no new Session or implicit defaults."""

    get_character: Callable[[Session, str], LoreCharacter | None]
    embedding_credential: Callable[[Session, str], _GoogleEmbeddingCredential]
    api_key: Callable[[Session, str], str]
    embed_text: Callable[[str, str], list[float]]
    embed_text_tracked: LoreTrackedEmbedding
    embedding_context: LoreEmbeddingContextFactory
    recent_topics: LoreRecentTopics
