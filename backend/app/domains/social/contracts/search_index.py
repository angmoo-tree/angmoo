"""The narrow search capability consumed by the social application."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


class SocialSearchHit(Protocol):
    @property
    def document_id(self) -> str: ...
    @property
    def world_id(self) -> str | None: ...
    @property
    def kind(self) -> str | None: ...


@runtime_checkable
class SocialSearchIndexPort(Protocol):
    def search(
        self,
        *,
        world_id: str,
        query: str,
        limit: int,
    ) -> tuple[SocialSearchHit, ...]: ...


__all__ = ["SocialSearchIndexPort"]
