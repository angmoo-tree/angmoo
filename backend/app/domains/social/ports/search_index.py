"""The narrow search capability consumed by the social application."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.domains.runtime.public import SearchIndexHit


@runtime_checkable
class SocialSearchIndexPort(Protocol):
    def search(
        self,
        *,
        world_id: str,
        query: str,
        limit: int,
    ) -> tuple[SearchIndexHit, ...]: ...


__all__ = ["SocialSearchIndexPort"]
