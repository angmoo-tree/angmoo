"""Compatibility adapter around the current search implementation callbacks."""

from __future__ import annotations

from collections.abc import Callable

from app.domains.runtime.ports.search_index import (
    SearchIndexDocument,
    SearchIndexHit,
)


class CallbackSearchIndexAdapter:
    def __init__(
        self,
        *,
        upsert: Callable[[SearchIndexDocument], None],
        remove: Callable[[str], None],
        search: Callable[[str, str, int], tuple[SearchIndexHit, ...]],
    ) -> None:
        self._upsert = upsert
        self._remove = remove
        self._search = search

    def upsert(self, document: SearchIndexDocument) -> None:
        self._upsert(document)

    def remove(self, *, document_id: str) -> None:
        self._remove(document_id)

    def search(
        self,
        *,
        world_id: str,
        query: str,
        limit: int,
    ) -> tuple[SearchIndexHit, ...]:
        return self._search(world_id, query, limit)


__all__ = ["CallbackSearchIndexAdapter"]
