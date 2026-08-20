"""Storage-neutral text-search projection boundary."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping, Protocol, runtime_checkable


@dataclass(frozen=True)
class SearchIndexDocument:
    document_id: str
    world_id: str
    kind: str
    text: str
    metadata: Mapping[str, str]
    character_id: str | None = None
    counterparty_id: str | None = None
    source_id: str | None = None
    source_event_id: str | None = None
    occurred_at: str | None = None
    searchable: bool = True


@dataclass(frozen=True)
class SearchIndexHit:
    document_id: str
    score: float
    snippet: str | None = None
    world_id: str | None = None
    kind: str | None = None
    character_id: str | None = None
    counterparty_id: str | None = None
    source_id: str | None = None
    source_event_id: str | None = None
    occurred_at: str | None = None
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SearchIndexQuery:
    world_id: str
    text: str
    limit: int = 20
    character_id: str | None = None
    counterparty_id: str | None = None
    kinds: tuple[str, ...] = ()


@dataclass(frozen=True)
class SearchIndexDoctor:
    database_path: str
    generation: str
    schema_version: int
    fts5_available: bool
    integrity_check: str
    document_count: int
    indexed_document_count: int
    digest: str
    digest_matches: bool
    healthy: bool
    tokenizer_strategy: str


@runtime_checkable
class SearchIndexPort(Protocol):
    def upsert(self, document: SearchIndexDocument) -> None: ...

    def remove(self, *, document_id: str) -> None: ...

    def search(
        self,
        *,
        world_id: str,
        query: str,
        limit: int,
    ) -> tuple[SearchIndexHit, ...]: ...


@runtime_checkable
class RebuildableSearchIndexPort(SearchIndexPort, Protocol):
    """Projection-specific operations that current search does not yet require."""

    def search_scoped(self, query: SearchIndexQuery) -> tuple[SearchIndexHit, ...]: ...

    def rebuild(self, documents: Iterable[SearchIndexDocument]) -> SearchIndexDoctor: ...

    def doctor(self) -> SearchIndexDoctor: ...


__all__ = [
    "RebuildableSearchIndexPort",
    "SearchIndexDoctor",
    "SearchIndexDocument",
    "SearchIndexHit",
    "SearchIndexPort",
    "SearchIndexQuery",
]
