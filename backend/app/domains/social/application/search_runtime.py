"""Process-local binding installed only by the embedded composition root."""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock

from app.domains.social.domain import SocialSearchState
from app.domains.social.ports import SocialSearchIndexPort


@dataclass(frozen=True)
class SocialSearchBinding:
    index: SocialSearchIndexPort | None
    state: SocialSearchState


_LOCK = RLock()
_BINDING = SocialSearchBinding(index=None, state=SocialSearchState.UNAVAILABLE)


def register_social_search(
    index: SocialSearchIndexPort | None,
    *,
    state: SocialSearchState,
) -> None:
    global _BINDING
    with _LOCK:
        _BINDING = SocialSearchBinding(index=index, state=state)


def current_social_search() -> SocialSearchBinding:
    with _LOCK:
        return _BINDING


def unregister_social_search(index: SocialSearchIndexPort | None) -> None:
    global _BINDING
    with _LOCK:
        if _BINDING.index is index:
            _BINDING = SocialSearchBinding(
                index=None,
                state=SocialSearchState.UNAVAILABLE,
            )


__all__ = [
    "SocialSearchBinding",
    "current_social_search",
    "register_social_search",
    "unregister_social_search",
]
