"""Storage-neutral text-search projection boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol, runtime_checkable


@dataclass(frozen=True)
class SearchIndexDocument:
    document_id: str
    world_id: str
    kind: str
    text: str
    metadata: Mapping[str, str]


@dataclass(frozen=True)
class SearchIndexHit:
    document_id: str
    score: float
    snippet: str | None = None


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


__all__ = ["SearchIndexDocument", "SearchIndexHit", "SearchIndexPort"]
