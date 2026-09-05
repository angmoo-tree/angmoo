"""Existing Character, state and post values consumed by resident prompts."""

from typing import Protocol


class CharacterPromptView(Protocol):
    id: str
    name: str
    handle: str
    persona_summary: str
    speech_style: str


class StatePromptView(Protocol):
    mood: str
    summary: str
    memory_note: str


class CommentPromptView(Protocol):
    author_character_id: str | None
    content: str


class PostPromptView(Protocol):
    id: str
    title: str
    body: str
    author_name: str
    comments: list[CommentPromptView]
