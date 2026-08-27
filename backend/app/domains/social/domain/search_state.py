"""Domain vocabulary for the rebuildable P5 search projection."""

from __future__ import annotations

from enum import StrEnum


class SocialSearchState(StrEnum):
    READY = "search_ready"
    REBUILDING = "search_rebuilding"
    SCHEMA_MISMATCH = "search_schema_mismatch"
    DIGEST_STALE = "search_digest_stale"
    UNAVAILABLE = "search_unavailable"


class SocialSearchUnavailable(RuntimeError):
    def __init__(self, state: SocialSearchState):
        self.state = state
        super().__init__(state.value)


__all__ = ["SocialSearchState", "SocialSearchUnavailable"]
