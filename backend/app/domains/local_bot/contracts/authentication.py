"""Authenticated LocalBot values and same-Session owner lookup collaboration."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from sqlalchemy.orm import Session

from app.domains.local_bot.models import AgentLocalKey


class LocalBotOwner(Protocol):
    id: str
    email: str | None
    deleted_at: datetime | None


class LocalBotCharacter(Protocol):
    id: str
    deleted_at: datetime | None
    execution_mode: str


@dataclass(frozen=True)
class LocalBotAuthenticationWorkflows:
    get_character: Callable[[Session, str], LocalBotCharacter | None]
    get_user: Callable[[Session, str], LocalBotOwner | None]


@dataclass
class LocalBotContext:
    user: LocalBotOwner
    character: LocalBotCharacter
    local_key: AgentLocalKey
