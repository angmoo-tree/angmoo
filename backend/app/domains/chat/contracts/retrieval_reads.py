"""Canonical facts consumed by Chat retrieval admission and name resolution."""

from __future__ import annotations

from typing import Protocol

from sqlalchemy.orm import Session

from app.domains.chat.contracts.context import (
    ChatCharacter,
    ChatInstallation,
    ChatWorldCharacter,
)
from app.domains.chat.contracts.retrieval_policy import RetrievalPreflightCommand


class RetrievalWorld(Protocol):
    timezone: str
    language: str


class RetrievalWorldCharacter(ChatWorldCharacter, Protocol):
    owner_user_id: str | None
    status: str


class RetrievalMembership(Protocol):
    user_id: str
    role: str
    status: str


class RetrievalPolicyReads(Protocol):
    def installation(
        self, session: Session, command: RetrievalPreflightCommand
    ) -> ChatInstallation | None: ...
    def world(
        self, session: Session, command: RetrievalPreflightCommand
    ) -> RetrievalWorld | None: ...
    def memory_enabled(
        self, session: Session, command: RetrievalPreflightCommand
    ) -> bool | None: ...
    def active_world_character(
        self, session: Session, *, world_id: str, world_character_id: str
    ) -> tuple[RetrievalWorldCharacter, ChatCharacter, RetrievalMembership] | None: ...
    def entity_mentions(
        self, session: Session, *, world_id: str, normalized: str
    ) -> list[tuple[RetrievalWorldCharacter, ChatCharacter, RetrievalMembership]]: ...
