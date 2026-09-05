"""Prepared Social image result and the readonly character prompt facts."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Protocol
from app.domains.social.contracts.actors import SocialCharacter


class ImageCharacter(SocialCharacter, Protocol):
    @property
    def personality(self) -> str: ...

    @property
    def speech_style(self) -> str: ...

    @property
    def worldview(self) -> str: ...

    @property
    def topic_preferences(self) -> str: ...

    @property
    def safety_rules(self) -> str: ...



@dataclass(frozen=True)
class PreparedPostImage:
    attempt: dict[str, Any]
    content_type: str | None = None
    content: bytes | None = None
    alt_text: str | None = None
    prompt_hash: str | None = None
    model: str | None = None
    key_source: str = "none"
    quota_reservation_id: int | None = None

    @property
    def ready(self) -> bool:
        return (
            self.attempt.get("status") == "ready"
            and self.content_type is not None
            and self.content is not None
            and self.alt_text is not None
            and self.prompt_hash is not None
            and self.model is not None
        )


class ImageReferenceLocation(Protocol):
    @property
    def public_url(self) -> str | None: ...
