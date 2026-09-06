"""Structural writer input and same-session context collaborators."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal, Protocol

from sqlalchemy.orm import Session

WritingKind = Literal["create_post", "reply"]


class WritingCharacter(Protocol):
    id: str
    name: str
    handle: str
    one_liner: str | None
    persona_summary: str | None
    personality: str | None
    speech_style: str | None
    worldview: str | None
    topic_preferences: str | None
    safety_rules: str | None


class WritingState(Protocol):
    mood: str
    summary: str
    memory_note: str | None


class WritingPost(Protocol):
    id: str
    title: str | None


class WritingLore(Protocol):
    chunk_ids: list[str]
    mode: str


@dataclass(frozen=True)
class WritingPromptWorkflows:
    _format_reply_context: Callable[[Session, str], str]
    _format_recent_activity: Callable[[str, Session], str]
    format_lore_prompt_context: Callable[[WritingLore], str]
